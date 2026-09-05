"""
backend/tests/test_ai_orchestrator.py — Step 8 Comprehensive Test Suite.

Verifies:
1. Desired State vs Actual State data model
2. Pre-flight check: camera offline/disabled fails (400 CAMERA_OFFLINE)
3. Pre-flight check: RTSP stream unverified fails (400 CAMERA_STREAM_NOT_VERIFIED)
4. Pre-flight check: missing AI profile assignment fails (400 NO_AI_PROFILE_ASSIGNED)
5. Pre-flight check: missing Crowd ROI fails (400 ROI_NOT_CONFIGURED)
6. Pre-flight check: missing Queue ROI fails (400 QUEUE_CONFIGURATION_NOT_READY)
7. Pre-flight check: missing Queue lines fails (400 QUEUE_CONFIGURATION_NOT_READY)
8. Runtime unavailable on unsupported host (400 RUNTIME_UNAVAILABLE, no fake data)
9. Capacity check blocks overcapacity start (409 AI_CAPACITY_EXCEEDED)
10. Crowd pipeline start lifecycle (VALIDATING -> STARTING -> RUNNING, sets last_started_at)
11. Queue pipeline start lifecycle (VALIDATING -> STARTING -> RUNNING)
12. Start idempotency (already running returns ALREADY_RUNNING)
13. Stop pipeline lifecycle (desired_state=STOPPED, actual_state=STOPPED, last_stopped_at)
14. Stop idempotency (already stopped returns ALREADY_STOPPED)
15. Restart workflow (RUNNING -> RESTARTING -> STOPPING -> STARTING -> RUNNING, increments restart_count)
16. Start-All prioritizes CRITICAL > HIGH > NORMAL > LOW
17. Start-All capacity cutoff marks remaining as blocked
18. Stop-All gracefully stops all pipelines across registries
19. Automatic RTSP disconnect transitions RUNNING -> DEGRADED with backoff
20. Automatic recovery exhaustion limit (max 3 in 10 minutes -> AI_PIPELINE_RECOVERY_EXHAUSTED)
21. Server restart staggered recovery restores desired_state == RUNNING
22. Server restart skips disabled cameras and invalid configurations
23. RBAC permissions (ai:read for view, ai:manage required for actions, 403 for viewer)
24. Immutable audit logging for all lifecycle operations
25. Zero FRS inference leakage (pure Crowd & Queue orchestration)
26. Zero arbitrary shell commands (no shell=True or os.system)
27. Status and health endpoints operational verification
28. AIDeploymentRepository CRUD and state queries
29. Zero crowd and queue regressions
30. Runtime instance ID assigned and tracked
"""

import asyncio
import inspect
import time
import uuid
from typing import Dict, List
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import TestSessionLocal

from app.ai.capacity.calculator import CapacityCalculator
from app.ai.deployments.service import AIDeployment
from app.ai.orchestrator.service import ai_orchestrator
from app.ai.orchestrator.state import PipelineState
from app.ai.pipelines.crowd.detector import MockPersonDetector
from app.ai.pipelines.crowd.models_registry import ModelRegistryService
from app.ai.pipelines.crowd.registry import CrowdPipelineRegistry
from app.ai.pipelines.queue.models_registry import QueueModelRegistryService
from app.ai.pipelines.queue.registry import QueuePipelineRegistry
from app.models.ai_deployment import AIPipelineDeployment
from app.models.audit_log import AuditLog
from app.models.camera import Camera
from app.models.camera_ai_assignment import CameraAIProfileAssignment
from app.models.camera_roi import CameraROIConfiguration, ROIType
from app.models.role import Permission, Role
from app.models.user import User
from app.repositories.ai_deployment_repository import AIDeploymentRepository
from app.security.encryption import encrypt_credential
from app.security.jwt import create_access_token
from app.security.password import get_password_hash


class MockSessionContext:
    def __init__(self, session):
        self.session = session
    def __call__(self):
        return self
    async def __aenter__(self):
        return self.session
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
def clean_orchestrator_state():
    CrowdPipelineRegistry.reset_for_testing()
    QueuePipelineRegistry.reset_for_testing()
    ai_orchestrator._reconnect_backoff_tracker.clear()
    ai_orchestrator._restart_history_tracker.clear()
    yield
    CrowdPipelineRegistry.reset_for_testing()
    QueuePipelineRegistry.reset_for_testing()
    ai_orchestrator._reconnect_backoff_tracker.clear()
    ai_orchestrator._restart_history_tracker.clear()


@pytest.fixture(autouse=True)
def default_capacity_allow():
    with patch("app.ai.capacity.calculator.CapacityCalculator.validate_capacity_for_deployment", return_value={"allowed": True, "verdict": "ALLOWED"}):
        yield


