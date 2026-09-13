import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.event import Event
from app.models.site import Site
from app.models.camera import Camera
from app.models.alert import Alert
from app.models.crowd import CrowdSnapshot
from app.models.user import User
from app.models.user_access import UserEventAccess
from app.schemas.event import EventCreate, EventRead, EventSummary, EventUpdate


def _normalize_dt(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure datetime has UTC timezone for reliable comparison."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class EventService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _evaluate_timing_lifecycle(self, e: Event, now_utc: datetime) -> bool:
        """
        Auto-transitions event status based on operational start_date and end_date:
        - If SCHEDULED and now >= start_date and now <= end_date -> ACTIVE
        - If SCHEDULED, ACTIVE, or LIVE and now > end_date -> COMPLETED
        Returns True if status changed.
        """
        if not e.start_date or not e.end_date:
            return False
        # Do not override manual operator overrides (DRAFT, PAUSED, ARCHIVED)
        if e.status in ("DRAFT", "PAUSED", "ARCHIVED"):
            return False

        s_utc = _normalize_dt(e.start_date)
        e_utc = _normalize_dt(e.end_date)
        if not s_utc or not e_utc:
            return False

        changed = False
        if e.status == "SCHEDULED" and s_utc <= now_utc <= e_utc:
            e.status = "ACTIVE"
            e.is_active = True
            changed = True
        elif e.status in ("SCHEDULED", "ACTIVE", "LIVE") and now_utc > e_utc:
            e.status = "COMPLETED"
            e.is_active = False
            changed = True
        return changed

    async def list_accessible_events(self, user: User) -> List[EventRead]:
        """Lists events the user has explicit or superadmin access to."""
        is_super = user.is_super_admin

        if is_super:
            stmt = select(Event).order_by(Event.is_active.desc(), Event.start_date.desc())
            res = await self.db.execute(stmt)
            events = res.scalars().all()
            access_roles = {e.id: "SUPER_ADMIN" for e in events}
        else:
            stmt = (
                select(Event, UserEventAccess.access_role)
                .join(UserEventAccess, UserEventAccess.event_id == Event.id)
                .where(
                    UserEventAccess.user_id == user.id,
                    UserEventAccess.is_active == True,
                )
                .order_by(Event.is_active.desc(), Event.start_date.desc())
            )
            res = await self.db.execute(stmt)
            rows = res.all()
            events = [row[0] for row in rows]
            access_roles = {row[0].id: row[1] for row in rows}

        if not events:
            return []

        # Automatic lifecycle evaluation based on real-world operational timings
        now_utc = datetime.now(timezone.utc)
        any_changed = False
        for e in events:
            if self._evaluate_timing_lifecycle(e, now_utc):
                any_changed = True
        if any_changed:
            await self.db.commit()

        event_ids = [e.id for e in events]

        # Aggregate site counts
        site_counts_stmt = (
            select(Site.event_id, func.count(Site.id))
            .where(Site.event_id.in_(event_ids))
            .group_by(Site.event_id)
        )
        site_counts_res = await self.db.execute(site_counts_stmt)
        site_map = dict(site_counts_res.all())

        # Aggregate camera counts
        cam_counts_stmt = (
            select(Camera.event_id, func.count(Camera.id))
            .where(Camera.event_id.in_(event_ids))
            .group_by(Camera.event_id)
        )
        cam_counts_res = await self.db.execute(cam_counts_stmt)
        cam_map = dict(cam_counts_res.all())

        # Aggregate active alert counts
        alert_counts_stmt = (
            select(Alert.event_id, func.count(Alert.id))
            .where(Alert.event_id.in_(event_ids), Alert.status == "ACTIVE")
            .group_by(Alert.event_id)
        )
        alert_counts_res = await self.db.execute(alert_counts_stmt)
        alert_map = dict(alert_counts_res.all())

        results = []
        for e in events:
            read_item = EventRead(
                id=e.id,
                code=e.code,
                name=e.name,
                description=e.description,
                year=e.year,
                start_date=e.start_date,
                end_date=e.end_date,
                status=e.status,
                is_active=e.is_active,
                timezone=e.timezone,
                location=e.location,
                city=e.city,
                state=e.state,
                country=e.country,
                latitude=e.latitude,
                longitude=e.longitude,
                created_at=e.created_at,
                updated_at=e.updated_at,
                created_by=e.created_by,
                updated_by=e.updated_by,
                site_count=site_map.get(e.id, 0),
                camera_count=cam_map.get(e.id, 0),
                active_alert_count=alert_map.get(e.id, 0),
                user_access_role=access_roles.get(e.id, "VIEWER"),
            )
            results.append(read_item)

        return results

    async def get_event_by_id(self, event_id: uuid.UUID, user: User) -> EventRead:
        stmt = select(Event).where(Event.id == event_id)
        res = await self.db.execute(stmt)
        e = res.scalars().first()
        if not e:
            raise HTTPException(status_code=404, detail="Event not found")

        # Automatic lifecycle evaluation based on real-world operational timings
        now_utc = datetime.now(timezone.utc)
        if self._evaluate_timing_lifecycle(e, now_utc):
            await self.db.commit()
            await self.db.refresh(e)

        is_super = user.is_super_admin
        user_role = "SUPER_ADMIN"
        if not is_super:
            access_stmt = select(UserEventAccess).where(
                UserEventAccess.event_id == event_id,
                UserEventAccess.user_id == user.id,
                UserEventAccess.is_active == True,
            )
            access_res = await self.db.execute(access_stmt)
            acc = access_res.scalars().first()
            if not acc:
                raise HTTPException(status_code=403, detail="Access denied for this event")
            user_role = acc.access_role

        # Counts
        site_count = (await self.db.execute(select(func.count(Site.id)).where(Site.event_id == event_id))).scalar() or 0
        cam_count = (await self.db.execute(select(func.count(Camera.id)).where(Camera.event_id == event_id))).scalar() or 0
        alert_count = (await self.db.execute(select(func.count(Alert.id)).where(Alert.event_id == event_id, Alert.status == "ACTIVE"))).scalar() or 0

        return EventRead(
            id=e.id,
            code=e.code,
            name=e.name,
            description=e.description,
            year=e.year,
            start_date=e.start_date,
            end_date=e.end_date,
            status=e.status,
            is_active=e.is_active,
            timezone=e.timezone,
            location=e.location,
            city=e.city,
            state=e.state,
            country=e.country,
            latitude=e.latitude,
            longitude=e.longitude,
            created_at=e.created_at,
            updated_at=e.updated_at,
            created_by=e.created_by,
            updated_by=e.updated_by,
            site_count=site_count,
            camera_count=cam_count,
            active_alert_count=alert_count,
            user_access_role=user_role,
        )

    async def create_event(self, data: EventCreate, created_by: str) -> EventRead:
        # Check uniqueness of code
        existing = (await self.db.execute(select(Event).where(Event.code == data.code))).scalars().first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Event code '{data.code}' already exists")

        now_utc = datetime.now(timezone.utc)
        s_utc = _normalize_dt(data.start_date)
        e_utc = _normalize_dt(data.end_date)

        status_val = data.status
        is_active_val = data.is_active
        # Auto-activate if operational timing is current
        if status_val == "SCHEDULED" and s_utc and e_utc:
            if s_utc <= now_utc <= e_utc:
                status_val = "ACTIVE"
                is_active_val = True
            elif now_utc > e_utc:
                status_val = "COMPLETED"
                is_active_val = False

        new_event = Event(
            code=data.code.upper(),
            name=data.name,
            description=data.description,
            year=data.year,
            start_date=data.start_date,
            end_date=data.end_date,
            status=status_val,
            is_active=is_active_val,
            timezone=data.timezone,
            location=data.location,
            city=data.city,
            state=data.state,
            country=data.country,
            latitude=data.latitude,
            longitude=data.longitude,
            created_by=created_by,
            updated_by=created_by,
        )
        self.db.add(new_event)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(new_event)

        return EventRead(
            id=new_event.id,
            code=new_event.code,
            name=new_event.name,
            description=new_event.description,
            year=new_event.year,
            start_date=new_event.start_date,
            end_date=new_event.end_date,
            status=new_event.status,
            is_active=new_event.is_active,
            timezone=new_event.timezone,
            location=new_event.location,
            city=new_event.city,
            state=new_event.state,
            country=new_event.country,
            latitude=new_event.latitude,
            longitude=new_event.longitude,
            created_at=new_event.created_at,
            updated_at=new_event.updated_at,
            created_by=new_event.created_by,
            updated_by=new_event.updated_by,
            site_count=0,
            camera_count=0,
            active_alert_count=0,
            user_access_role="SUPER_ADMIN",
        )

    async def update_event(self, event_id: uuid.UUID, data: EventUpdate, updated_by: str) -> EventRead:
        stmt = select(Event).where(Event.id == event_id)
        res = await self.db.execute(stmt)
        e = res.scalars().first()
        if not e:
            raise HTTPException(status_code=404, detail="Event not found")

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(e, key, value)
        e.updated_by = updated_by

        await self.db.commit()
        await self.db.refresh(e)

        site_count = (await self.db.execute(select(func.count(Site.id)).where(Site.event_id == event_id))).scalar() or 0
        cam_count = (await self.db.execute(select(func.count(Camera.id)).where(Camera.event_id == event_id))).scalar() or 0
        alert_count = (await self.db.execute(select(func.count(Alert.id)).where(Alert.event_id == event_id, Alert.status == "ACTIVE"))).scalar() or 0

        return EventRead(
            id=e.id,
            code=e.code,
            name=e.name,
            description=e.description,
            year=e.year,
            start_date=e.start_date,
            end_date=e.end_date,
            status=e.status,
            is_active=e.is_active,
            timezone=e.timezone,
            location=e.location,
            city=e.city,
            state=e.state,
            country=e.country,
            latitude=e.latitude,
            longitude=e.longitude,
            created_at=e.created_at,
            updated_at=e.updated_at,
            created_by=e.created_by,
            updated_by=e.updated_by,
            site_count=site_count,
            camera_count=cam_count,
            active_alert_count=alert_count,
            user_access_role="MANAGER",
        )

    async def archive_event(self, event_id: uuid.UUID, updated_by: str) -> dict:
        stmt = select(Event).where(Event.id == event_id)
        res = await self.db.execute(stmt)
        e = res.scalars().first()
        if not e:
            raise HTTPException(status_code=404, detail="Event not found")

        e.status = "ARCHIVED"
        e.is_active = False
        e.updated_by = updated_by
        await self.db.commit()
        return {"event_id": str(event_id), "status": "ARCHIVED", "is_active": False}