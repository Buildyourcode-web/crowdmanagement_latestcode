import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from app.schemas.common import BaseSchema


class SiteBase(BaseSchema):
    site_code: str = Field(..., max_length=50)
    site_name: str = Field(..., max_length=150)
    description: Optional[str] = Field(None, max_length=500)
    location: Optional[str] = Field(None, max_length=300)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: bool = True
    status: str = Field(default="ACTIVE", max_length=50)


class SiteCreate(SiteBase):
    event_id: Optional[uuid.UUID] = None  # Inferred from URL or header if omitted


class SiteUpdate(BaseModel):
    site_name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: Optional[bool] = None
    status: Optional[str] = None


class SiteRead(SiteBase):
    id: uuid.UUID
    event_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    
    # Aggregated metrics
    camera_count: Optional[int] = 0
    online_camera_count: Optional[int] = 0
    active_alert_count: Optional[int] = 0
    current_people: Optional[int] = 0