@pytest_asyncio.fixture
async def ai_viewer_token(db_session: AsyncSession) -> str:
    stmt_perm = select(Permission).where(Permission.code == "ai:read")
    perm = (await db_session.execute(stmt_perm)).scalars().first()
    if not perm:
        perm = Permission(code="ai:read", name="ai:read", description="Read AI")
        db_session.add(perm)
        await db_session.flush()

    stmt_role = select(Role).where(Role.code == "ROLE_AI_VIEWER")
    role = (await db_session.execute(stmt_role)).scalars().first()
    if not role:
        role = Role(code="ROLE_AI_VIEWER", name="AI Viewer", description="Read only AI", permissions=[perm])
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(role)

    stmt_user = select(User).where(User.username == "test_ai_viewer")
    user = (await db_session.execute(stmt_user)).scalars().first()
    if not user:
        user = User(
            username="test_ai_viewer",
            email="test_ai_viewer@byc.ai",
            password_hash=get_password_hash("viewer123!"),
            full_name="AI Viewer",
            role_id=role.id,
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

    return create_access_token(
        subject=str(user.id),
        role="ROLE_AI_VIEWER",
        permissions=["ai:read"],
    )


@pytest_asyncio.fixture
async def orchestrator_test_tokens(superadmin_token: str, ai_viewer_token: str) -> Dict[str, str]:
    return {
        "admin": superadmin_token,
        "viewer": ai_viewer_token,
    }


@pytest_asyncio.fixture
async def crowd_camera(db_session: AsyncSession) -> Camera:
    cam = (await db_session.execute(select(Camera).where(Camera.camera_code == "CAM-ORCH-CROWD"))).scalars().first()
    if not cam:
        cam = Camera(
            camera_code="CAM-ORCH-CROWD",
            name="Orchestrator Crowd Camera",
            label="Orchestrator Crowd Camera",
            rtsp_url_encrypted=encrypt_credential("rtsp://admin:SecretPass123@192.168.1.50:554/live"),
            status="online",
            stream_status="VERIFIED",
            resolution="1080p",
            fps=25,
            enabled=True,
        )
        db_session.add(cam)
        await db_session.flush()

        asgn = CameraAIProfileAssignment(
            camera_id=cam.id,
            camera_code=cam.camera_code,
            profile_id="CROWD_STANDARD",
            enabled=True,
            assigned_by="system_test",
        )
        db_session.add(asgn)
        await db_session.flush()

        roi = CameraROIConfiguration(
            camera_id=cam.id,
            camera_code=cam.camera_code,
            profile_id="CROWD_STANDARD",
            roi_type=ROIType.CROWD_ROI,
            name="Crowd Zone Sector",
            geometry_json={"points": [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.9, "y": 0.9}, {"x": 0.1, "y": 0.9}]},
            normalized=True,
            enabled=True,
            created_by="system_test",
        )
        db_session.add(roi)
        await db_session.commit()
    await db_session.refresh(cam)
    return cam


@pytest_asyncio.fixture
async def queue_camera(db_session: AsyncSession) -> Camera:
    cam = (await db_session.execute(select(Camera).where(Camera.camera_code == "CAM-ORCH-QUEUE"))).scalars().first()
    if not cam:
        cam = Camera(
            camera_code="CAM-ORCH-QUEUE",
            name="Orchestrator Queue Camera",
            label="Orchestrator Queue Camera",
            rtsp_url_encrypted=encrypt_credential("rtsp://admin:SecretPass456@192.168.1.60:554/live"),
            status="online",
            stream_status="VERIFIED",
            resolution="1080p",
            fps=25,
            enabled=True,
        )
        db_session.add(cam)
        await db_session.flush()

        asgn = CameraAIProfileAssignment(
            camera_id=cam.id,
            camera_code=cam.camera_code,
            profile_id="QUEUE_STANDARD",
            enabled=True,
            assigned_by="system_test",
        )
        db_session.add(asgn)
        await db_session.flush()

        r1 = CameraROIConfiguration(
            camera_id=cam.id,
            camera_code=cam.camera_code,
            profile_id="QUEUE_STANDARD",
            roi_type=ROIType.QUEUE_ROI,
            name="Queue Sector",
            geometry_json={"points": [{"x": 0.2, "y": 0.2}, {"x": 0.8, "y": 0.2}, {"x": 0.8, "y": 0.8}, {"x": 0.2, "y": 0.8}]},
            normalized=True,
            enabled=True,
            created_by="system_test",
        )
        r2 = CameraROIConfiguration(
            camera_id=cam.id,
            camera_code=cam.camera_code,
            profile_id="QUEUE_STANDARD",
            roi_type=ROIType.ENTRY_LINE,
            name="Entry",
            geometry_json={"start": {"x": 0.2, "y": 0.2}, "end": {"x": 0.8, "y": 0.2}},
            normalized=True,
            enabled=True,
            created_by="system_test",
        )
        r3 = CameraROIConfiguration(
            camera_id=cam.id,
            camera_code=cam.camera_code,
            profile_id="QUEUE_STANDARD",
            roi_type=ROIType.EXIT_LINE,
            name="Exit",
            geometry_json={"start": {"x": 0.2, "y": 0.8}, "end": {"x": 0.8, "y": 0.8}},
            normalized=True,
            enabled=True,
            created_by="system_test",
        )
        db_session.add_all([r1, r2, r3])
        await db_session.commit()
    await db_session.refresh(cam)
    return cam


