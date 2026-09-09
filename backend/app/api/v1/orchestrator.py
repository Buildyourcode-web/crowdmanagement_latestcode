"""
orchestrator.py — REST API Router for AI Orchestrator & Multi-Camera Management.

Endpoints:
- GET  /api/v1/ai/orchestrator/deployments              (List all camera AI deployments)
- GET  /api/v1/ai/orchestrator/deployments/{camera_id}  (Get single deployment details)
- POST /api/v1/ai/orchestrator/pipelines/{camera_id}/start   (Start pipeline)
- POST /api/v1/ai/orchestrator/pipelines/{camera_id}/stop    (Stop pipeline)
- POST /api/v1/ai/orchestrator/pipelines/{camera_id}/restart (Restart pipeline)
- POST /api/v1/ai/orchestrator/start-all               (Resource-aware Start All)
- POST /api/v1/ai/orchestrator/stop-all                (Graceful Stop All)
- GET  /api/v1/ai/orchestrator/status                  (Global orchestrator status & counts)
- GET  /api/v1/ai/orchestrator/health                  (Supervisor loop & engine health)
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel, Field

from app.ai.deployments.service import AIDeployment
from app.ai.orchestrator.service import ai_orchestrator
from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.common import StandardResponse
from app.security.permissions import Permissions
from app.utils.response import success_response

router = APIRouter(prefix="/orchestrator", tags=["AI Orchestration & Multi-Camera Management"])


class CameraModeSwitchRequest(BaseModel):
    target_mode: str = Field(..., example="CROWD")  # "FRS", "CROWD", "IDLE", "STOP"
    profile_id: Optional[str] = None


@router.get("/deployments", response_model=StandardResponse[List[AIDeployment]])
async def list_orchestrator_deployments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_READ)),
):
    """Lists all camera AI deployments with desired vs actual state and live metrics."""
    deployments = await ai_orchestrator.list_deployments(db)
    return success_response(deployments)


@router.get("/deployments/{camera_id_or_code}", response_model=StandardResponse[AIDeployment])
async def get_orchestrator_deployment(
    camera_id_or_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_READ)),
):
    """Retrieves a single deployment by camera UUID or camera_code."""
    deployments = await ai_orchestrator.list_deployments(db)
    dep = next((d for d in deployments if d.camera_code == camera_id_or_code or d.camera_id == camera_id_or_code), None)
    if not dep:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "DEPLOYMENT_NOT_FOUND", "message": f"Deployment for '{camera_id_or_code}' not found."},
        )
    return success_response(dep)


@router.post("/pipelines/{camera_id_or_code}/start", response_model=StandardResponse[Dict[str, Any]])
async def start_orchestrator_pipeline(
    camera_id_or_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_MANAGE)),
):
    """Starts an AI pipeline instance through the orchestrator."""
    client_ip = request.client.host if request.client else None
    res = await ai_orchestrator.start_pipeline(
        camera_id_or_code=camera_id_or_code,
        db=db,
        current_user=current_user,
        client_ip=client_ip,
    )
    return success_response(res)


@router.post("/pipelines/{camera_id_or_code}/stop", response_model=StandardResponse[Dict[str, Any]])
async def stop_orchestrator_pipeline(
    camera_id_or_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_MANAGE)),
):
    """Stops an AI pipeline instance gracefully and idempotently."""
    client_ip = request.client.host if request.client else None
    res = await ai_orchestrator.stop_pipeline(
        camera_id_or_code=camera_id_or_code,
        db=db,
        current_user=current_user,
        client_ip=client_ip,
    )
    return success_response(res)


@router.post("/pipelines/{camera_id_or_code}/restart", response_model=StandardResponse[Dict[str, Any]])
async def restart_orchestrator_pipeline(
    camera_id_or_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_MANAGE)),
):
    """Restarts an AI pipeline with full resource cleanup and reconnection."""
    client_ip = request.client.host if request.client else None
    res = await ai_orchestrator.restart_pipeline(
        camera_id_or_code=camera_id_or_code,
        db=db,
        current_user=current_user,
        client_ip=client_ip,
    )
    return success_response(res)


@router.post("/start-all", response_model=StandardResponse[Dict[str, Any]])
async def start_all_orchestrator_pipelines(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_MANAGE)),
):
    """Resource-aware Start All. Prioritizes deployments and halts at capacity limits."""
    client_ip = request.client.host if request.client else None
    res = await ai_orchestrator.start_all(
        db=db,
        current_user=current_user,
        client_ip=client_ip,
    )
    return success_response(res)


@router.post("/stop-all", response_model=StandardResponse[Dict[str, Any]])
async def stop_all_orchestrator_pipelines(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_MANAGE)),
):
    """Gracefully stops all active pipelines across the platform."""
    client_ip = request.client.host if request.client else None
    res = await ai_orchestrator.stop_all(
        db=db,
        current_user=current_user,
        client_ip=client_ip,
    )
    return success_response(res)


@router.get("/status", response_model=StandardResponse[Dict[str, Any]])
async def get_orchestrator_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_READ)),
):
    """Returns global orchestrator state counts and active pipelines."""
    status_data = await ai_orchestrator.get_orchestrator_status(db)
    return success_response(status_data)


@router.get("/health", response_model=StandardResponse[Dict[str, Any]])
async def get_orchestrator_health(
    current_user: User = Depends(require_permission(Permissions.AI_READ)),
):
    """Returns health status of the orchestrator supervision loop."""
    return success_response({
        "status": "HEALTHY" if ai_orchestrator._is_running else "IDLE",
        "supervision_loop_active": ai_orchestrator._is_running,
    })


@router.get("/cameras/{camera_id_or_code}/mode", response_model=StandardResponse[Dict[str, Any]])
async def get_camera_ai_mode(
    camera_id_or_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_READ)),
):
    """Retrieves current exclusive AI mode (IDLE, FRS_ACTIVE, CROWD_ACTIVE) and logical IDs."""
    res = await ai_orchestrator.get_camera_mode(camera_id_or_code, db)
    return success_response(res)


@router.post("/cameras/{camera_id_or_code}/switch-mode", response_model=StandardResponse[Dict[str, Any]])
async def switch_camera_ai_mode(
    camera_id_or_code: str,
    payload: CameraModeSwitchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_MANAGE)),
):
    """Exclusively switches physical camera between FRS, CROWD, and IDLE."""
    client_ip = request.client.host if request.client else None
    res = await ai_orchestrator.switch_camera_mode(
        camera_id_or_code=camera_id_or_code,
        target_mode=payload.target_mode,
        profile_id=payload.profile_id,
        db=db,
        current_user=current_user,
        client_ip=client_ip,
    )
    return success_response(res)
