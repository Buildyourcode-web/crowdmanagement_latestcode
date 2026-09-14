import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import AsyncSessionLocal, async_engine
from app.models.camera import Camera
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
            # Query camera count for event
            c_stmt = select(func.count(Camera.id)).where(Camera.event_id == e.id, Camera.is_active == True)
            c_res = await db.execute(c_stmt)
            cam_count = c_res.scalar() or 0
            print(f" • Event: {e.name:<32} | Code: {e.code:<12} | Cameras: {cam_count:<2} | ID: {e.id}")
        print("====================================\n")


async def list_event_cameras(event_identifier: str):
    async with AsyncSessionLocal() as db:
        event = await _get_event(db, event_identifier)
        if not event:
            return

        stmt = select(Camera).where(Camera.event_id == event.id, Camera.is_active == True).order_by(Camera.camera_code)
        res = await db.execute(stmt)
        cams = res.scalars().all()

        print(f"\n=== Cameras for Event: {event.name} ({event.code}) ===")
        if not cams:
            print(" (No active cameras assigned to this event)")
        for c in cams:
            print(f" • Code: {c.camera_code:<12} | Name: {c.name:<25} | Zone: {c.zone_code or 'N/A':<8} | ID: {c.id}")
        print("===================================================\n")


async def _get_event(db, event_identifier: str) -> Optional[Event]:
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
    return event


async def insert_manual_count(
    event_identifier: str,
    inflow: int,
    outflow: int,
    camera_target: Optional[str] = None,
    distribute_all: bool = False,
    custom_time_str: Optional[str] = None,
    zone_code_override: Optional[str] = None,
):
    async with AsyncSessionLocal() as db:
        event = await _get_event(db, event_identifier)
        if not event:
            await list_available_events()
            return

        # Time parsing
        tz_name = (event.timezone or "Asia/Kolkata").strip()
        tz = ZoneInfo(tz_name)

        if custom_time_str:
            try:
                dt_local = datetime.strptime(custom_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
            except ValueError:
                try:
                    dt_local = datetime.strptime(custom_time_str, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
                except ValueError:
                    print("❌ Error: Invalid timestamp format. Use 'YYYY-MM-DD HH:MM:SS' (e.g. '2026-09-14 10:30:00')")
                    return
        else:
            dt_local = datetime.now(tz)

        dt_utc = dt_local.astimezone(ZoneInfo("UTC"))

        # Fetch active event cameras
        stmt_cams = select(Camera).where(Camera.event_id == event.id, Camera.is_active == True).order_by(Camera.camera_code)
        res_cams = await db.execute(stmt_cams)
        event_cameras: List[Camera] = res_cams.scalars().all()

        snapshots_to_create = []

        if camera_target:
            # Case 1: Specific camera selected
            target_cam = next((c for c in event_cameras if c.camera_code.lower() == camera_target.strip().lower() or str(c.id) == camera_target.strip()), None)
            if not target_cam:
                # Also check DB globally if camera wasn't scoped
                stmt_single = select(Camera).where(or_(Camera.camera_code.ilike(camera_target.strip()), Camera.id == uuid.UUID(camera_target) if _is_uuid(camera_target) else False))
                res_s = await db.execute(stmt_single)
                target_cam = res_s.scalars().first()

            if not target_cam:
                print(f"❌ Error: Camera '{camera_target}' not found!")
                await list_event_cameras(event_identifier)
                return

            snapshots_to_create.append({
                "camera": target_cam,
                "inflow": inflow,
                "outflow": outflow,
            })

        elif distribute_all and event_cameras:
            # Case 2: Distribute evenly across all active cameras of the event
            n = len(event_cameras)
            base_in, rem_in = divmod(inflow, n)
            base_out, rem_out = divmod(outflow, n)

            for i, cam in enumerate(event_cameras):
                c_in = base_in + (1 if i < rem_in else 0)
                c_out = base_out + (1 if i < rem_out else 0)
                snapshots_to_create.append({
                    "camera": cam,
                    "inflow": c_in,
                    "outflow": c_out,
                })

        else:
            # Case 3: Event-level manual aggregate (or default single camera if exists)
            first_cam = event_cameras[0] if event_cameras else None
            snapshots_to_create.append({
                "camera": first_cam,
                "inflow": inflow,
                "outflow": outflow,
            })

        print(f"\n=======================================================")
        print(f"📝 Inserting Manual Count for {event.name} ({event.code})")
        print(f" • Time: {dt_local.strftime('%Y-%m-%d %H:%M:%S')} ({tz_name})")
        print(f" • Total Requested: +{inflow} Entries, +{outflow} Exits")
        print(f"-------------------------------------------------------")

        for item in snapshots_to_create:
            cam: Optional[Camera] = item["camera"]
            c_in = item["inflow"]
            c_out = item["outflow"]
            z_code = zone_code_override or (cam.zone_code if cam and cam.zone_code else "ZONE-A")
            z_id = cam.zone_id if cam else None
            c_code = cam.camera_code if cam else "MANUAL_ENTRY"
            c_id = cam.id if cam else None

            snap = CrowdSnapshot(
                id=uuid.uuid4(),
                event_id=event.id,
                zone_id=z_id,
                zone_code=z_code,
                camera_id=c_id,
                camera_code=c_code,
                profile_id="MANUAL_ENTRY",
                timestamp=dt_utc,
                people_count=max(0, c_in - c_out),
                density=0.0,
                inflow_rate=c_in,
                outflow_rate=c_out,
                occupancy_percentage=0.0,
                risk_level="LOW",
                risk_score=0.0,
            )
            db.add(snap)
            print(f" • Camera {c_code:<12} (Zone: {z_code}): +{c_in} Entries, +{c_out} Exits")

        await db.commit()
        print(f"=======================================================\n✅ Successfully committed to database!\n")


def _is_uuid(val: str) -> bool:
    try:
        uuid.UUID(val)
        return True
    except Exception:
        return False


async def run(args):
    try:
        if args.list:
            await list_available_events()
            return

        if not args.event:
            await list_available_events()
            print("Tip: Run with --event <CODE> --in <COUNT> to add entries.")
            return

        if args.list_cameras:
            await list_event_cameras(args.event)
            return

        await insert_manual_count(
            event_identifier=args.event,
            inflow=args.inflow,
            outflow=args.outflow,
            camera_target=args.camera,
            distribute_all=args.distribute,
            custom_time_str=args.time,
            zone_code_override=args.zone,
        )
    finally:
        await async_engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Add manual counts and distribute across cameras")
    parser.add_argument("--list", action="store_true", help="List all available events and codes")
    parser.add_argument("--event", type=str, help="Event code, name, or UUID")
    parser.add_argument("--list-cameras", action="store_true", help="List all cameras assigned to this event")
    parser.add_argument("--camera", type=str, default=None, help="Target a specific camera code (e.g. CAM-001)")
    parser.add_argument("--distribute", action="store_true", help="Distribute the counts evenly across all active cameras of the event")
    parser.add_argument("--in", dest="inflow", type=int, default=0, help="Number of entries to add (inflow)")
    parser.add_argument("--out", dest="outflow", type=int, default=0, help="Number of exits to add (outflow)")
    parser.add_argument("--time", type=str, default=None, help="Timestamp in IST 'YYYY-MM-DD HH:MM:SS' (defaults to current time)")
    parser.add_argument("--zone", type=str, default=None, help="Optional Zone code override (e.g. ZONE-A)")

    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()

