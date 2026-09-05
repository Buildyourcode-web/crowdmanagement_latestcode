"""
logging.py — Structured Logging Conventions for Future AI Services.

Standardizes audit and telemetry logging for all future AI pipeline events.
Every pipeline event structure conforms to:
- timestamp
- camera_id
- zone_id
- pipeline_id
- pipeline_type
- event_type
- status
- model_version
- processing_latency
- error
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from loguru import logger


class AIPipelineLogEvent(BaseModel):
    """Structured telemetry event schema for AI pipelines."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    camera_id: str
    zone_id: Optional[str] = None
    pipeline_id: str
    pipeline_type: str  # CROWD, QUEUE, FRS, SAFETY
    event_type: str     # INFERENCE, HEALTH_CHECK, STATE_CHANGE, ANOMALY, ERROR
    status: str         # SUCCESS, DEGRADED, FAILED, TIMEOUT
    model_version: Optional[str] = None
    processing_latency_ms: Optional[float] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_log_dict(self) -> Dict[str, Any]:
        d = self.model_dump()
        d["timestamp"] = self.timestamp.isoformat()
        return d


class AIPipelineLogger:
    """Helper for emitting standardized AI pipeline log records."""

    @staticmethod
    def log_event(event: AIPipelineLogEvent) -> None:
        """Emits structured log via loguru."""
        log_data = event.to_log_dict()
        if event.error:
            logger.error(f"[AI-Pipeline-Event] {log_data}")
        elif event.status in {"DEGRADED", "TIMEOUT"}:
            logger.warning(f"[AI-Pipeline-Event] {log_data}")
        else:
            logger.info(f"[AI-Pipeline-Event] {log_data}")
