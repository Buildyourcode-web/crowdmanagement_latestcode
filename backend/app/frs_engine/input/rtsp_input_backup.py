"""
rtsp_input.py — Live RTSP camera input for R0.

The RTSP URL must come from .env — never hardcoded.

Architecture:
    - A dedicated capture thread reads frames continuously.
    - A shared queue (size=1) always contains the latest frame.
    - The pipeline thread reads from the queue.

This is the same two-thread pattern from the production FRS,
cleaned up and decoupled from all production-specific logic
(no alerts, no email, no GPS, no DB writes inside the loop).
"""

from __future__ import annotations

import time
import threading
from queue import Queue, Empty

import cv2
import numpy as np

from app.config import RTSP_URL


class RTSPReader:
    """
    Threaded RTSP frame reader.

    Usage:
        reader = RTSPReader(url="rtsp://...")
        reader.start()
        while True:
            frame = reader.get_frame()   # RGB HxWx3
            if frame is None:
                time.sleep(0.01)
                continue
            process(frame)
        reader.stop()
    """

    def __init__(
        self,
        url: str = "",
        resize: tuple = (960, 540),
    ) -> None:
        self._url = url or RTSP_URL
        if not self._url:
            raise ValueError(
                "RTSP_URL is not set. Add it to .env:\n  RTSP_URL=rtsp://..."
            )
        self._resize = resize
        self._queue: Queue = Queue(maxsize=1)
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        print(f"[RTSPReader] Started: {self._url}")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    def get_frame(self, timeout: float = 0.1) -> np.ndarray | None:
        """
        Return the latest RGB frame, or None if none is available.
        Non-blocking — caller decides what to do when no frame is ready.
        """
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    # ── Internal ───────────────────────────────────────────────────────────────

    def _capture_loop(self) -> None:
        cap = self._open_capture()

        while self._running:
            ret, frame = cap.read()
            if not ret:
                print("[RTSPReader] Lost connection. Reconnecting in 2 s...")
                cap.release()
                time.sleep(2)
                cap = self._open_capture()
                continue

            if self._resize:
                frame = cv2.resize(frame, self._resize)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Keep only the freshest frame — drop old one if queue is full
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                except Empty:
                    pass
            self._queue.put(rgb)

        cap.release()

    def _open_capture(self) -> cv2.VideoCapture:
        cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        return cap
