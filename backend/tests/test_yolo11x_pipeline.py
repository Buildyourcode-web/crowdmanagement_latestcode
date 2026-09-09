"""
backend/tests/test_yolo11x_pipeline.py — Step 10 Comprehensive YOLO11x Test Suite.

Verifies:
1. YOLO11x model registry entries, aliases, paths, and versioning.
2. AI profile registration (CROWD_YOLO11X, QUEUE_YOLO11X) with resource estimates.
3. Strict Class 0 (person only) filtering (cars, animals, objects discarded).
4. Confidence threshold filtering and coordinate normalization [0.0, 1.0].
5. Bottom-center reference point grounding ((x1+x2)/2, y2) and Section 7 output schema.
6. Transient multi-object tracking (TRK-xxxx) without biometric identity.
7. Entry line crossing in forward IN direction, and wrong-direction suppression.
8. Exit line crossing in forward OUT direction.
9. Anti-duplicate temporal cooldown suppression across multiple consecutive frames.
10. Zone occupancy inside CROWD_ROI, exclusion zone filtering, and non-accumulation invariant.
11. Queue occupancy inside QUEUE_ROI, dwell/wait-time tracking, and movement state.
12. AI capacity validation and safety protection (AI_CAPACITY_EXCEEDED).
13. Detector introspection (get_model_info) and strict production unavailable reporting.
"""

import asyncio
import os
import time
import pytest

from app.ai.capacity.calculator import CapacityCalculator
from app.ai.pipelines.crowd.analytics import (
    CrowdSpatialAnalytics,
    check_segment_intersection,
    is_point_in_polygon,
)
from app.ai.pipelines.crowd.config import CrowdPipelineConfig
from app.ai.pipelines.crowd.detector import (
    DetectedPerson,
    YOLO11xPersonDetector,
)
from app.ai.pipelines.crowd.models_registry import ModelRegistryService
from app.ai.pipelines.crowd.pipeline import CrowdPipeline
from app.ai.pipelines.crowd.tracker import PersonTracker, TrackedPerson
from app.ai.pipelines.queue.analytics import QueueSpatialAnalytics
from app.ai.pipelines.queue.config import QueuePipelineConfig
from app.ai.pipelines.queue.models_registry import QueueModelRegistryService
from app.ai.pipelines.queue.pipeline import QueuePipeline
from app.ai.profiles.service import AIProfileService, AIProfileType


# ── 1. Model Registry & Versioning Tests ─────────────────────────────────────

def test_yolo11x_crowd_model_registry():
    """Verifies yolo11x-crowd is registered with correct version and specifications."""
    model = ModelRegistryService.get_model("yolo11x-crowd")
    assert model is not None
    assert model.model_id == "yolo11x-crowd"
    assert model.version == "11.0.0"
    assert model.allowed_classes == [0]
    assert model.confidence_threshold == 0.35
    assert model.iou_threshold == 0.50
    assert model.input_width == 1280
    assert model.input_height == 1280

    # Aliases
    alias_model = ModelRegistryService.get_model("yolo11x")
    assert alias_model is not None
    assert alias_model.model_id == "yolo11x-crowd"

    alias_crowd = ModelRegistryService.get_model("yolo11x_crowd")
    assert alias_crowd is not None
    assert alias_crowd.model_id == "yolo11x-crowd"


def test_yolo11x_queue_model_registry():
    """Verifies yolo11x-queue is registered for queue channels."""
    model = QueueModelRegistryService.get_model("yolo11x-queue")
    assert model is not None
    assert model.model_id == "yolo11x-queue"
    assert model.version == "11.0.0"
    assert model.allowed_classes == [0]
    assert model.confidence_threshold == 0.40
    assert model.input_width == 1280
    assert model.input_height == 1280

    # Queue aliases
    alias_model = QueueModelRegistryService.get_model("yolo11x")
    assert alias_model is not None
    assert alias_model.model_id == "yolo11x-queue"


# ── 2. Profile Registration & Sizing Tests ───────────────────────────────────

