import uuid
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.common import StandardResponse
from app.schemas.event import EventRead
from app.schemas.location import (
    ForgotAccessCodeRequest,
    LocationCreate,
    LocationEventCreate,
    LocationRead,
    LocationUpdate,
    ResetAccessCodeRequest,
    SendVerificationCodeRequest,
    VerifyAccessCodeRequest,
    VerifyAccessCodeResponse,
    VerifyCodeRequest,
)
from app.services.location_service import LocationService
from app.utils.response import success_response

router = APIRouter(prefix="/locations", tags=["Locations"])


@router.post("/send-verification-code", response_model=StandardResponse[dict])
async def send_verification_code(
    body: SendVerificationCodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Dispatches a single-use 6-digit OTP verification code to registered email.
    Includes explicit location context in email body.
    """
    service = LocationService(db)
    res = await service.send_verification_code(
        email=body.email,
        location_name=body.location_name,
        location_code=body.location_code,
        purpose=body.purpose,
    )
    return success_response(res)


@router.post("/verify-code", response_model=StandardResponse[dict])
async def verify_code(
    body: VerifyCodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Verifies that an OTP code is valid and not expired without consuming it yet (pre-check).
    """
    service = LocationService(db)
    await service.verify_code(
        email=body.email,
        code=body.code,
        purpose=body.purpose,
        consume=False,
    )
    return success_response({"message": "Verification code is valid."})


@router.get("", response_model=StandardResponse[List[LocationRead]])
async def list_locations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lists all locations with dynamic festival/event counts.
    Never exposes stored access code hashes.
    """
    service = LocationService(db)
    locations = await service.list_locations()
    return success_response(locations)


@router.post("", response_model=StandardResponse[LocationRead], status_code=status.HTTP_201_CREATED)
async def create_location(
    data: LocationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Creates a new location after verifying the email OTP code.
    Access code is hashed with bcrypt before storing.
    """
    service = LocationService(db)
    location = await service.create_location(data, created_by=current_user.username)
    return success_response(location)


@router.get("/{location_id}", response_model=StandardResponse[LocationRead])
async def get_location(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieves details for a single location.
    """
    service = LocationService(db)
    location = await service.get_location_by_id(location_id)
    return success_response(location)


@router.put("/{location_id}", response_model=StandardResponse[LocationRead])
async def update_location(
    location_id: uuid.UUID,
    data: LocationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Updates location metadata (name, city, state, status).
    """
    service = LocationService(db)
    location = await service.update_location(location_id, data, updated_by=current_user.username)
    return success_response(location)


@router.post("/{location_id}/verify-access", response_model=StandardResponse[VerifyAccessCodeResponse])
async def verify_location_access(
    location_id: uuid.UUID,
    body: VerifyAccessCodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Verifies location access code against stored bcrypt hash.
    Does not reveal or return stored code.
    """
    service = LocationService(db)
    result = await service.verify_access_code(location_id, body.access_code)
    return success_response(result)


@router.post("/{location_id}/forgot-access-code", response_model=StandardResponse[dict])
async def forgot_access_code(
    location_id: uuid.UUID,
    body: ForgotAccessCodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Requests a recovery OTP for forgotten location access code.
    Validates that the provided email matches the registered location email.
    """
    service = LocationService(db)
    res = await service.forgot_access_code(location_id, body.email)
    return success_response(res)


@router.post("/{location_id}/reset-access-code", response_model=StandardResponse[dict])
async def reset_access_code(
    location_id: uuid.UUID,
    body: ResetAccessCodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Resets location access code using verified OTP.
    Hashes new access code and invalidates previous access code.
    """
    service = LocationService(db)
    res = await service.reset_access_code(
        location_id=location_id,
        email=body.email,
        verification_code=body.verification_code,
        new_access_code=body.new_access_code,
        updated_by=current_user.username,
    )
    return success_response(res)


@router.get("/{location_id}/events", response_model=StandardResponse[List[EventRead]])
async def list_location_events(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lists all festivals/events configured for this location with start/end dates and status.
    """
    service = LocationService(db)
    events = await service.list_location_events(location_id, current_user)
    return success_response(events)


@router.post("/{location_id}/events", response_model=StandardResponse[EventRead], status_code=status.HTTP_201_CREATED)
async def create_location_event(
    location_id: uuid.UUID,
    data: LocationEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Adds a new festival/event under this location.
    Reuses existing Event architecture and operational models.
    """
    service = LocationService(db)
    event_data = await service.create_location_event(
        location_id=location_id,
        data=data,
        created_by=current_user.username,
    )
    return success_response(event_data)


from app.schemas.camera import CameraRead
from app.services.camera_service import CameraService


@router.post("/{location_id}/link-event/{event_id}", response_model=StandardResponse[dict])
async def link_existing_event(
    location_id: uuid.UUID,
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Deliberate administrative association step (Safeguard #1).
    Explicitly associates an existing event (e.g. KHB-2026) to a location.
    """
    service = LocationService(db)
    res = await service.link_existing_event(
        location_id=location_id,
        event_id=event_id,
        updated_by=current_user.username,
    )
    return success_response(res)


@router.get("/{location_id}/cameras", response_model=StandardResponse[List[CameraRead]])
async def list_location_cameras(
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lists all active cameras belonging to this location (via its events)."""
    service = CameraService(db)
    cameras, total = await service.get_cameras(location_id=location_id, page_size=200)
    return success_response(cameras)
