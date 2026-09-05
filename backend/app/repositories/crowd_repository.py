import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.crowd import CrowdSnapshot
from app.models.queue import QueueSnapshot
from app.repositories.base_repository import BaseRepository


class CrowdRepository(BaseRepository[CrowdSnapshot]):
    def __init__(self, db: AsyncSession):
        super().__init__(CrowdSnapshot, db)

    async def get_latest_zone_snapshots(self) -> List[CrowdSnapshot]:
        stmt = (
            select(CrowdSnapshot)
            .order_by(CrowdSnapshot.timestamp.desc())
            .limit(50)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_for_camera(self, camera_id_or_code: str) -> Optional[CrowdSnapshot]:
        """Fetch the most recent crowd snapshot for a camera."""
        conditions = [CrowdSnapshot.camera_code == camera_id_or_code]
        try:
            cam_uuid = uuid.UUID(str(camera_id_or_code))
            conditions.append(CrowdSnapshot.camera_id == cam_uuid)
        except (ValueError, TypeError, AttributeError):
            pass

        stmt = (
            select(CrowdSnapshot)
            .where(or_(*conditions))
            .order_by(CrowdSnapshot.timestamp.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_latest_for_zone(self, zone_code_or_id: str) -> List[CrowdSnapshot]:
        """Fetch latest snapshots for a specific zone."""
        conditions = [CrowdSnapshot.zone_code == zone_code_or_id]
        try:
            z_uuid = uuid.UUID(str(zone_code_or_id))
            conditions.append(CrowdSnapshot.zone_id == z_uuid)
        except (ValueError, TypeError, AttributeError):
            pass

        stmt = (
            select(CrowdSnapshot)
            .where(or_(*conditions))
            .order_by(CrowdSnapshot.timestamp.desc())
            .limit(20)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_camera_history(self, camera_id_or_code: str, limit: int = 50) -> List[CrowdSnapshot]:
        """Fetch historical snapshots for a camera."""
        conditions = [CrowdSnapshot.camera_code == camera_id_or_code]
        try:
            cam_uuid = uuid.UUID(str(camera_id_or_code))
            conditions.append(CrowdSnapshot.camera_id == cam_uuid)
        except (ValueError, TypeError, AttributeError):
            pass

        stmt = (
            select(CrowdSnapshot)
            .where(or_(*conditions))
            .order_by(CrowdSnapshot.timestamp.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_latest_queues(self) -> List[QueueSnapshot]:
        stmt = (
            select(QueueSnapshot)
            .order_by(QueueSnapshot.queue_code.asc())
            .limit(20)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
