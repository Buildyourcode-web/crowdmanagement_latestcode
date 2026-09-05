import uuid
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, Field
from app.schemas.common import BaseSchema


class FRSCameraSummary(BaseModel):
    id: str
    name: str


class FRSZoneSummary(BaseModel):
    id: str
    name: str


class FRSReferenceProfileSummary(BaseModel):
    id: str
    display_name: str
    image_url: str


class FRSDashboardKPIs(BaseModel):
    cameras_online: int = Field(..., alias="camerasOnline", example=15)
    cameras_total: int = Field(..., alias="camerasTotal", example=16)
    detections_today: int = Field(..., alias="detectionsToday", example=1842)
    possible_matches: int = Field(..., alias="possibleMatches", example=7)
    pending_review: int = Field(..., alias="pendingReview", example=3)
    dismissed: int = Field(..., example=4)
    active_cases: int = Field(..., alias="activeCases", example=2)
    processing_fps: int = Field(default=24, alias="processingFps")
    avg_latency_ms: int = Field(default=38, alias="avgLatencyMs")

    class Config:
        populate_by_name = True


class FRSReferenceProfileRead(BaseSchema):
    id: str = Field(..., example="WL-00281")
    reference_id: str
    display_name: str = Field(..., alias="referenceName")
    category: str = Field(default="Authorized Watchlist")
    status: str = Field(default="ACTIVE", alias="referenceStatus")
    reference_image_path: str = Field(..., alias="referenceImage")
    last_updated: str = Field(default="10 Sep 2026", alias="lastUpdated")

    class Config:
        populate_by_name = True
        from_attributes = True


class FRSCandidateRead(BaseSchema):
    id: str = Field(..., example="FRS-EVT-00042")
    detected_image: str = Field(..., alias="detectedImage")
    reference_image: str = Field(..., alias="referenceImage")
    reference_name: str = Field(..., alias="referenceName")
    reference_id: str = Field(..., alias="referenceId")
    category: str = Field(default="Authorized Watchlist")
    reference_status: str = Field(default="ACTIVE", alias="referenceStatus")
    last_updated: str = Field(default="10 Sep 2026", alias="lastUpdated")
    match_score: float = Field(..., alias="matchScore", example=94.2)
    detection_confidence: Optional[float] = Field(default=None, alias="detectionConfidence")
    quality_score: Optional[float] = Field(default=None, alias="qualityScore")
    camera_id: str = Field(..., alias="cameraId", example="FRS-KHB-007")
    camera_name: str = Field(..., alias="cameraName")
    location: str = Field(..., example="Khairatabad Main Entry")
    zone: str = Field(..., example="ZONE-A")
    timestamp: datetime
    date_str: str = Field(default="14 Sep 2026", alias="dateStr")
    time_str: str = Field(default="19:42:18", alias="timeStr")
    status: str = Field(default="REVIEW_REQUIRED")
    review_required: bool = Field(default=True, alias="reviewRequired")
    priority: str = Field(default="HIGH")
    image_quality: str = Field(default="High (94%)", alias="imageQuality")
    timeline: List[dict] = Field(default_factory=list)
    officer_notes: Optional[str] = Field(None, alias="officerNotes")
    review_reason: Optional[str] = Field(None, alias="reviewReason")
    reviewed_by: Optional[str] = Field(None, alias="reviewedBy")
    reviewed_at: Optional[str] = Field(None, alias="reviewedAt")
    model_version: str = Field(default="buffalo_l", alias="modelVersion")
    embedding_model_version: str = Field(default="insightface-r50", alias="embeddingModelVersion")

    class Config:
        populate_by_name = True
        from_attributes = True


class FRSReviewRequest(BaseModel):
    decision: str = Field(
        ...,
        example="CONFIRMED_BY_REVIEWER",
        description="CONFIRMED_BY_REVIEWER, REJECTED_BY_REVIEWER, UNRESOLVED, POSSIBLE_MATCH, NOT_A_MATCH, NEEDS_MORE_REVIEW, DISMISSED",
    )
    notes: Optional[str] = Field(default="", description="Investigative notes by review officer")
    reason: Optional[str] = Field(default=None, description="Detailed operational review rationale")


class FRSReviewResponse(BaseModel):
    candidate_id: str
    status: str
    review_required: bool
    reviewed_by: str
    reviewed_at: str
    notes: Optional[str] = None
    decision: Optional[str] = None


class FRSReferencePersonCreate(BaseModel):
    display_name: str = Field(..., example="Suspect A", description="Full name or alias of reference person")
    reference_id: Optional[str] = Field(None, example="REF-00123", description="Custom reference code")
    category: str = Field(default="Authorized Watchlist", example="Authorized Watchlist")
    reference_image_b64: Optional[str] = Field(None, description="Base64 encoded JPEG/PNG image")


class FRSReferencePersonUpdate(BaseModel):
    display_name: Optional[str] = None
    category: Optional[str] = None
    active: Optional[bool] = None


class FRSConfigRead(BaseModel):
    detection_confidence_threshold: float = 0.60
    min_sharpness_score: float = 50.0
    min_face_width: int = 60
    min_face_height: int = 60
    match_threshold: float = 0.75
    top_k: int = 3
    duplicate_suppression_seconds: int = 60
    retention_days: int = 30
    detector_model: str = "buffalo_l"
    embedding_model: str = "insightface-r50"


class FRSConfigUpdate(BaseModel):
    detection_confidence_threshold: Optional[float] = None
    min_sharpness_score: Optional[float] = None
    min_face_width: Optional[int] = None
    min_face_height: Optional[int] = None
    match_threshold: Optional[float] = None
    top_k: Optional[int] = None
    duplicate_suppression_seconds: Optional[int] = None
    retention_days: Optional[int] = None


class FRSRetentionCleanupResponse(BaseModel):
    deleted_candidates_count: int
    retention_days: int
    cutoff_timestamp: str
    status: str = "SUCCESS"
