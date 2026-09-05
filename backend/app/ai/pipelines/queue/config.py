"""
config.py — Queue AI Pipeline Configuration Builder.

Encapsulates camera metadata, decrypted internal RTSP feeds, sanitized public URLs,
normalized spatial geometries (Queue ROI, Entry/Exit lines, Direction lines, Exclusion zones),
and calibration parameters for real-time Queue AI execution.
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.ai.pipelines.crowd.models_registry import PersonDetectionModel
from app.ai.pipelines.queue.models_registry import QueueModelRegistryService
from app.models.camera import Camera
from app.models.camera_roi import CameraROIConfiguration, ROIType
from app.security.encryption import decrypt_credential


class QueueGeometryRequirement(BaseModel):
    """Result of checking queue geometry prerequisites."""
    model_config = {"arbitrary_types_allowed": True}
    is_ready: bool
    missing_requirements: List[str] = Field(default_factory=list)
    queue_roi: Optional[CameraROIConfiguration] = None
    entry_line: Optional[CameraROIConfiguration] = None
    exit_line: Optional[CameraROIConfiguration] = None
    direction_line: Optional[CameraROIConfiguration] = None
    exclusion_zones: List[CameraROIConfiguration] = Field(default_factory=list)


def sanitize_rtsp_url(rtsp_url: str) -> str:
    "Masks credentials from RTSP URLs for telemetry and logs."
    if not rtsp_url:
        return ""
    return re.sub(r"://([^:@]+):([^@]+)@", r"://\1:***@", rtsp_url)


class QueuePipelineConfig(BaseModel):
    "Runtime configuration for an individual camera's Queue AI pipeline."

    camera_id: str
    camera_code: str
    camera_name: str
    zone_id: Optional[str] = None
    zone_code: Optional[str] = None
    profile_id: str = "QUEUE_STANDARD"

    # RTSP Ingestion (Internal decrypted for ffmpeg/GStreamer, sanitized for logs)
    rtsp_url_internal: str
    rtsp_url_sanitized: str
    transport_protocol: str = "tcp"
    input_resolution: str = "1080p"
    processing_fps: int = 10
    batch_size: int = 1

    # AI Model
    model: PersonDetectionModel
    confidence_threshold: float = 0.50

    # Spatial Geometries (Normalized 0.0 - 1.0)
    queue_roi_points: List[Dict[str, float]] = Field(default_factory=list)
    queue_roi_id: Optional[str] = None
    queue_roi_name: Optional[str] = None
    entry_line: Dict[str, Any] = Field(default_factory=dict)
    exit_line: Dict[str, Any] = Field(default_factory=dict)
    direction_line: Optional[Dict[str, Any]] = None
    exclusion_zones: List[List[Dict[str, float]]] = Field(default_factory=list)

    # Calibration & Metrics
    queue_capacity: Optional[int] = None
    physical_area_m2: Optional[float] = None
    physical_length_meters: Optional[float] = None
    counting_window_seconds: int = 60
    growth_window_seconds: int = 60
    event_cooldown_seconds: int = 60

    # Thresholds
    occupancy_warning_pct: float = 75.0
    occupancy_critical_pct: float = 90.0
    wait_time_warning_seconds: int = 600
    wait_time_critical_seconds: int = 900
    inflow_spike_threshold: int = 40
    growth_spike_threshold: int = 25

    def __repr__(self) -> str:
        d = self.model_dump()
        d["rtsp_url_internal"] = sanitize_rtsp_url(self.rtsp_url_internal)
        return f"QueuePipelineConfig({d})"

    def __str__(self) -> str:
        return self.__repr__()

    @classmethod
    def check_geometry_requirements(cls, roi_configs: List[CameraROIConfiguration]) -> QueueGeometryRequirement:
        "Validates that QUEUE_ROI, ENTRY_LINE, and EXIT_LINE are configured."
        queue_roi = None
        entry_line = None
        exit_line = None
        direction_line = None
        exclusion_zones = []

        for r in roi_configs:
            if not r.enabled:
                continue
            geom = r.geometry_json or {}
            if r.roi_type == ROIType.QUEUE_ROI and len(geom.get("points", [])) >= 3:
                queue_roi = r
            elif r.roi_type == ROIType.ENTRY_LINE and "start" in geom and "end" in geom:
                entry_line = r
            elif r.roi_type == ROIType.EXIT_LINE and "start" in geom and "end" in geom:
                exit_line = r
            elif r.roi_type == ROIType.DIRECTION_LINE and "start" in geom and "end" in geom:
                direction_line = r
            elif r.roi_type == ROIType.EXCLUSION_ZONE and len(geom.get("points", [])) >= 3:
                exclusion_zones.append(r)

        missing = []
        if not queue_roi:
            missing.append("QUEUE_ROI missing")
        if not entry_line:
            missing.append("ENTRY_LINE missing")
        if not exit_line:
            missing.append("EXIT_LINE missing")

        return QueueGeometryRequirement(
            is_ready=len(missing) == 0,
            missing_requirements=missing,
            queue_roi=queue_roi,
            entry_line=entry_line,
            exit_line=exit_line,
            direction_line=direction_line,
            exclusion_zones=exclusion_zones,
        )

    @classmethod
    def from_camera_and_geometries(
        cls,
        camera: Camera,
        profile_id: str = "QUEUE_STANDARD",
        roi_configs: Optional[List[CameraROIConfiguration]] = None,
        queue_capacity: Optional[int] = None,
        physical_area_m2: Optional[float] = None,
        physical_length_meters: Optional[float] = None,
    ) -> "QueuePipelineConfig":
        "Builds validated QueuePipelineConfig from Camera and DB ROI configurations."
        # 1. Resolve RTSP URL
        raw_rtsp = ""
        if camera.rtsp_url_encrypted:
            try:
                raw_rtsp = decrypt_credential(camera.rtsp_url_encrypted)
            except Exception:
                raw_rtsp = camera.rtsp_url_encrypted
        elif camera.private_ip:
            raw_rtsp = f"rtsp://{camera.private_ip}:{camera.port or 554}/Streaming/Channels/101"

        sanitized_rtsp = sanitize_rtsp_url(raw_rtsp)

        # 2. Extract Geometries
        geoms = cls.check_geometry_requirements(roi_configs or [])
        queue_roi_pts = geoms.queue_roi.geometry_json.get("points", []) if geoms.queue_roi else []
        queue_roi_id = str(geoms.queue_roi.id) if geoms.queue_roi else None
        queue_roi_name = geoms.queue_roi.name if geoms.queue_roi else "Queue Sector"

        entry_line_dict = geoms.entry_line.geometry_json if geoms.entry_line else {}
        exit_line_dict = geoms.exit_line.geometry_json if geoms.exit_line else {}
        direction_line_dict = geoms.direction_line.geometry_json if geoms.direction_line else None

        excl_list = [
            e.geometry_json.get("points", [])
            for e in geoms.exclusion_zones
            if e.geometry_json and len(e.geometry_json.get("points", [])) >= 3
        ]

        # 3. Model
        model = QueueModelRegistryService.get_default_model()

        return cls(
            camera_id=str(camera.id),
            camera_code=camera.camera_code,
            camera_name=camera.name,
            zone_id=str(camera.zone_id) if camera.zone_id else None,
            zone_code=camera.zone_code,
            profile_id=profile_id,
            rtsp_url_internal=raw_rtsp,
            rtsp_url_sanitized=sanitized_rtsp,
            transport_protocol=camera.protocol or "tcp",
            input_resolution=camera.resolution or "1080p",
            processing_fps=10,
            batch_size=1,
            model=model,
            confidence_threshold=model.confidence_threshold,
            queue_roi_points=queue_roi_pts,
            queue_roi_id=queue_roi_id,
            queue_roi_name=queue_roi_name,
            entry_line=entry_line_dict,
            exit_line=exit_line_dict,
            direction_line=direction_line_dict,
            exclusion_zones=excl_list,
            queue_capacity=queue_capacity,
            physical_area_m2=physical_area_m2,
            physical_length_meters=physical_length_meters,
        )
