"""
queue.py — Queue AI Pipeline & Real-Time Metrics API Router.

Exposes REST endpoints for camera-level and zone-level queue metrics,
occupancy, density, line counting, wait times, health monitoring,
and pipeline lifecycle control (start/stop).
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.common import StandardResponse
from app.security.permissions import Permissions
from app.services.queue_pipeline_service import QueuePipelineService
from app.utils.response import success_response

router = APIRouter(prefix="/queue", tags=["Queue Intelligence"])


@router.get("/cameras/{camera_id}/metrics", response_model=StandardResponse[Dict[str, Any]])
async def get_camera_queue_metrics(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.QUEUE_READ)),
):
    """Retrieve real-time queue metrics (headcount, occupancy, wait time, length, inflow/outflow, risk) for a camera."""
    service = QueuePipelineService(db)
    metrics = await service.get_camera_queue_metrics(camera_id)
    return success_response(metrics)


@router.get("/zones/{zone_id}/metrics", response_model=StandardResponse[Dict[str, Any]])
async def get_zone_queue_metrics(
    zone_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.QUEUE_READ)),
):
    """Retrieve aggregated queue metrics across all active cameras in a zone."""
    service = QueuePipelineService(db)
    metrics = await service.get_zone_queue_metrics(zone_id)
    return success_response(metrics)


@router.get("/status", response_model=StandardResponse[Dict[str, Any]])
async def get_queue_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.QUEUE_READ)),
):
    """Precinct-wide queue monitoring status across active pipelines."""
    service = QueuePipelineService(db)
    status_report = await service.get_all_queues_status()
    return success_response(status_report)


@router.get("/health", response_model=StandardResponse[Any])
async def get_queue_health(
    camera_id: Optional[str] = Query(None, description="Optional filter by camera code/id"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.QUEUE_READ)),
):
    """Queue AI pipeline operational health monitoring."""
    service = QueuePipelineService(db)
    health = await service.get_pipeline_health(camera_id)
    return success_response(health)


@router.post("/pipelines/{camera_id}/start", response_model=StandardResponse[Dict[str, Any]])
async def start_queue_pipeline(
    camera_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_MANAGE)),
):
    """
    Start Queue AI inference pipeline on a verified camera stream.
    Validates QUEUE_ROI, ENTRY_LINE, and EXIT_LINE readiness, hardware capacity,
    and runtime capabilities.
    """
    service = QueuePipelineService(db)
    client_ip = request.client.host if request.client else None
    result = await service.start_queue_pipeline(
        camera_id_or_code=camera_id,
        current_user=current_user,
        client_ip=client_ip,
    )
    return success_response(result)


@router.post("/pipelines/{camera_id}/stop", response_model=StandardResponse[Dict[str, Any]])
async def stop_queue_pipeline(
    camera_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_MANAGE)),
):
    """Stop active Queue AI inference pipeline on a camera stream."""
    service = QueuePipelineService(db)
    client_ip = request.client.host if request.client else None
    result = await service.stop_queue_pipeline(
        camera_id_or_code=camera_id,
        current_user=current_user,
        client_ip=client_ip,
    )
    return success_response(result)


@router.get("/pipelines/{camera_id}/status", response_model=StandardResponse[Dict[str, Any]])
async def get_queue_pipeline_status(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_READ)),
):
    """Inspect detailed runtime state and health telemetry for a queue pipeline."""
    service = QueuePipelineService(db)
    metrics = await service.get_camera_queue_metrics(camera_id)
    return success_response(metrics)
