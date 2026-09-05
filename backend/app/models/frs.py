import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDMixin


class FRSReferenceProfile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "frs_reference_profiles"

    reference_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    reference_code: Mapped[Optional[str]] = mapped_column(String(50), index=True, nullable=True)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="Authorized Watchlist", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE", index=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reference_image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    embedding_vector: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(50), default="buffalo_l", nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(50), default="1.0.0", nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_updated_date: Mapped[str] = mapped_column(String(50), default="10 Sep 2026", nullable=False)
    
    candidates: Mapped[List["FRSCandidate"]] = relationship("FRSCandidate", back_populates="reference_profile")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "reference_code" not in kwargs and "reference_id" in kwargs:
            self.reference_code = kwargs["reference_id"]
        if "status" not in kwargs:
            self.status = "ACTIVE"
        if "active" not in kwargs:
            self.active = True
        if "category" not in kwargs:
            self.category = "Authorized Watchlist"
        if "embedding_model" not in kwargs:
            self.embedding_model = "buffalo_l"
        if "embedding_version" not in kwargs:
            self.embedding_version = "1.0.0"
        if "last_updated_date" not in kwargs:
            self.last_updated_date = "10 Sep 2026"


class FRSCandidate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "frs_candidates"

    candidate_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=True)
    
    camera_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id"), nullable=True)
    camera_code: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    camera_name: Mapped[str] = mapped_column(String(150), nullable=False)
    
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("zones.id"), nullable=True)
    zone_code: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    
    reference_profile_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("frs_reference_profiles.id"), nullable=True
    )
    
    detected_image_path: Mapped[str] = mapped_column(String(500), nullable=False)
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    detection_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )
    date_str: Mapped[str] = mapped_column(String(50), default="14 Sep 2026", nullable=False)
    time_str: Mapped[str] = mapped_column(String(50), default="19:42:18", nullable=False)
    
    status: Mapped[str] = mapped_column(String(50), default="REVIEW_REQUIRED", index=True, nullable=False)
    review_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="HIGH", nullable=False)
    image_quality: Mapped[str] = mapped_column(String(50), default="High (94%)", nullable=False)
    
    timeline: Mapped[Any] = mapped_column(JSON, default=list, nullable=False)
    officer_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    model_version: Mapped[str] = mapped_column(String(50), default="buffalo_l", nullable=False)
    embedding_model_version: Mapped[str] = mapped_column(String(50), default="insightface-r50", nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    reference_profile: Mapped[Optional[FRSReferenceProfile]] = relationship(
        "FRSReferenceProfile", back_populates="candidates", lazy="selectin"
    )
    reviews: Mapped[List["FRSReview"]] = relationship("FRSReview", back_populates="candidate")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if "status" not in kwargs:
            self.status = "REVIEW_REQUIRED"
        if "review_required" not in kwargs:
            self.review_required = True
        if "priority" not in kwargs:
            self.priority = "HIGH"
        if "image_quality" not in kwargs:
            self.image_quality = "High (94%)"
        if "timeline" not in kwargs:
            self.timeline = []
        if "model_version" not in kwargs:
            self.model_version = "buffalo_l"
        if "embedding_model_version" not in kwargs:
            self.embedding_model_version = "insightface-r50"
        if "date_str" not in kwargs:
            self.date_str = "14 Sep 2026"
        if "time_str" not in kwargs:
            self.time_str = "19:42:18"
        if "detected_at" not in kwargs:
            self.detected_at = datetime.now(timezone.utc)


class FRSReview(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "frs_reviews"

    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("frs_candidates.id"), nullable=False)
    reviewer_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewer_name: Mapped[str] = mapped_column(String(100), default="Cmd Officer Sharma", nullable=False)
    
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    candidate: Mapped[FRSCandidate] = relationship("FRSCandidate", back_populates="reviews")


class FRSAuditLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "frs_audit_logs"

    audit_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    candidate_code: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    reference_id: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    officer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
