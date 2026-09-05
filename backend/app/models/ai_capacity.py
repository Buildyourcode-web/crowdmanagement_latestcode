"""
ai_capacity.py — SQLAlchemy 2.0 Model for AI Server Capacity Snapshots.

Stores server hardware capabilities, runtime readiness, and capacity snapshots.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import String, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, UUIDMixin


class AICapacitySnapshot(Base, UUIDMixin, TimestampMixin):
    """
    Stores point-in-time capacity estimations and hardware readiness telemetry.
    """
    __tablename__ = "ai_capacity_snapshots"

    server_hostname: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    cpu_info: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    ram_info: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    gpu_info: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    runtime_readiness: Mapped[str] = mapped_column(String(50), nullable=False)
    readiness_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    capacity_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    calculation_mode: Mapped[str] = mapped_column(String(50), default="ESTIMATED", nullable=False)
