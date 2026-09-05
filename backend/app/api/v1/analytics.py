from fastapi import APIRouter, Depends, status
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.analytics import AttendanceAnalyticsResponse, CameraAnalyticsResponse, IncidentAnalyticsResponse
from app.schemas.common import StandardResponse
from app.security.permissions import Permissions
from app.services.analytics_service import AnalyticsService
from app.utils.response import success_response

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/attendance", response_model=StandardResponse[AttendanceAnalyticsResponse])
async def get_attendance_analytics(
    current_user: User = Depends(require_permission(Permissions.ANALYTICS_READ)),
):
    """Retrieve historical daily and hourly attendance metrics."""
    data = AnalyticsService.get_attendance_analytics()
    return success_response(data)


@router.get("/incidents", response_model=StandardResponse[IncidentAnalyticsResponse])
async def get_incident_analytics(
    current_user: User = Depends(require_permission(Permissions.ANALYTICS_READ)),
):
    """Retrieve incident frequency breakdown and resolution time analytics."""
    data = AnalyticsService.get_incident_analytics()
    return success_response(data)


@router.get("/cameras", response_model=StandardResponse[CameraAnalyticsResponse])
async def get_camera_analytics(
    current_user: User = Depends(require_permission(Permissions.ANALYTICS_READ)),
):
    """Retrieve camera fleet uptime and detection volume metrics."""
    data = AnalyticsService.get_camera_analytics()
    return success_response(data)
