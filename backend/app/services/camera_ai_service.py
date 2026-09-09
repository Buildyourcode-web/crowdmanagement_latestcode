"""
camera_ai_service.py — Service layer for Camera AI Profile Assignments.

Handles:
- Camera purpose vs AI profile compatibility rules
- FRS isolation and RBAC checks
- Pre-flight server capacity validation with safety headroom
- Audit logging of all assignment changes
- Zero AI inference execution (configuration only)
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.capacity.calculator import CapacityCalculator
from app.ai.profiles.service import AIProfile, AIProfileService, STANDARD_PROFILES
from app.ai.runtime.detector import RuntimeDetector
from app.models.audit_log import AuditLog
from app.models.camera import Camera
from app.models.camera_ai_assignment import CameraAIProfileAssignment
from app.models.user import User
from app.redis.event_bus import event_bus
from app.repositories.camera_ai_repository import CameraAIRepository
from app.repositories.camera_repository import CameraRepository
from app.schemas.camera_ai import (
    AvailableProfileItem,
    CameraAIAssignmentRead,
    CameraAIAssignRequest,
    CameraAIConfigResponse,
    CameraAIValidateRequest,
    CameraAIValidateResponse,
)
from app.security.permissions import Permissions


# ── Purpose Compatibility Mapping ─────────────────────────────────────────────

PURPOSE_COMPATIBLE_PROFILES: Dict[str, List[str]] = {
    "CROWD": [
        "CROWD_STANDARD",
        "CROWD_HIGH_DENSITY",
        "CROWD_YOLO11X",
    ],
    "QUEUE": [
        "QUEUE_STANDARD",
        "QUEUE_YOLO11X",
    ],
    "FRS": ["FRS_STANDARD"],
    "GENERAL": ["VIDEO_SAFETY", "CROWD_STANDARD", "CROWD_YOLO11X"],
    "MULTI_PURPOSE": [
        "CROWD_STANDARD",
        "CROWD_HIGH_DENSITY",
        "CROWD_YOLO11X",
        "QUEUE_STANDARD",
        "QUEUE_YOLO11X",
        "VIDEO_SAFETY",
        "FRS_STANDARD",
    ],
}


class CameraAIService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.camera_repo = CameraRepository(db)
        self.ai_repo = CameraAIRepository(db)

    @classmethod
    def check_compatibility(cls, camera_purpose: str, profile_id: str) -> Tuple[bool, Optional[str]]:
        """
        Validates whether a profile is compatible with the camera's operational purpose.
        Returns (is_compatible, rejection_reason).
        """
        purpose = (camera_purpose or "CROWD").strip().upper()
        allowed = PURPOSE_COMPATIBLE_PROFILES.get(purpose, [])
        if profile_id not in allowed:
            return False, f"Profile '{profile_id}' is not compatible with camera purpose '{purpose}'. Allowed: {allowed}"
        return True, None

    @classmethod
    def check_frs_authorization(cls, user: User, camera_purpose: str) -> Tuple[bool, Optional[str]]:
        """
        FRS Isolation: FRS profiles can ONLY be configured on FRS or MULTI_PURPOSE cameras,
        and strictly requires authorized FRS RBAC permissions.
        """
        purpose = (camera_purpose or "").strip().upper()
        if purpose not in ("FRS", "MULTI_PURPOSE"):
            return False, f"FRS profiles cannot be assigned to cameras with purpose '{purpose}'. Camera purpose must be 'FRS' or 'MULTI_PURPOSE'."

        # Super admin override
        if user.role and user.role.code == "SUPER_ADMIN":
            return True, None

        user_perms = [p.code for p in user.role.permissions] if user.role and user.role.permissions else []
        has_frs_perm = (
            Permissions.FRS_MANAGE in user_perms
            or Permissions.FRS_REVIEW in user_perms
            or Permissions.FRS_READ in user_perms
        )
        if not has_frs_perm:
            return False, "User does not possess authorized FRS permissions (FRS_MANAGE / FRS_REVIEW) required to configure facial recognition workloads."

        return True, None

    async def _get_current_deployment_workload(self, exclude_assignment_id: Optional[uuid.UUID] = None) -> Dict[str, int]:
        """Calculates active workload dictionary across all enabled camera assignments."""
        active_assignments = await self.ai_repo.get_all_active_assignments()
        workload: Dict[str, int] = {}
        for a in active_assignments:
            if exclude_assignment_id and a.id == exclude_assignment_id:
                continue
            workload[a.profile_id] = workload.get(a.profile_id, 0) + 1
        return workload

    async def get_camera_ai_config(self, camera_code: str, user: User) -> CameraAIConfigResponse:
        """Retrieves camera AI configuration, compatible profiles, and capacity projection."""
        camera = await self.camera_repo.get_by_code(camera_code)
        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CAMERA_NOT_FOUND", "message": f"Camera '{camera_code}' not found."},
            )

        assignments = await self.ai_repo.get_assignments_for_camera(camera.id)
        assigned_profile_ids = {a.profile_id: a for a in assignments}

        # Build available profiles with compatibility info
        available_profiles = []
        for p in AIProfileService.list_profiles():
            is_compat, reason = self.check_compatibility(camera.camera_type, p.profile_id)
            if p.profile_id == "FRS_STANDARD" and is_compat:
                is_auth, auth_reason = self.check_frs_authorization(user, camera.camera_type)
                if not is_auth:
                    is_compat = False
                    reason = auth_reason

            available_profiles.append(
                AvailableProfileItem(
                    profile_id=p.profile_id,
                    name=p.name,
                    type=p.type.value,
                    pipeline_type=p.pipeline_type,
                    compatible=is_compat,
                    compatibility_reason=reason,
                    assigned=p.profile_id in assigned_profile_ids,
                    workload=p.workload.model_dump(),
                    gpu_requirements=p.gpu_requirements.model_dump(),
                    description=p.description,
                )
            )

        # Build assignments read models
        assignment_reads = []
        for a in assignments:
            profile = AIProfileService.get_profile(a.profile_id)
            assignment_reads.append(
                CameraAIAssignmentRead(
                    id=str(a.id),
                    camera_id=str(a.camera_id),
                    camera_code=a.camera_code,
                    profile_id=a.profile_id,
                    profile_name=profile.name if profile else a.profile_id,
                    enabled=a.enabled,
                    validation_status=a.validation_status,
                    validation_message=a.validation_message,
                    workload_estimate=profile.workload.model_dump() if profile else None,
                    assigned_at=a.assigned_at,
                    assigned_by=a.assigned_by,
                    metadata_json=a.metadata_json,
                )
            )

        # Calculate current deployment capacity projection
        current_workload = await self._get_current_deployment_workload()
        cpu_info = RuntimeDetector.detect_cpu()
        ram_info = RuntimeDetector.detect_ram()
        gpu_info = RuntimeDetector.detect_gpu()

        capacity_projection = CapacityCalculator.calculate_mixed_workload_capacity(
            current_workload, cpu_info, ram_info, gpu_info
        )

        return CameraAIConfigResponse(
            camera_id=camera.camera_code,
            camera_name=camera.name,
            camera_purpose=camera.camera_type,
            available_profiles=available_profiles,
            assignments=assignment_reads,
            deployment_projection=capacity_projection.model_dump(),
        )

    async def validate_profile_assignment(
        self,
        camera_code: str,
        req: CameraAIValidateRequest,
        user: User,
    ) -> CameraAIValidateResponse:
        """
        Pre-flight dry-run validation of a proposed profile assignment.
        Returns detailed resource budget impact, bottleneck, and verdict without saving.
        """
        camera = await self.camera_repo.get_by_code(camera_code)
        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CAMERA_NOT_FOUND", "message": f"Camera '{camera_code}' not found."},
            )

        profile = AIProfileService.get_profile(req.profile_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "AI_PROFILE_NOT_FOUND", "message": f"AI Profile '{req.profile_id}' not found."},
            )

        # 1. Check compatibility
        is_compat, reason = self.check_compatibility(camera.camera_type, req.profile_id)
        if not is_compat:
            return CameraAIValidateResponse(
                camera_id=camera.camera_code,
                profile_id=req.profile_id,
                compatible=False,
                compatibility_reason=reason,
                verdict="BLOCKED",
                status="INVALID",
                reason=reason or "Profile not compatible with camera purpose.",
                current_workload={},
                projected_workload={},
                current_utilization={},
                requested_utilization={},
                projected_utilization={},
                safe_budget={},
                hard_max_budget={},
                remaining_capacity={},
                exceeded_resources=[],
            )

        # 2. Check FRS isolation
        if req.profile_id == "FRS_STANDARD":
            is_auth, auth_reason = self.check_frs_authorization(user, camera.camera_type)
            if not is_auth:
                return CameraAIValidateResponse(
                    camera_id=camera.camera_code,
                    profile_id=req.profile_id,
                    compatible=False,
                    compatibility_reason=auth_reason,
                    verdict="BLOCKED",
                    status="INVALID",
                    reason=auth_reason or "FRS assignment not authorized.",
                    current_workload={},
                    projected_workload={},
                    current_utilization={},
                    requested_utilization={},
                    projected_utilization={},
                    safe_budget={},
                    hard_max_budget={},
                    remaining_capacity={},
                    exceeded_resources=[],
                )

        # 3. Capacity calculation
        current_workload = await self._get_current_deployment_workload()
        requested_addition = {req.profile_id: 1} if req.enabled else {}

        cpu_info = RuntimeDetector.detect_cpu()
        ram_info = RuntimeDetector.detect_ram()
        gpu_info = RuntimeDetector.detect_gpu()

        validation = CapacityCalculator.validate_capacity_for_deployment(
            current_workload, requested_addition, cpu_info, ram_info, gpu_info
        )

        combined_workload = dict(current_workload)
        if req.enabled:
            combined_workload[req.profile_id] = combined_workload.get(req.profile_id, 0) + 1

        projected = CapacityCalculator.calculate_mixed_workload_capacity(
            combined_workload, cpu_info, ram_info, gpu_info
        )

        # Workload estimate for requested profile
        req_util = {
            "gpu_percent": profile.workload.estimated_gpu_load_percent,
            "vram_gb": profile.workload.estimated_vram_gb,
            "cpu_percent": profile.workload.estimated_cpu_percent,
            "ram_gb": round(profile.workload.estimated_ram_mb / 1024.0, 2),
        }

        remaining_safe = {
            "gpu_percent": max(0.0, round(projected.safe_budget.gpu_percent - projected.projected_usage.gpu_percent, 1)),
            "vram_gb": max(0.0, round(projected.safe_budget.vram_gb - projected.projected_usage.vram_gb, 2)),
            "cpu_percent": max(0.0, round(projected.safe_budget.cpu_percent - projected.projected_usage.cpu_percent, 1)),
            "ram_gb": max(0.0, round(projected.safe_budget.ram_gb - projected.projected_usage.ram_gb, 2)),
        }

        return CameraAIValidateResponse(
            camera_id=camera.camera_code,
            profile_id=req.profile_id,
            compatible=True,
            compatibility_reason=None,
            verdict=validation.verdict,
            status=validation.status,
            reason=validation.reason,
            current_workload=current_workload,
            projected_workload=combined_workload,
            current_utilization=projected.current_usage.model_dump(),
            requested_utilization=req_util,
            projected_utilization=projected.projected_usage.model_dump(),
            safe_budget=projected.safe_budget.model_dump(),
            hard_max_budget=projected.hard_max_budget.model_dump(),
            remaining_capacity=remaining_safe,
            exceeded_resources=validation.exceeded_resources,
        )

    async def assign_profile_to_camera(
        self,
        camera_code: str,
        req: CameraAIAssignRequest,
        user: User,
        client_ip: Optional[str] = None,
    ) -> CameraAIAssignmentRead:
        """
        Assigns an AI workload profile to a camera with capacity verification and duplicate protection.
        IMPORTANT: Configures desired state only. Does NOT start AI inference.
        """
        camera = await self.camera_repo.get_by_code(camera_code)
        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CAMERA_NOT_FOUND", "message": f"Camera '{camera_code}' not found."},
            )

        profile = AIProfileService.get_profile(req.profile_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "AI_PROFILE_NOT_FOUND", "message": f"AI Profile '{req.profile_id}' not found."},
            )

        # 1. Compatibility check
        is_compat, reason = self.check_compatibility(camera.camera_type, req.profile_id)
        if not is_compat:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "AI_PROFILE_NOT_COMPATIBLE", "message": reason},
            )

        # 2. FRS isolation check
        if req.profile_id == "FRS_STANDARD":
            is_auth, auth_reason = self.check_frs_authorization(user, camera.camera_type)
            if not is_auth:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"code": "FRS_ASSIGNMENT_NOT_AUTHORIZED", "message": auth_reason},
                )

        # 3. Duplicate check on (camera_id, profile_id)
        existing = await self.ai_repo.get_assignment(camera.id, req.profile_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "AI_PROFILE_ALREADY_ASSIGNED",
                    "message": f"Profile '{req.profile_id}' is already assigned to camera '{camera_code}'.",
                },
            )

        # 4. Capacity pre-flight check before saving
        current_workload = await self._get_current_deployment_workload()
        requested_addition = {req.profile_id: 1} if req.enabled else {}

        cpu_info = RuntimeDetector.detect_cpu()
        ram_info = RuntimeDetector.detect_ram()
        gpu_info = RuntimeDetector.detect_gpu()

        val_result = CapacityCalculator.validate_capacity_for_deployment(
            current_workload, requested_addition, cpu_info, ram_info, gpu_info
        )

        if val_result.verdict == "BLOCKED":
            # Record audit log of rejection
            audit_rej = AuditLog(
                user_id=user.id,
                username=user.username,
                action="AI_PROFILE_ASSIGNMENT_REJECTED",
                resource_type="camera_ai_assignment",
                resource_id=f"{camera.camera_code}:{req.profile_id}",
                ip_address=client_ip,
                metadata_json={
                    "camera_code": camera.camera_code,
                    "profile_id": req.profile_id,
                    "reason": val_result.reason,
                    "exceeded_resources": val_result.exceeded_resources,
                },
            )
            self.db.add(audit_rej)
            await self.db.commit()

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "AI_CAPACITY_EXCEEDED",
                    "message": val_result.reason,
                    "exceeded_resources": val_result.exceeded_resources,
                    "projected_utilization": val_result.projected_utilization.model_dump(),
                },
            )

        # 5. Persist assignment
        assignment = CameraAIProfileAssignment(
            camera_id=camera.id,
            camera_code=camera.camera_code,
            profile_id=req.profile_id,
            enabled=req.enabled,
            metadata_json=req.metadata_json or {},
            assigned_at=datetime.now(timezone.utc),
            assigned_by=user.username,
            validation_status=val_result.status,
            validation_message=val_result.reason,
        )

        self.db.add(assignment)

        # 6. Audit log
        audit = AuditLog(
            user_id=user.id,
            username=user.username,
            action="AI_PROFILE_ASSIGNED",
            resource_type="camera_ai_assignment",
            resource_id=f"{camera.camera_code}:{req.profile_id}",
            ip_address=client_ip,
            metadata_json={
                "camera_code": camera.camera_code,
                "profile_id": req.profile_id,
                "enabled": req.enabled,
                "validation_status": val_result.status,
            },
        )
        self.db.add(audit)
        await self.db.commit()
        await self.db.refresh(assignment)

        # 7. Broadcast WebSocket event
        await event_bus.publish(
            channel="ai",
            event_type="AI_CONFIGURATION_CHANGED",
            payload={
                "camera_id": camera.camera_code,
                "profile_id": req.profile_id,
                "action": "ASSIGNED",
                "validation_status": val_result.status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        logger.info(f"[CameraAIService] Assigned profile {req.profile_id} to camera {camera.camera_code} (State configured - NO inference started)")

        return CameraAIAssignmentRead(
            id=str(assignment.id),
            camera_id=str(assignment.camera_id),
            camera_code=assignment.camera_code,
            profile_id=assignment.profile_id,
            profile_name=profile.name,
            enabled=assignment.enabled,
            validation_status=assignment.validation_status,
            validation_message=assignment.validation_message,
            workload_estimate=profile.workload.model_dump(),
            assigned_at=assignment.assigned_at,
            assigned_by=assignment.assigned_by,
            metadata_json=assignment.metadata_json,
        )

    async def update_profile_assignment(
        self,
        camera_code: str,
        profile_id: str,
        req: CameraAIAssignRequest,
        user: User,
        client_ip: Optional[str] = None,
    ) -> CameraAIAssignmentRead:
        """Updates an existing camera AI profile assignment."""
        camera = await self.camera_repo.get_by_code(camera_code)
        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CAMERA_NOT_FOUND", "message": f"Camera '{camera_code}' not found."},
            )

        assignment = await self.ai_repo.get_assignment_by_code(camera_code, profile_id)
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "ASSIGNMENT_NOT_FOUND", "message": f"Profile '{profile_id}' is not assigned to camera '{camera_code}'."},
            )

        # If re-enabling, check capacity
        if req.enabled and not assignment.enabled:
            current_workload = await self._get_current_deployment_workload(exclude_assignment_id=assignment.id)
            cpu_info = RuntimeDetector.detect_cpu()
            ram_info = RuntimeDetector.detect_ram()
            gpu_info = RuntimeDetector.detect_gpu()
            val_result = CapacityCalculator.validate_capacity_for_deployment(
                current_workload, {profile_id: 1}, cpu_info, ram_info, gpu_info
            )
            if val_result.verdict == "BLOCKED":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "AI_CAPACITY_EXCEEDED", "message": val_result.reason},
                )

        assignment.enabled = req.enabled
        if req.metadata_json is not None:
            assignment.metadata_json = req.metadata_json

        audit = AuditLog(
            user_id=user.id,
            username=user.username,
            action="AI_PROFILE_UPDATED",
            resource_type="camera_ai_assignment",
            resource_id=f"{camera.camera_code}:{profile_id}",
            ip_address=client_ip,
            metadata_json={"enabled": req.enabled, "metadata": req.metadata_json},
        )
        self.db.add(audit)
        await self.db.commit()
        await self.db.refresh(assignment)

        profile = AIProfileService.get_profile(profile_id)
        await event_bus.publish(
            channel="ai",
            event_type="AI_CONFIGURATION_CHANGED",
            payload={
                "camera_id": camera.camera_code,
                "profile_id": profile_id,
                "action": "UPDATED",
                "enabled": req.enabled,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return CameraAIAssignmentRead(
            id=str(assignment.id),
            camera_id=str(assignment.camera_id),
            camera_code=assignment.camera_code,
            profile_id=assignment.profile_id,
            profile_name=profile.name if profile else profile_id,
            enabled=assignment.enabled,
            validation_status=assignment.validation_status,
            validation_message=assignment.validation_message,
            workload_estimate=profile.workload.model_dump() if profile else None,
            assigned_at=assignment.assigned_at,
            assigned_by=assignment.assigned_by,
            metadata_json=assignment.metadata_json,
        )

    async def remove_profile_assignment(
        self,
        camera_code: str,
        profile_id: str,
        user: User,
        client_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Removes an AI profile assignment from a camera."""
        camera = await self.camera_repo.get_by_code(camera_code)
        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CAMERA_NOT_FOUND", "message": f"Camera '{camera_code}' not found."},
            )

        assignment = await self.ai_repo.get_assignment_by_code(camera_code, profile_id)
        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "ASSIGNMENT_NOT_FOUND", "message": f"Profile '{profile_id}' is not assigned to camera '{camera_code}'."},
            )

        await self.db.delete(assignment)

        audit = AuditLog(
            user_id=user.id,
            username=user.username,
            action="AI_PROFILE_REMOVED",
            resource_type="camera_ai_assignment",
            resource_id=f"{camera.camera_code}:{profile_id}",
            ip_address=client_ip,
            metadata_json={"camera_code": camera.camera_code, "profile_id": profile_id},
        )
        self.db.add(audit)
        await self.db.commit()

        await event_bus.publish(
            channel="ai",
            event_type="AI_CONFIGURATION_CHANGED",
            payload={
                "camera_id": camera.camera_code,
                "profile_id": profile_id,
                "action": "REMOVED",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return {"message": f"AI Profile '{profile_id}' removed from camera '{camera_code}'.", "camera_id": camera_code, "profile_id": profile_id}
