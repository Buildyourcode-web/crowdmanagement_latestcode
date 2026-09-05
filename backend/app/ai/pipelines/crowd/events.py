"""
events.py — Structured AI Event Engine & Deduplication for Crowd Analytics.

Produces standard operational events with automatic cooldown suppression
to prevent alert flooding in real-time streaming contexts.
"""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid
from loguru import logger
from pydantic import BaseModel, Field

from app.ai.pipelines.crowd.analytics import CrowdMetricsResult
from app.redis.event_bus import event_bus


class CrowdAIEvent(BaseModel):
    """Normalized Crowd AI event payload."""
    event_id: str
    event_type: str
    camera_id: str
    camera_code: str
    zone_id: Optional[str] = None
    zone_code: Optional[str] = None
    profile_id: str
    timestamp: float
    timestamp_iso: str
    severity: str  # INFO, WARNING, HIGH, CRITICAL
    metrics: Dict[str, Any]
    factors: List[str] = Field(default_factory=list)
    message: str
    source: str = "CROWD_AI_ENGINE"


class CrowdEventEngine:
    """
    Evaluates metrics against threshold rules, applies cooldown suppression,
    and publishes structured events to Redis/WebSocket channels.
    """

    def __init__(self, cooldown_seconds: int = 60):
        self.cooldown_seconds = cooldown_seconds
        # Key: (camera_code, event_type) -> last_fired_epoch_seconds
        self._last_fired: Dict[Tuple[str, str], float] = {}
        # Tracks whether a condition was previously active to reset cooldown on recovery
        self._active_conditions: Dict[Tuple[str, str], bool] = {}

    def _should_fire(self, camera_code: str, event_type: str, now: float) -> bool:
        """Enforces cooldown suppression: returns True only if cooldown elapsed."""
        key = (camera_code, event_type)
        last = self._last_fired.get(key, 0.0)
        if (now - last) >= self.cooldown_seconds:
            self._last_fired[key] = now
            self._active_conditions[key] = True
            return True
        return False

    def _clear_condition_if_recovered(self, camera_code: str, event_type: str) -> None:
        """Clears active condition so a future spike triggers immediately."""
        key = (camera_code, event_type)
        if self._active_conditions.get(key):
            self._active_conditions[key] = False
            self._last_fired[key] = 0.0

    async def evaluate_and_emit(
        self,
        metrics: CrowdMetricsResult,
        risk_score: float,
        risk_level: str,
        risk_factors: List[str],
        stream_health: str = "HEALTHY",
    ) -> List[CrowdAIEvent]:
        """
        Evaluates metrics for trigger conditions and publishes generated events.
        """
        now = metrics.timestamp
        now_iso = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
        cam = metrics.camera_code
        events_generated: List[CrowdAIEvent] = []

        metrics_summary = {
            "current_count": metrics.current_count,
            "density": metrics.density,
            "density_level": metrics.density_level,
            "inflow_rate": metrics.inflow_rate,
            "outflow_rate": metrics.outflow_rate,
            "risk_score": risk_score,
            "risk_level": risk_level,
        }

        # 1. Critical Risk Event
        if risk_level == "CRITICAL":
            if self._should_fire(cam, "CROWD_RISK_CRITICAL", now):
                evt = CrowdAIEvent(
                    event_id=f"EVT-CROWD-{uuid.uuid4().hex[:8].upper()}",
                    event_type="CROWD_RISK_CRITICAL",
                    camera_id=metrics.camera_id,
                    camera_code=cam,
                    profile_id=metrics.profile_id,
                    timestamp=now,
                    timestamp_iso=now_iso,
                    severity="CRITICAL",
                    metrics=metrics_summary,
                    factors=risk_factors,
                    message=f"Critical crowd risk detected at {cam} (Score: {risk_score}/100)",
                )
                events_generated.append(evt)
        else:
            self._clear_condition_if_recovered(cam, "CROWD_RISK_CRITICAL")

        # 2. High Risk Event
        if risk_level == "HIGH":
            if self._should_fire(cam, "CROWD_RISK_HIGH", now):
                evt = CrowdAIEvent(
                    event_id=f"EVT-CROWD-{uuid.uuid4().hex[:8].upper()}",
                    event_type="CROWD_RISK_HIGH",
                    camera_id=metrics.camera_id,
                    camera_code=cam,
                    profile_id=metrics.profile_id,
                    timestamp=now,
                    timestamp_iso=now_iso,
                    severity="HIGH",
                    metrics=metrics_summary,
                    factors=risk_factors,
                    message=f"High crowd risk detected at {cam} (Score: {risk_score}/100)",
                )
                events_generated.append(evt)
        elif risk_level not in ("HIGH", "CRITICAL"):
            self._clear_condition_if_recovered(cam, "CROWD_RISK_HIGH")

        # 3. Density Threshold Exceeded
        if metrics.density_level in ("HIGH", "CRITICAL"):
            if self._should_fire(cam, "CROWD_THRESHOLD_EXCEEDED", now):
                evt = CrowdAIEvent(
                    event_id=f"EVT-CROWD-{uuid.uuid4().hex[:8].upper()}",
                    event_type="CROWD_THRESHOLD_EXCEEDED",
                    camera_id=metrics.camera_id,
                    camera_code=cam,
                    profile_id=metrics.profile_id,
                    timestamp=now,
                    timestamp_iso=now_iso,
                    severity="HIGH" if metrics.density_level == "CRITICAL" else "WARNING",
                    metrics=metrics_summary,
                    factors=risk_factors,
                    message=f"Crowd count {metrics.current_count} exceeded density safety threshold at {cam}",
                )
                events_generated.append(evt)
        else:
            self._clear_condition_if_recovered(cam, "CROWD_THRESHOLD_EXCEEDED")

        # 4. Inflow Surge
        if metrics.inflow_rate is not None and metrics.inflow_rate >= 80:
            if self._should_fire(cam, "CROWD_INFLOW_SPIKE", now):
                evt = CrowdAIEvent(
                    event_id=f"EVT-CROWD-{uuid.uuid4().hex[:8].upper()}",
                    event_type="CROWD_INFLOW_SPIKE",
                    camera_id=metrics.camera_id,
                    camera_code=cam,
                    profile_id=metrics.profile_id,
                    timestamp=now,
                    timestamp_iso=now_iso,
                    severity="WARNING",
                    metrics=metrics_summary,
                    factors=risk_factors,
                    message=f"Sudden inflow surge of {metrics.inflow_rate} persons/min at {cam}",
                )
                events_generated.append(evt)
        elif metrics.inflow_rate is not None and metrics.inflow_rate < 50:
            self._clear_condition_if_recovered(cam, "CROWD_INFLOW_SPIKE")

        # 5. Stream Health Events
        if stream_health == "DEGRADED":
            if self._should_fire(cam, "CAMERA_STREAM_DEGRADED", now):
                evt = CrowdAIEvent(
                    event_id=f"EVT-CROWD-{uuid.uuid4().hex[:8].upper()}",
                    event_type="CAMERA_STREAM_DEGRADED",
                    camera_id=metrics.camera_id,
                    camera_code=cam,
                    profile_id=metrics.profile_id,
                    timestamp=now,
                    timestamp_iso=now_iso,
                    severity="WARNING",
                    metrics=metrics_summary,
                    factors=["Stream framerate degraded"],
                    message=f"Camera stream {cam} degraded; crowd analytics may experience reduced fidelity",
                )
                events_generated.append(evt)
        elif stream_health == "FAILED":
            if self._should_fire(cam, "CAMERA_STREAM_LOST", now):
                evt = CrowdAIEvent(
                    event_id=f"EVT-CROWD-{uuid.uuid4().hex[:8].upper()}",
                    event_type="CAMERA_STREAM_LOST",
                    camera_id=metrics.camera_id,
                    camera_code=cam,
                    profile_id=metrics.profile_id,
                    timestamp=now,
                    timestamp_iso=now_iso,
                    severity="HIGH",
                    metrics=metrics_summary,
                    factors=["RTSP connection lost / no frames"],
                    message=f"Camera stream {cam} disconnected; crowd analytics halted",
                )
                events_generated.append(evt)
        elif stream_health == "HEALTHY":
            self._clear_condition_if_recovered(cam, "CAMERA_STREAM_DEGRADED")
            self._clear_condition_if_recovered(cam, "CAMERA_STREAM_LOST")

        # 6. Publish to Event Bus
        for evt in events_generated:
            try:
                await event_bus.publish(
                    channel="crowd",
                    event_type=evt.event_type,
                    payload=evt.model_dump(),
                )
                await event_bus.publish(
                    channel="ai",
                    event_type=evt.event_type,
                    payload=evt.model_dump(),
                )
                logger.info(f"[CrowdEventEngine] Emitted {evt.event_type} on {cam} (Severity: {evt.severity})")
            except Exception as ex:
                logger.warning(f"[CrowdEventEngine] Failed to broadcast event {evt.event_type}: {ex}")

        return events_generated
