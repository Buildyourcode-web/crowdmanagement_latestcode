import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.camera import Camera
from app.models.zone import Zone
from app.redis.event_bus import event_bus
from app.repositories.camera_repository import CameraRepository
from app.schemas.camera import (
    BulkCameraImportRequest,
    BulkCameraImportResult,
    BulkCameraRow,
    BulkCameraValidateResult,
    CameraCreate,
    CameraHealth,
    CameraRead,
    CameraStatsResponse,
    CameraUpdate,
    RTSPTestRequest,
    RTSPTestResponse,
)
from app.security.encryption import (
    build_authenticated_rtsp_url,
    decrypt_credential,
    encrypt_credential,
    extract_credentials_from_url,
    sanitize_rtsp_url,
    strip_credentials_from_url,
)
import asyncio
import time
from app.ai.pipelines.crowd.registry import CrowdPipelineRegistry
from app.ai.pipelines.queue.registry import QueuePipelineRegistry
from app.ai.pipelines.frs.registry import FRSPipelineRegistry
from app.frs_engine.frs_service import is_frs_worker_running
from app.services.rtsp_test_service import RTSPTestService

_stats_cache: Optional[CameraStatsResponse] = None
_stats_cache_time: float = 0.0
_is_refreshing_stats = False
_STATS_TTL: float = 10.0


async def _background_refresh_camera_stats():
    global _is_refreshing_stats
    try:
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            srv = CameraService(session)
            await srv._fetch_and_cache_direct()
    except Exception:
        pass
    finally:
        _is_refreshing_stats = False


