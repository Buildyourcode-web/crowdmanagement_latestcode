import uuid
from typing import List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models.site import Site
from app.models.camera import Camera
from app.models.alert import Alert
from app.models.user import User
from app.schemas.site import SiteCreate, SiteRead, SiteUpdate


class SiteService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_sites(
        self,
        event_id: uuid.UUID,
        allowed_site_ids: Optional[List[uuid.UUID]] = None,
    ) -> List[SiteRead]:
        stmt = select(Site).where(Site.event_id == event_id)
        if allowed_site_ids is not None:
            stmt = stmt.where(Site.id.in_(allowed_site_ids))
        stmt = stmt.order_by(Site.site_code.asc())

        res = await self.db.execute(stmt)
        sites = res.scalars().all()
        if not sites:
            return []

        site_ids = [s.id for s in sites]

        # Aggregate camera counts per site
        cam_stmt = (
            select(
                Camera.site_id,
                func.count(Camera.id).label("total"),
                func.count(Camera.id).filter(Camera.status == "online").label("online"),
            )
            .where(Camera.site_id.in_(site_ids))
            .group_by(Camera.site_id)
        )
        cam_res = await self.db.execute(cam_stmt)
        cam_map = {row[0]: (row[1], row[2]) for row in cam_res.all()}

        results = []
        for s in sites:
            total_cams, online_cams = cam_map.get(s.id, (0, 0))
            results.append(
                SiteRead(
                    id=s.id,
                    event_id=s.event_id,
                    site_code=s.site_code,
                    site_name=s.site_name,
                    description=s.description,
                    location=s.location,
                    latitude=s.latitude,
                    longitude=s.longitude,
                    is_active=s.is_active,
                    status=s.status,
                    created_at=s.created_at,
                    updated_at=s.updated_at,
                    created_by=s.created_by,
                    updated_by=s.updated_by,
                    camera_count=total_cams,
                    online_camera_count=online_cams,
                    active_alert_count=0,
                    current_people=0,
                )
            )

        return results

    async def get_site_by_id(self, site_id: uuid.UUID) -> SiteRead:
        stmt = select(Site).where(Site.id == site_id)
        res = await self.db.execute(stmt)
        s = res.scalars().first()
        if not s:
            raise HTTPException(status_code=404, detail="Site not found")

        total_cams = (await self.db.execute(select(func.count(Camera.id)).where(Camera.site_id == site_id))).scalar() or 0
        online_cams = (await self.db.execute(select(func.count(Camera.id)).where(Camera.site_id == site_id, Camera.status == "online"))).scalar() or 0

        return SiteRead(
            id=s.id,
            event_id=s.event_id,
            site_code=s.site_code,
            site_name=s.site_name,
            description=s.description,
            location=s.location,
            latitude=s.latitude,
            longitude=s.longitude,
            is_active=s.is_active,
            status=s.status,
            created_at=s.created_at,
            updated_at=s.updated_at,
            created_by=s.created_by,
            updated_by=s.updated_by,
            camera_count=total_cams,
            online_camera_count=online_cams,
            active_alert_count=0,
            current_people=0,
        )

    async def create_site(self, event_id: uuid.UUID, data: SiteCreate, created_by: str) -> SiteRead:
        # Check uniqueness of site_code within this event
        existing = (
            await self.db.execute(
                select(Site).where(Site.event_id == event_id, Site.site_code == data.site_code)
            )
        ).scalars().first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Site code '{data.site_code}' already exists in this event",
            )

        new_site = Site(
            event_id=event_id,
            site_code=data.site_code.upper(),
            site_name=data.site_name,
            description=data.description,
            location=data.location,
            latitude=data.latitude,
            longitude=data.longitude,
            is_active=data.is_active,
            status=data.status,
            created_by=created_by,
            updated_by=created_by,
        )
        self.db.add(new_site)
        await self.db.commit()
        await self.db.refresh(new_site)

        return SiteRead(
            id=new_site.id,
            event_id=new_site.event_id,
            site_code=new_site.site_code,
            site_name=new_site.site_name,
            description=new_site.description,
            location=new_site.location,
            latitude=new_site.latitude,
            longitude=new_site.longitude,
            is_active=new_site.is_active,
            status=new_site.status,
            created_at=new_site.created_at,
            updated_at=new_site.updated_at,
            created_by=new_site.created_by,
            updated_by=new_site.updated_by,
            camera_count=0,
            online_camera_count=0,
            active_alert_count=0,
            current_people=0,
        )

    async def update_site(self, site_id: uuid.UUID, data: SiteUpdate, updated_by: str) -> SiteRead:
        stmt = select(Site).where(Site.id == site_id)
        res = await self.db.execute(stmt)
        s = res.scalars().first()
        if not s:
            raise HTTPException(status_code=404, detail="Site not found")

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(s, key, value)
        s.updated_by = updated_by

        await self.db.commit()
        await self.db.refresh(s)

        total_cams = (await self.db.execute(select(func.count(Camera.id)).where(Camera.site_id == site_id))).scalar() or 0
        online_cams = (await self.db.execute(select(func.count(Camera.id)).where(Camera.site_id == site_id, Camera.status == "online"))).scalar() or 0

        return SiteRead(
            id=s.id,
            event_id=s.event_id,
            site_code=s.site_code,
            site_name=s.site_name,
            description=s.description,
            location=s.location,
            latitude=s.latitude,
            longitude=s.longitude,
            is_active=s.is_active,
            status=s.status,
            created_at=s.created_at,
            updated_at=s.updated_at,
            created_by=s.created_by,
            updated_by=s.updated_by,
            camera_count=total_cams,
            online_camera_count=online_cams,
            active_alert_count=0,
            current_people=0,
        )

    async def delete_site(self, site_id: uuid.UUID) -> dict:
        stmt = select(Site).where(Site.id == site_id)
        res = await self.db.execute(stmt)
        s = res.scalars().first()
        if not s:
            raise HTTPException(status_code=404, detail="Site not found")

        # Unassign cameras from this site before deletion
        cams_stmt = select(Camera).where(Camera.site_id == site_id)
        cams_res = await self.db.execute(cams_stmt)
        for cam in cams_res.scalars().all():
            cam.site_id = None

        await self.db.delete(s)
        await self.db.commit()
        return {"site_id": str(site_id), "deleted": True}