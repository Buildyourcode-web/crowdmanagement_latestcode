"""
crowd_pipeline_service.py — Crowd Pipeline Service & Lifecycle Manager.

Orchestrates:
- Pre-flight capacity validation using CapacityCalculator before pipeline launch.
- Spatial geometry verification (CROWD_ROI readiness check).
- Safe credential resolution without logging secrets.
- Runtime DeepStream / GPU capability verification.
- Real-time and historical metric resolution.
- Audit logging of pipeline lifecycle operations.
"""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional
import uuid
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.capacity.calculator import CapacityCalculator
from app.ai.orchestrator.state import PipelineState
from app.ai.pipelines.crowd.config import CrowdPipelineConfig
from app.ai.pipelines.crowd.detector import BasePersonDetector, DeepStreamPersonDetector
from app.ai.pipelines.crowd.pipeline import CrowdPipeline
from app.ai.pipelines.crowd.registry import CrowdPipelineRegistry
from app.ai.profiles.service import AIProfile, STANDARD_PROFILES
from app.ai.runtime.detector import RuntimeDetector
from app.models.audit_log import AuditLog
from app.models.camera import Camera
from app.models.camera_ai_assignment import CameraAIProfileAssignment
from app.models.camera_roi import CameraROIConfiguration, ROIType
from app.models.crowd import CrowdSnapshot
from app.models.user import User
from app.redis.event_bus import event_bus
from app.repositories.camera_ai_repository import CameraAIRepository
from app.repositories.camera_repository import CameraRepository
from app.repositories.camera_roi_repository import CameraROIRepository
from app.repositories.crowd_repository import CrowdRepository
from app.repositories.zone_repository import ZoneRepository


