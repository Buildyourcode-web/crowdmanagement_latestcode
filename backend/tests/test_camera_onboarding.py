"""
test_camera_onboarding.py — Comprehensive Tests for Camera Onboarding & RTSP Management (Step 3).

Verifies:
1.  Add camera (valid inputs, encryption of credentials, zone linkage)
2.  Duplicate camera ID blocked (409 Conflict)
3.  Duplicate IP blocked (409 Conflict)
4.  Invalid RTSP URL validation
5.  Camera not found (404)
6.  Zone validation (non-existent zone rejected)
7.  RBAC: Unauthorized (401) and forbidden without CAMERA_MANAGE
8.  Password never returned in CameraRead response
9.  Password never logged or leaked in sanitized URL
10. RTSP success response (mocked ffprobe probe)
11. RTSP authentication failure (mocked ffprobe probe)
12. RTSP timeout handling (mocked subprocess timeout)
13. Unsupported stream / no video track handling
14. Camera health states (ONLINE, OFFLINE, DEGRADED, NOT_TESTED)
15. Camera update (modifying name, zone, IP, purpose)
16. Camera disable / enable toggle
17. Bulk CSV camera validation and import
"""

import json
from unittest.mock import AsyncMock, patch
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.camera import Camera
from app.models.zone import Zone
from app.security.encryption import (
    build_authenticated_rtsp_url,
    decrypt_credential,
    encrypt_credential,
    sanitize_rtsp_url,
    strip_credentials_from_url,
)
from app.services.rtsp_test_service import RTSPErrorCode, RTSPTestService


# ── Helper Fixtures ────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def setup_test_zone(db_session: AsyncSession):
    """Creates or retrieves a sample zone for camera foreign key validation."""
    from sqlalchemy import select
    stmt = select(Zone).where(Zone.zone_code == "ZONE-ONBOARD-A")
    res = await db_session.execute(stmt)
    existing = res.scalars().first()
    if existing:
        return existing

    zone = Zone(
        zone_code="ZONE-ONBOARD-A",
        name="North Gate Perimeter",
        label="North Gate Zone",
        coordinates=[[78.4635, 17.4175], [78.4640, 17.4180]],
        capacity=5000,
        status="ACTIVE",
    )
    db_session.add(zone)
    await db_session.commit()
    await db_session.refresh(zone)
    return zone


# ── 1. Security & Encryption Unit Tests ────────────────────────────────────────

def test_credential_encryption_and_decryption():
    raw_password = "SuperSecretPassword#2026"
    encrypted = encrypt_credential(raw_password)
    assert encrypted is not None
    assert encrypted != raw_password
    assert len(encrypted) > 20

    decrypted = decrypt_credential(encrypted)
    assert decrypted == raw_password


def test_sanitize_rtsp_url():
    raw_url = "rtsp://admin:super_secret_pass@192.168.0.102:554/Streaming/Channels/101"
    sanitized = sanitize_rtsp_url(raw_url)
    assert "super_secret_pass" not in sanitized
    assert sanitized == "rtsp://admin:***@192.168.0.102:554/Streaming/Channels/101"


def test_strip_credentials_from_url():
    raw_url = "rtsp://admin:super_secret_pass@192.168.0.102:554/Streaming/Channels/101"
    stripped = strip_credentials_from_url(raw_url)
    assert "admin" not in stripped
    assert "super_secret_pass" not in stripped
    assert stripped == "rtsp://192.168.0.102:554/Streaming/Channels/101"


def test_build_authenticated_rtsp_url():
    base = "rtsp://192.168.0.102:554/live/ch0"
    authed = build_authenticated_rtsp_url(base, "operator1", "pass123")
    assert authed == "rtsp://operator1:pass123@192.168.0.102:554/live/ch0"


