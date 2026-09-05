"""
image_input.py — Static image input for R&D evaluation.

Used for offline testing:
    - Enrollment verification
    - Per-pose benchmark (0°, 15°, 30°, 45°, 60°, 75°, 90°)
    - Controlled experiments where we know the ground truth

Yields a single RGB frame from a file path.
"""

from __future__ import annotations

import cv2
import numpy as np
from typing import Optional


def load_image(path: str) -> Optional[np.ndarray]:
    """
    Load an image from disk and return it as an RGB numpy array.

    Returns:
        HxWx3 uint8 RGB array, or None if the file cannot be read.
    """
    bgr = cv2.imread(path)
    if bgr is None:
        print(f"[ImageInput] Cannot read: {path}")
        return None
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def load_image_bgr(path: str) -> Optional[np.ndarray]:
    """Load as BGR (for OpenCV display/save operations)."""
    img = cv2.imread(path)
    if img is None:
        print(f"[ImageInput] Cannot read: {path}")
    return img
