import uuid
from typing import Any, Optional
from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDMixin


class Gate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "gates"

    gate_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=True)
    zone_code: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    
    coordinates: Mapped[Any] = mapped_column(JSON, nullable=False)
    direction: Mapped[str] = mapped_column(String(50), default="ENTRY", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="open", nullable=False)
    
    flow_rate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=150, nullable=False)

    zone: Mapped[Optional["Zone"]] = relationship("Zone", back_populates="gates")
