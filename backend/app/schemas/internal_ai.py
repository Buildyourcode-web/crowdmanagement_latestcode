import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field


class AIEventIngestRequest(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = Field(
        ...,
        example="CROWD_UPDATE",
        description="PERSON_DETECTED, CROWD_UPDATE, QUEUE_UPDATE, PERSON_DOWN, PANIC_DETECTED, FRS_CANDIDATE, CAMERA_HEALTH",
    )
    source_service: str = Field(..., example="crowd_ai_worker_01")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    camera_code: Optional[str] = Field(None, example="CAM-KHB-007")
    zone_code: Optional[str] = Field(None, example="ZONE-A")
    payload: dict = Field(..., example={"people_count": 182, "density": 4.2, "inflow": 45, "outflow": 38})


class AIEventIngestResponse(BaseModel):
    success: bool = True
    event_id: str
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_channels: list[str] = Field(default_factory=list)
