import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.frs import FRSCandidate, FRSReferenceProfile


@pytest.mark.asyncio
async def test_frs_dashboard(client: AsyncClient, superadmin_token: str):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    response = await client.get("/api/v1/frs/dashboard", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "camerasOnline" in data["data"]
    assert "detectionsToday" in data["data"]


@pytest.mark.asyncio
async def test_frs_candidate_review_workflow(client: AsyncClient, db_session: AsyncSession, superadmin_token: str):
    # Setup reference profile and candidate
    profile = FRSReferenceProfile(
        reference_id="WL-TEST-01",
        display_name="Test Person",
        category="Authorized Watchlist",
        status="ACTIVE",
        reference_image_path="/media/frs/reference/test.jpg",
        last_updated_date="10 Sep 2026",
    )
    db_session.add(profile)
    await db_session.flush()

    candidate = FRSCandidate(
        candidate_code="FRS-TEST-999",
        camera_code="FRS-KHB-007",
        camera_name="Test FRS Cam",
        zone_code="ZONE-A",
        location="North Gate",
        reference_profile_id=profile.id,
        detected_image_path="/media/frs/detected/test.jpg",
        match_score=92.5,
        status="PENDING_REVIEW",
        review_required=True,
    )
    db_session.add(candidate)
    await db_session.commit()

    headers = {"Authorization": f"Bearer {superadmin_token}"}

    # Review Candidate
    review_payload = {
        "decision": "POSSIBLE_MATCH",
        "notes": "Verified facial markers match reference profile.",
    }
    response = await client.post(
        f"/api/v1/frs/candidates/{candidate.candidate_code}/review",
        json=review_payload,
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["status"] in ("CONFIRMED_BY_REVIEWER", "POSSIBLE_MATCH")
    assert data["data"]["review_required"] is False
