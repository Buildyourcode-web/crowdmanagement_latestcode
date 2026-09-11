from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_user, get_db, get_event_context, require_permission, EventContext
from app.models.user import User
from app.schemas.analytics import AttendanceAnalyticsResponse, CameraAnalyticsResponse, IncidentAnalyticsResponse
from app.schemas.common import StandardResponse
from app.security.permissions import Permissions
from app.services.analytics_service import AnalyticsService
from app.utils.response import success_response

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/attendance", response_model=StandardResponse[AttendanceAnalyticsResponse])
async def get_attendance_analytics(
    ctx: EventContext = Depends(get_event_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ANALYTICS_READ)),
):
    """Retrieve historical daily and hourly attendance metrics."""
    service = AnalyticsService(db)
    data = await service.get_attendance_analytics(event_id=ctx.event_id)
    return success_response(data)


@router.get("/incidents", response_model=StandardResponse[IncidentAnalyticsResponse])
async def get_incident_analytics(
    ctx: EventContext = Depends(get_event_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ANALYTICS_READ)),
):
    """Retrieve incident frequency breakdown and resolution time analytics."""
    service = AnalyticsService(db)
    data = await service.get_incident_analytics(event_id=ctx.event_id)
    return success_response(data)


@router.get("/cameras", response_model=StandardResponse[CameraAnalyticsResponse])
async def get_camera_analytics(
    ctx: EventContext = Depends(get_event_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ANALYTICS_READ)),
):
    """Retrieve camera fleet uptime and detection volume metrics."""
    service = AnalyticsService(db)
    data = await service.get_camera_analytics(event_id=ctx.event_id)
    return success_response(data)
