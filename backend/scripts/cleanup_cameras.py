import asyncio
import asyncpg
from loguru import logger

async def keep_single_camera():
    logger.info("Connecting to Supabase to update cameras...")
    conn = await asyncpg.connect(
        host="aws-0-ap-southeast-2.pooler.supabase.com",
        port=5432,
        user="postgres.qqnntcegjquiixyrxjpf",
        password="Bycai@2026$",
        database="postgres",
        statement_cache_size=0,
    )
    
    # Check total cameras
    count = await conn.fetchval("SELECT count(*) FROM cameras;")
    logger.info(f"Current camera count in Supabase: {count}")
    
    # Delete all cameras except CAM-KHB-001
    await conn.execute("DELETE FROM cameras WHERE camera_code != 'CAM-KHB-001';")
    
    # Update CAM-KHB-001 with zero people count and clean values
    await conn.execute("""
        UPDATE cameras 
        SET 
            name = 'Khairatabad Main Camera',
            label = 'Khairatabad Ganesh Main Idol View',
            status = 'online',
            ai_status = 'online',
            people_count = 0,
            fps = 24,
            latency_ms = 35,
            packet_loss_pct = 0.0,
            zone_code = 'ZONE-A'
        WHERE camera_code = 'CAM-KHB-001';
    """)
    
    new_count = await conn.fetchval("SELECT count(*) FROM cameras;")
    rows = await conn.fetch("SELECT camera_code, name, label, status, people_count FROM cameras;")
    logger.info(f"New camera count: {new_count}")
    for r in rows:
        logger.info(f" - Camera: {r['camera_code']} | {r['name']} | {r['label']} | Status: {r['status']} | Count: {r['people_count']}")
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(keep_single_camera())
