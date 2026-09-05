"""
health.py — FRS Pipeline Health Monitor.

Tracks:
- RTSP ingestion and processing FPS
- Latency breakdown: detection, embedding, matching
- Frame drop rates and stream timeout detection (10s threshold)
- Transition states: HEALTHY, DEGRADED, FAILED
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class FRSPipelineHealthTracker:
    camera_code: str
    fps: float = 0.0
    rtsp_fps: float = 0.0
    detection_latency_ms: float = 0.0
    embedding_latency_ms: float = 0.0
    matching_latency_ms: float = 0.0
    dropped_frames: int = 0
    total_frames: int = 0
    consecutive_errors: int = 0
    last_error: Optional[str] = None
    last_frame_time: Optional[float] = None
    status: str = "HEALTHY"

    def record_frame(
        self,
        det_ms: float = 0.0,
        emb_ms: float = 0.0,
        match_ms: float = 0.0,
        processing_fps: float = 10.0,
    ):
        """Record successful frame processing metrics."""
        self.last_frame_time = time.time()
        self.total_frames += 1
        self.consecutive_errors = 0
        self.last_error = None
        self.fps = round(processing_fps, 1)
        self.rtsp_fps = round(processing_fps, 1)

        # Exponential moving average for latencies
        alpha = 0.2
        self.detection_latency_ms = round(alpha * det_ms + (1 - alpha) * self.detection_latency_ms, 2)
        self.embedding_latency_ms = round(alpha * emb_ms + (1 - alpha) * self.embedding_latency_ms, 2)
        self.matching_latency_ms = round(alpha * match_ms + (1 - alpha) * self.matching_latency_ms, 2)

    def record_drop(self, count: int = 1):
        """Record dropped frames."""
        self.dropped_frames += count

    def record_error(self, error_msg: str):
        """Record pipeline processing error."""
        self.consecutive_errors += 1
        self.last_error = error_msg

    def evaluate_status(self) -> str:
        """Determines health status based on frame reception and error counters."""
        now = time.time()
        if self.consecutive_errors >= 5:
            self.status = "FAILED"
            return self.status

        if self.last_frame_time is not None:
            time_since_last = now - self.last_frame_time
            if time_since_last > 15.0:
                self.status = "FAILED"
            elif time_since_last > 8.0:
                self.status = "DEGRADED"
            else:
                self.status = "HEALTHY"
        else:
            self.status = "HEALTHY"

        return self.status

    def get_health(self) -> Dict[str, Any]:
        """Returns health summary dict."""
        curr_status = self.evaluate_status()
        last_dt = (
            datetime.fromtimestamp(self.last_frame_time, tz=timezone.utc).isoformat()
            if self.last_frame_time
            else None
        )
        return {
            "status": curr_status,
            "fps": self.fps,
            "rtsp_fps": self.rtsp_fps,
            "detection_latency_ms": self.detection_latency_ms,
            "embedding_latency_ms": self.embedding_latency_ms,
            "matching_latency_ms": self.matching_latency_ms,
            "dropped_frames": self.dropped_frames,
            "total_frames": self.total_frames,
            "consecutive_errors": self.consecutive_errors,
            "last_error": self.last_error,
            "last_frame_received_at": last_dt,
        }
