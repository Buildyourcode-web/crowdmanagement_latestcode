"""
test_production_counting.py — Comprehensive test suite for production-grade counting:
- Vector normal and signed distance calculations
- Spatial boundary state machine (OUTSIDE -> BUFFER -> INSIDE)
- Anti-duplicate debounce and hysteresis tolerances
- ByteTrack 2-stage association and occlusion recovery
- Idempotency key determinism and ledger consistency
"""

import time
import pytest
from app.ai.pipelines.crowd.analytics import (
    get_line_unit_normal,
    get_signed_distance_to_line,
    check_segment_intersection,
    CrowdSpatialAnalytics,
    ValidatedCrossing,
)
from app.ai.pipelines.crowd.config import CrowdPipelineConfig
from app.ai.pipelines.crowd.detector import DetectedPerson
from app.ai.pipelines.crowd.models_registry import PersonDetectionModel
from app.ai.pipelines.crowd.tracker import PersonTracker, TrackedPerson, TrackState


def test_line_unit_normal_and_signed_distance():
    # Horizontal line from (0.0, 0.5) to (1.0, 0.5)
    l1 = (0.0, 0.5)
    l2 = (1.0, 0.5)
    normal = get_line_unit_normal(l1, l2)
    
    # Normal should point in the +y direction (downwards / inside)
    assert pytest.approx(normal[0], abs=1e-5) == 0.0
    assert pytest.approx(normal[1], abs=1e-5) == 1.0

    # Point on outside side (y = 0.3)
    p_outside = (0.5, 0.3)
    d_out = get_signed_distance_to_line(p_outside, l1, l2, normal)
    assert d_out < 0.0
    assert pytest.approx(d_out, abs=1e-4) == -0.2

    # Point on inside side (y = 0.7)
    p_inside = (0.5, 0.7)
    d_in = get_signed_distance_to_line(p_inside, l1, l2, normal)
    assert d_in > 0.0
    assert pytest.approx(d_in, abs=1e-4) == 0.2

    # Point directly on line (y = 0.5)
    p_on_line = (0.5, 0.5)
    d_on = get_signed_distance_to_line(p_on_line, l1, l2, normal)
    assert pytest.approx(d_on, abs=1e-5) == 0.0


def test_segment_intersection():
    l1 = (0.0, 0.5)
    l2 = (1.0, 0.5)

    # Crossing movement downwards (IN): (0.5, 0.2) -> (0.5, 0.8)
    p1 = (0.5, 0.2)
    p2 = (0.5, 0.8)
    assert check_segment_intersection(p1, p2, l1, l2) == "IN"

    # Crossing movement upwards (OUT): (0.5, 0.8) -> (0.5, 0.2)
    assert check_segment_intersection(p2, p1, l1, l2) == "OUT"

    # Non-crossing movement: (0.5, 0.1) -> (0.5, 0.4)
    p3 = (0.5, 0.1)
    p4 = (0.5, 0.4)
    assert check_segment_intersection(p3, p4, l1, l2) is None

    # Parallel movement: (0.2, 0.3) -> (0.8, 0.3)
    p5 = (0.2, 0.3)
    p6 = (0.8, 0.3)
    assert check_segment_intersection(p5, p6, l1, l2) is None


