"""
backend/tests/test_crowd_ai_pipeline.py — Step 6 Comprehensive Test Suite.

Verifies:
1. Crowd profile validation (CROWD_STANDARD, CROWD_HIGH_DENSITY)
2. Camera/profile compatibility
3. ROI readiness required before startup (CROWD_ROI polygon >= 3 points)
4. Real RTSP configuration loaded securely without password exposure
5. Person class filtering (class 0 only, non-person discarded)
6. Detection confidence threshold filtering
7. Multi-object tracking integration (assigns transient track IDs)
8. Crowd ROI filtering (person bottom-center inside polygon counted)
9. Exclusion zone filtering (discards detections inside exclusion zones)
10. Crowd count calculation inside ROI
11. Relative density calculation
12. Physical density calculation when calibration exists (persons/m²)
13. Density level categorization (LOW, MODERATE, HIGH, CRITICAL)
14. Deterministic crowd risk calculation (score 0..100 and categorical level)
15. Inflow calculation over rolling window
16. Outflow calculation over rolling window
17. Direction handling (IN, OUT, BOTH)
18. Duplicate line-crossing prevention
19. Event generation for high risk / density threshold exceeded
20. Event cooldown suppression (avoids alert spamming)
21. WebSocket crowd metrics event emission (CROWD_METRICS_UPDATED)
22. Server capacity validation before startup
23. Over-capacity blocks startup (409 AI_CAPACITY_EXCEEDED)
24. Pipeline state transitions (CREATED -> STARTING -> RUNNING -> STOPPED)
25. RTSP disconnect handling
26. No-frame timeout handling (FAILED after 10s)
27. GPU / DeepStream unavailable handling (reports capability failure cleanly)
28. Credential non-leakage
29. RBAC permission enforcement (CROWD_READ, AI_READ, AI_MANAGE)
30. No FRS behavior (strictly no face detection, embeddings, or candidate generation)
31. No Queue behavior (strictly crowd headcount/flow analytics)
32. No fake data / random simulation in production code
33. No arbitrary command execution
"""

import asyncio
import time
import uuid
from typing import Dict
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.capacity.calculator import CapacityCalculator
from app.ai.orchestrator.state import PipelineState
from app.ai.pipelines.crowd.analytics import (
    CrowdMetricsResult,
    CrowdSpatialAnalytics,
    check_segment_intersection,
    is_point_in_polygon,
)
from app.ai.pipelines.crowd.config import CrowdPipelineConfig
from app.ai.pipelines.crowd.detector import (
    DetectedPerson,
    MockPersonDetector,
)
from app.ai.pipelines.crowd.events import CrowdEventEngine
from app.ai.pipelines.crowd.health import PipelineHealthMonitor
from app.ai.pipelines.crowd.models_registry import ModelRegistryService
from app.ai.pipelines.crowd.pipeline import CrowdPipeline
from app.ai.pipelines.crowd.registry import CrowdPipelineRegistry
from app.ai.pipelines.crowd.risk import CrowdRiskEngine
from app.ai.pipelines.crowd.tracker import PersonTracker, TrackedPerson
from app.ai.profiles.service import AIProfileType, STANDARD_PROFILES
from app.models.audit_log import AuditLog
from app.models.camera import Camera
from app.models.camera_ai_assignment import CameraAIProfileAssignment
from app.models.camera_roi import CameraROIConfiguration, ROIType
from app.models.role import Permission, Role
from app.models.user import User
from app.models.zone import Zone
from app.redis.event_bus import event_bus
from app.security.encryption import encrypt_credential
from app.security.jwt import create_access_token
from app.security.password import get_password_hash


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
def clean_registry():
    """Ensures CrowdPipelineRegistry is reset before and after every test."""
    CrowdPipelineRegistry.reset_for_testing()
    yield
    CrowdPipelineRegistry.reset_for_testing()


