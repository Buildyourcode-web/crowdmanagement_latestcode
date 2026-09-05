from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.common import StandardResponse
from app.schemas.crowd import CrowdSummaryResponse, CrowdTimeSeriesPoint, QueueResponse
from app.schemas.zone import ZoneRead
from app.security.permissions import Permissions
from app.services.crowd_pipeline_service import CrowdPipelineService
from app.services.crowd_service import CrowdService
from app.services.zone_service import ZoneService
from app.utils.response import success_response

router = APIRouter(prefix="/crowd", tags=["Crowd Intelligence"])


# ── Festival Summary & Zone Endpoints ────────────────────────────────────────

@router.get("/summary", response_model=StandardResponse[CrowdSummaryResponse])
async def get_crowd_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.CROWD_READ)),
):
    """Retrieve festival-wide crowd summary, active queues, and occupancy rates."""
    service = CrowdService(db)
    summary = await service.get_summary()
    return success_response(summary)


@router.get("/zones", response_model=StandardResponse[List[ZoneRead]])
async def get_zone_crowd_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.CROWD_READ)),
):
    """Retrieve crowd density and risk level for all zones."""
    service = ZoneService(db)
    zones = await service.list_zones()
    return success_response(zones)


@router.get("/timeseries", response_model=StandardResponse[List[CrowdTimeSeriesPoint]])
async def get_crowd_timeseries(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.CROWD_READ)),
):
    """Retrieve 24-hour historical inflow, outflow, and crowd curve."""
    service = CrowdService(db)
    timeseries = await service.get_timeseries()
    return success_response(timeseries)


@router.get("/queues", response_model=StandardResponse[List[QueueResponse]])
async def get_queues(
    zone: Optional[str] = Query(None, description="Filter by zone code"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.CROWD_READ)),
):
    """Retrieve active queue lengths, wait times, and growth rates."""
    service = CrowdService(db)
    queues = await service.get_queues(zone_code=zone)
    return success_response(queues)


# ── Step 6: Crowd AI Real-Time Pipeline & Metric Endpoints ───────────────────

@router.get("/cameras/{camera_id}/metrics", response_model=StandardResponse[Dict[str, Any]])
async def get_camera_crowd_metrics(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.CROWD_READ)),
):
    """Retrieve real-time crowd metrics (count, density, inflow/outflow, risk) for a camera."""
    service = CrowdPipelineService(db)
    metrics = await service.get_camera_crowd_metrics(camera_id)
    return success_response(metrics)


@router.get("/zones/{zone_id}/metrics", response_model=StandardResponse[Dict[str, Any]])
async def get_zone_crowd_metrics(
    zone_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.CROWD_READ)),
):
    """Retrieve aggregated crowd metrics across all active cameras in a zone."""
    service = CrowdPipelineService(db)
    metrics = await service.get_zone_crowd_metrics(zone_id)
    return success_response(metrics)


@router.get("/status", response_model=StandardResponse[Dict[str, Any]])
async def get_crowd_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.CROWD_READ)),
):
    """Precinct-wide crowd monitoring status across active pipelines."""
    service = CrowdPipelineService(db)
    status_report = await service.get_crowd_status()
    return success_response(status_report)


@router.get("/health", response_model=StandardResponse[Dict[str, Any]])
async def get_crowd_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.CROWD_READ)),
):
    """Crowd AI pipeline operational health monitoring."""
    service = CrowdPipelineService(db)
    health = await service.get_crowd_health()
    return success_response(health)


@router.post("/pipelines/{camera_id}/start", response_model=StandardResponse[Dict[str, Any]])
async def start_crowd_pipeline(
    camera_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_MANAGE)),
):
    """
    Start Crowd AI inference pipeline on a verified camera stream.
    Validates ROI readiness, hardware capacity, and runtime capabilities.
    """
    service = CrowdPipelineService(db)
    client_ip = request.client.host if request.client else None
    result = await service.start_crowd_pipeline(
        camera_id_or_code=camera_id,
        current_user=current_user,
        client_ip=client_ip,
    )
    return success_response(result)


@router.post("/pipelines/{camera_id}/stop", response_model=StandardResponse[Dict[str, Any]])
async def stop_crowd_pipeline(
    camera_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_MANAGE)),
):
    """Stop active Crowd AI inference pipeline on a camera stream."""
    service = CrowdPipelineService(db)
    client_ip = request.client.host if request.client else None
    result = await service.stop_crowd_pipeline(
        camera_id_or_code=camera_id,
        current_user=current_user,
        client_ip=client_ip,
    )
    return success_response(result)


@router.get("/pipelines/{camera_id}/status", response_model=StandardResponse[Dict[str, Any]])
async def get_crowd_pipeline_status(
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_READ)),
):
    """Inspect detailed runtime state and health telemetry for a camera pipeline."""
    service = CrowdPipelineService(db)
    metrics = await service.get_camera_crowd_metrics(camera_id)
    return success_response(metrics)
