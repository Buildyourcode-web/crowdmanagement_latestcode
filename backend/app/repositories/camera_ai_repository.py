import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.camera_ai_assignment import CameraAIProfileAssignment
from app.repositories.base_repository import BaseRepository


class CameraAIRepository(BaseRepository[CameraAIProfileAssignment]):
    def __init__(self, db: AsyncSession):
        super().__init__(CameraAIProfileAssignment, db)

    async def get_assignments_for_camera(self, camera_id: uuid.UUID) -> List[CameraAIProfileAssignment]:
        stmt = select(CameraAIProfileAssignment).where(CameraAIProfileAssignment.camera_id == camera_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # Ergonomic alias
    get_by_camera_id = get_assignments_for_camera

    async def get_assignments_for_camera_code(self, camera_code: str) -> List[CameraAIProfileAssignment]:
        stmt = select(CameraAIProfileAssignment).where(CameraAIProfileAssignment.camera_code == camera_code)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_assignment(self, camera_id: uuid.UUID, profile_id: str) -> Optional[CameraAIProfileAssignment]:
        stmt = select(CameraAIProfileAssignment).where(
            CameraAIProfileAssignment.camera_id == camera_id,
            CameraAIProfileAssignment.profile_id == profile_id,
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_assignment_by_code(self, camera_code: str, profile_id: str) -> Optional[CameraAIProfileAssignment]:
        stmt = select(CameraAIProfileAssignment).where(
            CameraAIProfileAssignment.camera_code == camera_code,
            CameraAIProfileAssignment.profile_id == profile_id,
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_all_active_assignments(self) -> List[CameraAIProfileAssignment]:
        stmt = select(CameraAIProfileAssignment).where(CameraAIProfileAssignment.enabled == True)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
