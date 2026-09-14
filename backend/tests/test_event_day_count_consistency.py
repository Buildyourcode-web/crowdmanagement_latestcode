"""
test_event_day_count_consistency.py — Dedicated Production Audit Test Suite for:
1. Report selected-day count & future empty day
2. Literal SUM(count_delta) aggregation (IN=1, OUT=0 reverse audit, IN=1 sequence 3 -> total=2)
3. Double persistence path idempotency (threadsafe FRS persist + pipeline durable persist -> 1 row)
4. Repeat/reconnect idempotency (1 row) vs genuine second crossing (2 rows)
5. Explicit Day 3 never falls back to today
6. Invalid day (day_number=999) does not fall back to today
7. 4-Way Count Parity: PostgreSQL Canonical == Dashboard == Analytics == Reports for Day 1, Day 2, Day 3
8. Dynamic N-day festival date resolution
"""

import asyncio
from datetime import date, datetime, time, timedelta, timezone
import uuid
import zoneinfo
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.camera import Camera
from app.models.event import Event
from app.models.line_crossing import LineCrossingEvent
from app.services.counting_service import CanonicalCountingService
from app.frs_engine.frs_service import _persist_line_crossing_event_threadsafe
from app.ai.pipelines.crowd.pipeline import CrowdPipeline, ValidatedCrossing


@pytest.mark.asyncio
async def test_literal_sum_count_delta_aggregation(db_session: AsyncSession):
    """
    Verify:
    - Authoritative canonical aggregation is literally SUM(count_delta)
    - IN  (count_delta=1) -> +1
    - OUT (count_delta=0, reverse audit) -> +0
    - IN  (count_delta=1, re-entry) -> +1
    - Total Entry = 1 + 0 + 1 = 2
    """
    event_id = uuid.uuid4()
    cam_in = uuid.uuid4()
    cam_out = uuid.uuid4()
    base_utc = datetime.now(timezone.utc)

    # 1. Valid IN crossing (delta=1)
    e1 = LineCrossingEvent(
        id=uuid.uuid4(),
        event_id=event_id,
        camera_id=cam_in,
        camera_code="CAM-IN-01",
        line_id="LINE-01",
        line_name="Gate 1 Line",
        track_session_id="sess-trk-100",
        track_token="TRK-100",
        crossing_sequence=1,
        direction="IN",
        count_delta=1,
        detection_confidence=0.95,
        idempotency_key=f"{event_id}:{cam_in}:LINE-01:sess-trk-100:CROSSING-001",
        crossing_timestamp=base_utc,
    )

    # 2. Reverse movement OUT (Wrong direction on entry line -> delta=0 audit)
    e2 = LineCrossingEvent(
        id=uuid.uuid4(),
        event_id=event_id,
        camera_id=cam_in,
        camera_code="CAM-IN-01",
        line_id="LINE-01",
        line_name="Gate 1 Line",
        track_session_id="sess-trk-100",
        track_token="TRK-100",
        crossing_sequence=2,
        direction="OUT",
        count_delta=0,
        detection_confidence=0.90,
        idempotency_key=f"{event_id}:{cam_in}:LINE-01:sess-trk-100:CROSSING-002",
        crossing_timestamp=base_utc + timedelta(seconds=10),
    )

    # 3. Legitimate re-entry IN (delta=1, sequence=3)
    e3 = LineCrossingEvent(
        id=uuid.uuid4(),
        event_id=event_id,
        camera_id=cam_in,
        camera_code="CAM-IN-01",
        line_id="LINE-01",
        line_name="Gate 1 Line",
        track_session_id="sess-trk-100",
        track_token="TRK-100",
        crossing_sequence=3,
        direction="IN",
        count_delta=1,
        detection_confidence=0.93,
        idempotency_key=f"{event_id}:{cam_in}:LINE-01:sess-trk-100:CROSSING-003",
        crossing_timestamp=base_utc + timedelta(seconds=20),
    )

    # 4. Valid OUT crossings (delta=1)
    e4 = LineCrossingEvent(
        id=uuid.uuid4(),
        event_id=event_id,
        camera_id=cam_out,
        camera_code="CAM-OUT-01",
        line_id="LINE-02",
        line_name="Exit Line",
        track_session_id="sess-trk-200",
        track_token="TRK-200",
        crossing_sequence=1,
        direction="OUT",
        count_delta=1,
        detection_confidence=0.91,
        idempotency_key=f"{event_id}:{cam_out}:LINE-02:sess-trk-200:CROSSING-001",
        crossing_timestamp=base_utc + timedelta(seconds=30),
    )

    db_session.add_all([e1, e2, e3, e4])
    await db_session.commit()

    service = CanonicalCountingService(db_session)
    tot_in, tot_out = await service.get_durable_counts(event_id)

    assert tot_in == 2, f"Expected 2 entries (1 + 0 + 1), got {tot_in}"
    assert tot_out == 1, f"Expected 1 exit, got {tot_out}"