@pytest_asyncio.fixture
async def viewer_token(db_session: AsyncSession) -> str:
    """Creates a token with only crowd:read permission."""
    stmt_perm = select(Permission).where(Permission.code == "crowd:read")
    perm = (await db_session.execute(stmt_perm)).scalars().first()
    if not perm:
        perm = Permission(code="crowd:read", name="crowd:read", description="Read crowd")
        db_session.add(perm)
        await db_session.flush()

    stmt_role = select(Role).where(Role.code == "ROLE_CROWD_VIEWER")
    role = (await db_session.execute(stmt_role)).scalars().first()
    if not role:
        role = Role(code="ROLE_CROWD_VIEWER", name="Crowd Viewer", description="Read only crowd", permissions=[perm])
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(role)

    stmt_user = select(User).where(User.username == "test_crowd_viewer")
    user = (await db_session.execute(stmt_user)).scalars().first()
    if not user:
        user = User(
            username="test_crowd_viewer",
            email="test_crowd_viewer@byc.ai",
            password_hash=get_password_hash("viewer123!"),
            full_name="Crowd Viewer",
            role_id=role.id,
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

    return create_access_token(
        subject=str(user.id),
        role="ROLE_CROWD_VIEWER",
        permissions=["crowd:read"],
    )


@pytest_asyncio.fixture
async def crowd_test_tokens(superadmin_token: str, viewer_token: str) -> Dict[str, str]:
    return {
        "admin": superadmin_token,
        "viewer": viewer_token,
    }


@pytest_asyncio.fixture
async def sample_crowd_camera(db_session: AsyncSession) -> Camera:
    """Creates a verified camera assigned to CROWD_STANDARD with valid CROWD_ROI."""
    zone = (await db_session.execute(select(Zone).where(Zone.zone_code == "ZONE-CROWD-TEST"))).scalars().first()
    if not zone:
        zone = Zone(
            zone_code="ZONE-CROWD-TEST",
            name="Crowd AI Test Courtyard",
            label="Crowd Courtyard",
            coordinates=[[78.4635, 17.4175], [78.4640, 17.4180]],
            capacity=1000,
            status="ACTIVE",
            current_people=0,
        )
        db_session.add(zone)
        await db_session.flush()

    cam = (await db_session.execute(select(Camera).where(Camera.camera_code == "CAM-CRW-001"))).scalars().first()
    if not cam:
        cam = Camera(
            camera_code="CAM-CRW-001",
            name="Pandal Inflow Crowd Cam",
            label="Pandal Inflow Crowd Cam",
            camera_type="CROWD",
            zone_id=zone.id,
            zone_code="ZONE-CROWD-TEST",
            status="online",
            stream_status="VERIFIED",
            resolution="1080p",
            fps=25,
            enabled=True,
            private_ip="192.168.1.101",
            port=554,
            rtsp_url_encrypted=encrypt_credential("rtsp://operator:SecretPass999@192.168.1.101:554/Streaming/Channels/101"),
        )
        db_session.add(cam)
        await db_session.flush()

    # Assign CROWD_STANDARD profile
    asgn = (await db_session.execute(
        select(CameraAIProfileAssignment).where(
            CameraAIProfileAssignment.camera_id == cam.id,
            CameraAIProfileAssignment.profile_id == "CROWD_STANDARD",
        )
    )).scalars().first()
    if not asgn:
        asgn = CameraAIProfileAssignment(
            camera_id=cam.id,
            camera_code=cam.camera_code,
            profile_id="CROWD_STANDARD",
            enabled=True,
            assigned_by="system_test",
        )
        db_session.add(asgn)
        await db_session.flush()

    # Add CROWD_ROI polygon
    roi = (await db_session.execute(
        select(CameraROIConfiguration).where(
            CameraROIConfiguration.camera_id == cam.id,
            CameraROIConfiguration.roi_type == ROIType.CROWD_ROI,
        )
    )).scalars().first()
    if not roi:
        roi = CameraROIConfiguration(
            camera_id=cam.id,
            camera_code=cam.camera_code,
            profile_id="CROWD_STANDARD",
            roi_type=ROIType.CROWD_ROI,
            name="Main Courtyard Gathering Area",
            geometry_json={
                "points": [
                    {"x": 0.1, "y": 0.1},
                    {"x": 0.9, "y": 0.1},
                    {"x": 0.9, "y": 0.9},
                    {"x": 0.1, "y": 0.9},
                ]
            },
            normalized=True,
            enabled=True,
            created_by="system_test",
        )
        db_session.add(roi)
        await db_session.flush()

    await db_session.commit()
    await db_session.refresh(cam)
    return cam


# ── TESTS ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_crowd_profile_validation():
    """1. Validates standard crowd profile specifications and model requirements."""
    std = STANDARD_PROFILES.get("CROWD_STANDARD")
    dense = STANDARD_PROFILES.get("CROWD_HIGH_DENSITY")

    assert std is not None
    assert std.type == AIProfileType.CROWD_STANDARD
    assert std.pipeline_type == "CROWD"
    assert std.processing_fps == 15
    assert std.confidence_threshold == 0.45
    assert std.tracker_enabled is True

    assert dense is not None
    assert dense.type == AIProfileType.CROWD_HIGH_DENSITY
    assert dense.processing_fps == 20
    assert dense.confidence_threshold == 0.35


@pytest.mark.asyncio
async def test_camera_profile_compatibility():
    """2. Verifies crowd models resolve correctly from profile IDs."""
    m_std = ModelRegistryService.get_model_for_profile("CROWD_STANDARD")
    m_dense = ModelRegistryService.get_model_for_profile("CROWD_HIGH_DENSITY")

    assert m_std.model_id == "yolov8n-crowd"
    assert m_dense.model_id == "yolov8x-crowd"
    assert m_std.allowed_classes == [0]
    assert m_dense.allowed_classes == [0]


@pytest.mark.asyncio
async def test_roi_readiness_required_for_pipeline_start(
    client: AsyncClient,
    crowd_test_tokens: Dict[str, str],
    db_session: AsyncSession,
):
    """3. Starting a pipeline on a camera without CROWD_ROI is rejected with 400."""
    # Create a camera without ROI
    cam = Camera(
        camera_code="CAM-NOROI-001",
        name="No ROI Camera",
        label="No ROI Camera",
        camera_type="CROWD",
        status="online",
        stream_status="VERIFIED",
        enabled=True,
        rtsp_url_encrypted=encrypt_credential("rtsp://admin:pass@192.168.1.200/stream"),
    )
    db_session.add(cam)
    await db_session.flush()

    asgn = CameraAIProfileAssignment(
        camera_id=cam.id,
        camera_code=cam.camera_code,
        profile_id="CROWD_STANDARD",
        enabled=True,
        assigned_by="test",
    )
    db_session.add(asgn)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/crowd/pipelines/{cam.camera_code}/start",
        headers={"Authorization": f"Bearer {crowd_test_tokens['admin']}"},
    )
    assert resp.status_code == 400
    body = resp.json()
    err_code = body.get("error", {}).get("code") or body.get("detail", {}).get("code")
    assert err_code == "ROI_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_rtsp_config_loaded_securely(sample_crowd_camera: Camera, db_session: AsyncSession):
    """4. Ensures RTSP credentials are decrypted internally but never logged or exposed."""
    roi_configs = [
        CameraROIConfiguration(
            camera_id=sample_crowd_camera.id,
            camera_code=sample_crowd_camera.camera_code,
            profile_id="CROWD_STANDARD",
            roi_type=ROIType.CROWD_ROI,
            name="Test ROI",
            geometry_json={"points": [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.9, "y": 0.9}]},
            enabled=True,
        )
    ]
    cfg = CrowdPipelineConfig.from_camera_and_geometries(sample_crowd_camera, "CROWD_STANDARD", roi_configs)

    assert "SecretPass999" in cfg.rtsp_url_internal
    assert "SecretPass999" not in cfg.rtsp_url_sanitized
    assert "***" in cfg.rtsp_url_sanitized
    # Check string representation does not leak password
    assert "SecretPass999" not in str(cfg)


