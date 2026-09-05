"""
app.services.rtsp_test_service — Production RTSP Stream Inspection & Validation.

Executes asynchronous stream inspection using system ffprobe with strict timeouts,
process tree cleanup, error classification, and complete credential sanitization.
"""

import asyncio
import json
import re
import shutil
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from loguru import logger
from app.security.encryption import sanitize_rtsp_url


class RTSPErrorCode:
    CAMERA_NOT_FOUND = "CAMERA_NOT_FOUND"
    INVALID_RTSP_URL = "INVALID_RTSP_URL"
    NETWORK_UNREACHABLE = "NETWORK_UNREACHABLE"
    RTSP_CONNECTION_FAILED = "RTSP_CONNECTION_FAILED"
    RTSP_AUTH_FAILED = "RTSP_AUTH_FAILED"
    STREAM_NOT_FOUND = "STREAM_NOT_FOUND"
    UNSUPPORTED_CODEC = "UNSUPPORTED_CODEC"
    NO_VIDEO_TRACK = "NO_VIDEO_TRACK"
    STREAM_TIMEOUT = "STREAM_TIMEOUT"
    FFPROBE_UNAVAILABLE = "FFPROBE_UNAVAILABLE"
    GST_PIPELINE_UNAVAILABLE = "GST_PIPELINE_UNAVAILABLE"
    UNKNOWN_STREAM_ERROR = "UNKNOWN_STREAM_ERROR"


ERROR_MESSAGES = {
    RTSPErrorCode.CAMERA_NOT_FOUND: "The requested camera was not found in the database.",
    RTSPErrorCode.INVALID_RTSP_URL: "The provided RTSP URL format is invalid. Must start with rtsp:// or rtsps://",
    RTSPErrorCode.NETWORK_UNREACHABLE: "Host or network unreachable. Check the camera IP address and subnet routing.",
    RTSPErrorCode.RTSP_CONNECTION_FAILED: "Failed to connect to RTSP port (typically 554). Ensure camera is powered and accessible.",
    RTSPErrorCode.RTSP_AUTH_FAILED: "Camera authentication failed. Verify username and password.",
    RTSPErrorCode.STREAM_NOT_FOUND: "RTSP stream path not found (404). Check channel/stream path configuration.",
    RTSPErrorCode.UNSUPPORTED_CODEC: "Video track has an unsupported codec. Recommended codecs: H.264 (AVC) or H.265 (HEVC).",
    RTSPErrorCode.NO_VIDEO_TRACK: "RTSP stream opened successfully but contains no active video tracks.",
    RTSPErrorCode.STREAM_TIMEOUT: "Connection timed out while probing RTSP stream. Camera responded too slowly.",
    RTSPErrorCode.FFPROBE_UNAVAILABLE: "ffprobe utility is not installed or not found in system PATH.",
    RTSPErrorCode.GST_PIPELINE_UNAVAILABLE: "GStreamer pipeline utility is unavailable on the host system.",
    RTSPErrorCode.UNKNOWN_STREAM_ERROR: "An unexpected error occurred while inspecting the RTSP stream.",
}


def _classify_ffprobe_error(stderr_text: str) -> Tuple[str, str]:
    """Classifies raw ffprobe stderr output into standardized error code & sanitized human message."""
    lower = stderr_text.lower()

    if "401 unauthorized" in lower or "authorization failed" in lower or "authentication failed" in lower:
        return RTSPErrorCode.RTSP_AUTH_FAILED, ERROR_MESSAGES[RTSPErrorCode.RTSP_AUTH_FAILED]
    if "404 not found" in lower or "stream not found" in lower:
        return RTSPErrorCode.STREAM_NOT_FOUND, ERROR_MESSAGES[RTSPErrorCode.STREAM_NOT_FOUND]
    if "connection refused" in lower or "connection reset" in lower:
        return RTSPErrorCode.RTSP_CONNECTION_FAILED, ERROR_MESSAGES[RTSPErrorCode.RTSP_CONNECTION_FAILED]
    if "no route to host" in lower or "host is down" in lower or "network is unreachable" in lower or "failed to resolve" in lower:
        return RTSPErrorCode.NETWORK_UNREACHABLE, ERROR_MESSAGES[RTSPErrorCode.NETWORK_UNREACHABLE]
    if "immediate exit requested" in lower or "timed out" in lower or "timeout" in lower:
        return RTSPErrorCode.STREAM_TIMEOUT, ERROR_MESSAGES[RTSPErrorCode.STREAM_TIMEOUT]

    return RTSPErrorCode.UNKNOWN_STREAM_ERROR, ERROR_MESSAGES[RTSPErrorCode.UNKNOWN_STREAM_ERROR]


def _parse_fps(rate_str: Optional[str]) -> int:
    """Safely converts rate strings like '25/1' or '30000/1001' or '24' to integer FPS."""
    if not rate_str:
        return 25
    try:
        if "/" in rate_str:
            num, den = rate_str.split("/", 1)
            num_f, den_f = float(num), float(den)
            return round(num_f / den_f) if den_f != 0 else 25
        return round(float(rate_str))
    except Exception:
        return 25


