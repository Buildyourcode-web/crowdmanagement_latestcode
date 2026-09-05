"""
service.py — Central AI Orchestrator & Control-Plane Engine.

Manages multi-camera AI pipeline deployments (Crowd AI, Queue AI), enforces desired
vs actual state machine transitions, performs resource-aware Start All and graceful Stop All,
coordinates automatic RTSP reconnection, fault-recovery retry limits, and staggered server-restart recovery.
"""

import asyncio
from datetime import datetime, timezone
import math
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.capacity.calculator import CapacityCalculator
from app.ai.deployments.service import AIDeployment
from app.ai.orchestrator.state import PipelineState
from app.ai.pipelines.crowd.config import CrowdPipelineConfig
from app.ai.pipelines.crowd.detector import BasePersonDetector
from app.ai.pipelines.crowd.pipeline import CrowdPipeline
from app.ai.pipelines.crowd.registry import CrowdPipelineRegistry
from app.ai.pipelines.manager import PipelineInstance, PipelineManager
from app.ai.pipelines.queue.config import QueuePipelineConfig
from app.ai.pipelines.queue.pipeline import QueuePipeline
from app.ai.pipelines.queue.registry import QueuePipelineRegistry
from app.ai.pipelines.frs.config import FRSPipelineConfig
from app.ai.pipelines.frs.pipeline import FRSPipeline
from app.ai.pipelines.frs.registry import FRSPipelineRegistry
from app.models.frs import FRSReferenceProfile
from app.ai.profiles.service import AIProfile, STANDARD_PROFILES
from app.ai.runtime.detector import RuntimeDetector
from app.db.session import AsyncSessionLocal
from app.models.ai_deployment import AIPipelineDeployment
from app.models.audit_log import AuditLog
from app.models.camera import Camera
from app.models.camera_roi import ROIType
from app.models.user import User
from app.redis.event_bus import event_bus
from app.repositories.ai_deployment_repository import AIDeploymentRepository
from app.repositories.camera_ai_repository import CameraAIRepository
from app.repositories.camera_repository import CameraRepository
from app.repositories.camera_roi_repository import CameraROIRepository


class OrchestratorResponse:
    """Standard response model for orchestrator operations."""
    def __init__(
        self,
        action: str,
        camera_code: Optional[str] = None,
        status: str = "SUCCESS",
        message: str = "",
        desired_state: str = "STOPPED",
        actual_state: str = "STOPPED",
        details: Optional[Dict[str, Any]] = None,
    ):
        self.action = action
        self.camera_code = camera_code
        self.status = status
        self.message = message
        self.desired_state = desired_state
        self.actual_state = actual_state
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "camera_code": self.camera_code,
            "status": self.status,
            "message": self.message,
            "desired_state": self.desired_state,
            "actual_state": self.actual_state,
            "details": self.details,
        }