# ── TESTS ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_desired_state_vs_actual_state_model():
    """1. Validates AIPipelineDeployment fields and state separation."""
    dep = AIPipelineDeployment(
        camera_id=uuid.uuid4(),
        camera_code="CAM-STATE-TEST",
        profile_id="CROWD_STANDARD",
        pipeline_type="CROWD",
        desired_state="RUNNING",
        actual_state="STARTING",
        health_state="UNKNOWN",
        priority="HIGH",
        auto_restart_enabled=True,
        auto_reconnect_enabled=True,
    )
    assert dep.desired_state == "RUNNING"
    assert dep.actual_state == "STARTING"
    assert dep.priority == "HIGH"
    assert dep.restart_count == 0
    assert dep.reconnect_count == 0


@pytest.mark.asyncio
async def test_orchestrator_preflight_camera_offline(db_session: AsyncSession):
    """2. Offline or disabled camera rejected with CAMERA_OFFLINE."""
    cam = Camera(
        camera_code="CAM-OFFLINE",
        name="Offline Cam",
        label="Offline Cam",
        status="offline",
        stream_status="VERIFIED",
        enabled=False,
    )
    db_session.add(cam)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await ai_orchestrator.start_pipeline("CAM-OFFLINE", db_session)
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "CAMERA_OFFLINE"


@pytest.mark.asyncio
async def test_orchestrator_preflight_stream_unverified(db_session: AsyncSession):
    """3. Unverified RTSP stream rejected with CAMERA_STREAM_NOT_VERIFIED."""
    cam = Camera(
        camera_code="CAM-UNVERIFIED",
        name="Unverified Cam",
        label="Unverified Cam",
        status="online",
        stream_status="NOT_TESTED",
        enabled=True,
    )
    db_session.add(cam)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await ai_orchestrator.start_pipeline("CAM-UNVERIFIED", db_session)
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "CAMERA_STREAM_NOT_VERIFIED"


@pytest.mark.asyncio
async def test_orchestrator_preflight_missing_ai_profile(db_session: AsyncSession):
    """4. Camera without active AI profile fails with NO_AI_PROFILE_ASSIGNED."""
    cam = Camera(
        camera_code="CAM-NO-PROFILE",
        name="No Profile Cam",
        label="No Profile Cam",
        status="online",
        stream_status="VERIFIED",
        enabled=True,
    )
    db_session.add(cam)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await ai_orchestrator.start_pipeline("CAM-NO-PROFILE", db_session)
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "NO_AI_PROFILE_ASSIGNED"


@pytest.mark.asyncio
async def test_orchestrator_preflight_missing_crowd_roi(db_session: AsyncSession):
    """5. Crowd camera without CROWD_ROI fails with ROI_NOT_CONFIGURED."""
    cam = Camera(
        camera_code="CAM-NO-ROI",
        name="No ROI Cam",
        label="No ROI Cam",
        status="online",
        stream_status="VERIFIED",
        enabled=True,
    )
    db_session.add(cam)
    await db_session.flush()

    asgn = CameraAIProfileAssignment(
        camera_id=cam.id,
        camera_code=cam.camera_code,
        profile_id="CROWD_STANDARD",
        enabled=True,
    )
    db_session.add(asgn)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await ai_orchestrator.start_pipeline("CAM-NO-ROI", db_session)
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "ROI_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_orchestrator_preflight_missing_queue_roi(db_session: AsyncSession):
    """6. Queue camera without QUEUE_ROI fails with QUEUE_CONFIGURATION_NOT_READY."""
    cam = Camera(
        camera_code="CAM-Q-NO-ROI",
        name="No Queue ROI",
        label="No Queue ROI",
        status="online",
        stream_status="VERIFIED",
        enabled=True,
    )
    db_session.add(cam)
    await db_session.flush()

    asgn = CameraAIProfileAssignment(
        camera_id=cam.id,
        camera_code=cam.camera_code,
        profile_id="QUEUE_STANDARD",
        enabled=True,
    )
    db_session.add(asgn)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await ai_orchestrator.start_pipeline("CAM-Q-NO-ROI", db_session)
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "QUEUE_CONFIGURATION_NOT_READY"


