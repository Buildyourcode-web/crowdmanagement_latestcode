import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, UUIDMixin


class MissingPersonCase(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "missing_person_cases"

    case_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=True)
    
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    reference_image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_seen_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_known_zone_code: Mapped[str] = mapped_column(String(50), default="ZONE-A", nullable=False)
    last_seen_camera_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    status: Mapped[str] = mapped_column(String(50), default="searching", index=True, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="HIGH", nullable=False)
    
    candidate_matches: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
