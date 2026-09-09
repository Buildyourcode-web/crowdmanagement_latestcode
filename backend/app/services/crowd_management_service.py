"""
crowd_management_service.py — Aggregation Service for Unified Crowd Management.

Aggregates real-time pipeline telemetry (Crowd AI, Queue AI), database snapshots,
camera health, zone density, risk scores, and event telemetry into a single,
consistent operational summary.
"""

from datetime import datetime, timedelta, timezone
import asyncio
import math
import time
from typing import Any, Dict, List, Optional
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.pipelines.crowd.pipeline import PipelineState
from app.ai.pipelines.crowd.registry import CrowdPipelineRegistry
from app.ai.pipelines.queue.registry import QueuePipelineRegistry
from app.models.alert import Alert
from app.models.camera import Camera
from app.models.camera_ai_assignment import CameraAIProfileAssignment
from app.models.crowd import CrowdSnapshot
from app.models.queue import QueueSnapshot
from app.models.zone import Zone
from app.repositories.alert_repository import AlertRepository
from app.repositories.camera_repository import CameraRepository
from app.repositories.crowd_repository import CrowdRepository
from app.repositories.zone_repository import ZoneRepository
from app.schemas.crowd_management import (
    ActiveEventItem,
    CameraStatusItem,
    CrowdManagementSummaryResponse,
    CrowdRiskBreakdown,
    HighRiskAreaItem,
    MovementTrendPoint,
    QueueCameraStatus,
    QueueTrendPoint,
    ZoneCameraStatus,
    ZoneTrendPoint,
)


class _SummaryCacheEntry:
    def __init__(self, data: CrowdManagementSummaryResponse, expires_at: float):
        self.data = data
        self.expires_at = expires_at


_summary_cache: Dict[str, _SummaryCacheEntry] = {}
_in_flight_requests: Dict[str, asyncio.Future] = {}
_CACHE_TTL_SECONDS: float = 4.5


