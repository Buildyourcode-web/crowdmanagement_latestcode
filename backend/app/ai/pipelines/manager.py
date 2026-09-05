"""
manager.py — AI Pipeline Manager Interface.

Tracks registered pipeline instances and their lifecycle states across Crowd and other AI engines.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.ai.orchestrator.state import PipelineState
from app.ai.pipelines.crowd.registry import CrowdPipelineRegistry
from app.ai.pipelines.queue.registry import QueuePipelineRegistry


class PipelineInstance(BaseModel):
    pipeline_id: str
    camera_id: str
    camera_code: Optional[str] = None
    profile_id: str
    state: PipelineState = PipelineState.CREATED
    fps_actual: float = 0.0
    latency_ms: float = 0.0
    error_message: Optional[str] = None


class PipelineManager:
    """Manages active AI inference pipeline instances across all camera streams."""

    @staticmethod
    def list_pipeline_instances() -> List[PipelineInstance]:
        """Returns active pipeline instances from active pipeline registries."""
        crowd_pipes = CrowdPipelineRegistry.list_pipelines()
        queue_pipes = QueuePipelineRegistry.list_all()
        results = []
        for p in crowd_pipes:
            hlth = p.get_health()
            results.append(
                PipelineInstance(
                    pipeline_id=f"PIPE-{p.camera_code}-{p.profile_id}",
                    camera_id=p.camera_id,
                    camera_code=p.camera_code,
                    profile_id=p.profile_id,
                    state=p.state,
                    fps_actual=hlth.processed_fps if hasattr(hlth, "processed_fps") else hlth.get("processed_fps", 0.0),
                    latency_ms=(hlth.detection_latency_ms + hlth.tracking_latency_ms) if hasattr(hlth, "detection_latency_ms") else (hlth.get("inference_latency_ms", 0.0) + hlth.get("analytics_latency_ms", 0.0)),
                    error_message=hlth.last_error if hasattr(hlth, "last_error") else hlth.get("last_error"),
                )
            )
        for q in queue_pipes:
            hlth = q.get_health()
            results.append(
                PipelineInstance(
                    pipeline_id=f"PIPE-{q.config.camera_code}-{q.config.profile_id}",
                    camera_id=q.config.camera_id,
                    camera_code=q.config.camera_code,
                    profile_id=q.config.profile_id,
                    state=q.state,
                    fps_actual=hlth.get("processed_fps", 0.0) if isinstance(hlth, dict) else hlth.processed_fps,
                    latency_ms=(hlth.get("inference_latency_ms", 0.0) + hlth.get("analytics_latency_ms", 0.0)) if isinstance(hlth, dict) else (hlth.detection_latency_ms + hlth.tracking_latency_ms),
                    error_message=hlth.get("last_error") if isinstance(hlth, dict) else hlth.last_error,
                )
            )
        return results

    @staticmethod
    def get_pipeline_instance(camera_id_or_code: str) -> Optional[PipelineInstance]:
        """Retrieve single pipeline instance."""
        p = CrowdPipelineRegistry.get(camera_id_or_code)
        if p:
            hlth = p.get_health()
            return PipelineInstance(
                pipeline_id=f"PIPE-{p.camera_code}-{p.profile_id}",
                camera_id=p.camera_id,
                camera_code=p.camera_code,
                profile_id=p.profile_id,
                state=p.state,
                fps_actual=hlth.processed_fps if hasattr(hlth, "processed_fps") else hlth.get("processed_fps", 0.0),
                latency_ms=(hlth.detection_latency_ms + hlth.tracking_latency_ms) if hasattr(hlth, "detection_latency_ms") else (hlth.get("inference_latency_ms", 0.0) + hlth.get("analytics_latency_ms", 0.0)),
                error_message=hlth.last_error if hasattr(hlth, "last_error") else hlth.get("last_error"),
            )

        q = QueuePipelineRegistry.get(camera_id_or_code)
        if q:
            hlth = q.get_health()
            return PipelineInstance(
                pipeline_id=f"PIPE-{q.config.camera_code}-{q.config.profile_id}",
                camera_id=q.config.camera_id,
                camera_code=q.config.camera_code,
                profile_id=q.config.profile_id,
                state=q.state,
                fps_actual=hlth.get("processed_fps", 0.0) if isinstance(hlth, dict) else hlth.processed_fps,
                latency_ms=(hlth.get("inference_latency_ms", 0.0) + hlth.get("analytics_latency_ms", 0.0)) if isinstance(hlth, dict) else (hlth.detection_latency_ms + hlth.tracking_latency_ms),
                error_message=hlth.get("last_error") if isinstance(hlth, dict) else hlth.last_error,
            )
        return None

    @staticmethod
    def register_pipeline(camera_id: str, profile_id: str) -> Dict[str, Any]:
        """Registers a pipeline definition."""
        return {
            "status": "REGISTERED",
            "camera_id": camera_id,
            "profile_id": profile_id,
            "state": PipelineState.CREATED.value,
        }
