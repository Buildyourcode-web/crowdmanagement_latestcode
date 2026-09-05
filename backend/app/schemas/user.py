import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field
from app.schemas.common import BaseSchema


class PermissionRead(BaseSchema):
    id: uuid.UUID
    code: str
    name: str
    description: Optional[str] = None


class RoleRead(BaseSchema):
    id: uuid.UUID
    code: str
    name: str
    description: Optional[str] = None
    permissions: List[PermissionRead] = Field(default_factory=list)


class UserRead(BaseSchema):
    id: uuid.UUID
    username: str
    email: str
    full_name: str
    role_id: uuid.UUID
    role_code: str
    role_name: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: str = Field(..., min_length=2, max_length=100)
    role_code: str = Field(default="CONTROL_ROOM")


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role_code: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None
