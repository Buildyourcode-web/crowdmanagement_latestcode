import asyncio
import os
import sys
from datetime import datetime, date, time as dtime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import AsyncSessionLocal, async_engine
from app.models.line_crossing import LineCrossingEvent
from app.models.crowd import CrowdSnapshot
from sqlalchemy import select, func


async def inspect():
    async with AsyncSessionLocal() as db:
        IST = timezone(timedelta(hours=5, minutes=30))
        today_ist = date(2026, 9, 15)
        start_utc = datetime.combine(today_ist, dtime.min, tzinfo=IST).astimezone(timezone.utc)
        end_utc = datetime.combine(today_ist + timedelta(days=1), dtime.min, tzinfo=IST).astimezone(timezone.utc)

        print("\n" + "=" * 80)
        print(f"📊 DAY 2 (15 SEP 2026) RECORD AUDIT — WHEN WAS EACH COUNT RECORDED?")
        print("=" * 80)

        # 1. Inspect LineCrossingEvent grouped by hour in IST
        stmt_lce = (
            select(
                LineCrossingEvent.crossing_timestamp,
                LineCrossingEvent.direction,
                LineCrossingEvent.count_delta,
                LineCrossingEvent.camera_code,
            )
            .where(
                LineCrossingEvent.crossing_timestamp >= start_utc,
                LineCrossingEvent.crossing_timestamp < end_utc,
            )
            .order_by(LineCrossingEvent.crossing_timestamp.asc())
        )
        res_lce = await db.execute(stmt_lce)
        all_crossings = res_lce.all()

        print(f"\n1️⃣  LINE CROSSING EVENTS (Exact camera gate detections for 15 Sep):")
        print(f"    Total raw crossing records found: {len(all_crossings)}")

        hourly_lce = {}
        for r in all_crossings:
            raw_ts = r.crossing_timestamp
            if raw_ts.tzinfo is None:
                raw_ts = raw_ts.replace(tzinfo=timezone.utc)
            loc_dt = raw_ts.astimezone(IST)
            h_str = f"{loc_dt.hour:02d}:00"
            if h_str not in hourly_lce:
                hourly_lce[h_str] = {
                    "in": 0, "out": 0, "count": 0,
                    "first": loc_dt.strftime("%H:%M:%S"),
                    "last": loc_dt.strftime("%H:%M:%S")
                }
            delta = int(r.count_delta or 0)
            if r.direction == "IN":
                hourly_lce[h_str]["in"] += delta
            elif r.direction == "OUT":
                hourly_lce[h_str]["out"] += delta
            hourly_lce[h_str]["count"] += 1
            hourly_lce[h_str]["last"] = loc_dt.strftime("%H:%M:%S")

        if hourly_lce:
            print(f"    {'Hour (IST)':<12} {'IN':<8} {'OUT':<8} {'Crossings':<12} {'First Seen':<12} {'Last Seen':<12}")
            print("    " + "-" * 66)
            for h in sorted(hourly_lce.keys()):
                d = hourly_lce[h]
                print(f"    {h:<12} {d['in']:<8} {d['out']:<8} {d['count']:<12} {d['first']:<12} {d['last']:<12}")
        else:
            print("    (No individual LineCrossingEvent rows found for 15 Sep)")

        # 2. Inspect CrowdSnapshot for 15 Sep
        stmt_snap = (
            select(CrowdSnapshot)
            .where(
                CrowdSnapshot.timestamp >= start_utc,
                CrowdSnapshot.timestamp < end_utc,
            )
            .order_by(CrowdSnapshot.timestamp.asc())
        )
        res_snap = await db.execute(stmt_snap)
        all_snaps = res_snap.scalars().all()

        print(f"\n2️⃣  CROWD SNAPSHOTS (Periodic / Hourly rollups in DB for 15 Sep):")
        print(f"    Total snapshot rows found: {len(all_snaps)}")
        if all_snaps:
            print(f"    {'Timestamp (IST)':<20} {'Profile ID':<22} {'Inflow':<10} {'Outflow':<10} {'People Count':<12}")
            print("    " + "-" * 76)
            for s in all_snaps:
                ts = s.timestamp
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                ist_ts = ts.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")
                print(f"    {ist_ts:<20} {s.profile_id or '-':<22} {s.inflow_rate or 0:<10} {s.outflow_rate or 0:<10} {s.people_count or 0:<12}")
        else:
            print("    (No CrowdSnapshot rows found for 15 Sep)")

        # 3. Live camera worker in-memory state
        print(f"\n3️⃣  ACTIVE CAMERA WORKERS IN-MEMORY STATE:")
        try:
            from app.frs_engine.frs_service import _camera_workers, _workers_lock
            with _workers_lock:
                workers = dict(_camera_workers)
            if workers:
                for cid, w in workers.items():
                    print(f"    • Camera: {cid:<20} | IN: {getattr(w, 'in_count', 0)} | OUT: {getattr(w, 'out_count', 0)} | Running: {getattr(w, 'running', False)}")
            else:
                print("    (No active workers registered)")
        except Exception as e:
            print(f"    (Could not inspect worker memory: {e})")

        print("=" * 80 + "\n")


def main():
    try:
        asyncio.run(inspect())
    finally:
        asyncio.run(async_engine.dispose())


if __name__ == "__main__":
    main()
