"""
queue_engine.py — Production Queue Movement Engine.

Performs 5-level queue movement analytics directly on TrackedPerson instances
produced by the common ByteTrack tracker:
- Level 1 (Occupancy): Headcount inside passage polygon ROI & occupancy status
- Level 2 (Movement): Directional forward movement projection, per-track classification, & median movement
- Level 3 (Speed): EMA-smoothed velocity (px/sec)
- Level 4 (Health): Asymmetric stabilized queue health (MOVING / SLOW / STOPPED / EMPTY)
- Level 5 (Stagnation Alert): Continuous low-speed timer & alert urgency (OK / BLOCKED / CRITICAL)

CRITICAL:
Never instantiates an internal detector or tracker. Directly consumes the
shared TrackedPerson objects from PersonTracker.
"""

from collections import deque
from dataclasses import dataclass
import math
import statistics
import time
from typing import Any, Deque, Dict, List, Optional, Tuple

from app.ai.pipelines.crowd.analytics import is_point_in_polygon
from app.ai.pipelines.crowd.tracker import TrackedPerson


# Direction vector presets (Image coordinate system: X right, Y down)
DIRECTION_VECTORS: Dict[str, Optional[Tuple[float, float]]] = {
    "UP": (0.0, -1.0),
    "DOWN": (0.0, 1.0),
    "LEFT": (-1.0, 0.0),
    "RIGHT": (1.0, 0.0),
    "ANY": None,
}

# Thresholds & Windows
SPEED_MOVING_MIN: float = 7.0        # > 7.0 px/s -> MOVING
SPEED_SLOW_MIN: float = 3.0          # 3.0 - 7.0 px/s -> SLOW (< 3.0 -> STOPPED)
ALERT_SPEED_THRESHOLD: float = 2.0   # < 2.0 px/s triggers stagnation timer
DEFAULT_JITTER_THRESHOLD_PX: float = 5.0

STAGNATION_BLOCKED_SEC: float = 30.0
STAGNATION_CRITICAL_SEC: float = 120.0

HEALTH_STABILIZATION_SEC: float = 3.0  # Degradation hold
HEALTH_RECOVERY_SEC: float = 1.0       # Improvement quick-adopt

HEALTH_ORDER: Dict[str, int] = {
    "MOVING": 3,
    "SLOW": 2,
    "STOPPED": 1,
    "EMPTY": 0,
    "UNKNOWN": 0,
}


@dataclass
class QueueMetricsResult:
    people: int = 0
    moving: int = 0
    slow: int = 0
    stopped: int = 0
    movement_px: float = 0.0
    speed_px_per_sec: float = 0.0
    health: str = "EMPTY"
    stagnation_seconds: float = 0.0
    stagnation_label: str = "OK"
    progress_ratio: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "people": self.people,
            "moving": self.moving,
            "slow": self.slow,
            "stopped": self.stopped,
            "movement_px": round(self.movement_px, 2),
            "speed_px_per_sec": round(self.speed_px_per_sec, 2),
            "health": self.health,
            "stagnation_seconds": round(self.stagnation_seconds, 1),
            "stagnation_label": self.stagnation_label,
            "progress_ratio": round(self.progress_ratio, 2),
        }


