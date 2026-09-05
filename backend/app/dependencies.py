import uuid
from typing import AsyncGenerator, Callable, List, Optional
from fastapi import Depends, HTTPException, Header, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.security.jwt import decode_token

security = HTTPBearer(auto_error=False)

# Shared Redis pool
_redis_pool: Optional[Redis] = None

# User lookup cache (avoids 3s DB roundtrip to Supabase on every single API request)
import time
_cached_dev_user: Optional[User] = None
_cached_users: dict[str, tuple[User, float]] = {}


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_redis() -> Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=5.0,
        )
    return _redis_pool


async def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Security(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    global _cached_dev_user, _cached_users
    if not auth or not auth.credentials:
        if settings.APP_ENV == "development":
            if _cached_dev_user is not None:
                return _cached_dev_user
            stmt = select(User).where(User.is_active == True)
            res = await db.execute(stmt)
            dev_user = res.scalars().first()
            if dev_user:
                _cached_dev_user = dev_user
                return dev_user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "NOT_AUTHENTICATED", "message": "Authentication token missing"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(auth.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Token is invalid or has expired"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Token payload malformed"},
        )

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": "Invalid user ID in token"},
        )

    now_ts = time.time()
    if user_id in _cached_users:
        cached_u, exp = _cached_users[user_id]
        if now_ts < exp:
            return cached_u

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "USER_NOT_FOUND", "message": "User no longer exists"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "USER_INACTIVE", "message": "User account is disabled"},
        )

    _cached_users[user_id] = (user, now_ts + 60.0)
    return user


def require_permission(required_permission: str) -> Callable:
    """Dependency factory checking if user has specific permission."""
    async def permission_checker(current_user: User = Depends(get_current_user)) -> User:
        user_permissions = [p.code for p in current_user.role.permissions] if current_user.role else []
        
        # Super admin override
        if current_user.role and current_user.role.code == "SUPER_ADMIN":
            return current_user

        if required_permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": f"Operation requires permission '{required_permission}'",
                },
            )
        return current_user

    return permission_checker


async def verify_ai_service_key(
    x_ai_service_key: Optional[str] = Header(None, alias="X-AI-Service-Key"),
) -> bool:
    """Validates internal AI service-to-service calls."""
    if not x_ai_service_key or x_ai_service_key != settings.AI_SERVICE_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "UNAUTHORIZED_AI_SERVICE", "message": "Invalid or missing AI Service API Key"},
        )
    return True
