import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy import and_, func, or_, select, String
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.frs import FRSAuditLog, FRSCandidate, FRSReferenceProfile, FRSReview
from app.repositories.base_repository import BaseRepository


class FRSRepository(BaseRepository[FRSCandidate]):
    def __init__(self, db: AsyncSession):
        super().__init__(FRSCandidate, db)

    async def get_by_code(self, code: str) -> Optional[FRSCandidate]:
        stmt = select(FRSCandidate).where(FRSCandidate.candidate_code == code)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_candidates(
        self,
        status: Optional[str] = None,
        camera_id: Optional[str] = None,
        zone: Optional[str] = None,
        min_score: Optional[float] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[FRSCandidate], int]:
        stmt = select(FRSCandidate)

        if status and status.upper() != "ALL":
            stmt = stmt.where(FRSCandidate.status == status.upper())
        if camera_id and camera_id.upper() != "ALL":
            stmt = stmt.where(FRSCandidate.camera_code == camera_id)
        if zone and zone.upper() != "ALL":
            stmt = stmt.where(FRSCandidate.zone_code == zone)
        if min_score is not None and min_score > 0:
            stmt = stmt.where(FRSCandidate.match_score >= min_score)
        if search:
            q = f"%{search}%"
            stmt = stmt.where(or_(
                FRSCandidate.candidate_code.ilike(q),
                FRSCandidate.camera_name.ilike(q),
                FRSCandidate.location.ilike(q),
            ))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(FRSCandidate.detected_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total

    async def count_reference_profiles(self, active_only: bool = True) -> int:
        stmt = select(func.count(FRSReferenceProfile.id))
        if active_only:
            stmt = stmt.where(FRSReferenceProfile.status == "ACTIVE")
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def list_reference_profiles(self, active_only: bool = False) -> List[FRSReferenceProfile]:
        stmt = select(FRSReferenceProfile)
        if active_only:
            stmt = stmt.where(FRSReferenceProfile.status == "ACTIVE")
        stmt = stmt.order_by(FRSReferenceProfile.reference_id.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_reference_profile_by_id(self, ref_id: str) -> Optional[FRSReferenceProfile]:
        # Support UUID or reference_id or reference_code
        stmt = select(FRSReferenceProfile).where(
            or_(
                FRSReferenceProfile.reference_id == ref_id,
                FRSReferenceProfile.reference_code == ref_id,
                func.cast(FRSReferenceProfile.id, String) == ref_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def create_reference_profile(
        self,
        reference_id: str,
        display_name: str,
        reference_image_path: str,
        embedding_vector: Optional[List[float]] = None,
        category: str = "Authorized Watchlist",
        embedding_model: str = "buffalo_l",
        embedding_version: str = "1.0.0",
        created_by: Optional[str] = None,
    ) -> FRSReferenceProfile:
        profile = FRSReferenceProfile(
            reference_id=reference_id,
            reference_code=reference_id,
            display_name=display_name,
            category=category,
            status="ACTIVE",
            active=True,
            reference_image_path=reference_image_path,
            embedding_vector=embedding_vector,
            embedding_model=embedding_model,
            embedding_version=embedding_version,
            created_by=created_by,
            last_updated_date=datetime.now(timezone.utc).strftime("%d %b %Y"),
        )
        self.db.add(profile)
        await self.db.flush()
        return profile

    async def update_reference_profile(
        self,
        ref_id: str,
        display_name: Optional[str] = None,
        category: Optional[str] = None,
        active: Optional[bool] = None,
    ) -> Optional[FRSReferenceProfile]:
        profile = await self.get_reference_profile_by_id(ref_id)
        if not profile:
            return None
        if display_name is not None:
            profile.display_name = display_name
        if category is not None:
            profile.category = category
        if active is not None:
            profile.active = active
            profile.status = "ACTIVE" if active else "INACTIVE"
        profile.last_updated_date = datetime.now(timezone.utc).strftime("%d %b %Y")
        await self.db.flush()
        return profile

    async def deactivate_reference_profile(self, ref_id: str) -> Optional[FRSReferenceProfile]:
        return await self.update_reference_profile(ref_id, active=False)

    async def get_expired_candidates(self, cutoff: datetime) -> List[FRSCandidate]:
        stmt = select(FRSCandidate).where(
            or_(
                FRSCandidate.expires_at <= cutoff,
                and_(FRSCandidate.expires_at.is_(None), FRSCandidate.detected_at <= cutoff),
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def delete_candidate(self, candidate: FRSCandidate) -> None:
        await self.db.delete(candidate)
        await self.db.flush()

    async def create_audit_log(
        self,
        candidate_code: str,
        reference_id: str,
        action: str,
        officer_name: str,
        details: Optional[str] = None,
    ) -> FRSAuditLog:
        audit_code = f"AUDIT-FRS-{int(datetime.now(timezone.utc).timestamp())}-{uuid.uuid4().hex[:6].upper()}"
        log = FRSAuditLog(
            audit_code=audit_code,
            candidate_code=candidate_code,
            reference_id=reference_id,
            action=action,
            officer_name=officer_name,
            timestamp=datetime.now(timezone.utc),
            details=details,
        )
        self.db.add(log)
        await self.db.flush()
        return log
