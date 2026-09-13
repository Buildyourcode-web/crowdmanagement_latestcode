import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, UUIDMixin


class QueueSnapshot(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "queue_snapshots"

    queue_code: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    gate_code: Mapped[str] = mapped_column(String(50), index=True, default="MAIN_GATE", nullable=False)
    zone_code: Mapped[str] = mapped_column(String(50), index=True, default="ZONE_GENERAL", nullable=False)

    camera_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=True, index=True)
    camera_code: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    profile_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=True)
    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=True, index=True)


    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )

    queue_length: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    people_waiting: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_wait_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_dwell_seconds: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    inflow_rate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outflow_rate: Mapped[Optional[int]] = mapped_column(Integer, default=0, nullable=True)
    processing_rate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    growth_rate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    occupancy_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    density: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    density_type: Mapped[Optional[str]] = mapped_column(String(50), default="RELATIVE", nullable=True)
    queue_length_val: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    queue_length_unit: Mapped[Optional[str]] = mapped_column(String(50), default="normalized_extent", nullable=True)

    risk_score: Mapped[Optional[float]] = mapped_column(Float, default=0.0, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(50), default="LOW", nullable=False)

    __table_args__ = (
        Index("idx_queue_event_time", "event_id", "timestamp"),
        Index("idx_queue_event_cam_time", "event_id", "camera_id", "timestamp"),
    )
