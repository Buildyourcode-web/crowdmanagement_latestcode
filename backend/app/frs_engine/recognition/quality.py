"""
quality.py — Face Quality Assessment & 5-State Decision Classifier.

Evaluates detected face crops for size, sharpness/blur, pose, and exposure.
Classifies operational state into:
  - NO_FACE
  - LOW_QUALITY
  - UNKNOWN
  - AMBIGUOUS
  - KNOWN
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

import cv2
import numpy as np

try:
    from app.frs_engine.config import (
        MIN_SHARPNESS_SCORE,
        MIN_FACE_WIDTH,
        MAX_POSE_YAW_DEG,
        AMBIGUITY_MARGIN,
    )
except ImportError:
    from app.config import (
        MIN_SHARPNESS_SCORE,
        MIN_FACE_WIDTH,
        MAX_POSE_YAW_DEG,
        AMBIGUITY_MARGIN,
    )


class FaceSizeCategory(str, Enum):
    LARGE = "LARGE"            # >= 120px
    MEDIUM = "MEDIUM"          # 60px - 119px
    SMALL = "SMALL"            # 30px - 59px
    VERY_SMALL = "VERY_SMALL"  # < 30px


class DecisionState(str, Enum):
    NO_FACE = "NO_FACE"
    LOW_QUALITY = "LOW_QUALITY"
    UNKNOWN = "UNKNOWN"
    AMBIGUOUS = "AMBIGUOUS"
    KNOWN = "KNOWN"


@dataclass
class QualityMetrics:
    face_width: int
    face_height: int
    size_category: FaceSizeCategory
    blur_score: float         # Laplacian variance (higher = sharper)
    is_blurry: bool
    brightness: float         # Mean grayscale intensity (0-255)
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    is_extreme_pose: bool = False
    is_usable: bool = True
    quality_score: float = 1.0  # Composite normalized score (0.0 - 1.0)


class FaceQualityAssessor:
    """
    Evaluates face crops and determines usability and decision states.
    """

    def __init__(
        self,
        min_sharpness: float = MIN_SHARPNESS_SCORE,
        min_width: int = MIN_FACE_WIDTH,
        max_yaw: float = MAX_POSE_YAW_DEG,
    ) -> None:
        self.min_sharpness = min_sharpness
        self.min_width = min_width
        self.max_yaw = max_yaw

    def compute_blur_score(self, face_crop_bgr: np.ndarray) -> float:
        """Compute sharpness using Laplacian variance."""
        if face_crop_bgr is None or face_crop_bgr.size == 0:
            return 0.0
        gray = cv2.cvtColor(face_crop_bgr, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    def compute_brightness(self, face_crop_bgr: np.ndarray) -> float:
        """Compute mean intensity (0-255)."""
        if face_crop_bgr is None or face_crop_bgr.size == 0:
            return 128.0
        gray = cv2.cvtColor(face_crop_bgr, cv2.COLOR_BGR2GRAY)
        return float(np.mean(gray))

    def categorize_size(self, width: int) -> FaceSizeCategory:
        if width >= 120:
            return FaceSizeCategory.LARGE
        elif width >= 60:
            return FaceSizeCategory.MEDIUM
        elif width >= 30:
            return FaceSizeCategory.SMALL
        else:
            return FaceSizeCategory.VERY_SMALL

    def assess_quality(
        self,
        frame_bgr: np.ndarray,
        bbox: np.ndarray,
        pose: Optional[np.ndarray] = None,
    ) -> QualityMetrics:
        """
        Extract crop from frame_bgr and compute QualityMetrics.
        """
        bbox_int = np.asarray(bbox, dtype=int)
        x1, y1, x2, y2 = bbox_int[0], bbox_int[1], bbox_int[2], bbox_int[3]

        h_img, w_img = frame_bgr.shape[:2]
        x1_c = max(0, min(x1, w_img - 1))
        y1_c = max(0, min(y1, h_img - 1))
        x2_c = max(0, min(x2, w_img - 1))
        y2_c = max(0, min(y2, h_img - 1))

        fw = max(0, x2_c - x1_c)
        fh = max(0, y2_c - y1_c)

        size_cat = self.categorize_size(fw)

        if fw <= 0 or fh <= 0:
            return QualityMetrics(
                face_width=0,
                face_height=0,
                size_category=FaceSizeCategory.VERY_SMALL,
                blur_score=0.0,
                is_blurry=True,
                brightness=0.0,
                is_usable=False,
                quality_score=0.0,
            )

        crop = frame_bgr[y1_c:y2_c, x1_c:x2_c]
        blur_score = self.compute_blur_score(crop)
        brightness = self.compute_brightness(crop)

        yaw, pitch, roll = 0.0, 0.0, 0.0
        if pose is not None and len(pose) >= 3:
            pitch, yaw, roll = float(pose[0]), float(pose[1]), float(pose[2])

        is_blurry = blur_score < self.min_sharpness
        is_too_small = fw < self.min_width or fh < self.min_width
        is_extreme_pose = abs(yaw) > self.max_yaw or abs(pitch) > 30.0

        # Extreme lighting check (underexposed < 25 or overexposed > 230)
        is_bad_exposure = brightness < 25.0 or brightness > 230.0

        is_usable = not (is_blurry or is_too_small or is_extreme_pose or is_bad_exposure)

        # Composite quality score (0.0 to 1.0)
        size_factor = min(1.0, fw / 100.0)
        sharp_factor = min(1.0, blur_score / max(1.0, self.min_sharpness * 2.0))
        pose_factor = max(0.0, 1.0 - (abs(yaw) / 90.0))
        quality_score = float(round(0.4 * size_factor + 0.4 * sharp_factor + 0.2 * pose_factor, 4))

        return QualityMetrics(
            face_width=fw,
            face_height=fh,
            size_category=size_cat,
            blur_score=round(blur_score, 2),
            is_blurry=is_blurry,
            brightness=round(brightness, 1),
            yaw=round(yaw, 1),
            pitch=round(pitch, 1),
            roll=round(roll, 1),
            is_extreme_pose=is_extreme_pose,
            is_usable=is_usable,
            quality_score=quality_score,
        )

    def classify_decision(
        self,
        match_similarity: float,
        is_known: bool,
        is_ambiguous: bool,
        quality: QualityMetrics,
    ) -> DecisionState:
        """
        Classify face state into one of 5 operational decision states.
        """
        if not quality.is_usable or quality.face_width == 0:
            return DecisionState.LOW_QUALITY

        if is_known:
            if is_ambiguous:
                return DecisionState.AMBIGUOUS
            return DecisionState.KNOWN

        if is_ambiguous:
            return DecisionState.AMBIGUOUS

        return DecisionState.UNKNOWN