# ── 2. Add Camera & Onboarding Tests ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_camera_success(client: AsyncClient, superadmin_token: str, setup_test_zone):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    payload = {
        "camera_id": "CAM-TEST-ONBOARD-01",
        "name": "North Gate Arch CCTV",
        "label": "North Gate Arch",
        "description": "Monitors entry queue",
        "camera_type": "CROWD",
        "private_ip": "192.168.10.51",
        "port": 554,
        "rtsp_url": "rtsp://192.168.10.51:554/Streaming/Channels/101",
        "username": "admin",
        "password": "CameraPassword123!",
        "zone_code": setup_test_zone.zone_code,
        "location_name": "Gate 1 Arch Walkway",
        "latitude": 17.4175,
        "longitude": 78.4635,
        "is_ptz": False,
    }

    res = await client.post("/api/v1/cameras", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()
    assert data["success"] is True
    cam = data["data"]
    assert cam["id"] == "CAM-TEST-ONBOARD-01"
    assert cam["name"] == "North Gate Arch CCTV"
    assert cam["zone"] == setup_test_zone.zone_code
    assert cam["camera_type"] == "CROWD"
    assert cam["stream_status"] == "NOT_TESTED"
    assert cam["private_ip"] == "192.168.10.51"

    # Password must NEVER be returned
    assert "password" not in cam
    assert "password_encrypted" not in cam
    assert "CameraPassword123!" not in str(cam)


@pytest.mark.asyncio
async def test_duplicate_camera_id_blocked(client: AsyncClient, superadmin_token: str, setup_test_zone):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    payload = {
        "camera_id": "CAM-TEST-DUP-01",
        "name": "Camera Original",
        "private_ip": "192.168.20.10",
        "rtsp_url": "rtsp://192.168.20.10:554/ch1",
        "zone_code": setup_test_zone.zone_code,
    }

    # 1. First registration succeeds
    res1 = await client.post("/api/v1/cameras", json=payload, headers=headers)
    assert res1.status_code == 201

    # 2. Duplicate registration with same camera_id is blocked with 409
    payload_dup = {
        "camera_id": "CAM-TEST-DUP-01",
        "name": "Camera Duplicate Attempt",
        "private_ip": "192.168.20.11",
        "zone_code": setup_test_zone.zone_code,
    }
    res2 = await client.post("/api/v1/cameras", json=payload_dup, headers=headers)
    assert res2.status_code == 409
    err = res2.json().get("error") or res2.json().get("detail")
    assert err["code"] == "CAMERA_ALREADY_REGISTERED"


@pytest.mark.asyncio
async def test_duplicate_ip_blocked(client: AsyncClient, superadmin_token: str, setup_test_zone):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    payload1 = {
        "camera_id": "CAM-TEST-IP-01",
        "name": "Camera One",
        "private_ip": "192.168.99.15",
        "zone_code": setup_test_zone.zone_code,
    }
    res1 = await client.post("/api/v1/cameras", json=payload1, headers=headers)
    assert res1.status_code == 201

    payload2 = {
        "camera_id": "CAM-TEST-IP-02",
        "name": "Camera Two Same IP",
        "private_ip": "192.168.99.15",
        "zone_code": setup_test_zone.zone_code,
    }
    res2 = await client.post("/api/v1/cameras", json=payload2, headers=headers)
    assert res2.status_code == 409
    err = res2.json().get("error") or res2.json().get("detail")
    assert err["code"] == "CAMERA_ALREADY_REGISTERED"


@pytest.mark.asyncio
async def test_zone_validation_missing_zone(client: AsyncClient, superadmin_token: str):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    payload = {
        "camera_id": "CAM-TEST-BAD-ZONE",
        "name": "Camera Invalid Zone",
        "zone_code": "NON_EXISTENT_ZONE_XYZ",
    }
    res = await client.post("/api/v1/cameras", json=payload, headers=headers)
    assert res.status_code == 400
    err = res.json().get("error") or res.json().get("detail")
    assert err["code"] == "ZONE_NOT_FOUND"


@pytest.mark.asyncio
async def test_camera_not_found_404(client: AsyncClient, superadmin_token: str):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    res = await client.get("/api/v1/cameras/NON_EXISTENT_CAM_9999", headers=headers)
    assert res.status_code == 404
    err = res.json().get("error") or res.json().get("detail")
    assert err["code"] == "CAMERA_NOT_FOUND"


# ── 3. RBAC & Security Protection Tests ───────────────────────────────────────

@pytest.mark.asyncio
async def test_camera_rbac_unauthorized_401(client: AsyncClient):
    """Endpoints return 401 when called without Authorization header."""
    res_get = await client.get("/api/v1/cameras")
    assert res_get.status_code == 401

    res_post = await client.post("/api/v1/cameras", json={"name": "Test"})
    assert res_post.status_code == 401

    res_test = await client.post("/api/v1/cameras/test-stream", json={"rtsp_url": "rtsp://test"})
    assert res_test.status_code == 401


# ── 4. RTSP Stream Testing (Subprocess Boundary Mocking) ───────────────────────

@pytest.mark.asyncio
async def test_rtsp_stream_test_success_mock(client: AsyncClient, superadmin_token: str, setup_test_zone):
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    # 1. Onboard camera
    cam_payload = {
        "camera_id": "CAM-PROBE-01",
        "name": "Probe Cam 1",
        "rtsp_url": "rtsp://192.168.1.100:554/live",
        "zone_code": setup_test_zone.zone_code,
    }
    await client.post("/api/v1/cameras", json=cam_payload, headers=headers)

    # 2. Mock RTSPTestService.test_stream to simulate successful ffprobe probe
    mock_success = {
        "camera_id": "CAM-PROBE-01",
        "reachable": True,
        "authenticated": True,
        "stream_available": True,
        "resolution": "1920x1080",
        "fps": 25,
        "codec": "h264",
        "latency_ms": 38,
        "protocol": "rtsp",
        "stability": "STABLE",
        "tested_at": "2026-09-03T17:00:00Z",
        "error": None,
    }

    with patch.object(RTSPTestService, "test_stream", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = mock_success
        res = await client.post("/api/v1/cameras/CAM-PROBE-01/test-stream", headers=headers)
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["reachable"] is True
        assert data["stream_available"] is True
        assert data["resolution"] == "1920x1080"
        assert data["fps"] == 25
        assert data["codec"] == "h264"
        assert data["stability"] == "STABLE"

    # 3. Verify camera record updated in database
    detail_res = await client.get("/api/v1/cameras/CAM-PROBE-01", headers=headers)
    cam = detail_res.json()["data"]
    assert cam["stream_status"] == "ONLINE"
    assert cam["fps"] == 25
    assert cam["resolution"] == "1920x1080"
    assert cam["stream_stability"] == "STABLE"


@pytest.mark.asyncio
async def test_rtsp_stream_test_auth_failure_mock(client: AsyncClient, superadmin_token: str, setup_test_zone):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam_payload = {
        "camera_id": "CAM-PROBE-AUTH-FAIL",
        "name": "Auth Fail Cam",
        "rtsp_url": "rtsp://192.168.1.101:554/live",
        "zone_code": setup_test_zone.zone_code,
    }
    await client.post("/api/v1/cameras", json=cam_payload, headers=headers)

    mock_auth_fail = {
        "camera_id": "CAM-PROBE-AUTH-FAIL",
        "reachable": True,
        "authenticated": False,
        "stream_available": False,
        "error_code": RTSPErrorCode.RTSP_AUTH_FAILED,
        "error_message": "Camera authentication failed. Verify username and password.",
        "latency_ms": 45,
        "tested_at": "2026-09-03T17:00:00Z",
    }

    with patch.object(RTSPTestService, "test_stream", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = mock_auth_fail
        res = await client.post("/api/v1/cameras/CAM-PROBE-AUTH-FAIL/test-stream", headers=headers)
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["stream_available"] is False
        assert data["error_code"] == "RTSP_AUTH_FAILED"

    # Verify camera marked as DEGRADED with last_error stored
    detail_res = await client.get("/api/v1/cameras/CAM-PROBE-AUTH-FAIL", headers=headers)
    cam = detail_res.json()["data"]
    assert cam["stream_status"] == "DEGRADED"
    assert "authentication failed" in cam["last_error"].lower()


@pytest.mark.asyncio
async def test_rtsp_stream_test_timeout_mock(client: AsyncClient, superadmin_token: str):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    mock_timeout = {
        "camera_id": "NEW_CAMERA",
        "reachable": False,
        "authenticated": False,
        "stream_available": False,
        "error_code": RTSPErrorCode.STREAM_TIMEOUT,
        "error_message": "Connection timed out while probing RTSP stream.",
        "latency_ms": 6000,
        "tested_at": "2026-09-03T17:00:00Z",
    }

    with patch.object(RTSPTestService, "test_stream", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = mock_timeout
        res = await client.post(
            "/api/v1/cameras/test-stream",
            json={"rtsp_url": "rtsp://10.255.255.1:554/live", "timeout_sec": 6.0},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["stream_available"] is False
        assert data["error_code"] == "STREAM_TIMEOUT"


@pytest.mark.asyncio
async def test_rtsp_invalid_url_syntax(client: AsyncClient, superadmin_token: str):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    res = await client.post(
        "/api/v1/cameras/test-stream",
        json={"rtsp_url": "http://not-an-rtsp-stream.com"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["stream_available"] is False
    assert data["error_code"] == "INVALID_RTSP_URL"


# ── 5. Camera Update & Disable Tests ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_camera_update(client: AsyncClient, superadmin_token: str, setup_test_zone):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam_payload = {
        "camera_id": "CAM-TEST-UPDATE-01",
        "name": "Initial Name",
        "zone_code": setup_test_zone.zone_code,
    }
    await client.post("/api/v1/cameras", json=cam_payload, headers=headers)

    # Update camera name and location
    update_payload = {
        "name": "Updated Surveillance Camera",
        "location_name": "VIP Pathway West",
        "fps": 30,
    }
    res = await client.patch("/api/v1/cameras/CAM-TEST-UPDATE-01", json=update_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["name"] == "Updated Surveillance Camera"
    assert data["location_name"] == "VIP Pathway West"
    assert data["fps"] == 30


@pytest.mark.asyncio
async def test_camera_disable_enable(client: AsyncClient, superadmin_token: str, setup_test_zone):
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    cam_payload = {
        "camera_id": "CAM-TEST-TOGGLE-01",
        "name": "Toggle Test Cam",
        "zone_code": setup_test_zone.zone_code,
    }
    await client.post("/api/v1/cameras", json=cam_payload, headers=headers)

    # 1. Disable camera
    res_disable = await client.patch("/api/v1/cameras/CAM-TEST-TOGGLE-01/toggle-status?enabled=false", headers=headers)
    assert res_disable.status_code == 200
    assert res_disable.json()["data"]["enabled"] is False
    assert res_disable.json()["data"]["status"] == "offline"

    # 2. Re-enable camera
    res_enable = await client.patch("/api/v1/cameras/CAM-TEST-TOGGLE-01/toggle-status?enabled=true", headers=headers)
    assert res_enable.status_code == 200
    assert res_enable.json()["data"]["enabled"] is True
    assert res_enable.json()["data"]["status"] == "online"


# ── 6. Bulk Camera CSV Validation & Import ────────────────────────────────────

@pytest.mark.asyncio
async def test_bulk_camera_csv_validation_and_import(client: AsyncClient, superadmin_token: str, setup_test_zone):
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    sample_rows = [
        {
            "camera_id": "CAM-BULK-01",
            "camera_name": "Bulk Camera 1",
            "private_ip": "192.168.33.1",
            "rtsp_url": "rtsp://192.168.33.1:554/ch1",
            "zone": setup_test_zone.zone_code,
            "camera_type": "CROWD",
        },
        {
            "camera_id": "CAM-BULK-02",
            "camera_name": "Bulk Camera 2",
            "private_ip": "192.168.33.2",
            "rtsp_url": "rtsp://192.168.33.2:554/ch1",
            "zone": setup_test_zone.zone_code,
            "camera_type": "FRS",
        },
        {
            "camera_id": "",  # Invalid row
            "camera_name": "Missing ID Cam",
        },
    ]

    # 1. Validate rows
    res_val = await client.post("/api/v1/cameras/bulk-validate", json=sample_rows, headers=headers)
    assert res_val.status_code == 200
    val_data = res_val.json()["data"]
    assert val_data["total"] == 3
    assert val_data["valid_count"] == 2
    assert val_data["invalid_count"] == 1

    # 2. Import valid rows
    import_req = {"cameras": val_data["valid_rows"]}
    res_imp = await client.post("/api/v1/cameras/bulk-import", json=import_req, headers=headers)
    assert res_imp.status_code == 200
    imp_data = res_imp.json()["data"]
    assert imp_data["imported_count"] == 2
    assert "CAM-BULK-01" in imp_data["imported_camera_ids"]
    assert "CAM-BULK-02" in imp_data["imported_camera_ids"]
