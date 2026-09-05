"""
queue_repository.py — Database repository for QueueSnapshot records.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.queue import QueueSnapshot
from app.repositories.base_repository import BaseRepository


class QueueRepository(BaseRepository[QueueSnapshot]):
    def __init__(self, db: AsyncSession):
        super().__init__(QueueSnapshot, db)

    async def get_latest_for_camera(self, camera_id_or_code: str) -> Optional[QueueSnapshot]:
        """Fetches the most recent queue snapshot for a camera."""
        conditions = [QueueSnapshot.camera_code == camera_id_or_code]
        try:
            cam_uuid = uuid.UUID(str(camera_id_or_code))
            conditions.append(QueueSnapshot.camera_id == cam_uuid)
        except (ValueError, TypeError, AttributeError):
            pass

        stmt = (
            select(QueueSnapshot)
            .where(or_(*conditions))
            .order_by(QueueSnapshot.timestamp.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_latest_for_zone(self, zone_code_or_id: str) -> List[QueueSnapshot]:
        "Fetches latest snapshots for a specific zone."
        conditions = [QueueSnapshot.zone_code == zone_code_or_id]
        try:
            z_uuid = uuid.UUID(str(zone_code_or_id))
            conditions.append(QueueSnapshot.zone_id == z_uuid)
        except (ValueError, TypeError, AttributeError):
            pass

        stmt = (
            select(QueueSnapshot)
            .where(or_(*conditions))
            .order_by(QueueSnapshot.timestamp.desc())
            .limit(20)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_camera_history(self, camera_id_or_code: str, limit: int = 50) -> List[QueueSnapshot]:
        "Fetches historical queue snapshots for a camera."
        conditions = [QueueSnapshot.camera_code == camera_id_or_code]
        try:
            cam_uuid = uuid.UUID(str(camera_id_or_code))
            conditions.append(QueueSnapshot.camera_id == cam_uuid)
        except (ValueError, TypeError, AttributeError):
            pass

        stmt = (
            select(QueueSnapshot)
            .where(or_(*conditions))
            .order_by(QueueSnapshot.timestamp.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_latest_queues(self, limit: int = 20) -> List[QueueSnapshot]:
        "Lists active queue snapshots ordered by timestamp."
        stmt = (
            select(QueueSnapshot)
            .order_by(QueueSnapshot.timestamp.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
