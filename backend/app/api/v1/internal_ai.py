from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from app.dependencies import verify_ai_service_key
from app.redis.event_bus import event_bus
from app.redis.keys import RedisChannels
from app.schemas.common import StandardResponse
from app.schemas.internal_ai import AIEventIngestRequest, AIEventIngestResponse
from app.utils.response import success_response

router = APIRouter(prefix="/internal/v1/ai", tags=["Internal AI Integration"])


@router.post("/events", response_model=StandardResponse[AIEventIngestResponse])
async def ingest_ai_event(
    event: AIEventIngestRequest,
    is_authenticated: bool = Depends(verify_ai_service_key),
):
    """
    Ingestion contract for external / worker AI inference pipelines (Crowd AI, FRS AI, YOLO).
    Publishes verified events to Redis and active WebSockets.
    """
    channel_map = {
        "CROWD_UPDATE": RedisChannels.CROWD,
        "PERSON_DETECTED": RedisChannels.CROWD,
        "QUEUE_UPDATE": RedisChannels.CROWD,
        "FRS_CANDIDATE": RedisChannels.FRS,
        "PERSON_DOWN": RedisChannels.ALERTS,
        "PANIC_DETECTED": RedisChannels.ALERTS,
        "CAMERA_HEALTH": RedisChannels.CAMERAS,
    }

    target_channel = channel_map.get(event.event_type, RedisChannels.CROWD)

    # Publish to Event Bus
    event_id = await event_bus.publish(
        channel=target_channel,
        event_type=event.event_type.lower(),
        payload=event.payload,
        source=event.source_service,
    )

    response_data = AIEventIngestResponse(
        success=True,
        event_id=event_id,
        processed_at=datetime.now(timezone.utc),
        published_channels=[target_channel],
    )
    return success_response(response_data)
