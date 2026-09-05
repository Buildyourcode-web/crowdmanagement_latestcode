import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDMixin


class Incident(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "incidents"

    incident_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=True)
    
    type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    type_label: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=True)
    zone_code: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    cameras: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    
    status: Mapped[str] = mapped_column(String(50), default="detected", index=True, nullable=False)
    
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    responding_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    assigned_team: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    assigned_team_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    timeline: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    related_alerts: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)

    notes: Mapped[List["IncidentNote"]] = relationship("IncidentNote", back_populates="incident", lazy="selectin")

    __table_args__ = (
        Index("idx_incidents_status_severity", "status", "severity"),
    )


class IncidentNote(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "incident_notes"

    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False)
    author: Mapped[str] = mapped_column(String(100), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    note_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    incident: Mapped[Incident] = relationship("Incident", back_populates="notes")
