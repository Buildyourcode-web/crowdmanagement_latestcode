"""
analytics.py — Spatial Geometry Analytics for Crowd AI.

Handles:
- Point-in-polygon Ray Casting algorithm for normalized coordinates.
- Reference point calculation: Bottom-center of bounding box ((x1+x2)/2, y2).
- Exclusion zone filtering.
- People count inside Crowd ROI.
- Relative density vs calibrated physical density (persons/m²).
- Entry/Exit line crossing detection with vector orientation and duplicate prevention.
- Rolling window inflow and outflow rate estimation.
"""

from collections import deque
import math
import time
from typing import Any, Deque, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.ai.pipelines.crowd.config import CrowdPipelineConfig
from app.ai.pipelines.crowd.tracker import TrackedPerson


class CrowdMetricsResult(BaseModel):
    """Calculated crowd metrics for a single frame or time slice."""
    camera_id: str
    camera_code: str
    profile_id: str
    timestamp: float
    is_roi_configured: bool = True
    crowd_roi_name: Optional[str] = None

    # People Counting
    current_count: int = 0
    total_tracked_in_frame: int = 0
    excluded_count: int = 0

    # Density
    density: float = 0.0
    density_type: str = "RELATIVE_DENSITY"  # RELATIVE_DENSITY or CALIBRATED
    density_unit: str = "RELATIVE_DENSITY"  # RELATIVE_DENSITY or persons/m²
    density_level: str = "LOW"  # LOW, MODERATE, HIGH, CRITICAL

    # Flow Analytics (None / unavailable if counting lines are not configured)
    inflow_rate: Optional[int] = None
    outflow_rate: Optional[int] = None
    flow_delta: Optional[int] = None
    counting_lines_active: bool = False

    # Track IDs currently active in ROI
    active_roi_track_ids: List[int] = Field(default_factory=list)


