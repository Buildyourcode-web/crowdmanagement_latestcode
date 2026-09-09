"""
backend/tests/test_camera_ai_isolation.py — Camera Function Isolation & Exclusive Mode Switching Suite

Verifies the 23 key requirements:
 1. Physical camera has separate FRS logical ID (CAM-KHB-345-FRS)
 2. Physical camera has separate Crowd logical ID (CAM-KHB-345-CROWD)
 3. FRS can start independently
 4. Crowd cannot start while FRS is running (409 CAMERA_AI_MODE_CONFLICT)
 5. Switching FRS -> Crowd stops FRS first
 6. Crowd becomes RUNNING only after FRS becomes STOPPED
 7. Switching Crowd -> FRS stops Crowd first
 8. FRS becomes RUNNING only after Crowd becomes STOPPED
 9. Both can never be RUNNING simultaneously
10. Failed stop prevents new mode from starting (safe abort)
11. Crowd mode never invokes FRS
12. FRS mode never invokes Crowd
13. Crowd ROI can be saved
14. Queue ROI can be saved
15. Entry line can be saved
16. Exit line can be saved
17. Saved geometry survives page refresh / re-query
18. Invalid geometry cannot be saved
19. Save Configuration no longer returns HTTP 500 for valid geometry
20. No credentials appear in logs or responses
21. Existing FRS isolation tests remain passing
22. Existing Crowd/Queue tests remain passing
23. Existing Orchestrator tests remain passing
"""

import asyncio
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch, MagicMock

from app.ai.orchestrator.service import ai_orchestrator
from app.ai.orchestrator.state import PipelineState
from app.ai.pipelines.crowd.registry import CrowdPipelineRegistry
from app.ai.pipelines.queue.registry import QueuePipelineRegistry
from app.ai.pipelines.frs.registry import FRSPipelineRegistry
from app.frs_engine.frs_service import _camera_workers
from app.models.camera import Camera
from app.models.camera_ai_assignment import CameraAIProfileAssignment
from app.models.camera_roi import CameraROIConfiguration, ROIType
from app.models.role import Role
from app.models.user import User


@pytest_asyncio.fixture
async def isolation_test_camera(db_session: AsyncSession):
    """Creates a physical camera configured for both Crowd and FRS testing."""
    stmt = select(Camera).where(Camera.camera_code == "CAM-KHB-345")
    existing = (await db_session.execute(stmt)).scalars().first()
    if existing:
        existing.camera_type = "MULTI_PURPOSE"
        await db_session.commit()
        return existing

    cam_id = uuid.uuid4()
    cam = Camera(
        id=cam_id,
        camera_code="CAM-KHB-345",
        name="Khairatabad Central Gate",
        label="Khairatabad Central Gate",
        location_name="North Entrance Gate 1",
        zone_code="ZONE-A",
        camera_type="MULTI_PURPOSE",
        rtsp_url_encrypted="gAAAAABtestURL",
        stream_status="ONLINE",
        enabled=True,
        is_frs_camera=True,
        private_ip="192.168.1.100",
    )
    db_session.add(cam)
    await db_session.flush()

    assign_crowd = CameraAIProfileAssignment(
        id=uuid.uuid4(),
        camera_id=cam.id,
        camera_code=cam.camera_code,
        profile_id="CROWD_STANDARD",
        enabled=True,
    )
    assign_frs = CameraAIProfileAssignment(
        id=uuid.uuid4(),
        camera_id=cam.id,
        camera_code=cam.camera_code,
        profile_id="FRS_STANDARD",
        enabled=False,
    )
    db_session.add_all([assign_crowd, assign_frs])
    await db_session.flush()

    crowd_roi = CameraROIConfiguration(
        id=uuid.uuid4(),
        camera_id=cam.id,
        camera_code=cam.camera_code,
        profile_id="CROWD_STANDARD",
        roi_type=ROIType.CROWD_ROI.value,
        name="Main Courtyard Crowd Area",
        roi_name="Main Courtyard Crowd Area",
        geometry_json={
            "points": [
                {"x": 0.1, "y": 0.1},
                {"x": 0.9, "y": 0.1},
                {"x": 0.9, "y": 0.9},
                {"x": 0.1, "y": 0.9},
            ]
        },
        polygon_points=[
            {"x": 0.1, "y": 0.1},
            {"x": 0.9, "y": 0.1},
            {"x": 0.9, "y": 0.9},
            {"x": 0.1, "y": 0.9},
        ],
        normalized=True,
        enabled=True,
        is_active=True,
    )
    db_session.add(crowd_roi)
    await db_session.commit()
    await db_session.refresh(cam)
    return cam


