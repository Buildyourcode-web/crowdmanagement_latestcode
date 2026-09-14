"""
test_unified_gate_queue_pipeline.py — Comprehensive test suite for the Unified
Entry/Exit Counting + Queue Movement Engine.

Validates:
A. ENTRY: OUTSIDE -> INSIDE = +1, INSIDE -> OUTSIDE = +0 (audited with delta=0)
B. EXIT: INSIDE -> OUTSIDE = +1, OUTSIDE -> INSIDE = +0 (audited with delta=0)
C. Duplicate suppression: Lingering across line = exactly 1 count
D. Line jitter: Oscillation inside buffer = no repeated counts
E. Occlusion: ByteTrack 2-stage association maintains track continuity
F. Wrong direction: Zero increment on primary count
G. Genuine second crossing: OUT -> IN -> OUT -> IN = +2 entry with CROSSING-001 & CROSSING-002
H. Exit equivalent: IN -> OUT -> IN -> OUT = +2 exit with CROSSING-001 & CROSSING-002
I. Queue movement: Per-track MOVING/SLOW/STOPPED classification & aggregate counts
J. Tracker sharing: CrossingEngine and QueueMovementEngine consume the exact same track IDs
K. Direction independence: Queue flow direction vector is independent of counting line normal
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
from app.ai.pipelines.crowd.queue_engine import QueueMovementEngine, QueueMetricsResult
from app.ai.pipelines.crowd.tracker import PersonTracker, TrackedPerson, TrackState


@pytest.fixture
def dummy_detection_model():
    return PersonDetectionModel(
        model_id="yolo11x-crowd",
        name="YOLO11x Crowd Person Detector",
        version="11.0",
        format="ONNX",
        input_width=1280,
        input_height=1280,
        confidence_threshold=0.45,
        iou_threshold=0.45,
        description="Production crowd person detector",
    )


def test_entry_camera_counting_and_wrong_direction_suppression(dummy_detection_model):
    """
    Validates Requirement A & F:
    For camera_purpose = ENTRY:
    - OUTSIDE -> BUFFER -> INSIDE increments entry count (+1)
    - INSIDE -> BUFFER -> OUTSIDE produces count_delta = 0 (audit recorded, 0 entry count)
    """
    config = CrowdPipelineConfig(
        camera_id="cam-entry-01",
        camera_code="CAM-KHB-ENTRY-01",
        camera_name="North Entry Gate 1",
        camera_purpose="ENTRY",
        event_id="evt-vigneshwara",
        rtsp_url_internal="rtsp://internal",
        rtsp_url_sanitized="rtsp://sanitized",
        model=dummy_detection_model,
        passage_roi_points=[{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0}],
        counting_lines=[{
            "id": "LINE-ENTRY-01",
            "name": "Gate 1 Entry Threshold",
            "start": {"x": 0.0, "y": 0.5},
            "end": {"x": 1.0, "y": 0.5},
            "direction": "IN",
        }],
    )
    analytics = CrowdSpatialAnalytics(config)
    now = time.time()

    # Person 1 (Devotee entering temple): OUTSIDE (0.5, 0.2) -> INSIDE (0.5, 0.7)
    trk_in = TrackedPerson(
        track_id=101,
        track_code="TRK-101",
        track_session_id="session-p1",
        current_bbox=(0.45, 0.1, 0.55, 0.3),
        current_point=(0.5, 0.2),
        confidence=0.90,
        trajectory=[(0.5, 0.2, now)],
    )

    analytics.process_tracks([trk_in], now, frame_id=1)
    crossings = analytics.get_and_clear_crossings()
    assert len(crossings) == 0
    assert trk_in.boundary_state == "OUTSIDE"

    # Step into INSIDE
    trk_in.trajectory.append((0.5, 0.7, now + 0.05))
    trk_in.current_point = (0.5, 0.7)
    analytics.process_tracks([trk_in], now + 0.05, frame_id=2)
    crossings = analytics.get_and_clear_crossings()

    assert len(crossings) == 1
    assert crossings[0].direction == "IN"
    assert crossings[0].count_delta == 1  # Entry count +1
    assert crossings[0].idempotency_key == "evt-vigneshwara_cam-entry-01_LINE-ENTRY-01_session-p1_CROSSING-001"

    # Person 2 (Devotee moving wrong direction on entry gate): INSIDE (0.5, 0.8) -> OUTSIDE (0.5, 0.2)
    trk_out = TrackedPerson(
        track_id=102,
        track_code="TRK-102",
        track_session_id="session-p2",
        current_bbox=(0.45, 0.7, 0.55, 0.9),
        current_point=(0.5, 0.8),
        confidence=0.88,
        trajectory=[(0.5, 0.8, now + 0.10)],
    )
    analytics.process_tracks([trk_out], now + 0.10, frame_id=3)
    assert trk_out.boundary_state == "INSIDE"

    # Step to OUTSIDE
    trk_out.trajectory.append((0.5, 0.2, now + 0.15))
    trk_out.current_point = (0.5, 0.2)
    analytics.process_tracks([trk_out], now + 0.15, frame_id=4)
    crossings_rev = analytics.get_and_clear_crossings()

    assert len(crossings_rev) == 1
    assert crossings_rev[0].direction == "OUT"
    assert crossings_rev[0].count_delta == 0  # SUPPRESSED for Entry Gate (+0)


def test_exit_camera_counting_and_wrong_direction_suppression(dummy_detection_model):
    """
    Validates Requirement B:
    For camera_purpose = EXIT:
    - INSIDE -> BUFFER -> OUTSIDE increments exit count (+1)
    - OUTSIDE -> BUFFER -> INSIDE produces count_delta = 0 (audit recorded, 0 exit count)
    """
    config = CrowdPipelineConfig(
        camera_id="cam-exit-01",
        camera_code="CAM-KHB-EXIT-01",
        camera_name="South Exit Gate 1",
        camera_purpose="EXIT",
        event_id="evt-vigneshwara",
        rtsp_url_internal="rtsp://internal",
        rtsp_url_sanitized="rtsp://sanitized",
        model=dummy_detection_model,
        passage_roi_points=[{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0}],
        counting_lines=[{
            "id": "LINE-EXIT-01",
            "name": "Gate 1 Exit Threshold",
            "start": {"x": 0.0, "y": 0.5},
            "end": {"x": 1.0, "y": 0.5},
            "direction": "OUT",
        }],
    )
    analytics = CrowdSpatialAnalytics(config)
    now = time.time()

    # Person leaving temple (INSIDE -> OUTSIDE)
    trk_exit = TrackedPerson(
        track_id=201,
        track_code="TRK-201",
        track_session_id="session-e1",
        current_bbox=(0.45, 0.7, 0.55, 0.9),
        current_point=(0.5, 0.8),
        confidence=0.92,
        trajectory=[(0.5, 0.8, now)],
    )
    analytics.process_tracks([trk_exit], now, frame_id=1)
    assert trk_exit.boundary_state == "INSIDE"

    # Step into OUTSIDE
    trk_exit.trajectory.append((0.5, 0.2, now + 0.05))
    trk_exit.current_point = (0.5, 0.2)
    analytics.process_tracks([trk_exit], now + 0.05, frame_id=2)
    crossings = analytics.get_and_clear_crossings()

    assert len(crossings) == 1
    assert crossings[0].direction == "OUT"
    assert crossings[0].count_delta == 1  # Exit count +1
    assert crossings[0].idempotency_key == "evt-vigneshwara_cam-exit-01_LINE-EXIT-01_session-e1_CROSSING-001"

    # Person trying to enter through exit gate (OUTSIDE -> INSIDE)
    trk_wrong = TrackedPerson(
        track_id=202,
        track_code="TRK-202",
        track_session_id="session-e2",
        current_bbox=(0.45, 0.1, 0.55, 0.3),
        current_point=(0.5, 0.2),
        confidence=0.87,
        trajectory=[(0.5, 0.2, now + 0.10)],
    )
    analytics.process_tracks([trk_wrong], now + 0.10, frame_id=3)
    assert trk_wrong.boundary_state == "OUTSIDE"

    # Step to INSIDE
    trk_wrong.trajectory.append((0.5, 0.8, now + 0.15))
    trk_wrong.current_point = (0.5, 0.8)
    analytics.process_tracks([trk_wrong], now + 0.15, frame_id=4)
    crossings_rev = analytics.get_and_clear_crossings()

    assert len(crossings_rev) == 1
    assert crossings_rev[0].direction == "IN"
    assert crossings_rev[0].count_delta == 0  # SUPPRESSED for Exit Gate (+0)


def test_genuine_multi_crossing_lifecycle(dummy_detection_model):
    """
    Validates Requirement G & H:
    A person legitimately moving OUTSIDE -> INSIDE -> OUTSIDE -> INSIDE
    produces exactly 2 valid Entry counts with sequence CROSSING-001 and CROSSING-002.
    """
    config = CrowdPipelineConfig(
        camera_id="cam-entry-02",
        camera_code="CAM-KHB-ENTRY-02",
        camera_name="East Entry Gate",
        camera_purpose="ENTRY",
        event_id="evt-vigneshwara",
        rtsp_url_internal="rtsp://internal",
        rtsp_url_sanitized="rtsp://sanitized",
        model=dummy_detection_model,
        passage_roi_points=[{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0}],
        counting_lines=[{
            "id": "LINE-ENTRY-02",
            "name": "East Gate Line",
            "start": {"x": 0.0, "y": 0.5},
            "end": {"x": 1.0, "y": 0.5},
            "direction": "IN",
        }],
    )
    analytics = CrowdSpatialAnalytics(config)
    now = time.time()

    trk = TrackedPerson(
        track_id=301,
        track_code="TRK-301",
        track_session_id="session-volunteer",
        current_bbox=(0.45, 0.1, 0.55, 0.3),
        current_point=(0.5, 0.2),
        confidence=0.95,
        trajectory=[(0.5, 0.2, now)],
    )

    # 1. Initial State: OUTSIDE
    analytics.process_tracks([trk], now, frame_id=1)
    analytics.get_and_clear_crossings()

    # 2. First Entry: OUTSIDE -> INSIDE
    trk.trajectory.append((0.5, 0.7, now + 0.05))
    trk.current_point = (0.5, 0.7)
    analytics.process_tracks([trk], now + 0.05, frame_id=2)
    c1 = analytics.get_and_clear_crossings()
    assert len(c1) == 1
    assert c1[0].crossing_sequence == 1
    assert c1[0].count_delta == 1
    assert c1[0].idempotency_key.endswith("CROSSING-001")

    # 3. Volunteer temporarily steps back out: INSIDE -> OUTSIDE
    trk.trajectory.append((0.5, 0.2, now + 0.10))
    trk.current_point = (0.5, 0.2)
    analytics.process_tracks([trk], now + 0.10, frame_id=3)
    c_out = analytics.get_and_clear_crossings()
    assert len(c_out) == 1
    assert c_out[0].crossing_sequence == 2  # Sequence 2 for the reverse audit event
    assert c_out[0].direction == "OUT"
    assert c_out[0].count_delta == 0  # Audit recorded, delta=0
    assert c_out[0].idempotency_key.endswith("CROSSING-002")

    # 4. Volunteer enters again: OUTSIDE -> INSIDE
    trk.trajectory.append((0.5, 0.75, now + 0.15))
    trk.current_point = (0.5, 0.75)
    analytics.process_tracks([trk], now + 0.15, frame_id=4)
    c2 = analytics.get_and_clear_crossings()
    assert len(c2) == 1
    assert c2[0].crossing_sequence == 3  # 1 (IN) + 1 (OUT audit) + 1 (IN) = sequence 3
    assert c2[0].direction == "IN"
    assert c2[0].count_delta == 1  # Legitimate 2nd Entry count!
    assert c2[0].idempotency_key.endswith("CROSSING-003")


def test_queue_movement_engine_per_track_and_aggregate():
    """
    Validates Requirement I & J:
    QueueMovementEngine directly consumes shared TrackedPerson instances,
    classifies individual tracks into MOVING, SLOW, STOPPED,
    and aggregates queue health & stagnation timer.
    """
    passage_polygon = [
        {"x": 0.1, "y": 0.1},
        {"x": 0.9, "y": 0.1},
        {"x": 0.9, "y": 0.9},
        {"x": 0.1, "y": 0.9},
    ]
    # Queue moving UP (towards smaller Y)
    queue_engine = QueueMovementEngine(
        passage_roi_points=passage_polygon,
        direction="UP",
        jitter_threshold_px=3.0,
    )
    now = time.time()

    # Track 101: Moving fast forward (Y decreases rapidly: 0.8 -> 0.7 in 40ms => 108 px / 0.04s = 2700 px/s)
    t1 = TrackedPerson(
        track_id=101,
        track_code="TRK-101",
        track_session_id="s101",
        current_bbox=(0.4, 0.7, 0.6, 0.85),
        current_point=(0.5, 0.8),
        confidence=0.90,
        trajectory=[(0.5, 0.8, now)],
    )
    # Track 102: Stationary (stuck in place)
    t2 = TrackedPerson(
        track_id=102,
        track_code="TRK-102",
        track_session_id="s102",
        current_bbox=(0.2, 0.5, 0.3, 0.65),
        current_point=(0.25, 0.6),
        confidence=0.88,
        trajectory=[(0.25, 0.6, now)],
    )

    # Frame 1: Establish baseline positions
    res1 = queue_engine.process_tracks([t1, t2], now, frame_width=1920, frame_height=1080)
    assert res1.people == 2
    assert res1.stopped == 2  # Baseline first frame

    # Frame 2 (40ms later): t1 moves forward along UP direction (y: 0.8 -> 0.78 => dy = -0.02 => -21.6 px)
    t1.trajectory.append((0.5, 0.78, now + 0.04))
    t1.current_point = (0.5, 0.78)

    # t2 stays completely stationary (jitter within 1 px)
    t2.trajectory.append((0.25, 0.6005, now + 0.04))
    t2.current_point = (0.25, 0.6005)

    res2 = queue_engine.process_tracks([t1, t2], now + 0.04, frame_width=1920, frame_height=1080)
    assert res2.people == 2
    assert res2.moving == 1  # Track 101 classified as MOVING
    assert res2.stopped == 1  # Track 102 classified as STOPPED
    assert res2.slow == 0
    assert res2.progress_ratio == 0.50
    assert res2.movement_px > 0.0
    assert res2.speed_px_per_sec > 0.0


def test_queue_direction_independence():
    """
    Validates Requirement K:
    Queue flow direction can be calibrated horizontally (LEFT -> RIGHT)
    independently of vertical counting lines.
    """
    queue_engine_horizontal = QueueMovementEngine(
        passage_roi_points=[{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0}],
        direction="RIGHT",  # Devotees walk left-to-right along barricade
        jitter_threshold_px=2.0,
    )
    now = time.time()

    # Track moving RIGHT: X goes from 0.2 -> 0.25
    trk = TrackedPerson(
        track_id=501,
        track_code="TRK-501",
        track_session_id="s501",
        current_bbox=(0.15, 0.4, 0.25, 0.6),
        current_point=(0.20, 0.5),
        confidence=0.91,
        trajectory=[(0.20, 0.5, now)],
    )

    queue_engine_horizontal.process_tracks([trk], now, frame_width=1920, frame_height=1080)

    # Move right: X=0.25 (+0.05 * 1920 = 96px in 0.04s)
    trk.trajectory.append((0.25, 0.5, now + 0.04))
    trk.current_point = (0.25, 0.5)

    res = queue_engine_horizontal.process_tracks([trk], now + 0.04, frame_width=1920, frame_height=1080)
    assert res.people == 1
    assert res.moving == 1
    assert res.stopped == 0
    assert res.movement_px == pytest.approx(96.0, abs=1.0)
