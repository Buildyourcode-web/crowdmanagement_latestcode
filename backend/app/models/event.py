from datetime import datetime
from typing import List, Optional
from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDMixin


# Event lifecycle: DRAFT → SCHEDULED → LIVE → PAUSED → COMPLETED → ARCHIVED
# "ACTIVE" kept for backward compatibility (= LIVE)
EVENT_STATUS_CHOICES = ("DRAFT", "SCHEDULED", "ACTIVE", "LIVE", "PAUSED", "COMPLETED", "ARCHIVED")


class Event(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "events"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Lifecycle status — expanded from single "ACTIVE"
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE", index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata", nullable=False)

    # Physical location
    location: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), default="India", nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Audit
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    sites: Mapped[List["Site"]] = relationship("Site", back_populates="event", cascade="all, delete-orphan", lazy="noload")
