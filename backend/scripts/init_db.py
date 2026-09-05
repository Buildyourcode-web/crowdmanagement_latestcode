import asyncio
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.base import Base
from app.db.session import async_engine
from loguru import logger


async def init_database():
    logger.info("Initializing database tables for main_crowd_ai...")
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Successfully created all database tables!")
    await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_database())
