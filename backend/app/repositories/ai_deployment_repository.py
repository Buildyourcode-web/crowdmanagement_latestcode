"""
ai_deployment_repository.py — Data Access Layer for AIPipelineDeployment.

Provides CRUD operations, state persistence queries, and lookup methods
for managing camera AI deployments across all pipeline types.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_deployment import AIPipelineDeployment
from app.repositories.base_repository import BaseRepository


class AIDeploymentRepository(BaseRepository[AIPipelineDeployment]):
    """Repository handling database operations for AIPipelineDeployment."""

    def __init__(self, db: AsyncSession):
        super().__init__(AIPipelineDeployment, db)

    async def get_by_camera_id(self, camera_id: uuid.UUID) -> Optional[AIPipelineDeployment]:
        """Retrieves deployment record for a camera."""
        stmt = select(AIPipelineDeployment).where(AIPipelineDeployment.camera_id == camera_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_by_camera_code(self, camera_code: str) -> Optional[AIPipelineDeployment]:
        """Retrieves deployment record by camera_code."""
        stmt = select(AIPipelineDeployment).where(AIPipelineDeployment.camera_code == camera_code)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_by_camera_and_profile(
        self, camera_id: uuid.UUID, profile_id: str
    ) -> Optional[AIPipelineDeployment]:
        """Retrieves deployment record for a specific (camera, profile) pair."""
        stmt = select(AIPipelineDeployment).where(
            AIPipelineDeployment.camera_id == camera_id,
            AIPipelineDeployment.profile_id == profile_id,
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_all(
        self,
        pipeline_type: Optional[str] = None,
        desired_state: Optional[str] = None,
        actual_state: Optional[str] = None,
    ) -> List[AIPipelineDeployment]:
        """Lists deployments with optional filtering."""
        stmt = select(AIPipelineDeployment)
        if pipeline_type:
            stmt = stmt.where(AIPipelineDeployment.pipeline_type == pipeline_type.upper())
        if desired_state:
            stmt = stmt.where(AIPipelineDeployment.desired_state == desired_state.upper())
        if actual_state:
            stmt = stmt.where(AIPipelineDeployment.actual_state == actual_state.upper())
        stmt = stmt.order_by(AIPipelineDeployment.camera_code)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_desired_state(self, desired_state: str) -> List[AIPipelineDeployment]:
        """Lists deployments matching a desired state (e.g., 'RUNNING' for startup recovery)."""
        stmt = (
            select(AIPipelineDeployment)
            .where(AIPipelineDeployment.desired_state == desired_state.upper())
            .order_by(AIPipelineDeployment.camera_code)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def upsert_deployment(
        self,
        camera_id: uuid.UUID,
        camera_code: str,
        profile_id: str,
        pipeline_type: str,
        desired_state: str = "STOPPED",
        actual_state: str = "STOPPED",
        health_state: str = "UNKNOWN",
        priority: str = "NORMAL",
        created_by: str = "SYSTEM",
        updated_by: str = "SYSTEM",
    ) -> AIPipelineDeployment:
        """Finds or creates a deployment record."""
        existing = await self.get_by_camera_and_profile(camera_id, profile_id)
        if existing:
            existing.camera_code = camera_code
            existing.pipeline_type = pipeline_type
            existing.desired_state = desired_state
            existing.actual_state = actual_state
            existing.health_state = health_state
            existing.priority = priority
            existing.updated_by = updated_by
            existing.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
            return existing

        deployment = AIPipelineDeployment(
            camera_id=camera_id,
            camera_code=camera_code,
            profile_id=profile_id,
            pipeline_type=pipeline_type,
            desired_state=desired_state,
            actual_state=actual_state,
            health_state=health_state,
            priority=priority,
            created_by=created_by,
            updated_by=updated_by,
        )
        self.db.add(deployment)
        await self.db.flush()
        return deployment
