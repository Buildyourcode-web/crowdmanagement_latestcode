"""
analytics.py — Production-Grade Spatial Geometry & Boundary State Machine Analytics for Crowd AI.

Key Features:
- Normal Vector & Signed Distance State Machine:
  Tracks transition through OUTSIDE -> BUFFER_ZONE -> INSIDE.
- Ray-casting point-in-polygon for normalized geometries.
- Geometric segment intersection with anti-duplicate debounce and clearance depth.
- Emission of durable ValidatedCrossing payloads with unique idempotency keys.
"""

from collections import deque
import math
import time
from typing import Any, Deque, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.ai.pipelines.crowd.config import CrowdPipelineConfig
from app.ai.pipelines.crowd.tracker import TrackedPerson


class ValidatedCrossing(BaseModel):
    """Immutable crossing event payload to be persisted to PostgreSQL."""
    event_id: Optional[str] = None
    site_id: Optional[str] = None
    camera_id: str
    camera_code: str
    line_id: str
    line_name: Optional[str] = None
    track_session_id: str
    track_token: str
    crossing_sequence: int
    direction: str  # "IN" or "OUT"
    count_delta: int = 1
    detection_confidence: float
    ground_x: float
    ground_y: float
    signed_distance: float
    timestamp: float
    idempotency_key: str
    frame_id: int = 0


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


