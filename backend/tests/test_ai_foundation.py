"""
test_ai_foundation.py — Comprehensive Tests for AI Infrastructure Foundation (Step 1).

Tests:
- PipelineState enum & transitions
- AIProfile schema & Standard Profiles
- Runtime Detection on CPU/GPU & safe failure handling
- Capacity Calculator interface & non-ready state
- AI Orchestrator interface returning NOT_IMPLEMENTED
- Structured AIPipelineLogger formatting
- API endpoints & RBAC protection
"""

import pytest
from httpx import AsyncClient

from app.ai.orchestrator.state import PipelineState
from app.ai.orchestrator.service import AIOrchestrator, OrchestratorResponse, ai_orchestrator
from app.ai.profiles.service import AIProfile, AIProfileType, AIProfileService, STANDARD_PROFILES
from app.ai.runtime.detector import RuntimeDetector
from app.ai.capacity.calculator import (
    CapacityCalculator,
    CapacitySafetyConfig,
    ProfileCapacityItem,
    MixedWorkloadCapacity,
    DeploymentValidationResult,
)
from app.ai.logging import AIPipelineLogEvent, AIPipelineLogger


# ── 1. Pipeline State Enum Tests ──────────────────────────────────────────────

def test_pipeline_state_enum_values():
    assert PipelineState.CREATED == "CREATED"
    assert PipelineState.VALIDATING == "VALIDATING"
    assert PipelineState.STARTING == "STARTING"
    assert PipelineState.RUNNING == "RUNNING"
    assert PipelineState.STOPPING == "STOPPING"
    assert PipelineState.STOPPED == "STOPPED"
    assert PipelineState.DEGRADED == "DEGRADED"
    assert PipelineState.FAILED == "FAILED"
    assert PipelineState.RESTARTING == "RESTARTING"
    assert PipelineState.UNKNOWN == "UNKNOWN"


def test_pipeline_state_predicates():
    assert PipelineState.is_active(PipelineState.RUNNING) is True
    assert PipelineState.is_active(PipelineState.STARTING) is True
    assert PipelineState.is_active(PipelineState.STOPPED) is False
    assert PipelineState.is_active(PipelineState.FAILED) is False

    assert PipelineState.is_terminal(PipelineState.STOPPED) is True
    assert PipelineState.is_terminal(PipelineState.FAILED) is True
    assert PipelineState.is_terminal(PipelineState.RUNNING) is False


# ── 2. AI Profile Tests ───────────────────────────────────────────────────────

def test_standard_profiles_registration():
    profiles = AIProfileService.list_profiles()
    assert len(profiles) >= 5

    expected_ids = {
        "CROWD_STANDARD",
        "CROWD_HIGH_DENSITY",
        "QUEUE_STANDARD",
        "FRS_STANDARD",
        "VIDEO_SAFETY",
    }
    actual_ids = {p.profile_id for p in profiles}
    assert expected_ids.issubset(actual_ids)


def test_profile_fields():
    crowd_prof = AIProfileService.get_profile("CROWD_STANDARD")
    assert crowd_prof is not None
    assert crowd_prof.type == AIProfileType.CROWD_STANDARD
    assert crowd_prof.model == "yolov8n"
    assert crowd_prof.processing_fps == 15
    assert crowd_prof.confidence_threshold > 0.0
    assert crowd_prof.tracker_enabled is True
    assert crowd_prof.batch_size == 1
    assert crowd_prof.gpu_requirements.min_vram_mb > 0
    assert crowd_prof.camera_requirements.min_fps > 0
    assert len(crowd_prof.enabled_features) > 0


def test_profile_lookup_nonexistent():
    assert AIProfileService.get_profile("NON_EXISTENT") is None
    assert AIProfileService.validate_profile_exists("NON_EXISTENT") is False
    assert AIProfileService.validate_profile_exists("FRS_STANDARD") is True


# ── 3. Runtime Detection Tests (Safe on CPU & GPU) ─────────────────────────────

def test_detect_cpu():
    cpu = RuntimeDetector.detect_cpu()
    assert "logical_cores" in cpu
    assert cpu["logical_cores"] >= 1
    assert "physical_cores" in cpu
    assert "processor" in cpu


def test_detect_ram():
    ram = RuntimeDetector.detect_ram()
    assert "total_bytes" in ram
    assert "available_bytes" in ram
    assert ram["total_bytes"] > 0
    assert ram["available_bytes"] > 0


def test_detect_storage():
    storage = RuntimeDetector.detect_storage()
    assert "total_bytes" in storage
    assert "free_bytes" in storage
    assert storage["total_bytes"] > 0


def test_detect_gpu_safe():
    gpu = RuntimeDetector.detect_gpu()
    assert "available" in gpu
    assert "status" in gpu
    assert isinstance(gpu["available"], bool)
    assert isinstance(gpu["devices"], list)
    # If no GPU is available, it must report False, not raise an error
    if not gpu["available"]:
        assert gpu["count"] == 0
        assert gpu["status"] in {"NOT_AVAILABLE", "ERROR_QUERYING"}


def test_detect_runtime():
    runtime = RuntimeDetector.detect_runtime()
    assert "docker" in runtime
    assert "nvidia_container_toolkit" in runtime
    assert "tensorrt" in runtime
    assert "deepstream" in runtime
    assert isinstance(runtime["docker"], bool)


@pytest.mark.asyncio
async def test_full_capabilities():
    caps = await RuntimeDetector.get_full_capabilities()
    assert "server" in caps
    assert "cpu" in caps
    assert "memory" in caps
    assert "gpu" in caps
    assert "runtime" in caps
    assert "database" in caps
    assert "redis" in caps
    assert "readiness" in caps


