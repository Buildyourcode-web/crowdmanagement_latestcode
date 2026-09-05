"""
analytics.py — Queue AI Spatial Analytics Engine.

Calculates real-time queue headcount, occupancy percentage, relative & calibrated density,
queue length, directional inflow and outflow across Entry/Exit lines, queue movement direction,
dwell / waiting time aggregation, and queue growth rate.
"""

from collections import deque
import math
import statistics
import time
from typing import Any, Deque, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from app.ai.pipelines.crowd.analytics import is_point_in_polygon, polygon_area_normalized, check_segment_intersection
from app.ai.pipelines.crowd.tracker import TrackedPerson
from app.ai.pipelines.queue.config import QueuePipelineConfig


class QueueMetricsResult(BaseModel):
    """Calculated queue metrics for a single frame or time slice."""

    camera_id: str
    camera_code: str
    profile_id: str = "QUEUE_STANDARD"
    timestamp: float
    is_geometry_configured: bool = True
    missing_requirements: List[str] = Field(default_factory=list)
    queue_name: Optional[str] = None

    # Headcount
    queue_count: int = 0
    total_tracked_in_frame: int = 0
    excluded_count: int = 0

    # Occupancy
    occupancy_percentage: Optional[float] = None
    occupancy_status: str = "NORMAL"
    occupancy_note: Optional[str] = None

    # Density
    density: float = 0.0
    density_type: str = "RELATIVE"
    density_unit: str = "RELATIVE"
    density_level: str = "LOW"

    # Queue Length
    queue_length: Dict[str, Any] = Field(default_factory=dict)

    # Inflow / Outflow
    inflow: Optional[int] = None
    outflow: Optional[int] = None
    flow_delta: Optional[int] = None

    # Direction
    queue_direction: str = "UNKNOWN"

    # Dwell / Waiting Time
    average_wait_seconds: Optional[int] = None
    median_wait_seconds: Optional[int] = None
    max_current_dwell_seconds: Optional[int] = None
    completed_wait_samples: int = 0
    wait_status: str = "NORMAL"

    # Growth Rate
    growth_per_minute: Optional[int] = None

    # Active Track IDs in Queue
    active_queue_track_ids: List[int] = Field(default_factory=list)


