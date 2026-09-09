"""
test_camera_ai_assignment.py — Comprehensive Tests for Step 4:
AI Profile -> Camera Assignment & Capacity Validation.

Verifies:
1.  List AI profiles
2.  Get camera AI configuration
3.  Assign valid Crowd profile to CROWD camera
4.  Assign valid Queue profile to QUEUE camera
5.  Assign valid FRS profile to authorized FRS camera
6.  Reject FRS profile on invalid camera purpose (CROWD)
7.  Reject FRS profile on invalid camera purpose (QUEUE)
8.  Reject Crowd profile on QUEUE camera
9.  Reject duplicate profile assignment (409 Conflict)
10. Update assignment (toggle enabled / metadata)
11. Remove assignment
12. Capacity validation succeeds (ALLOWED)
13. Capacity validation blocks over-capacity (409 Conflict)
14. Mixed workload calculation
15. AI_READ permission enforcement
16. AI_MANAGE permission enforcement
17. Unauthorized FRS assignment (without FRS permission -> 403)
18. Audit event generated on assignment
19. WebSocket event emitted on configuration change
20. Camera not found (404)
21. Profile not found (404)
22. No AI inference starts during assignment
"""

import uuid
from unittest.mock import AsyncMock, patch
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.camera import Camera
from app.models.camera_ai_assignment import CameraAIProfileAssignment
from app.models.role import Permission, Role
from app.models.user import User
from app.models.zone import Zone
from app.redis.event_bus import event_bus
from app.security.jwt import create_access_token
from app.security.password import get_password_hash


# ── Helper Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_system_hardware():
    """Provides simulated high-capacity server hardware so tests run reliably across platforms."""
    cpu_data = {
        "processor": "Intel Xeon Gold 6338",
        "physical_cores": 32,
        "logical_cores": 64,
        "usage_percent": 15.0,
        "current_freq_mhz": 2800.0,
    }
    ram_data = {
        "total_gb": 128.0,
        "available_gb": 112.0,
        "used_gb": 16.0,
        "used_percent": 12.5,
        "total_bytes": 137438953472,
        "available_bytes": 120259084288,
        "used_bytes": 17179869184,
    }
    gpu_data = {
        "available": True,
        "count": 1,
        "devices": [
            {
                "index": 0,
                "name": "NVIDIA L40S",
                "uuid": "GPU-mock-1234",
                "total_vram_gb": 48.0,
                "free_vram_gb": 44.0,
                "used_vram_gb": 4.0,
                "memory_total_mb": 49152,
                "memory_free_mb": 45056,
                "memory_used_mb": 4096,
                "gpu_utilization_percent": 10.0,
                "temperature_c": 42.0,
            }
        ],
        "driver_version": "535.129.03",
        "cuda_version": "12.2",
        "status": "AVAILABLE",
        "message": "Found 1 NVIDIA GPU device(s).",
    }
    with patch("app.ai.runtime.detector.RuntimeDetector.detect_cpu", return_value=cpu_data), \
         patch("app.ai.runtime.detector.RuntimeDetector.detect_ram", return_value=ram_data), \
         patch("app.ai.runtime.detector.RuntimeDetector.detect_gpu", return_value=gpu_data):
        yield


@pytest_asyncio.fixture
async def setup_zone(db_session: AsyncSession):
    stmt = select(Zone).where(Zone.zone_code == "ZONE-STEP4-A")
    res = await db_session.execute(stmt)
    existing = res.scalars().first()
    if existing:
        return existing

    zone = Zone(
        zone_code="ZONE-STEP4-A",
        name="Precinct East Gate",
        label="East Gate Sector",
        coordinates=[[78.4635, 17.4175], [78.4640, 17.4180]],
        capacity=8000,
        status="ACTIVE",
    )
    db_session.add(zone)
    await db_session.commit()
    await db_session.refresh(zone)
    return zone