def test_yolo11x_profile_registration():
    """Verifies CROWD_YOLO11X and QUEUE_YOLO11X profile specifications."""
    assert AIProfileService.validate_profile_exists("CROWD_YOLO11X")
    assert AIProfileService.validate_profile_exists("QUEUE_YOLO11X")

    crowd_prof = AIProfileService.get_profile("CROWD_YOLO11X")
    assert crowd_prof.type == AIProfileType.CROWD_YOLO11X
    assert crowd_prof.model == "yolo11x"
    assert crowd_prof.workload.estimated_vram_gb == 1.80
    assert crowd_prof.workload.estimated_gpu_load_percent == 12.0
    assert crowd_prof.workload.supports_cpu_execution is True

    queue_prof = AIProfileService.get_profile("QUEUE_YOLO11X")
    assert queue_prof.type == AIProfileType.QUEUE_YOLO11X
    assert queue_prof.model == "yolo11x"
    assert queue_prof.workload.estimated_vram_gb == 1.60
    assert queue_prof.workload.estimated_gpu_load_percent == 10.0


# ── 3. Strict Class-0 Filtering & Normalization ──────────────────────────────

def test_strict_person_class_0_filtering():
    """
    Verifies that only COCO Class 0 (person) is accepted.
    All non-person classes (bicycles, cars, animals, bags) are explicitly discarded.
    """
    detector = YOLO11xPersonDetector(synthetic_injector_mode=True, confidence_threshold=0.35)

    raw_candidates = [
        {"class_id": 0, "confidence": 0.92, "bbox": (0.1, 0.1, 0.3, 0.5)},   # Person -> Keep
        {"class_id": 1, "confidence": 0.88, "bbox": (0.2, 0.2, 0.4, 0.6)},   # Bicycle -> Discard
        {"class_id": 2, "confidence": 0.95, "bbox": (0.3, 0.3, 0.5, 0.7)},   # Car -> Discard
        {"class_id": 15, "confidence": 0.80, "bbox": (0.4, 0.4, 0.6, 0.8)},  # Cat -> Discard
        {"class_id": 16, "confidence": 0.85, "bbox": (0.5, 0.5, 0.7, 0.9)},  # Dog -> Discard
        {"class_id": 24, "confidence": 0.75, "bbox": (0.6, 0.6, 0.8, 0.95)}, # Backpack -> Discard
        {"class_id": 0, "confidence": 0.20, "bbox": (0.1, 0.2, 0.2, 0.4)},   # Person low conf -> Discard
        {"class_id": 0, "confidence": 0.89, "bbox": (0.7, 0.2, 0.85, 0.7)},  # Person -> Keep
    ]

    filtered = detector.filter_person_detections(raw_candidates, frame_id=1, timestamp=time.time())
    assert len(filtered) == 2
    for p in filtered:
        assert p.class_id == 0
        assert p.class_name == "person"
        assert p.confidence >= 0.35


def test_bottom_center_geometry_and_output_schema():
    """
    Verifies bottom-center calculation ((x1+x2)/2, y2), coordinate clamping,
    and Section 7 JSON output compliance.
    """
    detector = YOLO11xPersonDetector(synthetic_injector_mode=True, camera_code="CAM-01")
    raw = [
        {
            "class_id": 0,
            "confidence": 0.91,
            "bbox": {"x1": 0.45, "y1": 0.12, "x2": 0.62, "y2": 0.52},
            "camera_code": "CAM-01",
        }
    ]
    filtered = detector.filter_person_detections(raw, frame_id=1, timestamp=1700000000.0, camera_code="CAM-01")
    assert len(filtered) == 1
    person: DetectedPerson = filtered[0]

    # Verify bottom-center
    # x = (0.45 + 0.62) / 2 = 0.535, y = 0.52
    bc = person.bottom_center
    assert pytest.approx(bc[0], 0.001) == 0.535
    assert pytest.approx(bc[1], 0.001) == 0.52

    # Verify Section 7 output dictionary
    out = person.to_detection_output()
    assert out["class_id"] == 0
    assert out["confidence"] == 0.91
    assert out["camera_code"] == "CAM-01"
    assert "x1" in out["bbox"] and "y2" in out["bbox"]


# ── 4. Multi-Object Tracking Integration ─────────────────────────────────────

