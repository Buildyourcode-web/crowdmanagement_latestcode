from typing import List, Optional, Tuple
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.incident import Incident, IncidentNote
from app.repositories.base_repository import BaseRepository


class IncidentRepository(BaseRepository[Incident]):
    def __init__(self, db: AsyncSession):
        super().__init__(Incident, db)

    async def get_by_code(self, incident_code: str) -> Optional[Incident]:
        stmt = select(Incident).where(Incident.incident_code == incident_code)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_incidents(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        incident_type: Optional[str] = None,
        zone_code: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Incident], int]:
        stmt = select(Incident)

        if status and status.lower() != "all":
            stmt = stmt.where(Incident.status == status.lower())
        if severity and severity.lower() != "all":
            stmt = stmt.where(Incident.severity == severity.lower())
        if incident_type and incident_type.lower() != "all":
            stmt = stmt.where(Incident.type == incident_type.lower())
        if zone_code and zone_code.upper() != "ALL":
            stmt = stmt.where(Incident.zone_code == zone_code)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(Incident.detected_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total

    async def add_note(self, incident: Incident, author: str, text: str) -> IncidentNote:
        note = IncidentNote(incident_id=incident.id, author=author, text=text)
        self.db.add(note)
        await self.db.flush()
        return note
