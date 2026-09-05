import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_me_unauthorized(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "NOT_AUTHENTICATED"


@pytest.mark.asyncio
async def test_auth_me_authorized(client: AsyncClient, superadmin_token: str):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["username"] == "testadmin"
    assert data["data"]["role"] == "SUPER_ADMIN"


@pytest.mark.asyncio
async def test_auth_login_invalid(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "nonexistent", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INVALID_CREDENTIALS"
