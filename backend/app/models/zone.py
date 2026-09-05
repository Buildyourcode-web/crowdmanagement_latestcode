import uuid
from typing import Any, List, Optional
from sqlalchemy import Float, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDMixin


class Zone(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "zones"

    zone_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=True)
    
    # Coordinates stored as GeoJSON polygon / coordinate array
    coordinates: Mapped[Any] = mapped_column(JSON, nullable=False)
    center: Mapped[Any] = mapped_column(JSON, nullable=True)
    
    capacity: Mapped[int] = mapped_column(Integer, default=5000, nullable=False)
    current_people: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    density: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    density_label: Mapped[str] = mapped_column(String(20), default="LOW", nullable=False)
    
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE", index=True, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(50), default="LOW", index=True, nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="#3fb950", nullable=False)

    cameras: Mapped[List["Camera"]] = relationship("Camera", back_populates="zone", lazy="selectin")
    gates: Mapped[List["Gate"]] = relationship("Gate", back_populates="zone", lazy="selectin")
