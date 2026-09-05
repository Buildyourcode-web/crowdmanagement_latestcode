import uuid
from typing import Any, List, Optional
from pydantic import BaseModel, Field
from app.schemas.common import BaseSchema


class ZonePrediction(BaseModel):
    critical_in_minutes: Optional[int] = None
    next_level: Optional[str] = None
    next_level_in_minutes: Optional[int] = None


class ZoneRead(BaseSchema):
    id: str = Field(..., example="ZONE-A")
    zone_code: str
    name: str
    label: str
    description: Optional[str] = None
    people: int = Field(..., alias="current_people")
    capacity: int
    occupancy_pct: Optional[float] = None
    density: float
    density_label: str
    risk: str = Field(..., alias="risk_level")
    coordinates: List[List[float]]
    center: Optional[List[float]] = None
    cameras: List[str] = Field(default_factory=list)
    gates: List[str] = Field(default_factory=list)
    color: str
    inflow: int = 0
    outflow: int = 0
    prediction: Optional[ZonePrediction] = None

    class Config:
        populate_by_name = True
        from_attributes = True


class ZoneCreate(BaseModel):
    zone_code: str = Field(..., example="ZONE-M")
    name: str = Field(..., example="Zone M")
    label: str = Field(..., example="South Parking Overflow")
    description: Optional[str] = None
    capacity: int = Field(default=5000)
    coordinates: List[List[float]]
    center: Optional[List[float]] = None
    color: str = "#3fb950"


class ZoneUpdate(BaseModel):
    name: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    capacity: Optional[int] = None
    current_people: Optional[int] = None
    risk_level: Optional[str] = None
    color: Optional[str] = None
