from typing import List, Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.common import StandardResponse
from app.schemas.gate import GateRead
from app.schemas.zone import ZoneRead
from app.security.permissions import Permissions
from app.services.zone_service import ZoneService
from app.utils.response import success_response

router = APIRouter(prefix="/zones", tags=["Zones"])


@router.get("", response_model=StandardResponse[List[ZoneRead]])
async def list_zones(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ZONE_READ)),
):
    """Retrieve all operational zones with GIS geometries, capacities, and risk levels."""
    service = ZoneService(db)
    zones = await service.list_zones()
    return success_response(zones)


@router.get("/{id}", response_model=StandardResponse[ZoneRead])
async def get_zone_detail(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ZONE_READ)),
):
    """Retrieve details for a single zone by code (e.g. ZONE-A)."""
    service = ZoneService(db)
    zone = await service.get_zone_by_code(id)
    return success_response(zone)


@router.get("/{id}/gates", response_model=StandardResponse[List[GateRead]])
async def get_zone_gates(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ZONE_READ)),
):
    """Retrieve access gates associated with a zone."""
    service = ZoneService(db)
    gates = await service.get_zone_gates(id)
    return success_response(gates)


@router.get("/{id}/crowd", response_model=StandardResponse[dict])
async def get_zone_crowd(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ZONE_READ)),
):
    """Retrieve live crowd density for a specific zone."""
    service = ZoneService(db)
    zone = await service.get_zone_by_code(id)
    return success_response({
        "zone_code": zone.zone_code,
        "current_people": zone.people,
        "capacity": zone.capacity,
        "occupancy_percentage": zone.occupancy_pct,
        "density": zone.density,
        "risk_level": zone.risk,
    })
