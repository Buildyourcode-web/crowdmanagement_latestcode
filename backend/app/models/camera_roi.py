import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String
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
    Supports both legacy DB columns (roi_name, polygon_points, is_active) and modern schema.
    """
    __tablename__ = "camera_roi_configurations"

    camera_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cameras.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    camera_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    profile_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    roi_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Both name and roi_name are supported and synced (roi_name is NOT NULL in PostgreSQL)
    roi_name: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    # Geometry storage (polygon_points is NOT NULL in PostgreSQL)
    polygon_points: Mapped[Any] = mapped_column(JSON, nullable=False)
    geometry_json: Mapped[Any] = mapped_column(JSON, default=dict, nullable=True)

    calibrated_area_sqm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    direction: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Status (is_active is NOT NULL in PostgreSQL)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    normalized: Mapped[bool] = mapped_column(Boolean, default=True, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=True)

    created_by: Mapped[str] = mapped_column(String(100), default="SYSTEM", nullable=True)
    updated_by: Mapped[str] = mapped_column(String(100), default="SYSTEM", nullable=True)

    def __init__(self, **kwargs):
        # Auto-sync roi_name <-> name
        if "name" in kwargs and "roi_name" not in kwargs:
            kwargs["roi_name"] = kwargs["name"]
        elif "roi_name" in kwargs and "name" not in kwargs:
            kwargs["name"] = kwargs["roi_name"]

        # Auto-sync geometry_json <-> polygon_points
        if "geometry_json" in kwargs and "polygon_points" not in kwargs:
            geom = kwargs["geometry_json"]
            if isinstance(geom, dict):
                if "points" in geom:
                    kwargs["polygon_points"] = geom["points"]
                elif "start" in geom and "end" in geom:
                    kwargs["polygon_points"] = [geom["start"], geom["end"]]
                    if "direction" in geom and "direction" not in kwargs:
                        kwargs["direction"] = geom["direction"]
                else:
                    kwargs["polygon_points"] = geom
            else:
                kwargs["polygon_points"] = geom
        elif "polygon_points" in kwargs and "geometry_json" not in kwargs:
            kwargs["geometry_json"] = {"points": kwargs["polygon_points"]}

        # Auto-sync enabled <-> is_active
        if "enabled" in kwargs and "is_active" not in kwargs:
            kwargs["is_active"] = bool(kwargs["enabled"])
        elif "is_active" in kwargs and "enabled" not in kwargs:
            kwargs["enabled"] = bool(kwargs["is_active"])

        super().__init__(**kwargs)

    # Relationships
    camera = relationship("Camera", back_populates="roi_configurations")

    __table_args__ = (
        Index("ix_camera_roi_lookup", "camera_code", "profile_id"),
        Index("ix_camera_roi_type", "camera_code", "roi_type"),
    )
