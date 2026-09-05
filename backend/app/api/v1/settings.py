"""
Settings API Router — /api/v1/settings/*
All endpoints require JWT + appropriate RBAC permission.
"""
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.settings import (
    AIConfigResponse,
    AIConfigUpdate,
    AlertThresholdResponse,
    AlertThresholdUpdate,
    CameraSettingsResponse,
    CameraSettingsUpdate,
    CameraTestResponse,
    EventSettingsResponse,
    EventSettingsUpdate,
    FRSConfigResponse,
    FRSConfigUpdate,
    MaintenanceModeUpdate,
    NotificationResponse,
    NotificationUpdate,
    PermissionResponse,
    RoleCreate,
    RolePermissionsUpdate,
    RoleSettingsResponse,
    RoleUpdate,
    SettingsAuditResponse,
    SystemConfigResponse,
    SystemConfigUpdate,
    ZoneSettingsResponse,
    ZoneSettingsUpdate,
)
from app.security.permissions import Permissions
import app.services.settings_service as svc

router = APIRouter(prefix="/settings", tags=["Settings"])


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _cam_to_response(camera) -> Dict[str, Any]:
    """Convert Camera ORM to CameraSettingsResponse dict (never exposes rtsp_url_encrypted)."""
    return {
        "id": str(camera.id),
        "camera_code": camera.camera_code,
        "name": camera.name,
        "label": camera.label,
        "camera_type": camera.camera_type,
        "zone_code": camera.zone_code,
        "resolution": camera.resolution,
        "fps": camera.fps,
        "latency_ms": camera.latency_ms,
        "status": camera.status,
        "ai_status": camera.ai_status,
        "is_frs_camera": camera.is_frs_camera,
        "is_ptz": camera.is_ptz,
        "people_count": camera.people_count,
        "has_rtsp_configured": bool(camera.rtsp_url_encrypted),
        "created_at": camera.created_at,
        "updated_at": camera.updated_at,
    }


# ── Summary ───────────────────────────────────────────────────────────────────

@router.get("", summary="Settings summary")
async def get_settings_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.SETTINGS_READ)),
):
    alert = await svc.get_alert_settings(db)
    ai = await svc.get_ai_settings(db)
    frs = await svc.get_frs_settings(db)
    notif = await svc.get_notification_settings(db)
    system = await svc.get_system_settings(db)
    return {
        "status": "ok",
        "maintenance_mode": system.maintenance_mode,
        "config_versions": {
            "alert_thresholds": alert.config_version,
            "ai_config": ai.config_version,
            "frs_config": frs.config_version,
            "notifications": notif.config_version,
            "system": system.config_version,
        },
    }


# ── Event Settings ────────────────────────────────────────────────────────────

@router.get("/event", response_model=EventSettingsResponse, summary="Get event settings")
async def get_event(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.EVENT_SETTINGS_READ)),
):
    event = await svc.get_event_settings(db)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No event configured")
    return EventSettingsResponse.model_validate(event)


@router.patch("/event", response_model=EventSettingsResponse, summary="Update event settings")
async def update_event(
    body: EventSettingsUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.EVENT_SETTINGS_UPDATE)),
):
    try:
        updated = await svc.update_event_settings(db, current_user, body.model_dump(exclude_none=True), _client_ip(request))
        return EventSettingsResponse.model_validate(updated)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# ── Zone Settings ─────────────────────────────────────────────────────────────

@router.get("/zones", summary="List zone settings")
async def list_zones(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ZONE_SETTINGS_READ)),
):
    zones = await svc.get_zone_settings(db)
    return [ZoneSettingsResponse.model_validate(z) for z in zones]


@router.get("/zones/{zone_code}", response_model=ZoneSettingsResponse, summary="Get zone settings")
async def get_zone(
    zone_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ZONE_SETTINGS_READ)),
):
    try:
        zone = await svc.get_zone_setting(db, zone_code)
        return ZoneSettingsResponse.model_validate(zone)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/zones/{zone_code}", response_model=ZoneSettingsResponse, summary="Update zone settings")
