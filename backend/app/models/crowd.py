import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, UUIDMixin


class CrowdSnapshot(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "crowd_snapshots"

    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=True)
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=True)
    zone_code: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    camera_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=True)
    camera_code: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    profile_id: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )
    
    people_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    density: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    inflow_rate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outflow_rate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    occupancy_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(50), default="LOW", index=True, nullable=False)
    risk_score: Mapped[Optional[float]] = mapped_column(Float, default=0.0, nullable=True)

    __table_args__ = (
        Index("idx_crowd_snapshots_lookup", "zone_code", "timestamp"),
        Index("idx_crowd_snapshots_cam_time", "camera_code", "timestamp"),
    )
