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
        event_id: Optional[uuid.UUID] = None,
        allowed_site_ids: Optional[List[uuid.UUID]] = None,
    ) -> DashboardSummaryResponse:
        """
        Consolidated Command Center Dashboard aggregator with Stale-While-Revalidate (SWR)
        and single-flight request coalescing. Delivers instant <5ms responses while refreshing
        the database asynchronously in the background.
        """
        cache_key = f"dashboard:{event_id}:{date_range.lower()}"
        now = time.monotonic()

        cached = _dashboard_cache.get(cache_key)

        # 1. Fast path: In-memory cache HIT and Fresh (<8s) -> Return immediately (<1ms)
        if cached and now < cached.fresh_until:
            return cached.data

        # 2. SWR path: Cache is Stale (8s-300s) -> Return instantly, refresh in background!
        if cached and now < cached.stale_until:
            if not cached.is_updating:
                cached.is_updating = True
                asyncio.create_task(
                    self._refresh_in_background(cache_key, date_range, event_id, allowed_site_ids)
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
        # 1. Festival Event & Days Information
        # -------------------------------------------------------------------
        active_event = await self.counting_service.get_event(event_id)
        target_event_id = active_event.id if active_event else event_id
        tz = self.counting_service.get_event_timezone(active_event)
        now_local = now_dt.astimezone(tz)
        today_date = now_local.date()

        festival_day_current = 1
        festival_day_total = 11
        if active_event and active_event.start_date and active_event.end_date:
            s_date = active_event.start_date.astimezone(tz).date()
            e_date = active_event.end_date.astimezone(tz).date()
            total_days = max(1, (e_date - s_date).days + 1)
            cur_day = max(1, min(total_days, (today_date - s_date).days + 1))
            festival_day_current = cur_day
            festival_day_total = total_days

        festival_day_label = f"Day {festival_day_current} of {festival_day_total}"
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
                        if cid in event_camera_codes or getattr(w, "camera_id", "") in event_camera_codes:
                            if getattr(w, "running", False):
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
            )
            if (c.enabled and (c.status or "").lower() == "online") or is_worker_active:
                online_camera_codes.add(c.camera_code)

        cams_online = len(online_camera_codes)
        cams_offline = max(0, len(all_cameras) - cams_online)

        crowd_ai_running = len(live_crowd_pipes) + sum(1 for s in live_frs_workers.values() if getattr(s, "crowd_ai_active", False))
        queue_ai_running = len(live_queue_pipes) + sum(1 for s in live_frs_workers.values() if getattr(s, "crowd_ai_active", False) and "QUEUE" in getattr(s, "ai_purposes", []))
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
            range_in, range_out, range_occ = await self.counting_service.get_range_counts(target_event_id, date_range)
            today_in, today_out, today_occ = await self.counting_service.get_range_counts(target_event_id, "today")
        else:
            fest_total_in, fest_total_out, fest_occ = 0, 0, 0
            range_in, range_out, range_occ = 0, 0, 0
            today_in, today_out, today_occ = 0, 0, 0

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

        # 1. From live workers actively monitoring QUEUE
        for cid, s in live_frs_workers.items():
            if getattr(s, "running", False) and getattr(s, "crowd_ai_active", False) and "QUEUE" in getattr(s, "ai_purposes", []):
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
        # 6. Hourly / Daily Visitor Flow (Dynamic per date_range)
        # -------------------------------------------------------------------
        hourly_flow: List[HourlyFlowPoint] = []
        peak_h = "—"
        range_mode = (date_range or "today").lower().strip()

        if range_mode == "yesterday":
            range_label = "Yesterday"
            yesterday_d = today_date - timedelta(days=1)
            if target_event_id:
                h_items, peak_h = await self.counting_service.get_hourly_breakdown(target_event_id, yesterday_d)
                hourly_flow = [HourlyFlowPoint(hour=i.hour, entry=i.entry, exit=i.exit, net_flow=i.net_flow) for i in h_items]
        elif range_mode in ("7days", "7_days", "last7days", "last_7_days"):
            range_label = "Last 7 Days"
            seven_days_ago = today_date - timedelta(days=6)
            s_start_utc = datetime.combine(seven_days_ago, dtime.min, tzinfo=tz).astimezone(timezone.utc)
            tz_name = (active_event.timezone if active_event and active_event.timezone else "Asia/Kolkata").strip()
            kolkata_ts = func.timezone(tz_name, CrowdSnapshot.timestamp)

            stmt_7 = (
                select(
                    func.date(kolkata_ts).label("d"),
                    func.sum(CrowdSnapshot.inflow_rate).label("inflow"),
                    func.sum(CrowdSnapshot.outflow_rate).label("outflow"),
                )
                .where(
                    CrowdSnapshot.event_id == target_event_id,
                    CrowdSnapshot.timestamp >= s_start_utc,
                )
                .group_by(func.date(kolkata_ts))
            )
            res_7 = await self.db.execute(stmt_7)
            d7_map = {}
            for r in res_7.all():
                if r.d is not None:
                    d7_map[str(r.d)] = {"entry": int(r.inflow or 0), "exit": int(r.outflow or 0)}

            max_7_ent = -1
            for i in range(7):
                day_d = seven_days_ago + timedelta(days=i)
                d_str = str(day_d)
                ent = d7_map.get(d_str, {}).get("entry", 0)
                ext = d7_map.get(d_str, {}).get("exit", 0)
                lbl = day_d.strftime("%d %b")
                if ent > max_7_ent and ent > 0:
                    max_7_ent = ent
                    peak_h = f"{lbl} (Peak Day)"
                hourly_flow.append(
                    HourlyFlowPoint(
                        hour=lbl,
                        entry=ent,
                        exit=ext,
                        net_flow=ent - ext,
                    )
                )
        elif range_mode in ("festival", "fest"):
            range_label = "Festival"
            if target_event_id:
                daily_items, _, _, _ = await self.counting_service.get_festival_daily_breakdown(target_event_id)
                max_f_ent = -1
                for d_item in daily_items:
                    if d_item.entry_count > max_f_ent and d_item.entry_count > 0:
                        max_f_ent = d_item.entry_count
                        peak_h = f"{d_item.label} (Peak Day)"
                    hourly_flow.append(
                        HourlyFlowPoint(
                            hour=d_item.label,
                            entry=d_item.entry_count,
                            exit=d_item.exit_count,
                            net_flow=d_item.entry_count - d_item.exit_count,
                        )
                    )
        else:
            range_label = "Today"
            if target_event_id:
                h_items, peak_h = await self.counting_service.get_hourly_breakdown(target_event_id, today_date)
                hourly_flow = [HourlyFlowPoint(hour=i.hour, entry=i.entry, exit=i.exit, net_flow=i.net_flow) for i in h_items]

        range_entries = range_in
        range_exits = range_out
        _step("9-hourly-flow-built")

        # -------------------------------------------------------------------
        # 7. Daily Visitor Trend (Last 7–10 days)
        # -------------------------------------------------------------------
        daily_trend: List[DailyTrendPoint] = []
        cutoff_date = (now_dt - timedelta(days=7)).date()
        stmt_daily = (
            select(
                func.date(CrowdSnapshot.timestamp).label("d"),
                func.sum(CrowdSnapshot.inflow_rate).label("inflow"),
                func.sum(CrowdSnapshot.outflow_rate).label("outflow"),
            )
            .where(
                CrowdSnapshot.event_id == target_event_id,
                func.date(CrowdSnapshot.timestamp) >= cutoff_date,
            )
            .group_by(func.date(CrowdSnapshot.timestamp))
            .order_by(func.date(CrowdSnapshot.timestamp).asc())
        )
        try:
            res_daily = await self.db.execute(stmt_daily)
            for row in res_daily.all():
                d_str = str(row.d)
                ent = int(row.inflow or 0)
                ext = int(row.outflow or 0)
                daily_trend.append(
                    DailyTrendPoint(
                        date=d_str,
                        entries=ent,
                        exits=ext,
                        net_flow=ent - ext,
                    )
                )
        except Exception:
            pass
        _step("11-daily-query")

        # If today is missing from daily trend, append it
        today_str = str(now_dt.date())
        if not any(d.date == today_str for d in daily_trend):
            daily_trend.append(
                DailyTrendPoint(
                    date=today_str,
                    entries=today_in,
                    exits=today_out,
                    net_flow=today_in - today_out,
                )
            )

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
            today_entries=today_in,
            today_exits=today_out,
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