@pytest.mark.asyncio
async def test_double_persistence_and_idempotency_guarantee(db_session: AsyncSession):
    """
    Verify:
    1. One physical crossing written via threadsafe persist and pipeline persist
       produces EXACTLY ONE row in line_crossing_events (idempotency deduplication).
    2. Repeat / reconnect retry produces STILL EXACTLY ONE row.
    3. A second genuine crossing produces EXACTLY TWO rows (count=2).
    """
    event_id = uuid.uuid4()
    cam_id = uuid.uuid4()
    cam_code = f"CAM-DUP-{uuid.uuid4().hex[:6].upper()}"

    cam = Camera(
        id=cam_id,
        event_id=event_id,
        camera_code=cam_code,
        name="Deduplication Test Camera",
        label="Deduplication Test Camera",
        is_active=True,
        enabled=True,
        status="online",
    )
    db_session.add(cam)
    await db_session.commit()

    line_id = "LINE-GATE-1"
    session_id = f"session-cross-{uuid.uuid4().hex[:6]}"
    expected_idempotency_key = f"{event_id}_{cam_id}_{line_id}_{session_id}_CROSSING-001"

    # --- PATH A: Persist via _persist_line_crossing_event_threadsafe ---
    _persist_line_crossing_event_threadsafe(
        camera_code=cam_code,
        line_id=line_id,
        line_name="Gate 1 Counting Line",
        direction="IN",
        count_delta=1,
        track_session_id=session_id,
        track_token="TRK-777",
        crossing_sequence=1,
        confidence=0.95,
        ground_x=0.5,
        ground_y=0.5,
        signed_distance=0.0,
    )
    await asyncio.sleep(0.3)

    # Verify first persist created 1 row
    stmt = select(LineCrossingEvent).where(LineCrossingEvent.camera_code == cam_code)
    res = await db_session.execute(stmt)
    rows = list(res.scalars().all())
    assert len(rows) == 1, f"Expected 1 row after Path A, got {len(rows)}"
    assert rows[0].direction == "IN"
    assert rows[0].count_delta == 1

    # --- PATH B: Same physical crossing persisted via CrowdPipeline._persist_crossings_durable ---
    class MockConfig:
        camera_code = cam_code
        processing_fps = 15
    pipeline = CrowdPipeline.__new__(CrowdPipeline)
    pipeline.camera_code = cam_code
    pipeline.config = MockConfig()

    crossing_dup = ValidatedCrossing(
        event_id=str(event_id),
        site_id=None,
        camera_id=str(cam_id),
        camera_code=cam_code,
        line_id=line_id,
        line_name="Gate 1 Counting Line",
        track_session_id=session_id,
        track_token="TRK-777",
        crossing_sequence=1,
        direction="IN",
        count_delta=1,
        detection_confidence=0.95,
        ground_x=0.5,
        ground_y=0.5,
        signed_distance=0.0,
        timestamp=datetime.now(timezone.utc).timestamp(),
        idempotency_key=expected_idempotency_key,
        frame_id=100,
    )
    await pipeline._persist_crossings_durable([crossing_dup])

    # Verify database STILL has EXACTLY 1 row (no duplicate row created)
    res2 = await db_session.execute(stmt)
    rows2 = list(res2.scalars().all())
    assert len(rows2) == 1, f"Expected 1 row after duplicate Path B persist, got {len(rows2)}"

    # --- PATH C: Network reconnect retry (same crossing again) ---
    _persist_line_crossing_event_threadsafe(
        camera_code=cam_code,
        line_id=line_id,
        line_name="Gate 1 Counting Line",
        direction="IN",
        count_delta=1,
        track_session_id=session_id,
        track_token="TRK-777",
        crossing_sequence=1,
        confidence=0.95,
        ground_x=0.5,
        ground_y=0.5,
        signed_distance=0.0,
    )
    await asyncio.sleep(0.3)

    res3 = await db_session.execute(stmt)
    rows3 = list(res3.scalars().all())
    assert len(rows3) == 1, f"Expected 1 row after reconnect retry, got {len(rows3)}"

    # --- PATH D: Second genuine crossing (sequence 3) ---
    _persist_line_crossing_event_threadsafe(
        camera_code=cam_code,
        line_id=line_id,
        line_name="Gate 1 Counting Line",
        direction="IN",
        count_delta=1,
        track_session_id=session_id,
        track_token="TRK-777",
        crossing_sequence=3,
        confidence=0.92,
        ground_x=0.5,
        ground_y=0.5,
        signed_distance=0.0,
    )
    await asyncio.sleep(0.3)

    res4 = await db_session.execute(stmt)
    rows4 = list(res4.scalars().all())
    assert len(rows4) == 2, f"Expected 2 rows for two genuine crossings, got {len(rows4)}"

    # Canonical counting query returns 2
    counting_service = CanonicalCountingService(db_session)
    tot_in, _ = await counting_service.get_durable_counts(event_id)
    assert tot_in == 2, f"Expected canonical count of 2, got {tot_in}"


