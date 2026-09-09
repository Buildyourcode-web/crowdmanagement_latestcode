import asyncio
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.redis.client import get_redis_connection, _redis_instance
from app.services.crowd_management_service import (
    CrowdManagementService,
    _summary_cache,
    _in_flight_requests,
    _SummaryCacheEntry,
    _CACHE_TTL_SECONDS,
)
from app.schemas.crowd_management import CrowdManagementSummaryResponse


@pytest.mark.asyncio
async def test_redis_offline_cooldown_behavior():
    """Verify that when Redis connection fails, it enters a 60s cooldown and returns None in ~0ms."""
    import app.redis.client as redis_module

    # Reset module state
    redis_module._redis_instance = None
    redis_module._last_failure_time = 0.0

    with patch("app.redis.client.Redis.from_url") as mock_from_url:
        mock_instance = MagicMock()
        mock_instance.ping = AsyncMock(side_effect=ConnectionError("Refused"))
        mock_from_url.return_value = mock_instance

        # 1. First call fails and triggers cooldown
        t0 = time.perf_counter()
        res1 = await get_redis_connection()
        dt1 = (time.perf_counter() - t0) * 1000

        assert res1 is None
        assert redis_module._last_failure_time > 0

        # 2. Second call during cooldown: must return None immediately (0ms) without calling from_url again
        mock_from_url.reset_mock()
        t1 = time.perf_counter()
        res2 = await get_redis_connection()
        dt2 = (time.perf_counter() - t1) * 1000

        assert res2 is None
        assert dt2 < 20.0  # Must be fast (< 20ms)
        mock_from_url.assert_not_called()  # Reconnect skipped during cooldown


@pytest.mark.asyncio
async def test_redis_cooldown_expiration_and_recovery():
    """Verify that after cooldown period, a new connection is attempted and state resets on success."""
    import app.redis.client as redis_module

    # Simulate expired cooldown
    redis_module._redis_instance = None
    redis_module._last_failure_time = time.monotonic() - 70.0  # 70s ago (> 60s)

    with patch("app.redis.client.Redis.from_url") as mock_from_url:
        mock_instance = MagicMock()
        mock_instance.ping = AsyncMock(return_value=True)
        mock_from_url.return_value = mock_instance

        res = await get_redis_connection()
        assert res is not None
        assert redis_module._last_failure_time == 0.0  # Reset
        mock_from_url.assert_called_once()


@pytest.mark.asyncio
async def test_crowd_management_cache_hit_and_coalescing():
    """Verify that identical calls hit in-memory cache and concurrent calls coalesce into a single execution."""
    db_mock = AsyncMock()
    service = CrowdManagementService(db_mock)

    # Clear cache
    _summary_cache.clear()
    _in_flight_requests.clear()

    dummy_payload = {
        "total_people": 150,
        "total_entries": 300,
        "total_exits": 150,
        "net_change": 150,
        "active_cameras": 2,
        "total_cameras": 2,
        "active_queues": 1,
        "high_risk_zones": 0,
        "longest_queue": 15,
        "longest_wait_seconds": 60,
        "overall_risk": "LOW",
        "time_range": "today",
        "timestamp": "2026-09-08T00:00:00Z",
        "queues": [],
        "zones": [],
        "cameras": [],
        "risk_breakdown": {
            "overall_risk": "LOW",
            "risk_score": 15.0,
            "density_contribution": 10.0,
            "inflow": 5,
            "crowd_growth": 5,
            "highest_risk_queue": None,
            "highest_risk_zone": None,
        },
        "high_risk_areas": [],
        "events": [],
        "trends": {"movement": [], "queue_trend": [], "zone_trend": []},
    }
    dummy_resp = CrowdManagementSummaryResponse(**dummy_payload)

    execution_count = 0

    async def fake_uncached(**kwargs):
        nonlocal execution_count
        execution_count += 1
        await asyncio.sleep(0.05)  # Simulate small DB query delay
        return dummy_resp

    with patch.object(service, "_build_summary_uncached", side_effect=fake_uncached):
        # 1. First call (Cold / Miss)
        res1 = await service.get_summary(time_range="today", mode="all")
        assert execution_count == 1
        assert res1.total_people == 150

        # 2. Second call immediately: Cache HIT
        t0 = time.perf_counter()
        res2 = await service.get_summary(time_range="today", mode="all")
        dt2 = (time.perf_counter() - t0) * 1000
        assert execution_count == 1  # Uncached NOT called again!
        assert dt2 < 10.0  # Instantaneous
        assert res2.total_people == 150

        # 3. Concurrent calls coalescing
        _summary_cache.clear()  # Force miss
        execution_count = 0

        res_list = await asyncio.gather(
            service.get_summary(time_range="today", mode="all"),
            service.get_summary(time_range="today", mode="all"),
            service.get_summary(time_range="today", mode="all"),
        )
        assert len(res_list) == 3
        assert execution_count == 1  # Exactly ONE DB call executed across 3 concurrent requests!
        for r in res_list:
            assert r.total_people == 150


