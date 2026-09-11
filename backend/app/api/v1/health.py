from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.redis.client import get_redis_connection
from app.utils.response import success_response

router = APIRouter(prefix="/health", tags=["Health Checks"])


@router.get("", response_model=dict)
@router.get("/", response_model=dict)
@router.get("/live", response_model=dict)
async def liveness_probe():
    """Kubernetes / Docker container liveness probe."""
    return {"status": "alive", "service": "byc-command-center"}


@router.get("/ready", response_model=dict)
async def readiness_probe(db: AsyncSession = Depends(get_db)):
    """Kubernetes / Docker container readiness probe checking DB and Redis."""
    db_status = "healthy"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unhealthy"

    redis_status = "healthy"
    try:
        redis = await get_redis_connection()
        if redis:
            await redis.ping()
        else:
            redis_status = "unavailable"
    except Exception:
        redis_status = "unhealthy"

    overall = "healthy" if db_status == "healthy" else "degraded"
    return {
        "status": overall,
        "database": db_status,
        "redis": redis_status,
        "version": "1.0.0",
    }


@router.get("/database", response_model=dict)
async def db_health_check(db: AsyncSession = Depends(get_db)):
    """Direct database connectivity probe."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@router.get("/redis", response_model=dict)
async def redis_health_check():
    """Direct Redis connectivity probe."""
    try:
        redis = await get_redis_connection()
        if redis:
            await redis.ping()
            return {"status": "healthy", "redis": "connected"}
        return {"status": "degraded", "redis": "standalone_fallback"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
