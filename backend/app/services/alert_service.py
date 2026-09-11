import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from fastapi import HTTPException, status

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.alert import Alert
from app.repositories.alert_repository import AlertRepository
from app.schemas.alert import AlertActionRequest, AlertRead, AlertStatsResponse


class AlertService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.alert_repo = AlertRepository(db)

    async def list_alerts(
        self,
        severity: Optional[str] = None,
        alert_type: Optional[str] = None,
        zone_code: Optional[str] = None,
        camera_code: Optional[str] = None,
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
        event_id: Optional[uuid.UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[AlertRead], int]:
        skip = (page - 1) * page_size
        alerts, total = await self.alert_repo.list_alerts(
            severity=severity,
            alert_type=alert_type,
            zone_code=zone_code,
            camera_code=camera_code,
            status=status_filter,
            search=search,
            event_id=event_id,
            skip=skip,
            limit=page_size,
        )


        results = [
            AlertRead(
                id=a.alert_code,
                type=a.type,
                typeLabel=a.type_label,
                severity=a.severity,
                title=a.title,
                message=a.message,
                zone=a.zone_code,
                camera=a.camera_code,
                status=a.status,
                acknowledged=a.acknowledged,
                detected_at=a.detected_at,
                assigned_to=a.assigned_to,
                metadata_json=a.metadata_json,
            )
            for a in alerts
        ]
        return results, total

    async def acknowledge_alert(self, alert_code: str, officer_name: str = "CMD-CTR") -> AlertRead:
        alert = await self.alert_repo.get_by_code(alert_code)
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "ALERT_NOT_FOUND", "message": f"Alert {alert_code} not found"},
            )
        alert.acknowledged = True
        alert.acknowledged_at = datetime.now(timezone.utc)
        await self.alert_repo.update(alert)

        # Broadcast update
        from app.redis.event_bus import event_bus
        await event_bus.publish(
            channel="byc:alerts",
            event_type="alert_update",
            payload={"id": alert.alert_code, "acknowledged": True, "status": alert.status},
            source="alert_service",
        )

        return AlertRead(
            id=alert.alert_code,
            type=alert.type,
            typeLabel=alert.type_label,
            severity=alert.severity,
            title=alert.title,
            message=alert.message,
            zone=alert.zone_code,
            camera=alert.camera_code,
            status=alert.status,
            acknowledged=alert.acknowledged,
            detected_at=alert.detected_at,
            assigned_to=alert.assigned_to,
            metadata_json=alert.metadata_json,
        )

    async def get_stats(self) -> AlertStatsResponse:
        alerts, total = await self.alert_repo.list_alerts(limit=1000)
        critical = sum(1 for a in alerts if a.severity == "critical")
        high = sum(1 for a in alerts if a.severity == "high")
        medium = sum(1 for a in alerts if a.severity == "medium")
        low = sum(1 for a in alerts if a.severity == "low")
        active = sum(1 for a in alerts if a.status == "active")

        return AlertStatsResponse(
            total=total,
            critical=critical,
            high=high,
            medium=medium,
            low=low,
            active=active,
        )