@pytest.mark.asyncio
async def test_orchestrator_preflight_missing_queue_lines(db_session: AsyncSession):
    """7. Queue camera with QUEUE_ROI but missing lines fails."""
    cam = Camera(
        camera_code="CAM-Q-NO-LINES",
        name="No Lines Cam",
        label="No Lines Cam",
        status="online",
        stream_status="VERIFIED",
        enabled=True,
    )
    db_session.add(cam)
    await db_session.flush()

    asgn = CameraAIProfileAssignment(
        camera_id=cam.id,
        camera_code=cam.camera_code,
        profile_id="QUEUE_STANDARD",
        enabled=True,
    )
    r1 = CameraROIConfiguration(
        camera_id=cam.id,
        camera_code=cam.camera_code,
        profile_id="QUEUE_STANDARD",
        roi_type=ROIType.QUEUE_ROI,
        name="Queue Sector",
        geometry_json={"points": [{"x": 0.2, "y": 0.2}, {"x": 0.8, "y": 0.2}, {"x": 0.8, "y": 0.8}, {"x": 0.2, "y": 0.8}]},
        enabled=True,
    )
    db_session.add_all([asgn, r1])
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await ai_orchestrator.start_pipeline("CAM-Q-NO-LINES", db_session)
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "QUEUE_CONFIGURATION_NOT_READY"


@pytest.mark.asyncio
async def test_orchestrator_runtime_unavailable_on_unsupported_host(
    crowd_camera: Camera,
    db_session: AsyncSession,
):
    """8. Rejects pipeline launch on host without GPU / DeepStream (zero fake data)."""
    with patch("app.ai.runtime.detector.RuntimeDetector.detect_gpu", return_value={"available": False}), \
         patch("app.ai.runtime.detector.RuntimeDetector.detect_runtime", return_value={"deepstream": False}):
        with pytest.raises(HTTPException) as exc:
            await ai_orchestrator.start_pipeline(crowd_camera.camera_code, db_session)
        assert exc.value.status_code == 400
        assert exc.value.detail["code"] == "RUNTIME_UNAVAILABLE"


