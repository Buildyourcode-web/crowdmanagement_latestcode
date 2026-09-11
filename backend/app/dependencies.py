import uuid
from typing import Any, AsyncGenerator, Callable, List, Optional
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
_cached_default_event: Optional[Any] = None
_cached_default_event_exp: float = 0.0


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


from dataclasses import dataclass
from app.models.event import Event
from app.models.site import Site
from app.models.user_access import UserEventAccess, UserSiteAccess
from app.security.permissions import Permissions


@dataclass
class EventContext:
    event: Event
    event_id: uuid.UUID
    event_code: str
    access_role: str
    is_global_admin: bool
    allowed_site_ids: Optional[List[uuid.UUID]] = None  # None means all sites in this event are allowed
    has_frs_access: bool = False


async def get_event_context(
    x_event_id: Optional[str] = Header(None, alias="X-Event-ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> EventContext:
    """
    Validates event context and RBAC permissions.
    - SUPER_ADMIN: has access to all events and all sites.
    - Other users: must have explicit UserEventAccess record for the event.
    - If X-Event-ID is omitted:
        - If user has exactly one accessible event, defaults to that event.
        - If user has multiple events, raises 400 Bad Request requiring explicit selection.
    """
    is_super = bool(current_user.role and current_user.role.code == "SUPER_ADMIN")
    user_perms = [p.code for p in current_user.role.permissions] if current_user.role else []
    has_frs = is_super or any(
        p in user_perms for p in [Permissions.FRS_READ, Permissions.FRS_REVIEW, Permissions.FRS_MANAGE]
    )

    if is_super:
        if x_event_id:
            try:
                target_uuid = uuid.UUID(x_event_id)
                stmt = select(Event).where((Event.id == target_uuid) | (Event.code == x_event_id))
            except ValueError:
                stmt = select(Event).where(Event.code == x_event_id)
            res = await db.execute(stmt)
            target_event = res.scalars().first()
            if not target_event:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "EVENT_NOT_FOUND", "message": f"Event '{x_event_id}' not found"},
                )
        else:
            global _cached_default_event, _cached_default_event_exp
            now_ts = time.time()
            if _cached_default_event is not None and now_ts < _cached_default_event_exp:
                target_event = _cached_default_event
            else:
                # Default to primary Khairatabad Ganesh event first, then fallback to active/latest
                stmt = select(Event).where((Event.code == "KHB-2026") | (Event.name.ilike("%Khairatabad%"))).limit(1)
                res = await db.execute(stmt)
                target_event = res.scalars().first()
                if not target_event:
                    stmt = select(Event).where(Event.status.in_(["ACTIVE", "LIVE"])).order_by(Event.created_at.desc())
                    res = await db.execute(stmt)
                    target_event = res.scalars().first()
                if not target_event:
                    stmt = select(Event).order_by(Event.created_at.desc())
                    res = await db.execute(stmt)
                    target_event = res.scalars().first()
                if target_event:
                    _cached_default_event = target_event
                    _cached_default_event_exp = now_ts + 120.0

        if not target_event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NO_EVENTS_EXIST", "message": "No events configured in the system"},
            )

        return EventContext(
            event=target_event,
            event_id=target_event.id,
            event_code=target_event.code,
            access_role="SUPER_ADMIN",
            is_global_admin=True,
            allowed_site_ids=None,
            has_frs_access=True,
        )

    # Regular user: query accessible events from UserEventAccess
    stmt = select(UserEventAccess).where(
        UserEventAccess.user_id == current_user.id,
        UserEventAccess.is_active == True,
    )
    res = await db.execute(stmt)
    access_list = res.scalars().all()

    if not access_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "NO_EVENT_ACCESS", "message": "You do not have access to any events"},
        )

    accessible_event_ids = [acc.event_id for acc in access_list]
    access_map = {acc.event_id: acc for acc in access_list}

    target_event: Optional[Event] = None
    target_access: Optional[UserEventAccess] = None

    if x_event_id:
        try:
            target_uuid = uuid.UUID(x_event_id)
            stmt = select(Event).where(
                (Event.id == target_uuid) | (Event.code == x_event_id),
                Event.id.in_(accessible_event_ids),
            )
        except ValueError:
            stmt = select(Event).where(
                Event.code == x_event_id,
                Event.id.in_(accessible_event_ids),
            )
        res = await db.execute(stmt)
        target_event = res.scalars().first()

        if not target_event:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "EVENT_ACCESS_DENIED", "message": f"Access denied for event '{x_event_id}'"},
            )
        target_access = access_map.get(target_event.id)
    else:
        if len(accessible_event_ids) == 1:
            stmt = select(Event).where(Event.id == accessible_event_ids[0])
            res = await db.execute(stmt)
            target_event = res.scalars().first()
            target_access = access_map.get(target_event.id)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "EVENT_CONTEXT_REQUIRED",
                    "message": "Multiple events accessible. Provide 'X-Event-ID' header to select context.",
                },
            )

    if not target_event or not target_access:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "EVENT_NOT_FOUND", "message": "Accessible event could not be resolved"},
        )

    # Check site-level restrictions for this user in this event
    site_stmt = select(UserSiteAccess.site_id).where(
        UserSiteAccess.user_id == current_user.id,
        UserSiteAccess.event_id == target_event.id,
        UserSiteAccess.is_active == True,
    )
    site_res = await db.execute(site_stmt)
    site_ids = site_res.scalars().all()

    allowed_sites = list(site_ids) if site_ids else None

    return EventContext(
        event=target_event,
        event_id=target_event.id,
        event_code=target_event.code,
        access_role=target_access.access_role,
        is_global_admin=False,
        allowed_site_ids=allowed_sites,
        has_frs_access=has_frs,
    )

