from typing import Any, Optional
from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, UUIDMixin


class PoliceUnit(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "police_units"

    unit_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="police", nullable=False)
    zone_code: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    location: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="available", index=True, nullable=False)
    personnel: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    contact: Mapped[str] = mapped_column(String(50), default="Ch-1", nullable=False)


class MedicalUnit(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "medical_units"

    team_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="available", index=True, nullable=False)
    ambulance: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    contact: Mapped[str] = mapped_column(String(50), default="MED-1", nullable=False)


class EmergencyRoute(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "emergency_routes"

    route_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="clear", index=True, nullable=False)
    obstruction: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    estimated_time: Mapped[str] = mapped_column(String(50), default="4 min", nullable=False)
    coordinates: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