@pytest_asyncio.fixture
async def sample_cameras(db_session: AsyncSession, setup_zone):
    """Creates sample cameras with different operational purposes."""
    cams = {}
    purposes = [
        ("CAM-AI-CROWD-01", "CROWD", "East Gate Flow High Angle"),
        ("CAM-AI-QUEUE-01", "QUEUE", "VIP Barricade Queue Line"),
        ("CAM-AI-FRS-01", "FRS", "South Arch Facial Screening"),
        ("CAM-AI-GENERAL-01", "GENERAL", "Parking Perimeter Overview"),
        ("CAM-AI-MULTI-01", "MULTI_PURPOSE", "Main Concourse Multi-View"),
    ]
    for code, purp, name in purposes:
        stmt = select(Camera).where(Camera.camera_code == code)
        existing = (await db_session.execute(stmt)).scalars().first()
        if not existing:
            cam = Camera(
                camera_code=code,
                name=name,
                label=name,
                camera_type=purp,
                zone=setup_zone,
                zone_code=setup_zone.zone_code,
                zone_id=setup_zone.id,
                private_ip=f"192.168.99.{len(cams) + 50}",
                port=554,
                rtsp_url_encrypted="gAAAAABtest",
                status="online",
                stream_status="ONLINE",
                stream_stability="STABLE",
                enabled=True,
            )
            db_session.add(cam)
            await db_session.flush()
            await db_session.refresh(cam)
            cams[purp] = cam
        else:
            cams[purp] = existing
    await db_session.commit()
    return cams


