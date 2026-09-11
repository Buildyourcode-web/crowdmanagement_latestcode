"""
ai_deployment.py — Database Model for AI Pipeline Deployments.

Maintains persistent deployment state, tracks desired vs actual state,
health telemetry, recovery counters, runtime instance IDs, and execution priority.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class AIPipelineDeployment(Base, UUIDMixin, TimestampMixin):
    """
    Persistent model tracking camera AI pipeline deployments.
    Decouples operator desired state from runtime actual and health states.
    """
    __tablename__ = "ai_pipeline_deployments"

    camera_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cameras.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    camera_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    profile_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    pipeline_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # "CROWD", "QUEUE"

    # Event scoping — AI deployments are contextual per event
    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id"),
        nullable=True,
        index=True,
    )


    # State Machine: desired_state vs actual_state
    desired_state: Mapped[str] = mapped_column(String(50), default="STOPPED", nullable=False, index=True)
    actual_state: Mapped[str] = mapped_column(String(50), default="STOPPED", nullable=False, index=True)
    health_state: Mapped[str] = mapped_column(String(50), default="UNKNOWN", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="NORMAL", nullable=False)  # "CRITICAL", "HIGH", "NORMAL", "LOW"

    # Automatic Resilience Configuration
    auto_restart_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_reconnect_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    restart_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reconnect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Timestamps & Error Diagnostics
    last_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_stopped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Process Supervision
    process_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    runtime_instance_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Audit Metadata
    created_by: Mapped[str] = mapped_column(String(100), default="SYSTEM", nullable=False)
    updated_by: Mapped[str] = mapped_column(String(100), default="SYSTEM", nullable=False)

    # Relationships
    camera: Mapped["Camera"] = relationship("Camera")

    def __init__(self, **kwargs):
        kwargs.setdefault("desired_state", "STOPPED")
        kwargs.setdefault("actual_state", "STOPPED")
        kwargs.setdefault("health_state", "UNKNOWN")
        kwargs.setdefault("priority", "NORMAL")
        kwargs.setdefault("auto_restart_enabled", True)
        kwargs.setdefault("auto_reconnect_enabled", True)
        kwargs.setdefault("restart_count", 0)
        kwargs.setdefault("reconnect_count", 0)
        kwargs.setdefault("created_by", "SYSTEM")
        kwargs.setdefault("updated_by", "SYSTEM")
        super().__init__(**kwargs)

    __table_args__ = (
        UniqueConstraint("camera_id", "profile_id", name="uq_pipeline_deployment_camera_profile"),
        Index("ix_deployment_cam_type", "camera_code", "pipeline_type"),
        Index("ix_deployment_states", "desired_state", "actual_state"),
    )