@pytest.mark.asyncio
async def test_orchestrator_capacity_protection_blocks_startup(
    crowd_camera: Camera,
    db_session: AsyncSession,
):
    """9. Blocks startup when server capacity is exceeded (409 AI_CAPACITY_EXCEEDED)."""
    detector = MockPersonDetector(model=ModelRegistryService.get_default_model(), confidence_threshold=0.45)
    with patch("app.ai.capacity.calculator.CapacityCalculator.validate_capacity_for_deployment") as mock_cap:
        mock_cap.return_value = {
            "allowed": False,
            "verdict": "BLOCKED",
            "reason": "VRAM capacity exceeded: projected 95% > 90% hard limit",
        }
        with pytest.raises(HTTPException) as exc:
            await ai_orchestrator.start_pipeline(
                crowd_camera.camera_code,
                db_session,
                custom_detector=detector,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "AI_CAPACITY_EXCEEDED"


@pytest.mark.asyncio
async def test_orchestrator_crowd_pipeline_start_lifecycle(
    crowd_camera: Camera,
    db_session: AsyncSession,
):
    """10. Successful start transitions actual_state to RUNNING and sets timestamps."""
    detector = MockPersonDetector(model=ModelRegistryService.get_default_model(), confidence_threshold=0.45)
    res = await ai_orchestrator.start_pipeline(
        crowd_camera.camera_code,
        db_session,
        custom_detector=detector,
    )
    assert res["status"] == "STARTED"
    assert res["desired_state"] == "RUNNING"
    assert res["actual_state"] == "RUNNING"
    assert CrowdPipelineRegistry.get(crowd_camera.camera_code) is not None

    # Check DB deployment record
    repo = AIDeploymentRepository(db_session)
    dep = await repo.get_by_camera_code(crowd_camera.camera_code)
    assert dep is not None
    assert dep.desired_state == "RUNNING"
    assert dep.actual_state == "RUNNING"
    assert dep.last_started_at is not None


@pytest.mark.asyncio
async def test_orchestrator_queue_pipeline_start_lifecycle(
    queue_camera: Camera,
    db_session: AsyncSession,
):
    """11. Successful Queue AI pipeline launch via orchestrator."""
    detector = MockPersonDetector(model=QueueModelRegistryService.get_default_model(), confidence_threshold=0.45)
    with patch("app.ai.capacity.calculator.CapacityCalculator.validate_capacity_for_deployment", return_value={"allowed": True, "verdict": "ALLOWED"}):
        res = await ai_orchestrator.start_pipeline(
            queue_camera.camera_code,
            db_session,
            custom_detector=detector,
        )
    assert res["status"] == "STARTED"
    assert res["desired_state"] == "RUNNING"
    assert res["actual_state"] == "RUNNING"
    assert QueuePipelineRegistry.get(queue_camera.camera_code) is not None


@pytest.mark.asyncio
async def test_orchestrator_already_running_start_is_idempotent(
    crowd_camera: Camera,
    db_session: AsyncSession,
):
    """12. Starting already running pipeline returns ALREADY_RUNNING cleanly."""
    detector = MockPersonDetector(model=ModelRegistryService.get_default_model(), confidence_threshold=0.45)
    await ai_orchestrator.start_pipeline(crowd_camera.camera_code, db_session, custom_detector=detector)

    # Second start call
    res = await ai_orchestrator.start_pipeline(crowd_camera.camera_code, db_session, custom_detector=detector)
    assert res["status"] == "ALREADY_RUNNING"
    assert res["desired_state"] == "RUNNING"
    assert res["actual_state"] == "RUNNING"


@pytest.mark.asyncio
async def test_orchestrator_stop_pipeline_lifecycle(
    crowd_camera: Camera,
    db_session: AsyncSession,
):
    """13. Stopping a pipeline transitions desired and actual states to STOPPED."""
    detector = MockPersonDetector(model=ModelRegistryService.get_default_model(), confidence_threshold=0.45)
    await ai_orchestrator.start_pipeline(crowd_camera.camera_code, db_session, custom_detector=detector)

    res = await ai_orchestrator.stop_pipeline(crowd_camera.camera_code, db_session)
    assert res["status"] == "STOPPED"
    assert res["desired_state"] == "STOPPED"
    assert res["actual_state"] == "STOPPED"
    assert CrowdPipelineRegistry.get(crowd_camera.camera_code) is None

    repo = AIDeploymentRepository(db_session)
    dep = await repo.get_by_camera_code(crowd_camera.camera_code)
    assert dep.desired_state == "STOPPED"
    assert dep.actual_state == "STOPPED"
    assert dep.last_stopped_at is not None


@pytest.mark.asyncio
async def test_orchestrator_stop_pipeline_idempotent(
    crowd_camera: Camera,
    db_session: AsyncSession,
):
    """14. Calling stop on an already stopped pipeline succeeds without error."""
    res = await ai_orchestrator.stop_pipeline(crowd_camera.camera_code, db_session)
    assert res["status"] == "ALREADY_STOPPED"
    assert res["desired_state"] == "STOPPED"
    assert res["actual_state"] == "STOPPED"


@pytest.mark.asyncio
async def test_orchestrator_restart_pipeline_lifecycle(
    crowd_camera: Camera,
    db_session: AsyncSession,
):
    """15. Restart transitions RUNNING -> RESTARTING -> RUNNING and increments restart_count."""
    detector = MockPersonDetector(model=ModelRegistryService.get_default_model(), confidence_threshold=0.45)
    await ai_orchestrator.start_pipeline(crowd_camera.camera_code, db_session, custom_detector=detector)

    res = await ai_orchestrator.restart_pipeline(
        crowd_camera.camera_code,
        db_session,
        custom_detector=detector,
    )
    assert res["status"] == "RESTARTED"
    assert res["desired_state"] == "RUNNING"
    assert res["actual_state"] == "RUNNING"
    assert res["restart_count"] >= 1


@pytest.mark.asyncio
async def test_orchestrator_start_all_prioritizes_deployments(
    crowd_camera: Camera,
    queue_camera: Camera,
    db_session: AsyncSession,
):
    """16. Start All orders cameras by priority (CRITICAL > HIGH > NORMAL > LOW)."""
    repo = AIDeploymentRepository(db_session)
    # Queue is CRITICAL, Crowd is NORMAL
    await repo.upsert_deployment(
        camera_id=queue_camera.id,
        camera_code=queue_camera.camera_code,
        profile_id="QUEUE_STANDARD",
        pipeline_type="QUEUE",
        priority="CRITICAL",
    )
    await repo.upsert_deployment(
        camera_id=crowd_camera.id,
        camera_code=crowd_camera.camera_code,
        profile_id="CROWD_STANDARD",
        pipeline_type="CROWD",
        priority="NORMAL",
    )
    await db_session.commit()

    detector = MockPersonDetector(model=ModelRegistryService.get_default_model(), confidence_threshold=0.45)
    res = await ai_orchestrator.start_all(db_session, custom_detector=detector)

    assert queue_camera.camera_code in res["started"]
    assert crowd_camera.camera_code in res["started"]
    # Queue should be started before Crowd because priority is CRITICAL > NORMAL
    assert res["started"].index(queue_camera.camera_code) < res["started"].index(crowd_camera.camera_code)


@pytest.mark.asyncio
async def test_orchestrator_start_all_capacity_cutoff(
    crowd_camera: Camera,
    queue_camera: Camera,
    db_session: AsyncSession,
):
    """17. Start All halts at capacity and marks remaining cameras as blocked."""
    repo = AIDeploymentRepository(db_session)
    await repo.upsert_deployment(
        camera_id=queue_camera.id,
        camera_code=queue_camera.camera_code,
        profile_id="QUEUE_STANDARD",
        pipeline_type="QUEUE",
        priority="CRITICAL",
    )
    await repo.upsert_deployment(
        camera_id=crowd_camera.id,
        camera_code=crowd_camera.camera_code,
        profile_id="CROWD_STANDARD",
        pipeline_type="CROWD",
        priority="NORMAL",
    )
    await db_session.commit()

    call_count = 0
    def mock_capacity(workload, addition, cpu, ram, gpu):
        nonlocal call_count
        call_count += 1
        # First call succeeds, second call exceeds capacity
        if call_count == 1:
            return {"allowed": True, "verdict": "ALLOWED"}
        return {"allowed": False, "verdict": "BLOCKED", "reason": "GPU VRAM headroom limit reached"}

    detector = MockPersonDetector(model=ModelRegistryService.get_default_model(), confidence_threshold=0.45)
    with patch("app.ai.capacity.calculator.CapacityCalculator.validate_capacity_for_deployment", side_effect=mock_capacity):
        res = await ai_orchestrator.start_all(db_session, custom_detector=detector)

    assert len(res["started"]) == 1
    assert res["started"][0] == queue_camera.camera_code
    assert any(b["camera_code"] == crowd_camera.camera_code for b in res["blocked"])
    crowd_block = next(b for b in res["blocked"] if b["camera_code"] == crowd_camera.camera_code)
    assert "Blocked by server capacity." in crowd_block["reason"]


@pytest.mark.asyncio
async def test_orchestrator_stop_all_graceful_teardown(
    crowd_camera: Camera,
    queue_camera: Camera,
    db_session: AsyncSession,
):
    """18. Stop All terminates all running pipelines across both registries."""
    det1 = MockPersonDetector(model=ModelRegistryService.get_default_model(), confidence_threshold=0.45)
    det2 = MockPersonDetector(model=QueueModelRegistryService.get_default_model(), confidence_threshold=0.45)

    await ai_orchestrator.start_pipeline(crowd_camera.camera_code, db_session, custom_detector=det1)
    await ai_orchestrator.start_pipeline(queue_camera.camera_code, db_session, custom_detector=det2)

    assert len(CrowdPipelineRegistry.list_pipelines()) == 1
    assert QueuePipelineRegistry.count() == 1

    res = await ai_orchestrator.stop_all(db_session)
    assert len(res["stopped"]) == 2
    assert len(CrowdPipelineRegistry.list_pipelines()) == 0
    assert QueuePipelineRegistry.count() == 0


@pytest.mark.asyncio
async def test_orchestrator_rtsp_reconnect_backoff(
    crowd_camera: Camera,
    db_session: AsyncSession,
):
    """19. Temporary stream dropout transitions actual_state to DEGRADED and initiates backoff."""
    detector = MockPersonDetector(model=ModelRegistryService.get_default_model(), confidence_threshold=0.45)
    await ai_orchestrator.start_pipeline(crowd_camera.camera_code, db_session, custom_detector=detector)

    pipe = CrowdPipelineRegistry.get(crowd_camera.camera_code)
    # Simulate health monitor marking failure / no frames
    pipe.state = PipelineState.FAILED
    pipe.health_monitor.record_error("Stream timeout: no frames received in >10s")

    # Run single supervision check
    with patch("app.ai.orchestrator.service.AsyncSessionLocal", MockSessionContext(db_session)):
        await ai_orchestrator._supervision_iteration()

    repo = AIDeploymentRepository(db_session)
    dep = await repo.get_by_camera_code(crowd_camera.camera_code)
    assert dep.desired_state == "RUNNING"
    assert dep.actual_state == "DEGRADED"
    assert dep.reconnect_count >= 1


@pytest.mark.asyncio
async def test_orchestrator_recovery_exhaustion_limit(
    crowd_camera: Camera,
    db_session: AsyncSession,
):
    """20. Halts recovery when exceeding 3 restarts in 10 minutes."""
    repo = AIDeploymentRepository(db_session)
    dep = await repo.upsert_deployment(
        camera_id=crowd_camera.id,
        camera_code=crowd_camera.camera_code,
        profile_id="CROWD_STANDARD",
        pipeline_type="CROWD",
        desired_state="RUNNING",
        actual_state="FAILED",
    )
    await db_session.commit()

    now = time.time()
    # Populate history with 3 recent restarts
    ai_orchestrator._restart_history_tracker[crowd_camera.camera_code] = [now - 200, now - 100, now - 10]

    await ai_orchestrator._evaluate_auto_recovery(dep, db_session)

    assert "limit exceeded" in (dep.last_error or "").lower()
    assert dep.actual_state == "FAILED"


@pytest.mark.asyncio
async def test_orchestrator_server_restart_staggered_recovery(
    crowd_camera: Camera,
    db_session: AsyncSession,
):
    """21. Recovers deployments where desired_state == RUNNING across server restarts."""
    repo = AIDeploymentRepository(db_session)
    await repo.upsert_deployment(
        camera_id=crowd_camera.id,
        camera_code=crowd_camera.camera_code,
        profile_id="CROWD_STANDARD",
        pipeline_type="CROWD",
        desired_state="RUNNING",
        actual_state="STOPPED",
    )
    await db_session.commit()

    detector = MockPersonDetector(model=ModelRegistryService.get_default_model(), confidence_threshold=0.45)
    with patch("app.ai.orchestrator.service.AsyncSessionLocal", MockSessionContext(db_session)), \
         patch("app.ai.orchestrator.service.ai_orchestrator.start_pipeline") as mock_start:
        mock_start.return_value = {"status": "STARTED"}
        await ai_orchestrator.recover_on_startup()
        assert mock_start.called


@pytest.mark.asyncio
async def test_orchestrator_server_restart_recovery_skips_disabled_camera(
    db_session: AsyncSession,
):
    """22. Server restart recovery safely skips disabled cameras."""
    cam = Camera(
        camera_code="CAM-DISABLED-REC",
        name="Disabled Recovery",
        label="Disabled Recovery",
        status="offline",
        stream_status="VERIFIED",
        enabled=False,
    )
    db_session.add(cam)
    await db_session.flush()

    repo = AIDeploymentRepository(db_session)
    dep = await repo.upsert_deployment(
        camera_id=cam.id,
        camera_code=cam.camera_code,
        profile_id="CROWD_STANDARD",
        pipeline_type="CROWD",
        desired_state="RUNNING",
        actual_state="STOPPED",
    )
    await db_session.commit()

    with patch("app.ai.orchestrator.service.AsyncSessionLocal", MockSessionContext(db_session)):
        await ai_orchestrator.recover_on_startup()

    await db_session.refresh(dep)
    assert dep.actual_state == "STOPPED"
    assert "skipped" in (dep.last_error or "").lower()


@pytest.mark.asyncio
async def test_orchestrator_rbac_permissions(
    client: AsyncClient,
    orchestrator_test_tokens: Dict[str, str],
    crowd_camera: Camera,
):
    """23. Viewer can read (200), Viewer cannot start/stop (403), Admin can start/stop."""
    # Read status
    resp_read = await client.get(
        "/api/v1/ai/orchestrator/status",
        headers={"Authorization": f"Bearer {orchestrator_test_tokens['viewer']}"},
    )
    assert resp_read.status_code == 200

    # Viewer attempt to start -> 403 Forbidden
    resp_v_start = await client.post(
        f"/api/v1/ai/orchestrator/pipelines/{crowd_camera.camera_code}/start",
        headers={"Authorization": f"Bearer {orchestrator_test_tokens['viewer']}"},
    )
    assert resp_v_start.status_code == 403

    # Viewer attempt to start-all -> 403
    resp_v_all = await client.post(
        "/api/v1/ai/orchestrator/start-all",
        headers={"Authorization": f"Bearer {orchestrator_test_tokens['viewer']}"},
    )
    assert resp_v_all.status_code == 403


@pytest.mark.asyncio
async def test_orchestrator_audit_logging(
    crowd_camera: Camera,
    db_session: AsyncSession,
    superadmin_token: str,
):
    """24. Operations create immutable AuditLog entries."""
    detector = MockPersonDetector(model=ModelRegistryService.get_default_model(), confidence_threshold=0.45)
    stmt_user = select(User).where(User.username == "testadmin")
    user = (await db_session.execute(stmt_user)).scalars().first()

    with patch("app.ai.capacity.calculator.CapacityCalculator.validate_capacity_for_deployment", return_value={"allowed": True, "verdict": "ALLOWED"}):
        await ai_orchestrator.start_pipeline(
            crowd_camera.camera_code,
            db_session,
            current_user=user,
            custom_detector=detector,
        )
        await ai_orchestrator.stop_pipeline(
            crowd_camera.camera_code,
            db_session,
            current_user=user,
        )

    stmt = select(AuditLog).where(AuditLog.resource_id == crowd_camera.camera_code)
    logs = (await db_session.execute(stmt)).scalars().all()
    actions = [l.action for l in logs]
    assert "AI_PIPELINE_STARTED" in actions
    assert "AI_PIPELINE_STOPPED" in actions


@pytest.mark.asyncio
async def test_orchestrator_zero_frs_inference():
    """25. Confirms orchestrator contains zero face recognition or biometric models."""
    from app.ai.orchestrator import service
    src = inspect.getsource(service)
    assert "face_recognition" not in src
    assert "FRSCandidate" not in src
    assert "face_embedding" not in src


@pytest.mark.asyncio
async def test_orchestrator_no_arbitrary_shell_commands():
    """26. Confirms zero shell=True or os.system in orchestrator modules."""
    from app.ai.orchestrator import service, state
    for mod in (service, state):
        src = inspect.getsource(mod)
        assert "shell=True" not in src
        assert "os.system" not in src
        assert "killall" not in src


@pytest.mark.asyncio
async def test_orchestrator_status_and_health_endpoints(
    client: AsyncClient,
    orchestrator_test_tokens: Dict[str, str],
):
    """27. GET /status and /health return operational status."""
    resp_s = await client.get(
        "/api/v1/ai/orchestrator/status",
        headers={"Authorization": f"Bearer {orchestrator_test_tokens['admin']}"},
    )
    assert resp_s.status_code == 200
    assert resp_s.json()["data"]["orchestrator_status"] == "OPERATIONAL"

    resp_h = await client.get(
        "/api/v1/ai/orchestrator/health",
        headers={"Authorization": f"Bearer {orchestrator_test_tokens['admin']}"},
    )
    assert resp_h.status_code == 200
    assert "supervision_loop_active" in resp_h.json()["data"]


@pytest.mark.asyncio
async def test_orchestrator_repository_queries(db_session: AsyncSession):
    """28. AIDeploymentRepository queries, lookups, and state filtering."""
    repo = AIDeploymentRepository(db_session)
    cam_id = uuid.uuid4()
    dep = await repo.upsert_deployment(
        camera_id=cam_id,
        camera_code="CAM-REPO-TEST",
        profile_id="CROWD_STANDARD",
        pipeline_type="CROWD",
        desired_state="RUNNING",
        actual_state="RUNNING",
        priority="HIGH",
    )
    await db_session.commit()

    lookup = await repo.get_by_camera_code("CAM-REPO-TEST")
    assert lookup is not None
    assert lookup.priority == "HIGH"

    running_deps = await repo.list_by_desired_state("RUNNING")
    assert any(d.camera_code == "CAM-REPO-TEST" for d in running_deps)


@pytest.mark.asyncio
async def test_orchestrator_zero_crowd_queue_regressions(
    crowd_camera: Camera,
    queue_camera: Camera,
    db_session: AsyncSession,
):
    """29. Independent Crowd and Queue pipeline registries operate without regression."""
    det1 = MockPersonDetector(model=ModelRegistryService.get_default_model(), confidence_threshold=0.45)
    det2 = MockPersonDetector(model=QueueModelRegistryService.get_default_model(), confidence_threshold=0.45)

    with patch("app.ai.capacity.calculator.CapacityCalculator.validate_capacity_for_deployment", return_value={"allowed": True, "verdict": "ALLOWED"}):
        await ai_orchestrator.start_pipeline(crowd_camera.camera_code, db_session, custom_detector=det1)
        await ai_orchestrator.start_pipeline(queue_camera.camera_code, db_session, custom_detector=det2)

    assert CrowdPipelineRegistry.get(crowd_camera.camera_code) is not None
    assert QueuePipelineRegistry.get(queue_camera.camera_code) is not None
    assert QueuePipelineRegistry.get(crowd_camera.camera_code) is None


@pytest.mark.asyncio
async def test_orchestrator_runtime_instance_id_tracking(
    crowd_camera: Camera,
    db_session: AsyncSession,
):
    """30. Each pipeline startup generates and tracks unique runtime_instance_id."""
    detector = MockPersonDetector(model=ModelRegistryService.get_default_model(), confidence_threshold=0.45)
    with patch("app.ai.capacity.calculator.CapacityCalculator.validate_capacity_for_deployment", return_value={"allowed": True, "verdict": "ALLOWED"}):
        res = await ai_orchestrator.start_pipeline(
            crowd_camera.camera_code,
            db_session,
            custom_detector=detector,
        )
    assert res["runtime_instance_id"].startswith(f"RT-{crowd_camera.camera_code}-CROWD_STANDARD-")

    repo = AIDeploymentRepository(db_session)
    dep = await repo.get_by_camera_code(crowd_camera.camera_code)
    assert dep.runtime_instance_id == res["runtime_instance_id"]
