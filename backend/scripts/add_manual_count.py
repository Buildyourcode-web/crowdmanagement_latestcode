import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import AsyncSessionLocal, async_engine
from app.models.camera import Camera
from app.models.crowd import CrowdSnapshot
from app.models.event import Event
from app.models.zone import Zone
from app.services.counting_service import CanonicalCountingService
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


async def show_event_summary(event_identifier: str, target_date_str: Optional[str] = None):
    async with AsyncSessionLocal() as db:
        event = await _get_event(db, event_identifier)
        if not event:
            return

        tz = _get_timezone(event)
        now_local = datetime.now(tz)
        if target_date_str:
            try:
                eff_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            except ValueError:
                eff_date = now_local.date()
        else:
            eff_date = now_local.date()

        counting_srv = CanonicalCountingService(db)
        fest_in, fest_out, fest_occ = await counting_srv.get_festival_totals(event.id)
        today_in, today_out = await counting_srv.get_today_totals_only_db(event.id)
        hourly_items, peak_h = await counting_srv.get_hourly_breakdown(event.id, eff_date)
        daily_items, _, _, _ = await counting_srv.get_festival_daily_breakdown(event.id)

        # Cameras
        stmt_c = select(Camera).where(Camera.event_id == event.id, Camera.is_active == True).order_by(Camera.camera_code)
        cams = (await db.execute(stmt_c)).scalars().all()

        # Zones
        stmt_z = select(Zone).where(Zone.event_id == event.id).order_by(Zone.zone_code)
        zones = (await db.execute(stmt_z)).scalars().all()

        print("\n" + "=" * 76)
        print(f"📊 DATABASE SYNC & COUNT AUDIT: {event.name} ({event.code})")
        print("=" * 76)
        print(f" • Event Status:        {event.status or 'ACTIVE'}")
        print(f" • Festival Total:      {fest_in:,} Entries | {fest_out:,} Exits | {fest_occ:,} Current Occupancy")
        print(f" • Date Audited:        {eff_date} ({eff_date.strftime('%A')})")
        print(f" • Day's DB Total:      {today_in:,} Entries | {today_out:,} Exits")
        print("-" * 76)
        print(f"⏰ Hourly Breakdown for {eff_date} (Asia/Kolkata):")
        sum_h_in = 0
        sum_h_out = 0
        any_hourly = False
        for h in hourly_items:
            sum_h_in += h.entry
            sum_h_out += h.exit
            if h.entry > 0 or h.exit > 0:
                any_hourly = True
                h_num = int(h.hour[:2])
                print(f"   [{h.hour} – {(h_num+1):02d}:00]  IN: {h.entry:<6} | OUT: {h.exit:<6} | Net: {h.net_flow:<6}")
        if not any_hourly:
            print("   (No recorded entries for this date yet)")
        print(f" • Hourly Sum IN:       {sum_h_in:,} (Matches Day Total: {'✅ YES' if sum_h_in == today_in else '❌ NO'})")
        print(f" • Peak Hour:           {peak_h}")
        print("-" * 76)
        print(f"📅 Festival Daily Breakdown ({len(daily_items)} days):")
        for d in daily_items:
            if d.entry_count > 0 or d.status == "TODAY":
                print(f"   {d.label:<8} ({d.date}): {d.entry_count:<6} Entries | {d.exit_count:<6} Exits | Status: {d.status}")
        print("-" * 76)
        print(f"📹 Cameras ({len(cams)} active):")
        for c in cams:
            print(f"   • {c.camera_code:<15} ({c.name or 'Camera'}): {c.people_count or 0} people | Zone: {c.zone_code or 'N/A'}")
        if zones:
            print("-" * 76)
            print(f"🏢 Zones ({len(zones)} defined):")
            for z in zones:
                print(f"   • {z.zone_code:<10} ({z.name or z.zone_code}): {z.current_people or 0} people")
        print("=" * 76 + "\n")


