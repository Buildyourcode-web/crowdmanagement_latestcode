"""
dashboard_service.py — Aggregation Service for BYC AI Command Center Dashboard.

Single-flight, bulk-query aggregation service providing unified, real-time
festival operations telemetry without N+1 database queries or synthetic values.
"""

from datetime import datetime, time as dtime, timedelta, timezone
import asyncio
import time
import uuid
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import noload, selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.pipelines.crowd.pipeline import PipelineState
from app.ai.pipelines.crowd.registry import CrowdPipelineRegistry
from app.ai.pipelines.queue.registry import QueuePipelineRegistry
from app.models.alert import Alert
from app.models.camera import Camera
from app.models.camera_ai_assignment import CameraAIProfileAssignment
from app.models.crowd import CrowdSnapshot
from app.models.event import Event
from app.models.frs import FRSCandidate, FRSReferenceProfile
from app.models.queue import QueueSnapshot
from app.models.zone import Zone
from app.repositories.alert_repository import AlertRepository
from app.repositories.camera_repository import CameraRepository
from app.repositories.zone_repository import ZoneRepository
from app.services.counting_service import CanonicalCountingService
from app.schemas.dashboard import (
    AICameraHealth,
    ActiveCriticalEventItem,
    DailyTrendPoint,
    DashboardSummaryResponse,
    FRSReviewCandidateItem,
    HourlyFlowPoint,
    QueueMovementPoint,
    QueueStatusItem,
    TopRiskAreaItem,
    ZoneDensityItem,
    ZoneTrendPoint,
)


class _DashboardCacheEntry:
    __slots__ = ("data", "fresh_until", "stale_until", "is_updating")

    def __init__(self, data: DashboardSummaryResponse, fresh_until: float, stale_until: float):
        self.data = data
        self.fresh_until = fresh_until
        self.stale_until = stale_until
        self.is_updating = False


