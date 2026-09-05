from fastapi import APIRouter
from app.api.v1.ai import router as ai_router
from app.api.v1.alerts import router as alerts_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import router as auth_router
from app.api.v1.cameras import router as cameras_router
from app.api.v1.crowd import router as crowd_router
from app.api.v1.queue import router as queue_router
from app.api.v1.frs import router as frs_router
from app.api.v1.health import router as health_router
from app.api.v1.incidents import router as incidents_router
from app.api.v1.internal_ai import router as internal_ai_router
from app.api.v1.missing_persons import router as missing_persons_router
from app.api.v1.operations import router as operations_router
from app.api.v1.predictions import router as predictions_router
from app.api.v1.reports import router as reports_router
from app.api.v1.settings import router as settings_router
from app.api.v1.system import router as system_router
from app.api.v1.users import router as users_router
from app.api.v1.zones import router as zones_router

api_router = APIRouter()

# API v1 endpoints
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(cameras_router)
api_router.include_router(zones_router)
api_router.include_router(crowd_router)
api_router.include_router(queue_router)
api_router.include_router(frs_router)
api_router.include_router(missing_persons_router)
api_router.include_router(alerts_router)
api_router.include_router(incidents_router)
api_router.include_router(operations_router)
api_router.include_router(analytics_router)
api_router.include_router(predictions_router)
api_router.include_router(reports_router)
api_router.include_router(settings_router)
api_router.include_router(system_router)
api_router.include_router(ai_router)
