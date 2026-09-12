"""
app.services.camera_roi_service — Business Logic for Visual ROI & Counting-Line Configurations.

Enforces:
- Normalized coordinate bounds [0.0, 1.0]
- Min 3 points for polygons, 2 endpoints for lines
- Strict profile-to-ROI compatibility matrix
- FRS isolation (no crowd/queue analytics for FRS)
- Readiness lifecycle (NOT_CONFIGURED, PARTIALLY_CONFIGURED, READY, INVALID)
- Configuration versioning and audit trails
- Real-time WebSocket telemetry
- ZERO AI INFERENCE GUARANTEE
"""

import uuid
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.audit_log import AuditLog
from app.models.camera import Camera
from app.models.camera_roi import CameraROIConfiguration, ROIType
from app.models.user import User
from app.redis.event_bus import event_bus
from app.repositories.camera_ai_repository import CameraAIRepository
from app.repositories.camera_repository import CameraRepository
from app.repositories.camera_roi_repository import CameraROIRepository
from app.schemas.camera_roi import (
    CameraROICreate,
    CameraROIRead,
    CameraROIConfigSummary,
    CameraROIUpdate,
    CameraROIValidationRequest,
    CameraROIValidationResponse,
    ProfileReadinessItem,
)


# Profile-to-ROI compatibility matrix
CROWD_ROIS = {
    ROIType.CROWD_ROI,
    ROIType.ZONE_BOUNDARY,
    ROIType.EXCLUSION_ZONE,
    ROIType.COUNTING_LINE,
    ROIType.ENTRY_LINE,
    ROIType.EXIT_LINE,
}

QUEUE_ROIS = {
    ROIType.QUEUE_ROI,
    ROIType.DIRECTION_LINE,
    ROIType.ENTRY_LINE,
    ROIType.EXIT_LINE,
    ROIType.COUNTING_LINE,
    ROIType.EXCLUSION_ZONE,
}

PROFILE_ALLOWED_ROIS = {
    "CROWD_STANDARD": CROWD_ROIS,
    "CROWD_HIGH_DENSITY": CROWD_ROIS,
    "CROWD_YOLO11X": CROWD_ROIS,
    "CROWD_ZONE": CROWD_ROIS,
    "QUEUE_STANDARD": QUEUE_ROIS,
    "QUEUE_YOLO11X": QUEUE_ROIS,
    "CROWD_QUEUE": QUEUE_ROIS,
    "VIDEO_SAFETY": {ROIType.EXCLUSION_ZONE, ROIType.ZONE_BOUNDARY, ROIType.COUNTING_LINE},
    "FRS_STANDARD": set(),  # FRS strictly isolated: no crowd or queue analytics
}