_dashboard_cache: Dict[str, _DashboardCacheEntry] = {}
_in_flight_requests: Dict[str, asyncio.Future] = {}
_DASHBOARD_CACHE_FRESH_SECONDS: float = 8.0
_DASHBOARD_CACHE_STALE_SECONDS: float = 300.0
# Monotonic in-memory cache to guarantee completed hours never drop to 0 on rollover
_completed_hourly_cache: Dict[str, Tuple[int, int]] = {}


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.camera_repo = CameraRepository(db)
        self.zone_repo = ZoneRepository(db)
        self.alert_repo = AlertRepository(db)
        self.counting_service = CanonicalCountingService(db)

    async def get_summary(
        self,
        date_range: str = "today",
        day_number: Optional[int] = None,
        event_id: Optional[uuid.UUID] = None,
        allowed_site_ids: Optional[List[uuid.UUID]] = None,
        skip_cache: bool = False,
    ) -> DashboardSummaryResponse:
        """
        Consolidated Command Center Dashboard aggregator with Stale-While-Revalidate (SWR)
        and single-flight request coalescing. Delivers instant <5ms responses while refreshing
        the database asynchronously in the background.
        """
        cache_key = f"dashboard:{event_id}:{day_number}:{date_range.lower()}"
        now = time.monotonic()

        if not skip_cache:
            cached = _dashboard_cache.get(cache_key)

            # 1. Fast path: In-memory cache HIT and Fresh (<8s) -> Return immediately (<1ms)
            if cached and now < cached.fresh_until:
                return cached.data

            # 2. SWR path: Cache is Stale (8s-300s) -> Return instantly, refresh in background!
            if cached and now < cached.stale_until:
                if not cached.is_updating:
                    cached.is_updating = True
                    asyncio.create_task(
                        self._refresh_in_background(cache_key, date_range, day_number, event_id, allowed_site_ids)
                    )
                return cached.data

        # 3. Cache MISS: in-flight request coalescing
        if cache_key in _in_flight_requests:
            return await _in_flight_requests[cache_key]

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        _in_flight_requests[cache_key] = future
        t0 = time.perf_counter()

        try:
            res = await self._build_summary_uncached(
                date_range=date_range,
                day_number=day_number,
                event_id=event_id,
                allowed_site_ids=allowed_site_ids,
            )
            dt_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[DASHBOARD_COLD_FETCH] {dt_ms:.1f}ms for key={cache_key}")
            _dashboard_cache[cache_key] = _DashboardCacheEntry(
                res,
                fresh_until=time.monotonic() + _DASHBOARD_CACHE_FRESH_SECONDS,
                stale_until=time.monotonic() + _DASHBOARD_CACHE_STALE_SECONDS,
            )
            if not future.done():
                future.set_result(res)
            return res
        except Exception as exc:
            if not future.done():
                future.set_exception(exc)
            raise
        finally:
            _in_flight_requests.pop(cache_key, None)

    @classmethod
    async def _refresh_in_background(
        cls,
        cache_key: str,
        date_range: str,
        day_number: Optional[int],
        event_id: Optional[uuid.UUID],
        allowed_site_ids: Optional[List[uuid.UUID]],
    ) -> None:
        """Asynchronously refreshes dashboard summary from database in background."""
        try:
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                svc = cls(session)
                fresh_res = await svc._build_summary_uncached(
                    date_range=date_range,
                    day_number=day_number,
                    event_id=event_id,
                    allowed_site_ids=allowed_site_ids,
                )
                entry = _dashboard_cache.get(cache_key)
                if entry:
                    entry.data = fresh_res
                    entry.fresh_until = time.monotonic() + _DASHBOARD_CACHE_FRESH_SECONDS
                    entry.stale_until = time.monotonic() + _DASHBOARD_CACHE_STALE_SECONDS
                    entry.is_updating = False
                else:
                    _dashboard_cache[cache_key] = _DashboardCacheEntry(
                        fresh_res,
                        fresh_until=time.monotonic() + _DASHBOARD_CACHE_FRESH_SECONDS,
                        stale_until=time.monotonic() + _DASHBOARD_CACHE_STALE_SECONDS,
                    )
                logger.debug(f"[SWR] Background refresh completed for {cache_key}")
        except Exception as exc:
            logger.warning(f"[SWR] Background refresh failed for {cache_key}: {exc}")
            entry = _dashboard_cache.get(cache_key)
            if entry:
                entry.is_updating = False

    async def _build_summary_uncached(
        self,
        date_range: str = "today",
        day_number: Optional[int] = None,
        event_id: Optional[uuid.UUID] = None,
        allowed_site_ids: Optional[List[uuid.UUID]] = None,
    ) -> DashboardSummaryResponse:
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        _t = time.perf_counter()
        def _step(label):
            nonlocal _t
            elapsed = (time.perf_counter() - _t) * 1000
            if elapsed > 100:
                logger.warning(f"[DASH-STEP] {label}: {elapsed:.0f}ms")
            _t = time.perf_counter()

        # -------------------------------------------------------------------
        # 1. Festival Event & Dynamic Days Information
        # -------------------------------------------------------------------
        active_event, days_template, cur_day_num, tz = await self.counting_service.resolve_event_days(event_id)
        target_event_id = active_event.id if active_event else event_id
        now_local = now_dt.astimezone(tz)
        today_date = now_local.date()

        total_days = len(days_template)
        festival_day_current = cur_day_num
        festival_day_total = total_days
        festival_day_label = f"Day {festival_day_current} of {festival_day_total}"

        # Resolve exact target day boundary
        target_d, start_utc, end_utc, sel_day_num, range_label = await self.counting_service.resolve_day_boundary(
            target_event_id, day_number=day_number, date_range=date_range
        )

        event_days_serialized = [
            {
                "day_number": d.day_number,
                "date": d.date,
                "day_name": d.day_name,
                "label": d.label,
                "status": d.status,
            }
            for d in days_template
        ]
        _step("1-event-query")

        # -------------------------------------------------------------------
        # 2. Cameras & Live AI Pipeline States (Strictly Scoped to Event & Sites, Active Only)
        # -------------------------------------------------------------------
        stmt_cams = select(Camera).where(
            Camera.is_active.is_(True),
            Camera.status != "removed",
        )
        if target_event_id:
            stmt_cams = stmt_cams.where(Camera.event_id == target_event_id)
        if allowed_site_ids:
            stmt_cams = stmt_cams.where(Camera.site_id.in_(allowed_site_ids))
        stmt_cams = stmt_cams.order_by(Camera.camera_code)
        res_cams = await self.db.execute(stmt_cams)
        all_cameras = list(res_cams.scalars().all())
        _step("2-cameras-query")

        event_camera_codes = {c.camera_code for c in all_cameras}

        # Check live AI pipelines & FRS workers matching this event's active cameras
        live_crowd_pipes = {
            p.camera_code: p for p in CrowdPipelineRegistry.list_pipelines()
            if p.state == PipelineState.RUNNING and p.camera_code in event_camera_codes
        }
        live_queue_pipes = {
            p.config.camera_code: p for p in QueuePipelineRegistry.list_all()
            if p.state == PipelineState.RUNNING and p.config.camera_code in event_camera_codes
        }

        frs_running_count = 0
        live_frs_workers = {}
        try:
            from app.frs_engine.frs_service import _camera_workers, _workers_lock
            acquired = _workers_lock.acquire(timeout=0.5)
            if acquired:
                try:
                    for cid, w in list(_camera_workers.items()):
                        clean_cid = cid.replace("-FRS", "").replace("-CROWD", "")
                        if getattr(w, "running", False):
                            if (
                                not event_camera_codes
                                or cid in event_camera_codes
                                or clean_cid in event_camera_codes
                                or getattr(w, "camera_id", "") in event_camera_codes
                                or getattr(w, "camera_id", "").replace("-FRS", "").replace("-CROWD", "") in event_camera_codes
                            ):
                                if getattr(w, "is_frs", False):
                                    frs_running_count += 1
                                live_frs_workers[cid] = w
                finally:
                    _workers_lock.release()
        except Exception:
            pass

        # Check online cameras (DB status OR active running worker)
        online_camera_codes = set()
        for c in all_cameras:
            is_worker_active = (
                c.camera_code in live_crowd_pipes
                or c.camera_code in live_queue_pipes
                or c.camera_code in live_frs_workers
                or f"{c.camera_code}-CROWD" in live_frs_workers
                or f"{c.camera_code}-FRS" in live_frs_workers
            )
            if (c.enabled and (c.status or "").lower() == "online") or is_worker_active:
                online_camera_codes.add(c.camera_code)

        cams_online = len(online_camera_codes)
        cams_offline = max(0, len(all_cameras) - cams_online)

        crowd_ai_running = len(live_crowd_pipes) + sum(1 for s in live_frs_workers.values() if getattr(s, "crowd_ai_active", False))
        queue_ai_running = len(live_queue_pipes) + sum(1 for s in live_frs_workers.values() if getattr(s, "crowd_ai_active", False) and any(p in getattr(s, "ai_purposes", []) for p in ("QUEUE", "ENTRY", "ENTRY_EXIT")))
        _step("3-workers-lock")

        health = AICameraHealth(
            cameras_online=cams_online,
            cameras_offline=cams_offline,
            cameras_total=len(all_cameras),
            crowd_ai_running=crowd_ai_running,
            queue_ai_running=queue_ai_running,
            frs_running=frs_running_count,
            system_status="OPTIMAL" if (cams_offline == 0 and cams_online > 0) else ("DEGRADED" if cams_online > 0 else "OFFLINE"),
        )

        # -------------------------------------------------------------------
        # 3. Canonical Festival Totals & Selected Range Aggregation
        # -------------------------------------------------------------------
        if target_event_id:
            fest_total_in, fest_total_out, fest_occ = await self.counting_service.get_festival_totals(target_event_id)
            range_in, range_out, range_occ, _, _ = await self.counting_service.get_event_day_counts(
                target_event_id, day_number=day_number, date_range=date_range
            )
            today_in, today_out, today_occ, _, _ = await self.counting_service.get_event_day_counts(
                target_event_id, day_number=cur_day_num
            )
        else:
            fest_total_in, fest_total_out, fest_occ = 0, 0, 0
            range_in, range_out, range_occ = 0, 0, 0
            today_in, today_out, today_occ = 0, 0, 0

        # Live worker integration: ensure dashboard never reports counts lower than
        # what active camera workers have detected in memory.
        live_in = 0
        live_out = 0
        workers_pool = list(live_frs_workers.values())
        if not workers_pool:
            try:
                from app.frs_engine.frs_service import _camera_workers, _workers_lock
                with _workers_lock:
                    workers_pool = list(_camera_workers.values())
            except Exception:
                pass
        for s in workers_pool:
            if getattr(s, "crowd_ai_active", False) and getattr(s, "running", False):
                live_in += int(getattr(s, "in_count", 0) or 0)
                live_out += int(getattr(s, "out_count", 0) or 0)

        if live_in > 0 or live_out > 0:
            if today_in > 0 and 0 < live_in < (today_in * 0.5):
                today_in += live_in
                today_out += live_out
            else:
                today_in = max(today_in, live_in)
                today_out = max(today_out, live_out)

            today_occ = max(0, today_in - today_out)
            fest_total_in = max(fest_total_in, today_in)
            fest_total_out = max(fest_total_out, today_out)
            fest_occ = max(0, fest_total_in - fest_total_out)
            if range_in < today_in:
                range_in = today_in
                range_out = today_out
                range_occ = today_occ

        _step("4-canonical-totals")

        # -------------------------------------------------------------------
        # 4. Zones & Current Occupancy (Event-Scoped)
        # -------------------------------------------------------------------
        stmt_zones = select(Zone).options(noload(Zone.cameras), noload(Zone.gates))
        if target_event_id:
            stmt_zones = stmt_zones.where(Zone.event_id == target_event_id)
        stmt_zones = stmt_zones.order_by(Zone.zone_code.asc())
        res_zones = await self.db.execute(stmt_zones)
        all_zones = list(res_zones.scalars().all())
        _step("6-list-zones")
        zone_items: List[ZoneDensityItem] = []
        total_zone_people = 0

        # Bulk fetch latest crowd snapshots for zones
        zone_codes = [z.zone_code for z in all_zones]
        latest_zone_snaps: Dict[str, CrowdSnapshot] = {}
        if zone_codes and target_event_id:
            subq = (
                select(CrowdSnapshot.zone_code, func.max(CrowdSnapshot.timestamp).label("max_ts"))
                .where(
                    CrowdSnapshot.event_id == target_event_id,
                    CrowdSnapshot.zone_code.in_(zone_codes),
                )
                .group_by(CrowdSnapshot.zone_code)
                .subquery()
            )
            stmt_z_snaps = select(CrowdSnapshot).join(
                subq, (CrowdSnapshot.zone_code == subq.c.zone_code) & (CrowdSnapshot.timestamp == subq.c.max_ts)
            ).where(CrowdSnapshot.event_id == target_event_id)
            res_z_snaps = await self.db.execute(stmt_z_snaps)
            for s in res_z_snaps.scalars().all():
                latest_zone_snaps[s.zone_code] = s
        _step("8-zone-snaps")

        # Ensure primary zones ZONE-A, ZONE-B, ZONE-C, ZONE-D are ordered first
        primary_order = {"ZONE-A": 0, "ZONE-B": 1, "ZONE-C": 2, "ZONE-D": 3}
        sorted_zones = sorted(all_zones, key=lambda z: primary_order.get(z.zone_code, 99))

        for z in sorted_zones:
            cur_p = z.current_people or 0
            cap = z.capacity or 100
            snap = latest_zone_snaps.get(z.zone_code)
            if snap and snap.people_count is not None:
                cur_p = max(cur_p, snap.people_count)

            # Match active camera for this zone
            matched_cam = next((c for c in all_cameras if (c.zone_code or "").upper() == z.zone_code.upper()), None)
            cam_code = matched_cam.camera_code if matched_cam else None
            cam_name = matched_cam.name if matched_cam else None

            # Alert thresholds from active worker / ROI
            w_thresh = None
            d_thresh = None

            # Check if live worker is actively monitoring this zone
            worker_active = False
            for s in live_frs_workers.values():
                w_zone = getattr(s, "zone_code", "").upper()
                if w_zone == z.zone_code.upper():
                    worker_active = getattr(s, "running", False)
                    cam_code = s.camera_id
                    cam_name = s.name
                    if getattr(s, "warning_threshold", None):
                        w_thresh = s.warning_threshold
                    if getattr(s, "danger_threshold", None):
                        d_thresh = s.danger_threshold
                    if getattr(s, "zone_capacity", None):
                        cap = s.zone_capacity

                    if getattr(s, "crowd_ai_active", False):
                        if "ZONE" in getattr(s, "ai_purposes", []):
                            zd = getattr(s, "zone_data", [])
                            if zd:
                                cur_p = sum(item.get("count", 0) for item in zd)
                                first_zd = zd[0]
                                if first_zd.get("capacity"):
                                    cap = first_zd["capacity"]
                                if first_zd.get("warning_threshold"):
                                    w_thresh = first_zd["warning_threshold"]
                                if first_zd.get("danger_threshold"):
                                    d_thresh = first_zd["danger_threshold"]
                            live_occ = getattr(s, "occupancy_count", 0)
                            if live_occ > 0:
                                cur_p = max(cur_p, live_occ)
                        else:
                            # For entry/queue/crowd cameras in this zone, use live occupancy if present
                            live_occ = getattr(s, "occupancy_count", 0)
                            if live_occ > 0:
                                cur_p = max(cur_p, live_occ)

            # PRODUCTION RULE: Only show zones that have active/enabled cameras monitoring them!
            # If no camera is configured or active for this zone, omit it to avoid displaying dummy zeros.
            if not matched_cam and not worker_active:
                continue

            total_zone_people += cur_p
            density_pct = round((cur_p / float(cap)) * 100.0, 1) if cap > 0 else 0.0

            # Determine GREEN / ORANGE / RED status based on thresholds and density
            if (d_thresh is not None and cur_p >= d_thresh) or density_pct >= 85.0 or (z.risk_level or "").upper() == "CRITICAL":
                z_status = "RED"
                r_level = "CRITICAL"
            elif (w_thresh is not None and cur_p >= w_thresh) or density_pct >= 60.0 or (z.risk_level or "").upper() in ("HIGH", "MODERATE", "MEDIUM"):
                z_status = "ORANGE"
                r_level = "HIGH"
            else:
                z_status = "GREEN"
                r_level = "LOW"

            flow_trend = "STABLE"
            if snap:
                delta = snap.inflow_rate - snap.outflow_rate
                if delta > 10:
                    flow_trend = "INCREASING"
                elif delta < -10:
                    flow_trend = "DECREASING"

            zone_items.append(
                ZoneDensityItem(
                    zone_code=z.zone_code,
                    zone_name=z.name or z.zone_code,
                    current_people=cur_p,
                    capacity=cap,
                    density_pct=density_pct,
                    status=z_status,
                    risk_level=r_level,
                    flow_trend=flow_trend,
                    camera_code=cam_code,
                    camera_name=cam_name,
                )
            )

        current_occupancy = fest_occ
        net_flow = range_in - range_out

        # -------------------------------------------------------------------
        # 5. Queue Status & Flow (Enabled Cameras for this event)
        # -------------------------------------------------------------------
        queue_items: List[QueueStatusItem] = []
        enabled_camera_codes = {c.camera_code for c in all_cameras if c.enabled}

        # 1. From live workers actively monitoring QUEUE or ENTRY Gate Queues
        for cid, s in live_frs_workers.items():
            if getattr(s, "running", False) and getattr(s, "crowd_ai_active", False) and any(p in getattr(s, "ai_purposes", []) for p in ("QUEUE", "ENTRY", "ENTRY_EXIT")):
                q_cnt = getattr(s, "occupancy_count", 0)
                q_mov = getattr(s, "queue_movement_status", "STOPPED")
                flow_stat = q_mov if q_mov in ("FAST", "NORMAL", "SLOW", "STOPPED") else ("FAST" if q_cnt < 20 else "NORMAL")
                wait_min = round((q_cnt * 1.5) / 60) if q_cnt > 0 else 0
                queue_items.append(
                    QueueStatusItem(
                        queue_name=f"Queue {cid}",
                        camera_code=cid,
                        current_people=q_cnt,
                        estimated_wait_minutes=wait_min if wait_min > 0 else None,
                        flow_status=flow_stat,
                        queue_direction="TOWARDS_SANCTUM",
                        risk_level="HIGH" if flow_stat == "STOPPED" and q_cnt > 50 else "LOW",
                    )
                )

        stmt_q_snaps = select(QueueSnapshot)
        if target_event_id:
            stmt_q_snaps = stmt_q_snaps.where(QueueSnapshot.event_id == target_event_id)
        stmt_q_snaps = stmt_q_snaps.order_by(QueueSnapshot.queue_code, QueueSnapshot.timestamp.desc()).limit(20)
        res_q_snaps = await self.db.execute(stmt_q_snaps)
        latest_queues_by_code: Dict[str, QueueSnapshot] = {}
        for qs in res_q_snaps.scalars().all():
            if qs.camera_code and qs.camera_code in enabled_camera_codes:
                if qs.queue_code not in latest_queues_by_code:
                    latest_queues_by_code[qs.queue_code] = qs

        for qcode, qs in latest_queues_by_code.items():
            if any(q.queue_name == qcode or q.camera_code == qs.camera_code for q in queue_items):
                continue
            cur_p = qs.people_waiting or 0
            wait_m = round(qs.average_wait_seconds / 60) if qs.average_wait_seconds > 0 else None
            r_lvl = (qs.risk_level or "LOW").upper()
            f_stat = "STOPPED" if r_lvl == "CRITICAL" else ("SLOW" if r_lvl == "HIGH" else "NORMAL")
            queue_items.append(
                QueueStatusItem(
                    queue_name=qcode,
                    camera_code=qs.camera_code or "CAM-QUEUE",
                    current_people=cur_p,
                    estimated_wait_minutes=wait_m,
                    flow_status=f_stat,
                    queue_direction="FORWARD",
                    risk_level=r_lvl,
                )
            )

        # -------------------------------------------------------------------
        # 6. Hourly / Daily Visitor Flow (Dynamic per selected day)
        # -------------------------------------------------------------------
        hourly_flow: List[HourlyFlowPoint] = []
        peak_h = "No data"

        if target_event_id:
            if target_d is not None:
                # Specific day (Day 1..Day N or Yesterday/Today)
                h_items, peak_h = await self.counting_service.get_hourly_breakdown(target_event_id, target_d)
                hourly_flow = [HourlyFlowPoint(hour=i.hour, entry=i.entry, exit=i.exit, net_flow=i.net_flow) for i in h_items]
                if target_d == today_date:
                    # 1. Monotonic freeze: Ensure past completed hours NEVER drop below previously tracked in memory
                    for p in hourly_flow:
                        prev_in, prev_out = _completed_hourly_cache.get(p.hour, (0, 0))
                        if prev_in > p.entry:
                            p.entry = prev_in
                            p.exit = max(p.exit, prev_out)
                            p.net_flow = p.entry - p.exit

                    flow_sum = sum(p.entry for p in hourly_flow)
                    out_flow_sum = sum(p.exit for p in hourly_flow)

                    delta_live = max(0, today_in - flow_sum)
                    delta_out = max(0, today_out - out_flow_sum)

                    cur_h_str = f"{now_local.hour:02d}:00"
                    if delta_live > 0 or delta_out > 0:
                        for p in hourly_flow:
                            if p.hour == cur_h_str:
                                p.entry += delta_live
                                p.exit += delta_out
                                p.net_flow = p.entry - p.exit
                                break

                    # Record every non-zero hour into monotonic in-memory cache
                    for p in hourly_flow:
                        if p.entry > 0 or p.exit > 0:
                            cur_c_in, cur_c_out = _completed_hourly_cache.get(p.hour, (0, 0))
                            _completed_hourly_cache[p.hour] = (max(cur_c_in, p.entry), max(cur_c_out, p.exit))

                    # Production Guarantee: Persist the active hour count AND previous hour count to DB CrowdSnapshot
                    # so when this hour completes and rolls over to the next hour,
                    # the completed hour's count is already durable in PostgreSQL and NEVER turns to 0!
                    try:
                        cur_hour_int = now_local.hour
                        prev_hour_int = (cur_hour_int - 1) % 24
                        hours_to_persist = [cur_hour_int, prev_hour_int]

                        for h_int in hours_to_persist:
                            h_str = f"{h_int:02d}:00"
                            h_entry = next((p.entry for p in hourly_flow if p.hour == h_str), 0)
                            h_exit = next((p.exit for p in hourly_flow if p.hour == h_str), 0)
                            if h_entry > 0 or h_exit > 0:
                                ts_hour_utc = datetime.combine(today_date, dtime(h_int, 30, 0), tzinfo=tz).astimezone(timezone.utc)
                                h_profile = f"HOURLY_AUTO_{h_int:02d}"

                                q_snap = select(CrowdSnapshot).where(
                                    CrowdSnapshot.event_id == target_event_id,
                                    CrowdSnapshot.profile_id == h_profile,
                                    CrowdSnapshot.timestamp >= start_utc,
                                    CrowdSnapshot.timestamp < end_utc,
                                ).limit(1)
                                exist_snap = (await self.db.execute(q_snap)).scalars().first()

                                if exist_snap:
                                    exist_snap.inflow_rate = max(exist_snap.inflow_rate, h_entry)
                                    exist_snap.outflow_rate = max(exist_snap.outflow_rate, h_exit)
                                    exist_snap.people_count = max(0, exist_snap.inflow_rate - exist_snap.outflow_rate)
                                    exist_snap.timestamp = ts_hour_utc
                                else:
                                    new_snap = CrowdSnapshot(
                                        id=uuid.uuid4(),
                                        event_id=target_event_id,
                                        camera_code="CAM-KHB-001",
                                        profile_id=h_profile,
                                        timestamp=ts_hour_utc,
                                        people_count=max(0, h_entry - h_exit),
                                        density=0.0,
                                        inflow_rate=h_entry,
                                        outflow_rate=h_exit,
                                        occupancy_percentage=0.0,
                                        risk_level="LOW",
                                        risk_score=0.0,
                                    )
                                    self.db.add(new_snap)
                        await self.db.commit()
                    except Exception as persist_err:
                        logger.warning(f"[Dashboard] Hourly snapshot auto-persist warning: {persist_err}")

                    # Recompute peak hour accurately across all buckets
                    max_p = max(hourly_flow, key=lambda x: x.entry, default=None)
                    if max_p and max_p.entry > 0:
                        try:
                            h_int = int(max_p.hour.split(":")[0])
                            peak_h = f"{h_int:02d}:00 - {(h_int+1):02d}:00"
                        except Exception:
                            pass
                    elif peak_h in ("—", "No data"):
                        peak_h = f"{now_local.hour:02d}:00 - {(now_local.hour+1):02d}:00"
            else:
                # Festival Total -> Show Day-by-Day comparison bars
                daily_items, _, _, _ = await self.counting_service.get_festival_daily_breakdown(target_event_id)
                max_f_ent = 0
                for d_item in daily_items:
                    ent_val = d_item.entry_count
                    ext_val = d_item.exit_count
                    if d_item.day_number == cur_day_num and ent_val == 0 and live_in > 0:
                        ent_val = live_in
                        ext_val = live_out
                    if ent_val > max_f_ent:
                        max_f_ent = ent_val
                        peak_h = f"{d_item.label} (Peak Day)"
                    hourly_flow.append(
                        HourlyFlowPoint(
                            hour=d_item.label,
                            entry=ent_val,
                            exit=ext_val,
                            net_flow=ent_val - ext_val,
                        )
                    )

        range_entries = range_in
        range_exits = range_out
        _step("9-hourly-flow-built")

        # -------------------------------------------------------------------
        # 7. Daily Visitor Trend (Canonical from counting service)
        # -------------------------------------------------------------------
        daily_trend: List[DailyTrendPoint] = []
        if target_event_id:
            days_breakdown, _, _, _ = await self.counting_service.get_festival_daily_breakdown(target_event_id)
            for d_item in days_breakdown:
                ent_val = d_item.entry_count
                ext_val = d_item.exit_count
                if d_item.day_number == cur_day_num and ent_val == 0 and live_in > 0:
                    ent_val = live_in
                    ext_val = live_out
                daily_trend.append(
                    DailyTrendPoint(
                        date=d_item.date,
                        entries=ent_val,
                        exits=ext_val,
                        net_flow=ent_val - ext_val,
                    )
                )
        _step("11-daily-query")

        # -------------------------------------------------------------------
        # 8. Top Risk Areas (Max 3–5)
        # -------------------------------------------------------------------
        top_risk_areas: List[TopRiskAreaItem] = []
        for z in zone_items:
            if z.status in ("RED", "ORANGE") or z.density_pct >= 70.0:
                top_risk_areas.append(
                    TopRiskAreaItem(
                        name=z.zone_name,
                        type="ZONE",
                        risk_level=z.status,
                        current_people=z.current_people,
                        reason=f"Density at {z.density_pct}% ({z.current_people:,} / {z.capacity:,} capacity)",
                    )
                )
        for q in queue_items:
            if q.flow_status in ("STOPPED", "SLOW") and q.current_people > 0:
                top_risk_areas.append(
                    TopRiskAreaItem(
                        name=q.queue_name,
                        type="QUEUE",
                        risk_level="RED" if q.flow_status == "STOPPED" else "ORANGE",
                        current_people=q.current_people,
                        reason=f"Queue flow {q.flow_status} ({q.current_people} waiting, wait ~{q.estimated_wait_minutes or 0}m)",
                    )
                )
        top_risk_areas = top_risk_areas[:5]

        # -------------------------------------------------------------------
        # 9. Recent FRS Review Candidates (Max 2)
        # -------------------------------------------------------------------
        recent_frs_candidates: List[FRSReviewCandidateItem] = []
        try:
            stmt_frs = (
                select(FRSCandidate)
                .options(selectinload(FRSCandidate.reference_profile))
                .order_by(FRSCandidate.detected_at.desc())
                .limit(2)
            )
            res_frs = await self.db.execute(stmt_frs)
            for c in res_frs.scalars().all():
                p_name = c.reference_profile.display_name if c.reference_profile else "Watchlist Candidate"
                ref_img = c.reference_profile.reference_image_path if c.reference_profile else None
                recent_frs_candidates.append(
                    FRSReviewCandidateItem(
                        id=str(c.id),
                        candidate_code=c.candidate_code,
                        person_name=p_name,
                        match_score=round(c.match_score, 1),
                        detected_image=c.detected_image_path,
                        reference_image=ref_img,
                        camera_name=c.camera_name or c.camera_code,
                        timestamp=c.detected_at.isoformat() if c.detected_at else now_iso,
                        time_str=c.time_str or (c.detected_at.strftime("%H:%M:%S") if c.detected_at else "—"),
                        status="REVIEW_REQUIRED",
                        category=c.reference_profile.category if c.reference_profile else "Authorized Watchlist",
                    )
                )
        except Exception as e:
            logger.debug(f"[DashboardService] FRS candidate query notice: {e}")
        _step("12-frs-query")

        # -------------------------------------------------------------------
        # 10. Active Critical Events (Max 5)
        # -------------------------------------------------------------------
        active_critical_events: List[ActiveCriticalEventItem] = []
        stmt_alerts = (
            select(Alert)
            .where(Alert.status.in_(["active", "ACTIVE", "TRIGGERED", "UNRESOLVED"]))
        )
        if target_event_id:
            stmt_alerts = stmt_alerts.where(Alert.event_id == target_event_id)
        stmt_alerts = stmt_alerts.order_by(Alert.detected_at.desc()).limit(5)
        res_alerts = await self.db.execute(stmt_alerts)
        for a in res_alerts.scalars().all():
            active_critical_events.append(
                ActiveCriticalEventItem(
                    id=str(a.id),
                    severity=(a.severity or "HIGH").upper(),
                    type=(a.type or "CROWD_RISK").upper(),
                    location=a.zone_code or a.camera_code or "Khairatabad Precinct",
                    time=a.detected_at.strftime("%H:%M:%S") if a.detected_at else "Just now",
                    status=a.status or "ACTIVE",
                    description=a.message or a.title,
                )
            )
        _step("13-alerts-query")

        # -------------------------------------------------------------------
        # 11. Queue Movement & Zone Trend Series (Real data or empty)
        # -------------------------------------------------------------------
        queue_movement: List[QueueMovementPoint] = []
        if latest_queues_by_code and target_event_id:
            stmt_q_hist = (
                select(QueueSnapshot)
                .where(QueueSnapshot.event_id == target_event_id)
                .order_by(QueueSnapshot.timestamp.desc())
                .limit(12)
            )
            res_q_hist = await self.db.execute(stmt_q_hist)
            for qs in reversed(list(res_q_hist.scalars().all())):
                t_str = qs.timestamp.strftime("%H:%M") if qs.timestamp else "—"
                queue_movement.append(
                    QueueMovementPoint(
                        time=t_str,
                        people_in=qs.inflow_rate or 0,
                        people_out=qs.outflow_rate or 0,
                        queue_length=qs.people_waiting or qs.queue_length or 0,
                    )
                )
        _step("14-q-hist-query")

        zone_trends: List[ZoneTrendPoint] = []
        if target_event_id:
            stmt_z_hist = (
                select(CrowdSnapshot)
                .where(CrowdSnapshot.event_id == target_event_id)
                .order_by(CrowdSnapshot.timestamp.desc())
                .limit(20)
            )
            res_z_hist = await self.db.execute(stmt_z_hist)
            for cs in reversed(list(res_z_hist.scalars().all())):
                t_str = cs.timestamp.strftime("%H:%M") if cs.timestamp else "—"
                zone_trends.append(
                    ZoneTrendPoint(
                        time=t_str,
                        zone_code=cs.zone_code or "ZONE-A",
                        people_count=cs.people_count or 0,
                        density_pct=cs.occupancy_percentage or 0.0,
                    )
                )
        _step("15-z-hist-query")

        return DashboardSummaryResponse(
            timestamp=now_iso,
            data_status="LIVE DATA",
            date_range_selected=date_range.upper(),
            total_visitors_festival=fest_total_in,
            festival_total_entries=fest_total_in,
            festival_total_exits=fest_total_out,
            festival_day_current=festival_day_current,
            festival_day_total=festival_day_total,
            festival_day_label=festival_day_label,
            selected_day_number=sel_day_num,
            event_days=event_days_serialized,
            today_entries=range_in,
            today_exits=range_out,
            selected_range_entries=range_entries,
            selected_range_exits=range_exits,
            selected_range_label=range_label,
            current_occupancy=fest_occ,
            net_flow=range_entries - range_exits,
            hourly_flow=hourly_flow,
            peak_hour=peak_h,
            daily_trend=daily_trend,
            queues=queue_items,
            queue_movement=queue_movement,
            zones=zone_items,
            zone_trends=zone_trends,
            top_risk_areas=top_risk_areas,
            recent_frs_candidates=recent_frs_candidates,
            health=health,
            active_critical_events=active_critical_events,
        )
