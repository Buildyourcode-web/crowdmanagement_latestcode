import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.zone import Zone
from app.models.camera import Camera


@pytest.mark.asyncio
async def test_get_crowd_management_summary(client: AsyncClient, db_session: AsyncSession, superadmin_token: str):
    """Verifies that /api/v1/crowd-management/summary returns the consolidated structure."""
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    response = await client.get("/api/v1/crowd-management/summary", headers=headers)
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["success"] is True
    data = res_json["data"]

    # Verify top-level KPI fields
    assert "total_people" in data
    assert "total_entries" in data
    assert "total_exits" in data
    assert "net_change" in data
    assert data["net_change"] == data["total_entries"] - data["total_exits"]

    # Verify secondary status indicators
    assert "active_cameras" in data
    assert "total_cameras" in data
    assert "active_queues" in data
    assert "high_risk_zones" in data
    assert "longest_queue" in data
    assert "longest_wait_seconds" in data
    assert "overall_risk" in data

    # Verify sub-sections
    assert isinstance(data["queues"], list)
    assert isinstance(data["zones"], list)
    assert isinstance(data["cameras"], list)
    assert isinstance(data["risk_breakdown"], dict)
    assert isinstance(data["high_risk_areas"], list)
    assert isinstance(data["events"], list)
    assert isinstance(data["trends"], dict)

    # Verify trend structures
    trends = data["trends"]
    assert "movement" in trends
    assert "queue_trend" in trends
    assert "zone_trend" in trends


@pytest.mark.asyncio
async def test_crowd_management_filters(client: AsyncClient, superadmin_token: str):
    """Verifies time_range, mode, and risk_level query filters."""
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    # 1. Mode filter = queue
    res_queue = await client.get("/api/v1/crowd-management/summary?mode=queue", headers=headers)
    assert res_queue.status_code == 200
    assert len(res_queue.json()["data"]["zones"]) == 0

    # 2. Mode filter = zone
    res_zone = await client.get("/api/v1/crowd-management/summary?mode=zone", headers=headers)
    assert res_zone.status_code == 200
    assert len(res_zone.json()["data"]["queues"]) == 0

    # 3. Time filter = 15m
    res_15m = await client.get("/api/v1/crowd-management/summary?time_range=15m", headers=headers)
    assert res_15m.status_code == 200
    assert res_15m.json()["data"]["time_range"] == "15m"

    # 4. Time filter = 1h
    res_1h = await client.get("/api/v1/crowd-management/summary?time_range=1h", headers=headers)
    assert res_1h.status_code == 200
    assert res_1h.json()["data"]["time_range"] == "1h"

    # 5. Risk filter
    res_risk = await client.get("/api/v1/crowd-management/summary?risk_level=critical", headers=headers)
    assert res_risk.status_code == 200


@pytest.mark.asyncio
async def test_crowd_management_invalid_token(client: AsyncClient):
    """Verifies requests with invalid tokens are blocked with 401."""
    response = await client.get("/api/v1/crowd-management/summary", headers={"Authorization": "Bearer invalid.token.payload"})
    assert response.status_code == 401
