import uuid
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.common import BaseSchema


class IncidentNoteRead(BaseSchema):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: uuid.UUID
    author: str
    text: str
    time: datetime = Field(..., alias="note_time")


class IncidentNoteCreate(BaseModel):
    author: str = Field(default="CMD-CTR")
    text: str = Field(..., min_length=2)


class IncidentRead(BaseSchema):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str = Field(..., examples=["INC-2026-0001"])
    type: str = Field(..., examples=["crowd_surge"])
    type_label: str = Field(..., alias="typeLabel", examples=["Crowd Surge"])
    severity: str = Field(..., examples=["critical"])
    status: str = Field(..., examples=["responding"])
    zone: Optional[str] = Field(None, examples=["ZONE-A"])
    location: str
    cameras: List[str] = Field(default_factory=list)
    
    detected_at: datetime = Field(..., alias="detectedAt")
    acknowledged_at: Optional[datetime] = Field(None, alias="acknowledgedAt")
    assigned_at: Optional[datetime] = Field(None, alias="assignedAt")
    responding_at: Optional[datetime] = Field(None, alias="respondingAt")
    resolved_at: Optional[datetime] = Field(None, alias="resolvedAt")
    
    assigned_team: Optional[str] = Field(None, alias="assignedTeam")
    assigned_team_label: Optional[str] = Field(None, alias="assignedTeamLabel")
    description: str
    
    timeline: List[str] = Field(default_factory=list)
    related_alerts: List[str] = Field(default_factory=list, alias="relatedAlerts")
    notes: List[IncidentNoteRead] = Field(default_factory=list)


class IncidentCreate(BaseModel):
    incident_code: str = Field(..., examples=["INC-2026-0010"])
    type: str = "crowd_surge"
    type_label: str = "Crowd Surge"
    severity: str = "high"
    title: str
    description: str
    location: str
    zone_code: Optional[str] = "ZONE-A"
    cameras: List[str] = Field(default_factory=list)
    assigned_team: Optional[str] = None
    assigned_team_label: Optional[str] = None


class IncidentActionRequest(BaseModel):
    assigned_team: Optional[str] = None
    assigned_team_label: Optional[str] = None
    notes: Optional[str] = None
