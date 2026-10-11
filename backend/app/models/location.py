import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.event import Event


class Location(Base, UUIDMixin, TimestampMixin):
    """
    Physical administrative location entity.
    Represents a designated city/jurisdiction location (e.g. Khairatabad)
    that hosts one or more religious or cultural festivals/events over time.
    """
    __tablename__ = "locations"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    access_code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE", index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    events: Mapped[List["Event"]] = relationship(
        "Event",
        back_populates="location_ref",
        lazy="noload",
    )


class LocationVerification(Base, UUIDMixin, TimestampMixin):
    """
    Temporary single-use OTP verification records for location creation
    and forgot-access-code recovery.
    """
    __tablename__ = "location_verifications"

    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    location_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)  # CREATE_LOCATION, RESET_ACCESS_CODE
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
