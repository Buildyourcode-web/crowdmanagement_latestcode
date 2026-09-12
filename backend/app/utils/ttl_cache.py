import time
import asyncio
from typing import Any, Optional, Callable
from functools import wraps

# Simple in-memory TTL cache — no Redis needed
# Stores: { key: (value, expires_at) }
_cache: dict[str, tuple[Any, float]] = {}


def _make_key(prefix: str, *args, **kwargs) -> str:
    """Build a cache key from prefix + sorted kwargs."""
    parts = [prefix]
    for a in args:
        parts.append(str(a))
    for k, v in sorted(kwargs.items()):
        parts.append(f"{k}={v}")
    return ":".join(parts)


def cache_get(key: str) -> Optional[Any]:
    """Return cached value if not expired, else None."""
    entry = _cache.get(key)
    if entry and time.monotonic() < entry[1]:
        return entry[0]
    if entry:
        del _cache[key]  # expired
    return None


def cache_set(key: str, value: Any, ttl: int = 30) -> None:
    """Store value in cache with TTL seconds."""
    _cache[key] = (value, time.monotonic() + ttl)


def cache_delete(key: str) -> None:
    """Remove a specific key."""
    _cache.pop(key, None)


def cache_clear_prefix(prefix: str) -> None:
    """Remove all keys starting with prefix."""
    to_del = [k for k in _cache if k.startswith(prefix)]
    for k in to_del:
        del _cache[k]


def ttl_cache(prefix: str, ttl: int = 30, key_args: list[str] | None = None):
    """
    Async function decorator — caches the return value for ttl seconds.

    Usage:
        @ttl_cache("crowd:summary", ttl=30)
        async def my_fn(db, ...): ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build key from selected kwargs (or no args by default)
            if key_args:
                key_parts = {k: kwargs.get(k, "") for k in key_args}
            else:
                key_parts = {}
            key = _make_key(prefix, **key_parts)
            cached = cache_get(key)
            if cached is not None:
                return cached
            result = await func(*args, **kwargs)
            cache_set(key, result, ttl)
            return result
        return wrapper
    return decorator
