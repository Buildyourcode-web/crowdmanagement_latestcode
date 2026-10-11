from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.zone import Zone
from app.repositories.zone_repository import ZoneRepository
from app.schemas.gate import GateRead
from app.schemas.zone import ZonePrediction, ZoneRead


import asyncio
import time

from typing import Dict, List, Optional, Tuple
import asyncio
import time
import uuid

_zones_cache: Dict[str, Tuple[List[ZoneRead], float]] = {}
_ZONES_TTL: float = 10.0


class ZoneService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.zone_repo = ZoneRepository(db)

    def _build_zone_read(self, z: Zone) -> ZoneRead:
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

        return ZoneRead(
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
        )

    async def list_zones(
        self,
        event_id: Optional[uuid.UUID] = None,
        location_id: Optional[uuid.UUID] = None,
    ) -> List[ZoneRead]:
        global _zones_cache
        cache_key = f"{location_id}:{event_id}"
        now = time.time()

        if cache_key in _zones_cache:
            data, cache_time = _zones_cache[cache_key]
            if (now - cache_time) < _ZONES_TTL:
                return data

        zones = await self.zone_repo.list_all_zones(event_id=event_id, location_id=location_id)
        results = [self._build_zone_read(z) for z in zones]
        _zones_cache[cache_key] = (results, now)
        return results

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
