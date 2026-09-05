import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field
from app.schemas.common import BaseSchema


class LoginRequest(BaseModel):
    username: str = Field(..., example="admin", description="Username or email")
    password: str = Field(..., example="admin123", description="Plain text password")


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Valid JWT refresh token")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RoleSummary(BaseSchema):
    id: uuid.UUID
    code: str
    name: str
    permissions: List[str] = Field(default_factory=list)


class UserProfileResponse(BaseSchema):
    id: uuid.UUID
    username: str
    email: str
    full_name: str
    role: str
    permissions: List[str]
    initials: str
    is_active: bool
    last_login: Optional[datetime] = None