class CameraROIService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = CameraROIRepository(db)
        self.camera_repo = CameraRepository(db)
        self.ai_repo = CameraAIRepository(db)

    # -------------------------------------------------------------------------
    # VALIDATION HELPERS
    # -------------------------------------------------------------------------

    @staticmethod
    def validate_coordinates(geometry_json: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validates that all coordinate points are normalized between 0.0 and 1.0."""
        # Polygons
        if "points" in geometry_json:
            pts = geometry_json.get("points", [])
            if not isinstance(pts, list):
                return False, "Polygon points must be a list of {x, y} coordinates."
            for pt in pts:
                if not isinstance(pt, dict) or "x" not in pt or "y" not in pt:
                    return False, "Each vertex must contain 'x' and 'y' properties."
                x, y = pt["x"], pt["y"]
                if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                    return False, "Coordinates must be numbers."
                if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                    return False, f"Coordinate ({x}, {y}) is outside valid range [0.0, 1.0]."
            return True, None

        # Lines
        if "start" in geometry_json and "end" in geometry_json:
            for key in ("start", "end"):
                pt = geometry_json[key]
                if not isinstance(pt, dict) or "x" not in pt or "y" not in pt:
                    return False, f"Endpoint '{key}' must contain 'x' and 'y' properties."
                x, y = pt["x"], pt["y"]
                if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                    return False, f"Endpoint '{key}' coordinates must be numbers."
                if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                    return False, f"Endpoint '{key}' ({x}, {y}) is outside valid range [0.0, 1.0]."

            # Ensure start and end are distinct (auto-nudge if clicked at exact same spot)
            s, e = geometry_json["start"], geometry_json["end"]
            if abs(s["x"] - e["x"]) < 1e-4 and abs(s["y"] - e["y"]) < 1e-4:
                e["x"] = min(1.0, s["x"] + 0.05) if s["x"] < 0.95 else max(0.0, s["x"] - 0.05)

            return True, None

        return False, "Geometry must define either 'points' for polygons or 'start'/'end' for lines."

    @staticmethod
    def validate_geometry_structure(roi_type: str, geometry_json: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        """Validates geometry structure according to ROI type."""
        polygon_types = {
            ROIType.CROWD_ROI.value,
            ROIType.QUEUE_ROI.value,
            ROIType.EXCLUSION_ZONE.value,
            ROIType.ZONE_BOUNDARY.value,
        }
        line_types = {
            ROIType.COUNTING_LINE.value,
            ROIType.ENTRY_LINE.value,
            ROIType.EXIT_LINE.value,
            ROIType.DIRECTION_LINE.value,
        }

        if roi_type in polygon_types:
            pts = geometry_json.get("points")
            if not isinstance(pts, list):
                return False, "ROI_INVALID", "Polygon ROI must contain a 'points' array."
            if len(pts) < 3:
                return False, "ROI_TOO_FEW_POINTS", "Polygon ROI requires at least 3 vertices."

        elif roi_type in line_types:
            if "start" not in geometry_json or "end" not in geometry_json:
                return False, "COUNTING_LINE_INVALID", "Line geometry must contain both 'start' and 'end' points."
            st = geometry_json["start"]
            en = geometry_json["end"]
            if not isinstance(st, dict) or not isinstance(en, dict):
                return False, "COUNTING_LINE_INVALID", "Line geometry 'start' and 'end' must be point dictionaries."
            if st.get("x") == en.get("x") and st.get("y") == en.get("y"):
                return False, "COUNTING_LINE_INVALID", "Line geometry start and end points cannot be identical."
            direction = (geometry_json.get("direction") or "BOTH").upper()
            if direction not in ("IN", "OUT", "BOTH"):
                direction = "BOTH"
            geometry_json["direction"] = direction

        coord_valid, coord_err = CameraROIService.validate_coordinates(geometry_json)
        if not coord_valid:
            return False, "ROI_COORDINATE_OUT_OF_RANGE", coord_err

        return True, None, None

    @staticmethod
    def validate_profile_compatibility(profile_id: str, roi_type: str) -> Tuple[bool, Optional[str]]:
        """Validates whether an ROI type is compatible with an assigned AI profile."""
        if profile_id == "FRS_STANDARD":
            return False, "FRS profile does not support crowd or queue ROI configurations."

        allowed = PROFILE_ALLOWED_ROIS.get(profile_id)
        if not allowed:
            return False, f"Unknown AI profile '{profile_id}'."

        if roi_type not in [r.value for r in allowed]:
            return False, f"ROI type '{roi_type}' is not supported for profile '{profile_id}'."

        return True, None

    # -------------------------------------------------------------------------
    # READINESS ENGINE
    # -------------------------------------------------------------------------

    @classmethod
    def calculate_readiness_for_profile(
        cls,
        profile_id: str,
        rois: List[CameraROIConfiguration],
    ) -> ProfileReadinessItem:
        """Calculates configuration readiness state for a given profile."""
        active_rois = [r for r in rois if r.profile_id == profile_id and r.enabled]
        types_present = {r.roi_type for r in active_rois}

        if not active_rois:
            return ProfileReadinessItem(
                status="NOT_CONFIGURED",
                status_label="Not Configured",
                is_ready=False,
                missing_requirements=["Geometry configuration required"],
                message="No active ROIs configured for this profile.",
            )

        if profile_id in ("CROWD_STANDARD", "CROWD_HIGH_DENSITY", "CROWD_YOLO11X", "CROWD_ZONE"):
            crowd_valid_types = {
                ROIType.CROWD_ROI.value,
                ROIType.COUNTING_LINE.value,
                ROIType.ENTRY_LINE.value,
                ROIType.EXIT_LINE.value,
            }
            if any(t in types_present for t in crowd_valid_types):
                return ProfileReadinessItem(
                    status="READY",
                    status_label="Ready for AI Pipeline",
                    is_ready=True,
                    missing_requirements=[],
                    message="Crowd counting line or detection area configured and verified.",
                )
            else:
                return ProfileReadinessItem(
                    status="PARTIALLY_CONFIGURED",
                    status_label="Partially Configured",
                    is_ready=False,
                    missing_requirements=["CROWD_ROI polygon or Entry/Exit counting line is required"],
                    message="Crowd detection area or counting line is required.",
                )

        elif profile_id in ("QUEUE_STANDARD", "QUEUE_YOLO11X", "CROWD_QUEUE"):
            missing = []
            if ROIType.QUEUE_ROI.value not in types_present:
                missing.append("QUEUE_ROI area polygon")
            if ROIType.ENTRY_LINE.value not in types_present:
                missing.append("ENTRY_LINE counting line")
            if ROIType.EXIT_LINE.value not in types_present:
                missing.append("EXIT_LINE counting line")

            if not missing:
                return ProfileReadinessItem(
                    status="READY",
                    status_label="Ready for AI Pipeline",
                    is_ready=True,
                    missing_requirements=[],
                    message="Queue boundary, entry line, and exit line configured.",
                )
            else:
                return ProfileReadinessItem(
                    status="PARTIALLY_CONFIGURED",
                    status_label="Partially Configured",
                    is_ready=False,
                    missing_requirements=missing,
                    message=f"Missing requirements: {', '.join(missing)}.",
                )

        elif profile_id == "VIDEO_SAFETY":
            if types_present:
                return ProfileReadinessItem(
                    status="READY",
                    status_label="Ready for AI Pipeline",
                    is_ready=True,
                    missing_requirements=[],
                    message="Safety exclusion zones / boundaries configured.",
                )

        return ProfileReadinessItem(
            status="NOT_CONFIGURED",
            status_label="Not Configured",
            is_ready=False,
            missing_requirements=[],
            message="No configuration present.",
        )

    # -------------------------------------------------------------------------
    # SERVICE METHODS
    # -------------------------------------------------------------------------

    async def _resolve_camera(self, camera_id_or_code: str) -> Camera:
        """Finds camera by UUID or camera_code."""
        camera = None
        try:
            cam_uuid = uuid.UUID(camera_id_or_code)
            camera = await self.camera_repo.get_by_id(cam_uuid)
        except ValueError:
            pass

        if not camera:
            camera = await self.camera_repo.get_by_camera_code(camera_id_or_code)

        if not camera:
            clean_code = camera_id_or_code.replace("-CROWD", "").replace("-FRS", "")
            camera = await self.camera_repo.get_by_camera_code(clean_code)

        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CAMERA_NOT_FOUND", "message": f"Camera '{camera_id_or_code}' not found"},
            )
        return camera

    def _verify_camera_readiness_for_editing(self, camera: Camera) -> None:
        """Verifies camera is enabled, online, and tested before editing ROIs."""
        if not camera.enabled:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "CAMERA_OFFLINE", "message": "Camera Offline — ROI editor unavailable"},
            )

        status_norm = (camera.stream_status or "").upper()
        if status_norm == "NOT_TESTED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "CAMERA_STREAM_NOT_VERIFIED", "message": "Camera stream not verified"},
            )
        if status_norm == "OFFLINE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "CAMERA_OFFLINE", "message": "Camera Offline — ROI editor unavailable"},
            )

    async def get_camera_roi_config(
        self,
        camera_id_or_code: str,
        profile_id: Optional[str] = None,
    ) -> CameraROIConfigSummary:
        """Fetches ROI configuration summary and readiness state."""
        camera = await self._resolve_camera(camera_id_or_code)
        rois = await self.repo.get_by_camera_id(camera.id, profile_id=profile_id)

        # Fetch assigned profiles to calculate readiness
        assignments = await self.ai_repo.get_assignments_for_camera(camera.id)
        readiness_map: Dict[str, ProfileReadinessItem] = {}
        for asgn in assignments:
            readiness_map[asgn.profile_id] = self.calculate_readiness_for_profile(asgn.profile_id, rois)

        stream_verified = (camera.stream_status or "").upper() not in ("NOT_TESTED", "OFFLINE")

        return CameraROIConfigSummary(
            camera_id=str(camera.id),
            camera_code=camera.camera_code,
            camera_name=camera.name,
            camera_type=camera.camera_type,
            zone_code=camera.zone_code,
            zone_name=(
                camera.zone.name
                if ("zone" in camera.__dict__ and camera.zone is not None)
                else camera.zone_code
            ),
            stream_status=camera.stream_status or "NOT_TESTED",
            stream_verified=stream_verified,
            configurations=[
                CameraROIRead(
                    id=str(r.id),
                    camera_id=str(r.camera_id),
                    camera_code=r.camera_code,
                    profile_id=r.profile_id or "CROWD_STANDARD",
                    roi_type=r.roi_type,
                    name=r.name or r.roi_name or r.roi_type,
                    geometry_json=(
                        r.geometry_json
                        if (r.geometry_json and r.geometry_json != {})
                        else ({"points": r.polygon_points} if r.polygon_points else {})
                    ),
                    normalized=r.normalized if r.normalized is not None else True,
                    enabled=r.enabled if r.enabled is not None else r.is_active,
                    version=r.version or 1,
                    created_by=r.created_by or "SYSTEM",
                    updated_by=r.updated_by or "SYSTEM",
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
                for r in rois
            ],
            readiness_by_profile=readiness_map,
        )

    async def validate_roi_geometry(
        self,
        camera_id_or_code: str,
        req: CameraROIValidationRequest,
    ) -> CameraROIValidationResponse:
        """Pre-flight dry-run geometry validation without database mutation."""
        camera = await self._resolve_camera(camera_id_or_code)
        self._verify_camera_readiness_for_editing(camera)

        # 1. Profile compatibility
        comp_ok, comp_err = self.validate_profile_compatibility(req.profile_id, req.roi_type)
        if not comp_ok:
            return CameraROIValidationResponse(
                valid=False,
                error_code="ROI_PROFILE_MISMATCH",
                error_message=comp_err,
            )

        # 2. Geometry structure & normalized coordinates
        struct_ok, err_code, struct_err = self.validate_geometry_structure(req.roi_type, req.geometry_json)
        if not struct_ok:
            return CameraROIValidationResponse(
                valid=False,
                error_code=err_code,
                error_message=struct_err,
            )

        return CameraROIValidationResponse(
            valid=True,
            error_code=None,
            error_message=None,
            details={"status": "VALID", "message": "Geometry is normalized and structurally valid"},
        )

    async def create_roi_configuration(
        self,
        camera_id_or_code: str,
        req: CameraROICreate,
        current_user: User,
        client_ip: Optional[str] = None,
    ) -> CameraROIRead:
        """
        Creates and persists a new ROI configuration.
        IMPORTANT: Configures desired spatial geometry only. Does NOT start AI inference.
        """
        camera = await self._resolve_camera(camera_id_or_code)
        self._verify_camera_readiness_for_editing(camera)

        # 1. Check AI profile assignment exists (auto-assign if not yet present)
        asgn = await self.ai_repo.get_assignment(camera.id, req.profile_id)
        if not asgn:
            from app.models.camera_ai_assignment import CameraAIProfileAssignment
            asgn = CameraAIProfileAssignment(
                camera_id=camera.id,
                camera_code=camera.camera_code,
                profile_id=req.profile_id,
                enabled=True,
            )
            self.db.add(asgn)
            await self.db.commit()

        # 2. Check profile compatibility
        comp_ok, comp_err = self.validate_profile_compatibility(req.profile_id, req.roi_type)
        if not comp_ok:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "ROI_PROFILE_MISMATCH", "message": comp_err},
            )

        # 3. Check geometry structure
        struct_ok, err_code, struct_err = self.validate_geometry_structure(req.roi_type, req.geometry_json)
        if not struct_ok:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": err_code, "message": struct_err},
            )

        # 4. Create record
        # Normalize polygon_points for legacy database column compatibility
        pts = []
        dir_val = None
        if isinstance(req.geometry_json, dict):
            if "points" in req.geometry_json:
                pts = req.geometry_json["points"]
            elif "start" in req.geometry_json and "end" in req.geometry_json:
                pts = [req.geometry_json["start"], req.geometry_json["end"]]
                dir_val = req.geometry_json.get("direction", "BOTH")
            else:
                pts = req.geometry_json
        else:
            pts = req.geometry_json

        name_val = (req.name or f"{req.roi_type} Configuration").strip()
        if len(name_val) < 2:
            name_val = f"{req.roi_type} Line"

        username_val = getattr(current_user, "username", "SYSTEM") if current_user else "SYSTEM"

        # Determine target purpose group for this new ROI
        target_group = "QUEUE" if req.roi_type in ("QUEUE_ROI", "DIRECTION_LINE") else (
            "ZONE" if req.roi_type in ("CROWD_ROI", "ZONE_BOUNDARY", "EXCLUSION_ZONE") else (
                "ENTRY" if req.roi_type == "ENTRY_LINE" else (
                    "EXIT" if req.roi_type == "EXIT_LINE" else "ENTRY_EXIT"
                )
            )
        )


        roi = CameraROIConfiguration(
            camera_id=camera.id,
            camera_code=camera.camera_code,
            profile_id=req.profile_id,
            roi_type=req.roi_type,
            name=name_val,
            roi_name=name_val,
            geometry_json=req.geometry_json,
            polygon_points=pts,
            direction=dir_val,
            normalized=req.normalized,
            enabled=req.enabled,
            is_active=req.enabled,
            version=1,
            created_by=username_val,
            updated_by=username_val,
        )
        saved_roi = await self.repo.create(roi)
        await self.db.commit()

        # For ZONE ROIs, update camera zone_code and DB Zone capacity/thresholds
        target_zone_code = None
        roi_cap = 100
        warning_th = 50
        danger_th = 80
        if target_group == "ZONE":
            geom_dict = req.geometry_json if isinstance(req.geometry_json, dict) else {}
            target_zone_code = (geom_dict.get("zone_code") or camera.zone_code or "ZONE-A").upper()
            roi_cap = int(geom_dict.get("capacity") or 100)
            warning_th = int(geom_dict.get("warning_threshold") or 50)
            danger_th = int(geom_dict.get("danger_threshold") or 80)

            # Update camera zone_code
            camera.zone_code = target_zone_code

            # Update Zone in DB with user-configured capacity and alert thresholds
            from app.models.zone import Zone
            from sqlalchemy import select as sa_select_zone
            res_z = await self.db.execute(sa_select_zone(Zone).where(Zone.zone_code == target_zone_code).limit(1))
            zone_obj = res_z.scalars().first()
            if zone_obj:
                zone_obj.capacity = roi_cap
            await self.db.commit()

        # Synchronize running worker's purpose and cached ROI lines immediately
        try:
            from app.frs_engine.frs_service import get_worker_for_camera, sync_worker_roi_lines
            w_state = get_worker_for_camera(camera.camera_code)
            if w_state:
                w_state.ai_purposes = [target_group]
                if target_group == "ZONE" and target_zone_code:
                    w_state.zone_code = target_zone_code
                    w_state.zone_capacity = roi_cap
                    w_state.warning_threshold = warning_th
                    w_state.danger_threshold = danger_th
                w_state.in_count = 0
                w_state.out_count = 0
                w_state.occupancy_count = 0
                w_state.queue_movement_status = "STOPPED"
            sync_worker_roi_lines(camera.camera_code)
        except Exception:
            pass


        # 5. Calculate new readiness state
        all_rois = await self.repo.get_by_camera_id(camera.id, profile_id=req.profile_id)
        readiness = self.calculate_readiness_for_profile(req.profile_id, all_rois)

        # 6. Audit Log
        audit = AuditLog(
            user_id=current_user.id,
            username=current_user.username,
            action="ROI_CREATED",
            resource_type="camera_roi_configuration",
            resource_id=f"{camera.camera_code}:{saved_roi.id}",
            ip_address=client_ip,
            metadata_json={
                "camera_code": camera.camera_code,
                "profile_id": req.profile_id,
                "roi_type": req.roi_type,
                "version": 1,
                "new_geometry": req.geometry_json,
                "readiness_status": readiness.status,
            },
        )
        self.db.add(audit)
        await self.db.commit()

        # 7. WebSocket Event
        try:
            await event_bus.publish(
                channel="ai",
                event_type="AI_GEOMETRY_CHANGED",
                payload={
                    "camera_id": str(camera.id),
                    "camera_code": camera.camera_code,
                    "profile_id": req.profile_id,
                    "action": "ROI_CREATED",
                    "configuration_version": 1,
                    "readiness_status": readiness.status,
                },
            )
        except Exception as e:
            logger.warning(f"[CameraROIService] WebSocket emission failed: {e}")

        logger.info(
            f"[CameraROIService] Created ROI {saved_roi.id} ({req.roi_type}) for camera {camera.camera_code}. "
            f"Readiness: {readiness.status}. ZERO inference started."
        )

        return CameraROIRead(
            id=str(saved_roi.id),
            camera_id=str(saved_roi.camera_id),
            camera_code=saved_roi.camera_code,
            profile_id=saved_roi.profile_id,
            roi_type=saved_roi.roi_type,
            name=saved_roi.name,
            geometry_json=saved_roi.geometry_json,
            normalized=saved_roi.normalized,
            enabled=saved_roi.enabled,
            version=saved_roi.version,
            created_by=saved_roi.created_by,
            updated_by=saved_roi.updated_by,
            created_at=saved_roi.created_at,
            updated_at=saved_roi.updated_at,
        )

    async def update_roi_configuration(
        self,
        camera_id_or_code: str,
        roi_id: str,
        req: CameraROIUpdate,
        current_user: User,
        client_ip: Optional[str] = None,
    ) -> CameraROIRead:
        """Updates geometry or properties of an existing ROI and increments version."""
        camera = await self._resolve_camera(camera_id_or_code)
        self._verify_camera_readiness_for_editing(camera)

        try:
            roi_uuid = uuid.UUID(roi_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "ROI_NOT_FOUND", "message": f"ROI '{roi_id}' not found"},
            )

        roi = await self.repo.get_by_id(roi_uuid)
        if not roi or roi.camera_id != camera.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "ROI_NOT_FOUND", "message": f"ROI '{roi_id}' not found on camera {camera.camera_code}"},
            )

        old_geom = roi.geometry_json

        # Update fields
        if req.name is not None:
            roi.name = req.name.strip()
            roi.roi_name = req.name.strip()
        if req.enabled is not None:
            roi.enabled = req.enabled
            roi.is_active = req.enabled
        if req.geometry_json is not None:
            struct_ok, err_code, struct_err = self.validate_geometry_structure(roi.roi_type, req.geometry_json)
            if not struct_ok:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": err_code, "message": struct_err},
                )
            roi.geometry_json = req.geometry_json
            if isinstance(req.geometry_json, dict):
                if "points" in req.geometry_json:
                    roi.polygon_points = req.geometry_json["points"]
                elif "start" in req.geometry_json and "end" in req.geometry_json:
                    roi.polygon_points = [req.geometry_json["start"], req.geometry_json["end"]]
                    roi.direction = req.geometry_json.get("direction", "BOTH")
                else:
                    roi.polygon_points = req.geometry_json
            else:
                roi.polygon_points = req.geometry_json

        # Increment version
        roi.version += 1
        roi.updated_by = current_user.username

        updated_roi = await self.repo.update(roi)
        await self.db.commit()

        try:
            from app.frs_engine.frs_service import sync_worker_roi_lines
            sync_worker_roi_lines(camera.camera_code)
        except Exception:
            pass

        # Readiness
        all_rois = await self.repo.get_by_camera_id(camera.id, profile_id=roi.profile_id)
        readiness = self.calculate_readiness_for_profile(roi.profile_id, all_rois)

        # Audit Log
        audit = AuditLog(
            user_id=current_user.id,
            username=current_user.username,
            action="ROI_UPDATED",
            resource_type="camera_roi_configuration",
            resource_id=f"{camera.camera_code}:{roi.id}",
            ip_address=client_ip,
            metadata_json={
                "camera_code": camera.camera_code,
                "profile_id": roi.profile_id,
                "roi_type": roi.roi_type,
                "version": roi.version,
                "old_geometry": old_geom,
                "new_geometry": roi.geometry_json,
                "readiness_status": readiness.status,
            },
        )
        self.db.add(audit)
        await self.db.commit()

        # WebSocket Event
        try:
            await event_bus.publish(
                channel="ai",
                event_type="AI_GEOMETRY_CHANGED",
                payload={
                    "camera_id": str(camera.id),
                    "camera_code": camera.camera_code,
                    "profile_id": roi.profile_id,
                    "action": "ROI_UPDATED",
                    "configuration_version": roi.version,
                    "readiness_status": readiness.status,
                },
            )
        except Exception as e:
            logger.warning(f"[CameraROIService] WebSocket emission failed: {e}")

        return CameraROIRead(
            id=str(updated_roi.id),
            camera_id=str(updated_roi.camera_id),
            camera_code=updated_roi.camera_code,
            profile_id=updated_roi.profile_id,
            roi_type=updated_roi.roi_type,
            name=updated_roi.name,
            geometry_json=updated_roi.geometry_json,
            normalized=updated_roi.normalized,
            enabled=updated_roi.enabled,
            version=updated_roi.version,
            created_by=updated_roi.created_by,
            updated_by=updated_roi.updated_by,
            created_at=updated_roi.created_at,
            updated_at=updated_roi.updated_at,
        )

    async def delete_roi_configuration(
        self,
        camera_id_or_code: str,
        roi_id: str,
        current_user: User,
        client_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Deletes an existing ROI configuration."""
        camera = await self._resolve_camera(camera_id_or_code)
        self._verify_camera_readiness_for_editing(camera)

        try:
            roi_uuid = uuid.UUID(roi_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "ROI_NOT_FOUND", "message": f"ROI '{roi_id}' not found"},
            )

        roi = await self.repo.get_by_id(roi_uuid)
        if not roi or roi.camera_id != camera.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "ROI_NOT_FOUND", "message": f"ROI '{roi_id}' not found on camera {camera.camera_code}"},
            )

        profile_id = roi.profile_id
        roi_type = roi.roi_type
        old_geom = roi.geometry_json
        v = roi.version

        await self.repo.delete(roi)
        await self.db.commit()

        try:
            from app.frs_engine.frs_service import sync_worker_roi_lines
            sync_worker_roi_lines(camera.camera_code)
        except Exception:
            pass

        # Readiness after delete
        all_rois = await self.repo.get_by_camera_id(camera.id, profile_id=profile_id)
        readiness = self.calculate_readiness_for_profile(profile_id, all_rois)

        # Audit Log
        audit = AuditLog(
            user_id=current_user.id,
            username=current_user.username,
            action="ROI_DELETED",
            resource_type="camera_roi_configuration",
            resource_id=f"{camera.camera_code}:{roi_id}",
            ip_address=client_ip,
            metadata_json={
                "camera_code": camera.camera_code,
                "profile_id": profile_id,
                "roi_type": roi_type,
                "version": v,
                "deleted_geometry": old_geom,
                "readiness_status": readiness.status,
            },
        )
        self.db.add(audit)
        await self.db.commit()

        # WebSocket Event
        try:
            await event_bus.publish(
                channel="ai",
                event_type="AI_GEOMETRY_CHANGED",
                payload={
                    "camera_id": str(camera.id),
                    "camera_code": camera.camera_code,
                    "profile_id": profile_id,
                    "action": "ROI_DELETED",
                    "configuration_version": v,
                    "readiness_status": readiness.status,
                },
            )
        except Exception as e:
            logger.warning(f"[CameraROIService] WebSocket emission failed: {e}")

        logger.info(f"[CameraROIService] Deleted ROI {roi_id} for camera {camera.camera_code}")

        return {
            "camera_code": camera.camera_code,
            "profile_id": profile_id,
            "roi_id": roi_id,
            "deleted": True,
            "readiness_status": readiness.status,
        }