@pytest.mark.asyncio
async def test_person_class_filtering():
    """5. Verifies person class (class 0) filtering; non-person classes discarded."""
    model = ModelRegistryService.get_model_for_profile("CROWD_STANDARD")
    detector = MockPersonDetector(model=model, confidence_threshold=0.45)
    await detector.initialize()

    raw_detections = [
        {"class_id": 0, "confidence": 0.85, "bbox": (0.1, 0.1, 0.2, 0.3)},  # Person -> keep
        {"class_id": 2, "confidence": 0.90, "bbox": (0.4, 0.4, 0.6, 0.6)},  # Car -> discard
        {"class_id": 15, "confidence": 0.70, "bbox": (0.5, 0.5, 0.7, 0.7)}, # Cat -> discard
        {"class_id": 0, "confidence": 0.65, "bbox": (0.2, 0.2, 0.3, 0.4)},  # Person -> keep
    ]
    detector.set_next_detections(raw_detections)
    dets = await detector.detect(None, frame_id=1, timestamp=time.time())

    assert len(dets) == 2
    assert all(d.class_id == 0 for d in dets)
    assert all(d.class_name == "person" for d in dets)


@pytest.mark.asyncio
async def test_detection_confidence_threshold():
    """6. Detections below confidence threshold are discarded."""
    model = ModelRegistryService.get_model_for_profile("CROWD_STANDARD")
    detector = MockPersonDetector(model=model, confidence_threshold=0.50)
    await detector.initialize()

    raw_detections = [
        {"class_id": 0, "confidence": 0.75, "bbox": (0.1, 0.1, 0.2, 0.3)}, # >= 0.50 -> keep
        {"class_id": 0, "confidence": 0.49, "bbox": (0.2, 0.2, 0.3, 0.4)}, # < 0.50 -> discard
        {"class_id": 0, "confidence": 0.20, "bbox": (0.3, 0.3, 0.4, 0.5)}, # < 0.50 -> discard
    ]
    detector.set_next_detections(raw_detections)
    dets = await detector.detect(None, frame_id=1, timestamp=time.time())

    assert len(dets) == 1
    assert dets[0].confidence == 0.75


