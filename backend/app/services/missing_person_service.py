from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.missing_person import MissingPersonCase
from app.schemas.missing_person import MissingPersonCaseRead, MissingPersonCreate, MissingPersonUpdate


class MissingPersonService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_cases(self, status_filter: Optional[str] = None) -> List[MissingPersonCaseRead]:
        stmt = select(MissingPersonCase)
        if status_filter and status_filter.lower() != "all":
            stmt = stmt.where(MissingPersonCase.status == status_filter.lower())
        stmt = stmt.order_by(MissingPersonCase.reported_at.desc())
        result = await self.db.execute(stmt)
        cases = list(result.scalars().all())

        return [
            MissingPersonCaseRead(
                id=c.case_code,
                name=c.name,
                age=c.age,
                gender=c.gender,
                reportedAt=c.reported_at,
                lastSeenTime=c.last_seen_time,
                lastKnownZone=c.last_known_zone_code,
                lastSeenCamera=c.last_seen_camera_code,
                description=c.description,
                status=c.status,
                candidateMatches=c.candidate_matches if isinstance(c.candidate_matches, list) else [],
                notes=c.notes,
                referenceImage=c.reference_image_path,
            )
            for c in cases
        ]

    async def get_case_by_code(self, case_code: str) -> MissingPersonCaseRead:
        stmt = select(MissingPersonCase).where(MissingPersonCase.case_code == case_code)
        result = await self.db.execute(stmt)
        c = result.scalars().first()
        if not c:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CASE_NOT_FOUND", "message": f"Missing person case {case_code} not found"},
            )
        return MissingPersonCaseRead(
            id=c.case_code,
            name=c.name,
            age=c.age,
            gender=c.gender,
            reportedAt=c.reported_at,
            lastSeenTime=c.last_seen_time,
            lastKnownZone=c.last_known_zone_code,
            lastSeenCamera=c.last_seen_camera_code,
            description=c.description,
            status=c.status,
            candidateMatches=c.candidate_matches if isinstance(c.candidate_matches, list) else [],
            notes=c.notes,
            referenceImage=c.reference_image_path,
        )