@pytest.mark.asyncio
async def test_crowd_management_cache_expiration():
    """Verify that cache entries expire after TTL."""
    db_mock = AsyncMock()
    service = CrowdManagementService(db_mock)

    _summary_cache.clear()
    dummy_resp = CrowdManagementSummaryResponse(
        total_people=200,
        total_entries=400,
        total_exits=200,
        net_change=200,
        active_cameras=1,
        total_cameras=1,
        active_queues=1,
        high_risk_zones=0,
        longest_queue=10,
        longest_wait_seconds=45,
        overall_risk="LOW",
        time_range="today",
        timestamp="2026-09-08T00:00:00Z",
        queues=[],
        zones=[],
        cameras=[],
        risk_breakdown={
            "overall_risk": "LOW",
            "risk_score": 15.0,
            "density_contribution": 10.0,
            "inflow": 5,
            "crowd_growth": 5,
            "highest_risk_queue": None,
            "highest_risk_zone": None,
        },
        high_risk_areas=[],
        events=[],
        trends={"movement": [], "queue_trend": [], "zone_trend": []},
    )

    execution_count = 0

    async def fake_uncached(**kwargs):
        nonlocal execution_count
        execution_count += 1
        return dummy_resp

    with patch.object(service, "_build_summary_uncached", side_effect=fake_uncached):
        # Initial call
        await service.get_summary(time_range="today", mode="all")
        assert execution_count == 1

        # Simulate TTL expiration by backdating expires_at
        key = "today:all:ALL:all"
        _summary_cache[key].expires_at = time.monotonic() - 1.0

        # Next call must be a cache miss and re-run query
        await service.get_summary(time_range="today", mode="all")
        assert execution_count == 2


@pytest.mark.asyncio
async def test_api_response_compatibility():
    """Verify that CrowdManagementSummaryResponse maintains strict schema compatibility."""
    required_fields = {
        "total_people",
        "total_entries",
        "total_exits",
        "net_change",
        "active_cameras",
        "total_cameras",
        "active_queues",
        "high_risk_zones",
        "longest_queue",
        "longest_wait_seconds",
        "overall_risk",
        "time_range",
        "timestamp",
        "queues",
        "zones",
        "cameras",
        "risk_breakdown",
        "high_risk_areas",
        "events",
        "trends",
    }
    schema_fields = set(CrowdManagementSummaryResponse.model_fields.keys())
    assert required_fields.issubset(schema_fields), f"Missing fields: {required_fields - schema_fields}"

    # Verify JSON serialization works without error
    sample = CrowdManagementSummaryResponse(
        total_people=10,
        total_entries=20,
        total_exits=10,
        net_change=10,
        active_cameras=1,
        total_cameras=1,
        active_queues=0,
        high_risk_zones=0,
        longest_queue=0,
        longest_wait_seconds=0,
        overall_risk="LOW",
        time_range="today",
        timestamp="2026-09-08T00:00:00Z",
        queues=[],
        zones=[],
        cameras=[],
        risk_breakdown={
            "overall_risk": "LOW",
            "risk_score": 0.0,
            "density_contribution": 0.0,
            "inflow": 0,
            "crowd_growth": 0,
            "highest_risk_queue": None,
            "highest_risk_zone": None,
        },
        high_risk_areas=[],
        events=[],
        trends={"movement": [], "queue_trend": [], "zone_trend": []},
    )
    json_data = sample.model_dump_json()
    assert "total_people" in json_data
    assert sample.model_dump()["total_people"] == 10


@pytest.mark.asyncio
async def test_concurrent_request_coalescing_error_cleanup():
    """Verify that in-flight request tracking cleans up even if an exception occurs."""
    db_mock = AsyncMock()
    service = CrowdManagementService(db_mock)

    _summary_cache.clear()
    _in_flight_requests.clear()

    async def faulty_uncached(**kwargs):
        await asyncio.sleep(0.02)
        raise RuntimeError("Database connection timed out")

    with patch.object(service, "_build_summary_uncached", side_effect=faulty_uncached):
        key = "today:all:ALL:all"
        results = await asyncio.gather(
            service.get_summary(time_range="today", mode="all"),
            service.get_summary(time_range="today", mode="all"),
            return_exceptions=True,
        )
        assert len(results) == 2
        assert isinstance(results[0], RuntimeError)
        assert isinstance(results[1], RuntimeError)
        # Ensure the in-flight future was cleaned up and doesn't leak
        assert key not in _in_flight_requests