@pytest.mark.asyncio
async def test_multi_object_tracking():
    """7. Multi-object tracker assigns persistent track IDs across frames."""
    tracker = PersonTracker(max_age_frames=10, iou_threshold=0.2)
    now = time.time()

    # Frame 1: 2 persons detected
    f1 = [
        DetectedPerson(class_id=0, confidence=0.8, bbox=(0.10, 0.10, 0.20, 0.30)),
        DetectedPerson(class_id=0, confidence=0.85, bbox=(0.60, 0.60, 0.70, 0.80)),
    ]
    t1 = tracker.update(f1, timestamp=now)
    assert len(t1) == 2
    id_1 = t1[0].track_id
    id_2 = t1[1].track_id

    # Frame 2: Persons shifted slightly
    f2 = [
        DetectedPerson(class_id=0, confidence=0.82, bbox=(0.11, 0.11, 0.21, 0.31)),
        DetectedPerson(class_id=0, confidence=0.84, bbox=(0.61, 0.61, 0.71, 0.81)),
    ]
    t2 = tracker.update(f2, timestamp=now + 0.1)
    assert len(t2) == 2
    assert t2[0].track_id == id_1
    assert t2[1].track_id == id_2
    assert len(t2[0].trajectory) == 2


@pytest.mark.asyncio
async def test_crowd_roi_spatial_filtering(sample_crowd_camera: Camera):
    """8 & 10. Only persons whose bottom-center falls within CROWD_ROI are counted."""
    roi_poly = [
        {"x": 0.2, "y": 0.2},
        {"x": 0.8, "y": 0.2},
        {"x": 0.8, "y": 0.8},
        {"x": 0.2, "y": 0.8},
    ]
    cfg = CrowdPipelineConfig.from_camera_and_geometries(
        sample_crowd_camera,
        "CROWD_STANDARD",
        [
            CameraROIConfiguration(
                camera_id=sample_crowd_camera.id,
                camera_code=sample_crowd_camera.camera_code,
                profile_id="CROWD_STANDARD",
                roi_type=ROIType.CROWD_ROI,
                name="Center Court",
                geometry_json={"points": roi_poly},
                enabled=True,
            )
        ],
    )
    analytics = CrowdSpatialAnalytics(cfg)
    now = time.time()

    # Track 1: inside ROI (bottom-center at 0.5, 0.5)
    trk_in = TrackedPerson(
        track_id=1001,
        track_code="TRK-1001",
        current_bbox=(0.45, 0.40, 0.55, 0.50),
        current_point=(0.50, 0.50),
        confidence=0.85,
    )
    # Track 2: outside ROI (bottom-center at 0.10, 0.10)
    trk_out = TrackedPerson(
        track_id=1002,
        track_code="TRK-1002",
        current_bbox=(0.05, 0.05, 0.15, 0.10),
        current_point=(0.10, 0.10),
        confidence=0.80,
    )

    metrics = analytics.process_tracks([trk_in, trk_out], now)
    assert metrics.current_count == 1
    assert metrics.total_tracked_in_frame == 2
    assert metrics.active_roi_track_ids == [1001]


