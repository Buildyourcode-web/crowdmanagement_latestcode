import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.camera import Camera


@pytest.mark.asyncio
async def test_camera_listing(client: AsyncClient, db_session: AsyncSession, superadmin_token: str):
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
