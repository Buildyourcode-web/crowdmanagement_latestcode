"""
camera_ai_assignment.py — Database Model for Camera AI Profile Assignments.

Stores persistent configuration mapping cameras to AI workload profiles.
Enforces unique (camera_id, profile_id) pairs to prevent duplicate assignments.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class CameraAIProfileAssignment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "camera_ai_profile_assignments"

    camera_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cameras.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    camera_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    profile_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    assigned_by: Mapped[str] = mapped_column(String(100), default="SYSTEM", nullable=False)
    
    validation_status: Mapped[str] = mapped_column(String(50), default="VALID", nullable=False)
    validation_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Relationships
    camera: Mapped["Camera"] = relationship("Camera", back_populates="ai_assignments")

    __table_args__ = (
        UniqueConstraint("camera_id", "profile_id", name="uq_camera_profile_assignment"),
        Index("ix_camera_profile_code", "camera_code", "profile_id"),
    )
