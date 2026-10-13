import asyncio
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.init_schema import ensure_database_schema
from app.db.session import async_engine
from loguru import logger


async def init_database():
    logger.info("Initializing database tables & schema for main_crowd_ai...")
    await ensure_database_schema()
    logger.info("Successfully created and verified all database tables and schema migrations!")
    await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_database())

