from typing import Any, List, Optional
from pydantic import BaseModel, Field
from app.schemas.common import BaseSchema


class PoliceUnitRead(BaseSchema):
    id: str = Field(..., example="UNIT-01")
    name: str
    type: str = "police"
    zone: str = Field(..., alias="zone_code")
    location: str
    status: str = Field(default="available")
    personnel: int = 4
    contact: str = "Ch-1"

    class Config:
        populate_by_name = True
        from_attributes = True


class MedicalTeamRead(BaseSchema):
    id: str = Field(..., example="MED-01")
    name: str
    location: str
    status: str = Field(default="available")
    ambulance: bool = True
    contact: str = "MED-1"

    class Config:
        populate_by_name = True
        from_attributes = True


class EmergencyRouteRead(BaseSchema):
    id: str = Field(..., example="ROUTE-01")
    name: str
    description: str
    status: str = Field(default="clear")
    obstruction: Optional[str] = None
    estimated_time: str = Field(default="4 min", alias="estimatedTime")
    coordinates: List[List[float]] = Field(default_factory=list)

    class Config:
        populate_by_name = True
        from_attributes = True


class UnitStatusUpdate(BaseModel):
    status: str = Field(..., example="responding")
    location: Optional[str] = None
