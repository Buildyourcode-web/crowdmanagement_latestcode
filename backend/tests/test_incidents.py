import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.incident import Incident


@pytest.mark.asyncio
async def test_incident_lifecycle(client: AsyncClient, db_session: AsyncSession, superadmin_token: str):
    inc = Incident(
        incident_code="INC-TEST-01",
        type="crowd_surge",
        type_label="Crowd Surge",
        severity="critical",
        title="Test Surge Incident",
        description="Surge near gate 1",
        location="Gate 1 Approach",
        zone_code="ZONE-A",
        status="detected",
    )
    db_session.add(inc)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {superadmin_token}"}

    # 1. Acknowledge
    ack_res = await client.post(f"/api/v1/incidents/{inc.incident_code}/acknowledge", headers=headers)
    assert ack_res.status_code == 200
    assert ack_res.json()["data"]["status"] == "acknowledged"

    # 2. Assign team
    assign_res = await client.post(
        f"/api/v1/incidents/{inc.incident_code}/assign",
        json={"assigned_team": "UNIT-01", "assigned_team_label": "QRT Unit 1"},
        headers=headers,
    )
    assert assign_res.status_code == 200
    assert assign_res.json()["data"]["status"] == "assigned"
    assert assign_res.json()["data"]["assignedTeam"] == "UNIT-01"

    # 3. Add note
    note_res = await client.post(
        f"/api/v1/incidents/{inc.incident_code}/notes",
        json={"author": "Test Officer", "text": "Field unit arrived on site."},
        headers=headers,
    )
    assert note_res.status_code == 200
    assert note_res.json()["data"]["text"] == "Field unit arrived on site."