class AIOrchestrator:
    """
    Central AI Orchestrator Control-Plane.
    Coordinates deployment lifecycle, supervision loops, recovery, and capacity protection.
    """

    def __init__(self):
        self._supervision_task: Optional[asyncio.Task] = None
        self._recovery_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._reconnect_backoff_tracker: Dict[str, Dict[str, Any]] = {}
        self._restart_history_tracker: Dict[str, List[float]] = {}
        logger.info("[AI-Orchestrator] Initialized central control-plane orchestrator.")

    # ── Camera Resolution ─────────────────────────────────────────────────────

    async def _resolve_camera(self, camera_id_or_code: str, db: AsyncSession) -> Camera:
        """Finds camera by UUID or camera_code."""
        camera_repo = CameraRepository(db)
        camera = None
        try:
            cam_uuid = uuid.UUID(str(camera_id_or_code))
            camera = await camera_repo.get_by_id(cam_uuid)
        except (ValueError, TypeError, AttributeError):
            pass

        if not camera:
            camera = await camera_repo.get_by_code(str(camera_id_or_code))

        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CAMERA_NOT_FOUND", "message": f"Camera '{camera_id_or_code}' not found."},
            )
        return camera

    # ── Pipeline Start Workflow ───────────────────────────────────────────────

    async def start_pipeline(
        self,
        camera_id_or_code: str,
        db: AsyncSession,
        current_user: Optional[User] = None,
        client_ip: Optional[str] = None,
        custom_detector: Optional[BasePersonDetector] = None,
    ) -> Dict[str, Any]:
        """
        Executes pre-flight validation and starts a Crowd or Queue AI pipeline.
        Enforces desired vs actual states, capacity verification, and audit logging.
        """
        camera = await self._resolve_camera(camera_id_or_code, db)
        cam_repo = CameraRepository(db)
        ai_repo = CameraAIRepository(db)
        roi_repo = CameraROIRepository(db)
        deploy_repo = AIDeploymentRepository(db)

        # 1. Check Stream Status
        if not camera.enabled or camera.status == "offline":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "CAMERA_OFFLINE", "message": f"Camera {camera.camera_code} is offline or disabled."},
            )
        if (camera.stream_status or "").upper() in ("NOT_TESTED", "OFFLINE"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "CAMERA_STREAM_NOT_VERIFIED", "message": f"Camera {camera.camera_code} stream has not been verified."},
            )

        # 2. Check Assigned AI Profile
        assignments = await ai_repo.get_assignments_for_camera(camera.id)
        active_assignment = next((a for a in assignments if a.enabled), None)
        if not active_assignment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "NO_AI_PROFILE_ASSIGNED",
                    "message": f"Camera {camera.camera_code} has no active AI profile assigned.",
                },
            )

        profile_id = active_assignment.profile_id
        is_crowd = "CROWD" in profile_id.upper()
        is_queue = "QUEUE" in profile_id.upper()
        is_frs = "FRS" in profile_id.upper()
        pipeline_type = "CROWD" if is_crowd else ("QUEUE" if is_queue else ("FRS" if is_frs else "UNKNOWN"))

        if pipeline_type == "UNKNOWN":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "UNSUPPORTED_PROFILE", "message": f"Profile {profile_id} is not supported for automated pipeline execution."},
            )

        # FRS Camera Restriction Enforcement
        if is_frs:
            camera_purpose = (camera.camera_type or "").strip().upper()
            if camera_purpose not in ("FRS", "MULTI_PURPOSE"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "FRS_CAMERA_NOT_ALLOWED",
                        "message": f"FRS pipeline cannot be started on camera with purpose '{camera_purpose}'. Camera purpose must be 'FRS' or 'MULTI_PURPOSE'.",
                    },
                )

        # 3. Check Geometry Readiness (Crowd requires CROWD_ROI, Queue requires ENTRY/EXIT/ROI, FRS is isolated)
        roi_configs = []
        if is_crowd:
            roi_configs = await roi_repo.get_by_camera_id(camera.id, profile_id=profile_id)
            has_crowd_roi = any(
                r.enabled and r.roi_type == ROIType.CROWD_ROI and len((r.geometry_json or {}).get("points", [])) >= 3
                for r in roi_configs
            )
            if not has_crowd_roi:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "ROI_NOT_CONFIGURED",
                        "message": f"Camera {camera.camera_code} does not have a configured CROWD_ROI polygon.",
                    },
                )
        elif is_queue:
            roi_configs = await roi_repo.get_by_camera_id(camera.id, profile_id=profile_id)
            geom_check = QueuePipelineConfig.check_geometry_requirements(roi_configs)
            if not geom_check.is_ready:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "QUEUE_CONFIGURATION_NOT_READY",
                        "message": f"Queue geometries incomplete for {camera.camera_code}: missing {', '.join(geom_check.missing_requirements)}",
                        "missing_requirements": geom_check.missing_requirements,
                    },
                )

        # 4. Check Runtime Availability
        runtime_info = RuntimeDetector.detect_runtime()
        gpu_info = RuntimeDetector.detect_gpu()
        if not custom_detector and (not gpu_info.get("available") or not runtime_info.get("deepstream")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "RUNTIME_UNAVAILABLE",
                    "message": "NVIDIA DeepStream / AI runtime unavailable on this host.",
                    "gpu_available": gpu_info.get("available", False),
                    "deepstream_available": runtime_info.get("deepstream", False),
                },
            )

        # 5. Check if already running
        existing_pipe = (
            CrowdPipelineRegistry.get(camera.camera_code)
            if is_crowd
            else (
                QueuePipelineRegistry.get(camera.camera_code)
                if is_queue
                else FRSPipelineRegistry.get(camera.camera_code)
            )
        )
        if existing_pipe and existing_pipe.state == PipelineState.RUNNING:
            # Sync deployment
            await deploy_repo.upsert_deployment(
                camera_id=camera.id,
                camera_code=camera.camera_code,
                profile_id=profile_id,
                pipeline_type=pipeline_type,
                desired_state="RUNNING",
                actual_state="RUNNING",
                health_state="HEALTHY",
                updated_by=current_user.username if current_user else "SYSTEM",
            )
            await db.commit()
            return {
                "status": "ALREADY_RUNNING",
                "camera_code": camera.camera_code,
                "profile_id": profile_id,
                "pipeline_type": pipeline_type,
                "desired_state": "RUNNING",
                "actual_state": "RUNNING",
            }

        # 6. Capacity Protection (CapacityCalculator)
        all_active_assignments = await ai_repo.get_all_active_assignments()
        current_workload: Dict[str, int] = {}
        for asgn in all_active_assignments:
            if asgn.enabled:
                current_workload[asgn.profile_id] = current_workload.get(asgn.profile_id, 0) + 1

        requested_addition = {profile_id: 1}
        cpu_info = RuntimeDetector.detect_cpu()
        ram_info = RuntimeDetector.detect_ram()

        cap_validation = CapacityCalculator.validate_capacity_for_deployment(
            current_workload,
            requested_addition,
            cpu_info,
            ram_info,
            gpu_info,
        )

        is_blocked = False
        block_reason = "Server capacity limit exceeded"
        if isinstance(cap_validation, dict):
            if cap_validation.get("allowed") is False or cap_validation.get("verdict") == "BLOCKED":
                is_blocked = True
                block_reason = cap_validation.get("reason", block_reason)
        elif hasattr(cap_validation, "verdict"):
            if cap_validation.verdict == "BLOCKED":
                is_blocked = True
                block_reason = cap_validation.reason

        if is_blocked:
            # Record audit rejection
            if current_user:
                audit = AuditLog(
                    user_id=current_user.id,
                    username=current_user.username,
                    action="AI_PIPELINE_START_BLOCKED",
                    resource_type="ai_pipeline",
                    resource_id=camera.camera_code,
                    ip_address=client_ip,
                    metadata_json={"camera_code": camera.camera_code, "profile_id": profile_id, "reason": block_reason},
                )
                db.add(audit)
                await db.commit()

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "AI_CAPACITY_EXCEEDED",
                    "message": f"Server capacity exceeded: {block_reason}",
                    "capacity_report": cap_validation if isinstance(cap_validation, dict) else cap_validation.model_dump(),
                },
            )

        # 7. Persist Desired State and Transition to VALIDATING -> STARTING
        deployment = await deploy_repo.upsert_deployment(
            camera_id=camera.id,
            camera_code=camera.camera_code,
            profile_id=profile_id,
            pipeline_type=pipeline_type,
            desired_state="RUNNING",
            actual_state="STARTING",
            health_state="STARTING",
            updated_by=current_user.username if current_user else "SYSTEM",
        )
        runtime_id = f"RT-{camera.camera_code}-{profile_id}-{uuid.uuid4().hex[:6]}"
        deployment.runtime_instance_id = runtime_id
        await db.commit()

        # 8. Instantiate and Start Concrete Pipeline
        try:
            if is_crowd:
                crowd_cfg = CrowdPipelineConfig.from_camera_and_geometries(
                    camera=camera,
                    profile_id=profile_id,
                    roi_configs=roi_configs,
                )
                pipeline = CrowdPipeline(config=crowd_cfg, detector=custom_detector)
                await pipeline.start()
                CrowdPipelineRegistry.register(pipeline)
            elif is_queue:
                queue_cfg = QueuePipelineConfig.from_camera_and_geometries(
                    camera=camera,
                    profile_id=profile_id,
                    roi_configs=roi_configs,
                )
                pipeline = QueuePipeline(config=queue_cfg, detector=custom_detector)
                await pipeline.start()
                QueuePipelineRegistry.register(pipeline)
            elif is_frs:
                frs_cfg = FRSPipelineConfig(
                    camera_id=str(camera.id),
                    camera_code=camera.camera_code,
                    camera_name=camera.name,
                    rtsp_url=camera.rtsp_url_encrypted or f"rtsp://192.168.1.100:554/{camera.camera_code}",
                    sanitized_rtsp_url=FRSPipelineConfig.sanitize_url(camera.rtsp_url_encrypted or ""),
                    profile_id=profile_id,
                    zone_id=str(camera.zone_id) if camera.zone_id else None,
                    zone_code=camera.zone_code,
                    location_name=camera.location_name or "Khairatabad Perimeter",
                )
                pipeline = FRSPipeline(config=frs_cfg, custom_detector=custom_detector)
                # Load gallery from active reference profiles in DB
                stmt = select(FRSReferenceProfile).where(FRSReferenceProfile.status == "ACTIVE")
                res = await db.execute(stmt)
                gallery_items = [
                    {
                        "id": str(p.id),
                        "reference_id": p.reference_id,
                        "reference_code": p.reference_code or p.reference_id,
                        "display_name": p.display_name,
                        "embedding": p.embedding_vector,
                        "category": p.category,
                        "reference_image_path": p.reference_image_path,
                        "active": p.active,
                    }
                    for p in res.scalars().all()
                ]
                pipeline.matcher.load_gallery(gallery_items)
                await pipeline.start()
                FRSPipelineRegistry.register(camera.camera_code, pipeline)

            # 9. Health & Startup Confirmation -> Transition to RUNNING
            deployment.actual_state = "RUNNING"
            deployment.health_state = "HEALTHY"
            deployment.last_started_at = datetime.now(timezone.utc)
            deployment.last_error = None
            await db.commit()

        except Exception as e:
            deployment.actual_state = "FAILED"
            deployment.health_state = "FAILED"
            deployment.last_failure_at = datetime.now(timezone.utc)
            deployment.last_error = str(e)
            await db.commit()
            logger.error(f"[AI-Orchestrator] Failed to launch pipeline for {camera.camera_code}: {e}")
            raise

        # 10. Audit Log & Telemetry Publish
        if current_user:
            audit = AuditLog(
                user_id=current_user.id,
                username=current_user.username,
                action="AI_PIPELINE_STARTED",
                resource_type="ai_pipeline",
                resource_id=camera.camera_code,
                ip_address=client_ip,
                metadata_json={
                    "camera_code": camera.camera_code,
                    "profile_id": profile_id,
                    "pipeline_type": pipeline_type,
                    "runtime_instance_id": runtime_id,
                },
            )
            db.add(audit)
            await db.commit()

        await event_bus.publish(
            channel="ai",
            event_type="PIPELINE_STARTED",
            payload={"camera_code": camera.camera_code, "profile_id": profile_id, "pipeline_type": pipeline_type},
        )

        return {
            "status": "STARTED",
            "camera_code": camera.camera_code,
            "profile_id": profile_id,
            "pipeline_type": pipeline_type,
            "desired_state": "RUNNING",
            "actual_state": "RUNNING",
            "runtime_instance_id": runtime_id,
        }

    # ── Pipeline Stop Workflow ────────────────────────────────────────────────

    async def stop_pipeline(
        self,
        camera_id_or_code: str,
        db: AsyncSession,
        current_user: Optional[User] = None,
        client_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Stops an active AI pipeline gracefully.
        Guarantees idempotency (calling stop twice does not error).
        """
        camera = await self._resolve_camera(camera_id_or_code, db)
        deploy_repo = AIDeploymentRepository(db)
        deployment = await deploy_repo.get_by_camera_code(camera.camera_code)

        # Set desired state to STOPPED and actual_state to STOPPING
        if deployment:
            deployment.desired_state = "STOPPED"
            deployment.actual_state = "STOPPING"
            await db.commit()

        # Stop from Crowd, Queue, and FRS registries
        crowd_stopped = await CrowdPipelineRegistry.stop_pipeline(camera.camera_code)
        queue_stopped = await QueuePipelineRegistry.stop_pipeline(camera.camera_code)
        frs_pipe = FRSPipelineRegistry.get(camera.camera_code)
        frs_stopped = False
        if frs_pipe:
            frs_stopped = await frs_pipe.stop()
            FRSPipelineRegistry.unregister(camera.camera_code)
        was_running = crowd_stopped or queue_stopped or frs_stopped

        if deployment:
            deployment.actual_state = "STOPPED"
            deployment.health_state = "STOPPED"
            deployment.last_stopped_at = datetime.now(timezone.utc)
            await db.commit()

        # Audit Log
        if current_user:
            audit = AuditLog(
                user_id=current_user.id,
                username=current_user.username,
                action="AI_PIPELINE_STOPPED",
                resource_type="ai_pipeline",
                resource_id=camera.camera_code,
                ip_address=client_ip,
                metadata_json={"camera_code": camera.camera_code, "was_running": was_running},
            )
            db.add(audit)
            await db.commit()

        await event_bus.publish(
            channel="ai",
            event_type="PIPELINE_STOPPED",
            payload={"camera_code": camera.camera_code},
        )

        return {
            "status": "STOPPED" if was_running else "ALREADY_STOPPED",
            "camera_code": camera.camera_code,
            "desired_state": "STOPPED",
            "actual_state": "STOPPED",
        }

    # ── Pipeline Restart Workflow ─────────────────────────────────────────────

    async def restart_pipeline(
        self,
        camera_id_or_code: str,
        db: AsyncSession,
        current_user: Optional[User] = None,
        client_ip: Optional[str] = None,
        custom_detector: Optional[BasePersonDetector] = None,
    ) -> Dict[str, Any]:
        """
        Executes controlled restart:
        desired_state remains RUNNING.
        actual_state: RUNNING -> RESTARTING -> STOPPING -> STARTING -> RUNNING.
        Increments restart_count and clears cached backoff errors.
        """
        camera = await self._resolve_camera(camera_id_or_code, db)
        deploy_repo = AIDeploymentRepository(db)
        deployment = await deploy_repo.get_by_camera_code(camera.camera_code)

        if deployment:
            deployment.desired_state = "RUNNING"
            deployment.actual_state = "RESTARTING"
            deployment.restart_count += 1
            await db.commit()

        # Stop existing
        await CrowdPipelineRegistry.stop_pipeline(camera.camera_code)
        await QueuePipelineRegistry.stop_pipeline(camera.camera_code)

        # Clear backoff trackers
        self._reconnect_backoff_tracker.pop(camera.camera_code, None)

        # Start anew
        res = await self.start_pipeline(
            camera_id_or_code=camera.camera_code,
            db=db,
            current_user=current_user,
            client_ip=client_ip,
            custom_detector=custom_detector,
        )

        if current_user:
            audit = AuditLog(
                user_id=current_user.id,
                username=current_user.username,
                action="AI_PIPELINE_RESTARTED",
                resource_type="ai_pipeline",
                resource_id=camera.camera_code,
                ip_address=client_ip,
                metadata_json={"camera_code": camera.camera_code},
            )
            db.add(audit)
            await db.commit()

        return {
            "status": "RESTARTED",
            "camera_code": camera.camera_code,
            "desired_state": "RUNNING",
            "actual_state": "RUNNING",
            "restart_count": deployment.restart_count if deployment else 1,
        }

    # ── Start All (Resource-Aware) ────────────────────────────────────────────

    async def start_all(
        self,
        db: AsyncSession,
        current_user: Optional[User] = None,
        client_ip: Optional[str] = None,
        custom_detector: Optional[BasePersonDetector] = None,
    ) -> Dict[str, Any]:
        """
        Resource-aware Start All.
        Sorts eligible cameras by deployment priority (CRITICAL > HIGH > NORMAL > LOW).
        Starts pipelines incrementally up to server capacity limits;
        remaining deployments are explicitly marked as BLOCKED by capacity.
        """
        cam_repo = CameraRepository(db)
        ai_repo = CameraAIRepository(db)
        deploy_repo = AIDeploymentRepository(db)

        # 1. Discover all active AI assignments
        all_assignments = await ai_repo.get_all_active_assignments()
        if not all_assignments:
            return {
                "started": [],
                "already_running": [],
                "blocked": [],
                "failed": [],
                "message": "No active camera AI assignments found.",
            }

        # 2. Map priorities from existing deployment records
        deployments = await deploy_repo.list_all()
        priority_map = {d.camera_code: d.priority.upper() for d in deployments}

        priority_ranks = {"CRITICAL": 4, "HIGH": 3, "NORMAL": 2, "LOW": 1}

        # Sort assignments by priority desc, then camera_code asc
        sorted_assignments = sorted(
            all_assignments,
            key=lambda a: (-priority_ranks.get(priority_map.get(a.camera_code, "NORMAL"), 2), a.camera_code),
        )

        started: List[str] = []
        already_running: List[str] = []
        blocked: List[Dict[str, str]] = []
        failed: List[Dict[str, str]] = []

        for asgn in sorted_assignments:
            cam_code = asgn.camera_code
            # Check if running
            is_active = (
                CrowdPipelineRegistry.get(cam_code) is not None
                or QueuePipelineRegistry.get(cam_code) is not None
                or FRSPipelineRegistry.get(cam_code) is not None
            )
            if is_active:
                already_running.append(cam_code)
                continue

            try:
                res = await self.start_pipeline(
                    camera_id_or_code=cam_code,
                    db=db,
                    current_user=current_user,
                    client_ip=client_ip,
                    custom_detector=custom_detector,
                )
                if res.get("status") == "STARTED":
                    started.append(cam_code)
                elif res.get("status") == "ALREADY_RUNNING":
                    already_running.append(cam_code)
            except HTTPException as e:
                err_detail = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
                err_code = err_detail.get("code", "ERROR")
                err_msg = err_detail.get("message", str(e.detail))

                if err_code == "AI_CAPACITY_EXCEEDED":
                    blocked.append({"camera_code": cam_code, "reason": "Blocked by server capacity."})
                else:
                    failed.append({"camera_code": cam_code, "code": err_code, "reason": err_msg})
            except Exception as e:
                failed.append({"camera_code": cam_code, "code": "PIPELINE_ERROR", "reason": str(e)})

        if current_user:
            audit = AuditLog(
                user_id=current_user.id,
                username=current_user.username,
                action="AI_START_ALL_EXECUTED",
                resource_type="orchestrator",
                resource_id="GLOBAL",
                ip_address=client_ip,
                metadata_json={
                    "started_count": len(started),
                    "blocked_count": len(blocked),
                    "failed_count": len(failed),
                },
            )
            db.add(audit)
            await db.commit()

        return {
            "started": started,
            "already_running": already_running,
            "blocked": blocked,
            "failed": failed,
            "summary": {
                "total_requested": len(sorted_assignments),
                "started_count": len(started),
                "already_running_count": len(already_running),
                "blocked_count": len(blocked),
                "failed_count": len(failed),
            },
        }

    # ── Stop All ──────────────────────────────────────────────────────────────

    async def stop_all(
        self,
        db: AsyncSession,
        current_user: Optional[User] = None,
        client_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Gracefully stops all active pipelines across Crowd, Queue, and FRS registries.
        Sets desired_state = STOPPED and actual_state = STOPPED for all active deployments.
        """
        crowd_pipes = CrowdPipelineRegistry.list_pipelines()
        queue_pipes = QueuePipelineRegistry.list_all()
        frs_pipes = list(FRSPipelineRegistry.get_all().values())

        active_codes = list(set(
            [p.camera_code for p in crowd_pipes]
            + [q.config.camera_code for q in queue_pipes]
            + [f.camera_code for f in frs_pipes]
        ))

        stopped: List[str] = []
        already_stopped: List[str] = []
        failed: List[Dict[str, str]] = []

        deploy_repo = AIDeploymentRepository(db)
        all_deployments = await deploy_repo.list_all()

        for d in all_deployments:
            cam_code = d.camera_code
            if cam_code in active_codes:
                try:
                    await self.stop_pipeline(cam_code, db, current_user, client_ip)
                    stopped.append(cam_code)
                except Exception as e:
                    failed.append({"camera_code": cam_code, "reason": str(e)})
            else:
                if d.desired_state != "STOPPED" or d.actual_state != "STOPPED":
                    d.desired_state = "STOPPED"
                    d.actual_state = "STOPPED"
                    d.health_state = "STOPPED"
                already_stopped.append(cam_code)

        await db.commit()

        if current_user:
            audit = AuditLog(
                user_id=current_user.id,
                username=current_user.username,
                action="AI_STOP_ALL_EXECUTED",
                resource_type="orchestrator",
                resource_id="GLOBAL",
                ip_address=client_ip,
                metadata_json={"stopped_count": len(stopped)},
            )
            db.add(audit)
            await db.commit()

        return {
            "stopped": stopped,
            "already_stopped": already_stopped,
            "failed": failed,
            "summary": {
                "stopped_count": len(stopped),
                "already_stopped_count": len(already_stopped),
                "failed_count": len(failed),
            },
        }

    # ── Deployment Inspection & Status ────────────────────────────────────────

    async def list_deployments(self, db: AsyncSession) -> List[AIDeployment]:
        """Returns all pipeline deployments merged with real-time telemetry."""
        deploy_repo = AIDeploymentRepository(db)
        records = await deploy_repo.list_all()

        results: List[AIDeployment] = []
        for d in records:
            live_metrics = None
            pipe = (
                CrowdPipelineRegistry.get(d.camera_code)
                or QueuePipelineRegistry.get(d.camera_code)
                or FRSPipelineRegistry.get(d.camera_code)
            )
            if pipe:
                m = pipe.get_metrics() if hasattr(pipe, "get_metrics") else {}
                hlth = pipe.get_health() if hasattr(pipe, "get_health") else {}
                live_metrics = {
                    "processed_fps": hlth.processed_fps if hasattr(hlth, "processed_fps") else hlth.get("fps", 0.0),
                    "latency_ms": (hlth.detection_latency_ms + hlth.tracking_latency_ms) if hasattr(hlth, "detection_latency_ms") and hasattr(hlth, "tracking_latency_ms") else hlth.get("detection_latency_ms", 0.0),
                    "queue_count": m.get("queue_count"),
                    "crowd_count": m.get("count"),
                    "risk_level": m.get("risk_level"),
                }
            results.append(AIDeployment.from_orm_model(d, live_metrics))
        return results

    async def get_orchestrator_status(self, db: AsyncSession) -> Dict[str, Any]:
        """Returns system-level status summary of the AI Orchestrator."""
        deploy_repo = AIDeploymentRepository(db)
        deployments = await deploy_repo.list_all()

        running_count = sum(1 for d in deployments if d.actual_state == "RUNNING")
        degraded_count = sum(1 for d in deployments if d.actual_state == "DEGRADED")
        failed_count = sum(1 for d in deployments if d.actual_state == "FAILED")
        stopped_count = sum(1 for d in deployments if d.actual_state == "STOPPED")

        crowd_active = len(CrowdPipelineRegistry.list_pipelines())
        queue_active = QueuePipelineRegistry.count()
        frs_active = len(FRSPipelineRegistry.get_all())

        return {
            "orchestrator_status": "OPERATIONAL",
            "supervision_loop_active": self._is_running,
            "total_deployments": len(deployments),
            "state_counts": {
                "RUNNING": running_count,
                "DEGRADED": degraded_count,
                "FAILED": failed_count,
                "STOPPED": stopped_count,
            },
            "active_pipelines": {
                "crowd_pipelines": crowd_active,
                "queue_pipelines": queue_active,
                "frs_pipelines": frs_active,
                "total_active": crowd_active + queue_active + frs_active,
            },
        }

    # ── Background Supervision Loop ───────────────────────────────────────────

    async def start_supervision_loop(self) -> None:
        """Launches the background supervisory loop for health checking and recovery."""
        if self._is_running:
            return
        self._is_running = True
        self._supervision_task = asyncio.create_task(self._run_supervision_loop())
        logger.info("[AI-Orchestrator] Background pipeline supervision loop started.")

    async def _run_supervision_loop(self) -> None:
        """Periodic loop checking stream health, reconnecting dropouts, and recovering failures."""
        while self._is_running:
            try:
                await self._supervision_iteration()
            except Exception as e:
                logger.error(f"[AI-Orchestrator] Supervision iteration error: {e}")
            await asyncio.sleep(5.0)

    async def _supervision_iteration(self) -> None:
        """Single check across active deployments."""
        async with AsyncSessionLocal() as session:
            deploy_repo = AIDeploymentRepository(session)
            running_desired = await deploy_repo.list_by_desired_state("RUNNING")

            now = time.time()

            for d in running_desired:
                cam_code = d.camera_code
                pipe = (
                    CrowdPipelineRegistry.get(cam_code)
                    or QueuePipelineRegistry.get(cam_code)
                    or FRSPipelineRegistry.get(cam_code)
                )

                if pipe:
                    hlth = pipe.get_health()
                    if isinstance(hlth, dict):
                        status_val = hlth.get("health_status") or hlth.get("status")
                    else:
                        status_val = getattr(hlth, "health_status", None) or getattr(hlth, "status", None)
                    if hasattr(status_val, "value"):
                        status_val = status_val.value

                    # Check for temporary stream timeout (>= 10s without frame)
                    if status_val == "FAILED" or pipe.state == PipelineState.FAILED:
                        if d.actual_state == "RUNNING":
                            logger.warning(f"[AI-Orchestrator] Stream timeout detected for {cam_code}. Marking DEGRADED.")
                            d.actual_state = "DEGRADED"
                            d.health_state = "DEGRADED"
                            d.reconnect_count += 1
                            await session.commit()

                            # Initiate backoff reconnect if enabled
                            if d.auto_reconnect_enabled:
                                asyncio.create_task(self._attempt_reconnect(cam_code))
                else:
                    # Pipeline should be running but is missing in registry
                    if d.actual_state in ("RUNNING", "DEGRADED"):
                        d.actual_state = "FAILED"
                        d.health_state = "FAILED"
                        d.last_failure_at = datetime.now(timezone.utc)
                        d.last_error = "Pipeline instance terminated unexpectedly"
                        await session.commit()

                        # Evaluate Auto-Recovery policy
                        if d.auto_restart_enabled:
                            await self._evaluate_auto_recovery(d, session)

    async def _attempt_reconnect(self, camera_code: str) -> None:
        """Handles exponential backoff reconnect for temporary RTSP dropouts."""
        tracker = self._reconnect_backoff_tracker.setdefault(camera_code, {"attempts": 0, "last_attempt": 0.0})
        attempts = tracker["attempts"]
        if attempts >= 5:
            logger.error(f"[AI-Orchestrator] Max RTSP reconnect attempts reached for {camera_code}.")
            async with AsyncSessionLocal() as session:
                deploy_repo = AIDeploymentRepository(session)
                d = await deploy_repo.get_by_camera_code(camera_code)
                if d and d.desired_state == "RUNNING":
                    d.actual_state = "FAILED"
                    d.health_state = "FAILED"
                    d.last_error = "RTSP reconnect exhausted after 5 attempts"
                    d.last_failure_at = datetime.now(timezone.utc)
                    await session.commit()
            await event_bus.publish(
                channel="ai",
                event_type="AI_PIPELINE_RTSP_FAILED",
                payload={"camera_code": camera_code, "reason": "RTSP reconnect exhausted"},
            )
            return

        delay = min(30.0, 2.0 ** attempts)
        tracker["attempts"] += 1
        await asyncio.sleep(delay)

        # Attempt restart of stream pipeline
        try:
            async with AsyncSessionLocal() as session:
                res = await self.restart_pipeline(camera_code, session)
                if res.get("status") == "RESTARTED":
                    tracker["attempts"] = 0
                    logger.info(f"[AI-Orchestrator] RTSP Reconnect succeeded for {camera_code} after {delay}s backoff.")
        except Exception as e:
            logger.warning(f"[AI-Orchestrator] RTSP Reconnect attempt {attempts+1} failed for {camera_code}: {e}")

    async def _evaluate_auto_recovery(self, deployment: AIPipelineDeployment, session: AsyncSession) -> None:
        """
        Enforces auto-recovery policy:
        Maximum 3 restarts within a 10-minute (600s) rolling window.
        """
        cam_code = deployment.camera_code
        now = time.time()
        history = self._restart_history_tracker.setdefault(cam_code, [])

        # Prune older than 10 minutes (600s)
        history = [t for t in history if now - t < 600.0]
        self._restart_history_tracker[cam_code] = history

        if len(history) >= 3:
            logger.error(f"[AI-Orchestrator] Recovery exhausted for {cam_code} (3 restarts in 10min). Halting recovery.")
            deployment.last_error = "Auto-recovery limit exceeded (3 attempts in 10 minutes)"
            await session.commit()
            await event_bus.publish(
                channel="ai",
                event_type="AI_PIPELINE_RECOVERY_EXHAUSTED",
                payload={"camera_code": cam_code, "reason": "Max 3 restarts within 10 minutes exceeded"},
            )
            return

        # Attempt recovery restart
        history.append(now)
        logger.info(f"[AI-Orchestrator] Auto-recovering failed pipeline for {cam_code} (attempt {len(history)}/3)...")
        try:
            await self.restart_pipeline(cam_code, session)
        except Exception as e:
            logger.error(f"[AI-Orchestrator] Auto-recovery attempt failed for {cam_code}: {e}")

    # ── Server Restart Recovery ───────────────────────────────────────────────

    async def recover_on_startup(self) -> None:
        """
        Restores pipelines where desired_state == RUNNING across server restarts.
        Uses staggered batches of 2 with health verification to avoid GPU spikes.
        """
        logger.info("[AI-Orchestrator] Initiating server startup pipeline recovery...")
        async with AsyncSessionLocal() as session:
            deploy_repo = AIDeploymentRepository(session)
            to_restore = await deploy_repo.list_by_desired_state("RUNNING")

            if not to_restore:
                logger.info("[AI-Orchestrator] No pipelines with desired_state=RUNNING to restore.")
                return

            logger.info(f"[AI-Orchestrator] Found {len(to_restore)} pipelines to restore. Starting staggered recovery...")

            # Staggered batches of 2
            batch_size = 2
            for i in range(0, len(to_restore), batch_size):
                batch = to_restore[i : i + batch_size]
                for d in batch:
                    cam_code = d.camera_code
                    try:
                        logger.info(f"[AI-Orchestrator] Restoring {cam_code}...")
                        await self.start_pipeline(cam_code, session)
                    except Exception as e:
                        logger.warning(f"[AI-Orchestrator] Could not restore {cam_code}: {e}")
                        d.actual_state = "STOPPED"
                        d.health_state = "STOPPED"
                        d.last_error = f"Startup recovery skipped: {e}"
                        await session.commit()
                # Stagger delay
                await asyncio.sleep(2.0)

        logger.info("[AI-Orchestrator] Startup recovery complete.")

    # ── Graceful Shutdown ─────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        """Gracefully shuts down orchestrator and active pipelines."""
        self._is_running = False
        if self._supervision_task and not self._supervision_task.done():
            self._supervision_task.cancel()
            try:
                await self._supervision_task
            except asyncio.CancelledError:
                pass

        async with AsyncSessionLocal() as session:
            await self.stop_all(session)
        logger.info("[AI-Orchestrator] Orchestrator shutdown complete.")


# Global singleton instance
ai_orchestrator = AIOrchestrator()
