"""
config.py — FRS Pipeline Configuration & Camera Parameter Resolver.

Provides:
- Secure ingestion of RTSP stream credentials.
- Protection against credential leakage in logs/telemetry via masked repr.
- Configurable biometric, quality, matching, top-k, and retention thresholds.
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple
from urllib.parse import quote_plus, urlparse, urlunparse

from app.ai.pipelines.frs.models_registry import FRSModelRegistry, FRSModelSpec


@dataclass
class FRSPipelineConfig:
    camera_id: str
    camera_code: str
    camera_name: str
    rtsp_url: str
    sanitized_rtsp_url: str
    profile_id: str = "FRS_STANDARD"
    zone_id: Optional[str] = None
    zone_code: Optional[str] = None
    location_name: str = "Khairatabad Perimeter"

    # Biometric Models
    detector_model: FRSModelSpec = field(default_factory=FRSModelRegistry.get_default_detector)
    embedder_model: FRSModelSpec = field(default_factory=FRSModelRegistry.get_default_embedder)

    # Thresholds
    detection_confidence_threshold: float = 0.60
    min_face_width: int = 60
    min_face_height: int = 60
    min_sharpness_score: float = 50.0  # Laplacian variance
    min_brightness: float = 40.0
    max_brightness: float = 220.0
    max_pose_yaw_deg: float = 35.0
    max_pose_pitch_deg: float = 30.0
    match_threshold: float = 0.65  # 65% cosine similarity
    top_k: int = 3
    duplicate_suppression_seconds: int = 60
    retention_days: int = 30
    fps: int = 10
    resolution: Tuple[int, int] = (1920, 1080)

    def __repr__(self) -> str:
        return (
            f"FRSPipelineConfig(camera_code='{self.camera_code}', "
            f"profile='{self.profile_id}', "
            f"rtsp='{self.sanitized_rtsp_url}', "
            f"detector='{self.detector_model.model_id}', "
            f"embedder='{self.embedder_model.model_id}', "
            f"match_thresh={self.match_threshold})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    @classmethod
    def sanitize_url(cls, url: str) -> str:
        """Strips credentials from RTSP URLs for telemetry and logs."""
        if not url:
            return ""
        try:
            parsed = urlparse(url)
            if parsed.username or parsed.password:
                netloc = parsed.hostname or ""
                if parsed.port:
                    netloc += f":{parsed.port}"
                return urlunparse(parsed._replace(netloc=f"***:***@{netloc}"))
            return url
        except Exception:
            return "rtsp://***:***@hidden"

    @classmethod
    def build_rtsp_url(
        cls,
        ip: Optional[str],
        port: int = 554,
        username: Optional[str] = None,
        password: Optional[str] = None,
        stream_path: str = "Streaming/Channels/101",
    ) -> str:
        """Constructs an encrypted/authenticated RTSP URI safely."""
        if not ip:
            return ""
        user_enc = quote_plus(username) if username else ""
        pass_enc = quote_plus(password) if password else ""
        auth = f"{user_enc}:{pass_enc}@" if user_enc and pass_enc else ""
        clean_path = stream_path.lstrip("/")
        return f"rtsp://{auth}{ip}:{port}/{clean_path}"
