from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, get_event_context, require_permission, EventContext
from app.models.user import User
from app.schemas.common import StandardResponse
from app.schemas.dashboard import DashboardSummaryResponse
from app.security.permissions import Permissions
from app.services.dashboard_service import DashboardService
from app.utils.response import success_response

router = APIRouter(prefix="/dashboard", tags=["Command Center Dashboard"])


@router.get("/summary", response_model=StandardResponse[DashboardSummaryResponse])
async def get_dashboard_summary(
    date_range: str = Query("today", description="today, yesterday, 7days, festival, custom"),
    day_number: Optional[int] = Query(None, description="Optional festival day number (1..N)"),
    ctx: EventContext = Depends(get_event_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.CROWD_READ)),
):
    """
    Retrieve unified, bulk-aggregated Command Center Dashboard summary.
    Includes total festival visitors, hourly flow, queues, zone densities, FRS review, and health.
    Scoped by active Event context and site isolation boundaries.
    """
    service = DashboardService(db)
    summary = await service.get_summary(
        date_range=date_range,
        day_number=day_number,
        event_id=ctx.event_id,
        allowed_site_ids=ctx.allowed_site_ids,
    )
    return success_response(summary)