class QueueMovementEngine:
    """
    Analyzes queue progression and devotee movement inside a barricaded corridor.
    Operates strictly as a consumer of common TrackedPerson instances.
    """

    def __init__(
        self,
        passage_roi_points: Optional[List[Dict[str, float]]] = None,
        direction: str = "UP",
        custom_direction_vector: Optional[Tuple[float, float]] = None,
        reference_dimension: int = 1080,
        jitter_threshold_px: float = DEFAULT_JITTER_THRESHOLD_PX,
        min_people_for_blockage: int = 2,
        speed_window_size: int = 6,
    ):
        self.passage_roi_points = passage_roi_points or []
        self.direction = direction.upper()
        self.reference_dimension = reference_dimension
        self.jitter_threshold_px = jitter_threshold_px
        self.min_people_for_blockage = min_people_for_blockage
        self.speed_window_size = speed_window_size

        # Resolve direction unit vector
        if custom_direction_vector is not None:
            vx, vy = custom_direction_vector
            mag = math.hypot(vx, vy)
            self._direction_vec: Optional[Tuple[float, float]] = (vx / mag, vy / mag) if mag > 1e-6 else None
        else:
            self._direction_vec = DIRECTION_VECTORS.get(self.direction, (0.0, -1.0))

        # Runtime Tracking State
        self._prev_positions: Dict[int, Tuple[float, float]] = {}
        self._prev_time: Optional[float] = None
        self._speed_window: Deque[float] = deque(maxlen=speed_window_size)
        self._per_track_states: Dict[int, str] = {}

        # Stabilized Health & Stagnation
        self._queue_health: str = "EMPTY"
        self._pending_health: str = "EMPTY"
        self._pending_since: float = time.monotonic()
        self._stagnation_start: Optional[float] = None
        self._stagnation_seconds: float = 0.0

    def _forward_progress(self, dx_px: float, dy_px: float) -> float:
        """Projects displacement onto queue direction vector with jitter threshold."""
        if self._direction_vec is None:
            raw = math.hypot(dx_px, dy_px)
        else:
            fx, fy = self._direction_vec
            raw = dx_px * fx + dy_px * fy
            raw = max(0.0, raw)

        return raw if raw >= self.jitter_threshold_px else 0.0

    def update_passage_roi(self, points: List[Dict[str, float]]) -> None:
        """Updates the corridor polygon boundary dynamically."""
        self.passage_roi_points = points or []

    def set_direction(
        self,
        direction: str,
        custom_vector: Optional[Tuple[float, float]] = None,
    ) -> None:
        """Updates queue flow direction vector."""
        self.direction = direction.upper()
        if custom_vector is not None:
            vx, vy = custom_vector
            mag = math.hypot(vx, vy)
            self._direction_vec = (vx / mag, vy / mag) if mag > 1e-6 else None
        else:
            self._direction_vec = DIRECTION_VECTORS.get(self.direction, None)

    def process_tracks(
        self,
        tracks: List[TrackedPerson],
        timestamp: float,
        frame_width: int = 1920,
        frame_height: int = 1080,
    ) -> QueueMetricsResult:
        """
        Analyzes devotee movement and queue flow from shared TrackedPerson instances.
        """
        now = timestamp if timestamp > 0 else time.monotonic()
        dt = (now - self._prev_time) if self._prev_time is not None else 0.04
        if dt <= 0.001:
            dt = 0.04
        self._prev_time = now

        # 1. Filter tracks inside the Passage ROI corridor
        has_roi = len(self.passage_roi_points) >= 3
        in_corridor: List[TrackedPerson] = []

        for trk in tracks:
            pt = trk.current_point
            if has_roi:
                if is_point_in_polygon(pt, self.passage_roi_points):
                    in_corridor.append(trk)
            else:
                in_corridor.append(trk)

        people_count = len(in_corridor)

        # 2. Per-track forward movement & classification
        curr_positions: Dict[int, Tuple[float, float]] = {}
        movements: List[float] = []
        moving_count = 0
        slow_count = 0
        stopped_count = 0

        for trk in in_corridor:
            tid = trk.track_id
            # Normalized to pixel coordinates
            curr_x_px = trk.current_point[0] * frame_width
            curr_y_px = trk.current_point[1] * frame_height
            curr_positions[tid] = (curr_x_px, curr_y_px)

            if tid in self._prev_positions:
                prev_x_px, prev_y_px = self._prev_positions[tid]
                dx_px = curr_x_px - prev_x_px
                dy_px = curr_y_px - prev_y_px

                forward_px = self._forward_progress(dx_px, dy_px)
                movements.append(forward_px)

                track_speed = forward_px / dt

                # Classify individual track
                if track_speed > SPEED_MOVING_MIN:
                    track_state = "MOVING"
                    moving_count += 1
                elif track_speed >= SPEED_SLOW_MIN:
                    track_state = "SLOW"
                    slow_count += 1
                else:
                    track_state = "STOPPED"
                    stopped_count += 1

                self._per_track_states[tid] = track_state
            else:
                # Newly established track in this frame
                stopped_count += 1
                self._per_track_states[tid] = "STOPPED"

        # Clean up stale track states
        active_tids = set(curr_positions.keys())
        self._prev_positions = curr_positions
        self._per_track_states = {
            tid: state for tid, state in self._per_track_states.items() if tid in active_tids
        }

        # 3. Median movement across tracks (robust to outliers / majority-vote)
        if movements:
            movement_px = statistics.median(movements)
            progress_ratio = moving_count / float(people_count) if people_count > 0 else 0.0
        else:
            movement_px = 0.0
            progress_ratio = 0.0

        # 4. Speed calculation with EMA smoothing
        if people_count > 0:
            raw_speed = movement_px / dt
            self._speed_window.append(raw_speed)
            speed_px_per_sec = sum(self._speed_window) / len(self._speed_window)

            # Raw health mapping
            if speed_px_per_sec > SPEED_MOVING_MIN:
                raw_health = "MOVING"
            elif speed_px_per_sec >= SPEED_SLOW_MIN:
                raw_health = "SLOW"
            else:
                raw_health = "STOPPED"

            # Asymmetric health stabilization
            if raw_health != self._pending_health:
                self._pending_health = raw_health
                self._pending_since = now

            curr_rank = HEALTH_ORDER.get(self._queue_health, 0)
            pending_rank = HEALTH_ORDER.get(self._pending_health, 0)

            required_hold = HEALTH_RECOVERY_SEC if pending_rank > curr_rank else HEALTH_STABILIZATION_SEC
            if (now - self._pending_since) >= required_hold:
                self._queue_health = self._pending_health

            # 5. Stagnation / Alert Engine
            if speed_px_per_sec < ALERT_SPEED_THRESHOLD and people_count >= self.min_people_for_blockage:
                if self._stagnation_start is None:
                    self._stagnation_start = now
                self._stagnation_seconds = now - self._stagnation_start
            else:
                self._stagnation_start = None
                self._stagnation_seconds = 0.0
        else:
            movement_px = 0.0
            self._speed_window.clear()
            speed_px_per_sec = 0.0
            progress_ratio = 0.0
            self._queue_health = "EMPTY"
            self._pending_health = "EMPTY"
            self._pending_since = now
            self._stagnation_start = None
            self._stagnation_seconds = 0.0

        # Stagnation label
        if self._stagnation_seconds >= STAGNATION_CRITICAL_SEC:
            stagnation_label = "CRITICAL"
        elif self._stagnation_seconds >= STAGNATION_BLOCKED_SEC:
            stagnation_label = "BLOCKED"
        else:
            stagnation_label = "OK"

        return QueueMetricsResult(
            people=people_count,
            moving=moving_count,
            slow=slow_count,
            stopped=stopped_count,
            movement_px=movement_px,
            speed_px_per_sec=speed_px_per_sec,
            health=self._queue_health,
            stagnation_seconds=self._stagnation_seconds,
            stagnation_label=stagnation_label,
            progress_ratio=progress_ratio,
        )

    def reset(self) -> None:
        """Resets engine runtime state."""
        self._prev_positions.clear()
        self._prev_time = None
        self._speed_window.clear()
        self._per_track_states.clear()
        self._queue_health = "EMPTY"
        self._pending_health = "EMPTY"
        self._stagnation_start = None
        self._stagnation_seconds = 0.0
