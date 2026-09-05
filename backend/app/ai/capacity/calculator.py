"""
calculator.py — Dynamic AI Capacity Engine.

Calculates safe concurrent camera stream capacity based on actual detected hardware:
AVAILABLE_RESOURCES - SYSTEM_RESERVED - SAFETY_HEADROOM = AI_AVAILABLE_BUDGET

Calculates independently for:
- CROWD_STANDARD
- CROWD_HIGH_DENSITY
- QUEUE_STANDARD
- FRS_STANDARD
- VIDEO_SAFETY

Supports mixed workloads (e.g. 10 Crowd + 5 Queue + 3 FRS) and provides:
- validate_capacity_for_deployment()
- Detailed resource budgeting (GPU %, VRAM GB, CPU %, RAM GB)
- Transparent status reporting (HEALTHY, WARNING, LIMIT_REACHED, OVER_CAPACITY, GPU_UNAVAILABLE, RUNTIME_NOT_READY)
- CPU-only server handling without synthetic numbers
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.ai.runtime.detector import RuntimeDetector
from app.ai.profiles.service import AIProfile, AIProfileService


# ── Configurable System Reservations & Safety Headroom Defaults ──────────────

class CapacitySafetyConfig(BaseModel):
    """
    Configurable safety thresholds to prevent resource exhaustion and OOM.
    Never assumes 100% of host resources can be consumed by AI inference.
    """
    # System baseline reserved for OS, DB, Redis, and Web API
    system_reserved_cpu_percent: float = 15.0
    system_reserved_ram_gb: float = 2.0
    system_reserved_vram_gb: float = 0.5  # 512 MB reserved for display/driver

    # Additional safety headroom for workload spikes
    safe_headroom_cpu_percent: float = 10.0
    safe_headroom_ram_percent: float = 10.0
    safe_headroom_gpu_percent: float = 15.0
    safe_headroom_vram_percent: float = 15.0

    # Hard ceiling limits beyond which deployments are strictly BLOCKED
    hard_max_gpu_percent: float = 90.0
    hard_max_vram_percent: float = 90.0
    hard_max_cpu_percent: float = 85.0
    hard_max_ram_percent: float = 90.0


# Global configurable instance
safety_config = CapacitySafetyConfig()


# ── Data Schemas ─────────────────────────────────────────────────────────────

class ResourceBudget(BaseModel):
    gpu_percent: float = 0.0
    vram_gb: float = 0.0
    cpu_percent: float = 0.0
    ram_gb: float = 0.0


class ProfileCapacity(BaseModel):
    recommended_cameras: int = 0
    maximum_cameras: int = 0
    remaining_cameras: int = 0
    limiting_resource: str = "NONE"


class ProfileCapacityItem(BaseModel):
    profile: str
    capacity: ProfileCapacity
    resource_budget: ResourceBudget
    status: str = "AVAILABLE"  # AVAILABLE, GPU_UNAVAILABLE, CPU_FALLBACK, RESOURCE_EXHAUSTED
    status_reason: Optional[str] = None
    calculation_mode: str = "ESTIMATED"


class MixedWorkloadItem(BaseModel):
    profile_id: str
    camera_count: int


class MixedWorkloadCapacity(BaseModel):
    status: str  # HEALTHY, WARNING, LIMIT_REACHED, OVER_CAPACITY, GPU_UNAVAILABLE, RUNTIME_NOT_READY
    status_summary: str
    requested_workload: Dict[str, int]
    current_usage: ResourceBudget
    projected_usage: ResourceBudget
    safe_budget: ResourceBudget
    hard_max_budget: ResourceBudget
    bottleneck_resource: Optional[str] = None
    recommendations: List[str] = Field(default_factory=list)
    calculation_mode: str = "ESTIMATED"


class DeploymentValidationResult(BaseModel):
    verdict: str  # ALLOWED, WARNING, BLOCKED
    status: str
    reason: str
    current_utilization: ResourceBudget
    projected_utilization: ResourceBudget
    exceeded_resources: List[str] = Field(default_factory=list)


# ── Capacity Calculator Engine ───────────────────────────────────────────────

class CapacityCalculator:
    """Dynamic capacity computation engine for server deployment planning."""

    @classmethod
    def _compute_available_budget(
        cls,
        cpu_info: Dict[str, Any],
        ram_info: Dict[str, Any],
        gpu_info: Dict[str, Any],
        cfg: Optional[CapacitySafetyConfig] = None,
    ) -> Dict[str, Any]:
        """
        Calculates:
        AVAILABLE_RESOURCES - SYSTEM_RESERVED - SAFETY_HEADROOM = AI_AVAILABLE_BUDGET
        Also returns hard maximum allowable budget.
        """
        config = cfg or safety_config

        # 1. CPU
        total_cpu = 100.0
        used_cpu = cpu_info.get("usage_percent", 0.0)
        safe_cpu_limit = max(0.0, total_cpu - config.system_reserved_cpu_percent - config.safe_headroom_cpu_percent)
        hard_cpu_limit = config.hard_max_cpu_percent
        ai_available_cpu = max(0.0, safe_cpu_limit - used_cpu)
        hard_available_cpu = max(0.0, hard_cpu_limit - used_cpu)

        # 2. RAM
        total_ram_gb = ram_info.get("total_gb", 8.0)
        avail_ram_gb = ram_info.get("available_gb", 4.0)
        safe_ram_headroom_gb = (total_ram_gb * config.safe_headroom_ram_percent) / 100.0
        safe_ram_limit_gb = max(0.0, total_ram_gb - config.system_reserved_ram_gb - safe_ram_headroom_gb)
        hard_ram_limit_gb = (total_ram_gb * config.hard_max_ram_percent) / 100.0
        ai_available_ram = max(0.0, avail_ram_gb - config.system_reserved_ram_gb - safe_ram_headroom_gb)
        hard_available_ram = max(0.0, avail_ram_gb - config.system_reserved_ram_gb)

        # 3. GPU / VRAM
        has_gpu = gpu_info.get("available", False)
        devices = gpu_info.get("devices", [])

        if has_gpu and devices:
            total_vram_gb = sum(d.get("total_vram_gb", 0.0) for d in devices)
            free_vram_gb = sum(d.get("free_vram_gb", 0.0) for d in devices)
            avg_gpu_util = sum(d.get("gpu_utilization_percent", 0) for d in devices) / len(devices)

            safe_vram_headroom_gb = (total_vram_gb * config.safe_headroom_vram_percent) / 100.0
            safe_vram_limit_gb = max(0.0, total_vram_gb - config.system_reserved_vram_gb - safe_vram_headroom_gb)
            hard_vram_limit_gb = (total_vram_gb * config.hard_max_vram_percent) / 100.0
            ai_available_vram = max(0.0, free_vram_gb - config.system_reserved_vram_gb - safe_vram_headroom_gb)
            hard_available_vram = max(0.0, free_vram_gb - config.system_reserved_vram_gb)

            safe_gpu_limit = max(0.0, 100.0 - config.safe_headroom_gpu_percent)
            hard_gpu_limit = config.hard_max_gpu_percent
            ai_available_gpu = max(0.0, safe_gpu_limit - avg_gpu_util)
            hard_available_gpu = max(0.0, hard_gpu_limit - avg_gpu_util)
        else:
            total_vram_gb = 0.0
            free_vram_gb = 0.0
            avg_gpu_util = 0.0
            ai_available_vram = 0.0
            hard_available_vram = 0.0
            ai_available_gpu = 0.0
            hard_available_gpu = 0.0
            safe_vram_limit_gb = 0.0
            hard_vram_limit_gb = 0.0
            safe_gpu_limit = 0.0
            hard_gpu_limit = 0.0

        return {
            "has_gpu": has_gpu,
            "current_usage": ResourceBudget(
                gpu_percent=round(avg_gpu_util, 1),
                vram_gb=round(total_vram_gb - free_vram_gb, 2),
                cpu_percent=round(used_cpu, 1),
                ram_gb=round(total_ram_gb - avail_ram_gb, 2),
            ),
            "ai_safe_available": ResourceBudget(
                gpu_percent=round(ai_available_gpu, 1),
                vram_gb=round(ai_available_vram, 2),
                cpu_percent=round(ai_available_cpu, 1),
                ram_gb=round(ai_available_ram, 2),
            ),
            "ai_hard_available": ResourceBudget(
                gpu_percent=round(hard_available_gpu, 1),
                vram_gb=round(hard_available_vram, 2),
                cpu_percent=round(hard_available_cpu, 1),
                ram_gb=round(hard_available_ram, 2),
            ),
            "safe_limits": ResourceBudget(
                gpu_percent=round(safe_gpu_limit, 1),
                vram_gb=round(safe_vram_limit_gb, 2),
                cpu_percent=round(safe_cpu_limit, 1),
                ram_gb=round(safe_ram_limit_gb, 2),
            ),
            "hard_max_limits": ResourceBudget(
                gpu_percent=round(hard_gpu_limit, 1),
                vram_gb=round(hard_vram_limit_gb, 2),
                cpu_percent=round(hard_cpu_limit, 1),
                ram_gb=round(hard_ram_limit_gb, 2),
            ),
        }

    @classmethod
    def calculate_single_profile_capacity(
        cls,
        profile_id: str,
        cpu_info: Dict[str, Any],
        ram_info: Dict[str, Any],
        gpu_info: Dict[str, Any],
        cfg: Optional[CapacitySafetyConfig] = None,
    ) -> ProfileCapacityItem:
        """
        Calculates recommended and maximum camera stream capacity for a single AI profile.
        """
        profile = AIProfileService.get_profile(profile_id)
        if not profile:
            return ProfileCapacityItem(
                profile=profile_id,
                capacity=ProfileCapacity(recommended_cameras=0, maximum_cameras=0, remaining_cameras=0),
                resource_budget=ResourceBudget(),
                status="RESOURCE_EXHAUSTED",
                status_reason=f"Unknown profile '{profile_id}'",
                calculation_mode="ESTIMATED",
            )

        budget = cls._compute_available_budget(cpu_info, ram_info, gpu_info, cfg)
        has_gpu = budget["has_gpu"]
        safe_avail: ResourceBudget = budget["ai_safe_available"]
        hard_avail: ResourceBudget = budget["ai_hard_available"]
        workload = profile.workload

        # CPU-Only Server handling
        if not has_gpu:
            if not workload.supports_cpu_execution:
                return ProfileCapacityItem(
                    profile=profile_id,
                    capacity=ProfileCapacity(
                        recommended_cameras=0,
                        maximum_cameras=0,
                        remaining_cameras=0,
                        limiting_resource="GPU_UNAVAILABLE",
                    ),
                    resource_budget=ResourceBudget(
                        gpu_percent=0.0,
                        vram_gb=0.0,
                        cpu_percent=workload.cpu_only_estimated_cpu_percent or 25.0,
                        ram_gb=round(workload.estimated_ram_mb / 1024.0, 2),
                    ),
                    status="GPU_UNAVAILABLE",
                    status_reason=(
                        f"Profile '{profile_id}' requires NVIDIA GPU acceleration with min "
                        f"{profile.gpu_requirements.min_vram_mb} MB VRAM. Server is CPU-only."
                    ),
                    calculation_mode="ESTIMATED",
                )

            # Profile supports CPU execution
            cpu_per_cam = workload.cpu_only_estimated_cpu_percent or 25.0
            ram_per_cam = workload.estimated_ram_mb / 1024.0

            rec_by_cpu = int(safe_avail.cpu_percent // cpu_per_cam) if cpu_per_cam > 0 else 0
            rec_by_ram = int(safe_avail.ram_gb // ram_per_cam) if ram_per_cam > 0 else 0
            rec_cams = max(0, min(rec_by_cpu, rec_by_ram))

            max_by_cpu = int(hard_avail.cpu_percent // cpu_per_cam) if cpu_per_cam > 0 else 0
            max_by_ram = int(hard_avail.ram_gb // ram_per_cam) if ram_per_cam > 0 else 0
            max_cams = max(0, min(max_by_cpu, max_by_ram))

            limiting = "CPU_LOAD" if rec_by_cpu <= rec_by_ram else "RAM_CAPACITY"

            return ProfileCapacityItem(
                profile=profile_id,
                capacity=ProfileCapacity(
                    recommended_cameras=rec_cams,
                    maximum_cameras=max_cams,
                    remaining_cameras=rec_cams,
                    limiting_resource=limiting,
                ),
                resource_budget=ResourceBudget(
                    gpu_percent=0.0,
                    vram_gb=0.0,
                    cpu_percent=cpu_per_cam,
                    ram_gb=round(ram_per_cam, 2),
                ),
                status="CPU_FALLBACK",
                status_reason="Running in CPU fallback mode with reduced frame processing concurrency.",
                calculation_mode="ESTIMATED",
            )

        # GPU Server calculation
        vram_per_cam = workload.estimated_vram_gb
        gpu_per_cam = workload.estimated_gpu_load_percent
        cpu_per_cam = workload.estimated_cpu_percent
        ram_per_cam = workload.estimated_ram_mb / 1024.0

        rec_by_vram = int(safe_avail.vram_gb // vram_per_cam) if vram_per_cam > 0 else 0
        rec_by_gpu = int(safe_avail.gpu_percent // gpu_per_cam) if gpu_per_cam > 0 else 0
        rec_by_cpu = int(safe_avail.cpu_percent // cpu_per_cam) if cpu_per_cam > 0 else 0
        rec_by_ram = int(safe_avail.ram_gb // ram_per_cam) if ram_per_cam > 0 else 0

        limits = {
            "VRAM": rec_by_vram,
            "GPU_CORE": rec_by_gpu,
            "CPU": rec_by_cpu,
            "RAM": rec_by_ram,
        }
        limiting_res = min(limits, key=limits.get)
        rec_cameras = max(0, limits[limiting_res])

        max_by_vram = int(hard_avail.vram_gb // vram_per_cam) if vram_per_cam > 0 else 0
        max_by_gpu = int(hard_avail.gpu_percent // gpu_per_cam) if gpu_per_cam > 0 else 0
        max_by_cpu = int(hard_avail.cpu_percent // cpu_per_cam) if cpu_per_cam > 0 else 0
        max_by_ram = int(hard_avail.ram_gb // ram_per_cam) if ram_per_cam > 0 else 0
        max_cameras = max(0, min(max_by_vram, max_by_gpu, max_by_cpu, max_by_ram))

        return ProfileCapacityItem(
            profile=profile_id,
            capacity=ProfileCapacity(
                recommended_cameras=rec_cameras,
                maximum_cameras=max_cameras,
                remaining_cameras=rec_cameras,
                limiting_resource=limiting_res,
            ),
            resource_budget=ResourceBudget(
                gpu_percent=gpu_per_cam,
                vram_gb=vram_per_cam,
                cpu_percent=cpu_per_cam,
                ram_gb=round(ram_per_cam, 2),
            ),
            status="AVAILABLE" if rec_cameras > 0 else "RESOURCE_EXHAUSTED",
            status_reason=None if rec_cameras > 0 else f"Resource '{limiting_res}' headroom exhausted.",
            calculation_mode="ESTIMATED",
        )

    @classmethod
    def calculate_all_profiles(
        cls,
        cpu_info: Dict[str, Any],
        ram_info: Dict[str, Any],
        gpu_info: Dict[str, Any],
        cfg: Optional[CapacitySafetyConfig] = None,
    ) -> Dict[str, ProfileCapacityItem]:
        """Calculates capacity for all 5 standard profiles."""
        profiles = ["CROWD_STANDARD", "CROWD_HIGH_DENSITY", "QUEUE_STANDARD", "FRS_STANDARD", "VIDEO_SAFETY"]
        results = {}
        for p in profiles:
            results[p] = cls.calculate_single_profile_capacity(p, cpu_info, ram_info, gpu_info, cfg)
        return results

    @classmethod
    def calculate_mixed_workload_capacity(
        cls,
        workload_mix: Dict[str, int],
        cpu_info: Dict[str, Any],
        ram_info: Dict[str, Any],
        gpu_info: Dict[str, Any],
        runtime_readiness: Optional[str] = None,
        cfg: Optional[CapacitySafetyConfig] = None,
    ) -> MixedWorkloadCapacity:
        """
        Calculates resource footprint for a mixed combination of cameras:
        e.g. {"CROWD_STANDARD": 10, "QUEUE_STANDARD": 5, "FRS_STANDARD": 3}
        """
        budget = cls._compute_available_budget(cpu_info, ram_info, gpu_info, cfg)
        has_gpu = budget["has_gpu"]
        current: ResourceBudget = budget["current_usage"]
        safe_limits: ResourceBudget = budget["safe_limits"]
        hard_max_limits: ResourceBudget = budget["hard_max_limits"]

        req_gpu_pct = 0.0
        req_vram_gb = 0.0
        req_cpu_pct = 0.0
        req_ram_gb = 0.0
        requires_gpu = False
        recommendations: List[str] = []

        for pid, count in workload_mix.items():
            if count <= 0:
                continue
            profile = AIProfileService.get_profile(pid)
            if not profile:
                continue

            w = profile.workload
            if not has_gpu:
                if not w.supports_cpu_execution:
                    requires_gpu = True
                cpu_est = (w.cpu_only_estimated_cpu_percent or 25.0) * count
                ram_est = (w.estimated_ram_mb / 1024.0) * count
                req_cpu_pct += cpu_est
                req_ram_gb += ram_est
            else:
                req_gpu_pct += w.estimated_gpu_load_percent * count
                req_vram_gb += w.estimated_vram_gb * count
                req_cpu_pct += w.estimated_cpu_percent * count
                req_ram_gb += (w.estimated_ram_mb / 1024.0) * count

        projected = ResourceBudget(
            gpu_percent=round(current.gpu_percent + req_gpu_pct, 1),
            vram_gb=round(current.vram_gb + req_vram_gb, 2),
            cpu_percent=round(current.cpu_percent + req_cpu_pct, 1),
            ram_gb=round(current.ram_gb + req_ram_gb, 2),
        )

        # Status Evaluation
        if requires_gpu and not has_gpu:
            return MixedWorkloadCapacity(
                status="GPU_UNAVAILABLE",
                status_summary="Requested workload includes GPU-dependent models (e.g. FRS/Sanctum AI) on a CPU-only server.",
                requested_workload=workload_mix,
                current_usage=current,
                projected_usage=projected,
                safe_budget=safe_limits,
                hard_max_budget=hard_max_limits,
                bottleneck_resource="GPU_UNAVAILABLE",
                recommendations=["Provision an NVIDIA GPU server or switch to CPU-supported profiles (Crowd Standard)."],
                calculation_mode="ESTIMATED",
            )

        if runtime_readiness == "AI_RUNTIME_NOT_READY":
            return MixedWorkloadCapacity(
                status="RUNTIME_NOT_READY",
                status_summary="Underlying database or essential runtime dependencies are unavailable.",
                requested_workload=workload_mix,
                current_usage=current,
                projected_usage=projected,
                safe_budget=safe_limits,
                hard_max_budget=hard_max_limits,
                bottleneck_resource="RUNTIME_DEPENDENCY",
                recommendations=["Restore core database service before deploying workloads."],
                calculation_mode="ESTIMATED",
            )

        # Evaluate against limits
        bottleneck = None
        over_hard = False
        over_safe = False

        if projected.gpu_percent > hard_max_limits.gpu_percent:
            bottleneck = "GPU_LOAD"
            over_hard = True
        elif projected.vram_gb > hard_max_limits.vram_gb:
            bottleneck = "VRAM"
            over_hard = True
        elif projected.cpu_percent > hard_max_limits.cpu_percent:
            bottleneck = "CPU_LOAD"
            over_hard = True
        elif projected.ram_gb > hard_max_limits.ram_gb:
            bottleneck = "RAM_CAPACITY"
            over_hard = True
        elif projected.gpu_percent > safe_limits.gpu_percent:
            bottleneck = "GPU_LOAD"
            over_safe = True
        elif projected.vram_gb > safe_limits.vram_gb:
            bottleneck = "VRAM"
            over_safe = True
        elif projected.cpu_percent > safe_limits.cpu_percent:
            bottleneck = "CPU_LOAD"
            over_safe = True
        elif projected.ram_gb > safe_limits.ram_gb:
            bottleneck = "RAM_CAPACITY"
            over_safe = True

        if over_hard:
            status = "OVER_CAPACITY"
            summary = f"Projected workload strictly exceeds hard safety ceiling on '{bottleneck}'."
            recommendations.append(f"Reduce number of concurrent cameras or split across multiple inference nodes.")
        elif over_safe:
            status = "WARNING"
            summary = f"Projected workload exceeds recommended safe headroom on '{bottleneck}', but remains below hard ceiling."
            recommendations.append("Acceptable for short peak loads, but leaves reduced margin for sudden crowd bursts.")
        elif (
            projected.gpu_percent >= safe_limits.gpu_percent * 0.95
            or projected.vram_gb >= safe_limits.vram_gb * 0.95
            or projected.cpu_percent >= safe_limits.cpu_percent * 0.95
        ):
            status = "LIMIT_REACHED"
            summary = "Workload utilizes 95%+ of recommended safe capacity."
            recommendations.append("Operating at nominal peak safe capacity.")
        else:
            status = "HEALTHY"
            summary = "Workload operates comfortably within recommended safe headroom."

        return MixedWorkloadCapacity(
            status=status,
            status_summary=summary,
            requested_workload=workload_mix,
            current_usage=current,
            projected_usage=projected,
            safe_budget=safe_limits,
            hard_max_budget=hard_max_limits,
            bottleneck_resource=bottleneck,
            recommendations=recommendations,
            calculation_mode="ESTIMATED",
        )

    @classmethod
    def validate_capacity_for_deployment(
        cls,
        current_workload: Dict[str, int],
        requested_addition: Dict[str, int],
        cpu_info: Dict[str, Any],
        ram_info: Dict[str, Any],
        gpu_info: Dict[str, Any],
        cfg: Optional[CapacitySafetyConfig] = None,
    ) -> DeploymentValidationResult:
        """
        Reusable pre-flight validation called before starting new pipelines.
        Returns ALLOWED, WARNING, or BLOCKED with detailed reasons.
        """
        combined_workload = {}
        for k, v in current_workload.items():
            combined_workload[k] = combined_workload.get(k, 0) + v
        for k, v in requested_addition.items():
            combined_workload[k] = combined_workload.get(k, 0) + v

        mixed = cls.calculate_mixed_workload_capacity(
            combined_workload, cpu_info, ram_info, gpu_info, cfg=cfg
        )

        exceeded = []
        if mixed.projected_usage.gpu_percent > mixed.hard_max_budget.gpu_percent:
            exceeded.append(f"GPU ({mixed.projected_usage.gpu_percent}% > {mixed.hard_max_budget.gpu_percent}%)")
        if mixed.projected_usage.vram_gb > mixed.hard_max_budget.vram_gb:
            exceeded.append(f"VRAM ({mixed.projected_usage.vram_gb}GB > {mixed.hard_max_budget.vram_gb}GB)")
        if mixed.projected_usage.cpu_percent > mixed.hard_max_budget.cpu_percent:
            exceeded.append(f"CPU ({mixed.projected_usage.cpu_percent}% > {mixed.hard_max_budget.cpu_percent}%)")
        if mixed.projected_usage.ram_gb > mixed.hard_max_budget.ram_gb:
            exceeded.append(f"RAM ({mixed.projected_usage.ram_gb}GB > {mixed.hard_max_budget.ram_gb}GB)")

        if mixed.status == "OVER_CAPACITY" or mixed.status == "GPU_UNAVAILABLE":
            verdict = "BLOCKED"
            reason = f"Deployment BLOCKED: {mixed.status_summary}"
        elif mixed.status == "WARNING":
            verdict = "WARNING"
            reason = f"Deployment NOT RECOMMENDED: {mixed.status_summary}"
        else:
            verdict = "ALLOWED"
            reason = "Capacity validation passed. Host server has sufficient safe headroom."

        return DeploymentValidationResult(
            verdict=verdict,
            status=mixed.status,
            reason=reason,
            current_utilization=mixed.current_usage,
            projected_utilization=mixed.projected_usage,
            exceeded_resources=exceeded,
        )


# Global singleton helper
capacity_calculator = CapacityCalculator()
