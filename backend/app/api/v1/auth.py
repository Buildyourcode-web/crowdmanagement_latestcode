from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshTokenRequest, TokenResponse, UserProfileResponse
from app.schemas.common import StandardResponse
from app.services.auth_service import AuthService
from app.utils.response import success_response

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=StandardResponse[TokenResponse])
async def login(
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with username and password, returns JWT tokens."""
    service = AuthService(db)
    token_data = await service.authenticate_user(credentials)
    return success_response(token_data)


@router.post("/refresh", response_model=StandardResponse[TokenResponse])
async def refresh_token(
    body: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Obtain a new access token using a valid refresh token."""
    service = AuthService(db)
    new_tokens = await service.refresh_access_token(body.refresh_token)
    return success_response(new_tokens)


@router.post("/logout", response_model=StandardResponse[dict])
async def logout(
    current_user: User = Depends(get_current_user),
):
    """Logs out current user session."""
    return success_response({"message": "Successfully logged out"})


@router.get("/me", response_model=StandardResponse[UserProfileResponse])
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns the authenticated user's profile, role, and permissions."""
    service = AuthService(db)
    profile = service.get_user_profile(current_user)
    return success_response(profile)
