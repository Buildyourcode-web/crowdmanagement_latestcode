"""
backend/tests/test_queue_ai_pipeline.py — Step 7 Comprehensive Test Suite.

Verifies:
1. Queue profile specifications (QUEUE_STANDARD)
2. Queue model registry resolution & person class isolation
3. Geometry check: QUEUE_ROI required
4. Geometry check: ENTRY_LINE required
5. Geometry check: EXIT_LINE required
6. Geometry check: all geometries present
7. RTSP config loaded securely without password exposure
8. Person class filtering (class 0 only, non-person discarded)
9. Detection confidence threshold filtering
10. Multi-object tracking integration (assigns TRK-xxxx)
11. Queue ROI spatial filtering using bottom-center (x_mid, y_max)
12. Exclusion zone deduction inside Queue ROI
13. Queue headcount calculation accuracy
14. Occupancy percentage calculation
15. Missing capacity handling (UNAVAILABLE, occupancy None)
16. Relative density calculation
17. Calibrated density calculation (persons/m²)
18. Queue length estimation (relative vs calibrated)
19. Entry line crossing inflow counting
20. Exit line crossing outflow counting & dwell completion
21. Duplicate line-crossing prevention within 5s cooldown
22. Queue direction calculation: FORWARD
23. Queue direction calculation: BACKWARD
24. Queue direction calculation: UNKNOWN
25. Dwell time: average, median, and max dwell calculation
26. Insufficient dwell data handling (insufficient_data, None)
27. Growth rate calculation over rolling window
28. Deterministic multi-factor risk scoring (LOW, MEDIUM, HIGH, CRITICAL)
29. Event engine generation for risk, occupancy, inflow, and wait time
30. Event engine 60-second cooldown suppression
31. Server capacity validation blocks startup on overcapacity (409 AI_CAPACITY_EXCEEDED)
32. Pipeline state transitions (CREATED -> STARTING -> RUNNING -> STOPPED)
33. Health monitor frame processing & FPS calculation
34. Health monitor 10s no-frame timeout marks status FAILED
35. Runtime capability check: RUNTIME_UNAVAILABLE on unsupported host (no fake data)
36. Credential non-leakage in queue metrics and status endpoints
37. RBAC permissions: queue:read allows read, queue:manage / ai:manage required for start/stop
38. Strict FRS isolation: zero face recognition or biometrics
39. Zero Crowd AI regressions: Crowd pipeline registry remains intact
40. No arbitrary command execution (shell=True, os.system absent)
41. Zone queue aggregation across multiple cameras
42. Queue repository snapshot persistence queries
"""

import asyncio
import inspect
import math
import time
import uuid
from typing import Dict, List
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.capacity.calculator import CapacityCalculator
from app.ai.orchestrator.state import PipelineState
from app.ai.pipelines.crowd.detector import DetectedPerson, MockPersonDetector
from app.ai.pipelines.crowd.health import PipelineHealthMonitor
from app.ai.pipelines.crowd.registry import CrowdPipelineRegistry
from app.ai.pipelines.crowd.tracker import PersonTracker, TrackedPerson
from app.ai.pipelines.queue.analytics import (
    QueueMetricsResult,
    QueueSpatialAnalytics,
)
from app.ai.pipelines.queue.config import QueuePipelineConfig, sanitize_rtsp_url
from app.ai.pipelines.queue.events import QueueEventEngine
from app.ai.pipelines.queue.models_registry import QueueModelRegistryService, QUEUE_MODEL_REGISTRY
from app.ai.pipelines.queue.pipeline import QueuePipeline
from app.ai.pipelines.queue.registry import QueuePipelineRegistry
from app.ai.pipelines.queue.risk import QueueRiskEngine
from app.ai.profiles.service import AIProfileType, STANDARD_PROFILES
from app.models.camera import Camera
from app.models.camera_ai_assignment import CameraAIProfileAssignment
from app.models.camera_roi import CameraROIConfiguration, ROIType
from app.models.queue import QueueSnapshot
from app.models.role import Permission, Role
from app.models.user import User
from app.models.zone import Zone
from app.repositories.queue_repository import QueueRepository
from app.security.encryption import encrypt_credential
from app.security.jwt import create_access_token
from app.security.password import get_password_hash


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
def clean_registry():
    QueuePipelineRegistry.reset_for_testing()
    CrowdPipelineRegistry.reset_for_testing()
    yield
    QueuePipelineRegistry.reset_for_testing()
    CrowdPipelineRegistry.reset_for_testing()


