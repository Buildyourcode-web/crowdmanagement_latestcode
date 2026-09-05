"""
config.py — Crowd Pipeline Configuration Schema & Builder.

Assembles camera RTSP settings, spatial geometries (ROI, exclusion zones, counting lines),
model specifications, and threshold policies into an immutable runtime configuration.
Credentials are kept secure and never exposed in sanitized strings or logs.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.ai.pipelines.crowd.models_registry import ModelRegistryService, PersonDetectionModel
from app.ai.profiles.service import AIProfile, STANDARD_PROFILES
from app.models.camera import Camera
from app.models.camera_roi import CameraROIConfiguration, ROIType
from app.security.encryption import decrypt_credential, sanitize_rtsp_url


class CrowdPipelineConfig(BaseModel):
    """Immutable runtime configuration for a single camera Crowd AI pipeline."""
    camera_id: str
    camera_code: str
    camera_name: str
    zone_id: Optional[str] = None
    zone_code: Optional[str] = None
    profile_id: str = "CROWD_STANDARD"

    # Streaming & Transport
    rtsp_url_internal: str = Field(..., repr=False)  # Contains auth, never logged
    rtsp_url_sanitized: str
    transport_protocol: str = "tcp"  # TCP by default
    input_resolution: str = "1080p"
    processing_fps: int = 15
    batch_size: int = 1

    # AI Model
    model: PersonDetectionModel
    confidence_threshold: float = 0.45

    # Spatial Geometries (Normalized 0.0 - 1.0)
    crowd_roi_points: List[Dict[str, float]] = Field(default_factory=list)
    crowd_roi_id: Optional[str] = None
    crowd_roi_name: Optional[str] = None
    exclusion_zones: List[List[Dict[str, float]]] = Field(default_factory=list)
    counting_lines: List[Dict[str, Any]] = Field(default_factory=list)

    # Calibration & Metrics
    physical_area_m2: Optional[float] = None
    counting_window_seconds: int = 60
    event_cooldown_seconds: int = 60

    # Density & Risk Thresholds
    density_low_max: float = 40.0
    density_moderate_max: float = 70.0
    density_high_max: float = 85.0
    density_critical_min: float = 85.0

    @classmethod
    def from_camera_and_geometries(
        cls,
        camera: Camera,
        profile_id: str,
        roi_configs: List[CameraROIConfiguration],
        physical_area_m2: Optional[float] = None,
        threshold_override: Optional[Dict[str, float]] = None,
    ) -> "CrowdPipelineConfig":
        """
        Builds pipeline configuration from DB models with credential decryption
        and spatial geometry mapping.
        """
        # 1. Resolve RTSP URLs securely
        raw_rtsp = decrypt_credential(camera.rtsp_url_encrypted) if camera.rtsp_url_encrypted else ""
        sanitized_rtsp = sanitize_rtsp_url(raw_rtsp) if raw_rtsp else "rtsp://unknown"

        # 2. Resolve Profile & Model
        profile: AIProfile = STANDARD_PROFILES.get(profile_id, STANDARD_PROFILES["CROWD_STANDARD"])
        model = ModelRegistryService.get_model_for_profile(profile_id)

        # 3. Extract Spatial Geometries
        crowd_roi_pts: List[Dict[str, float]] = []
        crowd_roi_id: Optional[str] = None
        crowd_roi_name: Optional[str] = None
        exclusion_polygons: List[List[Dict[str, float]]] = []
        counting_lines_list: List[Dict[str, Any]] = []

        for r in roi_configs:
            if not r.enabled:
                continue
            geom = r.geometry_json or {}

            if r.roi_type == ROIType.CROWD_ROI:
                pts = geom.get("points", [])
                if len(pts) >= 3 and not crowd_roi_pts:
                    crowd_roi_pts = pts
                    crowd_roi_id = str(r.id)
                    crowd_roi_name = r.name
            elif r.roi_type == ROIType.EXCLUSION_ZONE:
                pts = geom.get("points", [])
                if len(pts) >= 3:
                    exclusion_polygons.append(pts)
            elif r.roi_type in (ROIType.ENTRY_LINE, ROIType.EXIT_LINE, ROIType.DIRECTION_LINE):
                start = geom.get("start")
                end = geom.get("end")
                direction = geom.get("direction", "BOTH")
                if start and end:
                    counting_lines_list.append({
                        "id": str(r.id),
                        "name": r.name,
                        "type": r.roi_type.value if hasattr(r.roi_type, "value") else str(r.roi_type),
                        "start": start,
                        "end": end,
                        "direction": direction,
                    })

        thresholds = threshold_override or {}

        return cls(
            camera_id=str(camera.id),
            camera_code=camera.camera_code,
            camera_name=camera.name,
            zone_id=str(camera.zone_id) if camera.zone_id else None,
            zone_code=camera.zone_code,
            profile_id=profile_id,
            rtsp_url_internal=raw_rtsp,
            rtsp_url_sanitized=sanitized_rtsp,
            transport_protocol="tcp",
            input_resolution=camera.resolution or profile.camera_requirements.min_resolution,
            processing_fps=profile.processing_fps,
            batch_size=profile.batch_size,
            model=model,
            confidence_threshold=profile.confidence_threshold,
            crowd_roi_points=crowd_roi_pts,
            crowd_roi_id=crowd_roi_id,
            crowd_roi_name=crowd_roi_name,
            exclusion_zones=exclusion_polygons,
            counting_lines=counting_lines_list,
            physical_area_m2=physical_area_m2,
            density_low_max=thresholds.get("low_max", 40.0),
            density_moderate_max=thresholds.get("mod_max", 70.0),
            density_high_max=thresholds.get("high_max", 85.0),
            density_critical_min=thresholds.get("crit_min", 85.0),
        )
