from datetime import datetime, timezone
from typing import Dict, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse, UserProfileResponse
from app.security.jwt import create_access_token, create_refresh_token, decode_token
from app.security.password import verify_password


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

    async def authenticate_user(self, credentials: LoginRequest) -> TokenResponse:
        user = await self.user_repo.get_by_username_or_email(credentials.username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_CREDENTIALS", "message": "Invalid username or password"},
            )

        if not verify_password(credentials.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_CREDENTIALS", "message": "Invalid username or password"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "ACCOUNT_DISABLED", "message": "User account is deactivated"},
            )

        # Update last login
        user.last_login = datetime.now(timezone.utc)
        await self.user_repo.update(user)

        role_code = user.role.code if user.role else "VIEWER"
        permissions = [p.code for p in user.role.permissions] if user.role else []

        access_token = create_access_token(
            subject=str(user.id),
            role=role_code,
            permissions=permissions,
        )
        refresh_token = create_refresh_token(subject=str(user.id))

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def refresh_access_token(self, refresh_token_str: str) -> TokenResponse:
        payload = decode_token(refresh_token_str)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_REFRESH_TOKEN", "message": "Invalid or expired refresh token"},
            )

        user_id = payload.get("sub")
        import uuid
        user = await self.user_repo.get_by_id(uuid.UUID(user_id))
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "USER_INACTIVE", "message": "User is no longer active"},
            )

        role_code = user.role.code if user.role else "VIEWER"
        permissions = [p.code for p in user.role.permissions] if user.role else []

        new_access_token = create_access_token(
            subject=str(user.id),
            role=role_code,
            permissions=permissions,
        )
        new_refresh_token = create_refresh_token(subject=str(user.id))

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    def get_user_profile(self, user: User) -> UserProfileResponse:
        role_code = user.role.code if user.role else "VIEWER"
        permissions = [p.code for p in user.role.permissions] if user.role else []
        
        # Calculate initials from full name
        name_parts = user.full_name.split()
        initials = "".join([part[0].upper() for part in name_parts[:2]]) if name_parts else "BYC"

        return UserProfileResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            role=role_code,
            permissions=permissions,
            initials=initials,
            is_active=user.is_active,
            last_login=user.last_login,
        )
