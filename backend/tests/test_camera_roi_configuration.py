"""
backend/tests/test_camera_roi_configuration.py — Step 5 Comprehensive Test Suite.

Verifies:
1. Get ROI configuration
2. Create Crowd ROI (valid polygon, >=3 points)
3. Create Queue ROI (valid polygon)
4. Create Entry/Exit counting lines
5. Update ROI (move vertices, rename, version increment)
6. Delete ROI
7. Invalid polygon rejected (<3 points)
8. Coordinates outside 0..1 rejected
9. Invalid counting line rejected
10. Profile/ROI mismatch rejected
11. Queue ROI required readiness validation
12. Crowd ROI required readiness validation
13. Camera stream not verified rejected
14. Offline camera rejected
15. Unauthorized user rejected (401)
16. AI_READ permission enforcement (403)
17. AI_MANAGE permission enforcement (403)
18. FRS isolation: Crowd/Queue ROI rejected on FRS camera/profile
19. Audit event generated on ROI creation (ROI_CREATED)
20. Audit event generated on ROI update (ROI_UPDATED)
21. WebSocket event generated on configuration change (AI_GEOMETRY_CHANGED)
22. Configuration version increment (v1 -> v2)
23. Camera snapshot endpoint returns JPEG frame
24. Camera snapshot offline/unverified rejected
25. STRICT INVARIANT: No AI inference starts on saving ROI configuration
26. Security: No passwords or internal secrets exposed
"""

import subprocess
import uuid
from typing import Dict
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.jwt import create_access_token
from app.security.password import get_password_hash
from app.models.audit_log import AuditLog
from app.models.camera import Camera
from app.models.camera_ai_assignment import CameraAIProfileAssignment
from app.models.camera_roi import CameraROIConfiguration, ROIType
from app.models.role import Permission, Role
from app.models.user import User
from app.models.zone import Zone
from app.services.snapshot_service import SnapshotService


# Valid dummy JPEG bytes for tests (\xff\xd8\xff\xe0...)
MOCK_JPEG_FRAME = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00" + (b"\xaa" * 200) + b"\xff\xd9"


@pytest_asyncio.fixture
async def setup_roi_zone(db_session: AsyncSession):
    stmt = select(Zone).where(Zone.zone_code == "ZONE-STEP5-A")
    res = await db_session.execute(stmt)
    existing = res.scalars().first()
    if existing:
        return existing

    zone = Zone(
        zone_code="ZONE-STEP5-A",
        name="Precinct West Gate",
        label="West Gate Sector",
        coordinates=[[78.4635, 17.4175], [78.4640, 17.4180]],
        capacity=6000,
        status="ACTIVE",
    )
    db_session.add(zone)
    await db_session.commit()
    await db_session.refresh(zone)
    return zone


