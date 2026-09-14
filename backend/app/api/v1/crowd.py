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


@router.get("/line-crossings", response_model=StandardResponse[List[Dict[str, Any]]])
async def get_line_crossings(
    camera_code: Optional[str] = Query(None, description="Filter by camera code"),
    direction: Optional[str] = Query(None, description="Filter by direction (IN/OUT)"),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.CROWD_READ)),
):
    """Retrieve durable, immutable line crossing events ledger."""
    from app.models.line_crossing import LineCrossingEvent
    from sqlalchemy import select
    stmt = select(LineCrossingEvent).order_by(LineCrossingEvent.crossing_timestamp.desc()).limit(limit)
    if camera_code:
        stmt = stmt.where(LineCrossingEvent.camera_code == camera_code)
    if direction:
        stmt = stmt.where(LineCrossingEvent.direction == direction.upper())
    res = await db.execute(stmt)
    records = res.scalars().all()
    out = [
        {
            "id": str(r.id),
            "event_id": str(r.event_id) if r.event_id else None,
            "camera_code": r.camera_code,
            "line_id": r.line_id,
            "line_name": r.line_name,
            "track_token": r.track_token,
            "crossing_sequence": r.crossing_sequence,
            "direction": r.direction,
            "count_delta": r.count_delta,
            "detection_confidence": r.detection_confidence,
            "crossing_timestamp": r.crossing_timestamp.isoformat() if r.crossing_timestamp else None,
            "idempotency_key": r.idempotency_key,
            "ground_x": r.ground_x,
            "ground_y": r.ground_y,
        }
        for r in records
    ]
    return success_response(out)


@router.get("/reliability", response_model=StandardResponse[Dict[str, Any]])
async def get_count_reliability_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.CROWD_READ)),
):
    """Retrieve real-time count reliability and anomaly detection report."""
    from app.services.counting_service import CanonicalCountingService
    counting_svc = CanonicalCountingService(db)
    evt = await counting_svc.get_event()
    if not evt:
        return success_response({"overall_reliability": "HIGH", "overall_confidence_score": 95.0, "anomalies": []})
    report = await counting_svc.get_event_count_reliability(evt.id)
    return success_response(report)
