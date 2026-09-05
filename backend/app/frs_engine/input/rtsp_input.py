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

        print(
            f"[RTSPReader] Started: {self._url}"
        )

    # ============================================================
    # STOP
    # ============================================================

    def stop(self) -> None:

        self._running = False

        if self._thread is not None:

            self._thread.join(
                timeout=3.0
            )

            self._thread = None

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

                    try:
                        cap.release()
                    except Exception:
                        pass

                cap = self._open_capture()

                if not cap.isOpened():

                    now = time.monotonic()

                    if (
                        now
                        - self._last_error_time
                        > 2.0
                    ):

                        print(
                            "[RTSPReader] "
                            "Could not open RTSP. "
                            "Retrying..."
                        )

                        self._last_error_time = now

                    time.sleep(1.0)

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

                try:
                    cap.release()
                except Exception:
                    pass

                cap = None

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

        if cap is not None:

            try:
                cap.release()
            except Exception:
                pass

    # ============================================================
    # OPEN RTSP
    # ============================================================

    def _open_capture(
        self,
    ) -> cv2.VideoCapture:
        """
        Open RTSP using FFmpeg.

        TCP is intentionally used because the CCTV stream previously
        showed H.264 packet/decoder errors.

        The low-latency flags help prevent OpenCV/FFmpeg from building
        a large backlog of old frames.
        """

        # --------------------------------------------------------
        # FFmpeg RTSP options
        # --------------------------------------------------------

        os.environ[
            "OPENCV_FFMPEG_CAPTURE_OPTIONS"
        ] = (
            "rtsp_transport;tcp|"
            "fflags;nobuffer|"
            "flags;low_delay"
        )

        print(
            "[RTSPReader] Opening RTSP "
            "using FFmpeg/TCP..."
        )

        cap = cv2.VideoCapture(
            self._url,
            cv2.CAP_FFMPEG,
        )

        # --------------------------------------------------------
        # Check connection
        # --------------------------------------------------------

        if not cap.isOpened():

            print(
                "[RTSPReader] ERROR: "
                "Could not open RTSP stream."
            )

            return cap

        # --------------------------------------------------------
        # Minimize OpenCV frame buffering
        # --------------------------------------------------------

        try:

            cap.set(
                cv2.CAP_PROP_BUFFERSIZE,
                1,
            )

        except Exception:

            pass

        print(
            "[RTSPReader] "
            "RTSP capture opened successfully."
        )

        return cap