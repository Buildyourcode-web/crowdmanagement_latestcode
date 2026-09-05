"""
app.repositories.camera_roi_repository — Database operations for CameraROIConfiguration.
"""

import uuid
from typing import List, Optional
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.camera_roi import CameraROIConfiguration


class CameraROIRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, roi_id: uuid.UUID) -> Optional[CameraROIConfiguration]:
        stmt = select(CameraROIConfiguration).where(CameraROIConfiguration.id == roi_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_by_camera_id(
        self,
        camera_id: uuid.UUID,
        profile_id: Optional[str] = None,
        enabled_only: bool = False,
    ) -> List[CameraROIConfiguration]:
        stmt = select(CameraROIConfiguration).where(CameraROIConfiguration.camera_id == camera_id)
        if profile_id:
            stmt = stmt.where(CameraROIConfiguration.profile_id == profile_id)
        if enabled_only:
            stmt = stmt.where(CameraROIConfiguration.enabled.is_(True))
        stmt = stmt.order_by(CameraROIConfiguration.created_at.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_camera_code(
        self,
        camera_code: str,
        profile_id: Optional[str] = None,
        enabled_only: bool = False,
    ) -> List[CameraROIConfiguration]:
        stmt = select(CameraROIConfiguration).where(CameraROIConfiguration.camera_code == camera_code)
        if profile_id:
            stmt = stmt.where(CameraROIConfiguration.profile_id == profile_id)
        if enabled_only:
            stmt = stmt.where(CameraROIConfiguration.enabled.is_(True))
        stmt = stmt.order_by(CameraROIConfiguration.created_at.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_camera_and_type(
        self,
        camera_id: uuid.UUID,
        profile_id: str,
        roi_type: str,
    ) -> List[CameraROIConfiguration]:
        stmt = select(CameraROIConfiguration).where(
            CameraROIConfiguration.camera_id == camera_id,
            CameraROIConfiguration.profile_id == profile_id,
            CameraROIConfiguration.roi_type == roi_type,
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, roi: CameraROIConfiguration) -> CameraROIConfiguration:
        self.db.add(roi)
        await self.db.flush()
        await self.db.refresh(roi)
        return roi

    async def update(self, roi: CameraROIConfiguration) -> CameraROIConfiguration:
        await self.db.flush()
        await self.db.refresh(roi)
        return roi

    async def delete(self, roi: CameraROIConfiguration) -> None:
        await self.db.delete(roi)
        await self.db.flush()