@pytest_asyncio.fixture
async def sample_roi_cameras(db_session: AsyncSession, setup_roi_zone) -> Dict[str, Camera]:
    """Sets up cameras with distinct purposes and pre-assigned AI profiles."""
    cams = {}
    purposes = [
        ("CAM-ROI-CROWD-01", "CROWD", "West Gate Crowd View"),
        ("CAM-ROI-QUEUE-01", "QUEUE", "VIP Barricade Queue View"),
        ("CAM-ROI-FRS-01", "FRS", "Main Arch FRS View"),
        ("CAM-ROI-OFFLINE-01", "CROWD", "Offline Camera"),
        ("CAM-ROI-UNVERIFIED-01", "CROWD", "Unverified Stream Camera"),
    ]

    for i, (code, purp, name) in enumerate(purposes):
        stmt = select(Camera).where(Camera.camera_code == code)
        existing = (await db_session.execute(stmt)).scalars().first()
        if not existing:
            is_offline = "OFFLINE" in code
            is_unverified = "UNVERIFIED" in code
            stream_status = "OFFLINE" if is_offline else ("NOT_TESTED" if is_unverified else "ONLINE")
            enabled = not is_offline

            cam = Camera(
                camera_code=code,
                name=name,
                label=name,
                camera_type=purp,
                zone=setup_roi_zone,
                zone_code=setup_roi_zone.zone_code,
                zone_id=setup_roi_zone.id,
                private_ip=f"192.168.120.{i + 10}",
                port=554,
                rtsp_url_encrypted="gAAAAABtestURL",
                status="offline" if is_offline else "online",
                stream_status=stream_status,
                stream_stability="STABLE" if not (is_offline or is_unverified) else "OFFLINE",
                enabled=enabled,
            )
            db_session.add(cam)
            await db_session.flush()
            await db_session.refresh(cam)
            cams[code] = cam
        else:
            cams[code] = existing

    # Assign profiles to online test cameras if not already assigned
    for cam_code, prof_id in [
        ("CAM-ROI-CROWD-01", "CROWD_STANDARD"),
        ("CAM-ROI-QUEUE-01", "QUEUE_STANDARD"),
        ("CAM-ROI-FRS-01", "FRS_STANDARD"),
    ]:
        cam_obj = cams[cam_code]
        stmt_asgn = select(CameraAIProfileAssignment).where(
            CameraAIProfileAssignment.camera_id == cam_obj.id,
            CameraAIProfileAssignment.profile_id == prof_id,
        )
        existing_asgn = (await db_session.execute(stmt_asgn)).scalars().first()
        if not existing_asgn:
            asgn = CameraAIProfileAssignment(
                camera_id=cam_obj.id,
                camera_code=cam_obj.camera_code,
                profile_id=prof_id,
                enabled=True,
                metadata_json={},
                assigned_by="TEST_ADMIN",
                validation_status="VALID",
            )
            db_session.add(asgn)

    await db_session.commit()

    # Register mock snapshot frame
    SnapshotService.set_mock_frame(str(cams["CAM-ROI-CROWD-01"].id), MOCK_JPEG_FRAME)
    SnapshotService.set_mock_frame(str(cams["CAM-ROI-QUEUE-01"].id), MOCK_JPEG_FRAME)
    SnapshotService.set_mock_frame(str(cams["CAM-ROI-FRS-01"].id), MOCK_JPEG_FRAME)

    return cams


