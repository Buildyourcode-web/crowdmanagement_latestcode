import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, get_event_context, require_permission, EventContext
from app.models.user import User
from app.schemas.common import StandardResponse
from app.schemas.site import SiteCreate, SiteRead, SiteUpdate
from app.security.permissions import Permissions
from app.services.site_service import SiteService
from app.utils.response import success_response

router = APIRouter(prefix="/sites", tags=["Sites"])


@router.get("", response_model=StandardResponse[List[SiteRead]])
async def list_sites(
    event_id: Optional[uuid.UUID] = Query(None, description="Event ID filter (defaults to current event context)"),
    ctx: EventContext = Depends(get_event_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.SITE_READ)),
):
    """List operational sites for the active event (or specified event), respecting user site permissions."""
    target_event_id = event_id or ctx.event_id
    service = SiteService(db)
    sites = await service.list_sites(target_event_id, ctx.allowed_site_ids)
    return success_response(sites)


@router.get("/{site_id}", response_model=StandardResponse[SiteRead])
async def get_site(
    site_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.SITE_READ)),
):
    """Retrieve details for a single site."""
    service = SiteService(db)
    site = await service.get_site_by_id(site_id)
    return success_response(site)


@router.post("", response_model=StandardResponse[SiteRead], status_code=status.HTTP_201_CREATED)
async def create_site(
    data: SiteCreate,
    ctx: EventContext = Depends(get_event_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.SITE_CREATE)),
):
    """Create a new physical operational site within the active event."""
    target_event_id = data.event_id or ctx.event_id
    service = SiteService(db)
    site = await service.create_site(target_event_id, data, created_by=current_user.username)
    return success_response(site)


@router.put("/{site_id}", response_model=StandardResponse[SiteRead])
async def update_site(
    site_id: uuid.UUID,
    data: SiteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.SITE_UPDATE)),
):
    """Update a site."""
    service = SiteService(db)
    site = await service.update_site(site_id, data, updated_by=current_user.username)
    return success_response(site)


@router.delete("/{site_id}", response_model=StandardResponse[dict])
async def delete_site(
    site_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.SITE_DELETE)),
):
    """Delete a site."""
    service = SiteService(db)
    res = await service.delete_site(site_id)
    return success_response(res)