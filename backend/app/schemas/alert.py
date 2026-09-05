import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field
from app.schemas.common import BaseSchema


class AlertRead(BaseSchema):
    id: str = Field(..., example="ALT-0001")
    type: str = Field(..., example="crowd_density")
    type_label: str = Field(..., alias="typeLabel", example="CRITICAL CROWD DENSITY")
    severity: str = Field(..., example="critical")
    title: str = Field(..., example="Zone A at 96% Capacity")
    message: str = Field(..., example="North Gate 1 approach experiencing acute congestion.")
    zone: Optional[str] = Field(None, example="ZONE-A")
    camera: Optional[str] = Field(None, example="CAM-KHB-001")
    status: str = Field(default="active")
    acknowledged: bool = Field(default=False)
    timestamp: datetime = Field(..., alias="detected_at")
    assigned_to: Optional[str] = None
    metadata: Optional[Any] = Field(default_factory=dict, alias="metadata_json")

    class Config:
        populate_by_name = True
        from_attributes = True


class AlertCreate(BaseModel):
    alert_code: str = Field(..., example="ALT-0025")
    type: str = "crowd_density"
    type_label: str = "CROWD SURGE"
    severity: str = "high"
    title: str
    message: str
    zone_code: Optional[str] = None
    camera_code: Optional[str] = None
    metadata_json: Optional[dict] = None


class AlertActionRequest(BaseModel):
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


class AlertStatsResponse(BaseModel):
    total: int
    critical: int
    high: int
    medium: int
    low: int
    active: int
