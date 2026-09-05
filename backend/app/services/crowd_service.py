from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.zone import Zone
from app.repositories.crowd_repository import CrowdRepository
from app.repositories.zone_repository import ZoneRepository
from app.schemas.crowd import CrowdSummaryResponse, CrowdTimeSeriesPoint, QueueResponse


import asyncio
import time

_summary_cache: Optional[CrowdSummaryResponse] = None
_summary_cache_time: float = 0.0
_is_refreshing_summary = False
_CROWD_TTL: float = 8.0


async def _background_refresh_summary():
    global _summary_cache, _summary_cache_time, _is_refreshing_summary
    try:
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            srv = CrowdService(session)
            await srv._fetch_and_cache_direct()
    except Exception:
        pass
    finally:
        _is_refreshing_summary = False


class CrowdService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.crowd_repo = CrowdRepository(db)
        self.zone_repo = ZoneRepository(db)

    async def _fetch_and_cache_direct(self) -> CrowdSummaryResponse:
        global _summary_cache, _summary_cache_time
        zones = await self.zone_repo.list_all_zones()
        current_crowd = sum(z.current_people for z in zones)
        total_capacity = sum(z.capacity for z in zones) or 1
        occupancy = round((current_crowd / total_capacity) * 100, 1) if current_crowd > 0 else 0.0
        critical_zones = sum(1 for z in zones if z.risk_level in ("HIGH", "CRITICAL"))

        queues = await self.crowd_repo.list_latest_queues()
        active_queues = len(queues)
        avg_wait = round(sum(q.average_wait_seconds for q in queues) / len(queues) / 60) if queues else 0

        # Inflow/outflow: only real data from snapshots, not hardcoded
        snapshots = await self.crowd_repo.get_latest_zone_snapshots()
        total_inflow = sum(s.inflow_rate for s in snapshots) if snapshots else 0
        total_outflow = sum(s.outflow_rate for s in snapshots) if snapshots else 0
        total_today = sum(s.people_count for s in snapshots) if snapshots else 0

        res = CrowdSummaryResponse(
            totalVisitorsToday=total_today,
            currentCrowd=current_crowd,
            activeQueues=active_queues,
            occupancy=occupancy,
            inflowPerMin=total_inflow,
            outflowPerMin=total_outflow,
            avgQueueWait=avg_wait,
            peakHour="—",
            critical_zones=critical_zones,
        )
        _summary_cache = res
        _summary_cache_time = time.time()
        return res

    async def get_summary(self) -> CrowdSummaryResponse:
        global _summary_cache, _summary_cache_time, _is_refreshing_summary
        now = time.time()

        if _summary_cache is not None:
            # If cache is expired and not currently refreshing, trigger silent background revalidation
            if (now - _summary_cache_time) > _CROWD_TTL and not _is_refreshing_summary:
                _is_refreshing_summary = True
                asyncio.create_task(_background_refresh_summary())
            # Return cached response instantly in <1ms
            return _summary_cache

        # Cold startup: set instant default and trigger background fetch
        default_res = CrowdSummaryResponse(
            totalVisitorsToday=0,
            currentCrowd=0,
            activeQueues=0,
            occupancy=0.0,
            inflowPerMin=0,
            outflowPerMin=0,
            avgQueueWait=0,
            peakHour="—",
            critical_zones=0,
        )
        _summary_cache = default_res
        if not _is_refreshing_summary:
            _is_refreshing_summary = True
            asyncio.create_task(_background_refresh_summary())
        return default_res

    async def get_timeseries(self) -> List[CrowdTimeSeriesPoint]:
        # Return empty timeseries — will be populated by real AI data
        results = []
        for i in range(24):
            results.append(CrowdTimeSeriesPoint(
                hour=f"{i:02d}:00",
                crowd=0,
                inflow=0,
                outflow=0,
            ))
        return results

    async def get_queues(self, zone_code: Optional[str] = None) -> List[QueueResponse]:
        queues = await self.crowd_repo.list_latest_queues()
        if not queues:
            return []

        results = []
        for q in queues:
            if zone_code and q.zone_code != zone_code:
                continue
            results.append(QueueResponse(
                id=q.queue_code,
                gate=q.gate_code,
                zone=q.zone_code,
                length=q.queue_length,
                waitMinutes=round(q.average_wait_seconds / 60),
                processingRate=q.processing_rate,
                growthRate=q.growth_rate,
                status=q.risk_level.lower(),
            ))
        return results
