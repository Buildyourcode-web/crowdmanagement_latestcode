from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.common import BaseSchema


class MissingPersonCaseRead(BaseSchema):
    id: str = Field(..., example="MP-2026-0042")
    name: str = Field(..., example="Demo Person 042")
    age: int = Field(..., example=9)
    gender: str = Field(..., example="Male")
    reported_at: datetime = Field(..., alias="reportedAt")
    last_seen_time: datetime = Field(..., alias="lastSeenTime")
    last_known_zone: str = Field(..., alias="lastKnownZone", example="ZONE-A")
    last_seen_camera: Optional[str] = Field(None, alias="lastSeenCamera", example="CAM-KHB-002")
    description: str
    status: str = Field(default="searching")
    candidate_matches: List[str] = Field(default_factory=list, alias="candidateMatches")
    notes: Optional[str] = None
    reference_image: Optional[str] = Field(None, alias="referenceImage")

    class Config:
        populate_by_name = True
        from_attributes = True


class MissingPersonCreate(BaseModel):
    case_code: str = Field(..., example="MP-2026-0055")
    name: str
    age: int
    gender: str
    description: str
    last_known_zone_code: str = "ZONE-A"
    last_seen_camera_code: Optional[str] = None
    notes: Optional[str] = None
    reference_image_path: Optional[str] = None


class MissingPersonUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    last_known_zone_code: Optional[str] = None
    candidate_matches: Optional[List[str]] = None
