"""
health.py — AI Runtime Health Inspector.

Provides real-time health and telemetry inspection for AI runtime environment.
"""

from typing import Any, Dict
from app.ai.runtime.detector import RuntimeDetector


class RuntimeHealthChecker:
    """Evaluates readiness of database, redis, and computational resources."""

    @staticmethod
    async def check_database() -> Dict[str, Any]:
        """Checks PostgreSQL connectivity and response latency."""
        return await RuntimeDetector.check_database_readiness()

    @staticmethod
    async def check_redis() -> Dict[str, Any]:
        """Checks Redis connectivity."""
        return await RuntimeDetector.check_redis_readiness()

    @classmethod
    async def get_runtime_health(cls) -> Dict[str, Any]:
        """Consolidates health status across all runtime components."""
        caps = await RuntimeDetector.get_full_capabilities()
        db_ready = caps["database"].get("postgresql", False)
        overall = "HEALTHY" if db_ready else "DEGRADED"

        return {
            "overall_status": overall,
            "readiness": caps["readiness"]["readiness"],
            "database": caps["database"],
            "redis": caps["redis"],
            "gpu": caps["gpu"],
            "memory": caps["memory"],
            "cpu": caps["cpu"],
            "server": caps["server"],
        }
