import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

# Add backend directory to sys.path
sys.path.insert(0, r"c:\khairatabad_ganesh\backend")

from app.db.session import AsyncSessionLocal, async_engine
from app.models.camera import Camera
from app.models.crowd import CrowdSnapshot
from app.models.event import Event
from app.models.zone import Zone
from app.services.analytics_service import AnalyticsService
from app.services.counting_service import CanonicalCountingService
from app.services.dashboard_service import DashboardService
from scripts.add_manual_count import insert_manual_count
from sqlalchemy import delete, func, select


async def test_case_suite():
    print("=" * 80)
    print("RUNNING COMPLETE EDGE-CASE TEST SUITE")
    print("=" * 80)

    tz = ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(tz)
    today_date_str = now_ist.strftime("%Y-%m-%d")

    # 1. Fetch event
    async with AsyncSessionLocal() as db:
        stmt = select(Event).where(Event.code == "KHB-2026").limit(1)
        res = await db.execute(stmt)
        event = res.scalars().first()
        if not event:
            stmt = select(Event).order_by(Event.created_at.desc()).limit(1)
            event = (await db.execute(stmt)).scalars().first()

        print(f"[EVENT] {event.name} (Code: {event.code}, ID: {event.id})")
        print(f"[TIME] Current IST: {now_ist.strftime('%Y-%m-%d %H:%M:%S')}")

        # Fetch cameras
        stmt_c = select(Camera).where(Camera.event_id == event.id, Camera.is_active == True).order_by(Camera.camera_code)
        cams = (await db.execute(stmt_c)).scalars().all()
        print(f"[CAMERAS] ({len(cams)} active): {[c.camera_code for c in cams]}")
        first_cam = cams[0] if cams else None

        # Clean prior test snapshots
        await db.execute(delete(CrowdSnapshot).where(CrowdSnapshot.profile_id == "MANUAL_ENTRY"))
        await db.commit()

        counting_srv = CanonicalCountingService(db)
        base_today_in, base_today_out = await counting_srv.get_today_totals_only_db(event.id)
        base_fest_in, base_fest_out, _ = await counting_srv.get_festival_totals(event.id)
        init_h_items, _ = await counting_srv.get_hourly_breakdown(event.id, now_ist.date())
        base_07_in = next((h.entry for h in init_h_items if h.hour == "07:00"), 0)
        base_14_in = next((h.entry for h in init_h_items if h.hour == "14:00"), 0)
        print(f"[BASELINE] Today: in={base_today_in}, out={base_today_out} | Festival: in={base_fest_in}, out={base_fest_out}")
        print(f"[BASELINE] Hour 07:00 in={base_07_in}, Hour 14:00 in={base_14_in}")

    # =========================================================================
    # TEST 1: Direct Count Addition (e.g. 340 entries at 07:30 IST)
    # =========================================================================
    print("\n--- TEST 1: Direct Count Addition (+340 entries at 07:30 IST) ---")
    await insert_manual_count(
        event_identifier=event.code,
        inflow=340,
        outflow=40,
        camera_target=first_cam.camera_code if first_cam else None,
        custom_time_str=f"{today_date_str} 07:30:00",
    )

    async with AsyncSessionLocal() as db:
        counting_srv = CanonicalCountingService(db)
        t_in, t_out = await counting_srv.get_today_totals_only_db(event.id)
        h_items, _ = await counting_srv.get_hourly_breakdown(event.id, now_ist.date())
        h_07 = next((h for h in h_items if h.hour == "07:00"), None)

        print(f" -> Today in: {t_in} (Expected >= {base_today_in + 340})")
        print(f" -> 07:00 hour in: {h_07.entry if h_07 else 0} (Expected: {base_07_in + 340})")
        assert t_in >= base_today_in + 340, f"Today total mismatch: {t_in}"
        assert h_07 and h_07.entry == base_07_in + 340, f"07:00 hour mismatch: {h_07}"
        print(">>> TEST 1 PASSED <<<")

    # =========================================================================
    # TEST 2: Incremental Delta on existing hour (340 + 200 = 540)
    # =========================================================================
    print("\n--- TEST 2: Incremental Delta Addition (+200 at 07:45 IST -> 540) ---")
    await insert_manual_count(
        event_identifier=event.code,
        inflow=200,
        outflow=0,
        camera_target=first_cam.camera_code if first_cam else None,
        custom_time_str=f"{today_date_str} 07:45:00",
    )

    async with AsyncSessionLocal() as db:
        counting_srv = CanonicalCountingService(db)
        t_in, _ = await counting_srv.get_today_totals_only_db(event.id)
        h_items, _ = await counting_srv.get_hourly_breakdown(event.id, now_ist.date())
        h_07 = next((h for h in h_items if h.hour == "07:00"), None)

        print(f" -> Today in: {t_in} (Expected >= {base_today_in + 540})")
        print(f" -> 07:00 hour in: {h_07.entry if h_07 else 0} (Expected: {base_07_in + 540})")
        assert t_in >= base_today_in + 540, f"Today total mismatch: {t_in}"
        assert h_07 and h_07.entry == base_07_in + 540, f"07:00 hour mismatch: {h_07}"
        print(">>> TEST 2 PASSED <<<")

    # =========================================================================
    # TEST 3: Target Mode Setting (--set-total 800)
    # =========================================================================
    print("\n--- TEST 3: Target Total Mode (--set-total 800 at 07:00 IST -> injects +260) ---")
    await insert_manual_count(
        event_identifier=event.code,
        inflow=0,
        outflow=0,
        set_total_inflow=800,
        camera_target=first_cam.camera_code if first_cam else None,
        custom_time_str=f"{today_date_str} 07:30:00",
    )

    async with AsyncSessionLocal() as db:
        counting_srv = CanonicalCountingService(db)
        h_items, _ = await counting_srv.get_hourly_breakdown(event.id, now_ist.date())
        h_07 = next((h for h in h_items if h.hour == "07:00"), None)

        print(f" -> 07:00 hour in: {h_07.entry if h_07 else 0} (Expected: 800)")
        assert h_07 and h_07.entry == 800, f"07:00 hour mismatch: {h_07}"
        print(">>> TEST 3 PASSED <<<")

    # =========================================================================
    # TEST 4: Target Mode Already at Target (No-op)
    # =========================================================================
    print("\n--- TEST 4: Target Mode when already at target (--set-total 800 -> no-op) ---")
    await insert_manual_count(
        event_identifier=event.code,
        inflow=0,
        outflow=0,
        set_total_inflow=800,
        camera_target=first_cam.camera_code if first_cam else None,
        custom_time_str=f"{today_date_str} 07:30:00",
    )

    async with AsyncSessionLocal() as db:
        counting_srv = CanonicalCountingService(db)
        h_items, _ = await counting_srv.get_hourly_breakdown(event.id, now_ist.date())
        h_07 = next((h for h in h_items if h.hour == "07:00"), None)

        print(f" -> 07:00 hour in: {h_07.entry if h_07 else 0} (Expected: 800)")
        assert h_07 and h_07.entry == 800, f"07:00 hour mismatch: {h_07}"
        print(">>> TEST 4 PASSED <<<")

    # =========================================================================
    # TEST 5: Even Camera Distribution (--distribute 500 across all cameras)
    # =========================================================================
    print(f"\n--- TEST 5: Camera Distribution (--distribute 500 across {len(cams)} cameras at 14:00 IST) ---")
    await insert_manual_count(
        event_identifier=event.code,
        inflow=500,
        outflow=50,
        distribute_all=True,
        custom_time_str=f"{today_date_str} 14:00:00",
    )

    async with AsyncSessionLocal() as db:
        counting_srv = CanonicalCountingService(db)
        h_items, _ = await counting_srv.get_hourly_breakdown(event.id, now_ist.date())
        h_14 = next((h for h in h_items if h.hour == "14:00"), None)

        print(f" -> 14:00 hour in: {h_14.entry if h_14 else 0} (Expected: 500)")
        assert h_14 and h_14.entry == 500, f"14:00 hour mismatch: {h_14}"
        print(">>> TEST 5 PASSED <<<")

    # =========================================================================
    # TEST 6: Strict Date Boundary & Midnight Isolation Check
    # =========================================================================
    print("\n--- TEST 6: Date & Midnight Boundary Isolation (23:55 yesterday vs 00:00 today) ---")
    yesterday_date = now_ist.date() - timedelta(days=1)
    yesterday_str = yesterday_date.strftime("%Y-%m-%d")

    await insert_manual_count(
        event_identifier=event.code,
        inflow=150,
        outflow=0,
        camera_target=first_cam.camera_code if first_cam else None,
        custom_time_str=f"{yesterday_str} 23:55:00",
    )

    async with AsyncSessionLocal() as db:
        counting_srv = CanonicalCountingService(db)
        y_items, _ = await counting_srv.get_hourly_breakdown(event.id, yesterday_date)
        y_23 = next((h for h in y_items if h.hour == "23:00"), None)
        t_items, _ = await counting_srv.get_hourly_breakdown(event.id, now_ist.date())
        t_00 = next((h for h in t_items if h.hour == "00:00"), None)

        print(f" -> Yesterday 23:00 hour: {y_23.entry if y_23 else 0} (Expected: >= 150)")
        print(f" -> Today 00:00 hour:     {t_00.entry if t_00 else 0} (Expected: 0 - ZERO spillover)")
        assert y_23 and y_23.entry >= 150, f"Yesterday 23:00 mismatch: {y_23}"
        assert t_00 and t_00.entry == 0, f"SPILLOVER DETECTED: Today 00:00 has {t_00.entry}!"
        print(">>> TEST 6 PASSED <<<")

    # =========================================================================
    # TEST 7: Cross-API Mathematical Consistency
    # =========================================================================
    print("\n--- TEST 7: Cross-API Full Mathematical Consistency ---")
    async with AsyncSessionLocal() as db:
        counting_srv = CanonicalCountingService(db)
        dash_srv = DashboardService(db)
        analytics_srv = AnalyticsService(db)

        fest_in, fest_out, fest_occ = await counting_srv.get_festival_totals(event.id)
        today_in, today_out = await counting_srv.get_today_totals_only_db(event.id)
        daily_items, d_tot_in, d_tot_out, _ = await counting_srv.get_festival_daily_breakdown(event.id)
        hourly_items, peak_h = await counting_srv.get_hourly_breakdown(event.id, now_ist.date())

        sum_hourly_today = sum(h.entry for h in hourly_items)
        sum_daily_fest = sum(d.entry_count for d in daily_items)

        dash_data = await dash_srv.get_summary(date_range="today", event_id=event.id)
        att_data = await analytics_srv.get_attendance_analytics(event_id=event.id, date_range="today")
        fest_att_data = await analytics_srv.get_attendance_analytics(event_id=event.id, date_range="festival")
        today_in_final, _ = await counting_srv.get_today_totals_only_db(event.id)
        fest_in_final, _, _ = await counting_srv.get_festival_totals(event.id)

        print(f" • Sum(Hourly 24h Today) = {sum_hourly_today}")
        print(f" • CountingService Today  = {today_in_final}")
        print(f" • Dashboard Today        = {dash_data.today_entries}")
        print(f" • Analytics Today        = {att_data.total_entries}")
        assert dash_data.today_entries == att_data.total_entries == today_in_final, "TODAY INCONSISTENCY!"

        print(f" • Sum(Daily Festival)   = {sum_daily_fest}")
        print(f" • CountingService Fest   = {fest_in_final}")
        print(f" • Dashboard Fest         = {dash_data.total_visitors_festival}")
        print(f" • Analytics Fest         = {fest_att_data.total_entries}")
        assert dash_data.total_visitors_festival == fest_att_data.total_entries == fest_in_final, "FESTIVAL INCONSISTENCY!"
        print(">>> TEST 7 PASSED <<<")

    print("\n" + "=" * 80)
    print("ALL 7 CRITICAL TEST CASES PASSED WITH 100% MATHEMATICAL PRECISION!")
    print("=" * 80)
    await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_case_suite())
