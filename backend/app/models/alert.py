import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, UUIDMixin


class Alert(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "alerts"

    alert_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=True)
    
    type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    type_label: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=True)
    zone_code: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    
    camera_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=True)
    camera_code: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    
    status: Mapped[str] = mapped_column(String(50), default="active", index=True, nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    assigned_to: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("idx_alerts_severity_status", "severity", "status"),
    )
