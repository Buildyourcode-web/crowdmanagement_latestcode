"""
service.py — AI Profile Abstraction, Workload Specifications & Registry.

Defines standardized workload profiles for Crowd, Queue, FRS, and Safety AI pipelines.
All resource consumption figures are marked as ESTIMATED.
Architecture allows future live benchmark measurements to override estimates.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AIProfileType(str, Enum):
    CROWD_STANDARD = "CROWD_STANDARD"
    CROWD_HIGH_DENSITY = "CROWD_HIGH_DENSITY"
    QUEUE_STANDARD = "QUEUE_STANDARD"
    FRS_STANDARD = "FRS_STANDARD"
    VIDEO_SAFETY = "VIDEO_SAFETY"


class GPURequirement(BaseModel):
    min_vram_mb: int = 2048
    recommended_vram_mb: int = 4096
    cuda_compute_capability: Optional[str] = "7.5"
    tensorrt_supported: bool = True


class CameraRequirement(BaseModel):
    min_resolution: str = "720p"
    recommended_resolution: str = "1080p"
    min_fps: int = 15
    max_latency_ms: int = 200


class ProfileWorkloadEstimate(BaseModel):
    """
    Estimated resource consumption per active camera stream under this profile.
    Explicitly marked as ESTIMATED until replaced by physical benchmarks.
    """
    estimated_vram_gb: float = Field(..., description="Estimated GPU VRAM required per camera stream (GB)")
    estimated_gpu_load_percent: float = Field(..., description="Estimated GPU core utilization percent per stream")
    estimated_cpu_percent: float = Field(..., description="Estimated CPU core load percent per stream")
    estimated_ram_mb: float = Field(..., description="Estimated system RAM required per stream (MB)")
    supports_cpu_execution: bool = Field(default=False, description="True if stream can run on CPU fallback")
    cpu_only_estimated_cpu_percent: Optional[float] = Field(default=25.0, description="CPU load if running on CPU-only")
    calculation_mode: str = "ESTIMATED"


class AIProfile(BaseModel):
    """
    Standard AI Profile schema for model and workload configuration.
    """
    profile_id: str
    name: str
    type: AIProfileType
    pipeline_type: str = "CROWD"  # CROWD, QUEUE, FRS, SAFETY
    model: str
    model_version: str
    processing_fps: int = 15
    confidence_threshold: float = 0.50
    tracker_enabled: bool = True
    batch_size: int = 1
    gpu_requirements: GPURequirement = Field(default_factory=GPURequirement)
    camera_requirements: CameraRequirement = Field(default_factory=CameraRequirement)
    workload: ProfileWorkloadEstimate
    enabled_features: List[str] = Field(default_factory=list)
    description: Optional[str] = None


# ── Standard Profiles with Configurable Estimated Workloads ─────────────────

STANDARD_PROFILES: Dict[str, AIProfile] = {
    "CROWD_STANDARD": AIProfile(
        profile_id="CROWD_STANDARD",
        name="Standard Crowd Headcount & Flow",
        type=AIProfileType.CROWD_STANDARD,
        pipeline_type="CROWD",
        model="yolov8n",
        model_version="8.2.0",
        processing_fps=15,
        confidence_threshold=0.45,
        tracker_enabled=True,
        batch_size=1,
        gpu_requirements=GPURequirement(min_vram_mb=1536, recommended_vram_mb=3072),
        camera_requirements=CameraRequirement(min_resolution="720p", recommended_resolution="1080p", min_fps=15),
        workload=ProfileWorkloadEstimate(
            estimated_vram_gb=0.45,
            estimated_gpu_load_percent=3.5,
            estimated_cpu_percent=4.0,
            estimated_ram_mb=350.0,
            supports_cpu_execution=True,
            cpu_only_estimated_cpu_percent=22.0,
            calculation_mode="ESTIMATED",
        ),
        enabled_features=["headcount", "flow_direction", "density_estimation"],
        description="Standard crowd monitoring for general pandal and queue sectors.",
    ),
    "CROWD_HIGH_DENSITY": AIProfile(
        profile_id="CROWD_HIGH_DENSITY",
        name="High-Density Sanctum Crowd AI",
        type=AIProfileType.CROWD_HIGH_DENSITY,
        pipeline_type="CROWD",
        model="yolov8x",
        model_version="8.2.0",
        processing_fps=20,
        confidence_threshold=0.35,
        tracker_enabled=True,
        batch_size=2,
        gpu_requirements=GPURequirement(min_vram_mb=4096, recommended_vram_mb=8192),
        camera_requirements=CameraRequirement(min_resolution="1080p", recommended_resolution="4K", min_fps=20),
        workload=ProfileWorkloadEstimate(
            estimated_vram_gb=1.20,
            estimated_gpu_load_percent=8.0,
            estimated_cpu_percent=7.0,
            estimated_ram_mb=750.0,
            supports_cpu_execution=False,
            cpu_only_estimated_cpu_percent=None,
            calculation_mode="ESTIMATED",
        ),
        enabled_features=["headcount", "dense_cluster_detection", "bottleneck_warning", "reverse_flow"],
        description="High precision detection for dense sanctum sanctorum crowd.",
    ),
    "QUEUE_STANDARD": AIProfile(
        profile_id="QUEUE_STANDARD",
        name="Queue Length & Wait-Time AI",
        type=AIProfileType.QUEUE_STANDARD,
        pipeline_type="QUEUE",
        model="yolov8s",
        model_version="8.2.0",
        processing_fps=10,
        confidence_threshold=0.50,
        tracker_enabled=True,
        batch_size=1,
        gpu_requirements=GPURequirement(min_vram_mb=2048, recommended_vram_mb=4096),
        camera_requirements=CameraRequirement(min_resolution="720p", recommended_resolution="1080p", min_fps=10),
        workload=ProfileWorkloadEstimate(
            estimated_vram_gb=0.55,
            estimated_gpu_load_percent=4.0,
            estimated_cpu_percent=4.5,
            estimated_ram_mb=400.0,
            supports_cpu_execution=True,
            cpu_only_estimated_cpu_percent=26.0,
            calculation_mode="ESTIMATED",
        ),
        enabled_features=["queue_length_meters", "people_in_queue", "wait_time_estimation"],
        description="Line queue tracking, barricade density, and congestion estimation.",
    ),
    "FRS_STANDARD": AIProfile(
        profile_id="FRS_STANDARD",
        name="Biometric Facial Recognition Standard",
        type=AIProfileType.FRS_STANDARD,
        pipeline_type="FRS",
        model="buffalo_l",
        model_version="1.0.1",
        processing_fps=12,
        confidence_threshold=0.50,
        tracker_enabled=True,
        batch_size=1,
        gpu_requirements=GPURequirement(min_vram_mb=3072, recommended_vram_mb=6144),
        camera_requirements=CameraRequirement(min_resolution="1080p", recommended_resolution="1080p", min_fps=15),
        workload=ProfileWorkloadEstimate(
            estimated_vram_gb=1.40,
            estimated_gpu_load_percent=10.0,
            estimated_cpu_percent=8.0,
            estimated_ram_mb=900.0,
            supports_cpu_execution=False,
            cpu_only_estimated_cpu_percent=None,
            calculation_mode="ESTIMATED",
        ),
        enabled_features=["face_detection", "512d_embedding", "cosine_matcher", "quality_filter"],
        description="InsightFace buffalo_l 512-D biometric matching against authorized watchlist.",
    ),
    "VIDEO_SAFETY": AIProfile(
        profile_id="VIDEO_SAFETY",
        name="Video Safety & Incident Anomaly AI",
        type=AIProfileType.VIDEO_SAFETY,
        pipeline_type="SAFETY",
        model="yolov8s-pose",
        model_version="8.2.0",
        processing_fps=15,
        confidence_threshold=0.55,
        tracker_enabled=True,
        batch_size=1,
        gpu_requirements=GPURequirement(min_vram_mb=2560, recommended_vram_mb=4096),
        camera_requirements=CameraRequirement(min_resolution="720p", recommended_resolution="1080p", min_fps=15),
        workload=ProfileWorkloadEstimate(
            estimated_vram_gb=0.75,
            estimated_gpu_load_percent=6.0,
            estimated_cpu_percent=6.0,
            estimated_ram_mb=550.0,
            supports_cpu_execution=True,
            cpu_only_estimated_cpu_percent=32.0,
            calculation_mode="ESTIMATED",
        ),
        enabled_features=["person_down_detection", "panic_movement_detection", "barrier_crossing"],
        description="Pose and motion anomaly detection for perimeter and crowd safety.",
    ),
}


class AIProfileService:
    """Service to retrieve and validate AI workload profiles."""

    @staticmethod
    def list_profiles() -> List[AIProfile]:
        """List all registered AI workload profiles."""
        return list(STANDARD_PROFILES.values())

    @staticmethod
    def get_profile(profile_id: str) -> Optional[AIProfile]:
        """Lookup an AI profile by its identifier."""
        return STANDARD_PROFILES.get(profile_id)

    @staticmethod
    def validate_profile_exists(profile_id: str) -> bool:
        """Returns True if the profile is registered."""
        return profile_id in STANDARD_PROFILES
