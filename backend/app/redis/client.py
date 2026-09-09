import json
from typing import Any, Optional
from loguru import logger
from redis.asyncio import Redis
from app.config import settings

import time

_redis_instance: Optional[Redis] = None
_last_failure_time: float = 0.0
_COOLDOWN_SECONDS: float = 60.0


async def get_redis_connection() -> Optional[Redis]:
    """Gets or initializes the global async Redis connection with offline cooldown."""
    global _redis_instance, _last_failure_time
    if _redis_instance is not None:
        return _redis_instance

    now = time.monotonic()
    if _last_failure_time > 0 and (now - _last_failure_time) < _COOLDOWN_SECONDS:
        remaining = round(_COOLDOWN_SECONDS - (now - _last_failure_time), 1)
        logger.debug(f"[REDIS_COOLDOWN_ACTIVE] Skipping reconnect attempt, cooldown remaining: {remaining}s")
        return None

    try:
        instance = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        await instance.ping()
        _redis_instance = instance
        _last_failure_time = 0.0
        logger.info("[REDIS_RECONNECTED] Connected to Redis successfully")
        return _redis_instance
    except Exception as e:
        _last_failure_time = time.monotonic()
        _redis_instance = None
        # Safe logging without exposing secrets or connection URLs
        error_type = type(e).__name__
        logger.warning(
            f"[REDIS_CONNECTION_FAILED] ({error_type}). Entering {_COOLDOWN_SECONDS}s cooldown. "
            "Continuing in standalone fallback mode."
        )
        return None


async def close_redis_connection():
    global _redis_instance
    if _redis_instance:
        await _redis_instance.close()
        _redis_instance = None
        logger.info("Closed Redis connection")