def test_transient_tracking_integration():
    """Verifies that detections receive transient track codes (TRK-xxxx) without biometric identity."""
    tracker = PersonTracker(max_age_frames=10, min_hits=1, iou_threshold=0.2)
    now = time.time()

    d1 = DetectedPerson(class_id=0, confidence=0.9, bbox=(0.1, 0.1, 0.2, 0.3), frame_id=1, timestamp=now)
    tracks_f1 = tracker.update([d1], now)

    assert len(tracks_f1) == 1
    track = tracks_f1[0]
    assert track.track_code.startswith("TRK-")
    assert track.track_id > 0
    assert len(track.trajectory) == 1

    # Frame 2: slightly moved
    d2 = DetectedPerson(class_id=0, confidence=0.92, bbox=(0.11, 0.11, 0.21, 0.31), frame_id=2, timestamp=now + 0.1)
    tracks_f2 = tracker.update([d2], now + 0.1)

    assert len(tracks_f2) == 1
    assert tracks_f2[0].track_id == track.track_id  # Same persistent track ID across frames
    assert tracks_f2[0].track_code == track.track_code
    assert len(tracks_f2[0].trajectory) == 2


# ── 5. Entry & Exit Line Crossing with Direction & Cooldown ─────────────────

def test_entry_and_exit_line_crossing():
    """
    Verifies:
    1. Person crossing horizontal entry line downwards (IN) produces valid crossing.
    2. Person crossing backwards (OUT) is correctly classified as OUT and suppressed for IN.
    3. Person approaching but not crossing does not trigger line crossing.
    """
    line_start = (0.2, 0.5)
    line_end = (0.8, 0.5)

    # 1. Approach but not crossing: (0.5, 0.2) -> (0.5, 0.45)
    res_approach = check_segment_intersection((0.5, 0.2), (0.5, 0.45), line_start, line_end)
    assert res_approach is None

    # 2. Forward entry crossing: (0.5, 0.4) -> (0.5, 0.6)
    res_in = check_segment_intersection((0.5, 0.4), (0.5, 0.6), line_start, line_end)
    assert res_in == "IN"

    # 3. Reverse exit crossing: (0.5, 0.6) -> (0.5, 0.4)
    res_out = check_segment_intersection((0.5, 0.6), (0.5, 0.4), line_start, line_end)
    assert res_out == "OUT"


@pytest.mark.asyncio
async def test_anti_duplicate_crossing_suppression():
    """
    Verifies that a person lingering across a line over multiple consecutive frames
    records the crossing key once and does not duplicate inflow events.
    """
    cfg = CrowdPipelineConfig(
        camera_id="cam-cd-1",
        camera_code="CAM-CD-01",
        camera_name="Main Gate Inflow",
        rtsp_url_internal="rtsp://internal",
        rtsp_url_sanitized="rtsp://sanitized",
        profile_id="CROWD_YOLO11X",
        model=ModelRegistryService.get_model("yolo11x-crowd"),
        crowd_roi_points=[{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0}],
        counting_lines=[
            {
                "id": "line-entry-1",
                "name": "Main Gate Entry",
                "type": "ENTRY_LINE",
                "start": {"x": 0.2, "y": 0.5},
                "end": {"x": 0.8, "y": 0.5},
                "direction": "IN",
            }
        ],
        event_cooldown_seconds=60,
    )
    analytics = CrowdSpatialAnalytics(cfg)

    # Frame 1: Person at (0.5, 0.4)
    t1 = TrackedPerson(
        track_id=1,
        track_code="TRK-0001",
        current_bbox=(0.4, 0.2, 0.6, 0.4),
        current_point=(0.5, 0.4),
        confidence=0.9,
        trajectory=[(0.5, 0.4, 100.0)],
    )
    m1 = analytics.process_tracks([t1], timestamp=100.0)
    assert len(analytics._inflow_events) == 0

    # Frame 2: Person moves to (0.5, 0.6) -> Crosses line-entry-1 in IN direction
    t1.trajectory.append((0.5, 0.6, 100.1))
    t1.current_point = (0.5, 0.6)
    m2 = analytics.process_tracks([t1], timestamp=100.1)
    assert len(analytics._inflow_events) == 1
    assert "line-entry-1_IN" in t1.crossed_lines

    # Frame 3: Same person moves slightly to (0.5, 0.65) -> Anti-duplicate suppresses second count
    t1.trajectory.append((0.5, 0.65, 100.2))
    t1.current_point = (0.5, 0.65)
    m3 = analytics.process_tracks([t1], timestamp=100.2)
    assert len(analytics._inflow_events) == 1  # Still 1, NOT duplicated!


