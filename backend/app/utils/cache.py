"""
Simple in-process TTL cache for high-latency remote DB (Supabase Sydney).

Every API response for read-heavy data (locations, events, cameras, dashboard)
is stored in memory with a TTL. On the next request within the TTL window the
cached value is returned instantly without hitting the DB (0ms vs 6500ms).

Cache is invalidated explicitly on writes (create / update / delete).
"""

import asyncio
import time
from typing import Any, Callable, Optional
from loguru import logger


class TTLCache:
    """Thread-safe in-process TTL cache."""

    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}   # key → (value, expire_at)
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expire_at = entry
            if time.monotonic() > expire_at:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: Any, ttl: float = 10.0):
        async with self._lock:
            self._store[key] = (value, time.monotonic() + ttl)

    async def delete(self, key: str):
        async with self._lock:
            self._store.pop(key, None)

    async def delete_prefix(self, prefix: str):
        async with self._lock:
            keys_to_delete = [k for k in self._store if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._store[k]

    async def get_or_set(self, key: str, loader: Callable, ttl: float = 10.0) -> Any:
        """Return cached value or call loader(), cache result, and return it."""
        cached = await self.get(key)
        if cached is not None:
            return cached
        value = await loader()
        await self.set(key, value, ttl)
        return value

    def clear(self):
        self._store.clear()


# Global singleton — shared across all requests in the same process
app_cache = TTLCache()
