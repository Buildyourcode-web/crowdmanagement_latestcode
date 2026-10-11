import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import BaseSchema


class SendVerificationCodeRequest(BaseModel):
    email: EmailStr
    location_name: str = Field(..., min_length=2, max_length=150)
    location_code: Optional[str] = Field(None, min_length=2, max_length=50)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    purpose: str = Field(default="CREATE_LOCATION", description="CREATE_LOCATION or RESET_ACCESS_CODE")


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=4, max_length=10)
    purpose: str = Field(default="CREATE_LOCATION")
    location_code: Optional[str] = None


class LocationCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    code: str = Field(..., min_length=2, max_length=50)
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    access_code: str = Field(..., min_length=4, max_length=100, description="Plaintext access code to be hashed")
    verification_code: str = Field(..., min_length=4, max_length=10)


class LocationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    city: Optional[str] = Field(None, min_length=2, max_length=100)
    state: Optional[str] = Field(None, min_length=2, max_length=100)
    status: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None


class LocationRead(BaseSchema):
    id: uuid.UUID
    code: str
    name: str
    city: str
    state: str
    email: str
    status: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    festival_count: int = 0


class VerifyAccessCodeRequest(BaseModel):
    access_code: str = Field(..., min_length=1, max_length=100)


class VerifyAccessCodeResponse(BaseModel):
    verified: bool = True
    location_id: uuid.UUID
    location_name: str
    location_code: str
    message: str = "Access code verified successfully"


class ForgotAccessCodeRequest(BaseModel):
    email: EmailStr


class ResetAccessCodeRequest(BaseModel):
    email: EmailStr
    verification_code: str = Field(..., min_length=4, max_length=10)
    new_access_code: str = Field(..., min_length=4, max_length=100)


class LocationEventCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=2, max_length=150)
    year: int
    start_date: datetime
    end_date: datetime
    description: Optional[str] = Field(None, max_length=500)
    status: str = Field(default="ACTIVE", max_length=50)
    is_active: bool = True
    timezone: str = Field(default="Asia/Kolkata", max_length=50)
    location: Optional[str] = Field(None, max_length=300)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(default="India", max_length=100)
