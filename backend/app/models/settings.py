from typing import Any, Optional
from sqlalchemy import Boolean, Float, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, UUIDMixin


class AlertThresholdConfig(Base, UUIDMixin, TimestampMixin):
    """Crowd / queue / camera alert threshold settings (singleton)."""
    __tablename__ = "alert_threshold_configs"

    crowd_warning_pct: Mapped[float] = mapped_column(Float, default=80.0, nullable=False)
    crowd_high_pct: Mapped[float] = mapped_column(Float, default=90.0, nullable=False)
    crowd_critical_pct: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    crowd_extreme_pct: Mapped[float] = mapped_column(Float, default=110.0, nullable=False)

    queue_warning_count: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    queue_critical_count: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    queue_wait_warning_min: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    queue_wait_critical_min: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    sudden_inflow_pct: Mapped[float] = mapped_column(Float, default=40.0, nullable=False)
    reverse_flow_pct: Mapped[float] = mapped_column(Float, default=25.0, nullable=False)
    density_growth_rate_pct: Mapped[float] = mapped_column(Float, default=15.0, nullable=False)

    camera_offline_sec: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    camera_degraded_sec: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    person_down_sec: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    panic_risk_score: Mapped[float] = mapped_column(Float, default=0.80, nullable=False)
    bottleneck_risk_score: Mapped[float] = mapped_column(Float, default=0.75, nullable=False)

    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    config_label: Mapped[str] = mapped_column(String(100), default="default", nullable=False)


class AIConfigSettings(Base, UUIDMixin, TimestampMixin):
    """AI model and detection pipeline configuration (singleton)."""
    __tablename__ = "ai_config_settings"

    crowd_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), default="YOLO", nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), default="v1", nullable=False)
    detection_confidence: Mapped[float] = mapped_column(Float, default=0.50, nullable=False)
    tracking_algorithm: Mapped[str] = mapped_column(String(50), default="ByteTrack", nullable=False)
    processing_fps: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    people_counting_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    queue_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    bottleneck_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reverse_flow_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fall_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    panic_risk_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class FRSConfigSettings(Base, UUIDMixin, TimestampMixin):
    """Facial Recognition System configuration (singleton)."""
    __tablename__ = "frs_config_settings"

    face_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_face_size: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    face_quality_threshold: Mapped[float] = mapped_column(Float, default=0.60, nullable=False)
    match_threshold: Mapped[float] = mapped_column(Float, default=0.94, nullable=False)
    candidate_threshold: Mapped[float] = mapped_column(Float, default=0.85, nullable=False)
    max_candidates: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_confirmation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    watchlist_access_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    missing_person_access_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    candidate_retention_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    image_retention_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    audit_retention_days: Mapped[int] = mapped_column(Integer, default=365, nullable=False)

    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class NotificationConfig(Base, UUIDMixin, TimestampMixin):
    """Notification channel and routing configuration (singleton)."""
    __tablename__ = "notification_configs"

    inapp_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    websocket_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    critical_immediate: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    high_immediate: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    medium_grouped: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    low_summary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    email_recipients: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)

    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class SystemConfig(Base, UUIDMixin, TimestampMixin):
    """Platform-wide system configuration (singleton)."""
    __tablename__ = "system_configs"

    app_name: Mapped[str] = mapped_column(String(100), default="BYC AI Command Center", nullable=False)
    app_version: Mapped[str] = mapped_column(String(20), default="1.0.0", nullable=False)
    environment: Mapped[str] = mapped_column(String(50), default="production", nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata", nullable=False)

    websocket_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    redis_pubsub_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    event_retention_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)

    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    maintenance_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