def get_line_unit_normal(l1: Tuple[float, float], l2: Tuple[float, float]) -> Tuple[float, float]:
    """
    Computes the perpendicular unit normal vector for line segment l1 -> l2.
    Points to the left of the line vector (the 'inside' convention).
    """
    dx = l2[0] - l1[0]
    dy = l2[1] - l1[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return (0.0, 1.0)
    return (-dy / length, dx / length)


def get_signed_distance_to_line(
    point: Tuple[float, float],
    l1: Tuple[float, float],
    l2: Tuple[float, float],
    normal: Optional[Tuple[float, float]] = None,
) -> float:
    """
    Calculates signed perpendicular distance from point to line l1 -> l2.
    """
    nx, ny = normal if normal is not None else get_line_unit_normal(l1, l2)
    vx = point[0] - l1[0]
    vy = point[1] - l1[1]
    return vx * nx + vy * ny


def check_segment_intersection(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    l1: Tuple[float, float],
    l2: Tuple[float, float],
) -> Optional[str]:
    """
    Tests if movement segment p1 -> p2 geometrically intersects line segment l1 -> l2.
    Returns 'IN' if moving towards the positive normal direction, 'OUT' if reversed,
    or None if segments do not intersect.
    """
    def ccw(A, B, C):
        return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

    if max(p1[0], p2[0]) < min(l1[0], l2[0]) or max(l1[0], l2[0]) < min(p1[0], p2[0]):
        return None
    if max(p1[1], p2[1]) < min(l1[1], l2[1]) or max(l1[1], l2[1]) < min(p1[1], p2[1]):
        return None

    intersects = (ccw(p1, l1, l2) != ccw(p2, l1, l2)) and (ccw(p1, p2, l1) != ccw(p1, p2, l2))
    if not intersects:
        return None

    normal = get_line_unit_normal(l1, l2)
    d1 = get_signed_distance_to_line(p1, l1, l2, normal)
    d2 = get_signed_distance_to_line(p2, l1, l2, normal)
    return "IN" if d2 >= d1 else "OUT"


class CrowdSpatialAnalytics:
    """
    Production Spatial Analytics engine with boundary state machine and hysteresis.
    """

    def __init__(self, config: CrowdPipelineConfig):
        self.config = config
        self.roi_points = config.crowd_roi_points
        self.exclusion_zones = config.exclusion_zones
        self.counting_lines = config.counting_lines

        # Precompute normalized ROI area
        self.roi_normalized_area = polygon_area_normalized(self.roi_points) if len(self.roi_points) >= 3 else 0.0

        # Precompute line normals
        self._line_normals: Dict[str, Tuple[float, float]] = {}
        for line in self.counting_lines:
            line_id = line.get("id", line.get("name", "line"))
            l1 = (float(line["start"]["x"]), float(line["start"]["y"]))
            l2 = (float(line["end"]["x"]), float(line["end"]["y"]))
            self._line_normals[line_id] = get_line_unit_normal(l1, l2)

        # Rolling window queues for line crossing rates
        self._inflow_events: Deque[float] = deque()
        self._outflow_events: Deque[float] = deque()
        self.window_seconds = config.counting_window_seconds

        # Newly validated crossings list
        self._new_crossings: List[ValidatedCrossing] = []

        # Spatial Hysteresis Parameters (Normalized space)
        self.buffer_epsilon = 0.015   # 1.5% buffer zone around line
        self.clearance_depth = 0.02   # 2% clearance depth into inside zone

    def get_and_clear_crossings(self) -> List[ValidatedCrossing]:
        """Returns and flushes newly validated crossing events."""
        crossings = list(self._new_crossings)
        self._new_crossings.clear()
        return crossings

    def process_tracks(
        self,
        tracks: List[TrackedPerson],
        timestamp: float,
        frame_id: int = 0,
    ) -> CrowdMetricsResult:
        """
        Processes active tracks against spatial geometries and boundary state machine.
        Returns calculated metrics. Newly validated crossings can be retrieved via get_and_clear_crossings().
        """
        has_valid_roi = len(self.roi_points) >= 3
        if not has_valid_roi and len(self.counting_lines) == 0:
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
            if has_valid_roi:
                in_roi = is_point_in_polygon(pt, self.roi_points)
                trk.inside_roi = in_roi
                if in_roi:
                    current_roi_count += 1
                    active_roi_ids.append(trk.track_id)
            else:
                trk.inside_roi = False

        # 2. Boundary State Machine & Line Crossing Analytics
        has_lines = len(self.counting_lines) > 0
        if has_lines:
            for trk in tracks:
                curr_pt = trk.current_point
                prev_pt = trk.previous_point

                for line in self.counting_lines:
                    line_id = line.get("id", line.get("name", "line"))
                    line_name = line.get("name")
                    l1 = (float(line["start"]["x"]), float(line["start"]["y"]))
                    l2 = (float(line["end"]["x"]), float(line["end"]["y"]))
                    allowed_direction = (line.get("direction") or "BOTH").upper()

                    normal = self._line_normals.get(line_id) or get_line_unit_normal(l1, l2)
                    dist_curr = get_signed_distance_to_line(curr_pt, l1, l2, normal)

                    # Update track state based on signed distance
                    if dist_curr < -self.buffer_epsilon:
                        trk.boundary_state = "OUTSIDE"
                        trk.confirmed_outside = True
                    elif dist_curr > self.buffer_epsilon:
                        trk.boundary_state = "INSIDE"
                        trk.confirmed_inside = True
                    else:
                        trk.boundary_state = "BUFFER_ZONE"

                    if not prev_pt or prev_pt == curr_pt:
                        continue

                    dist_prev = get_signed_distance_to_line(prev_pt, l1, l2, normal)

                    # Check for segment intersection and side transition
                    intersects = check_segment_intersection(prev_pt, curr_pt, l1, l2)

                    # IN Crossing Condition:
                    # Traversed from negative to positive side across the line
                    is_in_crossing = (
                        (dist_prev < -self.buffer_epsilon and dist_curr > self.buffer_epsilon) or
                        (dist_prev < 0.0 and dist_curr > 0.0 and intersects) or
                        (trk.confirmed_outside and intersects and dist_curr > self.clearance_depth)
                    )

                    # OUT Crossing Condition:
                    is_out_crossing = (
                        (dist_prev > self.buffer_epsilon and dist_curr < -self.buffer_epsilon) or
                        (dist_prev > 0.0 and dist_curr < 0.0 and intersects) or
                        (trk.confirmed_inside and intersects and dist_curr < -self.clearance_depth)
                    )

                    purpose = getattr(self.config, "camera_purpose", "ENTRY").upper()
                    crossing_dir: Optional[str] = None
                    count_delta: int = 1

                    if is_in_crossing:
                        crossing_dir = "IN"
                        if purpose == "EXIT":
                            count_delta = 0
                    elif is_out_crossing:
                        crossing_dir = "OUT"
                        if purpose == "ENTRY":
                            count_delta = 0

                    # Filter by line allowed_direction if configured
                    if crossing_dir:
                        if allowed_direction == "IN" and crossing_dir != "IN":
                            if purpose == "ENTRY":
                                count_delta = 0
                            else:
                                crossing_dir = None
                        elif allowed_direction == "OUT" and crossing_dir != "OUT":
                            if purpose == "EXIT":
                                count_delta = 0
                            else:
                                crossing_dir = None

                    if crossing_dir:
                        # Prevent duplicate counts while lingering near the line
                        crossing_key = f"{line_id}_{crossing_dir}"
                        opposite_key = f"{line_id}_{'OUT' if crossing_dir == 'IN' else 'IN'}"

                        if crossing_key not in trk.crossed_lines:
                            trk.crossed_lines.add(crossing_key)
                            trk.crossed_lines.discard(opposite_key)  # Reset opposite side to allow legitimate returns
                            trk.crossing_sequence += 1

                            if crossing_dir == "IN" and count_delta > 0:
                                self._inflow_events.append(timestamp)
                            elif crossing_dir == "OUT" and count_delta > 0:
                                self._outflow_events.append(timestamp)

                            evt_id_str = self.config.event_id or "event"
                            cam_id_str = self.config.camera_id
                            idempotency_key = (
                                f"{evt_id_str}_{cam_id_str}_{line_id}_{trk.track_session_id}_"
                                f"CROSSING-{trk.crossing_sequence:03d}"
                            )

                            crossing_record = ValidatedCrossing(
                                event_id=self.config.event_id,
                                site_id=self.config.site_id,
                                camera_id=self.config.camera_id,
                                camera_code=self.config.camera_code,
                                line_id=line_id,
                                line_name=line_name,
                                track_session_id=trk.track_session_id,
                                track_token=trk.track_code,
                                crossing_sequence=trk.crossing_sequence,
                                direction=crossing_dir,
                                count_delta=count_delta,
                                detection_confidence=round(trk.confidence, 4),
                                ground_x=round(curr_pt[0], 4),
                                ground_y=round(curr_pt[1], 4),
                                signed_distance=round(dist_curr, 4),
                                timestamp=timestamp,
                                idempotency_key=idempotency_key,
                                frame_id=frame_id,
                            )
                            self._new_crossings.append(crossing_record)

            # Prune events older than rolling window
            cutoff = timestamp - self.window_seconds
            while self._inflow_events and self._inflow_events[0] < cutoff:
                self._inflow_events.popleft()
            while self._outflow_events and self._outflow_events[0] < cutoff:
                self._outflow_events.popleft()

            factor = 60.0 / max(float(self.window_seconds), 1.0)
            inflow_rate = int(round(len(self._inflow_events) * factor))
            outflow_rate = int(round(len(self._outflow_events) * factor))
            flow_delta = inflow_rate - outflow_rate
        else:
            inflow_rate = None
            outflow_rate = None
            flow_delta = None

        # 3. Density Calculation
        if has_valid_roi:
            if self.config.physical_area_m2 and self.config.physical_area_m2 > 0:
                density_val = round(current_roi_count / self.config.physical_area_m2, 2)
                density_type = "CALIBRATED"
                density_unit = "persons/m²"
                if density_val < 2.0:
                    density_level = "LOW"
                elif density_val < 3.5:
                    density_level = "MODERATE"
                elif density_val < 5.0:
                    density_level = "HIGH"
                else:
                    density_level = "CRITICAL"
            else:
                norm_area = max(self.roi_normalized_area, 0.01)
                density_val = round(current_roi_count / norm_area, 1)
                density_type = "RELATIVE_DENSITY"
                density_unit = "RELATIVE_DENSITY"

                if current_roi_count <= self.config.density_low_max:
                    density_level = "LOW"
                elif current_roi_count <= self.config.density_moderate_max:
                    density_level = "MODERATE"
                elif current_roi_count <= self.config.density_high_max:
                    density_level = "HIGH"
                else:
                    density_level = "CRITICAL"
        else:
            density_val = 0.0
            density_type = "NOT_CONFIGURED"
            density_unit = "NOT_CONFIGURED"
            density_level = "LOW"

        return CrowdMetricsResult(
            camera_id=self.config.camera_id,
            camera_code=self.config.camera_code,
            profile_id=self.config.profile_id,
            timestamp=timestamp,
            is_roi_configured=has_valid_roi,
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
