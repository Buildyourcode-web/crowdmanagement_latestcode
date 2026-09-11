import uuid
from typing import List, Optional
from sqlalchemy import Boolean, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDMixin


class Site(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sites"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    site_code: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    site_name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE", index=True, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    event: Mapped["Event"] = relationship("Event", back_populates="sites")
    cameras: Mapped[List["Camera"]] = relationship("Camera", back_populates="site", lazy="noload")

    __table_args__ = (
        UniqueConstraint("event_id", "site_code", name="uq_site_event_code"),
    )
