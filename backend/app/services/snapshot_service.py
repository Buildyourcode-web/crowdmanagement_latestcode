"""
app.services.snapshot_service — Real RTSP Camera Snapshot Capture Service.

Extracts a single real frame from a camera's verified RTSP stream using ffmpeg.
Includes strict timeouts, process tree termination, in-memory caching,
and complete credential protection.
"""

import asyncio
import shutil
import time
from typing import Dict, Optional, Tuple
from fastapi import HTTPException, status
from loguru import logger
from app.models.camera import Camera
from app.security.encryption import (
    build_authenticated_rtsp_url,
    decrypt_credential,
    sanitize_rtsp_url,
)


class SnapshotService:
    # In-memory short-lived cache: camera_id -> (timestamp, jpeg_bytes)
    _cache: Dict[str, Tuple[float, bytes]] = {}
    CACHE_TTL_SEC = 5.0
    DEFAULT_TIMEOUT_SEC = 5.0

    # Test mock hook
    _mock_frames: Dict[str, bytes] = {}

    @classmethod
    def set_mock_frame(cls, camera_id: str, frame_bytes: bytes) -> None:
        """Sets a mock JPEG frame for automated test execution."""
        cls._mock_frames[camera_id] = frame_bytes

    @classmethod
    def clear_mock_frames(cls) -> None:
        cls._mock_frames.clear()
        cls._cache.clear()

    @classmethod
    async def capture_frame(
        cls,
        camera: Camera,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    ) -> bytes:
        """
        Captures a single real JPEG frame from the camera's verified RTSP stream.
        Enforces stream verification and online checks.
        Guarantees zero password leakage.
        """
        cam_id = str(camera.id)

        # 1. Validation checks
        if not camera.enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "CAMERA_OFFLINE",
                    "message": "Camera Offline — ROI editor unavailable",
                },
            )

        status_norm = (camera.stream_status or "").upper()
        if status_norm == "NOT_TESTED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "CAMERA_STREAM_NOT_VERIFIED",
                    "message": "Camera stream not verified",
                },
            )

        if status_norm == "OFFLINE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "CAMERA_OFFLINE",
                    "message": "Camera Offline — ROI editor unavailable",
                },
            )

        # Check mock hook (for tests)
        if cam_id in cls._mock_frames or "GLOBAL_MOCK" in cls._mock_frames:
            return cls._mock_frames.get(cam_id) or cls._mock_frames["GLOBAL_MOCK"]

        # Check cache
        now = time.time()
        if cam_id in cls._cache:
            ts, cached_bytes = cls._cache[cam_id]
            if now - ts < cls.CACHE_TTL_SEC:
                return cached_bytes

        # 2. Check ffmpeg availability
        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            logger.warning("[SnapshotService] ffmpeg binary not found in system PATH")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "FFMPEG_UNAVAILABLE",
                    "message": "ffmpeg utility is not available on the server",
                },
            )

        # 3. Decrypt and reconstruct authenticated RTSP URL
        raw_url = decrypt_credential(camera.rtsp_url_encrypted) if camera.rtsp_url_encrypted else None
        if not raw_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "CAMERA_STREAM_NOT_VERIFIED",
                    "message": "Camera has no configured RTSP stream URL",
                },
            )

        raw_pwd = decrypt_credential(camera.password_encrypted) if camera.password_encrypted else None
        authed_url = build_authenticated_rtsp_url(raw_url, camera.username, raw_pwd)

        sanitized_url = sanitize_rtsp_url(authed_url)
        logger.info(f"[SnapshotService] Capturing frame for camera {camera.camera_code} from {sanitized_url}")

        # 4. ffmpeg command
        stimeout_us = int(timeout_sec * 1_000_000)
        cmd = [
            ffmpeg_bin,
            "-y",
            "-rtsp_transport", "tcp",
            "-stimeout", str(stimeout_us),
            "-i", authed_url,
            "-frames:v", "1",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "-",
        ]

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

            if proc.returncode != 0 or len(stdout_data) < 100:
                stderr_text = stderr_data.decode("utf-8", errors="replace")
                sanitized_err = sanitize_rtsp_url(stderr_text)
                logger.warning(f"[SnapshotService] Frame capture failed for {camera.camera_code}: {sanitized_err}")
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail={
                        "code": "SNAPSHOT_CAPTURE_FAILED",
                        "message": "Failed to capture frame from camera stream",
                    },
                )

            # Basic JPEG magic bytes check (\xff\xd8)
            if not stdout_data.startswith(b"\xff\xd8"):
                logger.warning(f"[SnapshotService] Invalid JPEG header received for {camera.camera_code}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail={
                        "code": "INVALID_FRAME_FORMAT",
                        "message": "Camera returned an unreadable frame format",
                    },
                )

            cls._cache[cam_id] = (now, stdout_data)
            return stdout_data

        except asyncio.TimeoutError:
            if proc:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            logger.warning(f"[SnapshotService] Frame capture timed out for {camera.camera_code}")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail={
                    "code": "SNAPSHOT_CAPTURE_FAILED",
                    "message": "Connection timed out while capturing camera frame",
                },
            )
        except HTTPException:
            raise
        except Exception as e:
            if proc:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
            logger.error(f"[SnapshotService] Unexpected error capturing frame for {camera.camera_code}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "code": "SNAPSHOT_CAPTURE_FAILED",
                    "message": "An unexpected error occurred while capturing camera frame",
                },
            )
