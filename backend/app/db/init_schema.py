"""
init_schema.py — Safe, idempotent database schema synchronization.

Ensures that:
1. All tables defined in Base metadata (including locations, location_verifications, etc.) exist.
2. Additive columns (such as events.location_id, cameras.is_active, cameras.event_id)
   are safely added to existing tables if they were created prior to the migrations.
3. Relevant indexes exist for high-performance lookups.
4. Alembic version table is stamped so subsequent migrations run cleanly.
"""

from loguru import logger
from sqlalchemy import text
from app.db.base import Base
from app.db.session import async_engine

SAFE_DDL_STATEMENTS = [
    # 1. Locations table
    """
    CREATE TABLE IF NOT EXISTS locations (
        id UUID PRIMARY KEY,
        code VARCHAR(50) NOT NULL UNIQUE,
        name VARCHAR(150) NOT NULL,
        city VARCHAR(100) NOT NULL,
        state VARCHAR(100) NOT NULL,
        email VARCHAR(255) NOT NULL,
        access_code_hash VARCHAR(255) NOT NULL,
        status VARCHAR(50) DEFAULT 'ACTIVE' NOT NULL,
        is_active BOOLEAN DEFAULT TRUE NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
        created_by VARCHAR(100),
        updated_by VARCHAR(100)
    );
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_locations_code ON locations (code);",
    "CREATE INDEX IF NOT EXISTS ix_locations_status ON locations (status);",

    # 2. Location verifications table
    """
    CREATE TABLE IF NOT EXISTS location_verifications (
        id UUID PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        location_code VARCHAR(50),
        code_hash VARCHAR(255) NOT NULL,
        purpose VARCHAR(50) NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        is_used BOOLEAN DEFAULT FALSE NOT NULL,
        attempts INTEGER DEFAULT 0 NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_location_verifications_email ON location_verifications (email);",

    # 3. Ensure events has location_id
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'events') THEN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'events' AND column_name = 'location_id') THEN
                ALTER TABLE events ADD COLUMN location_id UUID REFERENCES locations(id) ON DELETE SET NULL;
            END IF;
        END IF;
    END $$;
    """,
    "CREATE INDEX IF NOT EXISTS ix_events_location_id ON events (location_id);",

    # 4. Ensure cameras has lifecycle and scoping columns
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'cameras') THEN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'cameras' AND column_name = 'is_active') THEN
                ALTER TABLE cameras ADD COLUMN is_active BOOLEAN DEFAULT TRUE NOT NULL;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'cameras' AND column_name = 'active_from') THEN
                ALTER TABLE cameras ADD COLUMN active_from TIMESTAMPTZ;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'cameras' AND column_name = 'removed_at') THEN
                ALTER TABLE cameras ADD COLUMN removed_at TIMESTAMPTZ;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'cameras' AND column_name = 'event_id') THEN
                ALTER TABLE cameras ADD COLUMN event_id UUID REFERENCES events(id) ON DELETE SET NULL;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'cameras' AND column_name = 'site_id') THEN
                ALTER TABLE cameras ADD COLUMN site_id UUID REFERENCES sites(id) ON DELETE SET NULL;
            END IF;
        END IF;
    END $$;
    """,
    "CREATE INDEX IF NOT EXISTS ix_cameras_is_active ON cameras (is_active);",
    "CREATE INDEX IF NOT EXISTS ix_cameras_event_active ON cameras (event_id, is_active);",

    # 5. Alembic version table alignment
    """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'alembic_version') THEN
            IF NOT EXISTS (SELECT 1 FROM alembic_version WHERE version_num = 'g8c9d0e1f2a3') THEN
                DELETE FROM alembic_version;
                INSERT INTO alembic_version (version_num) VALUES ('g8c9d0e1f2a3');
            END IF;
        END IF;
    END $$;
    """,
]


async def ensure_database_schema():
    """
    Synchronizes the database schema safely without dropping any data.
    Callable on FastAPI application startup and in scripts/init_db.py.
    """
    logger.info("[DB-Init] Verifying database schema integrity...")
    try:
        async with async_engine.begin() as conn:
            # 1. Create any missing tables registered in SQLAlchemy models
            await conn.run_sync(Base.metadata.create_all)

            # 2. Execute safe additive DDL statements
            for stmt in SAFE_DDL_STATEMENTS:
                await conn.execute(text(stmt))

        logger.info("[DB-Init] Database schema verified and synchronized successfully.")
    except Exception as e:
        logger.error(f"[DB-Init] Schema synchronization notice (non-fatal): {e}")
