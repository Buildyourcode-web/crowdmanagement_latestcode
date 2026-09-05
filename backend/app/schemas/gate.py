import uuid
from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.common import BaseSchema


class GateRead(BaseSchema):
    id: str = Field(..., example="GATE-01")
    gate_code: str
    name: str
    label: str
    zone: str = Field(..., alias="zone_code")
    coordinates: List[float] = Field(..., example=[78.4720, 17.4295])
    direction: str = Field(default="ENTRY")
    status: str = Field(default="open")
    flow_rate: int = Field(default=0)
    capacity: int = Field(default=200)

    class Config:
        populate_by_name = True
        from_attributes = True


class GateCreate(BaseModel):
    gate_code: str
    name: str
    label: str
    zone_code: str
    coordinates: List[float]
    direction: str = "ENTRY"
    status: str = "open"
    capacity: int = 200
