import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, UUIDMixin


class AuditLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "audit_logs"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(100), default="SYSTEM", nullable=False)
    action: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    resource_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[Any] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("idx_audit_logs_resource", "resource_type", "resource_id"),
    )
