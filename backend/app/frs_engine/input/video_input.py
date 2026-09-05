"""
video_input.py — Video file input for R&D evaluation.

Used for:
    - Testing against recorded CCTV clips (known pose sequences)
    - Offline R&D experiments without a live camera

Yields frames from a local video file one at a time.
"""

from __future__ import annotations

from typing import Generator

import cv2
import numpy as np

try:
    from app.frs_engine.config import FRAME_SKIP
except ImportError:
    from app.config import FRAME_SKIP


def iter_video_frames(
    path: str,
    skip: int = FRAME_SKIP,
    resize: tuple = (960, 540),
) -> Generator[tuple[int, np.ndarray], None, None]:
    """
    Yield (frame_index, rgb_frame) tuples from a video file.

    Args:
        path   : Path to video file.
        skip   : Process every Nth frame (1 = every frame).
        resize : Target (width, height). None = no resize.

    Yields:
        (frame_index, rgb_frame)  where rgb_frame is HxWx3 uint8.
    """
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print(f"[VideoInput] Cannot open: {path}")
        return

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % skip == 0:
            if resize:
                frame = cv2.resize(frame, resize)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            yield frame_idx, rgb

        frame_idx += 1

    cap.release()
