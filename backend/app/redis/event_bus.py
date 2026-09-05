import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from loguru import logger
from app.redis.client import get_redis_connection


class EventBus:
    """Event Bus for broadcasting events via Redis Pub/Sub to WebSockets and internal consumers."""

    @staticmethod
    async def publish(channel: str, event_type: str, payload: Dict[str, Any], source: str = "system") -> str:
        event_id = str(uuid.uuid4())
        event_message = {
            "event_id": event_id,
            "event_type": event_type,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }

        redis = await get_redis_connection()
        if redis:
            try:
                await redis.publish(channel, json.dumps(event_message))
            except Exception as e:
                logger.error(f"Failed to publish event to Redis channel {channel}: {e}")
        
        # Also notify local WebSocket connection manager
        from app.websocket.manager import ws_manager
        await ws_manager.broadcast_event(event_type, payload)

        return event_id


event_bus = EventBus()
