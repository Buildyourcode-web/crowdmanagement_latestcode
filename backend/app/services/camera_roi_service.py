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
PROFILE_ALLOWED_ROIS = {
    "CROWD_STANDARD": {ROIType.CROWD_ROI, ROIType.EXCLUSION_ZONE, ROIType.COUNTING_LINE},
    "CROWD_HIGH_DENSITY": {ROIType.CROWD_ROI, ROIType.EXCLUSION_ZONE, ROIType.COUNTING_LINE},
    "QUEUE_STANDARD": {
        ROIType.QUEUE_ROI,
        ROIType.ENTRY_LINE,
        ROIType.EXIT_LINE,
        ROIType.DIRECTION_LINE,
        ROIType.EXCLUSION_ZONE,
    },
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

            # Ensure start and end are distinct
            s, e = geometry_json["start"], geometry_json["end"]
            if abs(s["x"] - e["x"]) < 1e-4 and abs(s["y"] - e["y"]) < 1e-4:
                return False, "Start and end points of a counting or boundary line must be distinct."

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
            direction = geometry_json.get("direction", "BOTH")
            if direction not in ("IN", "OUT", "BOTH"):
                return False, "COUNTING_LINE_INVALID", "Line direction must be 'IN', 'OUT', or 'BOTH'."

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

        if profile_id in ("CROWD_STANDARD", "CROWD_HIGH_DENSITY"):
            if ROIType.CROWD_ROI.value in types_present:
                return ProfileReadinessItem(
                    status="READY",
                    status_label="Ready for AI Pipeline",
                    is_ready=True,
                    missing_requirements=[],
                    message="Crowd detection area configured and verified.",
                )
            else:
                return ProfileReadinessItem(
                    status="PARTIALLY_CONFIGURED",
                    status_label="Partially Configured",
                    is_ready=False,
                    missing_requirements=["CROWD_ROI polygon is required"],
                    message="Crowd detection area (CROWD_ROI) polygon is required.",
                )

        elif profile_id == "QUEUE_STANDARD":
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
            zone_name=camera.zone.name if camera.zone else None,
            stream_status=camera.stream_status or "NOT_TESTED",
            stream_verified=stream_verified,
            configurations=[
                CameraROIRead(
                    id=str(r.id),
                    camera_id=str(r.camera_id),
                    camera_code=r.camera_code,
                    profile_id=r.profile_id,
                    roi_type=r.roi_type,
                    name=r.name,
                    geometry_json=r.geometry_json,
                    normalized=r.normalized,
                    enabled=r.enabled,
                    version=r.version,
                    created_by=r.created_by,
                    updated_by=r.updated_by,
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

        # 1. Check AI profile assignment exists
        asgn = await self.ai_repo.get_assignment(camera.id, req.profile_id)
        if not asgn:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "AI_PROFILE_NOT_ASSIGNED",
                    "message": f"Profile '{req.profile_id}' is not assigned to camera {camera.camera_code}",
                },
            )

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
        roi = CameraROIConfiguration(
            camera_id=camera.id,
            camera_code=camera.camera_code,
            profile_id=req.profile_id,
            roi_type=req.roi_type,
            name=req.name.strip(),
            geometry_json=req.geometry_json,
            normalized=req.normalized,
            enabled=req.enabled,
            version=1,
            created_by=current_user.username,
            updated_by=current_user.username,
        )
        saved_roi = await self.repo.create(roi)
        await self.db.commit()

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
                "ai",
                {
                    "event_type": "AI_GEOMETRY_CHANGED",
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
        if req.enabled is not None:
            roi.enabled = req.enabled
        if req.geometry_json is not None:
            struct_ok, err_code, struct_err = self.validate_geometry_structure(roi.roi_type, req.geometry_json)
            if not struct_ok:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": err_code, "message": struct_err},
                )
            roi.geometry_json = req.geometry_json

        # Increment version
        roi.version += 1
        roi.updated_by = current_user.username

        updated_roi = await self.repo.update(roi)
        await self.db.commit()

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
                "ai",
                {
                    "event_type": "AI_GEOMETRY_CHANGED",
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
                "ai",
                {
                    "event_type": "AI_GEOMETRY_CHANGED",
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