class QueueSpatialAnalytics:
    """
    Spatial Analytics engine for Queue AI pipelines.
    Enforces real-world geometric constraints, duplicate prevention,
    and rigorous waiting time telemetry.
    """

    def __init__(self, config: QueuePipelineConfig):
        self.config = config
        self.queue_roi = config.queue_roi_points
        self.exclusion_zones = config.exclusion_zones
        self.entry_line = config.entry_line
        self.exit_line = config.exit_line
        self.direction_line = config.direction_line

        # Geometry checks
        self.has_roi = len(self.queue_roi) >= 3
        self.has_entry = "start" in self.entry_line and "end" in self.entry_line
        self.has_exit = "start" in self.exit_line and "end" in self.exit_line

        # Precompute normalized ROI area
        self.roi_area_normalized = polygon_area_normalized(self.queue_roi) if self.has_roi else 0.0

        # Line segments
        self.l_entry = None
        if self.has_entry:
            s, e = self.entry_line["start"], self.entry_line["end"]
            self.l_entry = ((float(s["x"]), float(s["y"])), (float(e["x"]), float(e["y"])))

        self.l_exit = None
        if self.has_exit:
            s, e = self.exit_line["start"], self.exit_line["end"]
            self.l_exit = ((float(s["x"]), float(s["y"])), (float(e["x"]), float(e["y"])))

        self.l_dir = None
        if self.direction_line and "start" in self.direction_line and "end" in self.direction_line:
            s, e = self.direction_line["start"], self.direction_line["end"]
            self.l_dir = ((float(s["x"]), float(s["y"])), (float(e["x"]), float(e["y"])))

        # Rolling queues for line crossings (timestamps)
        self._inflow_events: Deque[float] = deque()
        self._outflow_events: Deque[float] = deque()
        self.window_seconds = config.counting_window_seconds

        # Anti-repetition crossing cache: (track_id, ENTRY|EXIT) -> timestamp
        self._crossed_cache: Dict[Tuple[int, str], float] = {}

        # Dwell time tracking: track_id -> {entered_at: float, last_seen_at: float}
        self._dwell_tracker: Dict[int, Dict[str, float]] = {}
        self._completed_waits: Deque[float] = deque(maxlen=200)

        # Growth tracking: deque of (timestamp, count)
        self._count_history: Deque[Tuple[float, int]] = deque(maxlen=100)

    def process_tracks(self, tracks: List[TrackedPerson], timestamp: float) -> QueueMetricsResult:
        """Processes current active tracks through Queue AI analytics."""
        missing = []
        if not self.has_roi:
            missing.append("QUEUE_ROI missing")
        if not self.has_entry:
            missing.append("ENTRY_LINE missing")
        if not self.has_exit:
            missing.append("EXIT_LINE missing")

        if missing:
            return QueueMetricsResult(
                camera_id=self.config.camera_id,
                camera_code=self.config.camera_code,
                profile_id=self.config.profile_id,
                timestamp=timestamp,
                is_geometry_configured=False,
                missing_requirements=missing,
                queue_name=self.config.queue_roi_name,
                occupancy_note="QUEUE_CONFIGURATION_NOT_READY",
                wait_status="insufficient_data",
            )

        # 1. Spatial Filtering: Queue ROI & Exclusion Zones
        active_track_ids: List[int] = []
        active_points: List[Tuple[float, float]] = []
        excluded_count = 0

        for trk in tracks:
            pt = trk.current_point  # bottom-center (x_mid, y_max)
            if is_point_in_polygon(pt, self.queue_roi):
                # Check exclusion zones
                in_exclusion = any(is_point_in_polygon(pt, ez) for ez in self.exclusion_zones)
                if in_exclusion:
                    excluded_count += 1
                else:
                    active_track_ids.append(trk.track_id)
                    active_points.append(pt)

        queue_count = len(active_track_ids)

        # 2. Occupancy Calculation
        occupancy_pct = None
        occupancy_status = "NORMAL"
        occupancy_note = None

        if self.config.queue_capacity and self.config.queue_capacity > 0:
            occupancy_pct = round((queue_count / float(self.config.queue_capacity)) * 100.0, 1)
            if occupancy_pct >= self.config.occupancy_critical_pct:
                occupancy_status = "CRITICAL"
            elif occupancy_pct >= self.config.occupancy_warning_pct:
                occupancy_status = "WARNING"
            else:
                occupancy_status = "NORMAL"
        else:
            occupancy_note = "Queue capacity not configured."
            occupancy_status = "UNAVAILABLE"

        # 3. Density Estimation
        if self.config.physical_area_m2 and self.config.physical_area_m2 > 0:
            density_val = round(queue_count / self.config.physical_area_m2, 2)
            density_type = "CALIBRATED"
            density_unit = "persons/m²"
            if density_val < 2.0:
                density_lvl = "LOW"
            elif density_val < 3.5:
                density_lvl = "MODERATE"
            elif density_val < 5.0:
                density_lvl = "HIGH"
            else:
                density_lvl = "CRITICAL"
        else:
            norm_area = max(self.roi_area_normalized, 0.01)
            density_val = round(queue_count / norm_area, 1)
            density_type = "RELATIVE"
            density_unit = "RELATIVE"
            if queue_count <= 25:
                density_lvl = "LOW"
            elif queue_count <= 50:
                density_lvl = "MODERATE"
            elif queue_count <= 80:
                density_lvl = "HIGH"
            else:
                density_lvl = "CRITICAL"

        # 4. Queue Length Estimation
        if queue_count == 0:
            q_len = {
                "value": 0.0,
                "unit": "meters" if self.config.physical_length_meters else "normalized_extent",
                "source": "CALIBRATED" if self.config.physical_length_meters else "RELATIVE",
            }
        else:
            # Measure bounding span of people inside queue
            xs = [p[0] for p in active_points]
            ys = [p[1] for p in active_points]
            dx = max(xs) - min(xs)
            dy = max(ys) - min(ys)
            extent = round(math.sqrt(dx * dx + dy * dy), 2)
            if self.config.physical_length_meters and self.config.physical_length_meters > 0:
                calibrated_len = round(extent * self.config.physical_length_meters, 1)
                q_len = {"value": calibrated_len, "unit": "meters", "source": "CALIBRATED"}
            else:
                q_len = {"value": extent, "unit": "normalized_extent", "source": "RELATIVE"}

        # 5. Entry & Exit Line Crossing Analytics
        for trk in tracks:
            if len(trk.trajectory) < 2:
                continue
            prev_pt = trk.trajectory[-2][:2]
            curr_pt = trk.trajectory[-1][:2]

            # Entry line crossing
            if self.l_entry:
                cross_dir = check_segment_intersection(prev_pt, curr_pt, self.l_entry[0], self.l_entry[1])
                if cross_dir:
                    cache_key = (trk.track_id, "ENTRY")
                    last_crossed = self._crossed_cache.get(cache_key, 0.0)
                    if timestamp - last_crossed > 5.0:
                        self._crossed_cache[cache_key] = timestamp
                        self._inflow_events.append(timestamp)

            # Exit line crossing
            if self.l_exit:
                cross_dir = check_segment_intersection(prev_pt, curr_pt, self.l_exit[0], self.l_exit[1])
                if cross_dir:
                    cache_key = (trk.track_id, "EXIT")
                    last_crossed = self._crossed_cache.get(cache_key, 0.0)
                    if timestamp - last_crossed > 5.0:
                        self._crossed_cache[cache_key] = timestamp
                        self._outflow_events.append(timestamp)

                        # Record completed wait if track was in queue
                        if trk.track_id in self._dwell_tracker:
                            wait_dur = timestamp - self._dwell_tracker[trk.track_id]["entered_at"]
                            if wait_dur >= 1.0:
                                self._completed_waits.append(wait_dur)
                            del self._dwell_tracker[trk.track_id]

        # Prune crossing events outside window
        cutoff = timestamp - self.window_seconds
        while self._inflow_events and self._inflow_events[0] < cutoff:
            self._inflow_events.popleft()
        while self._outflow_events and self._outflow_events[0] < cutoff:
            self._outflow_events.popleft()

        factor = 60.0 / max(float(self.window_seconds), 1.0)
        inflow = int(round(len(self._inflow_events) * factor))
        outflow = int(round(len(self._outflow_events) * factor))
        flow_delta = inflow - outflow

        # 6. Dwell / Waiting Time Engine
        current_active_ids: Set[int] = set(active_track_ids)
        current_dwells: List[float] = []

        for tid in current_active_ids:
            if tid not in self._dwell_tracker:
                self._dwell_tracker[tid] = {"entered_at": timestamp, "last_seen_at": timestamp}
            else:
                self._dwell_tracker[tid]["last_seen_at"] = timestamp

            dwell_sec = timestamp - self._dwell_tracker[tid]["entered_at"]
            current_dwells.append(dwell_sec)

        # Detect tracks that left queue without crossing exit line (e.g. vanished/purged)
        stale_ids = [
            tid for tid, info in self._dwell_tracker.items()
            if tid not in current_active_ids and (timestamp - info["last_seen_at"]) > 3.0
        ]
        for tid in stale_ids:
            stale_wait = self._dwell_tracker[tid]["last_seen_at"] - self._dwell_tracker[tid]["entered_at"]
            if stale_wait >= 2.0:
                self._completed_waits.append(stale_wait)
            del self._dwell_tracker[tid]

        all_wait_samples = list(self._completed_waits) + current_dwells
        completed_samples_count = len(self._completed_waits)
        max_current_dwell = int(round(max(current_dwells))) if current_dwells else 0

        if not all_wait_samples:
            avg_wait = None
            med_wait = None
            wait_status = "insufficient_data"
        else:
            avg_wait = int(round(sum(all_wait_samples) / float(len(all_wait_samples))))
            med_wait = int(round(statistics.median(all_wait_samples)))
            if avg_wait >= self.config.wait_time_critical_seconds:
                wait_status = "CRITICAL"
            elif avg_wait >= self.config.wait_time_warning_seconds:
                wait_status = "HIGH"
            else:
                wait_status = "NORMAL"

        # 7. Queue Movement Direction
        # If DIRECTION_LINE exists, use it; otherwise use Entry -> Exit vector
        if self.l_dir:
            ref_vx = self.l_dir[1][0] - self.l_dir[0][0]
            ref_vy = self.l_dir[1][1] - self.l_dir[0][1]
        elif self.l_entry and self.l_exit:
            en_mid = ((self.l_entry[0][0] + self.l_entry[1][0]) / 2.0, (self.l_entry[0][1] + self.l_entry[1][1]) / 2.0)
            ex_mid = ((self.l_exit[0][0] + self.l_exit[1][0]) / 2.0, (self.l_exit[0][1] + self.l_exit[1][1]) / 2.0)
            ref_vx = ex_mid[0] - en_mid[0]
            ref_vy = ex_mid[1] - en_mid[1]
        else:
            ref_vx, ref_vy = 0.0, 0.0

        ref_mag = math.sqrt(ref_vx * ref_vx + ref_vy * ref_vy)
        queue_direction = "UNKNOWN"

        if ref_mag > 1e-4:
            ref_vx /= ref_mag
            ref_vy /= ref_mag

            dot_sum = 0.0
            motion_count = 0
            for trk in tracks:
                if trk.track_id in current_active_ids and len(trk.trajectory) >= 2:
                    p1 = trk.trajectory[-2][:2]
                    p2 = trk.trajectory[-1][:2]
                    mvx = p2[0] - p1[0]
                    mvy = p2[1] - p1[1]
                    mv_mag = math.sqrt(mvx * mvx + mvy * mvy)
                    if mv_mag > 0.002:
                        dot = (mvx * ref_vx) + (mvy * ref_vy)
                        dot_sum += dot
                        motion_count += 1

            if motion_count > 0:
                avg_dot = dot_sum / motion_count
                if avg_dot > 0.001:
                    queue_direction = "FORWARD"
                elif avg_dot < -0.001:
                    queue_direction = "BACKWARD"
                else:
                    queue_direction = "UNKNOWN"

        # 8. Queue Growth Rate
        self._count_history.append((timestamp, queue_count))
        growth_per_min = None
        if len(self._count_history) >= 2:
            oldest_t, oldest_c = self._count_history[0]
            elapsed = timestamp - oldest_t
            if elapsed >= 10.0:
                delta_c = queue_count - oldest_c
                growth_per_min = int(round(delta_c * (60.0 / elapsed)))

        return QueueMetricsResult(
            camera_id=self.config.camera_id,
            camera_code=self.config.camera_code,
            profile_id=self.config.profile_id,
            timestamp=timestamp,
            is_geometry_configured=True,
            missing_requirements=[],
            queue_name=self.config.queue_roi_name,
            queue_count=queue_count,
            total_tracked_in_frame=len(tracks),
            excluded_count=excluded_count,
            occupancy_percentage=occupancy_pct,
            occupancy_status=occupancy_status,
            occupancy_note=occupancy_note,
            density=density_val,
            density_type=density_type,
            density_unit=density_unit,
            density_level=density_lvl,
            queue_length=q_len,
            inflow=inflow,
            outflow=outflow,
            flow_delta=flow_delta,
            queue_direction=queue_direction,
            average_wait_seconds=avg_wait,
            median_wait_seconds=med_wait,
            max_current_dwell_seconds=max_current_dwell,
            completed_wait_samples=completed_samples_count,
            wait_status=wait_status,
            growth_per_minute=growth_per_min,
            active_queue_track_ids=active_track_ids,
        )