@pytest.mark.asyncio
async def test_count_parity_across_dashboard_analytics_reports_days_1_2_and_3(
    client: AsyncClient, db_session: AsyncSession, superadmin_token: str
):
    """
    Verify 100% count parity for:
    - Day 1 (5 IN, 2 OUT)
    - Day 2 (7 IN, 3 OUT)
    - Day 3 Empty Future State (0 IN, 0 OUT, peak='—')
    Across PostgreSQL, Dashboard API, Analytics API, and Reports API.
    """
    kolkata_tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    now_kolkata = datetime.now(kolkata_tz)
    today_kolkata = now_kolkata.date()

    event_id = uuid.uuid4()
    evt = Event(
        id=event_id,
        code=f"KHB-PARITY-{uuid.uuid4().hex[:6].upper()}",
        name="Parity Comprehensive Test",
        year=2026,
        status="ACTIVE",
        is_active=True,
        start_date=datetime.combine(today_kolkata, time.min, tzinfo=kolkata_tz).astimezone(timezone.utc),
        end_date=datetime.combine(today_kolkata + timedelta(days=9), time.max, tzinfo=kolkata_tz).astimezone(timezone.utc),
    )
    db_session.add(evt)
    await db_session.flush()

    cam = Camera(
        id=uuid.uuid4(),
        event_id=event_id,
        camera_code="CAM-PARITY-1",
        name="Parity Cam",
        label="Parity Cam",
        is_active=True,
        enabled=True,
        status="online",
    )
    db_session.add(cam)
    await db_session.flush()

    # --- Day 1 Seed: 5 entries, 2 exits ---
    d1_start_utc = datetime.combine(today_kolkata, time.min, tzinfo=kolkata_tz).astimezone(timezone.utc)
    for i in range(5):
        db_session.add(
            LineCrossingEvent(
                id=uuid.uuid4(),
                event_id=event_id,
                camera_id=cam.id,
                camera_code=cam.camera_code,
                line_id="LINE-IN",
                line_name="Entry Gate",
                track_session_id=str(uuid.uuid4()),
                track_token=f"TRK-D1-IN-{i}",
                crossing_sequence=1,
                direction="IN",
                count_delta=1,
                detection_confidence=0.92,
                idempotency_key=f"d1-in-{i}:{uuid.uuid4()}",
                crossing_timestamp=d1_start_utc + timedelta(hours=9, minutes=i * 10),
            )
        )
    for j in range(2):
        db_session.add(
            LineCrossingEvent(
                id=uuid.uuid4(),
                event_id=event_id,
                camera_id=cam.id,
                camera_code=cam.camera_code,
                line_id="LINE-OUT",
                line_name="Exit Gate",
                track_session_id=str(uuid.uuid4()),
                track_token=f"TRK-D1-OUT-{j}",
                crossing_sequence=1,
                direction="OUT",
                count_delta=1,
                detection_confidence=0.90,
                idempotency_key=f"d1-out-{j}:{uuid.uuid4()}",
                crossing_timestamp=d1_start_utc + timedelta(hours=10, minutes=j * 10),
            )
        )

    # --- Day 2 Seed: 7 entries, 3 exits ---
    d2_start_utc = datetime.combine(today_kolkata + timedelta(days=1), time.min, tzinfo=kolkata_tz).astimezone(timezone.utc)
    for i in range(7):
        db_session.add(
            LineCrossingEvent(
                id=uuid.uuid4(),
                event_id=event_id,
                camera_id=cam.id,
                camera_code=cam.camera_code,
                line_id="LINE-IN",
                line_name="Entry Gate",
                track_session_id=str(uuid.uuid4()),
                track_token=f"TRK-D2-IN-{i}",
                crossing_sequence=1,
                direction="IN",
                count_delta=1,
                detection_confidence=0.93,
                idempotency_key=f"d2-in-{i}:{uuid.uuid4()}",
                crossing_timestamp=d2_start_utc + timedelta(hours=8, minutes=i * 10),
            )
        )
    for j in range(3):
        db_session.add(
            LineCrossingEvent(
                id=uuid.uuid4(),
                event_id=event_id,
                camera_id=cam.id,
                camera_code=cam.camera_code,
                line_id="LINE-OUT",
                line_name="Exit Gate",
                track_session_id=str(uuid.uuid4()),
                track_token=f"TRK-D2-OUT-{j}",
                crossing_sequence=1,
                direction="OUT",
                count_delta=1,
                detection_confidence=0.91,
                idempotency_key=f"d2-out-{j}:{uuid.uuid4()}",
                crossing_timestamp=d2_start_utc + timedelta(hours=11, minutes=j * 10),
            )
        )

    # Day 3: Intentionally 0 events
    await db_session.commit()

    headers = {
        "Authorization": f"Bearer {superadmin_token}",
        "X-Event-ID": str(event_id),
    }

    # ==================== DAY 1 PARITY AUDIT ====================
    res_dash_d1 = await client.get("/api/v1/dashboard/summary?day_number=1", headers=headers)
    res_ana_d1 = await client.get("/api/v1/analytics/attendance?day_number=1", headers=headers)
    res_rep_d1 = await client.get("/api/v1/reports?day_number=1", headers=headers)

    assert res_dash_d1.status_code == 200
    assert res_ana_d1.status_code == 200
    assert res_rep_d1.status_code == 200

    dash_d1 = res_dash_d1.json()["data"]
    ana_d1 = res_ana_d1.json()["data"]
    rep_d1 = res_rep_d1.json()["data"]

    # Canonical Day 1 values: 5 IN, 2 OUT
    assert dash_d1["today_entries"] == 5
    assert dash_d1["today_exits"] == 2
    assert ana_d1["totalEntries"] == 5
    assert ana_d1["totalExits"] == 2
    assert ana_d1["totalFootfall"] == 5
    assert rep_d1[0]["total_entries"] == 5
    assert rep_d1[0]["total_exits"] == 2
    assert rep_d1[0]["total_footfall"] == 5

    # ==================== DAY 2 PARITY AUDIT ====================
    res_dash_d2 = await client.get("/api/v1/dashboard/summary?day_number=2", headers=headers)
    res_ana_d2 = await client.get("/api/v1/analytics/attendance?day_number=2", headers=headers)
    res_rep_d2 = await client.get("/api/v1/reports?day_number=2", headers=headers)

    dash_d2 = res_dash_d2.json()["data"]
    ana_d2 = res_ana_d2.json()["data"]
    rep_d2 = res_rep_d2.json()["data"]

    # Canonical Day 2 values: 7 IN, 3 OUT
    assert dash_d2["today_entries"] == 7
    assert dash_d2["today_exits"] == 3
    assert ana_d2["totalEntries"] == 7
    assert ana_d2["totalExits"] == 3
    assert ana_d2["totalFootfall"] == 7
    assert rep_d2[0]["total_entries"] == 7
    assert rep_d2[0]["total_exits"] == 3
    assert rep_d2[0]["total_footfall"] == 7

    # ==================== DAY 3 EMPTY STATE PARITY AUDIT ====================
    res_dash_d3 = await client.get("/api/v1/dashboard/summary?day_number=3", headers=headers)
    res_ana_d3 = await client.get("/api/v1/analytics/attendance?day_number=3", headers=headers)
    res_rep_d3 = await client.get("/api/v1/reports?day_number=3", headers=headers)

    dash_d3 = res_dash_d3.json()["data"]
    ana_d3 = res_ana_d3.json()["data"]
    rep_d3 = res_rep_d3.json()["data"]

    # Canonical Day 3 empty state values: 0 IN, 0 OUT, peak "—"
    assert dash_d3["today_entries"] == 0, f"Expected 0 entries on Day 3, got {dash_d3['today_entries']}"
    assert dash_d3["today_exits"] == 0
    assert dash_d3["peak_hour"] == "—"
    assert all(h["entry"] == 0 for h in dash_d3["hourly_flow"])

    assert ana_d3["totalEntries"] == 0
    assert ana_d3["totalExits"] == 0
    assert ana_d3["totalFootfall"] == 0
    assert ana_d3["peakHour"] == "—"
    assert all(h["visitors"] == 0 for h in ana_d3["hourly"])

    assert rep_d3[0]["total_entries"] == 0
    assert rep_d3[0]["total_exits"] == 0
    assert rep_d3[0]["total_footfall"] == 0