class CameraService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.camera_repo = CameraRepository(db)

    def _build_camera_read(self, c: Camera) -> CameraRead:
        """Constructs CameraRead schema, strictly sanitizing URLs and omitting passwords."""
        # Decrypt stored RTSP URL and sanitize it
        raw_rtsp = decrypt_credential(c.rtsp_url_encrypted) if c.rtsp_url_encrypted else None
        sanitized_rtsp = sanitize_rtsp_url(raw_rtsp) if raw_rtsp else None

        coords = c.coordinates if isinstance(c.coordinates, list) and len(c.coordinates) >= 2 else [78.4635, 17.4175]

        # Determine exclusive AI runtime mode and logical IDs
        cam_code = c.camera_code
        crowd_pipe = CrowdPipelineRegistry.get(cam_code)
        is_crowd_running = crowd_pipe is not None and getattr(crowd_pipe, "state", None) is not None and getattr(crowd_pipe.state, "value", str(crowd_pipe.state)) == "RUNNING"
        queue_pipe = QueuePipelineRegistry.get(cam_code)
        is_queue_running = queue_pipe is not None and getattr(queue_pipe, "state", None) is not None and getattr(queue_pipe.state, "value", str(queue_pipe.state)) == "RUNNING"
        frs_pipe = FRSPipelineRegistry.get(cam_code)
        is_frs_pipe_running = frs_pipe is not None and getattr(frs_pipe, "state", None) is not None and getattr(frs_pipe.state, "value", str(frs_pipe.state)) == "RUNNING"
        is_frs_running = is_frs_pipe_running or is_frs_worker_running(cam_code) or (c.id and is_frs_worker_running(str(c.id)))

        if is_crowd_running or is_queue_running:
            ai_mode = "CROWD_ACTIVE"
            crowd_status = "RUNNING"
            frs_status = "DISCONNECTED"
        elif is_frs_running:
            ai_mode = "FRS_ACTIVE"
            frs_status = "RUNNING"
            crowd_status = "DISCONNECTED"
        else:
            ai_mode = "IDLE"
            frs_status = "DISCONNECTED"
            crowd_status = "DISCONNECTED"

        return CameraRead(
            id=c.camera_code,
            camera_code=c.camera_code,
            name=c.name,
            label=c.label,
            description=c.description,
            camera_type=c.camera_type,
            private_ip=c.private_ip,
            port=c.port or 554,
            rtsp_url=sanitized_rtsp,
            username=c.username,
            codec=c.codec or "h264",
            protocol=c.protocol or "rtsp",
            zone=c.zone_code,
            zone_id=c.zone_id,
            location_name=c.location_name,
            latitude=c.latitude,
            longitude=c.longitude,
            coordinates=coords,
            status=c.status,
            ai_status=c.ai_status,
            stream_status=c.stream_status or "NOT_TESTED",
            stream_stability=c.stream_stability or "UNKNOWN",
            enabled=c.enabled,
            is_frs_camera=c.is_frs_camera,
            is_ptz=c.is_ptz,
            resolution=c.resolution or "1080p",
            fps=c.fps or 25,
            latency_ms=c.latency_ms or 0,
            packet_loss=f"{c.packet_loss_pct}%" if c.packet_loss_pct is not None else "0.0%",
            people_count=c.people_count or 0,
            reconnect_count=c.reconnect_count or 0,
            last_error=c.last_error,
            gpu_id=c.gpu_id or "GPU-01",
            last_seen_at=c.last_seen_at,
            last_tested_at=c.last_tested_at,
            logical_id_frs=f"{c.camera_code}-FRS",
            logical_id_crowd=f"{c.camera_code}-CROWD",
            ai_mode=ai_mode,
            frs_status=frs_status,
            crowd_status=crowd_status,
        )

    async def get_cameras(
        self,
        zone_code: Optional[str] = None,
        status_filter: Optional[str] = None,
        camera_type: Optional[str] = None,
        is_frs: Optional[bool] = None,
        search: Optional[str] = None,
        enabled_only: Optional[bool] = None,
        event_id: Optional[uuid.UUID] = None,
        allowed_site_ids: Optional[List[uuid.UUID]] = None,
        page: int = 1,
        page_size: int = 100,
    ) -> Tuple[List[CameraRead], int]:
        skip = (page - 1) * page_size
        cameras, total = await self.camera_repo.list_cameras(
            zone_code=zone_code,
            status=status_filter,
            camera_type=camera_type,
            is_frs=is_frs,
            search=search,
            enabled_only=enabled_only,
            event_id=event_id,
            allowed_site_ids=allowed_site_ids,
            skip=skip,
            limit=page_size,
        )
        return [self._build_camera_read(c) for c in cameras], total


    async def get_camera_by_code(self, camera_code: str) -> CameraRead:
        camera = await self.camera_repo.get_by_code(camera_code)
        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CAMERA_NOT_FOUND", "message": f"Camera '{camera_code}' not found"},
            )
        return self._build_camera_read(camera)

    async def get_camera_model(self, camera_code: str) -> Camera:
        camera = await self.camera_repo.get_by_code(camera_code)
        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CAMERA_NOT_FOUND", "message": f"Camera '{camera_code}' not found"},
            )
        return camera

    async def _fetch_and_cache_direct(self) -> CameraStatsResponse:
        global _stats_cache, _stats_cache_time
        cameras, total = await self.camera_repo.list_cameras(limit=2000)
        online = sum(1 for c in cameras if (c.status == "online" or c.stream_status == "ONLINE"))
        degraded = sum(1 for c in cameras if (c.status == "degraded" or c.stream_status == "DEGRADED"))
        offline = sum(1 for c in cameras if (c.status == "offline" or c.stream_status == "OFFLINE"))
        not_tested = sum(1 for c in cameras if c.stream_status == "NOT_TESTED")
        frs_count = sum(1 for c in cameras if c.is_frs_camera)
        ptz_count = sum(1 for c in cameras if c.is_ptz)

        res = CameraStatsResponse(
            total=total,
            online=online,
            degraded=degraded,
            offline=offline,
            not_tested=not_tested,
            frs_count=frs_count,
            ptz_count=ptz_count,
        )
        _stats_cache = res
        _stats_cache_time = time.time()
        return res

    async def get_camera_stats(self) -> CameraStatsResponse:
        global _stats_cache, _stats_cache_time, _is_refreshing_stats
        now = time.time()

        if _stats_cache is not None:
            if (now - _stats_cache_time) > _STATS_TTL and not _is_refreshing_stats:
                _is_refreshing_stats = True
                asyncio.create_task(_background_refresh_camera_stats())
            return _stats_cache

        # Cold fallback so user never waits
        default_stats = CameraStatsResponse(
            total=0,
            online=0,
            degraded=0,
            offline=0,
            not_tested=0,
            frs_count=0,
            ptz_count=0,
        )
        _stats_cache = default_stats
        if not _is_refreshing_stats:
            _is_refreshing_stats = True
            asyncio.create_task(_background_refresh_camera_stats())
        return default_stats

    async def get_camera_health(self, camera_code: str) -> CameraHealth:
        camera = await self.get_camera_model(camera_code)
        last_tested_str = camera.last_tested_at.isoformat() if camera.last_tested_at else "Never tested"
        last_seen_str = camera.last_seen_at.isoformat() if camera.last_seen_at else "Never seen"

        return CameraHealth(
            camera_id=camera.camera_code,
            status=camera.status,
            stream_status=camera.stream_status or "NOT_TESTED",
            fps=camera.fps or 0,
            latency_ms=camera.latency_ms or 0,
            packet_loss_pct=camera.packet_loss_pct or 0.0,
            gpu_unit=camera.gpu_id or "GPU-01",
            uptime_percentage=99.4 if camera.status == "online" else 0.0,
            last_seen=last_seen_str,
            last_tested=last_tested_str,
            stability=camera.stream_stability or "UNKNOWN",
            last_error=camera.last_error,
        )

    async def create_camera(self, data: CameraCreate) -> CameraRead:
        """Onboards a new IP camera with full validation, duplicate detection, and encryption."""
        code = (data.camera_id or data.camera_code or "").strip().upper()
        if not code:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_INPUT", "message": "Camera ID (camera_code) is required"},
            )

        name = data.name.strip()
        label = (data.label or name).strip()
        camera_type = data.camera_type.strip().upper()
        valid_types = {"GENERAL", "CROWD", "QUEUE", "FRS", "MULTI_PURPOSE"}
        if camera_type not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_CAMERA_TYPE", "message": f"Camera type must be one of {valid_types}"},
            )

        # 1. Duplicate Protection
        encrypted_url_probe = encrypt_credential(data.rtsp_url) if data.rtsp_url else None
        dup = await self.camera_repo.find_duplicate(
            camera_code=code,
            private_ip=data.private_ip,
            rtsp_url_encrypted=encrypted_url_probe,
        )
        if dup:
            field, existing_code = dup
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "CAMERA_ALREADY_REGISTERED",
                    "message": f"A camera already exists with matching {field}. Existing camera ID: {existing_code}",
                    "existing_camera_id": existing_code,
                    "field": field,
                },
            )

        # 2. Zone Validation
        zone_obj = None
        zone_code = data.zone_code
        zone_id = data.zone_id

        if zone_id:
            zone_stmt = select(Zone).where(Zone.id == zone_id)
            res = await self.db.execute(zone_stmt)
            zone_obj = res.scalars().first()
            if not zone_obj:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": "ZONE_NOT_FOUND", "message": f"Zone with ID {zone_id} does not exist"},
                )
            zone_code = zone_obj.zone_code
        elif zone_code:
            zone_stmt = select(Zone).where(Zone.zone_code == zone_code.strip().upper())
            res = await self.db.execute(zone_stmt)
            zone_obj = res.scalars().first()
            if not zone_obj:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": "ZONE_NOT_FOUND", "message": f"Zone '{zone_code}' does not exist"},
                )
            zone_id = zone_obj.id
            zone_code = zone_obj.zone_code

        # 3. RTSP URL & Credential Preparation
        final_rtsp_url = data.rtsp_url
        if final_rtsp_url and (data.username or data.password):
            final_rtsp_url = build_authenticated_rtsp_url(
                data.rtsp_url,
                username=data.username,
                password=data.password,
            )

        encrypted_rtsp = encrypt_credential(final_rtsp_url) if final_rtsp_url else None
        encrypted_password = encrypt_credential(data.password) if data.password else None

        # 4. Coordinates
        if data.coordinates and len(data.coordinates) >= 2:
            coords = data.coordinates
        elif data.latitude is not None and data.longitude is not None:
            coords = [data.longitude, data.latitude]
        else:
            coords = [78.4635, 17.4175]  # Default Khairatabad Ganesh precinct

        # 5. Create Camera Model
        is_frs = data.is_frs_camera or (camera_type == "FRS")
        new_cam = Camera(
            camera_code=code,
            name=name,
            label=label,
            description=data.description,
            camera_type=camera_type,
            private_ip=data.private_ip.strip() if data.private_ip else None,
            port=data.port or 554,
            rtsp_url_encrypted=encrypted_rtsp,
            username=data.username.strip() if data.username else None,
            password_encrypted=encrypted_password,
            codec=data.codec or "h264",
            protocol=data.protocol or "rtsp",
            zone_id=zone_id,
            zone_code=zone_code,
            location_name=data.location_name,
            latitude=data.latitude,
            longitude=data.longitude,
            coordinates=coords,
            status="online",
            ai_status="online",
            stream_status="NOT_TESTED",
            stream_stability="UNKNOWN",
            enabled=True,
            is_frs_camera=is_frs,
            is_ptz=data.is_ptz,
            resolution=data.resolution or "1080p",
            fps=data.fps or 25,
            latency_ms=0,
            packet_loss_pct=0.0,
            people_count=0,
            reconnect_count=0,
            last_error=None,
            gpu_id="GPU-01",
            last_seen_at=None,
            last_tested_at=None,
        )

        self.db.add(new_cam)
        await self.db.commit()
        await self.db.refresh(new_cam)

        # 6. Publish event
        safe_read = self._build_camera_read(new_cam)
        await event_bus.publish(
            channel="cameras",
            event_type="CAMERA_ADDED",
            payload={"camera_id": code, "name": name, "zone": zone_code, "camera_type": camera_type},
        )

        logger.info(f"[CameraService] Onboarded new camera {code} ({name}) in zone {zone_code}")
        return safe_read

    async def update_camera(self, camera_code: str, data: CameraUpdate) -> CameraRead:
        """Updates camera configuration with duplicate check and re-encryption."""
        camera = await self.get_camera_model(camera_code)

        # Check IP duplicate if changed
        if data.private_ip and data.private_ip != camera.private_ip:
            dup = await self.camera_repo.find_duplicate(
                camera_code=camera.camera_code,
                private_ip=data.private_ip,
                exclude_camera_code=camera.camera_code,
            )
            if dup:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "CAMERA_ALREADY_REGISTERED", "message": f"IP {data.private_ip} already in use by {dup[1]}"},
                )
            camera.private_ip = data.private_ip.strip()

        # Update Zone if changed
        if data.zone_code and data.zone_code != camera.zone_code:
            zone_stmt = select(Zone).where(Zone.zone_code == data.zone_code.strip().upper())
            res = await self.db.execute(zone_stmt)
            zone_obj = res.scalars().first()
            if not zone_obj:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": "ZONE_NOT_FOUND", "message": f"Zone '{data.zone_code}' does not exist"},
                )
            camera.zone_id = zone_obj.id
            camera.zone_code = zone_obj.zone_code

        # Update Credentials & RTSP
        if data.password:
            camera.password_encrypted = encrypt_credential(data.password)
        if data.username:
            camera.username = data.username.strip()

        if data.rtsp_url:
            user = data.username or camera.username
            pwd = data.password or (decrypt_credential(camera.password_encrypted) if camera.password_encrypted else None)
            final_url = build_authenticated_rtsp_url(data.rtsp_url, user, pwd)
            camera.rtsp_url_encrypted = encrypt_credential(final_url)

        # General fields
        if data.name is not None:
            camera.name = data.name.strip()
        if data.label is not None:
            camera.label = data.label.strip()
        if data.description is not None:
            camera.description = data.description
        if data.camera_type is not None:
            camera.camera_type = data.camera_type.strip().upper()
            if camera.camera_type == "FRS":
                camera.is_frs_camera = True
        if data.location_name is not None:
            camera.location_name = data.location_name
        if data.latitude is not None:
            camera.latitude = data.latitude
        if data.longitude is not None:
            camera.longitude = data.longitude
        if data.coordinates is not None:
            camera.coordinates = data.coordinates
        if data.status is not None:
            camera.status = data.status.lower()
        if data.ai_status is not None:
            camera.ai_status = data.ai_status.lower()
        if data.enabled is not None:
            camera.enabled = data.enabled
            if not data.enabled:
                camera.status = "offline"
                camera.stream_status = "OFFLINE"
        if data.fps is not None:
            camera.fps = data.fps
        if data.resolution is not None:
            camera.resolution = data.resolution
        if data.is_frs_camera is not None:
            camera.is_frs_camera = data.is_frs_camera
        if data.is_ptz is not None:
            camera.is_ptz = data.is_ptz

        await self.db.commit()
        await self.db.refresh(camera)

        safe_read = self._build_camera_read(camera)
        await event_bus.publish(
            channel="cameras",
            event_type="CAMERA_UPDATED",
            payload={"camera_id": camera.camera_code, "name": camera.name, "status": camera.status},
        )
        return safe_read

    async def toggle_camera_enabled(self, camera_code: str, enabled: Optional[bool] = None) -> CameraRead:
        """Enables or disables camera operation."""
        camera = await self.get_camera_model(camera_code)
        new_state = (not camera.enabled) if enabled is None else enabled
        camera.enabled = new_state
        if not new_state:
            camera.status = "offline"
            camera.stream_status = "OFFLINE"
            event_name = "CAMERA_OFFLINE"
        else:
            camera.status = "online"
            event_name = "CAMERA_ONLINE"

        await self.db.commit()
        await self.db.refresh(camera)

        safe_read = self._build_camera_read(camera)
        await event_bus.publish(
            channel="cameras",
            event_type=event_name,
            payload={"camera_id": camera.camera_code, "enabled": new_state},
        )
        return safe_read

    async def delete_camera(self, camera_code: str) -> Dict[str, Any]:
        """
        Permanently deletes camera, cleans up relations, unlinks events/metrics,
        and halts all streaming threads and AI inference pipelines.
        """
        global _stats_cache
        cam = await self.camera_repo.get_by_code(camera_code)

        target_code = cam.camera_code if cam else camera_code

        # 1. Stop background AI pipelines
        try:
            await CrowdPipelineRegistry.stop_pipeline(target_code)
        except Exception:
            pass
        try:
            await QueuePipelineRegistry.stop_pipeline(target_code)
        except Exception:
            pass
        try:
            await FRSPipelineRegistry.stop_pipeline(target_code)
        except Exception:
            pass

        # 2. Stop in-memory FRS / RTSP worker
        try:
            from app.frs_engine.frs_service import remove_frs_camera
            await remove_frs_camera(target_code, sync_db=False)
        except Exception:
            pass

        # 3. If in database, nullify foreign key references and delete
        in_db = False
        if cam:
            in_db = True
            try:
                from app.models.alert import Alert
                from app.models.crowd import CrowdSnapshot
                from app.models.queue import QueueSnapshot
                from app.models.frs import FRSCandidate
                from app.models.camera_roi import CameraROIConfiguration
                from app.models.camera_ai_assignment import CameraAIProfileAssignment
                from app.models.ai_deployment import AIPipelineDeployment
                from sqlalchemy import update, delete, text

                # 1. Nullify references in metric / snapshot / alert tables
                await self.db.execute(update(CrowdSnapshot).where(CrowdSnapshot.camera_id == cam.id).values(camera_id=None))
                await self.db.execute(update(QueueSnapshot).where(QueueSnapshot.camera_id == cam.id).values(camera_id=None))
                await self.db.execute(update(FRSCandidate).where(FRSCandidate.camera_id == cam.id).values(camera_id=None))
                await self.db.execute(update(Alert).where(Alert.camera_id == cam.id).values(camera_id=None))

                # 2. Delete configuration rows bound specifically to this camera
                await self.db.execute(delete(CameraROIConfiguration).where(CameraROIConfiguration.camera_id == cam.id))
                await self.db.execute(delete(CameraAIProfileAssignment).where(CameraAIProfileAssignment.camera_id == cam.id))
                await self.db.execute(delete(AIPipelineDeployment).where(AIPipelineDeployment.camera_id == cam.id))

                # 3. Direct SQL safety pass for any other raw database references
                await self.db.execute(text("UPDATE crowd_snapshots SET camera_id = NULL WHERE camera_id = :cid"), {"cid": cam.id})
                await self.db.execute(text("UPDATE queue_snapshots SET camera_id = NULL WHERE camera_id = :cid"), {"cid": cam.id})
                await self.db.execute(text("UPDATE frs_candidates SET camera_id = NULL WHERE camera_id = :cid"), {"cid": cam.id})
                await self.db.execute(text("UPDATE alerts SET camera_id = NULL WHERE camera_id = :cid"), {"cid": cam.id})
                await self.db.execute(text("DELETE FROM camera_roi_configurations WHERE camera_id = :cid"), {"cid": cam.id})
                await self.db.execute(text("DELETE FROM camera_ai_profile_assignments WHERE camera_id = :cid"), {"cid": cam.id})
                await self.db.execute(text("DELETE FROM ai_pipeline_deployments WHERE camera_id = :cid"), {"cid": cam.id})
            except Exception as e:
                logger.warning(f"Error unlinking references for camera {cam.camera_code}: {e}")

            try:
                await self.db.delete(cam)
                await self.db.commit()
            except Exception as db_err:
                logger.warning(f"ORM delete failed ({db_err}), executing raw delete on camera {cam.id}")
                await self.db.rollback()
                await self.db.execute(text("UPDATE crowd_snapshots SET camera_id = NULL WHERE camera_id = :cid"), {"cid": cam.id})
                await self.db.execute(text("UPDATE queue_snapshots SET camera_id = NULL WHERE camera_id = :cid"), {"cid": cam.id})
                await self.db.execute(text("UPDATE frs_candidates SET camera_id = NULL WHERE camera_id = :cid"), {"cid": cam.id})
                await self.db.execute(text("UPDATE alerts SET camera_id = NULL WHERE camera_id = :cid"), {"cid": cam.id})
                await self.db.execute(text("DELETE FROM camera_roi_configurations WHERE camera_id = :cid"), {"cid": cam.id})
                await self.db.execute(text("DELETE FROM camera_ai_profile_assignments WHERE camera_id = :cid"), {"cid": cam.id})
                await self.db.execute(text("DELETE FROM ai_pipeline_deployments WHERE camera_id = :cid"), {"cid": cam.id})
                await self.db.execute(text("DELETE FROM cameras WHERE id = :cid"), {"cid": cam.id})
                await self.db.commit()

            try:
                asyncio.create_task(
                    event_bus.publish(
                        channel="cameras",
                        event_type="CAMERA_DELETED",
                        payload={"camera_id": cam.camera_code},
                    )
                )
            except Exception:
                pass

        _stats_cache = None
        logger.info(f"[CameraService] Camera {target_code} deleted (in_database={in_db})")
        return {"deleted": True, "camera_code": target_code, "in_database": in_db}

    async def test_camera_stream(self, camera_code: str, timeout_sec: float = 6.0) -> RTSPTestResponse:
        """
        Tests stream connectivity for an existing saved camera.
        Updates stream status and metrics in the database.
        """
        camera = await self.get_camera_model(camera_code)

        if not camera.rtsp_url_encrypted:
            return RTSPTestResponse(
                camera_id=camera.camera_code,
                reachable=False,
                authenticated=False,
                stream_available=False,
                error_code=RTSPErrorCode.INVALID_RTSP_URL,
                error_message="No RTSP URL configured for this camera.",
                tested_at=datetime.now(timezone.utc).isoformat(),
            )

        # Decrypt actual RTSP URL with credentials for probing
        decrypted_url = decrypt_credential(camera.rtsp_url_encrypted)

        # Publish test started event
        await event_bus.publish(
            channel="cameras",
            event_type="CAMERA_TEST_STARTED",
            payload={"camera_id": camera.camera_code},
        )

        # Run probe
        result_dict = await RTSPTestService.test_stream(
            rtsp_url=decrypted_url,
            camera_id=camera.camera_code,
            timeout_sec=timeout_sec,
        )

        now_utc = datetime.now(timezone.utc)
        camera.last_tested_at = now_utc

        if result_dict["stream_available"]:
            camera.stream_status = "ONLINE"
            camera.status = "online"
            camera.resolution = result_dict.get("resolution") or camera.resolution
            camera.fps = result_dict.get("fps") or camera.fps
            camera.codec = result_dict.get("codec") or camera.codec
            camera.latency_ms = result_dict.get("latency_ms") or camera.latency_ms
            camera.stream_stability = result_dict.get("stability") or "STABLE"
            camera.last_seen_at = now_utc
            camera.last_error = None
            event_to_publish = "CAMERA_ONLINE"
        else:
            reachable = result_dict.get("reachable", False)
            camera.stream_status = "DEGRADED" if reachable else "OFFLINE"
            camera.status = "degraded" if reachable else "offline"
            camera.stream_stability = "DEGRADED" if reachable else "UNSTABLE"
            camera.last_error = result_dict.get("error_message")
            camera.reconnect_count += 1
            event_to_publish = "CAMERA_DEGRADED" if reachable else "CAMERA_OFFLINE"

        await self.db.commit()
        await self.db.refresh(camera)

        # Publish completion and status events
        await event_bus.publish(
            channel="cameras",
            event_type="CAMERA_TEST_COMPLETED",
            payload={"camera_id": camera.camera_code, "success": result_dict["stream_available"]},
        )
        await event_bus.publish(
            channel="cameras",
            event_type=event_to_publish,
            payload={"camera_id": camera.camera_code, "stream_status": camera.stream_status},
        )

        return RTSPTestResponse(**result_dict)

    async def test_ad_hoc_stream(self, req: RTSPTestRequest) -> RTSPTestResponse:
        """Tests an unsaved RTSP stream during onboarding wizard Step 3."""
        if not req.rtsp_url:
            return RTSPTestResponse(
                camera_id=req.camera_id or "PROBE",
                reachable=False,
                authenticated=False,
                stream_available=False,
                error_code=RTSPErrorCode.INVALID_RTSP_URL,
                error_message="RTSP URL is required for stream testing.",
                tested_at=datetime.now(timezone.utc).isoformat(),
            )

        full_url = build_authenticated_rtsp_url(
            req.rtsp_url,
            username=req.username,
            password=req.password,
        )

        result_dict = await RTSPTestService.test_stream(
            rtsp_url=full_url,
            camera_id=req.camera_id or "NEW_CAMERA",
            timeout_sec=req.timeout_sec or 6.0,
        )
        return RTSPTestResponse(**result_dict)

    async def bulk_validate_cameras(self, rows: List[BulkCameraRow]) -> BulkCameraValidateResult:
        """Pre-validates bulk camera CSV rows for duplicate conflicts and format errors."""
        valid_rows = []
        invalid_rows = []
        duplicate_rows = []
        seen_codes = set()
        seen_ips = set()

        for idx, row in enumerate(rows, start=1):
            code = (row.camera_id or "").strip().upper()
            ip = (row.private_ip or "").strip()

            # Syntax checks
            if not code or not row.camera_name:
                invalid_rows.append({"row": idx, "camera_id": code, "error": "Camera ID and Name are required."})
                continue

            if code in seen_codes:
                duplicate_rows.append({"row": idx, "camera_id": code, "error": f"Duplicate camera ID {code} within file."})
                continue
            if ip and ip in seen_ips:
                duplicate_rows.append({"row": idx, "camera_id": code, "error": f"Duplicate IP {ip} within file."})
                continue

            # DB duplicate check
            dup = await self.camera_repo.find_duplicate(camera_code=code, private_ip=ip)
            if dup:
                duplicate_rows.append({
                    "row": idx,
                    "camera_id": code,
                    "error": f"Already registered in database matching {dup[0]} (Existing: {dup[1]}).",
                })
                continue

            # Check Zone
            if row.zone:
                zone_stmt = select(Zone).where(Zone.zone_code == row.zone.strip().upper())
                res = await self.db.execute(zone_stmt)
                if not res.scalars().first():
                    invalid_rows.append({"row": idx, "camera_id": code, "error": f"Zone '{row.zone}' does not exist."})
                    continue

            seen_codes.add(code)
            if ip:
                seen_ips.add(ip)
            valid_rows.append(row)

        return BulkCameraValidateResult(
            total=len(rows),
            valid_count=len(valid_rows),
            invalid_count=len(invalid_rows),
            duplicate_count=len(duplicate_rows),
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
            duplicate_rows=duplicate_rows,
        )

    async def bulk_import_cameras(self, rows: List[BulkCameraRow]) -> BulkCameraImportResult:
        """Imports pre-validated bulk camera rows into database."""
        imported_ids = []
        errors = []

        for idx, row in enumerate(rows, start=1):
            try:
                create_req = CameraCreate(
                    camera_id=row.camera_id,
                    name=row.camera_name,
                    label=row.camera_name,
                    private_ip=row.private_ip,
                    rtsp_url=row.rtsp_url,
                    username=row.username,
                    password=row.password,
                    zone_code=row.zone,
                    camera_type=row.camera_type or "CROWD",
                    location_name=row.location,
                )
                created = await self.create_camera(create_req)
                imported_ids.append(created.camera_code)
            except Exception as e:
                errors.append({"row": idx, "camera_id": row.camera_id, "error": str(e)})

        return BulkCameraImportResult(
            imported_count=len(imported_ids),
            failed_count=len(errors),
            imported_camera_ids=imported_ids,
            errors=errors,
        )
