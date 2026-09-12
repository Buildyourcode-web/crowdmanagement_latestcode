import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.user import User
from app.models.event import Event
from app.models.site import Site
from app.models.user_access import UserEventAccess, UserSiteAccess
from app.schemas.event_access import (
    UserEventAccessCreate,
    UserEventAccessRead,
    UserEventAccessUpdate,
    UserSiteAccessCreate,
    UserSiteAccessRead,
)


class EventAccessService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_event_users(self, event_id: uuid.UUID) -> List[UserEventAccessRead]:
        stmt = (
            select(UserEventAccess, User.username, User.full_name, User.email)
            .join(User, User.id == UserEventAccess.user_id)
            .where(UserEventAccess.event_id == event_id)
            .order_by(User.full_name.asc())
        )
        res = await self.db.execute(stmt)
        rows = res.all()

        return [
            UserEventAccessRead(
                id=acc.id,
                user_id=acc.user_id,
                event_id=acc.event_id,
                access_role=acc.access_role,
                is_active=acc.is_active,
                granted_by=acc.granted_by,
                created_at=acc.created_at,
                username=username,
                full_name=full_name,
                email=email,
            )
            for acc, username, full_name, email in rows
        ]

    async def grant_user_event_access(
        self,
        event_id: uuid.UUID,
        data: UserEventAccessCreate,
        granted_by: str,
    ) -> UserEventAccessRead:
        # Verify user exists
        u = (await self.db.execute(select(User).where(User.id == data.user_id))).scalars().first()
        if not u:
            raise HTTPException(status_code=404, detail="User not found")

        # Check if access already exists
        existing = (
            await self.db.execute(
                select(UserEventAccess).where(
                    UserEventAccess.user_id == data.user_id,
                    UserEventAccess.event_id == event_id,
                )
            )
        ).scalars().first()

        if existing:
            existing.access_role = data.access_role
            existing.is_active = True
            existing.granted_by = granted_by
            await self.db.commit()
            await self.db.refresh(existing)
            record = existing
        else:
            record = UserEventAccess(
                user_id=data.user_id,
                event_id=event_id,
                access_role=data.access_role,
                is_active=True,
                granted_by=granted_by,
            )
            self.db.add(record)
            await self.db.commit()
            await self.db.refresh(record)

        return UserEventAccessRead(
            id=record.id,
            user_id=record.user_id,
            event_id=record.event_id,
            access_role=record.access_role,
            is_active=record.is_active,
            granted_by=record.granted_by,
            created_at=record.created_at,
            username=u.username,
            full_name=u.full_name,
            email=u.email,
        )

    async def revoke_user_event_access(self, event_id: uuid.UUID, user_id: uuid.UUID) -> dict:
        stmt = select(UserEventAccess).where(
            UserEventAccess.event_id == event_id,
            UserEventAccess.user_id == user_id,
        )
        res = await self.db.execute(stmt)
        record = res.scalars().first()
        if not record:
            raise HTTPException(status_code=404, detail="User event access record not found")

        # Also revoke any user site access for this event
        site_stmt = select(UserSiteAccess).where(
            UserSiteAccess.event_id == event_id,
            UserSiteAccess.user_id == user_id,
        )
        site_res = await self.db.execute(site_stmt)
        for sa in site_res.scalars().all():
            await self.db.delete(sa)

        await self.db.delete(record)
        await self.db.commit()
        return {"event_id": str(event_id), "user_id": str(user_id), "revoked": True}

    async def list_user_site_accesses(
        self,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> List[UserSiteAccessRead]:
        stmt = (
            select(UserSiteAccess, Site.site_code, Site.site_name)
            .join(Site, Site.id == UserSiteAccess.site_id)
            .where(
                UserSiteAccess.event_id == event_id,
                UserSiteAccess.user_id == user_id,
            )
        )
        res = await self.db.execute(stmt)
        rows = res.all()

        return [
            UserSiteAccessRead(
                id=sa.id,
                user_id=sa.user_id,
                event_id=sa.event_id,
                site_id=sa.site_id,
                is_active=sa.is_active,
                granted_by=sa.granted_by,
                created_at=sa.created_at,
                site_code=code,
                site_name=name,
            )
            for sa, code, name in rows
        ]

    async def set_user_site_accesses(
        self,
        event_id: uuid.UUID,
        user_id: uuid.UUID,
        site_ids: List[uuid.UUID],
        granted_by: str,
    ) -> List[UserSiteAccessRead]:
        # Clear existing
        del_stmt = select(UserSiteAccess).where(
            UserSiteAccess.event_id == event_id,
            UserSiteAccess.user_id == user_id,
        )
        del_res = await self.db.execute(del_stmt)
        for old in del_res.scalars().all():
            await self.db.delete(old)

        new_records = []
        for sid in site_ids:
            rec = UserSiteAccess(
                event_id=event_id,
                user_id=user_id,
                site_id=sid,
                is_active=True,
                granted_by=granted_by,
            )
            self.db.add(rec)
            new_records.append(rec)

        await self.db.commit()
        return await self.list_user_site_accesses(event_id, user_id)