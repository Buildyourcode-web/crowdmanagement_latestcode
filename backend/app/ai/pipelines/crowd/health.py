"""
health.py — Pipeline Health & Stream Telemetry Monitor.

Monitors frame arrival cadence, input/processing framerates, latencies,
dropped frames, and faults to declare pipeline health (HEALTHY, DEGRADED, FAILED).
"""

from collections import deque
import time
from typing import Deque, Optional
from pydantic import BaseModel
from app.ai.orchestrator.state import PipelineState


class PipelineHealthStatus(BaseModel):
    """Real-time health report for a running inference pipeline."""
    camera_id: str
    camera_code: str
    profile_id: str
    pipeline_state: PipelineState
    health_status: str  # HEALTHY, DEGRADED, FAILED, INACTIVE
    last_frame_at: Optional[float] = None
    seconds_since_last_frame: Optional[float] = None
    input_fps: float = 0.0
    processed_fps: float = 0.0
    target_fps: int = 15
    dropped_frames: int = 0
    total_frames_processed: int = 0
    detection_latency_ms: float = 0.0
    inference_latency_ms: float = 0.0
    tracking_latency_ms: float = 0.0
    error_count: int = 0
    last_error: Optional[str] = None


class PipelineHealthMonitor:
    """
    Monitors operational telemetry of an inference stream.
    Detects dropped frames, stuttering FPS, decoder faults, and stream loss.
    """

    def __init__(
        self,
        camera_id: str,
        camera_code: str,
        profile_id: str,
        target_fps: int = 15,
        no_frame_timeout_sec: float = 10.0,
    ):
        self.camera_id = camera_id
        self.camera_code = camera_code
        self.profile_id = profile_id
        self.target_fps = target_fps
        self.no_frame_timeout_sec = no_frame_timeout_sec

        self.pipeline_state = PipelineState.CREATED
        self.last_frame_at: Optional[float] = None
        self.dropped_frames: int = 0
        self.total_frames: int = 0
        self.error_count: int = 0
        self.last_error: Optional[str] = None

        # Rolling timestamp deque for FPS measurement (last 5 seconds)
        self._frame_timestamps: Deque[float] = deque()
        self._det_latencies: Deque[float] = deque(maxlen=30)
        self._trk_latencies: Deque[float] = deque(maxlen=30)

    def record_frame(
        self,
        timestamp: float,
        detection_latency_ms: float = 0.0,
        tracking_latency_ms: float = 0.0,
        dropped: int = 0,
    ) -> None:
        """Records telemetry for a processed video frame."""
        self.last_frame_at = timestamp
        self.total_frames += 1
        self.dropped_frames += dropped

        self._frame_timestamps.append(timestamp)
        self._det_latencies.append(detection_latency_ms)
        self._trk_latencies.append(tracking_latency_ms)

        # Keep timestamps in 5-second window
        cutoff = timestamp - 5.0
        while self._frame_timestamps and self._frame_timestamps[0] < cutoff:
            self._frame_timestamps.popleft()

    def record_error(self, error_message: str) -> None:
        """Records an operational failure or decoder error."""
        self.error_count += 1
        self.last_error = str(error_message)

    def compute_health(self) -> PipelineHealthStatus:
        """Evaluates health conditions and returns health report."""
        now = time.time()
        sec_since = (now - self.last_frame_at) if self.last_frame_at else None

        # Compute rolling FPS
        if len(self._frame_timestamps) >= 2:
            duration = self._frame_timestamps[-1] - self._frame_timestamps[0]
            current_fps = round(len(self._frame_timestamps) / max(duration, 0.1), 1)
        else:
            current_fps = 0.0

        avg_det_lat = (
            round(sum(self._det_latencies) / len(self._det_latencies), 1)
            if self._det_latencies
            else 0.0
        )
        avg_trk_lat = (
            round(sum(self._trk_latencies) / len(self._trk_latencies), 1)
            if self._trk_latencies
            else 0.0
        )

        # Health state determination
        if self.pipeline_state == PipelineState.RUNNING:
            if sec_since is not None and sec_since > self.no_frame_timeout_sec:
                health = "FAILED"
                self.last_error = f"Stream timeout: No frames received in {sec_since:.1f}s"
            elif current_fps > 0 and current_fps < (self.target_fps * 0.4):
                health = "DEGRADED"
            elif self.error_count > 10:
                health = "DEGRADED"
            else:
                health = "HEALTHY"
        elif self.pipeline_state in (PipelineState.STOPPED, PipelineState.CREATED):
            health = "INACTIVE"
        elif self.pipeline_state == PipelineState.FAILED:
            health = "FAILED"
        else:
            health = "DEGRADED"

        return PipelineHealthStatus(
            camera_id=self.camera_id,
            camera_code=self.camera_code,
            profile_id=self.profile_id,
            pipeline_state=self.pipeline_state,
            health_status=health,
            last_frame_at=self.last_frame_at,
            seconds_since_last_frame=round(sec_since, 1) if sec_since else None,
            input_fps=current_fps,
            processed_fps=current_fps,
            target_fps=self.target_fps,
            dropped_frames=self.dropped_frames,
            total_frames_processed=self.total_frames,
            detection_latency_ms=avg_det_lat,
            inference_latency_ms=avg_det_lat,
            tracking_latency_ms=avg_trk_lat,
            error_count=self.error_count,
            last_error=self.last_error,
        )
