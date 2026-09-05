import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDMixin


class ROIType(str, Enum):
    CROWD_ROI = "CROWD_ROI"
    QUEUE_ROI = "QUEUE_ROI"
    COUNTING_LINE = "COUNTING_LINE"
    ENTRY_LINE = "ENTRY_LINE"
    EXIT_LINE = "EXIT_LINE"
    EXCLUSION_ZONE = "EXCLUSION_ZONE"
    DIRECTION_LINE = "DIRECTION_LINE"
    ZONE_BOUNDARY = "ZONE_BOUNDARY"


class CameraROIConfiguration(Base, UUIDMixin, TimestampMixin):
    """
    Persisted geometric Regions of Interest (ROIs) and counting lines for cameras.
    Coordinates are normalized (0.0 to 1.0) for resolution independence.
    Configures intended spatial boundaries only — does NOT start AI inference.
    """
    __tablename__ = "camera_roi_configurations"

    camera_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cameras.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    camera_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    profile_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    roi_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    
    # Normalized geometry JSON: points list for polygons or start/end for lines
    geometry_json: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)
    normalized: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    created_by: Mapped[str] = mapped_column(String(100), default="SYSTEM", nullable=False)
    updated_by: Mapped[str] = mapped_column(String(100), default="SYSTEM", nullable=False)

    # Relationships
    camera = relationship("Camera", back_populates="roi_configurations")

    __table_args__ = (
        Index("ix_camera_roi_lookup", "camera_code", "profile_id"),
        Index("ix_camera_roi_type", "camera_code", "roi_type"),
    )