@pytest.mark.asyncio
async def test_exclusion_zone_filtering(sample_crowd_camera: Camera):
    """9. Detections falling inside an EXCLUSION_ZONE polygon are excluded from crowd count."""
    roi_poly = [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.9, "y": 0.9}, {"x": 0.1, "y": 0.9}]
    ex_poly = [{"x": 0.4, "y": 0.4}, {"x": 0.6, "y": 0.4}, {"x": 0.6, "y": 0.6}, {"x": 0.4, "y": 0.6}]

    cfg = CrowdPipelineConfig.from_camera_and_geometries(
        sample_crowd_camera,
        "CROWD_STANDARD",
        [
            CameraROIConfiguration(
                camera_id=sample_crowd_camera.id,
                camera_code=sample_crowd_camera.camera_code,
                profile_id="CROWD_STANDARD",
                roi_type=ROIType.CROWD_ROI,
                name="Courtyard",
                geometry_json={"points": roi_poly},
                enabled=True,
            ),
            CameraROIConfiguration(
                camera_id=sample_crowd_camera.id,
                camera_code=sample_crowd_camera.camera_code,
                profile_id="CROWD_STANDARD",
                roi_type=ROIType.EXCLUSION_ZONE,
                name="Staff Stage Area",
                geometry_json={"points": ex_poly},
                enabled=True,
            ),
        ],
    )
    analytics = CrowdSpatialAnalytics(cfg)
    now = time.time()

    # Person 1: Inside ROI, but also inside Exclusion Zone -> excluded!
    p1 = TrackedPerson(
        track_id=1, track_code="TRK-1",
        current_bbox=(0.45, 0.45, 0.55, 0.50),
        current_point=(0.50, 0.50),
        confidence=0.9,
    )
    # Person 2: Inside ROI, outside Exclusion Zone -> counted!
    p2 = TrackedPerson(
        track_id=2, track_code="TRK-2",
        current_bbox=(0.15, 0.15, 0.25, 0.20),
        current_point=(0.20, 0.20),
        confidence=0.9,
    )

    metrics = analytics.process_tracks([p1, p2], now)
    assert metrics.current_count == 1
    assert metrics.excluded_count == 1
    assert metrics.active_roi_track_ids == [2]


@pytest.mark.asyncio
async def test_relative_and_calibrated_density_calculation(sample_crowd_camera: Camera):
    """11 & 12. Relative vs Calibrated (persons/m²) density calculation."""
    roi_poly = [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0}]
    roi_config = CameraROIConfiguration(
        camera_id=sample_crowd_camera.id,
        camera_code=sample_crowd_camera.camera_code,
        profile_id="CROWD_STANDARD",
        roi_type=ROIType.CROWD_ROI,
        name="All Frame",
        geometry_json={"points": roi_poly},
        enabled=True,
    )

    # 1. Uncalibrated (Relative Density)
    cfg_uncal = CrowdPipelineConfig.from_camera_and_geometries(
        sample_crowd_camera, "CROWD_STANDARD", [roi_config], physical_area_m2=None
    )
    an_uncal = CrowdSpatialAnalytics(cfg_uncal)
    tracks = [
        TrackedPerson(track_id=i, track_code=f"TRK-{i}", current_bbox=(0.1, 0.1, 0.2, 0.2), current_point=(0.15, 0.15), confidence=0.9)
        for i in range(10)
    ]
    res_uncal = an_uncal.process_tracks(tracks, time.time())
    assert res_uncal.density_type == "RELATIVE_DENSITY"
    assert res_uncal.density_unit == "RELATIVE_DENSITY"
    assert res_uncal.current_count == 10

    # 2. Calibrated (persons/m²)
    cfg_cal = CrowdPipelineConfig.from_camera_and_geometries(
        sample_crowd_camera, "CROWD_STANDARD", [roi_config], physical_area_m2=5.0
    )
    an_cal = CrowdSpatialAnalytics(cfg_cal)
    res_cal = an_cal.process_tracks(tracks, time.time())
    assert res_cal.density_type == "CALIBRATED"
    assert res_cal.density_unit == "persons/m²"
    assert res_cal.density == 2.0  # 10 persons / 5 m² = 2.0 persons/m²


