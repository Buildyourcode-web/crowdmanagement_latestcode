import uuid
from typing import List, Optional, Tuple
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.alert import Alert
from app.repositories.base_repository import BaseRepository


class AlertRepository(BaseRepository[Alert]):
    def __init__(self, db: AsyncSession):
        super().__init__(Alert, db)

    async def get_by_code(self, alert_code: str) -> Optional[Alert]:
        stmt = select(Alert).where(Alert.alert_code == alert_code)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_alerts(
        self,
        severity: Optional[str] = None,
        alert_type: Optional[str] = None,
        zone_code: Optional[str] = None,
        camera_code: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        event_id: Optional[uuid.UUID] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[Alert], int]:
        stmt = select(Alert)

        if event_id is not None:
            stmt = stmt.where(or_(Alert.event_id == event_id, Alert.event_id.is_(None)))


        if severity and severity.lower() != "all":
            stmt = stmt.where(Alert.severity == severity.lower())
        if alert_type and alert_type.lower() != "all":
            stmt = stmt.where(Alert.type == alert_type.lower())
        if zone_code and zone_code.upper() != "ALL":
            stmt = stmt.where(Alert.zone_code == zone_code)
        if camera_code and camera_code.upper() != "ALL":
            stmt = stmt.where(Alert.camera_code == camera_code)
        if status and status.lower() != "all":
            stmt = stmt.where(Alert.status == status.lower())
        if search:
            q = f"%{search}%"
            stmt = stmt.where(or_(Alert.title.ilike(q), Alert.message.ilike(q), Alert.alert_code.ilike(q)))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(Alert.detected_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total