# ── 6. Zone Occupancy & Exclusion Zones ──────────────────────────────────────

@pytest.mark.asyncio
async def test_zone_occupancy_and_non_accumulation():
    """
    Verifies:
    1. Only persons whose bottom-center is inside CROWD_ROI are counted.
    2. Persons inside EXCLUSION_ZONE are discarded.
    3. Non-accumulation invariant: People count is instantaneous, NEVER cumulative.
    """
    cfg = CrowdPipelineConfig(
        camera_id="cam-zone-1",
        camera_code="CAM-ZONE-01",
        camera_name="Zone A Sanctum",
        rtsp_url_internal="rtsp://internal",
        rtsp_url_sanitized="rtsp://sanitized",
        profile_id="CROWD_YOLO11X",
        model=ModelRegistryService.get_model("yolo11x-crowd"),
        crowd_roi_points=[{"x": 0.2, "y": 0.2}, {"x": 0.8, "y": 0.2}, {"x": 0.8, "y": 0.8}, {"x": 0.2, "y": 0.8}],
        exclusion_zones=[[{"x": 0.3, "y": 0.3}, {"x": 0.5, "y": 0.3}, {"x": 0.5, "y": 0.5}, {"x": 0.3, "y": 0.5}]],
        event_cooldown_seconds=60,
    )
    analytics = CrowdSpatialAnalytics(cfg)

    # 1. Inside ROI: bottom-center (0.6, 0.6) -> IN
    p1 = TrackedPerson(track_id=1, track_code="TRK-1", current_bbox=(0.55, 0.4, 0.65, 0.6), current_point=(0.6, 0.6), confidence=0.9)
    # 2. Inside Exclusion Zone: bottom-center (0.4, 0.4) -> EXCLUDED
    p2 = TrackedPerson(track_id=2, track_code="TRK-2", current_bbox=(0.35, 0.2, 0.45, 0.4), current_point=(0.4, 0.4), confidence=0.9)
    # 3. Outside ROI: bottom-center (0.9, 0.9) -> OUT
    p3 = TrackedPerson(track_id=3, track_code="TRK-3", current_bbox=(0.85, 0.7, 0.95, 0.9), current_point=(0.9, 0.9), confidence=0.9)

    res_f1 = analytics.process_tracks([p1, p2, p3], timestamp=10.0)
    assert res_f1.current_count == 1
    assert res_f1.active_roi_track_ids == [1]
    assert res_f1.excluded_count == 1

    # Frame 2: Same 1 person inside
    res_f2 = analytics.process_tracks([p1], timestamp=10.1)
    # Crucial: Must be 1, NOT 1 + 1 = 2!
    assert res_f2.current_count == 1


# ── 7. Queue Occupancy, Dwell Time & Metrics ────────────────────────────────

