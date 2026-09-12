import asyncio
import os
import sys
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
settings.APP_ENV = "testing"
from app.db.base import Base
from app.dependencies import get_db
from app.main import app
from app.models.role import Permission, Role
from app.models.user import User
from app.security.jwt import create_access_token
from app.security.password import get_password_hash
from app.security.permissions import DEFAULT_ROLE_PERMISSIONS

# SQLite async in-memory with StaticPool so all connections share the same memory database
test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def superadmin_token(db_session: AsyncSession) -> str:
    from app.models.event import Event
    from datetime import datetime, timezone
    stmt_ev = select(Event).where(Event.code == "KHB-2026")
    ev = (await db_session.execute(stmt_ev)).scalars().first()
    if not ev:
        ev = Event(
            code="KHB-2026",
            name="Khairatabad Ganesh Utsav 2026",
            year=2026,
            status="ACTIVE",
            is_active=True,
            start_date=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc),
        )
        db_session.add(ev)
        await db_session.flush()

    # Check if role exists
    stmt_role = select(Role).where(Role.code == "SUPER_ADMIN")
    role = (await db_session.execute(stmt_role)).scalars().first()
    if not role:
        role = Role(code="SUPER_ADMIN", name="Super Admin", description="Full Access")
        db_session.add(role)
        await db_session.flush()

    stmt_user = select(User).where(User.username == "testadmin")
    user = (await db_session.execute(stmt_user)).scalars().first()
    if not user:
        user = User(
            username="testadmin",
            email="testadmin@byc.gov.in",
            password_hash=get_password_hash("testadmin123"),
            full_name="Test Administrator",
            role_id=role.id,
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()

    all_perms = []
    for perms in DEFAULT_ROLE_PERMISSIONS.values():
        all_perms.extend(perms)

    token = create_access_token(
        subject=str(user.id),
        role="SUPER_ADMIN",
        permissions=list(set(all_perms)),
    )
    return token
