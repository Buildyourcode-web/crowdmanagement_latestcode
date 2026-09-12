import uuid
from typing import Optional
from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDMixin


class UserEventAccess(Base, UUIDMixin, TimestampMixin):
    """Maps users to events they have access to, with a specific access role."""
    __tablename__ = "user_event_access"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Role within this event context: EVENT_MANAGER, COMMANDER, OPERATOR, VIEWER, FRS_OPERATOR
    access_role: Mapped[str] = mapped_column(String(50), default="VIEWER", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    granted_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="event_accesses", lazy="noload")
    event: Mapped["Event"] = relationship("Event", lazy="noload")

    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_user_event_access"),
    )


class UserSiteAccess(Base, UUIDMixin, TimestampMixin):
    """Maps users to specific sites within an event they have access to."""
    __tablename__ = "user_site_access"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    granted_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="site_accesses", lazy="noload")
    site: Mapped["Site"] = relationship("Site", lazy="noload")

    __table_args__ = (
        UniqueConstraint("user_id", "site_id", name="uq_user_site_access"),
    )
