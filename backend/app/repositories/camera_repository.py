import uuid
from typing import List, Optional, Tuple
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.camera import Camera
from app.repositories.base_repository import BaseRepository


class CameraRepository(BaseRepository[Camera]):
    def __init__(self, db: AsyncSession):
        super().__init__(Camera, db)

    async def get_by_code(self, camera_code: str, active_only: bool = True) -> Optional[Camera]:
        """Find camera by camera_code or by primary UUID id."""
        stmt = select(Camera).where(Camera.camera_code == camera_code)
        if active_only:
            stmt = stmt.where(Camera.is_active == True, Camera.status != "removed")
        result = await self.db.execute(stmt)
        cam = result.scalars().first()
        if cam:
            return cam

        if isinstance(camera_code, str) and ("-FRS" in camera_code or "-CROWD" in camera_code):
            base_code = camera_code.replace("-FRS", "").replace("-CROWD", "")
            stmt_base = select(Camera).where(Camera.camera_code == base_code)
            if active_only:
                stmt_base = stmt_base.where(Camera.is_active == True, Camera.status != "removed")
            res_base = await self.db.execute(stmt_base)
            cam = res_base.scalars().first()
            if cam:
                return cam

        # Fallback: check if camera_code is a valid UUID
        try:
            val_uuid = uuid.UUID(camera_code)
            stmt_uuid = select(Camera).where(Camera.id == val_uuid)
            if active_only:
                stmt_uuid = stmt_uuid.where(Camera.is_active == True, Camera.status != "removed")
            res_uuid = await self.db.execute(stmt_uuid)
            return res_uuid.scalars().first()
        except (ValueError, TypeError):
            return None

    async def get_by_camera_code(self, camera_code: str, active_only: bool = True) -> Optional[Camera]:
        """Alias for get_by_code."""
        return await self.get_by_code(camera_code, active_only=active_only)

    async def get_by_ip(self, ip: str) -> Optional[Camera]:
        """Find camera by its private IP address."""
        if not ip:
            return None
        stmt = select(Camera).where(Camera.private_ip == ip.strip(), Camera.is_active == True, Camera.status != "removed")
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def find_duplicate(
        self,
        camera_code: str,
        private_ip: Optional[str] = None,
        rtsp_url_encrypted: Optional[str] = None,
        exclude_camera_code: Optional[str] = None,
    ) -> Optional[Tuple[str, str]]:
        """
        Checks for accidental duplicate registration among active cameras.
        Returns tuple of (conflicting_field, existing_camera_code) or None.
        """
        # 1. Check camera_code
        stmt = select(Camera).where(Camera.camera_code == camera_code, Camera.is_active == True, Camera.status != "removed")
        if exclude_camera_code:
            stmt = stmt.where(Camera.camera_code != exclude_camera_code)
        res = await self.db.execute(stmt)
        existing = res.scalars().first()
        if existing:
            return "camera_id", existing.camera_code

        # 2. Check private IP
        if private_ip and private_ip.strip():
            stmt_ip = select(Camera).where(Camera.private_ip == private_ip.strip(), Camera.is_active == True, Camera.status != "removed")
            if exclude_camera_code:
                stmt_ip = stmt_ip.where(Camera.camera_code != exclude_camera_code)
            res_ip = await self.db.execute(stmt_ip)
            existing_ip = res_ip.scalars().first()
            if existing_ip:
                return "private_ip", existing_ip.camera_code

        # 3. Check RTSP URL if provided
        if rtsp_url_encrypted and rtsp_url_encrypted.strip():
            stmt_url = select(Camera).where(Camera.rtsp_url_encrypted == rtsp_url_encrypted.strip(), Camera.is_active == True, Camera.status != "removed")
            if exclude_camera_code:
                stmt_url = stmt_url.where(Camera.camera_code != exclude_camera_code)
            res_url = await self.db.execute(stmt_url)
            existing_url = res_url.scalars().first()
            if existing_url:
                return "rtsp_url", existing_url.camera_code

        return None

    async def list_cameras(
        self,
        zone_code: Optional[str] = None,
        status: Optional[str] = None,
        camera_type: Optional[str] = None,
        is_frs: Optional[bool] = None,
        search: Optional[str] = None,
        enabled_only: Optional[bool] = None,
        event_id: Optional[uuid.UUID] = None,
        allowed_site_ids: Optional[List[uuid.UUID]] = None,
        skip: int = 0,
        limit: int = 100,
        include_removed: bool = False,
    ) -> Tuple[List[Camera], int]:
        stmt = select(Camera)

        # 1. Lifecycle filter: Exclude removed/inactive cameras by default
        if not include_removed:
            stmt = stmt.where(Camera.is_active == True, Camera.status != "removed")

        # 2. Strict Event Scoping: NO cross-event leakage!
        if event_id is not None:
            stmt = stmt.where(Camera.event_id == event_id)
        if allowed_site_ids is not None:
            stmt = stmt.where(Camera.site_id.in_(allowed_site_ids))

        if zone_code and zone_code.upper() != "ALL":
            stmt = stmt.where(Camera.zone_code == zone_code)
        if status and status.lower() != "all":
            # Match either stream_status or operational status
            stat_val = status.lower()
            stmt = stmt.where(
                or_(
                    Camera.status == stat_val,
                    Camera.stream_status == status.upper(),
                )
            )
        if camera_type and camera_type.upper() != "ALL":
            stmt = stmt.where(Camera.camera_type == camera_type.upper())
        if is_frs is not None:
            stmt = stmt.where(Camera.is_frs_camera == is_frs)
        if enabled_only is not None:
            stmt = stmt.where(Camera.enabled == enabled_only)
        if search:
            q = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Camera.camera_code.ilike(q),
                    Camera.label.ilike(q),
                    Camera.name.ilike(q),
                    Camera.private_ip.ilike(q),
                    Camera.location_name.ilike(q),
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        stmt = stmt.order_by(Camera.camera_code.asc()).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total
