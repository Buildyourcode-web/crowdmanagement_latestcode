import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.alert import Alert


@pytest.mark.asyncio
async def test_alert_lifecycle(client: AsyncClient, db_session: AsyncSession, superadmin_token: str):
    alert = Alert(
        alert_code="ALT-TEST-01",
        type="crowd_density",
        type_label="CRITICAL DENSITY",
        severity="critical",
        title="Test Density Alert",
        message="Test alert message",
        zone_code="ZONE-A",
        status="active",
        acknowledged=False,
    )
    db_session.add(alert)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {superadmin_token}"}

    # 1. List alerts
    response = await client.get("/api/v1/alerts", headers=headers)
    assert response.status_code == 200
    assert response.json()["success"] is True

    # 2. Acknowledge alert
    ack_res = await client.post(f"/api/v1/alerts/{alert.alert_code}/acknowledge", headers=headers)
    assert ack_res.status_code == 200
    assert ack_res.json()["data"]["acknowledged"] is True
