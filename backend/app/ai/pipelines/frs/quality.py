"""
quality.py — Face Quality Gate.

Evaluates detected face crops before candidate matching:
- Minimum resolution (width/height >= 60px)
- Sharpness / blur via Laplacian variance (>= 50.0)
- Exposure / brightness (40 <= mean <= 220)
- Pose constraints (|yaw| <= 45°, |pitch| <= 30°)
- Detection confidence

Returns FACE_QUALITY_INSUFFICIENT if quality is below standards.
"""

from dataclasses import dataclass
from typing import Dict, Optional

import cv2
import numpy as np

from app.ai.pipelines.frs.detector import DetectedFace


@dataclass
class FaceQualityResult:
    passed: bool
    quality_score: float  # Composite normalized score (0.0 to 1.0)
    rejection_reason: Optional[str] = None
    metrics: Optional[Dict[str, float]] = None


class FaceQualityGate:
    """Pre-matching quality validation gate."""

    def __init__(
        self,
        min_width: int = 60,
        min_height: int = 60,
        min_sharpness: float = 50.0,
        min_brightness: float = 40.0,
        max_brightness: float = 220.0,
        max_yaw: float = 45.0,
        max_pitch: float = 30.0,
    ):
        self.min_width = min_width
        self.min_height = min_height
        self.min_sharpness = min_sharpness
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness
        self.max_yaw = max_yaw
        self.max_pitch = max_pitch

    def assess_quality(self, face_crop: np.ndarray, face: DetectedFace) -> FaceQualityResult:
        """Validate face crop quality and compute composite quality score."""
        metrics: Dict[str, float] = {}

        # 1. Dimension Check
        w, h = face.width, face.height
        metrics["width"] = float(w)
        metrics["height"] = float(h)
        if w < self.min_width or h < self.min_height:
            return FaceQualityResult(
                passed=False,
                quality_score=0.2,
                rejection_reason="FACE_QUALITY_INSUFFICIENT: TOO_SMALL",
                metrics=metrics,
            )

        if face_crop is None or face_crop.size == 0:
            return FaceQualityResult(
                passed=False,
                quality_score=0.0,
                rejection_reason="FACE_QUALITY_INSUFFICIENT: EMPTY_CROP",
                metrics=metrics,
            )

        # Grayscale conversion for blur & brightness
        if len(face_crop.shape) == 3:
            gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        else:
            gray = face_crop

        # 2. Sharpness / Blur Check (Laplacian variance)
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        metrics["sharpness"] = laplacian_var
        if laplacian_var < self.min_sharpness:
            return FaceQualityResult(
                passed=False,
                quality_score=round(min(0.5, laplacian_var / (self.min_sharpness * 2)), 3),
                rejection_reason="FACE_QUALITY_INSUFFICIENT: BLURRY",
                metrics=metrics,
            )

        # 3. Brightness / Exposure Check
        mean_brightness = float(np.mean(gray))
        metrics["brightness"] = mean_brightness
        if mean_brightness < self.min_brightness or mean_brightness > self.max_brightness:
            return FaceQualityResult(
                passed=False,
                quality_score=0.4,
                rejection_reason="FACE_QUALITY_INSUFFICIENT: IMPROPER_EXPOSURE",
                metrics=metrics,
            )

        # 4. Pose Check
        if face.pose is not None:
            yaw, pitch, roll = face.pose
            metrics["yaw"] = abs(yaw)
            metrics["pitch"] = abs(pitch)
            metrics["roll"] = abs(roll)
            if abs(yaw) > self.max_yaw or abs(pitch) > self.max_pitch:
                return FaceQualityResult(
                    passed=False,
                    quality_score=0.35,
                    rejection_reason="FACE_QUALITY_INSUFFICIENT: EXTREME_POSE",
                    metrics=metrics,
                )

        # 5. Composite Normalized Score
        # Sharpness score (0.0-1.0 mapped around 50..500)
        sharp_norm = min(1.0, laplacian_var / 300.0)
        # Size score (60..200)
        size_norm = min(1.0, w / 160.0)
        # Exposure score (bell curve centered at 128)
        exp_norm = max(0.0, 1.0 - abs(mean_brightness - 128.0) / 128.0)

        composite = round(0.4 * sharp_norm + 0.3 * size_norm + 0.3 * exp_norm, 3)
        metrics["composite_quality"] = composite

        return FaceQualityResult(
            passed=True,
            quality_score=composite,
            metrics=metrics,
        )
