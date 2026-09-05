from datetime import datetime, timezone
from typing import List, Optional, Tuple
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.incident import Incident
from app.repositories.incident_repository import IncidentRepository
from app.schemas.incident import IncidentActionRequest, IncidentNoteCreate, IncidentNoteRead, IncidentRead


class IncidentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.incident_repo = IncidentRepository(db)

    async def list_incidents(
        self,
        status_filter: Optional[str] = None,
        severity: Optional[str] = None,
        incident_type: Optional[str] = None,
        zone_code: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[IncidentRead], int]:
        skip = (page - 1) * page_size
        incidents, total = await self.incident_repo.list_incidents(
            status=status_filter,
            severity=severity,
            incident_type=incident_type,
            zone_code=zone_code,
            skip=skip,
            limit=page_size,
        )

        results = []
        for inc in incidents:
            notes_read = [
                IncidentNoteRead(
                    id=n.id,
                    author=n.author,
                    text=n.text,
                    note_time=n.note_time,
                )
                for n in inc.notes
            ]
            results.append(IncidentRead(
                id=inc.incident_code,
                type=inc.type,
                typeLabel=inc.type_label,
                severity=inc.severity,
                status=inc.status,
                zone=inc.zone_code,
                location=inc.location,
                cameras=inc.cameras if isinstance(inc.cameras, list) else [],
                detectedAt=inc.detected_at,
                acknowledgedAt=inc.acknowledged_at,
                assignedAt=inc.assigned_at,
                respondingAt=inc.responding_at,
                resolvedAt=inc.resolved_at,
                assignedTeam=inc.assigned_team,
                assignedTeamLabel=inc.assigned_team_label,
                description=inc.description,
                timeline=inc.timeline if isinstance(inc.timeline, list) else [],
                relatedAlerts=inc.related_alerts if isinstance(inc.related_alerts, list) else [],
                notes=notes_read,
            ))
        return results, total

    async def get_incident_by_code(self, code: str) -> IncidentRead:
        inc = await self.incident_repo.get_by_code(code)
        if not inc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "INCIDENT_NOT_FOUND", "message": f"Incident {code} not found"},
            )
        notes_read = [
            IncidentNoteRead(
                id=n.id,
                author=n.author,
                text=n.text,
                note_time=n.note_time,
            )
            for n in inc.notes
        ]
        return IncidentRead(
            id=inc.incident_code,
            type=inc.type,
            typeLabel=inc.type_label,
            severity=inc.severity,
            status=inc.status,
            zone=inc.zone_code,
            location=inc.location,
            cameras=inc.cameras if isinstance(inc.cameras, list) else [],
            detectedAt=inc.detected_at,
            acknowledgedAt=inc.acknowledged_at,
            assignedAt=inc.assigned_at,
            respondingAt=inc.responding_at,
            resolvedAt=inc.resolved_at,
            assignedTeam=inc.assigned_team,
            assignedTeamLabel=inc.assigned_team_label,
            description=inc.description,
            timeline=inc.timeline if isinstance(inc.timeline, list) else [],
            relatedAlerts=inc.related_alerts if isinstance(inc.related_alerts, list) else [],
            notes=notes_read,
        )

    async def update_lifecycle(
        self,
        code: str,
        new_status: str,
        assigned_team: Optional[str] = None,
        assigned_team_label: Optional[str] = None,
        notes: Optional[str] = None,
        author: str = "Command Officer",
    ) -> IncidentRead:
        inc = await self.incident_repo.get_by_code(code)
        if not inc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "INCIDENT_NOT_FOUND", "message": f"Incident {code} not found"},
            )

        now = datetime.now(timezone.utc)
        time_str = now.strftime("%H:%M")
        inc.status = new_status

        timeline = list(inc.timeline) if isinstance(inc.timeline, list) else []

        if new_status == "acknowledged":
            inc.acknowledged_at = now
            timeline.append(f"{time_str} — Acknowledged by {author}")
        elif new_status == "assigned":
            inc.assigned_at = now
            if assigned_team:
                inc.assigned_team = assigned_team
            if assigned_team_label:
                inc.assigned_team_label = assigned_team_label
            timeline.append(f"{time_str} — Assigned to {inc.assigned_team_label or inc.assigned_team}")
        elif new_status == "responding":
            inc.responding_at = now
            timeline.append(f"{time_str} — Team responding on scene")
        elif new_status == "resolved":
            inc.resolved_at = now
            timeline.append(f"{time_str} — Incident resolved")
        elif new_status == "closed":
            timeline.append(f"{time_str} — Incident closed")

        inc.timeline = timeline

        if notes:
            await self.incident_repo.add_note(inc, author=author, text=notes)

        await self.incident_repo.update(inc)

        # Broadcast update
        from app.redis.event_bus import event_bus
        await event_bus.publish(
            channel="byc:incidents",
            event_type="incident_update",
            payload={"incidentId": inc.incident_code, "status": inc.status, "message": f"Status changed to {inc.status}"},
            source="incident_service",
        )

        return await self.get_incident_by_code(code)

    async def add_note(self, code: str, note_data: IncidentNoteCreate) -> IncidentNoteRead:
        inc = await self.incident_repo.get_by_code(code)
        if not inc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "INCIDENT_NOT_FOUND", "message": f"Incident {code} not found"},
            )
        note = await self.incident_repo.add_note(inc, author=note_data.author, text=note_data.text)
        return IncidentNoteRead(
            id=note.id,
            author=note.author,
            text=note.text,
            note_time=note.note_time,
        )
