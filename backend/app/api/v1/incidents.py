from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.common import StandardResponse
from app.schemas.incident import IncidentActionRequest, IncidentNoteCreate, IncidentNoteRead, IncidentRead
from app.security.permissions import Permissions
from app.services.incident_service import IncidentService
from app.utils.response import ResponseMeta, success_response

router = APIRouter(prefix="/incidents", tags=["Incidents"])


@router.get("", response_model=StandardResponse[List[IncidentRead]])
async def list_incidents(
    status: Optional[str] = Query(None, description="detected, acknowledged, assigned, responding, resolved, closed"),
    severity: Optional[str] = Query(None, description="critical, high, medium, low"),
    type: Optional[str] = Query(None, description="crowd_surge, medical, etc."),
    zone: Optional[str] = Query(None, description="Zone code"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.INCIDENT_READ)),
):
    """List operational incidents across 5-stage lifecycle."""
    service = IncidentService(db)
    incidents, total = await service.list_incidents(
        status_filter=status,
        severity=severity,
        incident_type=type,
        zone_code=zone,
        page=page,
        page_size=page_size,
    )
    meta = ResponseMeta(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size if page_size > 0 else 1,
    )
    return success_response(incidents, meta=meta)


@router.get("/{id}", response_model=StandardResponse[IncidentRead])
async def get_incident_detail(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.INCIDENT_READ)),
):
    """Retrieve full incident details including chronology and field notes."""
    service = IncidentService(db)
    incident = await service.get_incident_by_code(id)
    return success_response(incident)


@router.post("/{id}/acknowledge", response_model=StandardResponse[IncidentRead])
async def acknowledge_incident(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.INCIDENT_MANAGE)),
):
    """Mark incident as acknowledged by control room."""
    service = IncidentService(db)
    officer = current_user.full_name or current_user.username
    inc = await service.update_lifecycle(id, "acknowledged", author=officer)
    return success_response(inc)


@router.post("/{id}/assign", response_model=StandardResponse[IncidentRead])
async def assign_incident(
    id: str,
    req: IncidentActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.INCIDENT_MANAGE)),
):
    """Assign incident to response unit (police or medical team)."""
    service = IncidentService(db)
    officer = current_user.full_name or current_user.username
    inc = await service.update_lifecycle(
        id,
        "assigned",
        assigned_team=req.assigned_team,
        assigned_team_label=req.assigned_team_label,
        notes=req.notes,
        author=officer,
    )
    return success_response(inc)


@router.post("/{id}/resolve", response_model=StandardResponse[IncidentRead])
async def resolve_incident(
    id: str,
    req: IncidentActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.INCIDENT_MANAGE)),
):
    """Mark incident as resolved."""
    service = IncidentService(db)
    officer = current_user.full_name or current_user.username
    inc = await service.update_lifecycle(id, "resolved", notes=req.notes, author=officer)
    return success_response(inc)


@router.post("/{id}/notes", response_model=StandardResponse[IncidentNoteRead])
async def add_incident_note(
    id: str,
    note: IncidentNoteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.INCIDENT_MANAGE)),
):
    """Append a field note / log entry to the incident record."""
    service = IncidentService(db)
    new_note = await service.add_note(id, note)
    return success_response(new_note)
