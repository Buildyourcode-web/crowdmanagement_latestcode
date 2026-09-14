import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDMixin


class LineCrossingEvent(Base, UUIDMixin, TimestampMixin):
    """
    Durable, immutable ledger for every validated line crossing event.
    Acts as the canonical single source of truth for temple ingress/egress footfall.
    Enforces idempotency via unique constraints on (camera_id, line_id, track_session_id, crossing_sequence)
    and unique idempotency_key.
    """
    __tablename__ = "line_crossing_events"

    # Event Scoping
    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Camera & Line Identifiers
    camera_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cameras.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    camera_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    line_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    line_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    # Tracking & State Machine Identifiers
    track_session_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    track_token: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # e.g. TRK-1042
    crossing_sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1, 2, ...
    direction: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # "IN" or "OUT"
    count_delta: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Quality & Frame Metrics
    detection_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    frame_id: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    crossing_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )

    # Deterministic Idempotency Key: event_id_camera_id_line_id_track_session_id_CROSSING-seq
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)

    # Audit & Spatial Telemetry
    ground_x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ground_y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    signed_distance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meta_data: Mapped[Any] = mapped_column(JSON, default=dict, nullable=True)

    # Relationships
    camera = relationship("Camera", lazy="selectin")
    event = relationship("Event", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("camera_id", "line_id", "track_session_id", "crossing_sequence", name="uq_crossing_event_sequence"),
        Index("idx_crossing_event_time", "event_id", "direction", "crossing_timestamp"),
        Index("idx_crossing_cam_line_time", "camera_id", "line_id", "crossing_timestamp"),
    )