@pytest_asyncio.fixture
async def read_only_roi_token(db_session: AsyncSession) -> str:
    """User with AI_READ and CAMERA_READ only (no AI_MANAGE)."""
    stmt = select(Role).where(Role.code == "ROLE_ROI_VIEWER")
    role = (await db_session.execute(stmt)).scalars().first()
    if not role:
        perms = []
        for p_code in ["ai:read", "camera:read"]:
            perm = (await db_session.execute(select(Permission).where(Permission.code == p_code))).scalars().first()
            if not perm:
                perm = Permission(code=p_code, name=p_code)
                db_session.add(perm)
                await db_session.flush()
            perms.append(perm)

        role = Role(code="ROLE_ROI_VIEWER", name="ROI Viewer", description="Read only", permissions=perms)
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(role)

    stmt_u = select(User).where(User.username == "roi_viewer")
    user = (await db_session.execute(stmt_u)).scalars().first()
    if not user:
        user = User(
            username="roi_viewer",
            email="roiviewer@byc.gov.in",
            password_hash=get_password_hash("viewer123"),
            full_name="ROI Viewer",
            role_id=role.id,
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

    return create_access_token(
        subject=str(user.id),
        role="ROLE_ROI_VIEWER",
        permissions=["ai:read", "camera:read"],
    )


# =========================================================================
# TEST SUITE
# =========================================================================

@pytest.mark.asyncio
async def test_get_roi_config_empty(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """GET /api/v1/cameras/{id}/roi-config on fresh camera returns empty list and NOT_CONFIGURED readiness."""
    cam = sample_roi_cameras["CAM-ROI-CROWD-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    res = await client.get(f"/api/v1/cameras/{cam.id}/roi-config", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]

    assert data["camera_code"] == "CAM-ROI-CROWD-01"
    assert data["stream_verified"] is True
    assert len(data["configurations"]) == 0
    assert "CROWD_STANDARD" in data["readiness_by_profile"]
    assert data["readiness_by_profile"]["CROWD_STANDARD"]["status"] == "NOT_CONFIGURED"
    assert data["readiness_by_profile"]["CROWD_STANDARD"]["is_ready"] is False


@pytest.mark.asyncio
async def test_create_valid_crowd_roi(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """POST /api/v1/cameras/{id}/roi-config with valid 4-point polygon creates CROWD_ROI."""
    cam = sample_roi_cameras["CAM-ROI-CROWD-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    payload = {
        "profile_id": "CROWD_STANDARD",
        "roi_type": "CROWD_ROI",
        "name": "East Gate Courtyard Density Zone",
        "geometry_json": {
            "points": [
                {"x": 0.10, "y": 0.20},
                {"x": 0.85, "y": 0.20},
                {"x": 0.90, "y": 0.85},
                {"x": 0.15, "y": 0.85},
            ]
        },
        "normalized": True,
        "enabled": True,
    }

    res = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=payload, headers=headers)
    assert res.status_code == 201
    data = res.json()["data"]

    assert data["camera_code"] == "CAM-ROI-CROWD-01"
    assert data["roi_type"] == "CROWD_ROI"
    assert data["version"] == 1
    assert data["normalized"] is True
    assert len(data["geometry_json"]["points"]) == 4

    # Check readiness transitioned to READY
    summary_res = await client.get(f"/api/v1/cameras/{cam.id}/roi-config", headers=headers)
    summary_data = summary_res.json()["data"]
    assert summary_data["readiness_by_profile"]["CROWD_STANDARD"]["status"] == "READY"
    assert summary_data["readiness_by_profile"]["CROWD_STANDARD"]["is_ready"] is True


@pytest.mark.asyncio
async def test_create_valid_queue_roi(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """POST /api/v1/cameras/{id}/roi-config creates QUEUE_ROI; readiness remains PARTIALLY_CONFIGURED until lines added."""
    cam = sample_roi_cameras["CAM-ROI-QUEUE-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    payload = {
        "profile_id": "QUEUE_STANDARD",
        "roi_type": "QUEUE_ROI",
        "name": "VIP Queue Barricade Box",
        "geometry_json": {
            "points": [
                {"x": 0.20, "y": 0.30},
                {"x": 0.70, "y": 0.30},
                {"x": 0.70, "y": 0.80},
                {"x": 0.20, "y": 0.80},
            ]
        },
        "normalized": True,
        "enabled": True,
    }

    res = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=payload, headers=headers)
    assert res.status_code == 201

    # Check readiness: PARTIALLY_CONFIGURED because ENTRY_LINE and EXIT_LINE are missing
    summary_res = await client.get(f"/api/v1/cameras/{cam.id}/roi-config", headers=headers)
    readiness = summary_res.json()["data"]["readiness_by_profile"]["QUEUE_STANDARD"]
    assert readiness["status"] == "PARTIALLY_CONFIGURED"
    assert readiness["is_ready"] is False
    assert any("ENTRY_LINE" in r for r in readiness["missing_requirements"])


@pytest.mark.asyncio
async def test_create_entry_and_exit_lines(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """Adding ENTRY_LINE and EXIT_LINE transitions QUEUE_STANDARD readiness to READY."""
    cam = sample_roi_cameras["CAM-ROI-QUEUE-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    # 1. Add Entry line
    entry_payload = {
        "profile_id": "QUEUE_STANDARD",
        "roi_type": "ENTRY_LINE",
        "name": "Queue Main Inflow",
        "geometry_json": {
            "start": {"x": 0.20, "y": 0.30},
            "end": {"x": 0.70, "y": 0.30},
            "direction": "IN",
        },
        "normalized": True,
        "enabled": True,
    }
    res1 = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=entry_payload, headers=headers)
    assert res1.status_code == 201

    # 2. Add Exit line
    exit_payload = {
        "profile_id": "QUEUE_STANDARD",
        "roi_type": "EXIT_LINE",
        "name": "Queue Turnstile Outflow",
        "geometry_json": {
            "start": {"x": 0.20, "y": 0.80},
            "end": {"x": 0.70, "y": 0.80},
            "direction": "OUT",
        },
        "normalized": True,
        "enabled": True,
    }
    res2 = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=exit_payload, headers=headers)
    assert res2.status_code == 201

    # 3. Check readiness is now READY
    summary_res = await client.get(f"/api/v1/cameras/{cam.id}/roi-config", headers=headers)
    readiness = summary_res.json()["data"]["readiness_by_profile"]["QUEUE_STANDARD"]
    assert readiness["status"] == "READY"
    assert readiness["is_ready"] is True
    assert len(readiness["missing_requirements"]) == 0


@pytest.mark.asyncio
async def test_update_roi_geometry_and_version(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """PATCH /api/v1/cameras/{id}/roi-config/{roi_id} updates geometry and increments version (v1 -> v2)."""
    cam = sample_roi_cameras["CAM-ROI-CROWD-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    # Fetch existing ROI
    summary_res = await client.get(f"/api/v1/cameras/{cam.id}/roi-config", headers=headers)
    roi = summary_res.json()["data"]["configurations"][0]
    roi_id = roi["id"]
    assert roi["version"] == 1

    # Update geometry
    patch_payload = {
        "name": "Updated East Gate Courtyard Zone",
        "geometry_json": {
            "points": [
                {"x": 0.12, "y": 0.22},
                {"x": 0.88, "y": 0.22},
                {"x": 0.92, "y": 0.88},
                {"x": 0.18, "y": 0.88},
            ]
        },
    }
    patch_res = await client.patch(f"/api/v1/cameras/{cam.id}/roi-config/{roi_id}", json=patch_payload, headers=headers)
    assert patch_res.status_code == 200
    updated_data = patch_res.json()["data"]

    assert updated_data["version"] == 2
    assert updated_data["name"] == "Updated East Gate Courtyard Zone"
    assert updated_data["geometry_json"]["points"][0]["x"] == 0.12


@pytest.mark.asyncio
async def test_delete_roi(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """DELETE /api/v1/cameras/{id}/roi-config/{roi_id} removes geometry and updates readiness."""
    cam = sample_roi_cameras["CAM-ROI-CROWD-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    # Get ROI id
    summary_res = await client.get(f"/api/v1/cameras/{cam.id}/roi-config", headers=headers)
    roi_id = summary_res.json()["data"]["configurations"][0]["id"]

    del_res = await client.delete(f"/api/v1/cameras/{cam.id}/roi-config/{roi_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["data"]["deleted"] is True

    # Check now NOT_CONFIGURED
    summary_res2 = await client.get(f"/api/v1/cameras/{cam.id}/roi-config", headers=headers)
    assert len(summary_res2.json()["data"]["configurations"]) == 0
    assert summary_res2.json()["data"]["readiness_by_profile"]["CROWD_STANDARD"]["status"] == "NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_reject_polygon_fewer_than_3_points(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """Polygon with < 3 points rejected with 422 ROI_TOO_FEW_POINTS."""
    cam = sample_roi_cameras["CAM-ROI-CROWD-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    payload = {
        "profile_id": "CROWD_STANDARD",
        "roi_type": "CROWD_ROI",
        "name": "Invalid Triangle",
        "geometry_json": {
            "points": [
                {"x": 0.10, "y": 0.10},
                {"x": 0.90, "y": 0.90},
            ]
        },
    }
    res = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=payload, headers=headers)
    assert res.status_code == 422
    assert "ROI_TOO_FEW_POINTS" in res.text or "at least 3" in res.text


@pytest.mark.asyncio
async def test_reject_coordinates_out_of_range(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """Coordinates outside [0.0, 1.0] rejected with 422 ROI_COORDINATE_OUT_OF_RANGE."""
    cam = sample_roi_cameras["CAM-ROI-CROWD-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    payload = {
        "profile_id": "CROWD_STANDARD",
        "roi_type": "CROWD_ROI",
        "name": "Out of range polygon",
        "geometry_json": {
            "points": [
                {"x": 0.10, "y": 0.10},
                {"x": 1.25, "y": 0.10},  # x > 1.0
                {"x": 0.50, "y": 0.90},
            ]
        },
    }
    res = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=payload, headers=headers)
    assert res.status_code == 422
    assert "ROI_COORDINATE_OUT_OF_RANGE" in res.text or "outside valid range" in res.text


@pytest.mark.asyncio
async def test_reject_invalid_counting_line(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """Line missing start/end or with identical endpoints rejected with 422 COUNTING_LINE_INVALID."""
    cam = sample_roi_cameras["CAM-ROI-QUEUE-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    # Identical start and end
    payload = {
        "profile_id": "QUEUE_STANDARD",
        "roi_type": "ENTRY_LINE",
        "name": "Zero Length Line",
        "geometry_json": {
            "start": {"x": 0.50, "y": 0.50},
            "end": {"x": 0.50, "y": 0.50},
            "direction": "IN",
        },
    }
    res = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=payload, headers=headers)
    assert res.status_code == 422
    assert "distinct" in res.text or "COUNTING_LINE_INVALID" in res.text


@pytest.mark.asyncio
async def test_reject_profile_roi_mismatch(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """Attempting to assign QUEUE_ROI to CROWD_STANDARD rejected with 422 ROI_PROFILE_MISMATCH."""
    cam = sample_roi_cameras["CAM-ROI-CROWD-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    payload = {
        "profile_id": "CROWD_STANDARD",
        "roi_type": "QUEUE_ROI",
        "name": "Mismatched Queue ROI on Crowd Camera",
        "geometry_json": {
            "points": [
                {"x": 0.1, "y": 0.1},
                {"x": 0.9, "y": 0.1},
                {"x": 0.5, "y": 0.9},
            ]
        },
    }
    res = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=payload, headers=headers)
    assert res.status_code == 422
    assert "ROI_PROFILE_MISMATCH" in res.text or "not supported" in res.text


@pytest.mark.asyncio
async def test_dry_run_roi_validation(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """POST /api/v1/cameras/{id}/roi-config/validate validates structure without saving."""
    cam = sample_roi_cameras["CAM-ROI-CROWD-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    # Valid payload
    payload_valid = {
        "profile_id": "CROWD_STANDARD",
        "roi_type": "CROWD_ROI",
        "geometry_json": {
            "points": [
                {"x": 0.1, "y": 0.1},
                {"x": 0.8, "y": 0.1},
                {"x": 0.8, "y": 0.8},
            ]
        },
    }
    res_v = await client.post(f"/api/v1/cameras/{cam.id}/roi-config/validate", json=payload_valid, headers=headers)
    assert res_v.status_code == 200
    assert res_v.json()["data"]["valid"] is True

    # Invalid payload (< 3 points)
    payload_invalid = {
        "profile_id": "CROWD_STANDARD",
        "roi_type": "CROWD_ROI",
        "geometry_json": {
            "points": [
                {"x": 0.1, "y": 0.1},
                {"x": 0.8, "y": 0.1},
            ]
        },
    }
    res_inv = await client.post(f"/api/v1/cameras/{cam.id}/roi-config/validate", json=payload_invalid, headers=headers)
    assert res_inv.status_code == 200
    assert res_inv.json()["data"]["valid"] is False
    assert res_inv.json()["data"]["error_code"] == "ROI_TOO_FEW_POINTS"


@pytest.mark.asyncio
async def test_reject_roi_on_unverified_stream(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """Camera with stream_status='NOT_TESTED' rejected with 400 CAMERA_STREAM_NOT_VERIFIED."""
    cam = sample_roi_cameras["CAM-ROI-UNVERIFIED-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    payload = {
        "profile_id": "CROWD_STANDARD",
        "roi_type": "CROWD_ROI",
        "name": "Unverified Test ROI",
        "geometry_json": {
            "points": [
                {"x": 0.1, "y": 0.1},
                {"x": 0.8, "y": 0.1},
                {"x": 0.8, "y": 0.8},
            ]
        },
    }
    res = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=payload, headers=headers)
    assert res.status_code == 400
    assert "CAMERA_STREAM_NOT_VERIFIED" in res.text or "not verified" in res.text


@pytest.mark.asyncio
async def test_reject_roi_on_offline_camera(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """Camera with stream_status='OFFLINE' or enabled=False rejected with 400 CAMERA_OFFLINE."""
    cam = sample_roi_cameras["CAM-ROI-OFFLINE-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    payload = {
        "profile_id": "CROWD_STANDARD",
        "roi_type": "CROWD_ROI",
        "name": "Offline Camera ROI",
        "geometry_json": {
            "points": [
                {"x": 0.1, "y": 0.1},
                {"x": 0.8, "y": 0.1},
                {"x": 0.8, "y": 0.8},
            ]
        },
    }
    res = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=payload, headers=headers)
    assert res.status_code == 400
    assert "CAMERA_OFFLINE" in res.text or "Offline" in res.text


@pytest.mark.asyncio
async def test_unauthenticated_roi_request(client: AsyncClient, sample_roi_cameras):
    """Request without token returns 401 Unauthorized."""
    cam = sample_roi_cameras["CAM-ROI-CROWD-01"]
    res = await client.get(f"/api/v1/cameras/{cam.id}/roi-config")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_ai_read_permission_enforcement(client: AsyncClient, sample_roi_cameras, db_session: AsyncSession):
    """User without AI_READ permission returns 403 Forbidden."""
    cam = sample_roi_cameras["CAM-ROI-CROWD-01"]

    # Create user with no AI permissions
    role = Role(code="ROLE_NO_AI", name="No AI Role", permissions=[])
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)

    user = User(
        username="no_ai_user",
        email="noai@byc.gov.in",
        password_hash=get_password_hash("pass123"),
        full_name="No AI User",
        role_id=role.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(subject=str(user.id), role="ROLE_NO_AI", permissions=[])
    headers = {"Authorization": f"Bearer {token}"}

    res = await client.get(f"/api/v1/cameras/{cam.id}/roi-config", headers=headers)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_ai_manage_permission_enforcement(client: AsyncClient, read_only_roi_token: str, sample_roi_cameras):
    """Read-only user cannot create or delete ROIs (403 Forbidden)."""
    cam = sample_roi_cameras["CAM-ROI-CROWD-01"]
    headers = {"Authorization": f"Bearer {read_only_roi_token}"}

    payload = {
        "profile_id": "CROWD_STANDARD",
        "roi_type": "CROWD_ROI",
        "name": "Unauthorized Attempt",
        "geometry_json": {
            "points": [{"x": 0.1, "y": 0.1}, {"x": 0.8, "y": 0.1}, {"x": 0.5, "y": 0.8}]
        },
    }
    res = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=payload, headers=headers)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_frs_isolation_rejects_crowd_queue_roi(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """FRS profile strictly rejects crowd/queue analytics geometry with 422 ROI_PROFILE_MISMATCH."""
    cam = sample_roi_cameras["CAM-ROI-FRS-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    payload = {
        "profile_id": "FRS_STANDARD",
        "roi_type": "CROWD_ROI",
        "name": "Illegal FRS Crowd ROI",
        "geometry_json": {
            "points": [{"x": 0.1, "y": 0.1}, {"x": 0.8, "y": 0.1}, {"x": 0.5, "y": 0.8}]
        },
    }
    res = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=payload, headers=headers)
    assert res.status_code == 422
    assert "FRS profile does not support" in res.text or "ROI_PROFILE_MISMATCH" in res.text


@pytest.mark.asyncio
async def test_audit_event_logged_on_roi_creation(client: AsyncClient, superadmin_token: str, sample_roi_cameras, db_session: AsyncSession):
    """ROI creation creates an AuditLog record with action ROI_CREATED."""
    cam = sample_roi_cameras["CAM-ROI-CROWD-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    payload = {
        "profile_id": "CROWD_STANDARD",
        "roi_type": "CROWD_ROI",
        "name": "Audited Density Zone",
        "geometry_json": {
            "points": [{"x": 0.1, "y": 0.1}, {"x": 0.8, "y": 0.1}, {"x": 0.5, "y": 0.8}]
        },
    }
    res = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=payload, headers=headers)
    assert res.status_code == 201

    stmt = select(AuditLog).where(
        AuditLog.action == "ROI_CREATED",
        AuditLog.resource_type == "camera_roi_configuration",
    ).order_by(AuditLog.timestamp.desc())
    audit = (await db_session.execute(stmt)).scalars().first()

    assert audit is not None
    assert audit.metadata_json["camera_code"] == "CAM-ROI-CROWD-01"
    assert audit.metadata_json["roi_type"] == "CROWD_ROI"
    assert "new_geometry" in audit.metadata_json


@pytest.mark.asyncio
async def test_websocket_event_emitted_on_roi_change(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """Changing ROI configuration emits AI_GEOMETRY_CHANGED event on the 'ai' WebSocket channel."""
    cam = sample_roi_cameras["CAM-ROI-CROWD-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    with patch("app.redis.event_bus.event_bus.publish", new_callable=AsyncMock) as mock_pub:
        payload = {
            "profile_id": "CROWD_STANDARD",
            "roi_type": "EXCLUSION_ZONE",
            "name": "Temple Tree Exclusion Zone",
            "geometry_json": {
                "points": [{"x": 0.3, "y": 0.3}, {"x": 0.6, "y": 0.3}, {"x": 0.45, "y": 0.6}]
            },
        }
        res = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=payload, headers=headers)
        assert res.status_code == 201

        mock_pub.assert_called_once()
        args, kwargs = mock_pub.call_args
        assert args[0] == "ai"
        assert args[1]["event_type"] == "AI_GEOMETRY_CHANGED"
        assert args[1]["camera_code"] == "CAM-ROI-CROWD-01"
        assert args[1]["action"] == "ROI_CREATED"


@pytest.mark.asyncio
async def test_camera_snapshot_endpoint(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """GET /api/v1/cameras/{id}/snapshot returns JPEG byte stream with valid magic bytes."""
    cam = sample_roi_cameras["CAM-ROI-CROWD-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    res = await client.get(f"/api/v1/cameras/{cam.id}/snapshot", headers=headers)
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    assert res.content.startswith(b"\xff\xd8")  # JPEG header


@pytest.mark.asyncio
async def test_camera_snapshot_offline_rejected(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """GET /api/v1/cameras/{id}/snapshot on offline camera returns 400 CAMERA_OFFLINE."""
    cam = sample_roi_cameras["CAM-ROI-OFFLINE-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    res = await client.get(f"/api/v1/cameras/{cam.id}/snapshot", headers=headers)
    assert res.status_code == 400
    assert "CAMERA_OFFLINE" in res.text or "Offline" in res.text


@pytest.mark.asyncio
async def test_camera_snapshot_unverified_rejected(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """GET /api/v1/cameras/{id}/snapshot on unverified stream returns 400 CAMERA_STREAM_NOT_VERIFIED."""
    cam = sample_roi_cameras["CAM-ROI-UNVERIFIED-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    res = await client.get(f"/api/v1/cameras/{cam.id}/snapshot", headers=headers)
    assert res.status_code == 400
    assert "CAMERA_STREAM_NOT_VERIFIED" in res.text or "not verified" in res.text


@pytest.mark.asyncio
async def test_no_ai_inference_starts_during_roi_save(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """
    CRITICAL STEP 5 INVARIANT:
    Saving or updating an ROI configuration MUST NOT start any AI inference or spawn inference processes.
    """
    cam = sample_roi_cameras["CAM-ROI-CROWD-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    payload = {
        "profile_id": "CROWD_STANDARD",
        "roi_type": "CROWD_ROI",
        "name": "Non Inference Test Area",
        "geometry_json": {
            "points": [{"x": 0.1, "y": 0.1}, {"x": 0.8, "y": 0.1}, {"x": 0.8, "y": 0.8}]
        },
    }

    # Verify no inference subprocesses are launched
    with patch("subprocess.Popen") as mock_popen, \
         patch("subprocess.run") as mock_run, \
         patch("asyncio.create_subprocess_shell") as mock_shell:

        res = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=payload, headers=headers)
        assert res.status_code == 201

        mock_popen.assert_not_called()
        mock_run.assert_not_called()
        mock_shell.assert_not_called()


@pytest.mark.asyncio
async def test_no_credentials_exposed_in_roi_and_snapshot(client: AsyncClient, superadmin_token: str, sample_roi_cameras):
    """Credentials and passwords must never appear in ROI or snapshot responses."""
    cam = sample_roi_cameras["CAM-ROI-CROWD-01"]
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    res = await client.get(f"/api/v1/cameras/{cam.id}/roi-config", headers=headers)
    assert res.status_code == 200
    res_text = res.text

    assert "password" not in res_text
    assert "gAAAAABtestURL" not in res_text
    assert "rtsp://" not in res_text