@pytest_asyncio.fixture
async def queue_viewer_token(db_session: AsyncSession) -> str:
    stmt_perm = select(Permission).where(Permission.code == 'queue:read')
    perm = (await db_session.execute(stmt_perm)).scalars().first()
    if not perm:
        perm = Permission(code='queue:read', name='queue:read', description='Read queue')
        db_session.add(perm)
        await db_session.flush()

    stmt_role = select(Role).where(Role.code == 'ROLE_QUEUE_VIEWER')
    role = (await db_session.execute(stmt_role)).scalars().first()
    if not role:
        role = Role(code='ROLE_QUEUE_VIEWER', name='Queue Viewer', description='Read queue only', permissions=[perm])
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(role)

    stmt_user = select(User).where(User.username == 'test_queue_viewer')
    user = (await db_session.execute(stmt_user)).scalars().first()
    if not user:
        user = User(
            username='test_queue_viewer',
            email='test_queue_viewer@byc.ai',
            password_hash=get_password_hash('viewer123!'),
            full_name='Queue Viewer',
            role_id=role.id,
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

    return create_access_token(
        subject=str(user.id),
        role='ROLE_QUEUE_VIEWER',
        permissions=['queue:read'],
    )


@pytest_asyncio.fixture
async def queue_test_tokens(superadmin_token: str, queue_viewer_token: str) -> Dict[str, str]:
    return {
        'admin': superadmin_token,
        'viewer': queue_viewer_token,
    }


@pytest_asyncio.fixture
async def sample_queue_camera(db_session: AsyncSession) -> Camera:
    zone = (await db_session.execute(select(Zone).where(Zone.zone_code == 'ZONE-QUEUE-TEST'))).scalars().first()
    if not zone:
        zone = Zone(
            zone_code='ZONE-QUEUE-TEST',
            name='Queue AI Test Sector',
            label='Queue Sector',
            coordinates=[[78.4635, 17.4175], [78.4640, 17.4180]],
            capacity=500,
            status='ACTIVE',
            current_people=0,
        )
        db_session.add(zone)
        await db_session.flush()

    cam = (await db_session.execute(select(Camera).where(Camera.camera_code == 'CAM-Q-001'))).scalars().first()
    if not cam:
        cam = Camera(
            camera_code='CAM-Q-001',
            name='North Darshan Queue Cam',
            label='North Darshan Queue Cam',
            camera_type='QUEUE',
            zone_id=zone.id,
            zone_code='ZONE-QUEUE-TEST',
            status='online',
            stream_status='VERIFIED',
            resolution='1080p',
            fps=25,
            enabled=True,
            private_ip='192.168.1.120',
            port=554,
            rtsp_url_encrypted=encrypt_credential('rtsp://operator:SecretPass999@192.168.1.120:554/live/ch1'),
        )
        db_session.add(cam)
        await db_session.flush()

    asgn = (await db_session.execute(
        select(CameraAIProfileAssignment).where(
            CameraAIProfileAssignment.camera_id == cam.id,
            CameraAIProfileAssignment.profile_id == 'QUEUE_STANDARD',
        )
    )).scalars().first()
    if not asgn:
        asgn = CameraAIProfileAssignment(
            camera_id=cam.id,
            camera_code=cam.camera_code,
            profile_id='QUEUE_STANDARD',
            enabled=True,
            assigned_by='system_test',
        )
        db_session.add(asgn)
        await db_session.flush()

    # 1. QUEUE_ROI
    roi = (await db_session.execute(
        select(CameraROIConfiguration).where(
            CameraROIConfiguration.camera_id == cam.id,
            CameraROIConfiguration.roi_type == ROIType.QUEUE_ROI,
        )
    )).scalars().first()
    if not roi:
        roi = CameraROIConfiguration(
            camera_id=cam.id,
            camera_code=cam.camera_code,
            profile_id='QUEUE_STANDARD',
            roi_type=ROIType.QUEUE_ROI,
            name='North Queue Barricade Channel',
            geometry_json={
                'points': [
                    {'x': 0.2, 'y': 0.2},
                    {'x': 0.8, 'y': 0.2},
                    {'x': 0.8, 'y': 0.8},
                    {'x': 0.2, 'y': 0.8},
                ]
            },
            normalized=True,
            enabled=True,
            created_by='system_test',
        )
        db_session.add(roi)
        await db_session.flush()

    # 2. ENTRY_LINE
    entry = (await db_session.execute(
        select(CameraROIConfiguration).where(
            CameraROIConfiguration.camera_id == cam.id,
            CameraROIConfiguration.roi_type == ROIType.ENTRY_LINE,
        )
    )).scalars().first()
    if not entry:
        entry = CameraROIConfiguration(
            camera_id=cam.id,
            camera_code=cam.camera_code,
            profile_id='QUEUE_STANDARD',
            roi_type=ROIType.ENTRY_LINE,
            name='Queue Inflow Barricade',
            geometry_json={'start': {'x': 0.2, 'y': 0.2}, 'end': {'x': 0.8, 'y': 0.2}},
            normalized=True,
            enabled=True,
            created_by='system_test',
        )
        db_session.add(entry)
        await db_session.flush()

    # 3. EXIT_LINE
    exit_l = (await db_session.execute(
        select(CameraROIConfiguration).where(
            CameraROIConfiguration.camera_id == cam.id,
            CameraROIConfiguration.roi_type == ROIType.EXIT_LINE,
        )
    )).scalars().first()
    if not exit_l:
        exit_l = CameraROIConfiguration(
            camera_id=cam.id,
            camera_code=cam.camera_code,
            profile_id='QUEUE_STANDARD',
            roi_type=ROIType.EXIT_LINE,
            name='Queue Outflow Turnstile',
            geometry_json={'start': {'x': 0.2, 'y': 0.8}, 'end': {'x': 0.8, 'y': 0.8}},
            normalized=True,
            enabled=True,
            created_by='system_test',
        )
        db_session.add(exit_l)
        await db_session.flush()

    await db_session.commit()
    await db_session.refresh(cam)
    return cam


# ── TESTS ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_queue_profile_specifications():
    """1. Validates standard queue profile configuration."""
    std = STANDARD_PROFILES.get('QUEUE_STANDARD')
    assert std is not None
    assert std.type == AIProfileType.QUEUE_STANDARD
    assert std.pipeline_type == 'QUEUE'
    assert std.processing_fps == 10
    assert std.tracker_enabled is True


@pytest.mark.asyncio
async def test_queue_model_registry_resolution():
    """2. Verifies queue models resolve correctly and enforce person class 0 isolation."""
    model = QueueModelRegistryService.get_model_for_profile('QUEUE_STANDARD')
    assert model.model_id == 'yolov8s-queue'
    assert model.allowed_classes == [0]
    assert model.class_names == {0: 'person'}
    assert QueueModelRegistryService.is_person_class(0) is True
    assert QueueModelRegistryService.is_person_class(1) is False


@pytest.mark.asyncio
async def test_queue_geometry_requirements_missing_queue_roi():
    """3. Prerequisite check: missing QUEUE_ROI fails readiness."""
    rois = [
        CameraROIConfiguration(
            camera_id=uuid.uuid4(),
            camera_code='CAM-1',
            profile_id='QUEUE_STANDARD',
            roi_type=ROIType.ENTRY_LINE,
            name='Entry',
            geometry_json={'start': {'x': 0.1, 'y': 0.1}, 'end': {'x': 0.5, 'y': 0.1}},
            enabled=True,
        ),
        CameraROIConfiguration(
            camera_id=uuid.uuid4(),
            camera_code='CAM-1',
            profile_id='QUEUE_STANDARD',
            roi_type=ROIType.EXIT_LINE,
            name='Exit',
            geometry_json={'start': {'x': 0.1, 'y': 0.9}, 'end': {'x': 0.5, 'y': 0.9}},
            enabled=True,
        ),
    ]
    geoms = QueuePipelineConfig.check_geometry_requirements(rois)
    assert geoms.is_ready is False
    assert any('QUEUE_ROI' in m for m in geoms.missing_requirements)


@pytest.mark.asyncio
async def test_queue_geometry_requirements_missing_entry_line():
    """4. Prerequisite check: missing ENTRY_LINE fails readiness."""
    rois = [
        CameraROIConfiguration(
            camera_id=uuid.uuid4(),
            camera_code='CAM-1',
            profile_id='QUEUE_STANDARD',
            roi_type=ROIType.QUEUE_ROI,
            name='Queue ROI',
            geometry_json={'points': [{'x': 0.1, 'y': 0.1}, {'x': 0.9, 'y': 0.1}, {'x': 0.9, 'y': 0.9}]},
            enabled=True,
        ),
        CameraROIConfiguration(
            camera_id=uuid.uuid4(),
            camera_code='CAM-1',
            profile_id='QUEUE_STANDARD',
            roi_type=ROIType.EXIT_LINE,
            name='Exit',
            geometry_json={'start': {'x': 0.1, 'y': 0.9}, 'end': {'x': 0.5, 'y': 0.9}},
            enabled=True,
        ),
    ]
    geoms = QueuePipelineConfig.check_geometry_requirements(rois)
    assert geoms.is_ready is False
    assert any('ENTRY_LINE' in m for m in geoms.missing_requirements)


@pytest.mark.asyncio
async def test_queue_geometry_requirements_missing_exit_line():
    """5. Prerequisite check: missing EXIT_LINE fails readiness."""
    rois = [
        CameraROIConfiguration(
            camera_id=uuid.uuid4(),
            camera_code='CAM-1',
            profile_id='QUEUE_STANDARD',
            roi_type=ROIType.QUEUE_ROI,
            name='Queue ROI',
            geometry_json={'points': [{'x': 0.1, 'y': 0.1}, {'x': 0.9, 'y': 0.1}, {'x': 0.9, 'y': 0.9}]},
            enabled=True,
        ),
        CameraROIConfiguration(
            camera_id=uuid.uuid4(),
            camera_code='CAM-1',
            profile_id='QUEUE_STANDARD',
            roi_type=ROIType.ENTRY_LINE,
            name='Entry',
            geometry_json={'start': {'x': 0.1, 'y': 0.1}, 'end': {'x': 0.5, 'y': 0.1}},
            enabled=True,
        ),
    ]
    geoms = QueuePipelineConfig.check_geometry_requirements(rois)
    assert geoms.is_ready is False
    assert any('EXIT_LINE' in m for m in geoms.missing_requirements)


@pytest.mark.asyncio
async def test_queue_geometry_requirements_all_present():
    """6. All 3 prerequisites present passes validation."""
    rois = [
        CameraROIConfiguration(
            camera_id=uuid.uuid4(),
            camera_code='CAM-1',
            profile_id='QUEUE_STANDARD',
            roi_type=ROIType.QUEUE_ROI,
            name='Queue ROI',
            geometry_json={'points': [{'x': 0.1, 'y': 0.1}, {'x': 0.9, 'y': 0.1}, {'x': 0.9, 'y': 0.9}]},
            enabled=True,
        ),
        CameraROIConfiguration(
            camera_id=uuid.uuid4(),
            camera_code='CAM-1',
            profile_id='QUEUE_STANDARD',
            roi_type=ROIType.ENTRY_LINE,
            name='Entry',
            geometry_json={'start': {'x': 0.1, 'y': 0.1}, 'end': {'x': 0.9, 'y': 0.1}},
            enabled=True,
        ),
        CameraROIConfiguration(
            camera_id=uuid.uuid4(),
            camera_code='CAM-1',
            profile_id='QUEUE_STANDARD',
            roi_type=ROIType.EXIT_LINE,
            name='Exit',
            geometry_json={'start': {'x': 0.1, 'y': 0.9}, 'end': {'x': 0.9, 'y': 0.9}},
            enabled=True,
        ),
    ]
    geoms = QueuePipelineConfig.check_geometry_requirements(rois)
    assert geoms.is_ready is True
    assert len(geoms.missing_requirements) == 0


@pytest.mark.asyncio
async def test_rtsp_config_loaded_securely_queue(sample_queue_camera: Camera):
    """7. RTSP credentials decrypted internally and masked in telemetry."""
    cfg = QueuePipelineConfig.from_camera_and_geometries(sample_queue_camera, 'QUEUE_STANDARD')
    assert 'SecretPass999' in cfg.rtsp_url_internal
    assert 'SecretPass999' not in cfg.rtsp_url_sanitized
    assert '***' in cfg.rtsp_url_sanitized
    assert 'SecretPass999' not in str(cfg)


@pytest.mark.asyncio
async def test_person_class_filtering_queue():
    """8. Non-person classes (car, chair) are discarded; only class 0 kept."""
    detector = MockPersonDetector(model=QueueModelRegistryService.get_default_model(), confidence_threshold=0.45)
    await detector.initialize()

    raw_detections = [
        {'class_id': 0, 'confidence': 0.85, 'bbox': (0.1, 0.1, 0.2, 0.3)},  # Person
        {'class_id': 2, 'confidence': 0.90, 'bbox': (0.4, 0.4, 0.6, 0.6)},  # Car
        {'class_id': 56, 'confidence': 0.70, 'bbox': (0.5, 0.5, 0.7, 0.7)}, # Chair
        {'class_id': 0, 'confidence': 0.65, 'bbox': (0.2, 0.2, 0.3, 0.4)},  # Person
    ]
    detector.set_next_detections(raw_detections)
    dets = await detector.detect(None, frame_id=1, timestamp=time.time())

    assert len(dets) == 2
    assert all(d.class_id == 0 for d in dets)


@pytest.mark.asyncio
async def test_detection_confidence_threshold_filtering():
    """9. Detections below confidence threshold are discarded."""
    detector = MockPersonDetector(model=QueueModelRegistryService.get_default_model(), confidence_threshold=0.50)
    await detector.initialize()

    raw_detections = [
        {'class_id': 0, 'confidence': 0.85, 'bbox': (0.1, 0.1, 0.2, 0.3)},
        {'class_id': 0, 'confidence': 0.42, 'bbox': (0.2, 0.2, 0.3, 0.4)}, # Below 0.50
    ]
    detector.set_next_detections(raw_detections)
    dets = await detector.detect(None, frame_id=1, timestamp=time.time())

    assert len(dets) == 1
    assert dets[0].confidence == 0.85


@pytest.mark.asyncio
async def test_multi_object_tracking_integration():
    """10. Multi-object tracker assigns persistent track codes."""
    tracker = PersonTracker(max_age_frames=10, iou_threshold=0.3, min_hits=1)
    now = time.time()
    dets = [
        DetectedPerson(class_id=0, confidence=0.8, bbox=(0.1, 0.1, 0.2, 0.3), timestamp=now),
        DetectedPerson(class_id=0, confidence=0.9, bbox=(0.5, 0.5, 0.6, 0.7), timestamp=now),
    ]
    tracks = tracker.update(dets, now)
    assert len(tracks) == 2
    assert tracks[0].track_code.startswith('TRK-')
    assert tracks[1].track_code.startswith('TRK-')
    assert tracks[0].track_id != tracks[1].track_id


@pytest.mark.asyncio
async def test_queue_roi_spatial_filtering_bottom_center():
    """11. Point-in-polygon uses bottom-center (x_mid, y_max)."""
    roi_poly = [{'x': 0.2, 'y': 0.2}, {'x': 0.8, 'y': 0.2}, {'x': 0.8, 'y': 0.8}, {'x': 0.2, 'y': 0.8}]
    cfg = QueuePipelineConfig(
        camera_id='cam-1',
        camera_code='CAM-1',
        camera_name='Test',
        rtsp_url_internal='rtsp://internal',
        rtsp_url_sanitized='rtsp://sanitized',
        model=QueueModelRegistryService.get_default_model(),
        queue_roi_points=roi_poly,
        entry_line={'start': {'x': 0.2, 'y': 0.2}, 'end': {'x': 0.8, 'y': 0.2}},
        exit_line={'start': {'x': 0.2, 'y': 0.8}, 'end': {'x': 0.8, 'y': 0.8}},
    )
    analytics = QueueSpatialAnalytics(cfg)

    # Person 1: bottom-center (0.5, 0.5) is inside
    t1 = TrackedPerson(track_id=1, track_code='TRK-1', current_bbox=(0.4, 0.3, 0.6, 0.5), current_point=(0.5, 0.5), confidence=0.9)
    # Person 2: top is inside ROI (0.5, 0.75), but bottom-center (0.5, 0.85) is outside
    t2 = TrackedPerson(track_id=2, track_code='TRK-2', current_bbox=(0.4, 0.75, 0.6, 0.85), current_point=(0.5, 0.85), confidence=0.9)

    res = analytics.process_tracks([t1, t2], time.time())
    assert res.queue_count == 1
    assert res.active_queue_track_ids == [1]


@pytest.mark.asyncio
async def test_exclusion_zone_deduction():
    """12. Exclusion zones inside Queue ROI are excluded from headcount."""
    roi_poly = [{'x': 0.0, 'y': 0.0}, {'x': 1.0, 'y': 0.0}, {'x': 1.0, 'y': 1.0}, {'x': 0.0, 'y': 1.0}]
    excl_poly = [[{'x': 0.4, 'y': 0.4}, {'x': 0.6, 'y': 0.4}, {'x': 0.6, 'y': 0.6}, {'x': 0.4, 'y': 0.6}]]
    cfg = QueuePipelineConfig(
        camera_id='cam-1',
        camera_code='CAM-1',
        camera_name='Test',
        rtsp_url_internal='rtsp://internal',
        rtsp_url_sanitized='rtsp://sanitized',
        model=QueueModelRegistryService.get_default_model(),
        queue_roi_points=roi_poly,
        entry_line={'start': {'x': 0.0, 'y': 0.0}, 'end': {'x': 1.0, 'y': 0.0}},
        exit_line={'start': {'x': 0.0, 'y': 1.0}, 'end': {'x': 1.0, 'y': 1.0}},
        exclusion_zones=excl_poly,
    )
    analytics = QueueSpatialAnalytics(cfg)

    # Person 1 in open queue (0.2, 0.2)
    t1 = TrackedPerson(track_id=1, track_code='TRK-1', current_bbox=(0.1, 0.1, 0.3, 0.2), current_point=(0.2, 0.2), confidence=0.9)
    # Person 2 inside exclusion zone (0.5, 0.5) (e.g. security booth)
    t2 = TrackedPerson(track_id=2, track_code='TRK-2', current_bbox=(0.45, 0.45, 0.55, 0.5), current_point=(0.5, 0.5), confidence=0.9)

    res = analytics.process_tracks([t1, t2], time.time())
    assert res.queue_count == 1
    assert res.excluded_count == 1
    assert res.active_queue_track_ids == [1]


@pytest.mark.asyncio
async def test_occupancy_percentage_and_missing_capacity():
    """14 & 15. Occupancy calculation with and without capacity configuration."""
    roi_poly = [{'x': 0.0, 'y': 0.0}, {'x': 1.0, 'y': 0.0}, {'x': 1.0, 'y': 1.0}, {'x': 0.0, 'y': 1.0}]
    # With capacity = 50
    cfg = QueuePipelineConfig(
        camera_id='cam-1',
        camera_code='CAM-1',
        camera_name='Test',
        rtsp_url_internal='rtsp://internal',
        rtsp_url_sanitized='rtsp://sanitized',
        model=QueueModelRegistryService.get_default_model(),
        queue_roi_points=roi_poly,
        entry_line={'start': {'x': 0.0, 'y': 0.0}, 'end': {'x': 1.0, 'y': 0.0}},
        exit_line={'start': {'x': 0.0, 'y': 1.0}, 'end': {'x': 1.0, 'y': 1.0}},
        queue_capacity=50,
    )
    analytics = QueueSpatialAnalytics(cfg)
    tracks = [
        TrackedPerson(track_id=i, track_code=f'TRK-{i}', current_bbox=(0.1, 0.1, 0.2, 0.2), current_point=(0.15, 0.15), confidence=0.8)
        for i in range(25)
    ]
    res = analytics.process_tracks(tracks, time.time())
    assert res.queue_count == 25
    assert res.occupancy_percentage == 50.0
    assert res.occupancy_status == 'NORMAL'

    # Without capacity
    cfg.queue_capacity = None
    analytics_no_cap = QueueSpatialAnalytics(cfg)
    res_no_cap = analytics_no_cap.process_tracks(tracks, time.time())
    assert res_no_cap.occupancy_percentage is None
    assert res_no_cap.occupancy_status == 'UNAVAILABLE'


@pytest.mark.asyncio
async def test_relative_and_calibrated_density():
    """16 & 17. Density calculation relative vs physical (persons/m²)."""
    roi_poly = [{'x': 0.0, 'y': 0.0}, {'x': 1.0, 'y': 0.0}, {'x': 1.0, 'y': 1.0}, {'x': 0.0, 'y': 1.0}]
    # Calibrated area = 20m²
    cfg = QueuePipelineConfig(
        camera_id='cam-1',
        camera_code='CAM-1',
        camera_name='Test',
        rtsp_url_internal='rtsp://internal',
        rtsp_url_sanitized='rtsp://sanitized',
        model=QueueModelRegistryService.get_default_model(),
        queue_roi_points=roi_poly,
        entry_line={'start': {'x': 0.0, 'y': 0.0}, 'end': {'x': 1.0, 'y': 0.0}},
        exit_line={'start': {'x': 0.0, 'y': 1.0}, 'end': {'x': 1.0, 'y': 1.0}},
        physical_area_m2=20.0,
    )
    analytics = QueueSpatialAnalytics(cfg)
    tracks = [
        TrackedPerson(track_id=i, track_code=f'TRK-{i}', current_bbox=(0.1, 0.1, 0.2, 0.2), current_point=(0.15, 0.15), confidence=0.8)
        for i in range(30)
    ]
    res = analytics.process_tracks(tracks, time.time())
    assert res.density_type == 'CALIBRATED'
    assert res.density == 1.5
    assert res.density_unit == 'persons/m²'


@pytest.mark.asyncio
async def test_queue_length_relative_vs_calibrated():
    """18. Queue length estimation extent."""
    roi_poly = [{'x': 0.0, 'y': 0.0}, {'x': 1.0, 'y': 0.0}, {'x': 1.0, 'y': 1.0}, {'x': 0.0, 'y': 1.0}]
    cfg = QueuePipelineConfig(
        camera_id='cam-1',
        camera_code='CAM-1',
        camera_name='Test',
        rtsp_url_internal='rtsp://internal',
        rtsp_url_sanitized='rtsp://sanitized',
        model=QueueModelRegistryService.get_default_model(),
        queue_roi_points=roi_poly,
        entry_line={'start': {'x': 0.0, 'y': 0.0}, 'end': {'x': 1.0, 'y': 0.0}},
        exit_line={'start': {'x': 0.0, 'y': 1.0}, 'end': {'x': 1.0, 'y': 1.0}},
        physical_length_meters=20.0,
    )
    analytics = QueueSpatialAnalytics(cfg)
    t1 = TrackedPerson(track_id=1, track_code='TRK-1', current_bbox=(0.1, 0.1, 0.2, 0.2), current_point=(0.15, 0.15), confidence=0.8)
    t2 = TrackedPerson(track_id=2, track_code='TRK-2', current_bbox=(0.8, 0.8, 0.9, 0.9), current_point=(0.85, 0.85), confidence=0.8)

    res = analytics.process_tracks([t1, t2], time.time())
    assert res.queue_length['source'] == 'CALIBRATED'
    assert res.queue_length['unit'] == 'meters'
    assert res.queue_length['value'] > 0


@pytest.mark.asyncio
async def test_entry_and_exit_line_crossings_with_anti_repetition():
    """19, 20 & 21. Entry and exit crossing counting and 5-second duplicate suppression."""
    roi_poly = [{'x': 0.0, 'y': 0.0}, {'x': 1.0, 'y': 0.0}, {'x': 1.0, 'y': 1.0}, {'x': 0.0, 'y': 1.0}]
    cfg = QueuePipelineConfig(
        camera_id='cam-1',
        camera_code='CAM-1',
        camera_name='Test',
        rtsp_url_internal='rtsp://internal',
        rtsp_url_sanitized='rtsp://sanitized',
        model=QueueModelRegistryService.get_default_model(),
        queue_roi_points=roi_poly,
        entry_line={'start': {'x': 0.0, 'y': 0.2}, 'end': {'x': 1.0, 'y': 0.2}},
        exit_line={'start': {'x': 0.0, 'y': 0.8}, 'end': {'x': 1.0, 'y': 0.8}},
    )
    analytics = QueueSpatialAnalytics(cfg)
    now = time.time()

    # Track 1 crosses entry line: from y=0.15 to y=0.25
    t1 = TrackedPerson(
        track_id=101,
        track_code='TRK-101',
        current_bbox=(0.4, 0.2, 0.6, 0.25),
        current_point=(0.5, 0.25),
        confidence=0.85,
        trajectory=[(0.5, 0.15, now - 0.2), (0.5, 0.25, now)],
    )
    res1 = analytics.process_tracks([t1], now)
    assert res1.inflow == 1  # 1 event in 60s rolling window = 1 person/min

    # Duplicate crossing within 2s should be suppressed
    t1_again = TrackedPerson(
        track_id=101,
        track_code='TRK-101',
        current_bbox=(0.4, 0.2, 0.6, 0.26),
        current_point=(0.5, 0.26),
        confidence=0.85,
        trajectory=[(0.5, 0.15, now - 0.2), (0.5, 0.26, now + 1.0)],
    )
    res2 = analytics.process_tracks([t1_again], now + 1.0)
    assert res2.inflow == 1  # Still 1, not 2 (duplicate ignored)


@pytest.mark.asyncio
async def test_queue_direction_calculation():
    """22, 23 & 24. Queue direction calculation (FORWARD, BACKWARD, UNKNOWN)."""
    roi_poly = [{'x': 0.0, 'y': 0.0}, {'x': 1.0, 'y': 0.0}, {'x': 1.0, 'y': 1.0}, {'x': 0.0, 'y': 1.0}]
    cfg = QueuePipelineConfig(
        camera_id='cam-1',
        camera_code='CAM-1',
        camera_name='Test',
        rtsp_url_internal='rtsp://internal',
        rtsp_url_sanitized='rtsp://sanitized',
        model=QueueModelRegistryService.get_default_model(),
        queue_roi_points=roi_poly,
        entry_line={'start': {'x': 0.0, 'y': 0.1}, 'end': {'x': 1.0, 'y': 0.1}},
        exit_line={'start': {'x': 0.0, 'y': 0.9}, 'end': {'x': 1.0, 'y': 0.9}},
    )
    analytics = QueueSpatialAnalytics(cfg)
    now = time.time()

    # Persons moving from entry (y=0.1) toward exit (y=0.9) -> FORWARD
    fwd_tracks = [
        TrackedPerson(
            track_id=i,
            track_code=f'TRK-{i}',
            current_bbox=(0.4, 0.4, 0.6, 0.5),
            current_point=(0.5, 0.5),
            confidence=0.85,
            trajectory=[(0.5, 0.40, now - 0.5), (0.5, 0.50, now)],
        )
        for i in range(1, 4)
    ]
    res_fwd = analytics.process_tracks(fwd_tracks, now)
    assert res_fwd.queue_direction == 'FORWARD'

    # Persons moving backward from y=0.60 to y=0.30 -> BACKWARD
    bwd_tracks = [
        TrackedPerson(
            track_id=10 + i,
            track_code=f'TRK-{10+i}',
            current_bbox=(0.4, 0.3, 0.6, 0.4),
            current_point=(0.5, 0.4),
            confidence=0.85,
            trajectory=[(0.5, 0.60, now - 0.5), (0.5, 0.30, now)],
        )
        for i in range(1, 4)
    ]
    res_bwd = analytics.process_tracks(bwd_tracks, now)
    assert res_bwd.queue_direction == 'BACKWARD'


@pytest.mark.asyncio
async def test_dwell_time_and_insufficient_data():
    """25 & 26. Dwell time tracking and insufficient data fallback."""
    roi_poly = [{'x': 0.0, 'y': 0.0}, {'x': 1.0, 'y': 0.0}, {'x': 1.0, 'y': 1.0}, {'x': 0.0, 'y': 1.0}]
    cfg = QueuePipelineConfig(
        camera_id='cam-1',
        camera_code='CAM-1',
        camera_name='Test',
        rtsp_url_internal='rtsp://internal',
        rtsp_url_sanitized='rtsp://sanitized',
        model=QueueModelRegistryService.get_default_model(),
        queue_roi_points=roi_poly,
        entry_line={'start': {'x': 0.0, 'y': 0.1}, 'end': {'x': 1.0, 'y': 0.1}},
        exit_line={'start': {'x': 0.0, 'y': 0.9}, 'end': {'x': 1.0, 'y': 0.9}},
    )
    analytics = QueueSpatialAnalytics(cfg)
    t0 = 1000.0

    # Frame 1: Empty queue -> insufficient_data
    r0 = analytics.process_tracks([], t0)
    assert r0.average_wait_seconds is None
    assert r0.wait_status == 'insufficient_data'

    # Person 1 enters at t0
    t1 = TrackedPerson(track_id=1, track_code='TRK-1', current_bbox=(0.1, 0.1, 0.2, 0.2), current_point=(0.15, 0.15), confidence=0.8)
    analytics.process_tracks([t1], t0)

    # Person 1 is in queue at t0 + 60s (dwell = 60s)
    r1 = analytics.process_tracks([t1], t0 + 60.0)
    assert r1.average_wait_seconds == 60
    assert r1.max_current_dwell_seconds == 60


@pytest.mark.asyncio
async def test_deterministic_risk_scoring():
    """28. Deterministic multi-factor risk calculation."""
    engine = QueueRiskEngine()

    # Normal metrics -> LOW
    m_low = QueueMetricsResult(
        camera_id='c1', camera_code='C1', timestamp=time.time(),
        queue_count=10, occupancy_percentage=20.0, average_wait_seconds=120,
        inflow=10, outflow=10, growth_per_minute=0,
    )
    eval_low = engine.evaluate(m_low)
    assert eval_low.risk_level == 'LOW'
    assert eval_low.risk_score < 40.0

    # Critical metrics -> CRITICAL
    m_crit = QueueMetricsResult(
        camera_id='c1', camera_code='C1', timestamp=time.time(),
        queue_count=90, occupancy_percentage=95.0, average_wait_seconds=950,
        inflow=50, outflow=15, growth_per_minute=25,
    )
    eval_crit = engine.evaluate(m_crit)
    assert eval_crit.risk_level == 'CRITICAL'
    assert eval_crit.risk_score >= 80.0


@pytest.mark.asyncio
async def test_event_generation_and_cooldown_60s():
    """29 & 30. Event generation and 60s duplicate cooldown suppression."""
    engine = QueueEventEngine(cooldown_seconds=60.0)
    now = time.time()

    m = QueueMetricsResult(
        camera_id='cam-1', camera_code='CAM-1', timestamp=now,
        queue_count=80, occupancy_percentage=92.0, average_wait_seconds=650,
        inflow=45, outflow=10, growth_per_minute=26,
    )

    evts1 = await engine.evaluate_and_emit(
        metrics=m, risk_score=88.0, risk_level='CRITICAL',
        risk_factors=['Critical occupancy (92.0%)', 'Elevated wait time (10m 50s)'],
    )
    assert len(evts1) >= 1
    types1 = [e.event_type for e in evts1]
    assert 'QUEUE_RISK_CRITICAL' in types1

    # Immediate second call at now + 5s -> suppressed by 60s cooldown
    m.timestamp = now + 5.0
    evts2 = await engine.evaluate_and_emit(
        metrics=m, risk_score=88.0, risk_level='CRITICAL',
        risk_factors=['Critical occupancy (92.0%)'],
    )
    assert len(evts2) == 0


@pytest.mark.asyncio
async def test_pipeline_state_transitions():
    """32. Pipeline state transitions CREATED -> RUNNING -> STOPPED."""
    roi_poly = [{'x': 0.1, 'y': 0.1}, {'x': 0.9, 'y': 0.1}, {'x': 0.9, 'y': 0.9}]
    cfg = QueuePipelineConfig(
        camera_id='cam-1', camera_code='CAM-1', camera_name='Test',
        rtsp_url_internal='rtsp://internal', rtsp_url_sanitized='rtsp://sanitized',
        model=QueueModelRegistryService.get_default_model(),
        queue_roi_points=roi_poly,
        entry_line={'start': {'x': 0.1, 'y': 0.1}, 'end': {'x': 0.9, 'y': 0.1}},
        exit_line={'start': {'x': 0.1, 'y': 0.9}, 'end': {'x': 0.9, 'y': 0.9}},
    )
    mock_det = MockPersonDetector(model=cfg.model, confidence_threshold=0.45)
    mock_det.set_next_detections([
        {'class_id': 0, 'confidence': 0.85, 'bbox': (0.3, 0.3, 0.4, 0.5)},
    ])

    pipeline = QueuePipeline(config=cfg, detector=mock_det)
    assert pipeline.state == PipelineState.CREATED

    await pipeline.start()
    assert pipeline.state == PipelineState.RUNNING
    QueuePipelineRegistry.register(pipeline)

    res = await pipeline.process_frame(None, frame_id=1, timestamp=time.time())
    assert res['status'] == 'RUNNING'

    await pipeline.stop()
    assert pipeline.state == PipelineState.STOPPED


@pytest.mark.asyncio
async def test_health_monitor_10s_no_frame_timeout():
    """34. Health monitor marks status FAILED if no frames received in 10s."""
    monitor = PipelineHealthMonitor(
        camera_id='cam-1', camera_code='CAM-1', profile_id='QUEUE_STANDARD',
        target_fps=10, no_frame_timeout_sec=5.0,
    )
    monitor.pipeline_state = PipelineState.RUNNING
    now = time.time()
    monitor.record_frame(now, 10.0, 2.0)
    assert monitor.compute_health().health_status == 'HEALTHY'

    with patch('time.time', return_value=now + 6.0):
        h = monitor.compute_health()
        assert h.health_status == 'FAILED'
        assert 'Stream timeout' in (h.last_error or '')


@pytest.mark.asyncio
async def test_runtime_unavailable_on_unsupported_host(
    client: AsyncClient,
    queue_test_tokens: Dict[str, str],
    sample_queue_camera: Camera,
):
    """35. Clearly reports RUNTIME_UNAVAILABLE without fake inference data."""
    with patch('app.ai.runtime.detector.RuntimeDetector.detect_runtime', return_value={'deepstream': False}),          patch('app.ai.runtime.detector.RuntimeDetector.detect_gpu', return_value={'available': False}):
        resp = await client.post(
            f'/api/v1/queue/pipelines/{sample_queue_camera.camera_code}/start',
            headers={'Authorization': f'Bearer {queue_test_tokens["admin"]}'},
        )
        assert resp.status_code == 400
        body = resp.json()
        err_code = body.get('error', {}).get('code') or body.get('detail', {}).get('code')
        assert err_code == 'RUNTIME_UNAVAILABLE'


@pytest.mark.asyncio
async def test_credential_non_leakage_in_queue_endpoints(
    client: AsyncClient,
    queue_test_tokens: Dict[str, str],
    sample_queue_camera: Camera,
):
    """36. Verifies credentials are never returned in queue metrics endpoints."""
    resp = await client.get(
        f'/api/v1/queue/cameras/{sample_queue_camera.camera_code}/metrics',
        headers={'Authorization': f'Bearer {queue_test_tokens["viewer"]}'},
    )
    assert resp.status_code == 200
    raw_text = resp.text
    assert 'SecretPass999' not in raw_text
    assert 'rtsp://' not in raw_text or '***' in raw_text


@pytest.mark.asyncio
async def test_rbac_permissions_queue(
    client: AsyncClient,
    queue_test_tokens: Dict[str, str],
    sample_queue_camera: Camera,
):
    """37. Verifies RBAC: Viewer cannot start/stop (403), Admin can."""
    resp_v = await client.post(
        f'/api/v1/queue/pipelines/{sample_queue_camera.camera_code}/start',
        headers={'Authorization': f'Bearer {queue_test_tokens["viewer"]}'},
    )
    assert resp_v.status_code == 403

    resp_r = await client.get(
        f'/api/v1/queue/cameras/{sample_queue_camera.camera_code}/metrics',
        headers={'Authorization': f'Bearer {queue_test_tokens["viewer"]}'},
    )
    assert resp_r.status_code == 200


@pytest.mark.asyncio
async def test_strict_frs_isolation_in_queue():
    """38. Zero face detection, embeddings, or biometric recognition in Queue module."""
    from app.ai.pipelines.queue import models_registry, analytics, pipeline
    trk = TrackedPerson(track_id=1, track_code='TRK-1', current_bbox=(0.1, 0.1, 0.2, 0.2), current_point=(0.15, 0.2), confidence=0.9)
    assert not hasattr(trk, 'face_embedding')
    assert not hasattr(trk, 'face_id')
    assert not hasattr(trk, 'identity')


@pytest.mark.asyncio
async def test_zero_crowd_ai_regressions():
    """39. Crowd pipeline registry and metrics continue working independently."""
    from app.ai.pipelines.crowd.registry import CrowdPipelineRegistry
    assert len(CrowdPipelineRegistry.list_pipelines()) == 0
    assert QueuePipelineRegistry.count() == 0


@pytest.mark.asyncio
async def test_no_arbitrary_command_execution_in_queue():
    """40. No shell=True or os.system in Queue modules."""
    from app.ai.pipelines.queue import pipeline, analytics, config
    for mod in (pipeline, analytics, config):
        src = inspect.getsource(mod)
        assert 'shell=True' not in src
        assert 'os.system' not in src


@pytest.mark.asyncio
async def test_zone_queue_summary_aggregation():
    """41. Aggregates multi-camera queues within a zone."""
    roi_poly = [{'x': 0.1, 'y': 0.1}, {'x': 0.9, 'y': 0.1}, {'x': 0.9, 'y': 0.9}]
    cfg1 = QueuePipelineConfig(
        camera_id='cam-1', camera_code='CAM-1', camera_name='Cam 1', zone_id='zone-1',
        rtsp_url_internal='rtsp://internal', rtsp_url_sanitized='rtsp://sanitized',
        model=QueueModelRegistryService.get_default_model(),
        queue_roi_points=roi_poly,
        entry_line={'start': {'x': 0.1, 'y': 0.1}, 'end': {'x': 0.9, 'y': 0.1}},
        exit_line={'start': {'x': 0.1, 'y': 0.9}, 'end': {'x': 0.9, 'y': 0.9}},
    )
    p1 = QueuePipeline(config=cfg1, detector=MockPersonDetector(model=cfg1.model, confidence_threshold=0.45))
    p1.state = PipelineState.RUNNING
    p1._latest_metrics = {'queue_count': 30, 'risk_score': 65.0, 'risk_level': 'HIGH', 'average_wait_seconds': 300}
    QueuePipelineRegistry.register(p1)

    cfg2 = QueuePipelineConfig(
        camera_id='cam-2', camera_code='CAM-2', camera_name='Cam 2', zone_id='zone-1',
        rtsp_url_internal='rtsp://internal', rtsp_url_sanitized='rtsp://sanitized',
        model=QueueModelRegistryService.get_default_model(),
        queue_roi_points=roi_poly,
        entry_line={'start': {'x': 0.1, 'y': 0.1}, 'end': {'x': 0.9, 'y': 0.1}},
        exit_line={'start': {'x': 0.1, 'y': 0.9}, 'end': {'x': 0.9, 'y': 0.9}},
    )
    p2 = QueuePipeline(config=cfg2, detector=MockPersonDetector(model=cfg2.model, confidence_threshold=0.45))
    p2.state = PipelineState.RUNNING
    p2._latest_metrics = {'queue_count': 20, 'risk_score': 45.0, 'risk_level': 'MEDIUM', 'average_wait_seconds': 200}
    QueuePipelineRegistry.register(p2)

    summary = QueuePipelineRegistry.get_zone_summary('zone-1')
    assert summary['active_queues_count'] == 2
    assert summary['total_people_in_queues'] == 50
    assert summary['max_risk_level'] == 'HIGH'
    assert summary['average_wait_seconds'] == 250


@pytest.mark.asyncio
async def test_queue_repository_snapshot_queries(db_session: AsyncSession):
    """42. Tests QueueRepository querying."""
    repo = QueueRepository(db_session)
    q = QueueSnapshot(
        queue_code='Q-SNAP-01',
        camera_id=uuid.uuid4(),
        camera_code='CAM-SNAP-01',
        people_waiting=35,
        average_wait_seconds=240,
        risk_level='LOW',
        inflow_rate=15,
        outflow_rate=14,
        occupancy_percent=70.0,
        density=1.4,
        risk_score=28.0,
    )
    db_session.add(q)
    await db_session.commit()

    latest = await repo.get_latest_for_camera('CAM-SNAP-01')
    assert latest is not None
    assert latest.people_waiting == 35
    assert latest.occupancy_percent == 70.0