# ── 4. AI Orchestrator Interface Tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_orchestrator_methods_return_not_implemented():
    orchestrator = AIOrchestrator()

    start_res = await orchestrator.start("pipe-001", "CROWD_STANDARD")
    assert start_res.status == "NOT_IMPLEMENTED"
    assert "not implemented" in start_res.message.lower()

    stop_res = await orchestrator.stop("pipe-001")
    assert stop_res.status == "NOT_IMPLEMENTED"

    restart_res = await orchestrator.restart("pipe-001")
    assert restart_res.status == "NOT_IMPLEMENTED"

    pause_res = await orchestrator.pause("pipe-001")
    assert pause_res.status == "NOT_IMPLEMENTED"

    status_res = await orchestrator.status("pipe-001")
    assert status_res.status == "NOT_IMPLEMENTED"

    health = await orchestrator.health_check()
    assert health["orchestrator_status"] == "NOT_IMPLEMENTED"
    assert health["active_pipelines"] == 0


# ── 5. Capacity Calculator Interface Tests ────────────────────────────────────

def test_capacity_calculator_cpu_only():
    """Verify capacity calculator returns valid ProfileCapacityItem for CPU-only machines."""
    cpu_info = {
        "logical_cores": 8,
        "physical_cores": 4,
        "usage_percent": 20.0,
        "current_freq_mhz": 3200.0,
        "processor": "Intel i7",
    }
    ram_info = {
        "total_gb": 16.0,
        "available_gb": 12.0,
        "used_gb": 4.0,
        "used_percent": 25.0,
        "total_bytes": 17179869184,
        "available_bytes": 12884901888,
        "used_bytes": 4294967296,
    }
    gpu_info = {
        "available": False,
        "count": 0,
        "devices": [],
        "driver_version": None,
        "cuda_version": None,
        "status": "NOT_AVAILABLE",
        "message": "nvidia-smi not found.",
    }

    cfg = CapacitySafetyConfig()
    result = CapacityCalculator.calculate_single_profile_capacity(
        "CROWD_STANDARD", cpu_info, ram_info, gpu_info, cfg
    )

    assert isinstance(result, ProfileCapacityItem)
    assert result.status in ("CPU_FALLBACK", "RESOURCE_EXHAUSTED", "GPU_UNAVAILABLE")
    assert result.calculation_mode == "ESTIMATED"
    assert result.capacity.recommended_cameras >= 0
    assert "calculation_mode" in result.model_dump()


# ── 6. Structured Logging Tests ───────────────────────────────────────────────

def test_ai_pipeline_log_event_structure():
    event = AIPipelineLogEvent(
        camera_id="CAM-001",
        zone_id="ZONE-A",
        pipeline_id="PIPE-CROWD-01",
        pipeline_type="CROWD",
        event_type="INFERENCE",
        status="SUCCESS",
        model_version="8.2.0",
        processing_latency_ms=18.4,
    )
    log_dict = event.to_log_dict()
    assert log_dict["camera_id"] == "CAM-001"
    assert log_dict["pipeline_type"] == "CROWD"
    assert log_dict["status"] == "SUCCESS"
    assert log_dict["processing_latency_ms"] == 18.4
    assert "timestamp" in log_dict

    # Verify logger handles without exception
    AIPipelineLogger.log_event(event)


# ── 7. API & RBAC Protection Tests ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ai_endpoints_unauthorized(client: AsyncClient):
    # Without authorization token, all AI endpoints must return 401
    res_caps = await client.get("/api/v1/ai/system/capabilities")
    assert res_caps.status_code == 401

    res_cap = await client.get("/api/v1/ai/system/capacity")
    assert res_cap.status_code == 401

    res_prof = await client.get("/api/v1/ai/profiles")
    assert res_prof.status_code == 401

    res_dep = await client.get("/api/v1/ai/deployments")
    assert res_dep.status_code == 401

    res_pipe = await client.get("/api/v1/ai/pipelines")
    assert res_pipe.status_code == 401


@pytest.mark.asyncio
async def test_ai_endpoints_authorized(client: AsyncClient, superadmin_token: str):
    headers = {"Authorization": f"Bearer {superadmin_token}"}

    # 1. System capabilities — Step 2 schema
    res_caps = await client.get("/api/v1/ai/system/capabilities", headers=headers)
    assert res_caps.status_code == 200
    caps_data = res_caps.json()
    assert caps_data["success"] is True
    # Step 2 keys
    assert "cpu" in caps_data["data"]
    assert "gpu" in caps_data["data"]
    assert "memory" in caps_data["data"]
    assert "runtime" in caps_data["data"]
    assert "readiness" in caps_data["data"]

    # 2. Capacity status — Step 2 schema (all profiles)
    res_cap = await client.get("/api/v1/ai/system/capacity", headers=headers)
    assert res_cap.status_code == 200
    cap_data = res_cap.json()
    assert cap_data["success"] is True
    assert "profiles" in cap_data["data"]
    assert "CROWD_STANDARD" in cap_data["data"]["profiles"]
    assert cap_data["data"]["calculation_mode"] == "ESTIMATED"

    # 3. Profiles
    res_prof = await client.get("/api/v1/ai/profiles", headers=headers)
    assert res_prof.status_code == 200
    prof_data = res_prof.json()
    assert prof_data["success"] is True
    assert len(prof_data["data"]) >= 5

    # 4. Deployments (empty — AI not yet deployed)
    res_dep = await client.get("/api/v1/ai/deployments", headers=headers)
    assert res_dep.status_code == 200
    assert res_dep.json()["data"] == []

    # 5. Pipelines (empty — no active pipelines)
    res_pipe = await client.get("/api/v1/ai/pipelines", headers=headers)
    assert res_pipe.status_code == 200
    assert res_pipe.json()["data"] == []
