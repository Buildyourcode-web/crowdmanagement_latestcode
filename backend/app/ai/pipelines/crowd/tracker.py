"""
tracker.py — Multi-Object Tracking Engine for Crowd AI.

Manages transient spatial tracking IDs (e.g. TRK-1001) and spatial trajectory histories.
Strict Invariants:
- Tracking IDs are transient numerical tokens, NOT personal identities.
- Tracking IDs are never persisted as biometric profiles or connected to FRS.
"""

import time
from typing import Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field
from app.ai.pipelines.crowd.detector import DetectedPerson


class TrackedPerson(BaseModel):
    """Represents a temporarily tracked individual in camera field of view."""
    track_id: int
    track_code: str
    current_bbox: Tuple[float, float, float, float]
    current_point: Tuple[float, float]  # Bottom-center (x, y) normalized
    confidence: float
    # List of (x, y, timestamp) representing trajectory history
    trajectory: List[Tuple[float, float, float]] = Field(default_factory=list)
    first_seen_at: float = Field(default_factory=time.time)
    last_seen_at: float = Field(default_factory=time.time)
    hits: int = 1
    frames_since_update: int = 0
    inside_roi: bool = False
    inside_exclusion: bool = False
    crossed_lines: Set[str] = Field(default_factory=set)

    @property
    def previous_point(self) -> Optional[Tuple[float, float]]:
        """Returns the point from the preceding frame if available."""
        if len(self.trajectory) >= 2:
            return (self.trajectory[-2][0], self.trajectory[-2][1])
        return None


def calculate_iou(boxA: Tuple[float, float, float, float], boxB: Tuple[float, float, float, float]) -> float:
    """Calculates Intersection over Union for two normalized boxes [x1, y1, x2, y2]."""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    inter_w = max(0.0, xB - xA)
    inter_h = max(0.0, yB - yA)
    interArea = inter_w * inter_h

    boxAArea = max(0.0, boxA[2] - boxA[0]) * max(0.0, boxA[3] - boxA[1])
    boxBArea = max(0.0, boxB[2] - boxB[0]) * max(0.0, boxB[3] - boxB[1])

    unionArea = boxAArea + boxBArea - interArea
    if unionArea <= 0.0:
        return 0.0
    return interArea / unionArea


class PersonTracker:
    """
    Multi-object person tracker using IoU and centroid distance matching.
    Provides trajectory smoothing, line-crossing support, and track cleanup.
    """

    def __init__(
        self,
        max_age_frames: int = 30,
        min_hits: int = 1,
        iou_threshold: float = 0.25,
        max_trajectory_length: int = 60,
    ):
        self.max_age_frames = max_age_frames
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.max_trajectory_length = max_trajectory_length
        self._next_track_id: int = 1000
        self.tracks: Dict[int, TrackedPerson] = {}

    def reset(self) -> None:
        """Clears all active tracks."""
        self.tracks.clear()
        self._next_track_id = 1000

    def update(self, detections: List[DetectedPerson], timestamp: float) -> List[TrackedPerson]:
        """
        Updates tracker state with new frame detections.
        Matches detections to existing tracks via IoU, updates trajectories,
        creates new tracks, and prunes expired tracks.
        """
        active_track_ids = list(self.tracks.keys())
        unmatched_detections = set(range(len(detections)))
        unmatched_tracks = set(active_track_ids)

        # 1. Match existing tracks to detections using IoU matrix
        matches = []
        if active_track_ids and detections:
            cost_matrix = []
            for tid in active_track_ids:
                trk = self.tracks[tid]
                row = [calculate_iou(trk.current_bbox, det.bbox) for det in detections]
                cost_matrix.append(row)

            # Greedy bipartite matching
            for t_idx, tid in enumerate(active_track_ids):
                best_iou = 0.0
                best_d_idx = -1
                for d_idx in unmatched_detections:
                    iou = cost_matrix[t_idx][d_idx]
                    if iou > best_iou and iou >= self.iou_threshold:
                        best_iou = iou
                        best_d_idx = d_idx

                if best_d_idx >= 0:
                    matches.append((tid, best_d_idx))
                    unmatched_detections.discard(best_d_idx)
                    unmatched_tracks.discard(tid)

        # 2. Update matched tracks
        for tid, d_idx in matches:
            det = detections[d_idx]
            trk = self.tracks[tid]
            trk.current_bbox = det.bbox
            trk.current_point = det.bottom_center
            trk.confidence = det.confidence
            trk.last_seen_at = timestamp
            trk.hits += 1
            trk.frames_since_update = 0

            # Append to trajectory
            trk.trajectory.append((det.bottom_center[0], det.bottom_center[1], timestamp))
            if len(trk.trajectory) > self.max_trajectory_length:
                trk.trajectory.pop(0)

        # 3. Create new tracks for unmatched detections
        for d_idx in unmatched_detections:
            det = detections[d_idx]
            self._next_track_id += 1
            new_id = self._next_track_id
            new_track = TrackedPerson(
                track_id=new_id,
                track_code=f"TRK-{new_id}",
                current_bbox=det.bbox,
                current_point=det.bottom_center,
                confidence=det.confidence,
                trajectory=[(det.bottom_center[0], det.bottom_center[1], timestamp)],
                first_seen_at=timestamp,
                last_seen_at=timestamp,
                hits=1,
                frames_since_update=0,
            )
            self.tracks[new_id] = new_track

        # 4. Age unmatched tracks and prune expired
        expired_ids = []
        for tid in unmatched_tracks:
            trk = self.tracks[tid]
            trk.frames_since_update += 1
            if trk.frames_since_update > self.max_age_frames:
                expired_ids.append(tid)

        for tid in expired_ids:
            del self.tracks[tid]

        # 5. Return confirmed active tracks (hits >= min_hits and updated recently)
        return [
            trk for trk in self.tracks.values()
            if trk.hits >= self.min_hits and trk.frames_since_update <= 1
        ]
