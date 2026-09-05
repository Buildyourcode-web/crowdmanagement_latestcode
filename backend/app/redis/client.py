import json
from typing import Any, Optional
from loguru import logger
from redis.asyncio import Redis
from app.config import settings

_redis_instance: Optional[Redis] = None


async def get_redis_connection() -> Optional[Redis]:
    """Gets or initializes the global async Redis connection."""
    global _redis_instance
    if _redis_instance is None:
        try:
            _redis_instance = Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_timeout=3.0,
            )
            # Ping to verify
            await _redis_instance.ping()
            logger.info("Connected to Redis successfully")
        except Exception as e:
            logger.warning(f"Redis connection unavailable ({e}). Continuing in standalone fallback mode.")
            _redis_instance = None
    return _redis_instance


async def close_redis_connection():
    global _redis_instance
    if _redis_instance:
        await _redis_instance.close()
        _redis_instance = None
        logger.info("Closed Redis connection")
