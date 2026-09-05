from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.operation_repository import OperationRepository
from app.schemas.operation import EmergencyRouteRead, MedicalTeamRead, PoliceUnitRead


class OperationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.op_repo = OperationRepository(db)

    async def list_police_units(self) -> List[PoliceUnitRead]:
        units = await self.op_repo.list_police_units()
        return [
            PoliceUnitRead(
                id=u.unit_code,
                name=u.name,
                type=u.type,
                zone_code=u.zone_code,
                location=u.location,
                status=u.status,
                personnel=u.personnel,
                contact=u.contact,
            )
            for u in units
        ]

    async def list_medical_units(self) -> List[MedicalTeamRead]:
        units = await self.op_repo.list_medical_units()
        return [
            MedicalTeamRead(
                id=u.team_code,
                name=u.name,
                location=u.location,
                status=u.status,
                ambulance=u.ambulance,
                contact=u.contact,
            )
            for u in units
        ]

    async def list_emergency_routes(self) -> List[EmergencyRouteRead]:
        routes = await self.op_repo.list_emergency_routes()
        return [
            EmergencyRouteRead(
                id=r.route_code,
                name=r.name,
                description=r.description,
                status=r.status,
                obstruction=r.obstruction,
                estimatedTime=r.estimated_time,
                coordinates=r.coordinates if isinstance(r.coordinates, list) else [],
            )
            for r in routes
        ]
