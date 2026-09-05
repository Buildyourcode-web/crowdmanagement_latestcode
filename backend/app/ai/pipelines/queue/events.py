"""
events.py — Queue AI Event Generation & Cooldown Engine.

Evaluates queue metrics and risk states, generating structured operational events
with 60-second duplicate cooldown suppression.
Emits events directly onto the shared application event bus.
"""

import time
import uuid
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.ai.pipelines.queue.analytics import QueueMetricsResult
from app.redis.event_bus import event_bus


class QueueAIEvent(BaseModel):
    """Structured operational event emitted by the Queue AI subsystem."""

    event_id: str = Field(default_factory=lambda: f"EVT-Q-{uuid.uuid4().hex[:8].upper()}")
    event_type: str
    camera_id: str
    camera_code: str
    zone_id: Optional[str] = None
    profile_id: str = "QUEUE_STANDARD"
    timestamp: float
    severity: str  # INFO, WARNING, CRITICAL
    message: str
    metrics: Dict[str, Any]
    source: str = "QUEUE_AI_PIPELINE"
    configuration_version: str = "1.0"


class QueueEventEngine:
    """
    Evaluates real-time queue states and publishes cooldown-suppressed events.
    Suppression interval defaults to 60.0 seconds per (camera_code, event_type).
    """

    def __init__(self, cooldown_seconds: float = 60.0):
        self.cooldown_seconds = cooldown_seconds
        # Cooldown cache: (camera_code, event_type) -> last_emitted_timestamp
        self._cooldown_cache: Dict[Tuple[str, str], float] = {}

    def _should_suppress(self, camera_code: str, event_type: str, now: float) -> bool:
        key = (camera_code, event_type)
        last_time = self._cooldown_cache.get(key, 0.0)
        if now - last_time < self.cooldown_seconds:
            return True
        self._cooldown_cache[key] = now
        return False

    async def evaluate_and_emit(
        self,
        metrics: QueueMetricsResult,
        risk_score: float,
        risk_level: str,
        risk_factors: List[str],
        zone_id: Optional[str] = None,
    ) -> List[QueueAIEvent]:
        """Evaluates metrics against operational thresholds and emits non-suppressed events."""
        now = metrics.timestamp
        events_to_emit: List[QueueAIEvent] = []

        metrics_snapshot = {
            "queue_count": metrics.queue_count,
            "occupancy_percentage": metrics.occupancy_percentage,
            "average_wait_seconds": metrics.average_wait_seconds,
            "max_current_dwell_seconds": metrics.max_current_dwell_seconds,
            "inflow": metrics.inflow,
            "outflow": metrics.outflow,
            "growth_per_minute": metrics.growth_per_minute,
            "risk_score": risk_score,
            "risk_level": risk_level,
        }

        # 1. Critical Risk Event
        if risk_level == "CRITICAL" and not self._should_suppress(metrics.camera_code, "QUEUE_RISK_CRITICAL", now):
            events_to_emit.append(
                QueueAIEvent(
                    event_type="QUEUE_RISK_CRITICAL",
                    camera_id=metrics.camera_id,
                    camera_code=metrics.camera_code,
                    zone_id=zone_id,
                    profile_id=metrics.profile_id,
                    timestamp=now,
                    severity="CRITICAL",
                    message=f"CRITICAL Queue Risk ({risk_score}/100) at {metrics.camera_code}: {'; '.join(risk_factors)}",
                    metrics=metrics_snapshot,
                )
            )

        # 2. High Risk Event
        elif risk_level == "HIGH" and not self._should_suppress(metrics.camera_code, "QUEUE_RISK_HIGH", now):
            events_to_emit.append(
                QueueAIEvent(
                    event_type="QUEUE_RISK_HIGH",
                    camera_id=metrics.camera_id,
                    camera_code=metrics.camera_code,
                    zone_id=zone_id,
                    profile_id=metrics.profile_id,
                    timestamp=now,
                    severity="WARNING",
                    message=f"High Queue Risk ({risk_score}/100) at {metrics.camera_code}: {'; '.join(risk_factors)}",
                    metrics=metrics_snapshot,
                )
            )

        # 3. Occupancy Threshold Exceeded (>= 90%)
        if metrics.occupancy_percentage and metrics.occupancy_percentage >= 90.0:
            if not self._should_suppress(metrics.camera_code, "QUEUE_THRESHOLD_EXCEEDED", now):
                events_to_emit.append(
                    QueueAIEvent(
                        event_type="QUEUE_THRESHOLD_EXCEEDED",
                        camera_id=metrics.camera_id,
                        camera_code=metrics.camera_code,
                        zone_id=zone_id,
                        profile_id=metrics.profile_id,
                        timestamp=now,
                        severity="CRITICAL",
                        message=f"Queue occupancy strictly exceeded 90% threshold ({metrics.occupancy_percentage}%) at {metrics.camera_code}.",
                        metrics=metrics_snapshot,
                    )
                )

        # 4. Wait Time High (>= 600s / 10 minutes)
        if metrics.average_wait_seconds and metrics.average_wait_seconds >= 600:
            if not self._should_suppress(metrics.camera_code, "QUEUE_WAIT_TIME_HIGH", now):
                mins = metrics.average_wait_seconds // 60
                events_to_emit.append(
                    QueueAIEvent(
                        event_type="QUEUE_WAIT_TIME_HIGH",
                        camera_id=metrics.camera_id,
                        camera_code=metrics.camera_code,
                        zone_id=zone_id,
                        profile_id=metrics.profile_id,
                        timestamp=now,
                        severity="WARNING",
                        message=f"Queue wait time elevated ({mins} mins) at {metrics.camera_code}.",
                        metrics=metrics_snapshot,
                    )
                )

        # 5. Inflow Spike (Inflow >= 40/min)
        if metrics.inflow and metrics.inflow >= 40:
            if not self._should_suppress(metrics.camera_code, "QUEUE_INFLOW_SPIKE", now):
                events_to_emit.append(
                    QueueAIEvent(
                        event_type="QUEUE_INFLOW_SPIKE",
                        camera_id=metrics.camera_id,
                        camera_code=metrics.camera_code,
                        zone_id=zone_id,
                        profile_id=metrics.profile_id,
                        timestamp=now,
                        severity="WARNING",
                        message=f"Queue inflow surge ({metrics.inflow} persons/min) at {metrics.camera_code}.",
                        metrics=metrics_snapshot,
                    )
                )

        # 6. Growth Spike (Growth >= 25/min)
        if metrics.growth_per_minute and metrics.growth_per_minute >= 25:
            if not self._should_suppress(metrics.camera_code, "QUEUE_GROWTH_SPIKE", now):
                events_to_emit.append(
                    QueueAIEvent(
                        event_type="QUEUE_GROWTH_SPIKE",
                        camera_id=metrics.camera_id,
                        camera_code=metrics.camera_code,
                        zone_id=zone_id,
                        profile_id=metrics.profile_id,
                        timestamp=now,
                        severity="WARNING",
                        message=f"Rapid queue growth (+{metrics.growth_per_minute} persons/min) at {metrics.camera_code}.",
                        metrics=metrics_snapshot,
                    )
                )

        # Publish events to event bus
        for evt in events_to_emit:
            await event_bus.publish(
                channel="ai",
                event_type=evt.event_type,
                payload=evt.model_dump(),
            )

        return events_to_emit
