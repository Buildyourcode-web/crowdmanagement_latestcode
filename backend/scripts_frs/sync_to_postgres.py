import sys, os, sqlite3, json, asyncio
sys.path.insert(0, os.path.abspath("."))
from datetime import datetime, timezone
import numpy as np
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.frs import FRSReferenceProfile

async def sync_profiles_to_pg():
    if AsyncSessionLocal is None:
        print("AsyncSessionLocal is None")
        return

    # Read distinct profiles and their first embedding from SQLite
    src_db = os.path.abspath("data/frs/embeddings.db")
    conn = sqlite3.connect(src_db)
    cur = conn.cursor()
    cur.execute("""
        SELECT person_id, person_name, category, source_file, embedding
        FROM face_embeddings
        GROUP BY person_id
    """)
    rows = cur.fetchall()
    conn.close()
    print(f"Read {len(rows)} distinct profiles from SQLite")

    async with AsyncSessionLocal() as session:
        # Check existing reference_ids
        existing_stmt = select(FRSReferenceProfile.reference_id)
        res = await session.execute(existing_stmt)
        existing_ids = set(res.scalars().all())
        print(f"Existing profiles in PostgreSQL: {len(existing_ids)}")

        batch = []
        added_count = 0
        now_date_str = datetime.now(timezone.utc).strftime("%d %b %Y")

        for pid, name, cat, src_file, blob in rows:
            ref_id = f"WL-{pid}"
            if ref_id in existing_ids:
                continue

            # Parse embedding
            emb_list = None
            if blob:
                try:
                    arr = np.frombuffer(blob, dtype=np.float32)
                    if arr.shape[0] == 512:
                        emb_list = [round(float(x), 5) for x in arr]
                except Exception:
                    pass

            display_category = "Pickpocket Watchlist" if "pick" in str(cat).lower() else "Authorized Watchlist"

            prof = FRSReferenceProfile(
                reference_id=ref_id,
                reference_code=ref_id,
                display_name=str(name),
                category=display_category,
                status="ACTIVE",
                active=True,
                reference_image_path=str(src_file) if src_file else "",
                embedding_vector=emb_list,
                embedding_model="buffalo_sc",
                embedding_version="1.0.0",
                created_by="Batch Enrollment 2019",
                last_updated_date=now_date_str,
            )
            session.add(prof)
            added_count += 1
            if added_count % 250 == 0:
                await session.commit()
                print(f"  Committed {added_count} profiles to PostgreSQL...")

        await session.commit()
        print(f"Successfully synced {added_count} new reference profiles to PostgreSQL!")

        # Verify new count
        cnt_stmt = select(FRSReferenceProfile.id)
        res = await session.execute(cnt_stmt)
        total_pg = len(res.scalars().all())
        print(f"Total reference profiles in PostgreSQL now: {total_pg}")

asyncio.run(sync_profiles_to_pg())
