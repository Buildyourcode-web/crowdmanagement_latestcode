from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.common import StandardResponse
from app.schemas.missing_person import MissingPersonCaseRead
from app.security.permissions import Permissions
from app.services.missing_person_service import MissingPersonService
from app.utils.response import success_response

router = APIRouter(prefix="/missing-persons", tags=["Missing Persons"])


@router.get("", response_model=StandardResponse[List[MissingPersonCaseRead]])
async def list_missing_persons(
    status: Optional[str] = Query(None, description="Filter: searching, found, closed"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.MISSING_PERSON_READ)),
):
    """Retrieve active and resolved missing person registry cases."""
    service = MissingPersonService(db)
    cases = await service.list_cases(status_filter=status)
    return success_response(cases)


@router.get("/{id}", response_model=StandardResponse[MissingPersonCaseRead])
async def get_missing_person_detail(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.MISSING_PERSON_READ)),
):
    """Retrieve specific missing person case details and candidate detections."""
    service = MissingPersonService(db)
    case = await service.get_case_by_code(id)
    return success_response(case)


@router.get("/{id}/timeline", response_model=StandardResponse[List[dict]])
async def get_missing_person_timeline(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.MISSING_PERSON_READ)),
):
    """Retrieve search chronology for a missing person case."""
    service = MissingPersonService(db)
    case = await service.get_case_by_code(id)
    timeline = [
        {"time": case.reported_at.isoformat(), "event": "Case opened by command desk"},
        {"time": case.last_seen_time.isoformat(), "event": f"Last reported sighting at {case.last_known_zone}"},
    ]
    return success_response(timeline)
