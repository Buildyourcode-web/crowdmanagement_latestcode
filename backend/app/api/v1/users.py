from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_user, get_db, require_permission
from app.models.role import Permission, Role
from app.models.user import User
from app.schemas.common import StandardResponse
from app.schemas.user import RoleRead, UserRead
from app.security.permissions import Permissions
from app.utils.response import success_response

router = APIRouter(prefix="/users", tags=["User Management & RBAC"])


@router.get("", response_model=StandardResponse[List[UserRead]])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.SYSTEM_READ)),
):
    """List system users and their assigned operational roles."""
    stmt = select(User).options(selectinload(User.role)).order_by(User.created_at.asc())
    result = await db.execute(stmt)
    users = list(result.scalars().all())

    return success_response([
        UserRead(
            id=u.id,
            username=u.username,
            email=u.email,
            full_name=u.full_name,
            role_id=u.role_id,
            role_code=u.role_code or "VIEWER",
            role_name=u.role_name or "Viewer",
            is_active=u.is_active,
            created_at=u.created_at,
            last_login=u.last_login,
        )
        for u in users
    ])


@router.get("/roles", response_model=StandardResponse[List[RoleRead]])
async def list_roles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.SYSTEM_READ)),
):
    """List all available operational roles and permissions."""
    stmt = select(Role).order_by(Role.code.asc())
    result = await db.execute(stmt)
    roles = list(result.scalars().all())
    return success_response(roles)
