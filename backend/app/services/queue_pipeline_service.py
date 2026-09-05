"""
queue_pipeline_service.py — Queue AI Pipeline Orchestration Service.

Validates pre-flight camera stream status, assigned Queue profiles, spatial geometry readiness
(QUEUE_ROI, ENTRY_LINE, EXIT_LINE), hardware runtime capability, and server capacity limits.
Manages pipeline lifecycle, audit logging, Redis event bus publishing, and real-time metrics retrieval.
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.capacity.calculator import CapacityCalculator
from app.ai.pipelines.crowd.detector import BasePersonDetector
from app.ai.pipelines.crowd.pipeline import PipelineState
from app.ai.pipelines.queue.config import QueuePipelineConfig
from app.ai.pipelines.queue.pipeline import QueuePipeline
from app.ai.pipelines.queue.registry import QueuePipelineRegistry
from app.ai.profiles.service import AIProfile, STANDARD_PROFILES
from app.ai.runtime.detector import RuntimeDetector
from app.models.audit_log import AuditLog
from app.models.camera import Camera
from app.models.camera_roi import ROIType
from app.models.queue import QueueSnapshot
from app.models.user import User
from app.redis.event_bus import event_bus
from app.repositories.camera_ai_repository import CameraAIRepository
from app.repositories.camera_repository import CameraRepository
from app.repositories.camera_roi_repository import CameraROIRepository
from app.repositories.queue_repository import QueueRepository


class QueuePipelineService:
    """Service layer managing real-time Queue AI detection & analytics pipelines."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.camera_repo = CameraRepository(db)
        self.ai_repo = CameraAIRepository(db)
        self.roi_repo = CameraROIRepository(db)
        self.queue_repo = QueueRepository(db)

    async def _resolve_camera(self, camera_id_or_code: str) -> Camera:
        """Finds camera by UUID or camera_code."""
        camera = None
        try:
            cam_uuid = uuid.UUID(str(camera_id_or_code))
            camera = await self.camera_repo.get_by_id(cam_uuid)
        except (ValueError, TypeError, AttributeError):
            pass

        if not camera:
            camera = await self.camera_repo.get_by_code(str(camera_id_or_code))

        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "CAMERA_NOT_FOUND", "message": f"Camera '{camera_id_or_code}' not found."},
            )
        return camera

    async def start_queue_pipeline(
        self,
        camera_id_or_code: str,
        current_user: User,
        client_ip: Optional[str] = None,
        custom_detector: Optional[BasePersonDetector] = None,
    ) -> Dict[str, Any]:
        """
        Validates deployment requirements and launches a Queue AI pipeline.
        Enforces stream health, assigned profile, geometric readiness, runtime capability,
        and server capacity protection.
        """
        camera = await self._resolve_camera(camera_id_or_code)

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

        # 2. Check Assigned Queue Profile
        assignments = await self.ai_repo.get_assignments_for_camera(camera.id)
        queue_assignment = next(
            (a for a in assignments if a.enabled and ("QUEUE" in a.profile_id.upper())),
            None,
        )
        if not queue_assignment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "NO_QUEUE_PROFILE_ASSIGNED",
                    "message": f"Camera {camera.camera_code} has no active QUEUE AI profile assigned.",
                },
            )

        profile_id = queue_assignment.profile_id
        profile: AIProfile = STANDARD_PROFILES.get(profile_id, STANDARD_PROFILES["QUEUE_STANDARD"])

        # 3. Check Queue Spatial Geometry Readiness (Step 5 & Step 7 requirement)
        # Must require QUEUE_ROI, ENTRY_LINE, and EXIT_LINE
        roi_configs = await self.roi_repo.get_by_camera_id(camera.id, profile_id=profile_id)
        geoms = QueuePipelineConfig.check_geometry_requirements(roi_configs)
        if not geoms.is_ready:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "QUEUE_CONFIGURATION_NOT_READY",
                    "message": f"Queue AI requires QUEUE_ROI, ENTRY_LINE, and EXIT_LINE to be configured. Missing: {', '.join(geoms.missing_requirements)}.",
                    "missing_requirements": geoms.missing_requirements,
                },
            )

        # 4. Runtime Capability Verification (Host must support DeepStream & GPU)
        runtime_info = RuntimeDetector.detect_runtime()
        gpu_info = RuntimeDetector.detect_gpu()
        if not custom_detector and (not gpu_info.get("available") or not runtime_info.get("deepstream")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "RUNTIME_UNAVAILABLE",
                    "message": "NVIDIA DeepStream runtime unavailable on this host.",
                    "gpu_available": gpu_info.get("available", False),
                    "deepstream_available": runtime_info.get("deepstream", False),
                },
            )

        # 5. Pre-Flight Server Capacity Validation (Step 2 capacity check accounting for mixed workloads)
        all_active_assignments = await self.ai_repo.get_all_active_assignments()
        current_workload: Dict[str, int] = {}
        for asgn in all_active_assignments:
            if asgn.enabled:
                current_workload[asgn.profile_id] = current_workload.get(asgn.profile_id, 0) + 1

        # If pipeline already running, don't duplicate
        existing = QueuePipelineRegistry.get(camera.camera_code)
        if existing and existing.state == PipelineState.RUNNING:
            return {
                "status": "ALREADY_RUNNING",
                "camera_code": camera.camera_code,
                "profile_id": profile_id,
                "metrics": existing.get_metrics(),
            }

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
            # Audit log rejection
            audit = AuditLog(
                user_id=current_user.id,
                username=current_user.username,
                action="QUEUE_PIPELINE_START_BLOCKED",
                resource_type="queue_pipeline",
                resource_id=camera.camera_code,
                ip_address=client_ip,
                metadata_json={
                    "camera_code": camera.camera_code,
                    "profile_id": profile_id,
                    "reason": block_reason,
                    "status": "BLOCKED",
                },
            )
            self.db.add(audit)
            await self.db.commit()

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "AI_CAPACITY_EXCEEDED",
                    "message": f"Server capacity exceeded: {block_reason}",
                    "capacity_report": cap_validation if isinstance(cap_validation, dict) else cap_validation.model_dump(),
                },
            )

        # 6. Build Pipeline Configuration
        pipe_config = QueuePipelineConfig.from_camera_and_geometries(
            camera=camera,
            profile_id=profile_id,
            roi_configs=roi_configs,
        )

        # 7. Instantiate & Start Pipeline
        pipeline = QueuePipeline(config=pipe_config, detector=custom_detector)
        await pipeline.start()
        QueuePipelineRegistry.register(pipeline)

        # 8. Audit Log
        audit = AuditLog(
            user_id=current_user.id,
            username=current_user.username,
            action="QUEUE_PIPELINE_STARTED",
            resource_type="queue_pipeline",
            resource_id=camera.camera_code,
            ip_address=client_ip,
            metadata_json={
                "camera_code": camera.camera_code,
                "profile_id": profile_id,
                "queue_name": pipe_config.queue_roi_name,
                "model": pipe_config.model.name,
                "input_resolution": pipe_config.input_resolution,
                "status": "SUCCESS",
            },
        )
        self.db.add(audit)
        await self.db.commit()

        # 9. Broadcast Telemetry Event
        await event_bus.publish(
            channel="ai",
            event_type="PIPELINE_STARTED",
            payload={"camera_code": camera.camera_code, "profile_id": profile_id, "pipeline_type": "QUEUE"},
        )

        return {
            "status": "STARTED",
            "camera_code": camera.camera_code,
            "profile_id": profile_id,
            "pipeline_id": f"PIPE-{camera.camera_code}-{profile_id}",
            "model_name": pipe_config.model.name,
            "queue_name": pipe_config.queue_roi_name,
            "processing_fps": pipe_config.processing_fps,
        }

    async def stop_queue_pipeline(
        self,
        camera_id_or_code: str,
        current_user: User,
        client_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stops an active queue pipeline and releases resources."""
        camera = await self._resolve_camera(camera_id_or_code)
        pipeline = QueuePipelineRegistry.get(camera.camera_code)

        if not pipeline:
            return {"status": "NOT_RUNNING", "camera_code": camera.camera_code}

        await QueuePipelineRegistry.stop_pipeline(camera.camera_code)

        # Audit Log
        audit = AuditLog(
            user_id=current_user.id,
            username=current_user.username,
            action="QUEUE_PIPELINE_STOPPED",
            resource_type="queue_pipeline",
            resource_id=camera.camera_code,
            ip_address=client_ip,
            metadata_json={"camera_code": camera.camera_code, "status": "SUCCESS"},
        )
        self.db.add(audit)
        await self.db.commit()

        # Broadcast Event
        await event_bus.publish(
            channel="ai",
            event_type="PIPELINE_STOPPED",
            payload={"camera_code": camera.camera_code, "pipeline_type": "QUEUE"},
        )

        return {"status": "STOPPED", "camera_code": camera.camera_code}

    async def get_camera_queue_metrics(self, camera_id_or_code: str) -> Dict[str, Any]:
        """Retrieves live queue metrics if pipeline is running, or latest stored snapshot if idle."""
        camera = await self._resolve_camera(camera_id_or_code)
        pipeline = QueuePipelineRegistry.get(camera.camera_code)

        if pipeline and pipeline.state == PipelineState.RUNNING:
            return pipeline.get_metrics()

        # Check latest persisted snapshot
        snapshot = await self.queue_repo.get_latest_for_camera(camera.camera_code)
        if snapshot:
            return {
                "camera_id": str(camera.id),
                "camera_code": camera.camera_code,
                "camera_name": camera.name,
                "zone_id": str(camera.zone_id) if camera.zone_id else None,
                "zone_code": camera.zone_code,
                "profile_id": snapshot.profile_id or "QUEUE_STANDARD",
                "status": "STOPPED",
                "timestamp": snapshot.timestamp.timestamp(),
                "queue_count": snapshot.people_waiting,
                "total_tracked_in_frame": snapshot.people_waiting,
                "excluded_count": 0,
                "occupancy_percentage": snapshot.occupancy_percent,
                "occupancy_status": "NORMAL",
                "occupancy_note": None if snapshot.occupancy_percent is not None else "Queue capacity not configured.",
                "density": snapshot.density or 0.0,
                "density_type": snapshot.density_type or "RELATIVE",
                "density_unit": "persons/m²" if snapshot.density_type == "CALIBRATED" else "RELATIVE",
                "density_level": snapshot.risk_level or "LOW",
                "queue_length": {
                    "value": snapshot.queue_length_val or float(snapshot.queue_length),
                    "unit": snapshot.queue_length_unit or "normalized_extent",
                    "source": "CALIBRATED" if snapshot.queue_length_unit == "meters" else "RELATIVE",
                },
                "inflow": snapshot.inflow_rate,
                "outflow": snapshot.outflow_rate or 0,
                "flow_delta": snapshot.inflow_rate - (snapshot.outflow_rate or 0),
                "queue_direction": "UNKNOWN",
                "average_wait_seconds": snapshot.average_wait_seconds,
                "median_wait_seconds": snapshot.average_wait_seconds,
                "max_current_dwell_seconds": snapshot.max_dwell_seconds or 0,
                "completed_wait_samples": 0,
                "wait_status": "NORMAL" if snapshot.average_wait_seconds else "insufficient_data",
                "growth_per_minute": snapshot.growth_rate,
                "risk_score": snapshot.risk_score or 0.0,
                "risk_level": snapshot.risk_level or "LOW",
                "risk_factors": ["Persisted snapshot"],
                "active_queue_track_ids": [],
                "processing_fps": 0,
                "is_geometry_configured": True,
                "missing_requirements": [],
            }

        # Idle / Not Started
        return {
            "camera_id": str(camera.id),
            "camera_code": camera.camera_code,
            "camera_name": camera.name,
            "zone_id": str(camera.zone_id) if camera.zone_id else None,
            "zone_code": camera.zone_code,
            "profile_id": "QUEUE_STANDARD",
            "status": "STOPPED",
            "timestamp": time.time(),
            "queue_count": 0,
            "total_tracked_in_frame": 0,
            "excluded_count": 0,
            "occupancy_percentage": None,
            "occupancy_status": "NORMAL",
            "occupancy_note": "Queue pipeline not running.",
            "density": 0.0,
            "density_type": "RELATIVE",
            "density_unit": "RELATIVE",
            "density_level": "LOW",
            "queue_length": {"value": 0.0, "unit": "normalized_extent", "source": "RELATIVE"},
            "inflow": None,
            "outflow": None,
            "flow_delta": None,
            "queue_direction": "UNKNOWN",
            "average_wait_seconds": None,
            "median_wait_seconds": None,
            "max_current_dwell_seconds": None,
            "completed_wait_samples": 0,
            "wait_status": "insufficient_data",
            "growth_per_minute": None,
            "risk_score": 0.0,
            "risk_level": "LOW",
            "risk_factors": ["Pipeline stopped"],
            "active_queue_track_ids": [],
            "processing_fps": 0,
            "is_geometry_configured": False,
            "missing_requirements": [],
        }

    async def get_zone_queue_metrics(self, zone_id_or_code: str) -> Dict[str, Any]:
        """Returns aggregated queue metrics across all cameras in a zone."""
        return QueuePipelineRegistry.get_zone_summary(zone_id_or_code)

    async def get_all_queues_status(self) -> Dict[str, Any]:
        """Returns system-wide status of all queue monitoring pipelines."""
        active = QueuePipelineRegistry.list_all()
        running_count = sum(1 for p in active if p.state == PipelineState.RUNNING)
        failed_count = sum(1 for p in active if p.state == PipelineState.FAILED)

        total_people = sum(p.get_metrics().get("queue_count", 0) for p in active)
        critical_queues = [
            p.config.camera_code for p in active
            if p.get_metrics().get("risk_level") == "CRITICAL"
        ]

        return {
            "total_pipelines": len(active),
            "running_pipelines": running_count,
            "failed_pipelines": failed_count,
            "total_people_in_queues": total_people,
            "critical_queues": critical_queues,
            "pipelines": [
                {
                    "camera_code": p.config.camera_code,
                    "queue_name": p.config.queue_roi_name,
                    "state": p.state.value,
                    "metrics": p.get_metrics(),
                    "health": p.get_health(),
                }
                for p in active
            ],
        }

    async def get_pipeline_health(self, camera_id_or_code: Optional[str] = None) -> Any:
        """Returns health diagnostics for one or all queue pipelines."""
        if camera_id_or_code:
            camera = await self._resolve_camera(camera_id_or_code)
            pipeline = QueuePipelineRegistry.get(camera.camera_code)
            if not pipeline:
                return {
                    "camera_code": camera.camera_code,
                    "pipeline_state": "STOPPED",
                    "health_status": "STOPPED",
                    "message": "Pipeline is not active.",
                }
            return pipeline.get_health()

        # All pipelines
        return [
            {
                "camera_code": p.config.camera_code,
                "profile_id": p.config.profile_id,
                "pipeline_state": p.state.value,
                "health": p.get_health(),
            }
            for p in QueuePipelineRegistry.list_all()
        ]