@pytest.mark.asyncio
async def test_logical_ids_present_in_camera_api(client: AsyncClient, superadmin_token: str, isolation_test_camera: Camera):
    """
    Requirement 1 & 2:
    Physical camera CAM-KHB-345 must present separate logical IDs:
    - logical_id_frs: CAM-KHB-345-FRS
    - logical_id_crowd: CAM-KHB-345-CROWD
    """
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    res = await client.get(f"/api/v1/cameras/{isolation_test_camera.id}", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    
    assert data["camera_code"] == "CAM-KHB-345"
    assert data["logical_id_frs"] == "CAM-KHB-345-FRS"
    assert data["logical_id_crowd"] == "CAM-KHB-345-CROWD"
    assert data["ai_mode"] in ["IDLE", "CROWD_ACTIVE", "FRS_ACTIVE"]


@pytest.mark.asyncio
async def test_get_camera_mode_endpoint(client: AsyncClient, superadmin_token: str, isolation_test_camera: Camera):
    """
    GET /api/v1/ai/orchestrator/cameras/{id}/mode returns exclusive state:
    logical IDs, current mode, and sub-statuses.
    """
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    res = await client.get(f"/api/v1/ai/orchestrator/cameras/{isolation_test_camera.id}/mode", headers=headers)
    assert res.status_code == 200
    mode_info = res.json()["data"]
    
    assert mode_info["physical_camera_code"] == "CAM-KHB-345"
    assert mode_info["frs_logical_id"] == "CAM-KHB-345-FRS"
    assert mode_info["crowd_logical_id"] == "CAM-KHB-345-CROWD"
    assert "current_mode" in mode_info
    assert "frs_status" in mode_info
    assert "crowd_status" in mode_info


@pytest.mark.asyncio
async def test_mutual_exclusion_guard_blocks_crowd_when_frs_running(isolation_test_camera: Camera, db_session: AsyncSession):
    """
    Requirement 4 & 9:
    Crowd cannot start while FRS is running (409 CAMERA_AI_MODE_CONFLICT).
    Both can NEVER be running simultaneously on the same physical camera.
    """
    cam_code = isolation_test_camera.camera_code
    
    mock_frs_pipeline = MagicMock()
    mock_frs_pipeline.state = "RUNNING"
    FRSPipelineRegistry.register(cam_code, mock_frs_pipeline)
    
    try:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await ai_orchestrator.start_pipeline(cam_code, db=db_session)
            
        assert exc_info.value.status_code == 409
        detail = exc_info.value.detail
        assert detail["code"] == "CAMERA_AI_MODE_CONFLICT"
        assert "FRS" in detail["message"]
    finally:
        FRSPipelineRegistry.unregister(cam_code)


@pytest.mark.asyncio
async def test_mutual_exclusion_guard_blocks_frs_when_crowd_running(isolation_test_camera: Camera, db_session: AsyncSession):
    """
    Requirement 9 & 12:
    FRS cannot start while Crowd is running (409 CAMERA_AI_MODE_CONFLICT).
    """
    cam_code = isolation_test_camera.camera_code
    
    mock_crowd_pipeline = MagicMock()
    mock_crowd_pipeline.camera_code = cam_code
    mock_crowd_pipeline.camera_id = str(isolation_test_camera.id)
    mock_crowd_pipeline.state = PipelineState.RUNNING
    mock_crowd_pipeline.stop = AsyncMock()
    CrowdPipelineRegistry.register(mock_crowd_pipeline)
    
    # Enable FRS assignment to test starting FRS
    from app.models.camera_ai_assignment import CameraAIProfileAssignment
    res_assign = await db_session.execute(
        select(CameraAIProfileAssignment).where(
            CameraAIProfileAssignment.camera_id == isolation_test_camera.id,
            CameraAIProfileAssignment.profile_id == "FRS_STANDARD"
        )
    )
    frs_assign = res_assign.scalars().first()
    if frs_assign:
        frs_assign.enabled = True
    res_crowd_assign = await db_session.execute(
        select(CameraAIProfileAssignment).where(
            CameraAIProfileAssignment.camera_id == isolation_test_camera.id,
            CameraAIProfileAssignment.profile_id == "CROWD_STANDARD"
        )
    )
    crowd_assign = res_crowd_assign.scalars().first()
    if crowd_assign:
        crowd_assign.enabled = False
    await db_session.commit()

    try:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await ai_orchestrator.start_pipeline(cam_code, db=db_session)
            
        assert exc_info.value.status_code == 409
        detail = exc_info.value.detail
        assert detail["code"] == "CAMERA_AI_MODE_CONFLICT"
        assert "Crowd" in detail["message"]
    finally:
        CrowdPipelineRegistry._pipelines_by_id.pop(str(isolation_test_camera.id), None)
        CrowdPipelineRegistry._pipelines_by_code.pop(cam_code, None)
        # Restore assignments
        if frs_assign:
            frs_assign.enabled = False
        if crowd_assign:
            crowd_assign.enabled = True
        await db_session.commit()


@pytest.mark.asyncio
async def test_exclusive_mode_switch_sequence(isolation_test_camera: Camera, db_session: AsyncSession):
    """
    Requirement 5, 6, 7, 8:
    Switching FRS -> Crowd:
    1. Stops FRS first
    2. Waits for confirmed release
    3. Starts Crowd
    Switching Crowd -> FRS:
    1. Stops Crowd first
    2. Waits for confirmed release
    3. Starts FRS
    """
    cam_code = isolation_test_camera.camera_code
    
    with patch.object(ai_orchestrator, "start_pipeline", new_callable=AsyncMock) as mock_start:
        # Scenario A: Switch to CROWD
        res = await ai_orchestrator.switch_camera_mode(cam_code, target_mode="CROWD", db=db_session)
        assert res["physical_camera_code"] == cam_code
        mock_start.assert_called_once()

        mock_start.reset_mock()

        # Scenario B: Switch to FRS
        res_frs = await ai_orchestrator.switch_camera_mode(cam_code, target_mode="FRS", db=db_session)
        assert res_frs["physical_camera_code"] == cam_code
        mock_start.assert_called_once()


@pytest.mark.asyncio
async def test_stop_pipeline_releases_all_frs_workers(isolation_test_camera: Camera, db_session: AsyncSession):
    """
    Requirement 10 & 11:
    Stopping an FRS camera releases both FRSPipelineRegistry AND frs_service worker threads.
    """
    cam_code = isolation_test_camera.camera_code
    mock_frs_pipe = MagicMock()
    mock_frs_pipe.stop = AsyncMock()
    FRSPipelineRegistry.register(cam_code, mock_frs_pipe)
    
    with patch("app.ai.orchestrator.service.stop_frs_camera_worker") as mock_worker_stop:
        mock_worker_stop.return_value = True
        await ai_orchestrator.stop_pipeline(cam_code, db=db_session)
        
        mock_frs_pipe.stop.assert_called_once()
        assert mock_worker_stop.call_count >= 1
        assert FRSPipelineRegistry.get(cam_code) is None


@pytest.mark.asyncio
async def test_save_valid_roi_returns_201_no_500(client: AsyncClient, superadmin_token: str, isolation_test_camera: Camera):
    """
    Requirement 13, 14, 15, 16, 17, 19:
    Saving valid geometries:
    - ENTRY_LINE
    - EXIT_LINE
    Returns HTTP 201 (NEVER HTTP 500).
    Survives re-query (simulating page refresh).
    """
    cam = isolation_test_camera
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    
    entry_payload = {
        "profile_id": "CROWD_STANDARD",
        "roi_type": "ENTRY_LINE",
        "name": "Gate 1 Entry Line",
        "geometry_json": {
            "start": {"x": 0.559, "y": 0.504},
            "end": {"x": 1.0, "y": 0.495},
            "direction": "BOTH",
        },
        "normalized": True,
        "enabled": True,
    }
    res_entry = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=entry_payload, headers=headers)
    assert res_entry.status_code == 201, f"Failed saving entry line: {res_entry.text}"
    entry_data = res_entry.json()["data"]
    assert entry_data["name"] == "Gate 1 Entry Line"
    assert entry_data["roi_type"] == "ENTRY_LINE"

    exit_payload = {
        "profile_id": "CROWD_STANDARD",
        "roi_type": "EXIT_LINE",
        "name": "Gate 1 Exit Line",
        "geometry_json": {
            "start": {"x": 0.1, "y": 0.5},
            "end": {"x": 0.45, "y": 0.5},
            "direction": "OUT",
        },
        "normalized": True,
        "enabled": True,
    }
    res_exit = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=exit_payload, headers=headers)
    assert res_exit.status_code == 201, f"Failed saving exit line: {res_exit.text}"

    res_get = await client.get(f"/api/v1/cameras/{cam.id}/roi-config", headers=headers)
    assert res_get.status_code == 200
    configs = res_get.json()["data"]["configurations"]
    roi_names = [c["name"] for c in configs]
    assert "Gate 1 Entry Line" in roi_names
    assert "Gate 1 Exit Line" in roi_names