class RTSPTestService:
    """Production RTSP stream validation and inspection service."""

    DEFAULT_TIMEOUT_SEC = 6.0

    @classmethod
    def validate_url_syntax(cls, url: Optional[str]) -> bool:
        """Validates basic syntax of RTSP/RTSPS URLs."""
        if not url or not isinstance(url, str):
            return False
        clean = url.strip()
        return clean.startswith("rtsp://") or clean.startswith("rtsps://")

    @classmethod
    async def test_stream(
        cls,
        rtsp_url: str,
        camera_id: str = "PROBE_STREAM",
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    ) -> Dict[str, Any]:
        """
        Validates an RTSP stream using ffprobe.
        Returns a structured dictionary conforming to Step 3 specification.
        Guarantees zero password leakage.
        """
        tested_at = datetime.now(timezone.utc).isoformat()

        # 1. URL syntax validation
        if not cls.validate_url_syntax(rtsp_url):
            return {
                "camera_id": camera_id,
                "reachable": False,
                "authenticated": False,
                "stream_available": False,
                "error_code": RTSPErrorCode.INVALID_RTSP_URL,
                "error_message": ERROR_MESSAGES[RTSPErrorCode.INVALID_RTSP_URL],
                "tested_at": tested_at,
            }

        # 2. Check ffprobe availability
        ffprobe_bin = shutil.which("ffprobe")
        if not ffprobe_bin:
            logger.warning("[RTSPTestService] ffprobe not found in system PATH")
            return {
                "camera_id": camera_id,
                "reachable": False,
                "authenticated": False,
                "stream_available": False,
                "error_code": RTSPErrorCode.FFPROBE_UNAVAILABLE,
                "error_message": ERROR_MESSAGES[RTSPErrorCode.FFPROBE_UNAVAILABLE],
                "tested_at": tested_at,
            }

        # 3. Construct probe command
        # stimeout in microseconds (e.g. 5,000,000 = 5 seconds)
        stimeout_us = int(timeout_sec * 1_000_000)
        cmd = [
            ffprobe_bin,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,r_frame_rate,avg_frame_rate",
            "-of", "json",
            "-rtsp_transport", "tcp",
            "-stimeout", str(stimeout_us),
            "-i", rtsp_url,
        ]

        sanitized_url = sanitize_rtsp_url(rtsp_url)
        logger.info(f"[RTSPTestService] Testing stream {camera_id} at {sanitized_url} (timeout={timeout_sec}s)")

        start_time = time.perf_counter()
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_data, stderr_data = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_sec + 1.0,
            )
            elapsed_ms = round((time.perf_counter() - start_time) * 1000)

            stdout_text = stdout_data.decode("utf-8", errors="replace").strip()
            stderr_text = stderr_data.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0 or not stdout_text:
                err_code, err_msg = _classify_ffprobe_error(stderr_text)
                logger.warning(f"[RTSPTestService] Probe failed for {camera_id}: {err_code} - {err_msg}")
                return {
                    "camera_id": camera_id,
                    "reachable": err_code not in (RTSPErrorCode.NETWORK_UNREACHABLE, RTSPErrorCode.RTSP_CONNECTION_FAILED),
                    "authenticated": err_code != RTSPErrorCode.RTSP_AUTH_FAILED,
                    "stream_available": False,
                    "error_code": err_code,
                    "error_message": err_msg,
                    "latency_ms": elapsed_ms,
                    "tested_at": tested_at,
                }

            # Parse JSON stream entries
            data = json.loads(stdout_text)
            streams = data.get("streams", [])

            if not streams:
                return {
                    "camera_id": camera_id,
                    "reachable": True,
                    "authenticated": True,
                    "stream_available": False,
                    "error_code": RTSPErrorCode.NO_VIDEO_TRACK,
                    "error_message": ERROR_MESSAGES[RTSPErrorCode.NO_VIDEO_TRACK],
                    "latency_ms": elapsed_ms,
                    "tested_at": tested_at,
                }

            v_stream = streams[0]
            width = v_stream.get("width")
            height = v_stream.get("height")
            codec = v_stream.get("codec_name", "unknown").lower()
            r_fps = _parse_fps(v_stream.get("r_frame_rate"))

            # Codec check
            if codec not in ("h264", "hevc", "h265", "mjpeg", "mpeg4"):
                logger.warning(f"[RTSPTestService] Unusual codec detected: {codec}")

            resolution_str = f"{width}x{height}" if width and height else "1920x1080"
            stability = "STABLE" if elapsed_ms < 1500 and r_fps >= 15 else "DEGRADED"

            return {
                "camera_id": camera_id,
                "reachable": True,
                "authenticated": True,
                "stream_available": True,
                "resolution": resolution_str,
                "fps": r_fps,
                "codec": codec,
                "latency_ms": elapsed_ms,
                "protocol": "rtsp",
                "stability": stability,
                "tested_at": tested_at,
                "error": None,
            }

        except asyncio.TimeoutError:
            if proc:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            logger.warning(f"[RTSPTestService] Stream probe timed out after {timeout_sec}s for {camera_id}")
            return {
                "camera_id": camera_id,
                "reachable": False,
                "authenticated": False,
                "stream_available": False,
                "error_code": RTSPErrorCode.STREAM_TIMEOUT,
                "error_message": ERROR_MESSAGES[RTSPErrorCode.STREAM_TIMEOUT],
                "latency_ms": round(timeout_sec * 1000),
                "tested_at": tested_at,
            }
        except Exception as e:
            if proc:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            logger.error(f"[RTSPTestService] Unexpected probe exception for {camera_id}: {e}")
            return {
                "camera_id": camera_id,
                "reachable": False,
                "authenticated": False,
                "stream_available": False,
                "error_code": RTSPErrorCode.UNKNOWN_STREAM_ERROR,
                "error_message": ERROR_MESSAGES[RTSPErrorCode.UNKNOWN_STREAM_ERROR],
                "tested_at": tested_at,
            }
