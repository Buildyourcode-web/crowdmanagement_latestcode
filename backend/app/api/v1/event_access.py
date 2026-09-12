import uuid
from typing import List
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.common import StandardResponse
from app.schemas.event_access import (
    UserEventAccessCreate,
    UserEventAccessRead,
    UserSiteAccessCreate,
    UserSiteAccessRead,
)
from app.security.permissions import Permissions
from app.services.event_access_service import EventAccessService
from app.utils.response import success_response

router = APIRouter(prefix="/events/{event_id}/access", tags=["Event Access"])


class BatchSiteAccessRequest(BaseModel):
    user_id: uuid.UUID
    site_ids: List[uuid.UUID]


@router.get("", response_model=StandardResponse[List[UserEventAccessRead]])
async def list_event_access(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.EVENT_ACCESS_MANAGE)),
):
    """List all users assigned to this event."""
    service = EventAccessService(db)
    access_list = await service.list_event_users(event_id)
    return success_response(access_list)


@router.post("", response_model=StandardResponse[UserEventAccessRead], status_code=status.HTTP_201_CREATED)
async def grant_event_access(
    event_id: uuid.UUID,
    data: UserEventAccessCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.EVENT_ACCESS_MANAGE)),
):
    """Grant or update user access to this event."""
    service = EventAccessService(db)
    result = await service.grant_user_event_access(event_id, data, granted_by=current_user.username)
    return success_response(result)


@router.delete("/{user_id}", response_model=StandardResponse[dict])
async def revoke_event_access(
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.EVENT_ACCESS_MANAGE)),
):
    """Revoke user access from this event."""
    service = EventAccessService(db)
    res = await service.revoke_user_event_access(event_id, user_id)
    return success_response(res)


@router.get("/{user_id}/sites", response_model=StandardResponse[List[UserSiteAccessRead]])
async def list_user_sites(
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.EVENT_ACCESS_MANAGE)),
):
    """List specific sites within this event accessible to this user."""
    service = EventAccessService(db)
    sites = await service.list_user_site_accesses(event_id, user_id)
    return success_response(sites)


@router.post("/sites", response_model=StandardResponse[List[UserSiteAccessRead]])
async def set_user_sites(
    event_id: uuid.UUID,
    data: BatchSiteAccessRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.EVENT_ACCESS_MANAGE)),
):
    """Set the specific sites within this event accessible to this user."""
    service = EventAccessService(db)
    sites = await service.set_user_site_accesses(
        event_id, data.user_id, data.site_ids, granted_by=current_user.username
    )
    return success_response(sites)