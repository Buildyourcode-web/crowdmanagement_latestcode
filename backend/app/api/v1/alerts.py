from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_user, get_db, get_event_context, require_permission, EventContext
from app.models.user import User

from app.schemas.alert import AlertActionRequest, AlertRead, AlertStatsResponse
from app.schemas.common import StandardResponse
from app.security.permissions import Permissions
from app.services.alert_service import AlertService
from app.utils.response import ResponseMeta, success_response

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("", response_model=StandardResponse[List[AlertRead]])
async def list_alerts(
    severity: Optional[str] = Query(None, description="critical, high, medium, low"),
    type: Optional[str] = Query(None, description="crowd_density, queue, bottleneck, etc."),
    zone: Optional[str] = Query(None, description="Zone filter"),
    camera: Optional[str] = Query(None, description="Camera filter"),
    status: Optional[str] = Query(None, description="active, acknowledged, resolved, dismissed"),
    search: Optional[str] = Query(None, description="Search alert title or message"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    ctx: EventContext = Depends(get_event_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ALERT_READ)),
):
    """Retrieve operational alerts with multi-criteria filtering and event context isolation."""
    service = AlertService(db)
    alerts, total = await service.list_alerts(
        severity=severity,
        alert_type=type,
        zone_code=zone,
        camera_code=camera,
        status_filter=status,
        search=search,
        event_id=ctx.event_id,
        page=page,
        page_size=page_size,
    )

    meta = ResponseMeta(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size if page_size > 0 else 1,
    )
    return success_response(alerts, meta=meta)


@router.get("/stats", response_model=StandardResponse[AlertStatsResponse])
async def get_alert_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ALERT_READ)),
):
    """Retrieve counts of critical, high, medium, and active alerts."""
    service = AlertService(db)
    stats = await service.get_stats()
    return success_response(stats)


@router.post("/{id}/acknowledge", response_model=StandardResponse[AlertRead])
async def acknowledge_alert(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ALERT_MANAGE)),
):
    """Acknowledge an active alert."""
    service = AlertService(db)
    officer_name = current_user.full_name or current_user.username
    alert = await service.acknowledge_alert(id, officer_name=officer_name)
    return success_response(alert)


@router.post("/{id}/resolve", response_model=StandardResponse[dict])
async def resolve_alert(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ALERT_MANAGE)),
):
    """Mark an alert as resolved."""
    return success_response({"id": id, "status": "resolved", "resolved_by": current_user.username})


@router.post("/{id}/dismiss", response_model=StandardResponse[dict])
async def dismiss_alert(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ALERT_MANAGE)),
):
    """Dismiss an alert."""
    return success_response({"id": id, "status": "dismissed", "dismissed_by": current_user.username})
