import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.camera import Camera
from app.models.crowd import CrowdSnapshot
from app.models.alert import Alert


@pytest.mark.asyncio
async def test_camera_listing(client: AsyncClient, db_session: AsyncSession, superadmin_token: str):
    from app.models.event import Event
    ev = (await db_session.execute(select(Event).where(Event.code == "KHB-2026"))).scalars().first()
    cam = Camera(
        camera_code="CAM-KHB-999",
        name="Test Camera 999",
        label="Sector 1 Test Cam",
        camera_type="CROWD",
        zone_code="ZONE-A",
        coordinates=[78.4635, 17.4175],
        status="online",
        ai_status="online",
        is_frs_camera=False,
        is_ptz=False,
        is_active=True,
        event_id=ev.id if ev else None,
    )
    db_session.add(cam)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {superadmin_token}"}
    response = await client.get("/api/v1/cameras", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) >= 1


@pytest.mark.asyncio
async def test_camera_stats(client: AsyncClient, superadmin_token: str):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    response = await client.get("/api/v1/cameras/stats", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "online" in data["data"]


@pytest.mark.asyncio
async def test_delete_camera(client: AsyncClient, db_session: AsyncSession, superadmin_token: str):
    from app.models.event import Event
    ev = (await db_session.execute(select(Event).where(Event.code == "KHB-2026"))).scalars().first()
    cam = Camera(
        camera_code="CAM-KHB-DEL-01",
        name="Test Delete Camera",
        label="Delete Cam Test",
        camera_type="CROWD",
        zone_code="ZONE-A",
        coordinates=[78.4635, 17.4175],
        status="online",
        ai_status="online",
        is_frs_camera=False,
        is_ptz=False,
        is_active=True,
        event_id=ev.id if ev else None,
    )
    db_session.add(cam)
    await db_session.commit()
    await db_session.refresh(cam)

    # Add a CrowdSnapshot referencing this camera to test FK preservation
    snapshot = CrowdSnapshot(
        camera_id=cam.id,
        camera_code=cam.camera_code,
        people_count=42,
        density=0.5,
        inflow_rate=5,
        outflow_rate=2,
        occupancy_percentage=50.0,
        risk_level="LOW",
        event_id=ev.id if ev else None,
    )
    db_session.add(snapshot)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {superadmin_token}"}
    del_res = await client.delete(f"/api/v1/cameras/{cam.camera_code}", headers=headers)
    assert del_res.status_code == 200
    data = del_res.json()
    assert data["success"] is True

    # Confirm it's not in active camera queries (soft-deleted)
    get_res = await client.get(f"/api/v1/cameras/{cam.camera_code}", headers=headers)
    assert get_res.status_code == 404

    # Verify camera record still exists in DB as soft-deleted
    await db_session.refresh(cam)
    assert cam.is_active is False
    assert cam.status == "removed"
    assert cam.removed_at is not None

    # CRITICAL: Verify snapshot STILL references this camera with zero FK nullification
    await db_session.refresh(snapshot)
    assert snapshot.camera_id == cam.id
