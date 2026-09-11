import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from app.schemas.common import BaseSchema


class EventBase(BaseSchema):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=150)
    description: Optional[str] = Field(None, max_length=500)
    year: int
    start_date: datetime
    end_date: datetime
    status: str = Field(default="ACTIVE", max_length=50)
    is_active: bool = True
    timezone: str = Field(default="Asia/Kolkata", max_length=50)
    location: Optional[str] = Field(None, max_length=300)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(default="India", max_length=100)
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    year: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None
    timezone: Optional[str] = None
    location: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class EventRead(EventBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    
    # Aggregated metrics for display
    site_count: Optional[int] = 0
    camera_count: Optional[int] = 0
    active_alert_count: Optional[int] = 0
    current_crowd: Optional[int] = 0
    user_access_role: Optional[str] = None


class EventSummary(BaseSchema):
    id: uuid.UUID
    code: str
    name: str
    status: str
    is_active: bool
    year: int
    start_date: datetime
    end_date: datetime
    location: Optional[str] = None
    city: Optional[str] = None
    sites_count: int = 0
    cameras_count: int = 0
    total_visitors_today: int = 0
    current_occupancy: int = 0