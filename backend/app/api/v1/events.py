import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, get_event_context, require_permission, EventContext
from app.models.user import User
from app.schemas.common import StandardResponse
from app.schemas.event import EventCreate, EventRead, EventUpdate
from app.security.permissions import Permissions
from app.services.event_service import EventService
from app.utils.response import success_response

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("", response_model=StandardResponse[List[EventRead]])
async def list_events(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all events accessible to the current user."""
    service = EventService(db)
    events = await service.list_accessible_events(current_user)
    return success_response(events)


@router.get("/current", response_model=StandardResponse[EventRead])
async def get_current_event_context(
    ctx: EventContext = Depends(get_event_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve details of the currently selected event context (via X-Event-ID or auto-selected)."""
    service = EventService(db)
    event_data = await service.get_event_by_id(ctx.event_id, current_user)
    return success_response(event_data)


@router.get("/{event_id}", response_model=StandardResponse[EventRead])
async def get_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve details of a specific event."""
    service = EventService(db)
    event_data = await service.get_event_by_id(event_id, current_user)
    return success_response(event_data)


@router.post("", response_model=StandardResponse[EventRead], status_code=status.HTTP_201_CREATED)
async def create_event(
    data: EventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.EVENT_CREATE)),
):
    """Create a new event."""
    service = EventService(db)
    event_data = await service.create_event(data, created_by=current_user.username)
    return success_response(event_data)


@router.put("/{event_id}", response_model=StandardResponse[EventRead])
async def update_event(
    event_id: uuid.UUID,
    data: EventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.EVENT_UPDATE)),
):
    """Update event configuration."""
    service = EventService(db)
    event_data = await service.update_event(event_id, data, updated_by=current_user.username)
    return success_response(event_data)


@router.post("/{event_id}/archive", response_model=StandardResponse[dict])
async def archive_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.EVENT_ARCHIVE)),
):
    """Archive an event when concluded."""
    service = EventService(db)
    res = await service.archive_event(event_id, updated_by=current_user.username)
    return success_response(res)