from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.zone import Zone
from app.repositories.zone_repository import ZoneRepository
from app.schemas.gate import GateRead
from app.schemas.zone import ZonePrediction, ZoneRead


import asyncio
import time

_zones_cache: Optional[List[ZoneRead]] = None
_zones_cache_time: float = 0.0
_is_refreshing_zones = False
_ZONES_TTL: float = 10.0


async def _background_refresh_zones():
    global _is_refreshing_zones
    try:
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            srv = ZoneService(session)
            await srv._fetch_and_cache_direct()
    except Exception:
        pass
    finally:
        _is_refreshing_zones = False


class ZoneService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.zone_repo = ZoneRepository(db)

    async def _fetch_and_cache_direct(self) -> List[ZoneRead]:
        global _zones_cache, _zones_cache_time
        zones = await self.zone_repo.list_all_zones()
        results = []
        for z in zones:
            cam_ids = [c.camera_code for c in z.cameras] if z.cameras else []
            gate_ids = [g.gate_code for g in z.gates] if z.gates else []
            occupancy = round((z.current_people / z.capacity * 100), 1) if z.capacity > 0 else 0.0

            prediction = None
            if z.risk_level == "HIGH" or z.risk_level == "CRITICAL":
                prediction = ZonePrediction(
                    critical_in_minutes=12 if z.risk_level == "HIGH" else 0,
                    next_level="CRITICAL" if z.risk_level == "HIGH" else "MAXIMUM",
                    next_level_in_minutes=12,
                )

            results.append(ZoneRead(
                id=z.zone_code,
                zone_code=z.zone_code,
                name=z.name,
                label=z.label,
                description=z.description,
                current_people=z.current_people,
                capacity=z.capacity,
                occupancy_pct=occupancy,
                density=z.density,
                density_label=z.density_label,
                risk_level=z.risk_level,
                coordinates=z.coordinates if isinstance(z.coordinates, list) else [],
                center=z.center,
                cameras=cam_ids,
                gates=gate_ids,
                color=z.color,
                inflow=round(z.current_people * 0.03),
                outflow=round(z.current_people * 0.02),
                prediction=prediction,
            ))
        _zones_cache = results
        _zones_cache_time = time.time()
        return results

    async def list_zones(self) -> List[ZoneRead]:
        global _zones_cache, _zones_cache_time, _is_refreshing_zones
        now = time.time()

        if _zones_cache is not None:
            if (now - _zones_cache_time) > _ZONES_TTL and not _is_refreshing_zones:
                _is_refreshing_zones = True
                asyncio.create_task(_background_refresh_zones())
            return _zones_cache

        _zones_cache = []
        if not _is_refreshing_zones:
            _is_refreshing_zones = True
            asyncio.create_task(_background_refresh_zones())
        return _zones_cache

    async def get_zone_by_code(self, zone_code: str) -> ZoneRead:
        zone = await self.zone_repo.get_by_code(zone_code)
        if not zone:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "ZONE_NOT_FOUND", "message": f"Zone {zone_code} not found"},
            )
        cam_ids = [c.camera_code for c in zone.cameras] if zone.cameras else []
        gate_ids = [g.gate_code for g in zone.gates] if zone.gates else []
        occupancy = round((zone.current_people / zone.capacity * 100), 1) if zone.capacity > 0 else 0.0

        return ZoneRead(
            id=zone.zone_code,
            zone_code=zone.zone_code,
            name=zone.name,
            label=zone.label,
            description=zone.description,
            current_people=zone.current_people,
            capacity=zone.capacity,
            occupancy_pct=occupancy,
            density=zone.density,
            density_label=zone.density_label,
            risk_level=zone.risk_level,
            coordinates=zone.coordinates if isinstance(zone.coordinates, list) else [],
            center=zone.center,
            cameras=cam_ids,
            gates=gate_ids,
            color=zone.color,
            inflow=round(zone.current_people * 0.03),
            outflow=round(zone.current_people * 0.02),
        )

    async def get_zone_gates(self, zone_code: str) -> List[GateRead]:
        gates = await self.zone_repo.list_gates_by_zone(zone_code)
        return [
            GateRead(
                id=g.gate_code,
                gate_code=g.gate_code,
                name=g.name,
                label=g.label,
                zone_code=g.zone_code or zone_code,
                coordinates=g.coordinates if isinstance(g.coordinates, list) else [78.4720, 17.4295],
                direction=g.direction,
                status=g.status,
                flow_rate=g.flow_rate,
                capacity=g.capacity,
            )
            for g in gates
        ]
