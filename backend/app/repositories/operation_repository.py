from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.operation import EmergencyRoute, MedicalUnit, PoliceUnit


class OperationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_police_units(self) -> List[PoliceUnit]:
        stmt = select(PoliceUnit).order_by(PoliceUnit.unit_code.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_police_unit_by_code(self, code: str) -> Optional[PoliceUnit]:
        stmt = select(PoliceUnit).where(PoliceUnit.unit_code == code)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_medical_units(self) -> List[MedicalUnit]:
        stmt = select(MedicalUnit).order_by(MedicalUnit.team_code.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_medical_unit_by_code(self, code: str) -> Optional[MedicalUnit]:
        stmt = select(MedicalUnit).where(MedicalUnit.team_code == code)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_emergency_routes(self) -> List[EmergencyRoute]:
        stmt = select(EmergencyRoute).order_by(EmergencyRoute.route_code.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
