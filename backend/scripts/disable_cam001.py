import asyncio
import sys
sys.path.insert(0, "backend")

from app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as session:
        await session.execute(text("UPDATE cameras SET enabled = false WHERE camera_code = 'CAM-KHB-001'"))
        await session.commit()
        print("CAM-KHB-001 disabled successfully.")

if __name__ == "__main__":
    asyncio.run(main())