def test_boundary_state_machine_and_hysteresis():
    dummy_model = PersonDetectionModel(
        model_id="yolo11x-onnx",
        name="YOLO11x ONNX",
        version="11.0",
        format="ONNX",
        input_width=1280,
        input_height=1280,
        confidence_threshold=0.45,
        iou_threshold=0.45,
        description="High-density crowd person detector",
    )
    config = CrowdPipelineConfig(
        camera_id="cam-001",
        camera_code="CAM-KHB-001",
        camera_name="Main Entry Gate",
        event_id="evt-vigneshwara",
        rtsp_url_internal="rtsp://dummy",
        rtsp_url_sanitized="rtsp://sanitized",
        model=dummy_model,
        crowd_roi_points=[{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0}],
        counting_lines=[{
            "id": "LINE-ENTRY-01",
            "name": "Gate A Entry",
            "start": {"x": 0.0, "y": 0.5},
            "end": {"x": 1.0, "y": 0.5},
            "direction": "IN",
        }],
    )
    analytics = CrowdSpatialAnalytics(config)

    now = time.time()
    trk = TrackedPerson(
        track_id=1042,
        track_code="TRK-1042",
        track_session_id="session-abc123",
        current_bbox=(0.45, 0.1, 0.55, 0.3),
        current_point=(0.5, 0.3),
        confidence=0.88,
        trajectory=[(0.5, 0.3, now)],
    )

    # Frame 1: Person is OUTSIDE
    metrics = analytics.process_tracks([trk], now, frame_id=1)
    crossings = analytics.get_and_clear_crossings()
    assert trk.boundary_state == "OUTSIDE"
    assert trk.confirmed_outside is True
    assert len(crossings) == 0

    # Frame 2: Person steps into BUFFER_ZONE (dist ≈ 0.01)
    trk.trajectory.append((0.5, 0.49, now + 0.04))
    trk.current_point = (0.5, 0.49)
    metrics = analytics.process_tracks([trk], now + 0.04, frame_id=2)
    crossings = analytics.get_and_clear_crossings()
    assert trk.boundary_state == "BUFFER_ZONE"
    assert len(crossings) == 0  # No premature crossing in buffer

    # Frame 3: Person completes crossing into INSIDE zone with clearance (y = 0.65)
    trk.trajectory.append((0.5, 0.65, now + 0.08))
    trk.current_point = (0.5, 0.65)
    metrics = analytics.process_tracks([trk], now + 0.08, frame_id=3)
    crossings = analytics.get_and_clear_crossings()
    assert trk.boundary_state == "INSIDE"
    assert len(crossings) == 1
    
    crossing = crossings[0]
    assert crossing.direction == "IN"
    assert crossing.count_delta == 1
    assert crossing.track_token == "TRK-1042"
    assert crossing.crossing_sequence == 1
    assert crossing.idempotency_key == "evt-vigneshwara_cam-001_LINE-ENTRY-01_session-abc123_CROSSING-001"

    # Frame 4: Person continues walking deeper inside (y = 0.80) -> MUST NOT duplicate count
    trk.trajectory.append((0.5, 0.80, now + 0.12))
    trk.current_point = (0.5, 0.80)
    metrics = analytics.process_tracks([trk], now + 0.12, frame_id=4)
    crossings = analytics.get_and_clear_crossings()
    assert len(crossings) == 0  # Debounced, no duplicate!


def test_bytetrack_two_stage_association():
    tracker = PersonTracker(
        max_age_frames=30,
        min_hits=1,
        high_threshold=0.50,
        low_threshold=0.15,
        iou_threshold=0.25,
        iou_low_threshold=0.15,
    )
    now = time.time()

    # Frame 1: High confidence detection -> creates new track
    det1 = DetectedPerson(
        class_id=0,
        confidence=0.92,
        bbox=(0.4, 0.4, 0.6, 0.8),
        timestamp=now,
    )
    tracks_f1 = tracker.update([det1], now)
    assert len(tracks_f1) == 1
    t1 = tracks_f1[0]
    assert t1.track_state == TrackState.TRACKED
    assigned_id = t1.track_id

    # Frame 2: Person is partially occluded / blurred -> confidence drops to 0.30 (low confidence)
    det2_occluded = DetectedPerson(
        class_id=0,
        confidence=0.30,
        bbox=(0.42, 0.42, 0.62, 0.82),
        timestamp=now + 0.05,
    )
    tracks_f2 = tracker.update([det2_occluded], now + 0.05)
    assert len(tracks_f2) == 1
    assert tracks_f2[0].track_id == assigned_id
    assert tracks_f2[0].hits == 2
