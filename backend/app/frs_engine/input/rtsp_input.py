"""
rtsp_input.py — Low-latency RTSP reader for CCTV FRS.

Goals:
    - Dedicated capture thread.
    - Keep only the newest frame.
    - Drop stale frames to avoid video latency.
    - Use FFmpeg TCP transport.
    - Low-latency FFmpeg flags.
    - Automatic reconnect.
    - Resize decoded frames to the application display size.
    - Return RGB frames to the FRS pipeline.
"""

from __future__ import annotations

import os
import time
import threading
from queue import Queue, Empty

import cv2
import numpy as np

try:
    from app.frs_engine.config import RTSP_URL
except ImportError:
    try:
        from app.config import RTSP_URL
    except ImportError:
        RTSP_URL = ""

_rtsp_open_lock = threading.Lock()


class RTSPReader:
    """
    Threaded RTSP frame reader.

    The queue contains at most ONE frame.

    If FRS processing is slower than the CCTV camera, old frames are
    discarded instead of allowing latency to build up.
    """

    def __init__(
        self,
        url: str = "",
        resize: tuple[int, int] | None = (960, 540),
    ) -> None:

        self._url = url or RTSP_URL

        if not self._url:
            raise ValueError(
                "RTSP_URL is not set. "
                "Add RTSP_URL to .env."
            )

        self._resize = resize

        # Latest-frame-only queue.
        self._queue: Queue = Queue(maxsize=1)

        self._running = False

        self._thread: threading.Thread | None = None

        self._frame_counter = 0

        self._last_error_time = 0.0
        self._cap: cv2.VideoCapture | None = None
        self._cap_lock = threading.Lock()

    # ============================================================
    # START
    # ============================================================

    def start(self) -> None:

        if self._running:
            return

        self._running = True

        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name="RTSP-Capture",
        )

        self._thread.start()

        import re
        safe_url = re.sub(r"://(.*)@", "://***:***@", self._url) if "@" in self._url else self._url
        print(
            f"[RTSPReader] Started: {safe_url}"
        )

    # ============================================================
    # STOP
    # ============================================================

    def stop(self) -> None:

        self._running = False

        # First wait for the capture thread to exit cleanly on its own.
        # Calling cap.release() while cap.read() is executing in C++ FFmpeg
        # causes a fatal "double free or corruption (out)" crash!
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        with self._cap_lock:
            if self._cap is not None:
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None

        print(
            "[RTSPReader] Stopped."
        )

    # ============================================================
    # GET FRAME
    # ============================================================

    def get_frame(
        self,
        timeout: float = 0.01,
    ) -> np.ndarray | None:
        """
        Return the newest RGB frame.

        We intentionally use a very small timeout so the display/
        processing loop does not wait on an old frame.
        """

        try:

            return self._queue.get(
                timeout=timeout
            )

        except Empty:

            return None

    # ============================================================
    # CAPTURE LOOP
    # ============================================================

    def _capture_loop(self) -> None:

        cap: cv2.VideoCapture | None = None

        while self._running:

            # ----------------------------------------------------
            # Open / reopen RTSP
            # ----------------------------------------------------

            if (
                cap is None
                or not cap.isOpened()
            ):

                if cap is not None:
                    with self._cap_lock:
                        try:
                            cap.release()
                        except Exception:
                            pass
                        cap = None
                        self._cap = None

                cap = self._open_capture()

                if not cap.isOpened():
                    now = time.monotonic()
                    if (now - self._last_error_time > 5.0):
                        print("[RTSPReader] Could not open RTSP. Retrying in 5s...")
                        self._last_error_time = now
                    time.sleep(5.0)
                    continue

            # ----------------------------------------------------
            # Read frame
            # ----------------------------------------------------

            ret, frame = cap.read()

            if (
                not ret
                or frame is None
            ):

                now = time.monotonic()

                if (
                    now
                    - self._last_error_time
                    > 2.0
                ):

                    print(
                        "[RTSPReader] "
                        "Frame read failed. "
                        "Reconnecting..."
                    )

                    self._last_error_time = now

                with self._cap_lock:
                    if cap is not None:
                        try:
                            cap.release()
                        except Exception:
                            pass
                    cap = None
                    self._cap = None

                time.sleep(0.5)

                continue

            # ----------------------------------------------------
            # Resize
            # ----------------------------------------------------

            if self._resize:

                frame = cv2.resize(
                    frame,
                    self._resize,
                    interpolation=cv2.INTER_LINEAR,
                )

            # ----------------------------------------------------
            # BGR -> RGB
            # ----------------------------------------------------

            rgb = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB,
            )

            self._frame_counter += 1

            # ----------------------------------------------------
            # LATEST FRAME ONLY
            # ----------------------------------------------------

            #
            # Never allow old CCTV frames to accumulate.
            #
            # If the FRS is processing frame 100 while camera
            # already produced frame 110, we want frame 110,
            # NOT frame 101.
            #

            if self._queue.full():

                try:

                    self._queue.get_nowait()

                except Empty:

                    pass

            try:

                self._queue.put_nowait(
                    rgb
                )

            except Exception:

                pass

        # --------------------------------------------------------
        # Cleanup when stopping
        # --------------------------------------------------------

        with self._cap_lock:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
                cap = None
                self._cap = None

    # ============================================================
    # OPEN RTSP
    # ============================================================

    def _open_capture(
        self,
    ) -> cv2.VideoCapture:
        """
        Open RTSP using FFmpeg with bounded 5-second timeout and TCP/UDP fallback.
        Serialized across worker threads to avoid environment variable race condition.
        """
        import re
        safe_url = re.sub(r"://(.*)@", "://***:***@", self._url) if "@" in self._url else self._url

        global _rtsp_open_lock
        # 1. Try FFmpeg / TCP first with 5-second connection timeout & low-delay flags
        with _rtsp_open_lock:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                "rtsp_transport;tcp|"
                "stimeout;5000000|"
                "max_delay;500000|"
                "fflags;nobuffer|"
                "flags;low_delay"
            )
            print(f"[RTSPReader] Opening RTSP via FFmpeg/TCP (5s timeout): {safe_url}")
            cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)

        if cap.isOpened():
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            print(f"[RTSPReader] RTSP capture opened successfully via TCP.")
            with self._cap_lock:
                self._cap = cap
            return cap

        with self._cap_lock:
            try:
                cap.release()
            except Exception:
                pass

        # 2. Try FFmpeg / UDP fallback
        with _rtsp_open_lock:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                "rtsp_transport;udp|"
                "stimeout;5000000|"
                "max_delay;500000|"
                "fflags;nobuffer|"
                "flags;low_delay"
            )
            print(f"[RTSPReader] TCP failed, retrying via FFmpeg/UDP (5s timeout)...")
            cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)

        if cap.isOpened():
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            print(f"[RTSPReader] RTSP capture opened successfully via UDP.")
            with self._cap_lock:
                self._cap = cap
            return cap

        print(f"[RTSPReader] ERROR: Could not open RTSP stream (TCP and UDP timed out or rejected).")
        with self._cap_lock:
            self._cap = None
        return cap