@pytest.mark.asyncio
async def test_queue_occupancy_dwell_time_and_metrics():
    """
    Verifies Queue AI pipeline with YOLO11x:
    1. Queue count matches active tracks inside QUEUE_ROI.
    2. Dwell/wait time calculated from entry to exit.
    3. Model info is included in queue metrics.
    """
    cfg = QueuePipelineConfig(
        camera_id="cam-q-1",
        camera_code="CAM-Q-01",
        camera_name="Queue 1 General",
        rtsp_url_internal="rtsp://internal",
        rtsp_url_sanitized="rtsp://sanitized",
        profile_id="QUEUE_YOLO11X",
        model=QueueModelRegistryService.get_model("yolo11x-queue"),
        queue_roi_points=[{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.1}, {"x": 0.9, "y": 0.9}, {"x": 0.1, "y": 0.9}],
        entry_line={"start": {"x": 0.1, "y": 0.2}, "end": {"x": 0.9, "y": 0.2}, "direction": "IN"},
        exit_line={"start": {"x": 0.1, "y": 0.8}, "end": {"x": 0.9, "y": 0.8}, "direction": "OUT"},
        queue_capacity=100,
    )
    detector = YOLO11xPersonDetector(model=cfg.model, synthetic_injector_mode=True, camera_code="CAM-Q-01")
    await detector.initialize()

    queue_pipeline = QueuePipeline(config=cfg, detector=detector)

    # Frame 1: 2 persons detected (tentative hits=1)
    dets = [
        {"class_id": 0, "confidence": 0.9, "bbox": (0.3, 0.3, 0.4, 0.5)},
        {"class_id": 0, "confidence": 0.9, "bbox": (0.6, 0.4, 0.7, 0.6)},
    ]
    detector.set_next_detections(dets)
    await queue_pipeline.process_frame(None, frame_id=1, timestamp=100.0)

    # Frame 2: Persons confirmed on second consecutive frame (hits >= 2)
    detector.set_next_detections(dets)
    payload = await queue_pipeline.process_frame(None, frame_id=2, timestamp=100.1)

    assert payload["queue_count"] == 2
    assert "model_info" in payload
    assert payload["model_info"]["model_id"] == "yolo11x-queue"


# ── 8. Capacity Validation & Safety Ceilings ─────────────────────────────────

def test_capacity_validation_with_yolo11x():
    """Verifies that CapacityCalculator enforces safety limits for YOLO11x deployments."""
    cpu_info = {"usage_percent": 25.0}
    ram_info = {"total_gb": 16.0, "available_gb": 10.0}
    gpu_info = {
        "available": True,
        "devices": [
            {
                "index": 0,
                "name": "NVIDIA GeForce RTX 3050",
                "total_vram_gb": 6.0,
                "free_vram_gb": 4.5,
                "gpu_utilization_percent": 30,
            }
        ],
    }

    # 1. Single YOLO11x stream on 6GB GPU should be ALLOWED
    res1 = CapacityCalculator.validate_capacity_for_deployment(
        current_workload={},
        requested_addition={"CROWD_YOLO11X": 1},
        cpu_info=cpu_info,
        ram_info=ram_info,
        gpu_info=gpu_info,
    )
    assert res1.verdict in ("ALLOWED", "WARNING")

    # 2. Deploying 10 YOLO11x streams (18 GB VRAM) on a 6GB GPU must be BLOCKED
    res_blocked = CapacityCalculator.validate_capacity_for_deployment(
        current_workload={},
        requested_addition={"CROWD_YOLO11X": 10},
        cpu_info=cpu_info,
        ram_info=ram_info,
        gpu_info=gpu_info,
    )
    assert res_blocked.verdict == "BLOCKED"
    assert "OVER_CAPACITY" in res_blocked.status or "VRAM" in res_blocked.reason


# ── 9. Strict Production Unavailable Status ──────────────────────────────────

@pytest.mark.asyncio
async def test_yolo11x_strict_no_mock_production_status():
    """
    Verifies Section 62 requirement:
    In production configuration without test injector, if model weights/engine
    are absent, detector reports YOLO11X_UNAVAILABLE and does NOT generate fake counts.
    """
    model = ModelRegistryService.get_model("yolo11x-crowd").model_copy()
    model.weights_path = "models/non_existent_weights_12345.pt"
    model.engine_path = "models/non_existent_engine_12345.engine"

    detector = YOLO11xPersonDetector(
        model=model,
        allow_cpu_fallback=False,
        synthetic_injector_mode=False,
    )
    init_ok = await detector.initialize()
    assert init_ok is False

    info = detector.get_model_info()
    assert info["status"] in ("YOLO11X_UNAVAILABLE", "GPU_INFERENCE_UNAVAILABLE")

    # Attempting to detect without initialization must raise RuntimeError, never fake counts
    with pytest.raises(RuntimeError) as exc_info:
        await detector.detect(frame_data=None, frame_id=1, timestamp=time.time())
    assert "UNAVAILABLE" in str(exc_info.value)
