import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.base import Base
from app.db.session import async_engine
from loguru import logger

async def test_supabase_init():
    logger.info("Connecting to Supabase...")
    async with async_engine.connect() as conn:
        res = await conn.exec_driver_sql("SELECT version();")
        v = res.scalar()
        logger.info(f"Connected to Supabase! Version: {v[:40]}")
        
        tables_res = await conn.exec_driver_sql("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
        tables = [r[0] for r in tables_res.fetchall()]
        logger.info(f"Existing public tables: {tables}")

    logger.info(f"Total model tables to create: {len(Base.metadata.tables)}")
    for t in Base.metadata.sorted_tables:
        logger.info(f" - Table: {t.name}")

    logger.info("Executing Base.metadata.create_all...")
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Successfully created all tables in Supabase!")
    
    async with async_engine.connect() as conn:
        tables_res = await conn.exec_driver_sql("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
        tables = [r[0] for r in tables_res.fetchall()]
        logger.info(f"Updated public tables in Supabase: {tables}")

    await async_engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_supabase_init())
