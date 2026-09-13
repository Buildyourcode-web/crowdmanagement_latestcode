from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings

# ---------------------------------------------------------------------------
# Async engine (used by FastAPI endpoints)
# ---------------------------------------------------------------------------
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_size=10,
    max_overflow=5,
    pool_timeout=20,
    pool_recycle=300,
    pool_pre_ping=True,   # validates connections before use — prevents stale-connection errors on AWS/Supabase
    connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            if session.dirty or session.new or session.deleted:
                await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Synchronous engine (used by background worker threads like Crowd AI)
# ---------------------------------------------------------------------------
_sync_db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

try:
    sync_engine = create_engine(
        _sync_db_url,
        echo=False,
        pool_size=5,
        max_overflow=3,
        pool_timeout=10,
        pool_recycle=300,
        pool_pre_ping=True,   # prevents stale-connection errors on AWS for background threads
    )
    SyncSessionLocal = sessionmaker(
        bind=sync_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
except Exception as _e:
    # psycopg2 not installed — fallback: SyncSessionLocal = None
    sync_engine = None
    SyncSessionLocal = None