class CrowdManagementService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.camera_repo = CameraRepository(db)
        self.crowd_repo = CrowdRepository(db)
        self.zone_repo = ZoneRepository(db)
        self.alert_repo = AlertRepository(db)

    async def get_summary(
        self,
        time_range: str = "today",
        mode: str = "all",
        camera_id_or_code: Optional[str] = None,
        risk_filter: str = "all",
    ) -> CrowdManagementSummaryResponse:
        """
        Builds the consolidated Crowd Management dashboard payload with 4.5s in-memory
        caching and concurrent request coalescing to prevent DB connection pressure.
        """
        cache_key = f"{time_range}:{mode}:{camera_id_or_code or 'ALL'}:{risk_filter}"
        now = time.monotonic()

        # 1. Fast path: Cache HIT
        cached = _summary_cache.get(cache_key)
        if cached and now < cached.expires_at:
            logger.debug(f"[CROWD_MGMT_CACHE_HIT] key={cache_key} ttl_remaining={cached.expires_at - now:.1f}s")
            return cached.data

        # 2. In-flight coalescing: If identical query is already executing, wait for its result
        if cache_key in _in_flight_requests:
            logger.debug(f"[CROWD_MGMT_CACHE_HIT] (coalesced) key={cache_key}")
            return await _in_flight_requests[cache_key]

        # 3. Cache MISS: execute single-flight DB retrieval
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        _in_flight_requests[cache_key] = future
        logger.info(f"[CROWD_MGMT_CACHE_MISS] key={cache_key}")
        t0 = time.perf_counter()

        try:
            res = await self._build_summary_uncached(
                time_range=time_range,
                mode=mode,
                camera_id_or_code=camera_id_or_code,
                risk_filter=risk_filter,
            )
            dt_ms = (time.perf_counter() - t0) * 1000
            logger.info(f"[CROWD_MGMT_QUERY_TIME] {dt_ms:.1f}ms for key={cache_key}")
            _summary_cache[cache_key] = _SummaryCacheEntry(res, time.monotonic() + _CACHE_TTL_SECONDS)
            if not future.done():
                future.set_result(res)
            return res
        except Exception as exc:
            if not future.done():
                future.set_exception(exc)
            raise
        finally:
            _in_flight_requests.pop(cache_key, None)

    async def _build_summary_uncached(
        self,
        time_range: str = "today",
        mode: str = "all",
        camera_id_or_code: Optional[str] = None,
        risk_filter: str = "all",
    ) -> CrowdManagementSummaryResponse:
        """
        Executes bulk-optimized database queries across the Supabase link.
        """
        now_dt = datetime.now(timezone.utc)
        now_ts = now_dt.timestamp()

        # 1. Fetch Cameras and AI Profile Assignments
        stmt_cams = select(Camera).order_by(Camera.camera_code)
        result_cams = await self.db.execute(stmt_cams)
        all_cameras = list(result_cams.scalars().all())

        stmt_assignments = select(CameraAIProfileAssignment).where(CameraAIProfileAssignment.enabled == True)
        result_assignments = await self.db.execute(stmt_assignments)
        assignments = list(result_assignments.scalars().all())
        assignment_map: Dict[str, List[str]] = {}
        for a in assignments:
            assignment_map.setdefault(a.camera_code, []).append(a.profile_id)

        # 2. Fetch Zones
        all_zones = await self.zone_repo.list_all_zones()
        zone_map: Dict[str, Zone] = {z.zone_code: z for z in all_zones}

        # 3. Running Pipelines in memory
        live_crowd_pipes = {p.camera_code: p for p in CrowdPipelineRegistry.list_pipelines()}
        live_queue_pipes = {p.config.camera_code: p for p in QueuePipelineRegistry.list_all()}

        # 4. Filter cameras by camera_id_or_code if requested
        if camera_id_or_code and camera_id_or_code.strip().upper() not in ("ALL", ""):
            filter_code = camera_id_or_code.strip().upper()
            all_cameras = [c for c in all_cameras if c.camera_code == filter_code or str(c.id) == camera_id_or_code]

        # 5. Build Queue Items (4–5 cameras dynamically)
        # Bulk pre-fetch latest QueueSnapshot for cameras not in live pipelines in a single query
        queue_cam_codes = [c.camera_code for c in all_cameras if c.camera_code not in live_queue_pipes]
        latest_queue_snaps: Dict[str, QueueSnapshot] = {}
        if queue_cam_codes:
            stmt_q_bulk = (
                select(QueueSnapshot)
                .where(QueueSnapshot.camera_code.in_(queue_cam_codes))
                .distinct(QueueSnapshot.camera_code)
                .order_by(QueueSnapshot.camera_code, QueueSnapshot.timestamp.desc())
            )
            res_q_bulk = await self.db.execute(stmt_q_bulk)
            for qs in res_q_bulk.scalars().all():
                latest_queue_snaps[qs.camera_code] = qs

        queue_items: List[QueueCameraStatus] = []
        for cam in all_cameras:
            assigned_profiles = assignment_map.get(cam.camera_code, [])
            is_queue_cam = (
                "QUEUE_STANDARD" in assigned_profiles
                or cam.camera_type == "QUEUE"
                or cam.camera_code in live_queue_pipes
            )
            if not is_queue_cam:
                continue

            pipe = live_queue_pipes.get(cam.camera_code)
            if pipe and pipe.state == PipelineState.RUNNING:
                m = pipe.get_metrics()
                pipe_status = "RUNNING"
                cur_people = m.get("queue_count", 0)
                q_len_val = m.get("queue_length", {}).get("value", 0.0) if isinstance(m.get("queue_length"), dict) else 0.0
                q_len_unit = m.get("queue_length", {}).get("unit", "normalized_extent") if isinstance(m.get("queue_length"), dict) else "normalized_extent"
                avg_wait = m.get("average_wait_seconds")
                inflow = m.get("inflow")
                outflow = m.get("outflow")
                growth = m.get("growth_per_minute")
                direction = m.get("queue_direction", "UNKNOWN")
                risk = m.get("risk_level", "LOW")
                q_name = pipe.config.queue_roi_name or f"Queue {cam.camera_code}"
            else:
                pipe_status = "STOPPED" if cam.enabled else "OFFLINE"
                snap = latest_queue_snaps.get(cam.camera_code)
                if snap:
                    cur_people = snap.people_waiting
                    q_len_val = snap.queue_length_val or float(snap.queue_length)
                    q_len_unit = snap.queue_length_unit or "normalized_extent"
                    avg_wait = snap.average_wait_seconds
                    inflow = snap.inflow_rate
                    outflow = snap.outflow_rate
                    growth = snap.growth_rate
                    direction = "UNKNOWN"
                    risk = snap.risk_level
                    q_name = f"Queue {cam.camera_code}"
                else:
                    cur_people = 0
                    q_len_val = 0.0
                    q_len_unit = "normalized_extent"
                    avg_wait = None
                    inflow = None
                    outflow = None
                    growth = None
                    direction = "UNKNOWN"
                    risk = "LOW"
                    q_name = f"Queue {cam.camera_code}"

            cam_status_str = "ONLINE" if cam.enabled and (cam.status or "").lower() == "online" else "OFFLINE"
            if cam.enabled and (cam.status or "").lower() == "degraded":
                cam_status_str = "DEGRADED"

            queue_items.append(
                QueueCameraStatus(
                    camera_id=str(cam.id),
                    camera_code=cam.camera_code,
                    camera_name=cam.name,
                    queue_name=q_name,
                    zone_code=cam.zone_code,
                    current_people=cur_people,
                    queue_length=round(float(q_len_val), 1),
                    queue_length_unit=q_len_unit,
                    average_wait_seconds=avg_wait,
                    inflow_rate=inflow,
                    outflow_rate=outflow,
                    growth_rate=growth,
                    queue_direction=direction,
                    risk_level=risk.upper(),
                    camera_status=cam_status_str,
                    pipeline_status=pipe_status,
                )
            )

        # 6. Build Zone Items (2 zone cameras dynamically)
        zone_items: List[ZoneCameraStatus] = []
        # Find cameras configured for Zone/Crowd monitoring
        zone_cams = [
            c for c in all_cameras
            if "CROWD_STANDARD" in assignment_map.get(c.camera_code, [])
            or c.camera_type in ("CROWD", "MULTI_PURPOSE", "GENERAL")
            or c.camera_code in live_crowd_pipes
        ]

        # Map zones to cameras
        zones_to_process = all_zones[:2] if len(all_zones) >= 2 else all_zones
        zone_codes_needed = [z.zone_code for z in zones_to_process]
        latest_crowd_snaps: Dict[str, CrowdSnapshot] = {}
        if zone_codes_needed:
            stmt_c_bulk = (
                select(CrowdSnapshot)
                .where(CrowdSnapshot.zone_code.in_(zone_codes_needed))
                .distinct(CrowdSnapshot.zone_code)
                .order_by(CrowdSnapshot.zone_code, CrowdSnapshot.timestamp.desc())
            )
            res_c_bulk = await self.db.execute(stmt_c_bulk)
            for cs in res_c_bulk.scalars().all():
                latest_crowd_snaps[cs.zone_code] = cs

        for idx, z in enumerate(zones_to_process):
            # Find camera linked to this zone if any
            matched_cam = next((c for c in zone_cams if c.zone_code == z.zone_code), None)
            if not matched_cam and idx < len(zone_cams):
                matched_cam = zone_cams[idx]

            pipe = live_crowd_pipes.get(matched_cam.camera_code) if matched_cam else None
            if pipe and pipe.state == PipelineState.RUNNING:
                m = pipe.get_metrics()
                cur_people = m.get("count", 0)
                capacity = z.capacity or 5000
                density_pct = round((cur_people / float(capacity)) * 100.0, 1) if capacity > 0 else 0.0
                density_lvl = m.get("density_level", "LOW")
                risk = m.get("risk_level", "LOW")
                trend = "INCREASING" if (m.get("flow_delta") or 0) > 10 else ("DECREASING" if (m.get("flow_delta") or 0) < -10 else "STABLE")
                pipe_status = "RUNNING"
            else:
                pipe_status = "STOPPED" if matched_cam and matched_cam.enabled else "OFFLINE"
                snap = latest_crowd_snaps.get(z.zone_code)
                if snap:
                    cur_people = snap.people_count
                    capacity = z.capacity or 5000
                    density_pct = snap.occupancy_percentage or round((cur_people / float(capacity)) * 100.0, 1)
                    density_lvl = "HIGH" if density_pct > 75 else ("MODERATE" if density_pct > 50 else "LOW")
                    risk = snap.risk_level
                    delta = snap.inflow_rate - snap.outflow_rate
                    trend = "INCREASING" if delta > 10 else ("DECREASING" if delta < -10 else "STABLE")
                else:
                    cur_people = z.current_people or 0
                    capacity = z.capacity or 5000
                    density_pct = round((cur_people / float(capacity)) * 100.0, 1) if capacity > 0 else 0.0
                    density_lvl = "LOW"
                    risk = z.risk_level or "LOW"
                    trend = "STABLE"

            cam_status_str = "ONLINE" if matched_cam and matched_cam.enabled and (matched_cam.status or "").lower() == "online" else "OFFLINE"
            if matched_cam and matched_cam.enabled and (matched_cam.status or "").lower() == "degraded":
                cam_status_str = "DEGRADED"

            zone_items.append(
                ZoneCameraStatus(
                    zone_id=str(z.id),
                    zone_code=z.zone_code,
                    zone_name=z.name or z.zone_code,
                    camera_id=str(matched_cam.id) if matched_cam else None,
                    camera_code=matched_cam.camera_code if matched_cam else None,
                    current_people=cur_people,
                    capacity=capacity,
                    density_pct=density_pct,
                    density_level=density_lvl.upper(),
                    risk_level=risk.upper(),
                    trend=trend,
                    camera_status=cam_status_str,
                    pipeline_status=pipe_status,
                )
            )

        # 7. Build Camera Status Table (7 dynamic crowd management cameras)
        # Combine queue cameras and zone cameras up to 7, or all available
        crowd_mgmt_cams = []
        seen_cam_codes = set()

        for q in queue_items:
            if q.camera_code not in seen_cam_codes:
                seen_cam_codes.add(q.camera_code)
                crowd_mgmt_cams.append(
                    CameraStatusItem(
                        camera_id=q.camera_id,
                        camera_code=q.camera_code,
                        name=q.camera_name,
                        purpose="QUEUE",
                        stream_status=q.camera_status,
                        fps=15.0 if q.pipeline_status == "RUNNING" else 0.0,
                        pipeline_status=q.pipeline_status,
                        current_people=q.current_people,
                        last_update=now_dt.isoformat(),
                    )
                )

        for z in zone_items:
            if z.camera_code and z.camera_code not in seen_cam_codes:
                seen_cam_codes.add(z.camera_code)
                crowd_mgmt_cams.append(
                    CameraStatusItem(
                        camera_id=z.camera_id,
                        camera_code=z.camera_code,
                        name=f"{z.zone_name} Monitor",
                        purpose="ZONE",
                        stream_status=z.camera_status,
                        fps=15.0 if z.pipeline_status == "RUNNING" else 0.0,
                        pipeline_status=z.pipeline_status,
                        current_people=z.current_people,
                        last_update=now_dt.isoformat(),
                    )
                )

        # 8. Apply Mode Filter
        filtered_queues = queue_items
        filtered_zones = zone_items
        if mode.lower() == "queue":
            filtered_zones = []
        elif mode.lower() == "zone":
            filtered_queues = []

        # 9. Apply Risk Filter
        if risk_filter.lower() != "all":
            rf = risk_filter.upper()
            filtered_queues = [q for q in filtered_queues if q.risk_level == rf]
            filtered_zones = [z for z in filtered_zones if z.risk_level == rf]

        # 10. Compute High-Level KPIs (Occupancy, Line Crossings)
        # Total People: current valid occupancy across non-overlapping monitored areas
        # If live pipelines exist, sum their active counts. Otherwise sum zone occupancy.
        if live_crowd_pipes or live_queue_pipes:
            total_people = sum(q.current_people for q in queue_items) + sum(z.current_people for z in zone_items)
        else:
            total_people = sum(z.current_people for z in all_zones)

        # Line Crossings:
        # Time window:
        if time_range == "15m":
            time_threshold = now_dt - timedelta(minutes=15)
        elif time_range == "1h":
            time_threshold = now_dt - timedelta(hours=1)
        else:  # today
            time_threshold = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)

        # Inflow (entries) and outflow (exits) from snapshots + active pipelines
        stmt_inout = select(
            func.coalesce(func.sum(CrowdSnapshot.inflow_rate), 0),
            func.coalesce(func.sum(CrowdSnapshot.outflow_rate), 0),
        ).where(CrowdSnapshot.timestamp >= time_threshold)
        res_inout = await self.db.execute(stmt_inout)
        snap_inflow, snap_outflow = res_inout.one()

        # Add active live pipeline line-crossing counts
        live_entries = sum(q.inflow_rate or 0 for q in queue_items)
        live_exits = sum(q.outflow_rate or 0 for q in queue_items)

        total_entries = int(snap_inflow) + live_entries
        total_exits = int(snap_outflow) + live_exits
        net_change = total_entries - total_exits

        # Secondary indicators
        active_cams_cnt = sum(1 for c in crowd_mgmt_cams if c.stream_status == "ONLINE")
        total_cams_cnt = len(crowd_mgmt_cams)
        active_queues_cnt = sum(1 for q in queue_items if q.pipeline_status == "RUNNING" or q.current_people > 0)
        high_risk_zones_cnt = sum(1 for z in all_zones if (z.risk_level or "").upper() in ("HIGH", "CRITICAL"))

        longest_queue_len = max([q.current_people for q in queue_items], default=0)
        longest_wait_sec = max([q.average_wait_seconds or 0 for q in queue_items], default=0)

        # 11. Overall Risk & Breakdown
        all_risks = [q.risk_level for q in queue_items] + [z.risk_level for z in zone_items]
        if "CRITICAL" in all_risks:
            overall_risk = "CRITICAL"
        elif "HIGH" in all_risks:
            overall_risk = "HIGH"
        elif "MEDIUM" in all_risks:
            overall_risk = "MEDIUM"
        else:
            overall_risk = "LOW"

        avg_density = (
            round(sum(z.density_pct for z in zone_items) / len(zone_items), 1)
            if zone_items
            else 0.0
        )
        highest_q = max(queue_items, key=lambda q: (q.risk_level == "CRITICAL", q.risk_level == "HIGH", q.current_people), default=None)
        highest_z = max(zone_items, key=lambda z: (z.risk_level == "CRITICAL", z.risk_level == "HIGH", z.density_pct), default=None)

        risk_breakdown = CrowdRiskBreakdown(
            overall_risk=overall_risk,
            risk_score=92.0 if overall_risk == "CRITICAL" else (72.0 if overall_risk == "HIGH" else (45.0 if overall_risk == "MEDIUM" else 15.0)),
            density_contribution=avg_density,
            inflow=live_entries,
            crowd_growth=net_change,
            highest_risk_queue=f"{highest_q.queue_name} ({highest_q.risk_level})" if highest_q else None,
            highest_risk_zone=f"{highest_z.zone_name} ({highest_z.risk_level})" if highest_z else None,
        )

        # 12. High Risk Areas List
        high_risk_areas: List[HighRiskAreaItem] = []
        for q in queue_items:
            if q.risk_level in ("MEDIUM", "HIGH", "CRITICAL"):
                high_risk_areas.append(
                    HighRiskAreaItem(
                        name=q.queue_name,
                        area_type="QUEUE",
                        current_people=q.current_people,
                        density_pct=None,
                        risk_level=q.risk_level,
                        trend="INCREASING" if (q.growth_rate or 0) > 0 else "STABLE",
                        camera_code=q.camera_code,
                    )
                )
        for z in zone_items:
            if z.risk_level in ("MEDIUM", "HIGH", "CRITICAL") or z.density_pct >= 60:
                high_risk_areas.append(
                    HighRiskAreaItem(
                        name=z.zone_name,
                        area_type="ZONE",
                        current_people=z.current_people,
                        density_pct=z.density_pct,
                        risk_level=z.risk_level,
                        trend=z.trend,
                        camera_code=z.camera_code or "",
                    )
                )
        # Sort by severity
        severity_order = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}
        high_risk_areas.sort(key=lambda a: (severity_order.get(a.risk_level, 0), a.current_people), reverse=True)

        # 13. Active Events
        stmt_alerts = (
            select(Alert)
            .where(Alert.status != "dismissed")
            .order_by(Alert.detected_at.desc())
            .limit(10)
        )
        res_alerts = await self.db.execute(stmt_alerts)
        alerts_db = res_alerts.scalars().all()
        events: List[ActiveEventItem] = [
            ActiveEventItem(
                id=str(a.id),
                alert_code=a.alert_code,
                title=a.title,
                message=a.message,
                severity=a.severity.upper(),
                type=a.type.upper(),
                camera_code=a.camera_code,
                zone_code=a.zone_code,
                detected_at=a.detected_at.isoformat() if a.detected_at else now_dt.isoformat(),
                status=a.status,
            )
            for a in alerts_db
        ]

        # 14. Trends
        # Movement Trend
        movement_points: List[MovementTrendPoint] = []
        if time_range == "15m":
            for i in range(15):
                m_label = f"-{15 - i}m"
                movement_points.append(
                    MovementTrendPoint(
                        timestamp_label=m_label,
                        entries=0,
                        exits=0,
                        people_inside=total_people,
                    )
                )
        elif time_range == "1h":
            for i in range(12):
                m_label = f"-{60 - i * 5}m"
                movement_points.append(
                    MovementTrendPoint(
                        timestamp_label=m_label,
                        entries=0,
                        exits=0,
                        people_inside=total_people,
                    )
                )
        else:  # today (hourly)
            for h in range(24):
                movement_points.append(
                    MovementTrendPoint(
                        timestamp_label=f"{h:02d}:00",
                        entries=0,
                        exits=0,
                        people_inside=total_people if h == now_dt.hour else 0,
                    )
                )

        # Queue Trend
        queue_trend_points: List[QueueTrendPoint] = []
        for i in range(10):
            lbl = f"-{30 - i * 3}m"
            queue_trend_points.append(
                QueueTrendPoint(
                    timestamp_label=lbl,
                    queue_count=sum(q.current_people for q in queue_items),
                    inflow_rate=live_entries,
                    outflow_rate=live_exits,
                )
            )

        # Zone Trend
        zone_trend_points: List[ZoneTrendPoint] = []
        for i in range(10):
            lbl = f"-{30 - i * 3}m"
            densities_dict = {z.zone_name: z.density_pct for z in zone_items}
            zone_trend_points.append(
                ZoneTrendPoint(
                    timestamp_label=lbl,
                    densities=densities_dict,
                )
            )

        return CrowdManagementSummaryResponse(
            total_people=total_people,
            total_entries=total_entries,
            total_exits=total_exits,
            net_change=net_change,
            active_cameras=active_cams_cnt,
            total_cameras=total_cams_cnt,
            active_queues=active_queues_cnt,
            high_risk_zones=high_risk_zones_cnt,
            longest_queue=longest_queue_len,
            longest_wait_seconds=longest_wait_sec,
            overall_risk=overall_risk,
            time_range=time_range,
            timestamp=now_dt.isoformat(),
            queues=filtered_queues,
            zones=filtered_zones,
            cameras=crowd_mgmt_cams,
            risk_breakdown=risk_breakdown,
            high_risk_areas=high_risk_areas,
            events=events,
            trends={
                "movement": [p.model_dump() for p in movement_points],
                "queue_trend": [p.model_dump() for p in queue_trend_points],
                "zone_trend": [p.model_dump() for p in zone_trend_points],
            },
        )
