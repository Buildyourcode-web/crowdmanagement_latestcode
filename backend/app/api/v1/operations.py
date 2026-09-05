from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.common import StandardResponse
from app.schemas.operation import EmergencyRouteRead, MedicalTeamRead, PoliceUnitRead
from app.security.permissions import Permissions
from app.services.operation_service import OperationService
from app.utils.response import success_response

router = APIRouter(prefix="/operations", tags=["Operations & Field Units"])


@router.get("/police-units", response_model=StandardResponse[List[PoliceUnitRead]])
async def list_police_units(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.OPERATIONS_READ)),
):
    """Retrieve deployed police patrol and sector units."""
    service = OperationService(db)
    units = await service.list_police_units()
    return success_response(units)


@router.get("/medical-units", response_model=StandardResponse[List[MedicalTeamRead]])
async def list_medical_units(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.OPERATIONS_READ)),
):
    """Retrieve on-duty medical and emergency first-responder units."""
    service = OperationService(db)
    units = await service.list_medical_units()
    return success_response(units)


@router.get("/emergency-routes", response_model=StandardResponse[List[EmergencyRouteRead]])
async def list_emergency_routes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.OPERATIONS_READ)),
):
    """Retrieve designated emergency evacuation and ambulance corridors."""
    service = OperationService(db)
    routes = await service.list_emergency_routes()
    return success_response(routes)
