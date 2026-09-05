"""
events.py — FRS Event Engine & Temporal Duplicate Suppression.

Manages:
- Structured event generation for candidate matches and system states.
- Temporal suppression of duplicate alerts (same camera + same reference person within 60s).
- Sanitized payload generation (no embeddings, no credentials, no internal paths).
- Dispatch through Redis event bus and WebSocket channels.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger


class FRSEventType:
    FRS_CANDIDATE_MATCH = "FRS_CANDIDATE_MATCH"
    FRS_NO_MATCH = "FRS_NO_MATCH"
    FRS_FACE_QUALITY_LOW = "FRS_FACE_QUALITY_LOW"
    FRS_PIPELINE_DEGRADED = "FRS_PIPELINE_DEGRADED"
    FRS_PIPELINE_FAILED = "FRS_PIPELINE_FAILED"
    FRS_REVIEW_REQUIRED = "FRS_REVIEW_REQUIRED"


@dataclass
class FRSEventPayload:
    event_id: str
    event_type: str
    camera_id: str
    camera_code: str
    zone_id: Optional[str]
    zone_code: Optional[str]
    location: str
    candidate_id: Optional[str]
    reference_id: Optional[str]
    reference_name: Optional[str]
    similarity_score: Optional[float]
    review_status: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "camera_id": self.camera_id,
            "camera_code": self.camera_code,
            "zone_id": self.zone_id,
            "zone_code": self.zone_code,
            "location": self.location,
            "candidate_id": self.candidate_id,
            "reference_id": self.reference_id,
            "reference_name": self.reference_name,
            "similarity_score": self.similarity_score,
            "review_status": self.review_status,
            "timestamp": self.timestamp,
        }


class FRSEventEngine:
    """Event generation engine with duplicate suppression."""

    def __init__(self, suppression_cooldown_seconds: int = 60):
        self.cooldown_seconds = suppression_cooldown_seconds
        # Maps (camera_code, reference_id) -> last_alert_time (epoch float)
        self._suppression_cache: Dict[str, float] = {}

    def is_suppressed(self, camera_code: str, reference_id: str) -> bool:
        """Check if an event for this camera and reference is within the suppression cooldown."""
        key = f"{camera_code}:{reference_id}"
        now = time.time()
        last_time = self._suppression_cache.get(key)
        if last_time and (now - last_time) < self.cooldown_seconds:
            return True
        return False

    def record_match(self, camera_code: str, reference_id: str):
        """Record match alert timestamp to trigger suppression."""
        key = f"{camera_code}:{reference_id}"
        self._suppression_cache[key] = time.time()

    def build_candidate_event(
        self,
        camera_id: str,
        camera_code: str,
        zone_id: Optional[str],
        zone_code: Optional[str],
        location: str,
        candidate_code: str,
        reference_id: str,
        reference_name: str,
        similarity_score: float,
        review_status: str = "REVIEW_REQUIRED",
    ) -> FRSEventPayload:
        """Construct sanitized FRS candidate event payload."""
        event_id = f"EVT-FRS-{uuid.uuid4().hex[:8].upper()}"
        now_iso = datetime.now(timezone.utc).isoformat()

        return FRSEventPayload(
            event_id=event_id,
            event_type=FRSEventType.FRS_REVIEW_REQUIRED,
            camera_id=camera_id,
            camera_code=camera_code,
            zone_id=zone_id,
            zone_code=zone_code,
            location=location,
            candidate_id=candidate_code,
            reference_id=reference_id,
            reference_name=reference_name,
            similarity_score=similarity_score,
            review_status=review_status,
            timestamp=now_iso,
        )

    async def emit_event(self, payload: FRSEventPayload) -> bool:
        """Dispatches sanitized event to Redis event bus and WebSocket."""
        try:
            from app.redis.event_bus import event_bus
            await event_bus.publish(
                channel="byc:frs",
                event_type="frs_candidate",
                payload=payload.to_dict(),
                source="frs_pipeline",
            )
            return True
        except Exception as e:
            logger.debug(f"FRSEventEngine: Redis publish bypassed or failed: {e}")
            return False
