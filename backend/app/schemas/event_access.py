import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from app.schemas.common import BaseSchema


class UserEventAccessCreate(BaseModel):
    user_id: uuid.UUID
    event_id: uuid.UUID
    access_role: str = Field(default="VIEWER", max_length=50)


class UserEventAccessUpdate(BaseModel):
    access_role: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None


class UserEventAccessRead(BaseSchema):
    id: uuid.UUID
    user_id: uuid.UUID
    event_id: uuid.UUID
    access_role: str
    is_active: bool
    granted_by: Optional[str] = None
    created_at: datetime
    
    # User details
    username: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None


class UserSiteAccessCreate(BaseModel):
    user_id: uuid.UUID
    event_id: uuid.UUID
    site_id: uuid.UUID


class UserSiteAccessRead(BaseSchema):
    id: uuid.UUID
    user_id: uuid.UUID
    event_id: uuid.UUID
    site_id: uuid.UUID
    is_active: bool
    granted_by: Optional[str] = None
    created_at: datetime
    
    # Site details
    site_code: Optional[str] = None
    site_name: Optional[str] = None