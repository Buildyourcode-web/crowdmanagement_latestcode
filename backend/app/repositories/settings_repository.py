"""
Settings Repository — async CRUD for all singleton config tables.
Uses first-or-create pattern for singleton configs.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.camera import Camera
from app.models.event import Event
from app.models.role import Permission, Role, role_permissions
from app.models.settings import (
    AIConfigSettings,
    AlertThresholdConfig,
    FRSConfigSettings,
    NotificationConfig,
    SystemConfig,
)
from app.models.user import User
from app.models.zone import Zone


# ── Singleton helper ──────────────────────────────────────────────────────────

async def _get_or_create_singleton(session: AsyncSession, model_cls, defaults: Dict[str, Any]):
    """Return the first record of model_cls, or create one with defaults."""
    result = await session.execute(select(model_cls))
    record = result.scalars().first()
    if record is None:
        record = model_cls(**defaults)
        session.add(record)
        await session.flush()
    return record


# ── Alert Thresholds ──────────────────────────────────────────────────────────

async def get_alert_thresholds(session: AsyncSession) -> AlertThresholdConfig:
    return await _get_or_create_singleton(session, AlertThresholdConfig, {})


async def update_alert_thresholds(
    session: AsyncSession, data: Dict[str, Any], updated_by: str
) -> AlertThresholdConfig:
    record = await get_alert_thresholds(session)
    for key, val in data.items():
        if val is not None and hasattr(record, key):
            setattr(record, key, val)
    record.config_version = (record.config_version or 0) + 1
    record.updated_by = updated_by
    record.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(record)
    return record


async def reset_alert_thresholds(session: AsyncSession, updated_by: str) -> AlertThresholdConfig:
    record = await get_alert_thresholds(session)
    defaults = {
        "crowd_warning_pct": 80.0, "crowd_high_pct": 90.0,
        "crowd_critical_pct": 100.0, "crowd_extreme_pct": 110.0,
        "queue_warning_count": 500, "queue_critical_count": 1000,
        "queue_wait_warning_min": 20, "queue_wait_critical_min": 30,
        "sudden_inflow_pct": 40.0, "reverse_flow_pct": 25.0,
        "density_growth_rate_pct": 15.0, "camera_offline_sec": 30,
        "camera_degraded_sec": 10, "person_down_sec": 10,
        "panic_risk_score": 0.80, "bottleneck_risk_score": 0.75,
    }
    for key, val in defaults.items():
        setattr(record, key, val)
    record.config_version = (record.config_version or 0) + 1
    record.updated_by = updated_by
    record.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(record)
    return record


# ── AI Config ─────────────────────────────────────────────────────────────────

async def get_ai_config(session: AsyncSession) -> AIConfigSettings:
    return await _get_or_create_singleton(session, AIConfigSettings, {})


async def update_ai_config(
    session: AsyncSession, data: Dict[str, Any], updated_by: str
) -> AIConfigSettings:
    record = await get_ai_config(session)
    for key, val in data.items():
        if val is not None and hasattr(record, key):
            setattr(record, key, val)
    record.config_version = (record.config_version or 0) + 1
    record.updated_by = updated_by
    record.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(record)
    return record


# ── FRS Config ────────────────────────────────────────────────────────────────

async def get_frs_config(session: AsyncSession) -> FRSConfigSettings:
    return await _get_or_create_singleton(session, FRSConfigSettings, {})


async def update_frs_config(
    session: AsyncSession, data: Dict[str, Any], updated_by: str
) -> FRSConfigSettings:
    record = await get_frs_config(session)
    for key, val in data.items():
        if val is not None and hasattr(record, key):
            # SAFETY: never allow disabling human review or enabling auto-confirm
            if key == "human_review_required":
                continue
            if key == "auto_confirmation_enabled":
                continue
            setattr(record, key, val)
    # Enforce safety invariants
    record.human_review_required = True
    record.auto_confirmation_enabled = False
    record.config_version = (record.config_version or 0) + 1
    record.updated_by = updated_by
    record.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(record)
    return record


# ── Notification Config ────────────────────────────────────────────────────────

async def get_notification_config(session: AsyncSession) -> NotificationConfig:
    return await _get_or_create_singleton(session, NotificationConfig, {})


async def update_notification_config(
    session: AsyncSession, data: Dict[str, Any], updated_by: str
) -> NotificationConfig:
    record = await get_notification_config(session)
    for key, val in data.items():
        if val is not None and hasattr(record, key):
            setattr(record, key, val)
    record.config_version = (record.config_version or 0) + 1
    record.updated_by = updated_by
    record.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(record)
    return record


# ── System Config ─────────────────────────────────────────────────────────────

async def get_system_config(session: AsyncSession) -> SystemConfig:
    return await _get_or_create_singleton(session, SystemConfig, {})


async def update_system_config(
    session: AsyncSession, data: Dict[str, Any], updated_by: str
) -> SystemConfig:
    record = await get_system_config(session)
    for key, val in data.items():
        if val is not None and hasattr(record, key):
            setattr(record, key, val)
    record.config_version = (record.config_version or 0) + 1
    record.updated_by = updated_by
    record.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(record)
    return record


async def set_maintenance_mode(
    session: AsyncSession, enabled: bool, message: Optional[str], updated_by: str
) -> SystemConfig:
    record = await get_system_config(session)
    record.maintenance_mode = enabled
    record.maintenance_message = message if enabled else None
    record.config_version = (record.config_version or 0) + 1
    record.updated_by = updated_by
    record.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(record)
    return record


# ── Event Settings (reuses events table) ──────────────────────────────────────

async def get_event_settings(session: AsyncSession) -> Optional[Event]:
    result = await session.execute(select(Event).order_by(Event.created_at.desc()))
    return result.scalars().first()


async def update_event_settings(
    session: AsyncSession, event_id: uuid.UUID, data: Dict[str, Any]
) -> Event:
    result = await session.execute(select(Event).where(Event.id == event_id))
    event = result.scalars().first()
    if not event:
        raise ValueError("Event not found")
    for key, val in data.items():
        if val is not None and hasattr(event, key):
            setattr(event, key, val)
    event.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(event)
    return event


# ── Zone Settings (reuses zones table) ────────────────────────────────────────

async def get_zones_for_settings(session: AsyncSession) -> List[Zone]:
    result = await session.execute(select(Zone).order_by(Zone.zone_code))
    return list(result.scalars().all())


async def get_zone_by_code(session: AsyncSession, zone_code: str) -> Optional[Zone]:
    result = await session.execute(select(Zone).where(Zone.zone_code == zone_code))
    return result.scalars().first()


async def update_zone_settings(
    session: AsyncSession, zone_code: str, data: Dict[str, Any]
) -> Zone:
    zone = await get_zone_by_code(session, zone_code)
    if not zone:
        raise ValueError(f"Zone '{zone_code}' not found")
    for key, val in data.items():
        if val is not None and hasattr(zone, key):
            setattr(zone, key, val)
    zone.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(zone)
    return zone


# ── Camera Settings (reuses cameras table) ────────────────────────────────────

async def get_cameras_for_settings(session: AsyncSession) -> List[Camera]:
    result = await session.execute(select(Camera).order_by(Camera.camera_code))
    return list(result.scalars().all())


async def get_camera_by_code(session: AsyncSession, camera_code: str) -> Optional[Camera]:
    result = await session.execute(select(Camera).where(Camera.camera_code == camera_code))
    return result.scalars().first()


async def update_camera_settings(
    session: AsyncSession, camera_code: str, data: Dict[str, Any]
) -> Camera:
    camera = await get_camera_by_code(session, camera_code)
    if not camera:
        raise ValueError(f"Camera '{camera_code}' not found")
    for key, val in data.items():
        if key == "rtsp_url":
            # Store RTSP URL in encrypted field (store directly for now)
            if val:
                camera.rtsp_url_encrypted = val
            continue
        if val is not None and hasattr(camera, key):
            setattr(camera, key, val)
    camera.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(camera)
    return camera


# ── Role Settings (reuses roles / permissions tables) ─────────────────────────

async def get_roles_with_user_count(session: AsyncSession) -> List[Dict[str, Any]]:
    """Return roles with user_count computed."""
    result = await session.execute(select(Role).order_by(Role.name))
    roles = list(result.scalars().all())

    # Count users per role
    count_result = await session.execute(
        select(User.role_id, func.count(User.id).label("cnt")).group_by(User.role_id)
    )
    counts = {str(row.role_id): row.cnt for row in count_result}

    return [
        {
            "id": str(r.id),
            "code": r.code,
            "name": r.name,
            "description": r.description,
            "user_count": counts.get(str(r.id), 0),
            "is_system_role": r.code == "SUPER_ADMIN",
            "permissions": list(r.permissions),
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in roles
    ]


async def get_role_by_id(session: AsyncSession, role_id: uuid.UUID) -> Optional[Dict]:
    result = await session.execute(select(Role).where(Role.id == role_id))
    role = result.scalars().first()
    if not role:
        return None
    count_result = await session.execute(
        select(func.count(User.id)).where(User.role_id == role_id)
    )
    user_count = count_result.scalar() or 0
    return {
        "id": str(role.id),
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "user_count": user_count,
        "is_system_role": role.code == "SUPER_ADMIN",
        "permissions": list(role.permissions),
        "created_at": role.created_at,
        "updated_at": role.updated_at,
    }


async def update_role(
    session: AsyncSession, role_id: uuid.UUID, data: Dict[str, Any]
) -> Role:
    result = await session.execute(select(Role).where(Role.id == role_id))
    role = result.scalars().first()
    if not role:
        raise ValueError("Role not found")
    if role.code == "SUPER_ADMIN":
        raise ValueError("SUPER_ADMIN is a protected system role and cannot be modified")
    if data.get("name"):
        role.name = data["name"]
    if data.get("description") is not None:
        role.description = data["description"]
    role.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(role)
    return role


async def update_role_permissions(
    session: AsyncSession, role_id: uuid.UUID, permission_codes: List[str]
) -> Role:
    """Replace all permissions for a role atomically."""
    result = await session.execute(select(Role).where(Role.id == role_id))
    role = result.scalars().first()
    if not role:
        raise ValueError("Role not found")
    if role.code == "SUPER_ADMIN":
        raise ValueError("Cannot modify SUPER_ADMIN permissions")

    # Resolve permission objects
    perm_result = await session.execute(
        select(Permission).where(Permission.code.in_(permission_codes))
    )
    perms = list(perm_result.scalars().all())

    # Delete existing associations
    await session.execute(
        delete(role_permissions).where(role_permissions.c.role_id == role.id)
    )
    await session.flush()

    # Insert new associations
    for perm in perms:
        await session.execute(
            role_permissions.insert().values(role_id=role.id, permission_id=perm.id)
        )
    await session.flush()
    await session.refresh(role)
    return role


async def get_all_permissions(session: AsyncSession) -> List[Permission]:
    result = await session.execute(select(Permission).order_by(Permission.code))
    return list(result.scalars().all())


# ── Audit Logs ────────────────────────────────────────────────────────────────

async def get_settings_audit_logs(
    session: AsyncSession, resource_type: Optional[str] = None, limit: int = 50
) -> List[AuditLog]:
    q = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    if resource_type:
        q = q.where(AuditLog.resource_type == resource_type)
    else:
        # Only settings-related audit logs
        settings_types = [
            "alert_threshold", "ai_config", "frs_config",
            "notification_config", "system_config", "event_settings",
            "zone_settings", "camera_settings", "role", "role_permissions",
        ]
        q = q.where(AuditLog.resource_type.in_(settings_types))
    result = await session.execute(q)
    return list(result.scalars().all())