def _get_timezone(event: Optional[Event] = None):
    tz_name = (event.timezone if event and event.timezone else "Asia/Kolkata").strip()
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except Exception:
        pass
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Asia/Kolkata")
    except Exception:
        pass
    # Built-in fixed offset UTC+05:30 (IST) — works anywhere without tzdata package
    return timezone(timedelta(hours=5, minutes=30))


async def _get_event(db, event_identifier: str) -> Optional[Event]:
    is_uuid = False
    try:
        evt_uuid = uuid.UUID(event_identifier)
        is_uuid = True
    except ValueError:
        pass

    if is_uuid:
        stmt = select(Event).where(Event.id == evt_uuid)
        res = await db.execute(stmt)
        event = res.scalars().first()
    else:
        clean_id = event_identifier.strip().lower()
        # 1. Exact match by code or name
        stmt = select(Event).where(
            or_(
                func.lower(Event.code) == clean_id,
                func.lower(Event.name) == clean_id,
            )
        )
        res = await db.execute(stmt)
        event = res.scalars().first()

        # 2. Substring match (e.g. 'Khairatabad' matches 'Khairatabad Ganesh Festival 2026')
        if not event:
            stmt = select(Event).where(
                or_(
                    Event.code.ilike(f"%{clean_id}%"),
                    Event.name.ilike(f"%{clean_id}%"),
                )
            ).order_by(Event.created_at.desc()).limit(1)
            res = await db.execute(stmt)
            event = res.scalars().first()

    if not event:
        print(f"❌ Error: Event '{event_identifier}' not found in database.")
    return event