async def update_zone(
    zone_code: str,
    body: ZoneSettingsUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ZONE_SETTINGS_UPDATE)),
):
    try:
        updated = await svc.update_zone_setting(db, current_user, zone_code, body.model_dump(exclude_none=True), _client_ip(request))
        return ZoneSettingsResponse.model_validate(updated)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ── Camera Settings ────────────────────────────────────────────────────────────

@router.get("/cameras", summary="List camera settings")
async def list_cameras(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.CAMERA_SETTINGS_READ)),
):
    cameras = await svc.get_camera_settings(db)
    return [CameraSettingsResponse(**_cam_to_response(c)) for c in cameras]


@router.get("/cameras/{camera_code}", response_model=CameraSettingsResponse, summary="Get camera settings")
async def get_camera(
    camera_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.CAMERA_SETTINGS_READ)),
):
    try:
        cam = await svc.get_camera_setting(db, camera_code)
        return CameraSettingsResponse(**_cam_to_response(cam))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/cameras/{camera_code}", response_model=CameraSettingsResponse, summary="Update camera settings")
async def update_camera(
    camera_code: str,
    body: CameraSettingsUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.CAMERA_SETTINGS_UPDATE)),
):
    try:
        updated = await svc.update_camera_setting(db, current_user, camera_code, body.model_dump(exclude_none=True), _client_ip(request))
        return CameraSettingsResponse(**_cam_to_response(updated))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/cameras/{camera_code}/test", response_model=CameraTestResponse, summary="Test camera RTSP connection")
async def test_camera(
    camera_code: str,
    current_user: User = Depends(require_permission(Permissions.CAMERA_SETTINGS_READ)),
):
    result = await svc.test_camera_connection(camera_code)
    return CameraTestResponse(**result)


# ── Alert Thresholds ──────────────────────────────────────────────────────────

@router.get("/alerts", response_model=AlertThresholdResponse, summary="Get alert thresholds")
async def get_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ALERT_SETTINGS_READ)),
):
    rec = await svc.get_alert_settings(db)
    return AlertThresholdResponse.model_validate(rec)


@router.patch("/alerts", response_model=AlertThresholdResponse, summary="Update alert thresholds")
async def update_alerts(
    body: AlertThresholdUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ALERT_SETTINGS_UPDATE)),
):
    updated = await svc.update_alert_settings(db, current_user, body.model_dump(exclude_none=True), _client_ip(request))
    return AlertThresholdResponse.model_validate(updated)


@router.post("/alerts/reset", response_model=AlertThresholdResponse, summary="Reset alert thresholds to defaults")
async def reset_alerts(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ALERT_SETTINGS_UPDATE)),
):
    reset = await svc.reset_alert_settings(db, current_user, _client_ip(request))
    return AlertThresholdResponse.model_validate(reset)


# ── Role Settings ─────────────────────────────────────────────────────────────

@router.get("/roles", summary="List roles with user counts")
async def list_roles(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ROLE_READ)),
):
    roles = await svc.get_roles(db)
    return roles


@router.get("/roles/{role_id}", summary="Get role detail")
async def get_role(
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ROLE_READ)),
):
    try:
        role = await svc.get_role(db, role_id)
        return role
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/roles/{role_id}", summary="Update role metadata")
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ROLE_UPDATE)),
):
    try:
        updated = await svc.update_role(db, current_user, role_id, body.model_dump(exclude_none=True), _client_ip(request))
        return {"id": str(updated.id), "code": updated.code, "name": updated.name}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/roles/{role_id}/permissions", summary="Replace role permissions")
