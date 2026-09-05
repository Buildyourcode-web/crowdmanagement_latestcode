from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.gate import Gate
from app.models.zone import Zone
from app.repositories.base_repository import BaseRepository


class ZoneRepository(BaseRepository[Zone]):
    def __init__(self, db: AsyncSession):
        super().__init__(Zone, db)

    async def get_by_code(self, zone_code: str) -> Optional[Zone]:
        stmt = select(Zone).where(Zone.zone_code == zone_code)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_all_zones(self) -> List[Zone]:
        stmt = select(Zone).order_by(Zone.zone_code.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_gates_by_zone(self, zone_code: str) -> List[Gate]:
        stmt = select(Gate).where(Gate.zone_code == zone_code).order_by(Gate.gate_code.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
