"""
app.schemas.camera_roi — Pydantic DTOs for Visual ROI & Counting-Line Configurations.

All coordinates are normalized (0.0 to 1.0) for resolution independence.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ROITypeEnum(str, Enum):
    CROWD_ROI = "CROWD_ROI"
    QUEUE_ROI = "QUEUE_ROI"
    COUNTING_LINE = "COUNTING_LINE"
    ENTRY_LINE = "ENTRY_LINE"
    EXIT_LINE = "EXIT_LINE"
    EXCLUSION_ZONE = "EXCLUSION_ZONE"
    DIRECTION_LINE = "DIRECTION_LINE"
    ZONE_BOUNDARY = "ZONE_BOUNDARY"


class Point2D(BaseModel):
    x: float = Field(..., ge=0.0, le=1.0, description="Normalized X coordinate (0.0 to 1.0)")
    y: float = Field(..., ge=0.0, le=1.0, description="Normalized Y coordinate (0.0 to 1.0)")


class PolygonGeometry(BaseModel):
    points: List[Point2D] = Field(..., min_length=3, description="List of normalized polygon vertices (min 3 points)")


class LineGeometry(BaseModel):
    start: Point2D = Field(..., description="Normalized starting point")
    end: Point2D = Field(..., description="Normalized ending point")
    direction: Optional[str] = Field("BOTH", description="Allowed directions: IN, OUT, BOTH")


class CameraROICreate(BaseModel):
    profile_id: str = Field(..., description="AI Profile ID (e.g. CROWD_STANDARD, QUEUE_STANDARD)")
    roi_type: str = Field(..., description="ROI Type (CROWD_ROI, QUEUE_ROI, ENTRY_LINE, etc.)")
    name: Optional[str] = Field("Counting Line", max_length=150, description="Human-readable label for this geometry")
    geometry_json: Dict[str, Any] = Field(..., description="Normalized geometry definition (points or start/end)")
    normalized: bool = Field(True, description="Always true for resolution-independent coordinates")
    enabled: bool = Field(True, description="Whether this geometry is active")


class CameraROIUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    geometry_json: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


class CameraROIRead(BaseModel):
    id: str
    camera_id: str
    camera_code: str
    profile_id: str
    roi_type: str
    name: str
    geometry_json: Dict[str, Any]
    normalized: bool
    enabled: bool
    version: int
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProfileReadinessItem(BaseModel):
    status: str = Field(..., description="NOT_CONFIGURED, PARTIALLY_CONFIGURED, READY, INVALID")
    status_label: str
    is_ready: bool
    missing_requirements: List[str] = Field(default_factory=list)
    message: str


class CameraROIConfigSummary(BaseModel):
    camera_id: str
    camera_code: str
    camera_name: str
    camera_type: str
    zone_code: Optional[str] = None
    zone_name: Optional[str] = None
    stream_status: str
    stream_verified: bool
    configurations: List[CameraROIRead] = Field(default_factory=list)
    readiness_by_profile: Dict[str, ProfileReadinessItem] = Field(default_factory=dict)


class CameraROIValidationRequest(BaseModel):
    profile_id: str
    roi_type: str
    geometry_json: Dict[str, Any]


class CameraROIValidationResponse(BaseModel):
    valid: bool
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
