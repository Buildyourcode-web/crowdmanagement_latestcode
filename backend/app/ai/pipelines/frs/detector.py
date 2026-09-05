"""
detector.py — Face Detection & 5-Point Landmark Extraction Engine.

Wraps SCRFD / Buffalo_L face detection.
Supports dependency injection for offline/unit test execution.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional, Tuple

import numpy as np
from loguru import logger


@dataclass
class DetectedFace:
    """Represents a validated face detection bounding box and landmarks."""
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    confidence: float
    landmarks: Optional[np.ndarray] = None  # (5, 2) coords
    pose: Optional[Tuple[float, float, float]] = None  # (yaw, pitch, roll) in degrees
    timestamp: datetime = None
    frame_ref: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)

    @property
    def width(self) -> int:
        return max(0, self.bbox[2] - self.bbox[0])

    @property
    def height(self) -> int:
        return max(0, self.bbox[3] - self.bbox[1])


class FaceDetector:
    """Face detector interface supporting both real InsightFace and custom injection."""

    def __init__(
        self,
        confidence_threshold: float = 0.60,
        custom_detector: Optional[Callable[[np.ndarray], List[DetectedFace]]] = None,
    ):
        self.confidence_threshold = confidence_threshold
        self._custom_detector = custom_detector
        self._app = None

        if self._custom_detector is None:
            self._init_insightface()

    def _init_insightface(self):
        try:
            from insightface.app import FaceAnalysis
            app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
            app.prepare(ctx_id=-1, det_size=(640, 640))
            self._app = app
            logger.info("FaceDetector: InsightFace buffalo_l loaded successfully.")
        except Exception as e:
            logger.warning(f"FaceDetector: InsightFace unavailable ({e}). Fallback detector active.")
            self._app = None

    def detect(self, frame: np.ndarray) -> List[DetectedFace]:
        """Detect faces in RGB/BGR image frame."""
        if frame is None or frame.size == 0:
            return []

        if self._custom_detector is not None:
            raw_faces = self._custom_detector(frame)
            return [f for f in raw_faces if f.confidence >= self.confidence_threshold]

        if self._app is None:
            return []

        try:
            # InsightFace expects BGR or RGB
            faces = self._app.get(frame)
            results: List[DetectedFace] = []
            for f in faces:
                score = float(getattr(f, "det_score", 0.0))
                if score < self.confidence_threshold:
                    continue

                bbox = tuple(int(v) for v in f.bbox[:4])
                kps = getattr(f, "kps", None)
                pose = getattr(f, "pose", None)
                pose_tuple = tuple(float(p) for p in pose) if pose is not None else None

                results.append(
                    DetectedFace(
                        bbox=bbox,
                        confidence=score,
                        landmarks=kps,
                        pose=pose_tuple,
                    )
                )
            return results
        except Exception as e:
            logger.error(f"FaceDetector: detection failure: {e}")
            return []
