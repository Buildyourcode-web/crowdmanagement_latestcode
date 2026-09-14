import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import AsyncSessionLocal, async_engine
from app.models.crowd import CrowdSnapshot
from app.models.event import Event
from sqlalchemy import select, or_, func


async def list_available_events():
    async with AsyncSessionLocal() as db:
        stmt = select(Event).order_by(Event.name)
        res = await db.execute(stmt)
        events = res.scalars().all()
        print("\n=== Available Events in Database ===")
        for e in events:
            print(f" • Name: {e.name:<35} | Code: {e.code:<15} | ID: {e.id}")
        print("====================================\n")


async def insert_manual_count(
    event_identifier: str,
    inflow: int,
    outflow: int,
    custom_time_str: str = None,
    zone_code: str = "ZONE-A",
):
    async with AsyncSessionLocal() as db:
        # Find event
        is_uuid = False
        try:
            evt_uuid = uuid.UUID(event_identifier)
            is_uuid = True
        except ValueError:
            pass

        if is_uuid:
            stmt = select(Event).where(Event.id == evt_uuid)
        else:
            stmt = select(Event).where(
                or_(
                    func.lower(Event.code) == event_identifier.strip().lower(),
                    func.lower(Event.name) == event_identifier.strip().lower(),
                )
            )

        res = await db.execute(stmt)
        event = res.scalars().first()
        if not event:
            print(f"❌ Error: Event '{event_identifier}' not found in database.")
            await list_available_events()
            return

        # Determine target timestamp in UTC
        tz_name = (event.timezone or "Asia/Kolkata").strip()
        tz = ZoneInfo(tz_name)

        if custom_time_str:
            try:
                dt_local = datetime.strptime(custom_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
            except ValueError:
                try:
                    dt_local = datetime.strptime(custom_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
                except ValueError:
                    print("❌ Error: Invalid timestamp format. Please use 'YYYY-MM-DD HH:MM:SS' (e.g. '2026-09-14 10:30:00')")
                    return
        else:
            dt_local = datetime.now(tz)

        dt_utc = dt_local.astimezone(ZoneInfo("UTC"))

        snap = CrowdSnapshot(
            id=uuid.uuid4(),
            event_id=event.id,
            zone_code=zone_code,
            camera_code="MANUAL_ENTRY",
            profile_id="MANUAL_ENTRY",
            timestamp=dt_utc,
            people_count=max(0, inflow - outflow),
            density=0.0,
            inflow_rate=inflow,
            outflow_rate=outflow,
            occupancy_percentage=0.0,
            risk_level="LOW",
            risk_score=0.0,
        )
        db.add(snap)
        await db.commit()

        print("\n✅ Successfully added manual count!")
        print(f" • Event:        {event.name} ({event.code})")
        print(f" • Entries (+):  {inflow}")
        print(f" • Exits (-):    {outflow}")
        print(f" • Local Time:   {dt_local.strftime('%Y-%m-%d %H:%M:%S')} ({tz_name})")
        print(f" • UTC Time:     {dt_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f" • Zone:         {zone_code}\n")


async def run(args):
    try:
        if args.list or not args.event:
            await list_available_events()
            if not args.event:
                print("Tip: Run with --event <CODE> --in <COUNT> to add entries.")
                return

        await insert_manual_count(
            event_identifier=args.event,
            inflow=args.inflow,
            outflow=args.outflow,
            custom_time_str=args.time,
            zone_code=args.zone,
        )
    finally:
        await async_engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Add manual counts to an event in the database")
    parser.add_argument("--list", action="store_true", help="List all available events and codes")
    parser.add_argument("--event", type=str, help="Event code, name, or UUID")
    parser.add_argument("--in", dest="inflow", type=int, default=0, help="Number of entries to add (inflow)")
    parser.add_argument("--out", dest="outflow", type=int, default=0, help="Number of exits to add (outflow)")
    parser.add_argument("--time", type=str, default=None, help="Timestamp in IST 'YYYY-MM-DD HH:MM:SS' (defaults to current time)")
    parser.add_argument("--zone", type=str, default="ZONE-A", help="Zone code (default: ZONE-A)")

    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()

