"""
tracker.py — Face tracking and identity persistence across frames.

Maintains track identity state across short detection drops or temporary blur spikes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

try:
    from app.frs_engine.config import MAX_MISSED_FRAMES
    from app.frs_engine.models.face_model import DetectedFace
    from app.frs_engine.recognition.matcher import MatchResult
    from app.frs_engine.recognition.quality import DecisionState, QualityMetrics
except ImportError:
    from app.config import MAX_MISSED_FRAMES
    from app.models.face_model import DetectedFace
    from app.recognition.matcher import MatchResult
    from app.recognition.quality import DecisionState, QualityMetrics


def _bbox_iou(a: np.ndarray, b: np.ndarray) -> float:
    a_arr = np.asarray(a, dtype=np.float32)
    b_arr = np.asarray(b, dtype=np.float32)

    ix1 = max(a_arr[0], b_arr[0])
    iy1 = max(a_arr[1], b_arr[1])
    ix2 = min(a_arr[2], b_arr[2])
    iy2 = min(a_arr[3], b_arr[3])

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih

    area_a = max(0.0, a_arr[2] - a_arr[0]) * max(0.0, a_arr[3] - a_arr[1])
    area_b = max(0.0, b_arr[2] - b_arr[0]) * max(0.0, b_arr[3] - b_arr[1])

    union = area_a + area_b - inter
    return float(inter / union) if union > 0.0 else 0.0


def _bbox_center_dist(a: np.ndarray, b: np.ndarray) -> float:
    ca = np.array([(a[0] + a[2]) * 0.5, (a[1] + a[3]) * 0.5])
    cb = np.array([(b[0] + b[2]) * 0.5, (b[1] + b[3]) * 0.5])
    return float(np.linalg.norm(ca - cb))


@dataclass
class TrackState:
    """
    State of an active face track.
    """
    track_id: int
    bbox: np.ndarray                    # [x1, y1, x2, y2]
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float32))
    first_seen_frame: int = 0
    last_seen_frame: int = 0
    updated_at: float = field(default_factory=time.monotonic)
    misses: int = 0
    
    # Candidate identity & match evidence
    candidate_id: Optional[Union[int, str]] = None
    candidate_name: str = "Unknown"
    candidate_similarity: float = 0.0
    decision_state: DecisionState = DecisionState.UNKNOWN
    
    # Recent history
    quality_history: List[QualityMetrics] = field(default_factory=list)
    match_history: List[MatchResult] = field(default_factory=list)
    embedding_history: List[np.ndarray] = field(default_factory=list)

    def predict_bbox(self, current_frame_id: int) -> np.ndarray:
        delta = max(0, current_frame_id - self.last_seen_frame)
        shift = self.velocity * float(delta)
        return self.bbox.astype(np.float32) + np.array([shift[0], shift[1], shift[0], shift[1]], dtype=np.float32)


class FaceTracker:
    """
    Lightweight IoU & motion tracker for face bounding boxes.
    Maintains persistent track IDs and temporal identity evidence.
    """

    def __init__(
        self,
        max_missed_frames: int = MAX_MISSED_FRAMES,
        min_iou: float = 0.1,
        max_center_distance: float = 180.0,
    ) -> None:
        self.max_missed_frames = max_missed_frames
        self.min_iou = min_iou
        self.max_center_distance = max_center_distance
        self._next_track_id = 1
        self._tracks: Dict[int, TrackState] = {}

    def clear(self) -> None:
        self._tracks.clear()
        self._next_track_id = 1

    @property
    def active_track_count(self) -> int:
        return len(self._tracks)

    def update(
        self,
        detections: List[DetectedFace],
        frame_id: int,
    ) -> List[TrackState]:
        """
        Update tracker with new detections in the current frame.
        """
        now = time.monotonic()
        track_ids = list(self._tracks.keys())
        predicted_bboxes = [
            self._tracks[tid].predict_bbox(frame_id) for tid in track_ids
        ]

        assigned_detections = set()
        assigned_tracks = set()

        # Step 1: Match tracks to detections via IoU and centroid distance
        matches: List[Tuple[int, int, float]] = []
        for t_idx, tid in enumerate(track_ids):
            pred_bbox = predicted_bboxes[t_idx]
            for d_idx, det in enumerate(detections):
                iou = _bbox_iou(pred_bbox, det.bbox)
                cdist = _bbox_center_dist(pred_bbox, det.bbox)
                if iou >= self.min_iou or cdist <= self.max_center_distance:
                    score = iou + max(0.0, 1.0 - (cdist / self.max_center_distance))
                    matches.append((t_idx, d_idx, score))

        matches.sort(key=lambda x: x[2], reverse=True)

        for t_idx, d_idx, _ in matches:
            if t_idx in assigned_tracks or d_idx in assigned_detections:
                continue

            assigned_tracks.add(t_idx)
            assigned_detections.add(d_idx)

            tid = track_ids[t_idx]
            track = self._tracks[tid]
            det = detections[d_idx]

            # Motion velocity update
            delta_frames = max(1, frame_id - track.last_seen_frame)
            old_center = np.array([(track.bbox[0] + track.bbox[2]) * 0.5, (track.bbox[1] + track.bbox[3]) * 0.5])
            new_center = np.array([(det.bbox[0] + det.bbox[2]) * 0.5, (det.bbox[1] + det.bbox[3]) * 0.5])
            instant_vel = (new_center - old_center) / float(delta_frames)
            track.velocity = track.velocity * 0.4 + instant_vel * 0.6

            # Update track state
            track.bbox = det.bbox.astype(np.float32)
            track.last_seen_frame = frame_id
            track.updated_at = now
            track.misses = 0

            if det.embedding is not None:
                track.embedding_history.append(det.embedding)
                if len(track.embedding_history) > 30:
                    track.embedding_history.pop(0)

        # Step 2: Create new tracks for unassigned detections
        for d_idx, det in enumerate(detections):
            if d_idx not in assigned_detections:
                tid = self._next_track_id
                self._next_track_id += 1
                new_track = TrackState(
                    track_id=tid,
                    bbox=det.bbox.astype(np.float32),
                    velocity=np.zeros(2, dtype=np.float32),
                    first_seen_frame=frame_id,
                    last_seen_frame=frame_id,
                    updated_at=now,
                    misses=0,
                    candidate_id=None,
                    candidate_name="Unknown",
                    candidate_similarity=0.0,
                    decision_state=DecisionState.UNKNOWN,
                )
                if det.embedding is not None:
                    new_track.embedding_history.append(det.embedding)
                self._tracks[tid] = new_track

        # Step 3: Increment misses for unassigned tracks and remove expired
        expired_ids = []
        for t_idx, tid in enumerate(track_ids):
            if t_idx not in assigned_tracks:
                track = self._tracks[tid]
                track.misses += max(1, frame_id - track.last_seen_frame)
                if track.misses > self.max_missed_frames:
                    expired_ids.append(tid)

        for tid in expired_ids:
            del self._tracks[tid]

        return list(self._tracks.values())