@pytest_asyncio.fixture
async def read_only_token(db_session: AsyncSession) -> str:
    """User with AI_READ and CAMERA_READ only (no AI_MANAGE, no FRS_MANAGE)."""
    stmt = select(Role).where(Role.code == "ROLE_VIEWER")
    role = (await db_session.execute(stmt)).scalars().first()
    if not role:
        perms = []
        for p_code in ["ai:read", "camera:read"]:
            perm = (await db_session.execute(select(Permission).where(Permission.code == p_code))).scalars().first()
            if not perm:
                perm = Permission(code=p_code, name=p_code)
                db_session.add(perm)
                await db_session.flush()
            perms.append(perm)

        role = Role(code="ROLE_VIEWER", name="Viewer Role", description="Read only", permissions=perms)
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(role)

    stmt_u = select(User).where(User.username == "viewer_user")
    user = (await db_session.execute(stmt_u)).scalars().first()
    if not user:
        user = User(
            username="viewer_user",
            email="viewer@byc.gov.in",
            password_hash=get_password_hash("viewer123"),
            full_name="Viewer User",
            role_id=role.id,
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

    return create_access_token(
        subject=str(user.id),
        role="ROLE_VIEWER",
        permissions=["ai:read", "camera:read"],
    )


@pytest_asyncio.fixture
async def ai_manager_no_frs_token(db_session: AsyncSession) -> str:
    """User with AI_MANAGE and CAMERA_MANAGE but NO FRS permissions."""
    stmt = select(Role).where(Role.code == "ROLE_AI_NO_FRS")
    role = (await db_session.execute(stmt)).scalars().first()
    if not role:
        perms = []
        for p_code in ["ai:manage", "ai:read", "camera:read", "camera:manage"]:
            perm = (await db_session.execute(select(Permission).where(Permission.code == p_code))).scalars().first()
            if not perm:
                perm = Permission(code=p_code, name=p_code)
                db_session.add(perm)
                await db_session.flush()
            perms.append(perm)

        role = Role(code="ROLE_AI_NO_FRS", name="AI Operator No FRS", description="AI Manage without FRS", permissions=perms)
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(role)

    stmt_u = select(User).where(User.username == "ai_no_frs_user")
    user = (await db_session.execute(stmt_u)).scalars().first()
    if not user:
        user = User(
            username="ai_no_frs_user",
            email="ainofrs@byc.gov.in",
            password_hash=get_password_hash("operator123"),
            full_name="AI Operator No FRS",
            role_id=role.id,
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

    return create_access_token(
        subject=str(user.id),
        role="ROLE_AI_NO_FRS",
        permissions=["ai:read", "ai:manage", "camera:read", "camera:manage"],
    )


# ── 1. List AI Profiles ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_ai_profiles(client: AsyncClient, superadmin_token: str):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    res = await client.get("/api/v1/ai/profiles", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    profiles = data["data"]
    assert len(profiles) >= 5
    profile_ids = [p["profile_id"] for p in profiles]
    assert "CROWD_STANDARD" in profile_ids
    assert "CROWD_HIGH_DENSITY" in profile_ids
    assert "QUEUE_STANDARD" in profile_ids
    assert "FRS_STANDARD" in profile_ids
    assert "VIDEO_SAFETY" in profile_ids

    # Verify workload estimate structure
    crowd = next(p for p in profiles if p["profile_id"] == "CROWD_STANDARD")
    assert "workload" in crowd
    assert crowd["workload"]["estimated_gpu_load_percent"] > 0
    assert crowd["workload"]["estimated_vram_gb"] > 0


# ── 2. Get Camera AI Configuration ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_camera_ai_config_empty(client: AsyncClient, superadmin_token: str, sample_cameras):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam = sample_cameras["CROWD"]
    res = await client.get(f"/api/v1/cameras/{cam.camera_code}/ai-config", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    config = data["data"]
    assert config["camera_id"] == cam.camera_code
    assert config["camera_purpose"] == "CROWD"
    assert config["assignments"] == []
    assert len(config["available_profiles"]) >= 5

    # CROWD_STANDARD must be compatible
    crowd_prof = next(p for p in config["available_profiles"] if p["profile_id"] == "CROWD_STANDARD")
    assert crowd_prof["compatible"] is True

    # FRS_STANDARD must NOT be compatible with CROWD camera
    frs_prof = next(p for p in config["available_profiles"] if p["profile_id"] == "FRS_STANDARD")
    assert frs_prof["compatible"] is False

    # Check deployment projection
    assert "deployment_projection" in config
    assert "current_usage" in config["deployment_projection"]


# ── 3. Assign Valid Profiles ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_assign_valid_crowd_profile(client: AsyncClient, superadmin_token: str, sample_cameras):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam = sample_cameras["CROWD"]
    payload = {
        "profile_id": "CROWD_STANDARD",
        "enabled": True,
        "metadata_json": {"confidence_threshold": 0.45},
    }
    res = await client.post(f"/api/v1/cameras/{cam.camera_code}/ai-config", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["success"] is True
    asgn = data["data"]
    assert asgn["camera_code"] == cam.camera_code
    assert asgn["profile_id"] == "CROWD_STANDARD"
    assert asgn["enabled"] is True
    assert asgn["validation_status"] in ("HEALTHY", "VALID", "LIMIT_REACHED", "WARNING")
    assert asgn["workload_estimate"] is not None


@pytest.mark.asyncio
async def test_assign_valid_queue_profile(client: AsyncClient, superadmin_token: str, sample_cameras):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam = sample_cameras["QUEUE"]
    payload = {
        "profile_id": "QUEUE_STANDARD",
        "enabled": True,
        "metadata_json": {"max_queue_length_meters": 50},
    }
    res = await client.post(f"/api/v1/cameras/{cam.camera_code}/ai-config", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["success"] is True
    assert data["data"]["profile_id"] == "QUEUE_STANDARD"


@pytest.mark.asyncio
async def test_assign_valid_frs_profile_to_frs_camera(client: AsyncClient, superadmin_token: str, sample_cameras):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam = sample_cameras["FRS"]
    payload = {
        "profile_id": "FRS_STANDARD",
        "enabled": True,
    }
    res = await client.post(f"/api/v1/cameras/{cam.camera_code}/ai-config", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["success"] is True
    assert data["data"]["profile_id"] == "FRS_STANDARD"


# ── 4. Compatibility & Isolation Rejections ───────────────────────────────────

@pytest.mark.asyncio
async def test_reject_frs_profile_on_crowd_camera(client: AsyncClient, superadmin_token: str, sample_cameras):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam = sample_cameras["CROWD"]
    payload = {"profile_id": "FRS_STANDARD", "enabled": True}
    res = await client.post(f"/api/v1/cameras/{cam.camera_code}/ai-config", json=payload, headers=headers)
    assert res.status_code == 422
    data = res.json()
    assert data["success"] is False
    assert data["error"]["code"] == "AI_PROFILE_NOT_COMPATIBLE"


@pytest.mark.asyncio
async def test_reject_frs_profile_on_queue_camera(client: AsyncClient, superadmin_token: str, sample_cameras):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam = sample_cameras["QUEUE"]
    payload = {"profile_id": "FRS_STANDARD", "enabled": True}
    res = await client.post(f"/api/v1/cameras/{cam.camera_code}/ai-config", json=payload, headers=headers)
    assert res.status_code == 422
    data = res.json()
    assert data["success"] is False
    assert data["error"]["code"] == "AI_PROFILE_NOT_COMPATIBLE"


@pytest.mark.asyncio
async def test_reject_crowd_profile_on_queue_camera(client: AsyncClient, superadmin_token: str, sample_cameras):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam = sample_cameras["QUEUE"]
    payload = {"profile_id": "CROWD_STANDARD", "enabled": True}
    res = await client.post(f"/api/v1/cameras/{cam.camera_code}/ai-config", json=payload, headers=headers)
    assert res.status_code == 422
    data = res.json()
    assert data["success"] is False
    assert data["error"]["code"] == "AI_PROFILE_NOT_COMPATIBLE"


# ── 5. Duplicate Protection ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reject_duplicate_profile_assignment(client: AsyncClient, superadmin_token: str, sample_cameras):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam = sample_cameras["MULTI_PURPOSE"]
    payload = {"profile_id": "CROWD_HIGH_DENSITY", "enabled": True}

    # First assignment succeeds
    res1 = await client.post(f"/api/v1/cameras/{cam.camera_code}/ai-config", json=payload, headers=headers)
    assert res1.status_code == 201

    # Second assignment of identical profile on same camera fails with 409
    res2 = await client.post(f"/api/v1/cameras/{cam.camera_code}/ai-config", json=payload, headers=headers)
    assert res2.status_code == 409
    data = res2.json()
    assert data["success"] is False
    assert data["error"]["code"] == "AI_PROFILE_ALREADY_ASSIGNED"


# ── 6. Update Assignment ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_assignment_toggle_enabled(client: AsyncClient, superadmin_token: str, sample_cameras):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam = sample_cameras["CROWD"]

    # Toggle enabled to False
    res = await client.patch(
        f"/api/v1/cameras/{cam.camera_code}/ai-config/CROWD_STANDARD",
        json={"profile_id": "CROWD_STANDARD", "enabled": False},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["data"]["enabled"] is False

    # Toggle back to True
    res2 = await client.patch(
        f"/api/v1/cameras/{cam.camera_code}/ai-config/CROWD_STANDARD",
        json={"profile_id": "CROWD_STANDARD", "enabled": True},
        headers=headers,
    )
    assert res2.status_code == 200
    assert res2.json()["data"]["enabled"] is True


# ── 7. Remove Assignment ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_remove_assignment(client: AsyncClient, superadmin_token: str, sample_cameras):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam = sample_cameras["QUEUE"]

    res = await client.delete(
        f"/api/v1/cameras/{cam.camera_code}/ai-config/QUEUE_STANDARD",
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True

    # Check that it is no longer listed in assignments
    conf_res = await client.get(f"/api/v1/cameras/{cam.camera_code}/ai-config", headers=headers)
    assignments = conf_res.json()["data"]["assignments"]
    assert not any(a["profile_id"] == "QUEUE_STANDARD" for a in assignments)


# ── 8. Capacity Validation ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_capacity_validation_succeeds(client: AsyncClient, superadmin_token: str, sample_cameras):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam = sample_cameras["GENERAL"]
    payload = {"profile_id": "VIDEO_SAFETY", "enabled": True}

    res = await client.post(f"/api/v1/cameras/{cam.camera_code}/ai-config/validate", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    val = data["data"]
    assert val["compatible"] is True
    assert val["verdict"] in ("ALLOWED", "WARNING")
    assert "current_utilization" in val
    assert "requested_utilization" in val
    assert "projected_utilization" in val
    assert "safe_budget" in val


@pytest.mark.asyncio
async def test_capacity_validation_blocks_over_capacity(client: AsyncClient, superadmin_token: str, sample_cameras):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam = sample_cameras["CROWD"]

    # Mock validate_capacity_for_deployment to simulate strict OVER_CAPACITY
    from app.ai.capacity.calculator import CapacityCalculator, DeploymentValidationResult, ResourceBudget

    mock_blocked = DeploymentValidationResult(
        verdict="BLOCKED",
        status="OVER_CAPACITY",
        reason="Projected workload strictly exceeds hard safety ceiling on 'GPU_LOAD'.",
        current_utilization=ResourceBudget(gpu_percent=88.0, vram_gb=15.0, cpu_percent=70.0, ram_gb=28.0),
        projected_utilization=ResourceBudget(gpu_percent=95.0, vram_gb=17.0, cpu_percent=75.0, ram_gb=30.0),
        exceeded_resources=["GPU (95.0% > 90.0%)", "VRAM (17.0GB > 16.0GB)"],
    )

    with patch.object(CapacityCalculator, "validate_capacity_for_deployment", return_value=mock_blocked):
        # 1. Validation returns verdict="BLOCKED"
        val_res = await client.post(
            f"/api/v1/cameras/{cam.camera_code}/ai-config/validate",
            json={"profile_id": "CROWD_HIGH_DENSITY", "enabled": True},
            headers=headers,
        )
        assert val_res.status_code == 200
        assert val_res.json()["data"]["verdict"] == "BLOCKED"

        # 2. Assignment attempt is strictly rejected with 409 Conflict
        assign_res = await client.post(
            f"/api/v1/cameras/{cam.camera_code}/ai-config",
            json={"profile_id": "CROWD_HIGH_DENSITY", "enabled": True},
            headers=headers,
        )
        assert assign_res.status_code == 409
        data = assign_res.json()
        assert data["success"] is False
        assert data["error"]["code"] == "AI_CAPACITY_EXCEEDED"


# ── 9. Mixed Workload Calculation ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mixed_workload_calculation(client: AsyncClient, superadmin_token: str):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    # Direct pre-flight mixed capacity calculation endpoint
    payload = {
        "current_workload": {"CROWD_STANDARD": 5, "QUEUE_STANDARD": 2},
        "requested_addition": {"FRS_STANDARD": 1, "CROWD_STANDARD": 2},
    }
    res = await client.post("/api/v1/ai/system/capacity/validate", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    res_data = data["data"]
    assert "verdict" in res_data
    assert "projected_utilization" in res_data


# ── 10. RBAC Permissions Enforcement ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_ai_read_permission_enforced(client: AsyncClient, sample_cameras):
    # No auth header -> 401
    from app.config import settings
    import app.dependencies as deps
    orig_env = settings.APP_ENV
    orig_dev = deps._cached_dev_user
    try:
        settings.APP_ENV = "production"
        deps._cached_dev_user = None
        cam = sample_cameras["CROWD"]
        res = await client.get(f"/api/v1/cameras/{cam.camera_code}/ai-config")
        assert res.status_code == 401
    finally:
        settings.APP_ENV = orig_env
        deps._cached_dev_user = orig_dev


@pytest.mark.asyncio
async def test_ai_manage_permission_enforced(client: AsyncClient, read_only_token: str, sample_cameras):
    # User has AI_READ but lacks AI_MANAGE -> 403 Forbidden
    headers = {"Authorization": f"Bearer {read_only_token}"}
    cam = sample_cameras["GENERAL"]
    payload = {"profile_id": "VIDEO_SAFETY", "enabled": True}
    res = await client.post(f"/api/v1/cameras/{cam.camera_code}/ai-config", json=payload, headers=headers)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_unauthorized_frs_assignment_rejected(
    client: AsyncClient, ai_manager_no_frs_token: str, sample_cameras
):
    # User has AI_MANAGE but NOT FRS_MANAGE / FRS_REVIEW -> 403 Forbidden
    headers = {"Authorization": f"Bearer {ai_manager_no_frs_token}"}
    cam = sample_cameras["FRS"]
    payload = {"profile_id": "FRS_STANDARD", "enabled": True}
    res = await client.post(f"/api/v1/cameras/{cam.camera_code}/ai-config", json=payload, headers=headers)
    assert res.status_code == 403
    data = res.json()
    assert data["success"] is False
    assert data["error"]["code"] == "FRS_ASSIGNMENT_NOT_AUTHORIZED"


# ── 11. Audit Logging ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_event_logged_on_assignment(
    client: AsyncClient, superadmin_token: str, db_session: AsyncSession, sample_cameras
):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam = sample_cameras["GENERAL"]
    payload = {"profile_id": "VIDEO_SAFETY", "enabled": True}

    res = await client.post(f"/api/v1/cameras/{cam.camera_code}/ai-config", json=payload, headers=headers)
    assert res.status_code == 201

    # Verify AuditLog row exists
    stmt = select(AuditLog).where(
        AuditLog.action == "AI_PROFILE_ASSIGNED",
        AuditLog.resource_id == f"{cam.camera_code}:VIDEO_SAFETY",
    )
    result = await db_session.execute(stmt)
    audit = result.scalars().first()
    assert audit is not None
    assert audit.resource_type == "camera_ai_assignment"
    assert audit.metadata_json["profile_id"] == "VIDEO_SAFETY"


# ── 12. WebSocket Event Broadcast ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_websocket_event_emitted_on_config_change(
    client: AsyncClient, superadmin_token: str, sample_cameras
):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam = sample_cameras["MULTI_PURPOSE"]
    payload = {"profile_id": "QUEUE_STANDARD", "enabled": True}

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_publish:
        res = await client.post(f"/api/v1/cameras/{cam.camera_code}/ai-config", json=payload, headers=headers)
        assert res.status_code == 201
        assert mock_publish.called
        call_kwargs = mock_publish.call_args.kwargs
        assert call_kwargs["channel"] == "ai"
        assert call_kwargs["event_type"] == "AI_CONFIGURATION_CHANGED"
        assert call_kwargs["payload"]["camera_id"] == cam.camera_code
        assert call_kwargs["payload"]["profile_id"] == "QUEUE_STANDARD"


# ── 13. Not Found Errors ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_camera_not_found_404(client: AsyncClient, superadmin_token: str):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    res = await client.get("/api/v1/cameras/CAM-NONEXISTENT/ai-config", headers=headers)
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "CAMERA_NOT_FOUND"


@pytest.mark.asyncio
async def test_profile_not_found_404(client: AsyncClient, superadmin_token: str, sample_cameras):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam = sample_cameras["CROWD"]
    res = await client.post(
        f"/api/v1/cameras/{cam.camera_code}/ai-config",
        json={"profile_id": "PROFILE_DOES_NOT_EXIST", "enabled": True},
        headers=headers,
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "AI_PROFILE_NOT_FOUND"


# ── 14. Non-Inference Invariant Verification ───────────────────────────────────

@pytest.mark.asyncio
async def test_no_ai_inference_starts_during_assignment(
    client: AsyncClient, superadmin_token: str, sample_cameras
):
    """
    STRICT INVARIANT: Saving AI profile assignments MUST NOT start AI inference,
    launch DeepStream, or load models.
    """
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam = sample_cameras["MULTI_PURPOSE"]

    with patch("asyncio.create_subprocess_exec") as mock_exec, \
         patch("subprocess.Popen") as mock_popen:
        res = await client.post(
            f"/api/v1/cameras/{cam.camera_code}/ai-config",
            json={"profile_id": "CROWD_STANDARD", "enabled": True},
            headers=headers,
        )
        assert res.status_code == 201

        # Zero processes started
        assert not mock_exec.called
        assert not mock_popen.called