async def insert_manual_count(
    event_identifier: str,
    inflow: int,
    outflow: int,
    set_total_inflow: Optional[int] = None,
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

        # Time parsing with zero-dependency fallback
        tz = _get_timezone(event)
        tz_name = (event.timezone or "Asia/Kolkata").strip()

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

        dt_utc = dt_local.astimezone(timezone.utc)

        # Fetch active event cameras
        stmt_cams = select(Camera).where(Camera.event_id == event.id, Camera.is_active == True).order_by(Camera.camera_code)
        res_cams = await db.execute(stmt_cams)
        event_cameras: List[Camera] = res_cams.scalars().all()

        target_cam = None
        if camera_target:
            target_cam = next((c for c in event_cameras if c.camera_code.lower() == camera_target.strip().lower() or str(c.id) == camera_target.strip()), None)
            if not target_cam:
                stmt_single = select(Camera).where(or_(Camera.camera_code.ilike(camera_target.strip()), Camera.id == uuid.UUID(camera_target) if _is_uuid(camera_target) else False))
                res_s = await db.execute(stmt_single)
                target_cam = res_s.scalars().first()

            if not target_cam:
                print(f"❌ Error: Camera '{camera_target}' not found!")
                await list_event_cameras(event_identifier)
                return

        # Handle --set-total: calculate existing count for that hour and compute delta
        if set_total_inflow is not None:
            h_start_local = dt_local.replace(minute=0, second=0, microsecond=0)
            h_end_local = h_start_local + timedelta(hours=1)
            h_start_utc = h_start_local.astimezone(timezone.utc)
            h_end_utc = h_end_local.astimezone(timezone.utc)

            counting_srv = CanonicalCountingService(db)
            existing_inflow, _ = await counting_srv.get_durable_counts(
                event_id=event.id,
                camera_id=target_cam.id if target_cam else None,
                start_time=h_start_utc,
                end_time=h_end_utc,
            )

            delta = set_total_inflow - existing_inflow
            print(f"\n🔍 Target Mode (--set-total {set_total_inflow}):")
            print(f" • Hour Window:        {h_start_local.strftime('%H:00')} – {h_end_local.strftime('%H:00')} IST ({dt_local.strftime('%Y-%m-%d')})")
            print(f" • Existing Count:     {existing_inflow}")
            print(f" • Desired Total:      {set_total_inflow}")
            print(f" • Calculated Delta:   {'+' if delta >= 0 else ''}{delta}")

            if delta == 0:
                print(f"✅ The count for this hour is already exactly {set_total_inflow}. No changes needed.\n")
                return
            elif delta < 0:
                print(f"⚠️ Warning: Target count ({set_total_inflow}) is lower than existing ({existing_inflow}).")
                # To reduce, we insert a negative delta or prompt
                inflow = delta
            else:
                inflow = delta

        snapshots_to_create = []

        if target_cam:
            snapshots_to_create.append({
                "camera": target_cam,
                "inflow": inflow,
                "outflow": outflow,
            })
        elif distribute_all and event_cameras:
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
            first_cam = event_cameras[0] if event_cameras else None
            snapshots_to_create.append({
                "camera": first_cam,
                "inflow": inflow,
                "outflow": outflow,
            })

        print(f"\n=======================================================")
        print(f"📝 Inserting Manual Count for {event.name} ({event.code})")
        print(f" • Time: {dt_local.strftime('%Y-%m-%d %H:%M:%S')} ({tz_name})")
        print(f" • Total Entries Delta: {'+' if inflow >= 0 else ''}{inflow}")
        print(f" • Total Exits Delta:   {'+' if outflow >= 0 else ''}{outflow}")
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

            # Update Camera record if applicable
            if cam:
                cam.people_count = max(0, (cam.people_count or 0) + (c_in - c_out))
                cam.last_seen_at = dt_utc
                db.add(cam)

            # Update Zone record if applicable
            if z_id:
                from app.models.zone import Zone
                z_res = await db.execute(select(Zone).where(Zone.id == z_id))
                zone_obj = z_res.scalars().first()
                if zone_obj:
                    zone_obj.current_people = max(0, (zone_obj.current_people or 0) + (c_in - c_out))
                    db.add(zone_obj)

            print(f" • Camera {c_code:<12} (Zone: {z_code}): {'+' if c_in >= 0 else ''}{c_in} Entries, {'+' if c_out >= 0 else ''}{c_out} Exits")

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

        if args.summary or (args.inflow == 0 and args.outflow == 0 and args.set_total is None):
            # If no count deltas specified or summary requested, display full audit report
            date_arg = None
            if args.time:
                try:
                    date_arg = args.time.strip().split()[0]
                except Exception:
                    pass
            await show_event_summary(args.event, date_arg)
            return

        await insert_manual_count(
            event_identifier=args.event,
            inflow=args.inflow,
            outflow=args.outflow,
            set_total_inflow=args.set_total,
            camera_target=args.camera,
            distribute_all=args.distribute,
            custom_time_str=args.time,
            zone_code_override=args.zone,
        )
    finally:
        await async_engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Add manual counts, audit totals, and distribute across cameras")
    parser.add_argument("--list", action="store_true", help="List all available events and codes")
    parser.add_argument("--event", type=str, help="Event code, name, or UUID")
    parser.add_argument("--summary", "--audit", dest="summary", action="store_true", help="Display full audit report and database sync verification")
    parser.add_argument("--list-cameras", action="store_true", help="List all cameras assigned to this event")
    parser.add_argument("--camera", type=str, default=None, help="Target a specific camera code (e.g. CAM-001)")
    parser.add_argument("--distribute", action="store_true", help="Distribute the counts evenly across all active cameras of the event")
    parser.add_argument("--in", dest="inflow", type=int, default=0, help="Delta entries to add (+N)")
    parser.add_argument("--out", dest="outflow", type=int, default=0, help="Delta exits to add (+N)")
    parser.add_argument("--set-total", dest="set_total", type=int, default=None, help="Set the exact target total for that hour (automatically computes delta)")
    parser.add_argument("--time", type=str, default=None, help="Timestamp in IST 'YYYY-MM-DD HH:MM:SS' (defaults to current time)")
    parser.add_argument("--zone", type=str, default=None, help="Optional Zone code override (e.g. ZONE-A)")

    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()