async def set_role_permissions(
    role_id: uuid.UUID,
    body: RolePermissionsUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ROLE_UPDATE)),
):
    try:
        await svc.update_role_permissions(db, current_user, role_id, body.permissions, _client_ip(request))
        return {"message": "Permissions updated successfully", "role_id": str(role_id), "permissions": body.permissions}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/permissions", summary="List all available permissions")
async def list_permissions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.ROLE_READ)),
):
    perms = await svc.get_all_permissions(db)
    return [PermissionResponse.model_validate(p) for p in perms]


# ── Notification Settings ─────────────────────────────────────────────────────

@router.get("/notifications", response_model=NotificationResponse, summary="Get notification settings")
async def get_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.NOTIFICATION_SETTINGS_READ)),
):
    rec = await svc.get_notification_settings(db)
    return NotificationResponse.model_validate(rec)


@router.patch("/notifications", response_model=NotificationResponse, summary="Update notification settings")
async def update_notifications(
    body: NotificationUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.NOTIFICATION_SETTINGS_UPDATE)),
):
    updated = await svc.update_notification_settings(db, current_user, body.model_dump(exclude_none=True), _client_ip(request))
    return NotificationResponse.model_validate(updated)


# ── AI Settings ───────────────────────────────────────────────────────────────

@router.get("/ai", response_model=AIConfigResponse, summary="Get AI configuration")
async def get_ai(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_SETTINGS_READ)),
):
    rec = await svc.get_ai_settings(db)
    return AIConfigResponse.model_validate(rec)


@router.patch("/ai", response_model=AIConfigResponse, summary="Update AI configuration")
async def update_ai(
    body: AIConfigUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.AI_SETTINGS_UPDATE)),
):
    updated = await svc.update_ai_settings(db, current_user, body.model_dump(exclude_none=True), _client_ip(request))
    return AIConfigResponse.model_validate(updated)


# ── FRS Settings ──────────────────────────────────────────────────────────────

@router.get("/frs", response_model=FRSConfigResponse, summary="Get FRS configuration")
async def get_frs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_SETTINGS_READ)),
):
    rec = await svc.get_frs_settings(db)
    return FRSConfigResponse.model_validate(rec)


@router.patch("/frs", response_model=FRSConfigResponse, summary="Update FRS configuration")
async def update_frs(
    body: FRSConfigUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.FRS_SETTINGS_UPDATE)),
):
    try:
        updated = await svc.update_frs_settings(db, current_user, body.model_dump(exclude_none=True), _client_ip(request))
        return FRSConfigResponse.model_validate(updated)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


# ── System Settings ────────────────────────────────────────────────────────────

@router.get("/system", response_model=SystemConfigResponse, summary="Get system configuration")
async def get_system(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.SYSTEM_SETTINGS_READ)),
):
    rec = await svc.get_system_settings(db)
    return SystemConfigResponse.model_validate(rec)


@router.patch("/system", response_model=SystemConfigResponse, summary="Update system configuration")
async def update_system(
    body: SystemConfigUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.SYSTEM_SETTINGS_UPDATE)),
):
    updated = await svc.update_system_settings(db, current_user, body.model_dump(exclude_none=True), _client_ip(request))
    return SystemConfigResponse.model_validate(updated)


@router.post("/system/maintenance", response_model=SystemConfigResponse, summary="Toggle maintenance mode")
async def toggle_maintenance(
    body: MaintenanceModeUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.SYSTEM_MANAGE)),
):
    if not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set confirm=true to apply maintenance mode change",
        )
    try:
        updated = await svc.toggle_maintenance_mode(
            db, current_user, body.enabled, body.message, _client_ip(request)
        )
        return SystemConfigResponse.model_validate(updated)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


# ── Audit ─────────────────────────────────────────────────────────────────────

@router.get("/audit", summary="Settings audit log")
async def get_audit(
    resource_type: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.SETTINGS_READ)),
):
    logs = await svc.get_settings_audit(db, resource_type=resource_type, limit=min(limit, 200))
    return [SettingsAuditResponse.model_validate(log) for log in logs]
