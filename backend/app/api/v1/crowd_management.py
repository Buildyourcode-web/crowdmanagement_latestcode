"""
crowd_management.py — Consolidated Crowd Management Dashboard API Router.

Exposes REST endpoints aggregating Crowd AI, Queue AI, Zone status,
camera health, risk calculations, and active events.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.common import StandardResponse
from app.schemas.crowd_management import CrowdManagementSummaryResponse
from app.security.permissions import Permissions
from app.services.crowd_management_service import CrowdManagementService
from app.utils.response import success_response

router = APIRouter(prefix="/crowd-management", tags=["Crowd Management"])


@router.get("/summary", response_model=StandardResponse[CrowdManagementSummaryResponse])
async def get_crowd_management_summary(
    time_range: str = Query("today", description="Time window: 15m, 1h, today"),
    mode: str = Query("all", description="Display mode: all, queue, zone"),
    camera_id: Optional[str] = Query(None, description="Optional camera ID or code filter"),
    risk_level: str = Query("all", description="Risk filter: all, low, medium, high, critical"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.CROWD_READ)),
):
    """
    Returns unified operational dashboard summary combining crowd occupancy,
    queue wait times, zone density, camera health, and real-time events.
    """
    service = CrowdManagementService(db)
    summary = await service.get_summary(
        time_range=time_range,
        mode=mode,
        camera_id_or_code=camera_id,
        risk_filter=risk_level,
    )
    return success_response(summary)