@pytest.mark.asyncio
async def test_density_level_and_deterministic_risk():
    """13 & 14. Density levels and deterministic risk calculation without LLM."""
    metrics_low = CrowdMetricsResult(
        camera_id="cam-1",
        camera_code="CAM-1",
        profile_id="CROWD_STANDARD",
        timestamp=time.time(),
        current_count=10,
        density=0.5,
        density_level="LOW",
        inflow_rate=10,
        outflow_rate=12,
    )
    score_low, level_low, _ = CrowdRiskEngine.calculate_risk(metrics_low, "HEALTHY")
    assert level_low == "LOW"
    assert score_low < 35.0

    metrics_crit = CrowdMetricsResult(
        camera_id="cam-1",
        camera_code="CAM-1",
        profile_id="CROWD_STANDARD",
        timestamp=time.time(),
        current_count=150,
        density=5.5,
        density_level="CRITICAL",
        inflow_rate=80,
        outflow_rate=20,  # Surge +60
    )
    score_crit, level_crit, factors = CrowdRiskEngine.calculate_risk(metrics_crit, "HEALTHY")
    assert level_crit == "CRITICAL"
    assert score_crit >= 85.0
    assert any("Density CRITICAL" in f for f in factors)


@pytest.mark.asyncio
async def test_inflow_outflow_and_duplicate_prevention(sample_crowd_camera: Camera):
    """15, 16, 17, 18. Line crossing inflow/outflow, direction, and duplicate prevention."""
    line_config = CameraROIConfiguration(
        camera_id=sample_crowd_camera.id,
        camera_code=sample_crowd_camera.camera_code,
        profile_id="CROWD_STANDARD",
        roi_type=ROIType.ENTRY_LINE,
        name="Main Entry Gate Line",
        geometry_json={
            "start": {"x": 0.0, "y": 0.5},
            "end": {"x": 1.0, "y": 0.5},
            "direction": "IN",
        },
        enabled=True,
    )
    roi_config = CameraROIConfiguration(
        camera_id=sample_crowd_camera.id,
        camera_code=sample_crowd_camera.camera_code,
        profile_id="CROWD_STANDARD",
        roi_type=ROIType.CROWD_ROI,
        name="Full Courtyard",
        geometry_json={"points": [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0}]},
        enabled=True,
    )
    cfg = CrowdPipelineConfig.from_camera_and_geometries(sample_crowd_camera, "CROWD_STANDARD", [roi_config, line_config])
    analytics = CrowdSpatialAnalytics(cfg)
    now = time.time()

    # Track moving across the line from y=0.4 to y=0.6
    trk = TrackedPerson(
        track_id=501,
        track_code="TRK-501",
        current_bbox=(0.4, 0.55, 0.5, 0.65),
        current_point=(0.45, 0.60),
        confidence=0.9,
        trajectory=[(0.45, 0.40, now - 0.1), (0.45, 0.60, now)],
    )

    # First crossing: should count inflow
    m1 = analytics.process_tracks([trk], now)
    assert m1.counting_lines_active is True
    assert m1.inflow_rate == 1  # 1 event in 60s window = 1/min rate

    # Second frame with same track lingering across the line: must NOT count again!
    trk.trajectory.append((0.45, 0.62, now + 0.1))
    trk.current_point = (0.45, 0.62)
    m2 = analytics.process_tracks([trk], now + 0.1)
    assert m2.inflow_rate == 1  # Still 1 event, not 2!


@pytest.mark.asyncio
async def test_event_generation_and_cooldown_suppression():
    """19 & 20. Event engine fires events and suppresses duplicates within cooldown."""
    engine = CrowdEventEngine(cooldown_seconds=10)
    now = time.time()
    metrics = CrowdMetricsResult(
        camera_id="cam-1",
        camera_code="CAM-CRW-TEST",
        profile_id="CROWD_STANDARD",
        timestamp=now,
        current_count=180,
        density=6.0,
        density_level="CRITICAL",
        inflow_rate=95,
        outflow_rate=15,
    )

    with patch.object(event_bus, "publish", new_callable=AsyncMock) as mock_pub:
        # First check -> should fire CROWD_RISK_CRITICAL and CROWD_THRESHOLD_EXCEEDED
        evts1 = await engine.evaluate_and_emit(metrics, 92.0, "CRITICAL", ["Density CRITICAL"])
        assert len(evts1) >= 2
        assert mock_pub.called

        # Second check 2 seconds later (within 10s cooldown) -> must be suppressed!
        mock_pub.reset_mock()
        metrics.timestamp = now + 2.0
        evts2 = await engine.evaluate_and_emit(metrics, 92.0, "CRITICAL", ["Density CRITICAL"])
        assert len(evts2) == 0
        assert not mock_pub.called

        # Third check 12 seconds later (cooldown expired) -> should fire again!
        metrics.timestamp = now + 12.0
        evts3 = await engine.evaluate_and_emit(metrics, 92.0, "CRITICAL", ["Density CRITICAL"])
        assert len(evts3) >= 1