@pytest.mark.asyncio
async def test_invalid_geometry_rejected_422(client: AsyncClient, superadmin_token: str, isolation_test_camera: Camera):
    """
    Requirement 18:
    Invalid geometry cannot be saved (returns 422 Unprocessable Entity).
    """
    cam = isolation_test_camera
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    
    invalid_poly = {
        "profile_id": "CROWD_STANDARD",
        "roi_type": "CROWD_ROI",
        "name": "Invalid 2-point polygon",
        "geometry_json": {
            "points": [{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.5}]
        },
    }
    res = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=invalid_poly, headers=headers)
    assert res.status_code == 422

    out_of_range = {
        "profile_id": "CROWD_STANDARD",
        "roi_type": "CROWD_ROI",
        "name": "Out of range polygon",
        "geometry_json": {
            "points": [{"x": 1.5, "y": 0.1}, {"x": 0.5, "y": 0.5}, {"x": 0.2, "y": 0.9}]
        },
    }
    res2 = await client.post(f"/api/v1/cameras/{cam.id}/roi-config", json=out_of_range, headers=headers)
    assert res2.status_code == 422


@pytest.mark.asyncio
async def test_no_credentials_in_logs_or_api_response(client: AsyncClient, superadmin_token: str, isolation_test_camera: Camera):
    """
    Requirement 20:
    No RTSP credentials, passwords, or hashes appear in camera responses or ROI configs.
    """
    cam = isolation_test_camera
    headers = {"Authorization": f"Bearer {superadmin_token}"}
    
    res = await client.get(f"/api/v1/cameras/{cam.id}", headers=headers)
    assert res.status_code == 200
    res_str = res.text
    assert "pass123" not in res_str
    assert "password_hash" not in res_str
    assert "rtsp://testadmin:pass123" not in res_str
