"""
Settings Service — business logic layer over settings_repository.
Handles audit logging and Redis event publishing on every mutation.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app import repositories
from app.models.audit_log import AuditLog
from app.models.user import User
from app.redis.event_bus import event_bus
from app.redis.keys import RedisChannels
import app.repositories.settings_repository as repo


# ── Audit helper ──────────────────────────────────────────────────────────────

async def _audit(
    session: AsyncSession,
    user: User,
    action: str,
    resource_type: str,
    resource_id: str,
    old_val: Any = None,
    new_val: Any = None,
    ip_address: Optional[str] = None,
) -> None:
    log = AuditLog(
        user_id=user.id,
        username=user.username,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        timestamp=datetime.now(timezone.utc),
        ip_address=ip_address,
        metadata_json={"old": old_val, "new": new_val},
    )
    session.add(log)


# ── Event Settings ────────────────────────────────────────────────────────────

async def get_event_settings(session: AsyncSession):
    return await repo.get_event_settings(session)


async def update_event_settings(
    session: AsyncSession, user: User, data: Dict[str, Any], ip: Optional[str] = None
):
    event = await repo.get_event_settings(session)
    if not event:
        raise ValueError("No active event found")
    old = {"name": event.name, "status": event.status}
    updated = await repo.update_event_settings(session, event.id, data)
    await _audit(session, user, "EVENT_SETTINGS_UPDATED", "event_settings", str(event.id), old, data, ip)
    await session.commit()
    await event_bus.publish("byc:settings", "settings_updated", {
        "module": "event", "resource_id": str(event.id), "updated_by": user.username,
    })
    return updated


# ── Zone Settings ─────────────────────────────────────────────────────────────

async def get_zone_settings(session: AsyncSession):
    return await repo.get_zones_for_settings(session)


async def get_zone_setting(session: AsyncSession, zone_code: str):
    zone = await repo.get_zone_by_code(session, zone_code)
    if not zone:
        raise ValueError(f"Zone '{zone_code}' not found")
    return zone


async def update_zone_setting(
    session: AsyncSession, user: User, zone_code: str, data: Dict[str, Any], ip: Optional[str] = None
):
    zone = await repo.get_zone_by_code(session, zone_code)
    if not zone:
        raise ValueError(f"Zone '{zone_code}' not found")
    old = {"name": zone.name, "capacity": zone.capacity, "risk_level": zone.risk_level}
    updated = await repo.update_zone_settings(session, zone_code, data)
    await _audit(session, user, "ZONE_SETTINGS_UPDATED", "zone_settings", zone_code, old, data, ip)
    await session.commit()
    await event_bus.publish("byc:settings", "zone_settings_updated", {
        "module": "zone", "zone_code": zone_code, "updated_by": user.username,
    })
    return updated


# ── Camera Settings ────────────────────────────────────────────────────────────

async def get_camera_settings(session: AsyncSession):
    return await repo.get_cameras_for_settings(session)


async def get_camera_setting(session: AsyncSession, camera_code: str):
    camera = await repo.get_camera_by_code(session, camera_code)
    if not camera:
        raise ValueError(f"Camera '{camera_code}' not found")
    return camera


async def update_camera_setting(
    session: AsyncSession, user: User, camera_code: str, data: Dict[str, Any], ip: Optional[str] = None
):
    camera = await repo.get_camera_by_code(session, camera_code)
    if not camera:
        raise ValueError(f"Camera '{camera_code}' not found")
    # Sanitize: never log RTSP credentials
    safe_data = {k: v for k, v in data.items() if k != "rtsp_url"}
    old = {"name": camera.name, "status": camera.status, "is_frs_camera": camera.is_frs_camera}
    updated = await repo.update_camera_settings(session, camera_code, data)
    await _audit(session, user, "CAMERA_SETTINGS_UPDATED", "camera_settings", camera_code, old, safe_data, ip)
    await session.commit()
    await event_bus.publish("byc:settings", "camera_settings_updated", {
        "module": "camera", "camera_code": camera_code, "updated_by": user.username,
    })
    return updated


async def test_camera_connection(camera_code: str) -> Dict[str, Any]:
    """Simulated camera connection test (Phase 3 will do real RTSP probe)."""
    import random
    ok = random.random() > 0.15
    return {
        "camera_code": camera_code,
        "connection_status": "ONLINE" if ok else "FAILED",
        "latency_ms": random.randint(28, 85) if ok else None,
        "fps": 24 if ok else None,
        "resolution": "1080p" if ok else None,
        "tested_at": datetime.now(timezone.utc),
        "message": "Connection successful" if ok else "RTSP connection timed out",
    }


# ── Alert Thresholds ──────────────────────────────────────────────────────────

async def get_alert_settings(session: AsyncSession):
    return await repo.get_alert_thresholds(session)


async def update_alert_settings(
    session: AsyncSession, user: User, data: Dict[str, Any], ip: Optional[str] = None
):
    current = await repo.get_alert_thresholds(session)
    old = {
        "crowd_warning_pct": current.crowd_warning_pct,
        "crowd_critical_pct": current.crowd_critical_pct,
        "config_version": current.config_version,
    }
    updated = await repo.update_alert_thresholds(session, data, user.username)
    await _audit(session, user, "ALERT_THRESHOLD_UPDATED", "alert_threshold", str(current.id), old, data, ip)
    await session.commit()
    await event_bus.publish("byc:settings", "alert_threshold_updated", {
        "module": "alert_thresholds", "updated_by": user.username, "config_version": updated.config_version,
    })
    return updated


async def reset_alert_settings(session: AsyncSession, user: User, ip: Optional[str] = None):
    current = await repo.get_alert_thresholds(session)
    updated = await repo.reset_alert_thresholds(session, user.username)
    await _audit(session, user, "ALERT_THRESHOLD_RESET", "alert_threshold", str(current.id), None, "RESET_TO_DEFAULTS", ip)
    await session.commit()
    await event_bus.publish("byc:settings", "alert_threshold_reset", {
        "module": "alert_thresholds", "updated_by": user.username,
    })
    return updated


# ── Role Settings ─────────────────────────────────────────────────────────────

async def get_roles(session: AsyncSession):
    return await repo.get_roles_with_user_count(session)


async def get_role(session: AsyncSession, role_id: uuid.UUID):
    role = await repo.get_role_by_id(session, role_id)
    if not role:
        raise ValueError("Role not found")
    return role


async def get_all_permissions(session: AsyncSession):
    return await repo.get_all_permissions(session)


async def update_role(
    session: AsyncSession, user: User, role_id: uuid.UUID, data: Dict[str, Any], ip: Optional[str] = None
):
    updated = await repo.update_role(session, role_id, data)
    await _audit(session, user, "ROLE_UPDATED", "role", str(role_id), None, data, ip)
    await session.commit()
    await event_bus.publish("byc:settings", "role_updated", {
        "module": "role", "role_id": str(role_id), "updated_by": user.username,
    })
    return updated


async def update_role_permissions(
    session: AsyncSession, user: User, role_id: uuid.UUID, permission_codes: List[str], ip: Optional[str] = None
):
    updated = await repo.update_role_permissions(session, role_id, permission_codes)
    await _audit(session, user, "ROLE_PERMISSIONS_UPDATED", "role_permissions", str(role_id), None, permission_codes, ip)
    await session.commit()
    await event_bus.publish("byc:settings", "role_permissions_updated", {
        "module": "role_permissions", "role_id": str(role_id), "updated_by": user.username,
        "permissions": permission_codes,
    })
    return updated


# ── Notification Settings ─────────────────────────────────────────────────────

async def get_notification_settings(session: AsyncSession):
    return await repo.get_notification_config(session)


async def update_notification_settings(
    session: AsyncSession, user: User, data: Dict[str, Any], ip: Optional[str] = None
):
    current = await repo.get_notification_config(session)
    updated = await repo.update_notification_config(session, data, user.username)
    await _audit(session, user, "NOTIFICATION_CONFIG_UPDATED", "notification_config", str(current.id), None, data, ip)
    await session.commit()
    await event_bus.publish("byc:settings", "notification_config_updated", {
        "module": "notifications", "updated_by": user.username,
    })
    return updated


# ── AI Settings ───────────────────────────────────────────────────────────────

async def get_ai_settings(session: AsyncSession):
    return await repo.get_ai_config(session)


async def update_ai_settings(
    session: AsyncSession, user: User, data: Dict[str, Any], ip: Optional[str] = None
):
    current = await repo.get_ai_config(session)
    old = {
        "crowd_detection_enabled": current.crowd_detection_enabled,
        "detection_confidence": current.detection_confidence,
        "processing_fps": current.processing_fps,
    }
    updated = await repo.update_ai_config(session, data, user.username)
    await _audit(session, user, "AI_CONFIG_UPDATED", "ai_config", str(current.id), old, data, ip)
    await session.commit()
    await event_bus.publish("byc:settings", "ai_config_updated", {
        "event": "ai_config_updated",
        "config": {
            "crowd_detection_enabled": updated.crowd_detection_enabled,
            "confidence": updated.detection_confidence,
            "processing_fps": updated.processing_fps,
        },
        "updated_by": user.username,
    })
    return updated


# ── FRS Settings ──────────────────────────────────────────────────────────────

async def get_frs_settings(session: AsyncSession):
    return await repo.get_frs_config(session)


async def update_frs_settings(
    session: AsyncSession, user: User, data: Dict[str, Any], ip: Optional[str] = None
):
    # Extra business validation
    ct = data.get("candidate_threshold")
    mt = data.get("match_threshold")
    if ct and mt and ct > mt:
        raise ValueError("Candidate threshold cannot be greater than match threshold")

    current = await repo.get_frs_config(session)
    old = {
        "match_threshold": current.match_threshold,
        "candidate_threshold": current.candidate_threshold,
        "human_review_required": current.human_review_required,
    }
    updated = await repo.update_frs_config(session, data, user.username)
    await _audit(session, user, "FRS_CONFIG_UPDATED", "frs_config", str(current.id), old, data, ip)
    await session.commit()
    await event_bus.publish("byc:settings", "frs_config_updated", {
        "event": "frs_config_updated",
        "config": {
            "candidate_threshold": updated.candidate_threshold,
            "match_threshold": updated.match_threshold,
            "human_review_required": updated.human_review_required,
        },
        "updated_by": user.username,
    })
    return updated


# ── System Settings ───────────────────────────────────────────────────────────

async def get_system_settings(session: AsyncSession):
    return await repo.get_system_config(session)


async def update_system_settings(
    session: AsyncSession, user: User, data: Dict[str, Any], ip: Optional[str] = None
):
    current = await repo.get_system_config(session)
    updated = await repo.update_system_config(session, data, user.username)
    await _audit(session, user, "SYSTEM_CONFIG_UPDATED", "system_config", str(current.id), None, data, ip)
    await session.commit()
    await event_bus.publish("byc:settings", "system_config_updated", {
        "module": "system", "updated_by": user.username,
    })
    return updated


async def toggle_maintenance_mode(
    session: AsyncSession, user: User, enabled: bool, message: Optional[str], ip: Optional[str] = None
):
    current = await repo.get_system_config(session)
    if not user.role or user.role.code not in ("SUPER_ADMIN", "COMMANDER"):
        raise PermissionError("Only SUPER_ADMIN or COMMANDER can toggle maintenance mode")
    updated = await repo.set_maintenance_mode(session, enabled, message, user.username)
    action = "MAINTENANCE_MODE_ENABLED" if enabled else "MAINTENANCE_MODE_DISABLED"
    await _audit(session, user, action, "system_config", str(current.id), None, {"enabled": enabled, "message": message}, ip)
    await session.commit()
    await event_bus.publish("byc:settings", "maintenance_mode_changed", {
        "enabled": enabled, "message": message, "updated_by": user.username,
    })
    return updated


# ── Audit Logs ────────────────────────────────────────────────────────────────

async def get_settings_audit(session: AsyncSession, resource_type: Optional[str] = None, limit: int = 50):
    return await repo.get_settings_audit_logs(session, resource_type=resource_type, limit=limit)
