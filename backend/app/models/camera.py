import uuid
from datetime import datetime
from typing import Any, List, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDMixin


class Camera(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "cameras"

    # Core Identifiers
    camera_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    camera_type: Mapped[str] = mapped_column(String(50), default="CROWD", index=True, nullable=False)
    
    # Network & RTSP Configuration
    private_ip: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    port: Mapped[Optional[int]] = mapped_column(Integer, default=554, nullable=True)
    rtsp_url_encrypted: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    password_encrypted: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    codec: Mapped[Optional[str]] = mapped_column(String(50), default="h264", nullable=True)
    protocol: Mapped[Optional[str]] = mapped_column(String(20), default="rtsp", nullable=True)

    # Location & Zone
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=True)
    zone_code: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    location_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    coordinates: Mapped[Any] = mapped_column(JSON, default=lambda: [78.4635, 17.4175], nullable=False)
    
    # Operational & Stream Status
    status: Mapped[str] = mapped_column(String(50), default="online", index=True, nullable=False)
    ai_status: Mapped[str] = mapped_column(String(50), default="online", nullable=False)
    stream_status: Mapped[str] = mapped_column(String(50), default="NOT_TESTED", nullable=False)
    stream_stability: Mapped[str] = mapped_column(String(50), default="UNKNOWN", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Capabilities & Metrics
    is_frs_camera: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    is_ptz: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolution: Mapped[str] = mapped_column(String(50), default="1080p", nullable=False)
    fps: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=38, nullable=False)
    packet_loss_pct: Mapped[float] = mapped_column(Float, default=0.1, nullable=False)
    people_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reconnect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Telemetry
    gpu_id: Mapped[Optional[str]] = mapped_column(String(50), default="GPU-01", nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    zone: Mapped[Optional["Zone"]] = relationship("Zone", back_populates="cameras")
    ai_assignments: Mapped[List["CameraAIProfileAssignment"]] = relationship(
        "CameraAIProfileAssignment",
        back_populates="camera",
        cascade="all, delete-orphan",
        lazy="noload",  # was "selectin" — caused 7s Supabase N+1 queries
    )
    roi_configurations: Mapped[List["CameraROIConfiguration"]] = relationship(
        "CameraROIConfiguration",
        back_populates="camera",
        cascade="all, delete-orphan",
        lazy="noload",  # was "selectin" — caused 7s Supabase N+1 queries
    )

