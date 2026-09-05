"""
ai.py — AI Orchestration, Runtime Inspection & Dynamic Capacity API Router.

Endpoints:
- GET  /api/v1/ai/system/capabilities     (Full hardware, accelerator & stack detection)
- GET  /api/v1/ai/system/capacity         (Dynamic single-profile & mixed workload capacity)
- POST /api/v1/ai/system/capacity/validate(Pre-flight validation for new camera workloads)
- POST /api/v1/ai/system/capacity/snapshots (Persist a point-in-time capacity snapshot)
- GET  /api/v1/ai/system/capacity/snapshots (List recent capacity snapshots)
- PUT  /api/v1/ai/system/capacity/config  (Update safety headroom thresholds with audit log)
- GET  /api/v1/ai/profiles                (List registered standard AI profiles)
- GET  /api/v1/ai/deployments             (List active deployments)
- GET  /api/v1/ai/pipelines               (List active pipeline instances)
- GET  /api/v1/ai/health                  (Consolidated runtime health)

Guarded with existing JWT/RBAC:
- AI_READ: viewing capabilities, capacity, profiles, health
- AI_MANAGE: updating capacity safety headroom, managing deployments
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.models.audit_log import AuditLog
from app.models.ai_capacity import AICapacitySnapshot
from app.security.permissions import Permissions
from app.schemas.common import StandardResponse
from app.utils.response import success_response
from app.ai.runtime.detector import RuntimeDetector
from app.ai.runtime.health import RuntimeHealthChecker
from app.ai.capacity.calculator import (
    CapacityCalculator,
    CapacitySafetyConfig,
    safety_config,
    ProfileCapacityItem,
    MixedWorkloadCapacity,
    DeploymentValidationResult,
)
from app.ai.profiles.service import AIProfile, AIProfileService
from app.ai.deployments.service import AIDeployment, DeploymentService
from app.ai.pipelines.manager import PipelineInstance, PipelineManager
from app.ai.orchestrator.service import ai_orchestrator
from app.api.v1.orchestrator import router as orchestrator_router

router = APIRouter(prefix="/ai", tags=["AI Orchestration & Infrastructure"])
router.include_router(orchestrator_router)


# ── Request / Response Schemas ───────────────────────────────────────────────

class ValidateDeploymentRequest(BaseModel):
    current_workload: Dict[str, int] = Field(
        default_factory=dict,
        example={"CROWD_STANDARD": 5, "QUEUE_STANDARD": 2},
    )
    requested_addition: Dict[str, int] = Field(
        ...,
        example={"FRS_STANDARD": 1, "CROWD_STANDARD": 2},
    )


class UpdateCapacityConfigRequest(BaseModel):
    system_reserved_cpu_percent: Optional[float] = Field(None, ge=5.0, le=40.0)
    system_reserved_ram_gb: Optional[float] = Field(None, ge=1.0, le=16.0)
    system_reserved_vram_gb: Optional[float] = Field(None, ge=0.2, le=4.0)
    safe_headroom_cpu_percent: Optional[float] = Field(None, ge=5.0, le=30.0)
    safe_headroom_ram_percent: Optional[float] = Field(None, ge=5.0, le=30.0)
    safe_headroom_gpu_percent: Optional[float] = Field(None, ge=5.0, le=30.0)
    safe_headroom_vram_percent: Optional[float] = Field(None, ge=5.0, le=30.0)
    hard_max_gpu_percent: Optional[float] = Field(None, ge=70.0, le=98.0)
    hard_max_vram_percent: Optional[float] = Field(None, ge=70.0, le=98.0)
    hard_max_cpu_percent: Optional[float] = Field(None, ge=60.0, le=95.0)
    hard_max_ram_percent: Optional[float] = Field(None, ge=70.0, le=98.0)


# ── 1. System Capabilities ───────────────────────────────────────────────────

@router.get("/system/capabilities", response_model=StandardResponse[Dict[str, Any]])
async def get_system_capabilities(
    current_user: User = Depends(require_permission(Permissions.AI_READ)),
):
    """
    Inspects and returns server hardware, CPU, RAM, GPU, storage,
    accelerators, AI runtime stacks, and database/redis readiness.
    """
    capabilities = await RuntimeDetector.get_full_capabilities()
    return success_response(capabilities)


# ── 2. Dynamic Capacity Engine ───────────────────────────────────────────────

@router.get("/system/capacity", response_model=StandardResponse[Dict[str, Any]])
async def get_system_capacity(
    crowd_standard: int = Query(0, ge=0, description="Hypothetical active Crowd Standard cameras"),
    crowd_high_density: int = Query(0, ge=0, description="Hypothetical active High Density cameras"),
    queue_standard: int = Query(0, ge=0, description="Hypothetical active Queue cameras"),
    frs_standard: int = Query(0, ge=0, description="Hypothetical active FRS cameras"),
    video_safety: int = Query(0, ge=0, description="Hypothetical active Safety cameras"),
    current_user: User = Depends(require_permission(Permissions.AI_READ)),
):
    """
    Returns dynamically computed AI workload capacity for each standard profile,
    along with mixed workload projection for the requested camera distribution.
    """
    cpu = RuntimeDetector.detect_cpu()
    ram = RuntimeDetector.detect_ram()
    gpu = RuntimeDetector.detect_gpu()
    runtime = RuntimeDetector.detect_runtime()
    db = await RuntimeDetector.check_database_readiness()
    redis = await RuntimeDetector.check_redis_readiness()
    readiness = RuntimeDetector.evaluate_readiness(gpu, runtime, db, redis)

    # Calculate per-profile capacities
    profile_capacities = CapacityCalculator.calculate_all_profiles(cpu, ram, gpu, safety_config)

    # Calculate mixed workload if requested
    mix_dict = {
        "CROWD_STANDARD": crowd_standard,
        "CROWD_HIGH_DENSITY": crowd_high_density,
        "QUEUE_STANDARD": queue_standard,
        "FRS_STANDARD": frs_standard,
        "VIDEO_SAFETY": video_safety,
    }
    has_mixed_request = any(v > 0 for v in mix_dict.values())
    mixed_result = None

    if has_mixed_request:
        mixed_result = CapacityCalculator.calculate_mixed_workload_capacity(
            mix_dict,
            cpu,
            ram,
            gpu,
            runtime_readiness=readiness["readiness"],
            cfg=safety_config,
        )

    response_payload = {
        "calculation_mode": "ESTIMATED",
        "note": "Capacity values are dynamically estimated based on model complexity and detected resources.",
        "server_resources": {
            "cpu_cores": cpu.get("logical_cores"),
            "cpu_usage_percent": cpu.get("usage_percent"),
            "ram_total_gb": ram.get("total_gb"),
            "ram_available_gb": ram.get("available_gb"),
            "gpu_available": gpu.get("available"),
            "gpu_count": gpu.get("count"),
            "devices": gpu.get("devices", []),
        },
        "safety_headroom_config": safety_config.model_dump(),
        "profiles": {k: v.model_dump() for k, v in profile_capacities.items()},
        "mixed_workload": mixed_result.model_dump() if mixed_result else None,
        "runtime_readiness": readiness,
    }

    return success_response(response_payload)


# ── 3. Pre-Flight Deployment Validation ──────────────────────────────────────

@router.post("/system/capacity/validate", response_model=StandardResponse[DeploymentValidationResult])
async def validate_deployment(
    request: ValidateDeploymentRequest,
    current_user: User = Depends(require_permission(Permissions.AI_READ)),
):
    """
    Pre-flight capacity validator.
    Evaluates whether adding requested cameras to current workload will cause resource exhaustion.
    """
    cpu = RuntimeDetector.detect_cpu()
    ram = RuntimeDetector.detect_ram()
    gpu = RuntimeDetector.detect_gpu()

    result = CapacityCalculator.validate_capacity_for_deployment(
        current_workload=request.current_workload,
        requested_addition=request.requested_addition,
        cpu_info=cpu,
        ram_info=ram,
        gpu_info=gpu,
        cfg=safety_config,
    )
    return success_response(result)


# ── 4. Capacity Snapshots ───────────────────────────────────────────────────

@router.post("/system/capacity/snapshots", response_model=StandardResponse[Dict[str, Any]])
async def create_capacity_snapshot(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_READ)),
):
    """
    Captures a point-in-time snapshot of server hardware capabilities,
    runtime readiness, and profile capacities into the database.
    """
    caps = await RuntimeDetector.get_full_capabilities()
    cpu = caps["cpu"]
    ram = caps["memory"]
    gpu = caps["gpu"]
    readiness = caps["readiness"]

    profile_caps = CapacityCalculator.calculate_all_profiles(cpu, ram, gpu, safety_config)
    serialized_caps = {k: v.model_dump() for k, v in profile_caps.items()}

    snapshot = AICapacitySnapshot(
        server_hostname=caps["server"]["hostname"],
        timestamp=datetime.now(timezone.utc),
        cpu_info=cpu,
        ram_info=ram,
        gpu_info=gpu,
        runtime_readiness=readiness["readiness"],
        readiness_details=readiness,
        capacity_snapshot=serialized_caps,
        calculation_mode="ESTIMATED",
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)

    return success_response({
        "snapshot_id": str(snapshot.id),
        "server_hostname": snapshot.server_hostname,
        "timestamp": snapshot.timestamp.isoformat(),
        "runtime_readiness": snapshot.runtime_readiness,
        "calculation_mode": snapshot.calculation_mode,
    })


@router.get("/system/capacity/snapshots", response_model=StandardResponse[List[Dict[str, Any]]])
async def list_capacity_snapshots(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_READ)),
):
    """Lists historical capacity snapshots."""
    stmt = select(AICapacitySnapshot).order_by(desc(AICapacitySnapshot.timestamp)).limit(limit)
    result = await db.execute(stmt)
    snapshots = result.scalars().all()

    items = [
        {
            "id": str(s.id),
            "server_hostname": s.server_hostname,
            "timestamp": s.timestamp.isoformat(),
            "runtime_readiness": s.runtime_readiness,
            "calculation_mode": s.calculation_mode,
            "capacity_summary": {
                k: {
                    "recommended": v.get("capacity", {}).get("recommended_cameras", 0),
                    "maximum": v.get("capacity", {}).get("maximum_cameras", 0),
                }
                for k, v in s.capacity_snapshot.items()
            },
        }
        for s in snapshots
    ]
    return success_response(items)


# ── 5. Capacity Config & Audit Log ───────────────────────────────────────────

@router.put("/system/capacity/config", response_model=StandardResponse[Dict[str, Any]])
async def update_capacity_config(
    req: UpdateCapacityConfigRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_MANAGE)),
):
    """
    Updates safety headroom and system reserved thresholds.
    Requires AI_MANAGE permission and records an audit log entry.
    """
    old_values = safety_config.model_dump()
    updates = req.model_dump(exclude_unset=True)

    for field, val in updates.items():
        if val is not None and hasattr(safety_config, field):
            setattr(safety_config, field, val)

    new_values = safety_config.model_dump()

    # Record Audit Log
    client_ip = request.client.host if request.client else None
    audit = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="UPDATE_CAPACITY_CONFIG",
        resource_type="AI_CAPACITY_CONFIG",
        resource_id="GLOBAL",
        ip_address=client_ip,
        metadata_json={
            "old_config": old_values,
            "new_config": new_values,
            "updated_fields": list(updates.keys()),
        },
    )
    db.add(audit)
    await db.commit()

    return success_response({
        "message": "AI capacity safety configuration updated successfully.",
        "config": new_values,
    })


# ── 6. Profiles, Deployments & Pipelines ─────────────────────────────────────

@router.get("/profiles", response_model=StandardResponse[List[AIProfile]])
async def list_ai_profiles(
    current_user: User = Depends(require_permission(Permissions.AI_READ)),
):
    """Lists registered standard AI workload profiles with estimated workload specs."""
    profiles = AIProfileService.list_profiles()
    return success_response(profiles)


@router.get("/deployments", response_model=StandardResponse[List[AIDeployment]])
async def list_ai_deployments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_READ)),
):
    """Lists active camera AI pipeline deployments."""
    deployments = await ai_orchestrator.list_deployments(db)
    return success_response(deployments)


@router.get("/pipelines", response_model=StandardResponse[List[PipelineInstance]])
async def list_ai_pipelines(
    current_user: User = Depends(require_permission(Permissions.AI_READ)),
):
    """Lists active AI inference pipeline instances."""
    pipelines = PipelineManager.list_pipeline_instances()
    return success_response(pipelines)


@router.get("/health", response_model=StandardResponse[Dict[str, Any]])
async def get_ai_runtime_health(
    current_user: User = Depends(require_permission(Permissions.AI_READ)),
):
    """Telemetry and health status across PostgreSQL, Redis, and compute resources."""
    health = await RuntimeHealthChecker.get_runtime_health()
    return success_response(health)
