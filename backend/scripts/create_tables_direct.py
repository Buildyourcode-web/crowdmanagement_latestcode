import asyncio
import sys
import os
import asyncpg
import urllib.parse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.base import Base
from sqlalchemy.schema import CreateTable
from loguru import logger

async def create_tables_direct():
    logger.info("Connecting directly via asyncpg to Supabase...")
    conn = await asyncpg.connect(
        host="aws-0-ap-southeast-2.pooler.supabase.com",
        port=5432,
        user="postgres.qqnntcegjquiixyrxjpf",
        password="Bycai@2026$",
        database="postgres",
        statement_cache_size=0,
    )
    
    logger.info("Connected! Generating DDL statements...")
    # Generate DDL for each table
    from sqlalchemy.dialects import postgresql
    dialect = postgresql.dialect()
    
    for table in Base.metadata.sorted_tables:
        create_sql = str(CreateTable(table).compile(dialect=dialect))
        table_name = table.name
        logger.info(f"Creating table: {table_name}")
        try:
            await conn.execute(f"DROP TABLE IF EXISTS \"{table_name}\" CASCADE;")
            await conn.execute(create_sql)
            logger.info(f" ✓ Created table: {table_name}")
        except Exception as e:
            logger.error(f" ✗ Error creating {table_name}: {e}")
            
    logger.info("All tables created! Verifying...")
    rows = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;")
    tables = [r['table_name'] for r in rows]
    logger.info(f"Public tables in Supabase ({len(tables)}): {tables}")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(create_tables_direct())