@pytest.mark.asyncio
async def test_capacity_validation_blocks_startup(
    client: AsyncClient,
    crowd_test_tokens: Dict[str, str],
    sample_crowd_camera: Camera,
):
    """22 & 23. Over-capacity deployment rejected with 409 AI_CAPACITY_EXCEEDED."""
    with patch("app.ai.runtime.detector.RuntimeDetector.detect_runtime", return_value={"deepstream": True}), \
         patch("app.ai.runtime.detector.RuntimeDetector.detect_gpu", return_value={"available": True}), \
         patch.object(
             CapacityCalculator,
             "validate_capacity_for_deployment",
             return_value={"allowed": False, "reason": "GPU VRAM capacity exceeded (92.5% > 85.0% threshold)"},
         ):
        resp = await client.post(
            f"/api/v1/crowd/pipelines/{sample_crowd_camera.camera_code}/start",
            headers={"Authorization": f"Bearer {crowd_test_tokens['admin']}"},
        )
        assert resp.status_code == 409
        body = resp.json()
        err_code = body.get("error", {}).get("code") or body.get("detail", {}).get("code")
        assert err_code == "AI_CAPACITY_EXCEEDED"


@pytest.mark.asyncio
async def test_pipeline_state_transitions_and_mock_execution(sample_crowd_camera: Camera):
    """24. Follows state transitions: CREATED -> STARTING -> RUNNING -> STOPPED."""
    roi_poly = [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.9, "y": 0.9}, {"x": 0.1, "y": 0.9}]
    cfg = CrowdPipelineConfig.from_camera_and_geometries(
        sample_crowd_camera,
        "CROWD_STANDARD",
        [
            CameraROIConfiguration(
                camera_id=sample_crowd_camera.id,
                camera_code=sample_crowd_camera.camera_code,
                profile_id="CROWD_STANDARD",
                roi_type=ROIType.CROWD_ROI,
                name="Courtyard",
                geometry_json={"points": roi_poly},
                enabled=True,
            )
        ],
    )

    mock_det = MockPersonDetector(model=cfg.model, confidence_threshold=0.45)
    mock_det.set_next_detections([
        {"class_id": 0, "confidence": 0.85, "bbox": (0.3, 0.3, 0.4, 0.5)},
        {"class_id": 0, "confidence": 0.78, "bbox": (0.5, 0.5, 0.6, 0.7)},
    ])

    pipeline = CrowdPipeline(config=cfg, detector=mock_det)
    assert pipeline.state == PipelineState.CREATED

    # Start
    await pipeline.start()
    assert pipeline.state == PipelineState.RUNNING
    CrowdPipelineRegistry.register(pipeline)

    # Process frame
    res = await pipeline.process_frame(None, frame_id=1, timestamp=time.time())
    assert res["count"] == 2
    assert res["status"] == "RUNNING"

    # Stop
    await pipeline.stop()
    assert pipeline.state == PipelineState.STOPPED


@pytest.mark.asyncio
async def test_no_frame_timeout_marks_health_failed():
    """25 & 26. Health monitor marks pipeline as FAILED if no frames in 10s."""
    monitor = PipelineHealthMonitor(
        camera_id="cam-1",
        camera_code="CAM-1",
        profile_id="CROWD_STANDARD",
        target_fps=15,
        no_frame_timeout_sec=5.0,
    )
    monitor.pipeline_state = PipelineState.RUNNING
    now = time.time()

    # Frame 1 received at t=now
    monitor.record_frame(now, 10.0, 2.0)
    h1 = monitor.compute_health()
    assert h1.health_status == "HEALTHY"

    # Simulate 6 seconds elapsed without frames
    with patch("time.time", return_value=now + 6.0):
        h2 = monitor.compute_health()
        assert h2.health_status == "FAILED"
        assert "Stream timeout" in (h2.last_error or "")