def is_point_in_polygon(point: Tuple[float, float], polygon_points: List[Dict[str, float]]) -> bool:
    """
    Ray-casting algorithm to test if (x, y) is inside a polygon.
    Polygon vertices are dictionaries with 'x' and 'y' floats in [0.0, 1.0].
    """
    if len(polygon_points) < 3:
        return False

    px, py = point
    inside = False
    n = len(polygon_points)

    p1 = polygon_points[0]
    p1x, p1y = float(p1["x"]), float(p1["y"])

    for i in range(1, n + 1):
        p2 = polygon_points[i % n]
        p2x, p2y = float(p2["x"]), float(p2["y"])

        if py > min(p1y, p2y):
            if py <= max(p1y, p2y):
                if px <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (py - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or px <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y

    return inside


def polygon_area_normalized(points: List[Dict[str, float]]) -> float:
    """Calculates polygon area in normalized coordinate space using Shoelace formula."""
    n = len(points)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        xi, yi = float(points[i]["x"]), float(points[i]["y"])
        xj, yj = float(points[j]["x"]), float(points[j]["y"])
        area += xi * yj
        area -= xj * yi
    return abs(area) / 2.0


def check_segment_intersection(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    l1: Tuple[float, float],
    l2: Tuple[float, float],
) -> Optional[str]:
    """
    Tests if trajectory segment p1 -> p2 crosses line segment l1 -> l2.
    Returns 'IN' or 'OUT' based on vector orientation (2D cross product),
    or None if no intersection.
    """
    def ccw(A, B, C):
        return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

    # Check bounding-box overlap first
    if max(p1[0], p2[0]) < min(l1[0], l2[0]) or max(l1[0], l2[0]) < min(p1[0], p2[0]):
        return None
    if max(p1[1], p2[1]) < min(l1[1], l2[1]) or max(l1[1], l2[1]) < min(p1[1], p2[1]):
        return None

    # Line intersection test
    intersect = (ccw(p1, l1, l2) != ccw(p2, l1, l2)) and (ccw(p1, p2, l1) != ccw(p1, p2, l2))
    if not intersect:
        return None

    # Determine crossing direction via 2D cross product:
    # vector line: l2 - l1
    # vector movement: p2 - p1
    vx_line = l2[0] - l1[0]
    vy_line = l2[1] - l1[1]
    vx_mov = p2[0] - p1[0]
    vy_mov = p2[1] - p1[1]

    cross_z = (vx_line * vy_mov) - (vy_line * vx_mov)
    if cross_z > 0:
        return "IN"
    elif cross_z < 0:
        return "OUT"
    return "IN"


class CrowdSpatialAnalytics:
    """
    Spatial Analytics engine that computes crowd metrics from tracked persons.
    """

    def __init__(self, config: CrowdPipelineConfig):
        self.config = config
        self.roi_points = config.crowd_roi_points
        self.exclusion_zones = config.exclusion_zones
        self.counting_lines = config.counting_lines

        # Precompute normalized ROI area
        self.roi_normalized_area = polygon_area_normalized(self.roi_points) if len(self.roi_points) >= 3 else 0.0

        # Rolling window queues for line crossing rates (tuples of timestamp, direction)
        self._inflow_events: Deque[float] = deque()
        self._outflow_events: Deque[float] = deque()
        self.window_seconds = config.counting_window_seconds

    def process_tracks(self, tracks: List[TrackedPerson], timestamp: float) -> CrowdMetricsResult:
        """Processes current active tracks against spatial geometries."""
        has_valid_roi = len(self.roi_points) >= 3
        if not has_valid_roi:
            return CrowdMetricsResult(
                camera_id=self.config.camera_id,
                camera_code=self.config.camera_code,
                profile_id=self.config.profile_id,
                timestamp=timestamp,
                is_roi_configured=False,
                current_count=0,
                total_tracked_in_frame=len(tracks),
                density=0.0,
                density_type="NOT_CONFIGURED",
                density_unit="NOT_CONFIGURED",
                density_level="LOW",
                inflow_rate=None,
                outflow_rate=None,
                counting_lines_active=False,
            )

        current_roi_count = 0
        excluded_count = 0
        active_roi_ids = []

        # 1. Point-in-Polygon & Exclusion Checks
        for trk in tracks:
            pt = trk.current_point

            # Check Exclusion Zones first
            in_exclusion = False
            for ex_poly in self.exclusion_zones:
                if is_point_in_polygon(pt, ex_poly):
                    in_exclusion = True
                    break

            trk.inside_exclusion = in_exclusion
            if in_exclusion:
                excluded_count += 1
                trk.inside_roi = False
                continue

            # Check Crowd ROI
            in_roi = is_point_in_polygon(pt, self.roi_points)
            trk.inside_roi = in_roi
            if in_roi:
                current_roi_count += 1
                active_roi_ids.append(trk.track_id)

        # 2. Line Crossing Analytics
        has_lines = len(self.counting_lines) > 0
        if has_lines:
            for trk in tracks:
                prev_pt = trk.previous_point
                curr_pt = trk.current_point
                if not prev_pt or prev_pt == curr_pt:
                    continue

                for line in self.counting_lines:
                    line_id = line.get("id", line.get("name", "line"))
                    line_start = (float(line["start"]["x"]), float(line["start"]["y"]))
                    line_end = (float(line["end"]["x"]), float(line["end"]["y"]))
                    allowed_direction = (line.get("direction") or "BOTH").upper()

                    crossing_dir = check_segment_intersection(prev_pt, curr_pt, line_start, line_end)
                    if crossing_dir:
                        # Prevent duplicate counts while lingering near the line
                        crossing_key = f"{line_id}_{crossing_dir}"
                        if crossing_key not in trk.crossed_lines:
                            trk.crossed_lines.add(crossing_key)

                            if allowed_direction in ("IN", "BOTH") and crossing_dir == "IN":
                                self._inflow_events.append(timestamp)
                            elif allowed_direction in ("OUT", "BOTH") and crossing_dir == "OUT":
                                self._outflow_events.append(timestamp)

            # Prune events older than rolling window
            cutoff = timestamp - self.window_seconds
            while self._inflow_events and self._inflow_events[0] < cutoff:
                self._inflow_events.popleft()
            while self._outflow_events and self._outflow_events[0] < cutoff:
                self._outflow_events.popleft()

            # Extrapolate to rate per minute
            factor = 60.0 / max(float(self.window_seconds), 1.0)
            inflow_rate = int(round(len(self._inflow_events) * factor))
            outflow_rate = int(round(len(self._outflow_events) * factor))
            flow_delta = inflow_rate - outflow_rate
        else:
            inflow_rate = None
            outflow_rate = None
            flow_delta = None

        # 3. Density Calculation
        if self.config.physical_area_m2 and self.config.physical_area_m2 > 0:
            density_val = round(current_roi_count / self.config.physical_area_m2, 2)
            density_type = "CALIBRATED"
            density_unit = "persons/m²"
            # Calibrated density levels (persons/m²)
            if density_val < 2.0:
                density_level = "LOW"
            elif density_val < 3.5:
                density_level = "MODERATE"
            elif density_val < 5.0:
                density_level = "HIGH"
            else:
                density_level = "CRITICAL"
        else:
            # Relative density based on normalized ROI area
            norm_area = max(self.roi_normalized_area, 0.01)
            density_val = round(current_roi_count / norm_area, 1)
            density_type = "RELATIVE_DENSITY"
            density_unit = "RELATIVE_DENSITY"

            # Categorize relative density against configured thresholds
            if current_roi_count <= self.config.density_low_max:
                density_level = "LOW"
            elif current_roi_count <= self.config.density_moderate_max:
                density_level = "MODERATE"
            elif current_roi_count <= self.config.density_high_max:
                density_level = "HIGH"
            else:
                density_level = "CRITICAL"

        return CrowdMetricsResult(
            camera_id=self.config.camera_id,
            camera_code=self.config.camera_code,
            profile_id=self.config.profile_id,
            timestamp=timestamp,
            is_roi_configured=True,
            crowd_roi_name=self.config.crowd_roi_name,
            current_count=current_roi_count,
            total_tracked_in_frame=len(tracks),
            excluded_count=excluded_count,
            density=density_val,
            density_type=density_type,
            density_unit=density_unit,
            density_level=density_level,
            inflow_rate=inflow_rate,
            outflow_rate=outflow_rate,
            flow_delta=flow_delta,
            counting_lines_active=has_lines,
            active_roi_track_ids=active_roi_ids,
        )