class CrowdPipelineService:
    """Business logic for Crowd AI pipeline management and analytics."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.camera_repo = CameraRepository(db)
        self.ai_repo = CameraAIRepository(db)
        self.roi_repo = CameraROIRepository(db)
        self.crowd_repo = CrowdRepository(db)
        self.zone_repo = ZoneRepository(db)

    async def _resolve_camera(self, camera_id_or_code: str) -> Camera:
        """Resolves camera by UUID or camera_code."""
        try:
            cam_uuid = uuid.UUID(camera_id_or_code)
            cam = await self.camera_repo.get_by_id(cam_uuid)
            if cam:
                return cam
        except ValueError:
            pass

        cam = await self.camera_repo.get_by_code(camera_id_or_code.strip().upper())
        if cam:
            return cam

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CAMERA_NOT_FOUND", "message": f"Camera '{camera_id_or_code}' not found"},
        )

    async def start_crowd_pipeline(
        self,
        camera_id_or_code: str,
        current_user: User,
        client_ip: Optional[str] = None,
        custom_detector: Optional[BasePersonDetector] = None,
    ) -> Dict[str, Any]:
        """
        Validates deployment requirements and launches a Crowd AI pipeline.
        Enforces server capacity, ROI readiness, and runtime checks.
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

        # 2. Check Assigned Crowd Profile
        assignments = await self.ai_repo.get_assignments_for_camera(camera.id)
        crowd_assignment = next(
            (a for a in assignments if a.enabled and ("CROWD" in a.profile_id.upper())),
            None,
        )
        if not crowd_assignment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "NO_CROWD_PROFILE_ASSIGNED",
                    "message": f"Camera {camera.camera_code} has no active CROWD AI profile assigned.",
                },
            )

        profile_id = crowd_assignment.profile_id
        profile: AIProfile = STANDARD_PROFILES.get(profile_id, STANDARD_PROFILES["CROWD_STANDARD"])

        # 3. Check Crowd ROI Readiness (Step 5 requirement)
        roi_configs = await self.roi_repo.get_by_camera_id(camera.id, profile_id=profile_id)
        has_crowd_roi = any(
            r.enabled and r.roi_type == ROIType.CROWD_ROI and len((r.geometry_json or {}).get("points", [])) >= 3
            for r in roi_configs
        )
        if not has_crowd_roi:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "ROI_NOT_CONFIGURED",
                    "message": f"Camera {camera.camera_code} does not have a configured CROWD_ROI polygon. Configure spatial boundaries before starting pipeline.",
                },
            )

        # 4. Pre-Flight Server Capacity Validation (Step 2 capacity check)
        all_active_assignments = await self.ai_repo.get_all_active_assignments()
        active_workload = {"gpu_vram_gb": 0.0, "gpu_load_percent": 0.0, "cpu_percent": 0.0, "ram_mb": 0.0}
        for asgn in all_active_assignments:
            p = STANDARD_PROFILES.get(asgn.profile_id)
            if p and p.workload:
                active_workload["gpu_vram_gb"] += p.workload.estimated_vram_gb
                active_workload["gpu_load_percent"] += p.workload.estimated_gpu_load_percent
                active_workload["cpu_percent"] += p.workload.estimated_cpu_percent
                active_workload["ram_mb"] += p.workload.estimated_ram_mb

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

        # 5. Pre-Flight Server Capacity Validation (Step 2 capacity check)
        all_active_assignments = await self.ai_repo.get_all_active_assignments()
        current_workload: Dict[str, int] = {}
        for asgn in all_active_assignments:
            if asgn.enabled:
                current_workload[asgn.profile_id] = current_workload.get(asgn.profile_id, 0) + 1

        # If pipeline already running, don't double count
        existing = CrowdPipelineRegistry.get(camera.camera_code)
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
            # Log audit rejection
            audit = AuditLog(
                user_id=current_user.id,
                username=current_user.username,
                action="CROWD_PIPELINE_START_BLOCKED",
                resource_type="crowd_pipeline",
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
        pipe_config = CrowdPipelineConfig.from_camera_and_geometries(
            camera=camera,
            profile_id=profile_id,
            roi_configs=roi_configs,
        )

        # 7. Instantiate & Start Pipeline
        pipeline = CrowdPipeline(config=pipe_config, detector=custom_detector)
        await pipeline.start()
        CrowdPipelineRegistry.register(pipeline)

        # 8. Audit Log
        audit = AuditLog(
            user_id=current_user.id,
            username=current_user.username,
            action="CROWD_PIPELINE_STARTED",
            resource_type="crowd_pipeline",
            resource_id=camera.camera_code,
            ip_address=client_ip,
            metadata_json={
                "camera_code": camera.camera_code,
                "profile_id": profile_id,
                "roi_name": pipe_config.crowd_roi_name,
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
            payload={"camera_code": camera.camera_code, "profile_id": profile_id, "pipeline_type": "CROWD"},
        )

        return {
            "status": "STARTED",
            "camera_code": camera.camera_code,
            "profile_id": profile_id,
            "pipeline_id": f"PIPE-{camera.camera_code}-{profile_id}",
            "model_name": pipe_config.model.name,
            "roi_name": pipe_config.crowd_roi_name,
            "processing_fps": pipe_config.processing_fps,
        }

    async def stop_crowd_pipeline(
        self,
        camera_id_or_code: str,
        current_user: User,
        client_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stops an active crowd pipeline and unregisters it."""
        camera = await self._resolve_camera(camera_id_or_code)
        pipeline = CrowdPipelineRegistry.get(camera.camera_code)

        if not pipeline:
            return {"status": "NOT_RUNNING", "camera_code": camera.camera_code}

        await CrowdPipelineRegistry.stop_pipeline(camera.camera_code)

        # Audit Log
        audit = AuditLog(
            user_id=current_user.id,
            username=current_user.username,
            action="CROWD_PIPELINE_STOPPED",
            resource_type="crowd_pipeline",
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
            payload={"camera_code": camera.camera_code, "pipeline_type": "CROWD"},
        )

        return {"status": "STOPPED", "camera_code": camera.camera_code}

    async def get_camera_crowd_metrics(self, camera_id_or_code: str) -> Dict[str, Any]:
        """
        Retrieves live crowd metrics if pipeline is running,
        or the latest stored snapshot if idle.
        """
        camera = await self._resolve_camera(camera_id_or_code)
        pipeline = CrowdPipelineRegistry.get(camera.camera_code)

        if pipeline and pipeline.state == PipelineState.RUNNING:
            return pipeline.get_metrics()

        # Check latest persisted snapshot
        snapshot = await self.crowd_repo.get_latest_for_camera(camera.camera_code)
        if snapshot:
            return {
                "camera_id": str(camera.id),
                "camera_code": camera.camera_code,
                "camera_name": camera.name,
                "zone_id": str(camera.zone_id) if camera.zone_id else None,
                "zone_code": camera.zone_code,
                "profile_id": snapshot.profile_id or "CROWD_STANDARD",
                "timestamp": snapshot.timestamp.timestamp(),
                "timestamp_iso": snapshot.timestamp.isoformat(),
                "status": "STOPPED",
                "health": "INACTIVE",
                "count": snapshot.people_count,
                "density": snapshot.density,
                "density_type": "HISTORICAL",
                "density_unit": "RELATIVE_DENSITY",
                "density_level": snapshot.risk_level,
                "inflow": snapshot.inflow_rate,
                "outflow": snapshot.outflow_rate,
                "flow_delta": (snapshot.inflow_rate - snapshot.outflow_rate) if snapshot.inflow_rate else None,
                "risk_score": snapshot.risk_score or 0.0,
                "risk_level": snapshot.risk_level,
                "risk_factors": [],
                "events_fired": [],
                "fps": 0.0,
            }

        return {
            "camera_id": str(camera.id),
            "camera_code": camera.camera_code,
            "camera_name": camera.name,
            "zone_id": str(camera.zone_id) if camera.zone_id else None,
            "zone_code": camera.zone_code,
            "profile_id": "CROWD_STANDARD",
            "timestamp": time.time(),
            "timestamp_iso": datetime.now(timezone.utc).isoformat(),
            "status": "STOPPED",
            "health": "INACTIVE",
            "count": 0,
            "density": 0.0,
            "density_type": "RELATIVE_DENSITY",
            "density_unit": "RELATIVE_DENSITY",
            "density_level": "LOW",
            "inflow": None,
            "outflow": None,
            "flow_delta": None,
            "risk_score": 0.0,
            "risk_level": "LOW",
            "risk_factors": [],
            "events_fired": [],
            "fps": 0.0,
        }

    async def get_zone_crowd_metrics(self, zone_id_or_code: str) -> Dict[str, Any]:
        """Aggregates crowd metrics across all cameras assigned to a zone."""
        # 1. Try real-time registry aggregation
        live_agg = CrowdPipelineRegistry.get_zone_aggregated_metrics(zone_id_or_code)
        if live_agg.get("active_cameras", 0) > 0:
            return live_agg

        # 2. Fallback to latest DB snapshots for the zone
        snapshots = await self.crowd_repo.get_latest_for_zone(zone_id_or_code)
        total_count = sum(s.people_count for s in snapshots)
        densities = [s.density for s in snapshots]
        avg_density = round(sum(densities) / len(densities), 2) if densities else 0.0
        inflows = sum(s.inflow_rate for s in snapshots)
        outflows = sum(s.outflow_rate for s in snapshots)
        risk_levels = [s.risk_level for s in snapshots]
        highest_risk = "CRITICAL" if "CRITICAL" in risk_levels else ("HIGH" if "HIGH" in risk_levels else ("MEDIUM" if "MEDIUM" in risk_levels else "LOW"))

        return {
            "zone_id": zone_id_or_code,
            "active_cameras": 0,
            "camera_codes": [s.camera_code for s in snapshots if s.camera_code],
            "total_count": total_count,
            "average_density": avg_density,
            "total_inflow": inflows if inflows > 0 else None,
            "total_outflow": outflows if outflows > 0 else None,
            "max_risk_score": max((s.risk_score or 0.0) for s in snapshots) if snapshots else 0.0,
            "risk_level": highest_risk,
        }

    async def get_crowd_status(self) -> Dict[str, Any]:
        """Precinct-wide crowd monitoring summary."""
        active_pipelines = CrowdPipelineRegistry.list_pipelines()
        all_metrics = [p.get_metrics() for p in active_pipelines]

        total_active_crowd = sum(m.get("count", 0) for m in all_metrics)
        critical_cameras = [m["camera_code"] for m in all_metrics if m.get("risk_level") in ("HIGH", "CRITICAL")]

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "active_pipelines_count": len(active_pipelines),
            "running_cameras": [p.camera_code for p in active_pipelines if p.state == PipelineState.RUNNING],
            "total_tracked_crowd": total_active_crowd,
            "critical_cameras_count": len(critical_cameras),
            "critical_camera_codes": critical_cameras,
            "runtime_environment": {
                "deepstream_available": RuntimeDetector.detect_runtime().get("deepstream", False),
                "gpu_available": RuntimeDetector.detect_gpu().get("available", False),
            },
        }

    async def get_crowd_health(self) -> Dict[str, Any]:
        """Health telemetry across all crowd pipelines."""
        active_pipelines = CrowdPipelineRegistry.list_pipelines()
        health_reports = [p.get_health().model_dump() for p in active_pipelines]

        healthy_cnt = sum(1 for h in health_reports if h["health_status"] == "HEALTHY")
        degraded_cnt = sum(1 for h in health_reports if h["health_status"] == "DEGRADED")
        failed_cnt = sum(1 for h in health_reports if h["health_status"] == "FAILED")

        overall_status = "HEALTHY"
        if failed_cnt > 0:
            overall_status = "FAILED"
        elif degraded_cnt > 0:
            overall_status = "DEGRADED"
        elif not active_pipelines:
            overall_status = "INACTIVE"

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": overall_status,
            "total_pipelines": len(active_pipelines),
            "healthy_count": healthy_cnt,
            "degraded_count": degraded_cnt,
            "failed_count": failed_cnt,
            "pipelines": health_reports,
        }