@pytest.mark.asyncio
async def test_explicit_day_isolation_and_invalid_day_handling(
    client: AsyncClient, db_session: AsyncSession, superadmin_token: str
):
    """
    Verify:
    1. Explicit Day 3 returns Day 3 empty state and NEVER falls back to today (Day 1).
    2. Invalid Day 999 returns clean Out of Range empty state and NEVER falls back to today.
    """
    kolkata_tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    today_kolkata = datetime.now(kolkata_tz).date()

    event_id = uuid.uuid4()
    evt = Event(
        id=event_id,
        code=f"KHB-ISO-{uuid.uuid4().hex[:6].upper()}",
        name="Isolation Test Event",
        year=2026,
        status="ACTIVE",
        is_active=True,
        start_date=datetime.combine(today_kolkata, time.min, tzinfo=kolkata_tz).astimezone(timezone.utc),
        end_date=datetime.combine(today_kolkata + timedelta(days=9), time.max, tzinfo=kolkata_tz).astimezone(timezone.utc),
    )
    db_session.add(evt)
    await db_session.flush()

    cam = Camera(
        id=uuid.uuid4(),
        event_id=event_id,
        camera_code="CAM-ISO-1",
        name="Isolation Cam",
        label="Isolation Cam",
        is_active=True,
        enabled=True,
        status="online",
    )
    db_session.add(cam)
    await db_session.flush()

    # Seed Day 1 with 15 entries
    d1_start = datetime.combine(today_kolkata, time.min, tzinfo=kolkata_tz).astimezone(timezone.utc)
    for i in range(15):
        db_session.add(
            LineCrossingEvent(
                id=uuid.uuid4(),
                event_id=event_id,
                camera_id=cam.id,
                camera_code=cam.camera_code,
                line_id="LINE-IN",
                line_name="Entry Gate",
                track_session_id=str(uuid.uuid4()),
                track_token=f"TRK-ISO-{i}",
                crossing_sequence=1,
                direction="IN",
                count_delta=1,
                detection_confidence=0.92,
                idempotency_key=f"iso-in-{i}:{uuid.uuid4()}",
                crossing_timestamp=d1_start + timedelta(hours=10),
            )
        )
    await db_session.commit()

    headers = {
        "Authorization": f"Bearer {superadmin_token}",
        "X-Event-ID": str(event_id),
    }

    # 1. Query Explicit Day 3 (No records seeded) -> Must NOT return 15 from Day 1
    res_d3 = await client.get("/api/v1/analytics/attendance?day_number=3", headers=headers)
    assert res_d3.status_code == 200
    d3_data = res_d3.json()["data"]
    assert d3_data["totalEntries"] == 0, f"Expected 0 entries on Day 3, got {d3_data['totalEntries']}"
    assert d3_data["totalFootfall"] == 0
    assert d3_data["peakHour"] == "—"

    # 2. Query Invalid Day 999 -> Must NOT return 15 from Day 1
    res_d999 = await client.get("/api/v1/analytics/attendance?day_number=999", headers=headers)
    assert res_d999.status_code == 200
    d999_data = res_d999.json()["data"]
    assert d999_data["totalEntries"] == 0, f"Expected 0 entries for invalid Day 999, got {d999_data['totalEntries']}"
    assert d999_data["totalFootfall"] == 0
    assert d999_data["peakHour"] == "—"
    assert "Out of Range" in d999_data["selectedDayLabel"]

    # 3. Query Dashboard with Day 999 -> Must NOT return 15 from Day 1
    res_dash_999 = await client.get("/api/v1/dashboard/summary?day_number=999", headers=headers)
    assert res_dash_999.status_code == 200
    dash_999 = res_dash_999.json()["data"]
    assert dash_999["today_entries"] == 0
    assert dash_999["peak_hour"] == "—"


@pytest.mark.asyncio
async def test_dynamic_n_day_calculation(db_session: AsyncSession):
    """
    Verify dynamic festival day calculation for arbitrary durations:
    - 5-day event
    - 11-day event
    - 14-day event
    """
    service = CanonicalCountingService(db_session)
    kolkata_tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    base_d = date(2026, 9, 14)

    for num_days in [5, 11, 14]:
        evt = Event(
            id=uuid.uuid4(),
            code=f"KHB-DUR-{num_days}-{uuid.uuid4().hex[:4]}",
            name=f"{num_days} Day Festival",
            year=2026,
            status="ACTIVE",
            is_active=True,
            start_date=datetime.combine(base_d, time.min, tzinfo=kolkata_tz).astimezone(timezone.utc),
            end_date=datetime.combine(base_d + timedelta(days=num_days - 1), time.max, tzinfo=kolkata_tz).astimezone(timezone.utc),
        )
        db_session.add(evt)
        await db_session.flush()

        active_evt, days_template, cur_day, tz = await service.resolve_event_days(evt.id)
        assert len(days_template) == num_days, f"Expected {num_days} days, got {len(days_template)}"
        assert days_template[0].day_number == 1
        assert days_template[-1].day_number == num_days
