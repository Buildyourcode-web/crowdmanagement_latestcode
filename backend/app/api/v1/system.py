from fastapi import APIRouter, Depends, status
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.common import StandardResponse
from app.schemas.system import SystemHealthResponse
from app.security.permissions import Permissions
from app.services.system_service import SystemService
from app.utils.response import success_response

router = APIRouter(prefix="/system", tags=["System & Infrastructure"])


@router.get("/health", response_model=StandardResponse[SystemHealthResponse])
async def get_system_health(
    current_user: User = Depends(require_permission(Permissions.SYSTEM_READ)),
):
    """Retrieve full cluster health, GPU metrics, and service latencies."""
    data = SystemService.get_system_health()
    return success_response(data)


@router.get("/gpus", response_model=StandardResponse[dict])
async def get_gpu_telemetry(
    current_user: User = Depends(require_permission(Permissions.SYSTEM_READ)),
):
    """Retrieve detailed GPU utilization and temperature stats."""
    health = SystemService.get_system_health()
    return success_response(health.gpu.model_dump(by_alias=True))


@router.get("/services", response_model=StandardResponse[dict])
async def get_services_status(
    current_user: User = Depends(require_permission(Permissions.SYSTEM_READ)),
):
    """Retrieve service health summary for Database, Redis, and WebSocket."""
    health = SystemService.get_system_health()
    return success_response({
        "database": health.database.model_dump(by_alias=True),
        "redis": health.redis.model_dump(by_alias=True),
        "websocket": health.websocket.model_dump(by_alias=True),
        "ai_engine": health.ai_engine.model_dump(by_alias=True),
        "frs_engine": health.frs_engine.model_dump(by_alias=True),
    })
