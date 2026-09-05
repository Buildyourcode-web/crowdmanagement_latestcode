import time
import uuid
from typing import Dict, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.api.router import api_router
from app.api.v1.health import router as health_router
from app.api.v1.internal_ai import router as internal_ai_router
from app.config import settings
from app.logging_config import setup_logging
from app.redis.client import close_redis_connection, get_redis_connection
from app.services.storage_service import storage_service
from app.utils.response import error_response
from app.websocket.router import router as websocket_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize logging, verify Redis
    setup_logging()
    logger.info(f"Starting {settings.APP_NAME} in {settings.APP_ENV} mode")
    await get_redis_connection()

    # Auto-start FRS engine main camera only if RTSP_ENABLED
    if settings.RTSP_ENABLED:
        try:
            import asyncio
            from app.frs_engine.frs_service import auto_start_main_camera, set_main_event_loop
            set_main_event_loop(asyncio.get_running_loop())
            import threading
            t = threading.Thread(target=auto_start_main_camera, daemon=True, name="FRS-AutoStart")
            t.start()
            logger.info("FRS Engine: auto-start initiated")
        except Exception as e:
            logger.warning(f"FRS Engine auto-start skipped: {e}")
    else:
        logger.info("RTSP_ENABLED is False: skipping automatic RTSP stream connection (PoE camera can be started on demand)")

    # Start AI Orchestrator Background Supervision Loop & Startup Recovery
    try:
        import asyncio
        from app.ai.orchestrator.service import ai_orchestrator
        await ai_orchestrator.start_supervision_loop()
        asyncio.create_task(ai_orchestrator.recover_on_startup())
        logger.info("AI Orchestrator: supervision loop and startup recovery initiated")
    except Exception as e:
        logger.warning(f"AI Orchestrator startup skipped: {e}")

    # Pre-warm DB connection pool and cache in background (avoids blocking startup)
    async def _warm_db_and_cache():
        try:
            from app.db.session import AsyncSessionLocal
            from app.dependencies import get_current_user
            from app.services.crowd_service import CrowdService
            from app.services.zone_service import ZoneService
            from app.services.camera_service import CameraService
            async with AsyncSessionLocal() as session:
                await get_current_user(auth=None, db=session)
                await CrowdService(session).get_summary()
                await ZoneService(session).list_zones()
                await CameraService(session).get_camera_stats()
            logger.info("DB cache pre-warmed successfully (user, summary, zones, camera stats)")
        except Exception as e:
            logger.warning(f"DB cache pre-warm skipped (non-fatal): {e}")

    asyncio.create_task(_warm_db_and_cache())

    yield
    # Shutdown: Close orchestrator and connections
    try:
        from app.ai.orchestrator.service import ai_orchestrator
        await ai_orchestrator.shutdown()
    except Exception as e:
        logger.warning(f"AI Orchestrator shutdown error: {e}")

    await close_redis_connection()
    logger.info("Application shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    description="Production-grade AI Command & Control Platform API for Crowd Management, AI Video Analytics, and FRS.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS Middleware (supports all local Vite ports e.g. 5173, 5174, 5175)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




# Structured Request Logging Middleware
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start_time = time.perf_counter()
    request.state.request_id = request_id

    response = await call_next(request)

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    user_info = getattr(request.state, "user_id", "anonymous")

    logger.info(
        f"request_id={request_id} method={request.method} path={request.url.path} "
        f"status={response.status_code} duration={duration_ms}ms user={user_info}"
    )


    response.headers["X-Request-ID"] = request_id
    return response


def _cors_headers_for_request(request: Request) -> Dict[str, str]:
    origin = request.headers.get("origin")
    if origin:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
    return {}


# Global Exception Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        code = exc.detail.get("code", "ERROR")
        message = exc.detail.get("message", "An error occurred")
    else:
        code = "HTTP_ERROR"
        message = str(exc.detail)

    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(code=code, message=message),
        headers=_cors_headers_for_request(request),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled Exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected internal server error occurred.",
        ),
        headers=_cors_headers_for_request(request),
    )


# Mount Routers
app.include_router(health_router)
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(internal_ai_router)
app.include_router(websocket_router)

# Mount FRS Engine Router (Live RTSP + MJPEG)
try:
    from app.frs_engine.frs_service import router as frs_engine_router
    app.include_router(frs_engine_router, prefix=settings.API_V1_STR)
    logger.info("FRS Engine router mounted at /api/v1/frs-engine")
except Exception as e:
    logger.warning(f"FRS Engine router not mounted: {e}")

# Mount Static Media Storage
app.mount("/media", StaticFiles(directory=settings.MEDIA_ROOT), name="media")

# Mount Static FRS Enrollment & Face Crop Storage
import os
os.makedirs("backend/data/enrollment", exist_ok=True)
os.makedirs("backend/data/crops", exist_ok=True)
app.mount("/static/enrollment", StaticFiles(directory="backend/data/enrollment"), name="enrollment_photos")
app.mount("/static/crops", StaticFiles(directory="backend/data/crops"), name="crop_photos")



@app.get("/", tags=["Root"])
async def root():
    return {
        "app": settings.APP_NAME,
        "version": "1.0.0",
        "status": "OPERATIONAL",
        "docs": "/docs",
        "health": "/health/ready",
        "websocket": "/ws/v1/events",
    }
