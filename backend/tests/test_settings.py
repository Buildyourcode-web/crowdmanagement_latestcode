"""
Backend tests for Settings API endpoints.
Uses the existing conftest.py with superadmin_token and SQLite in-memory session.
"""
import pytest
from httpx import AsyncClient


# ── Alert Thresholds ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_alert_thresholds_unauthorized(client: AsyncClient):
    """GET /settings/alerts without token → 401."""
    resp = await client.get("/api/v1/settings/alerts")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_alert_thresholds_authorized(client: AsyncClient, superadmin_token: str):
    """GET /settings/alerts with valid token → 200 with threshold fields."""
    resp = await client.get("/api/v1/settings/alerts", headers={"Authorization": f"Bearer {superadmin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "crowd_warning_pct" in data
    assert "crowd_critical_pct" in data
    assert "panic_risk_score" in data


@pytest.mark.asyncio
async def test_update_alert_thresholds(client: AsyncClient, superadmin_token: str):
    """PATCH /settings/alerts with valid values → 200, values persisted."""
    payload = {"crowd_warning_pct": 75.0, "crowd_high_pct": 85.0, "crowd_critical_pct": 95.0}
    resp = await client.patch(
        "/api/v1/settings/alerts",
        json=payload,
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["crowd_warning_pct"] == 75.0
    assert data["crowd_critical_pct"] == 95.0
    assert data["config_version"] >= 1


@pytest.mark.asyncio
async def test_update_alert_thresholds_invalid_order(client: AsyncClient, superadmin_token: str):
    """PATCH /settings/alerts where high <= warning → 422."""
    payload = {"crowd_warning_pct": 90.0, "crowd_high_pct": 80.0}
    resp = await client.patch(
        "/api/v1/settings/alerts",
        json=payload,
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reset_alert_thresholds(client: AsyncClient, superadmin_token: str):
    """POST /settings/alerts/reset → 200 with default values."""
    resp = await client.post(
        "/api/v1/settings/alerts/reset",
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["crowd_warning_pct"] == 80.0
    assert data["crowd_critical_pct"] == 100.0


# ── AI Config ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_ai_config(client: AsyncClient, superadmin_token: str):
    """GET /settings/ai → 200 with detection fields."""
    resp = await client.get("/api/v1/settings/ai", headers={"Authorization": f"Bearer {superadmin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "crowd_detection_enabled" in data
    assert "detection_confidence" in data
    assert "processing_fps" in data


@pytest.mark.asyncio
async def test_update_ai_config(client: AsyncClient, superadmin_token: str):
    """PATCH /settings/ai → 200, values updated."""
    resp = await client.patch(
        "/api/v1/settings/ai",
        json={"detection_confidence": 0.65, "processing_fps": 15},
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["detection_confidence"] == 0.65
    assert data["processing_fps"] == 15


@pytest.mark.asyncio
async def test_update_ai_config_invalid_confidence(client: AsyncClient, superadmin_token: str):
    """PATCH /settings/ai with confidence > 1.0 → 422."""
    resp = await client.patch(
        "/api/v1/settings/ai",
        json={"detection_confidence": 1.5},
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert resp.status_code == 422


# ── FRS Config ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_frs_config(client: AsyncClient, superadmin_token: str):
    """GET /settings/frs → 200, human_review_required is always True."""
    resp = await client.get("/api/v1/settings/frs", headers={"Authorization": f"Bearer {superadmin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["human_review_required"] is True
    assert data["auto_confirmation_enabled"] is False
    assert "match_threshold" in data
    assert "candidate_threshold" in data


@pytest.mark.asyncio
async def test_update_frs_config_valid(client: AsyncClient, superadmin_token: str):
    """PATCH /settings/frs with valid thresholds → 200."""
    resp = await client.patch(
        "/api/v1/settings/frs",
        json={"match_threshold": 0.95, "candidate_threshold": 0.80},
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["match_threshold"] == 0.95
    assert data["candidate_threshold"] == 0.80
    # Safety invariants must hold
    assert data["human_review_required"] is True
    assert data["auto_confirmation_enabled"] is False


@pytest.mark.asyncio
async def test_update_frs_config_invalid_threshold(client: AsyncClient, superadmin_token: str):
    """PATCH /settings/frs where candidate > match → 422."""
    resp = await client.patch(
        "/api/v1/settings/frs",
        json={"match_threshold": 0.80, "candidate_threshold": 0.90},
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_frs_human_review_cannot_be_disabled(client: AsyncClient, superadmin_token: str):
    """PATCH /settings/frs with human_review_required=false → still True in response."""
    resp = await client.patch(
        "/api/v1/settings/frs",
        json={"human_review_required": False},
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    # Either the API silently ignores this field or succeeds; human_review must remain True
    if resp.status_code == 200:
        data = resp.json()
        assert data["human_review_required"] is True


# ── Notification Config ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_notification_config(client: AsyncClient, superadmin_token: str):
    """GET /settings/notifications → 200 with channel fields."""
    resp = await client.get("/api/v1/settings/notifications", headers={"Authorization": f"Bearer {superadmin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "inapp_enabled" in data
    assert "websocket_enabled" in data


@pytest.mark.asyncio
async def test_update_notification_config(client: AsyncClient, superadmin_token: str):
    """PATCH /settings/notifications → 200."""
    resp = await client.patch(
        "/api/v1/settings/notifications",
        json={"sms_enabled": True, "email_enabled": False},
        headers={"Authorization": f"Bearer {superadmin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sms_enabled"] is True
    assert data["email_enabled"] is False


# ── System Config ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_system_config(client: AsyncClient, superadmin_token: str):
    """GET /settings/system → 200 with app fields."""
    resp = await client.get("/api/v1/settings/system", headers={"Authorization": f"Bearer {superadmin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "app_name" in data
    assert "maintenance_mode" in data
    assert "environment" in data


# ── Role Settings ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_roles(client: AsyncClient, superadmin_token: str):
    """GET /settings/roles → 200, list of roles."""
    resp = await client.get("/api/v1/settings/roles", headers={"Authorization": f"Bearer {superadmin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    codes = [r["code"] for r in data]
    assert "SUPER_ADMIN" in codes


@pytest.mark.asyncio
async def test_get_permissions(client: AsyncClient, superadmin_token: str):
    """GET /settings/permissions → 200, list of permissions."""
    resp = await client.get("/api/v1/settings/permissions", headers={"Authorization": f"Bearer {superadmin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ── Camera — no RTSP exposure ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_camera_list_no_rtsp_exposure(client: AsyncClient, superadmin_token: str):
    """GET /settings/cameras → 200, no rtsp_url_encrypted field exposed."""
    resp = await client.get("/api/v1/settings/cameras", headers={"Authorization": f"Bearer {superadmin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    if isinstance(data, list) and data:
        first = data[0]
        assert "rtsp_url_encrypted" not in first
        assert "rtsp_url" not in first
        # Only has_rtsp_configured bool
        assert "has_rtsp_configured" in first


# ── Settings summary ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_settings_summary(client: AsyncClient, superadmin_token: str):
    """GET /settings → 200 with summary."""
    resp = await client.get("/api/v1/settings", headers={"Authorization": f"Bearer {superadmin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "config_versions" in data


# ── Audit log ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_settings_audit(client: AsyncClient, superadmin_token: str):
    """GET /settings/audit → 200, list (may be empty on fresh DB)."""
    resp = await client.get("/api/v1/settings/audit", headers={"Authorization": f"Bearer {superadmin_token}"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