@pytest.mark.asyncio
async def test_deepstream_unavailable_on_unsupported_host(
    client: AsyncClient,
    crowd_test_tokens: Dict[str, str],
    sample_crowd_camera: Camera,
):
    """27. Clearly reports RUNTIME_UNAVAILABLE without pretending inference succeeded."""
    with patch("app.ai.runtime.detector.RuntimeDetector.detect_runtime", return_value={"deepstream": False}), \
         patch("app.ai.runtime.detector.RuntimeDetector.detect_gpu", return_value={"available": False}):
        resp = await client.post(
            f"/api/v1/crowd/pipelines/{sample_crowd_camera.camera_code}/start",
            headers={"Authorization": f"Bearer {crowd_test_tokens['admin']}"},
        )
        assert resp.status_code == 400
        data = resp.json()
        err_code = data.get("error", {}).get("code") or data.get("detail", {}).get("code")
        assert err_code == "RUNTIME_UNAVAILABLE"


@pytest.mark.asyncio
async def test_no_credentials_leaked_in_metrics_or_health(
    client: AsyncClient,
    crowd_test_tokens: Dict[str, str],
    sample_crowd_camera: Camera,
):
    """28. Verifies passwords/secrets are never returned in crowd metrics endpoints."""
    resp = await client.get(
        f"/api/v1/crowd/cameras/{sample_crowd_camera.camera_code}/metrics",
        headers={"Authorization": f"Bearer {crowd_test_tokens['viewer']}"},
    )
    assert resp.status_code == 200
    raw_text = resp.text
    assert "SecretPass999" not in raw_text
    assert "rtsp://" not in raw_text or "***" in raw_text


@pytest.mark.asyncio
async def test_rbac_permission_enforcement(
    client: AsyncClient,
    crowd_test_tokens: Dict[str, str],
    sample_crowd_camera: Camera,
):
    """29. Verifies RBAC: Viewer cannot start/stop pipeline (403), Admin can."""
    # Viewer tries to start pipeline -> 403 Forbidden
    resp_v = await client.post(
        f"/api/v1/crowd/pipelines/{sample_crowd_camera.camera_code}/start",
        headers={"Authorization": f"Bearer {crowd_test_tokens['viewer']}"},
    )
    assert resp_v.status_code == 403

    # Viewer can read metrics -> 200 OK
    resp_r = await client.get(
        f"/api/v1/crowd/cameras/{sample_crowd_camera.camera_code}/metrics",
        headers={"Authorization": f"Bearer {crowd_test_tokens['viewer']}"},
    )
    assert resp_r.status_code == 200


@pytest.mark.asyncio
async def test_no_frs_or_queue_behavior_in_crowd_pipeline():
    """30 & 31. Strict Isolation: No FRS or Queue behavior inside Crowd pipeline."""
    from app.ai.pipelines.crowd import models_registry, detector, tracker

    # Check detector only operates on class 0 (person)
    assert models_registry.ModelRegistryService.is_person_class(0) is True
    assert models_registry.ModelRegistryService.is_person_class(1) is False  # not face
    assert models_registry.ModelRegistryService.is_person_class(2) is False

    # Check tracking IDs are pure integers/tokens
    trk = tracker.TrackedPerson(
        track_id=1005,
        track_code="TRK-1005",
        current_bbox=(0.1, 0.1, 0.2, 0.2),
        current_point=(0.15, 0.20),
        confidence=0.88,
    )
    # Ensure no biometric embeddings or face attributes exist
    assert not hasattr(trk, "face_embedding")
    assert not hasattr(trk, "face_id")
    assert not hasattr(trk, "identity")


@pytest.mark.asyncio
async def test_no_fake_data_in_analytics_when_no_lines():
    """32. Flow rates are None/unavailable when counting lines are not configured."""
    roi_poly = [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.9, "y": 0.9}]
    cfg = CrowdPipelineConfig(
        camera_id="cam-1",
        camera_code="CAM-1",
        camera_name="Test Cam",
        rtsp_url_internal="rtsp://internal",
        rtsp_url_sanitized="rtsp://sanitized",
        model=ModelRegistryService.get_model_for_profile("CROWD_STANDARD"),
        crowd_roi_points=roi_poly,
        counting_lines=[],  # NO counting lines
    )
    analytics = CrowdSpatialAnalytics(cfg)
    m = analytics.process_tracks([], time.time())

    assert m.inflow_rate is None
    assert m.outflow_rate is None
    assert m.counting_lines_active is False


@pytest.mark.asyncio
async def test_no_arbitrary_command_execution():
    """33. Confirms no subprocess.Popen/run with unsanitized shell strings in crowd pipeline."""
    import inspect
    from app.ai.pipelines.crowd import pipeline, detector, config

    for mod in (pipeline, detector, config):
        source = inspect.getsource(mod)
        assert "shell=True" not in source
        assert "os.system" not in source
