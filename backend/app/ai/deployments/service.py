"""
service.py — AI Deployment Service & Data Models.

Provides unified data models for camera AI pipeline deployments,
bridging database persistence and runtime orchestrator state.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.models.ai_deployment import AIPipelineDeployment


class AIDeployment(BaseModel):
    """External representation of an AI Pipeline Deployment."""
    id: str
    camera_id: str
    camera_code: str
    profile_id: str
    pipeline_type: str
    desired_state: str = "STOPPED"
    actual_state: str = "STOPPED"
    health_state: str = "UNKNOWN"
    priority: str = "NORMAL"
    auto_restart_enabled: bool = True
    auto_reconnect_enabled: bool = True
    restart_count: int = 0
    reconnect_count: int = 0
    last_started_at: Optional[str] = None
    last_stopped_at: Optional[str] = None
    last_failure_at: Optional[str] = None
    last_error: Optional[str] = None
    process_id: Optional[int] = None
    runtime_instance_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Optional real-time metrics
    fps_actual: Optional[float] = None
    latency_ms: Optional[float] = None
    queue_count: Optional[int] = None
    crowd_count: Optional[int] = None
    risk_level: Optional[str] = None

    @classmethod
    def from_orm_model(cls, d: AIPipelineDeployment, live_metrics: Optional[Dict[str, Any]] = None) -> "AIDeployment":
        """Converts SQLAlchemy AIPipelineDeployment to Pydantic schema with optional live telemetry."""
        metrics = live_metrics or {}
        return cls(
            id=str(d.id),
            camera_id=str(d.camera_id),
            camera_code=d.camera_code,
            profile_id=d.profile_id,
            pipeline_type=d.pipeline_type,
            desired_state=d.desired_state,
            actual_state=d.actual_state,
            health_state=d.health_state,
            priority=d.priority,
            auto_restart_enabled=d.auto_restart_enabled,
            auto_reconnect_enabled=d.auto_reconnect_enabled,
            restart_count=d.restart_count,
            reconnect_count=d.reconnect_count,
            last_started_at=d.last_started_at.isoformat() if d.last_started_at else None,
            last_stopped_at=d.last_stopped_at.isoformat() if d.last_stopped_at else None,
            last_failure_at=d.last_failure_at.isoformat() if d.last_failure_at else None,
            last_error=d.last_error,
            process_id=d.process_id,
            runtime_instance_id=d.runtime_instance_id,
            created_at=d.created_at.isoformat() if d.created_at else None,
            updated_at=d.updated_at.isoformat() if d.updated_at else None,
            fps_actual=metrics.get("processed_fps"),
            latency_ms=metrics.get("latency_ms"),
            queue_count=metrics.get("queue_count"),
            crowd_count=metrics.get("crowd_count"),
            risk_level=metrics.get("risk_level"),
        )


class DeploymentService:
    """Deployment service adapter providing static lookup utilities."""

    @staticmethod
    def list_deployments() -> List[AIDeployment]:
        return []

    @staticmethod
    def get_deployment(deployment_id: str) -> Optional[AIDeployment]:
        return None

