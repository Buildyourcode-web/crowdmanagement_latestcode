import asyncio
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

        try:
            redis = await asyncio.wait_for(get_redis_connection(), timeout=0.8)
            if redis:
                await asyncio.wait_for(redis.publish(channel, json.dumps(event_message)), timeout=0.8)
        except Exception as e:
            logger.debug(f"EventBus Redis publish bypassed or timed out: {e}")

        # Also notify local WebSocket connection manager
        try:
            from app.websocket.manager import ws_manager
            await ws_manager.broadcast_event(event_type, payload)
        except Exception as ws_err:
            logger.debug(f"EventBus WebSocket broadcast bypassed: {ws_err}")

        return event_id


event_bus = EventBus()
