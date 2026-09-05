from typing import List
from fastapi import APIRouter, Depends, status
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.common import StandardResponse
from app.security.permissions import Permissions
from app.utils.response import success_response

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("", response_model=StandardResponse[List[dict]])
async def list_reports(
    current_user: User = Depends(require_permission(Permissions.REPORTS_READ)),
):
    """Retrieve generated operational reports."""
    reports = [
        {"id": "REP-2026-001", "title": "Day 8 Executive Daily Briefing", "type": "DAILY_SUMMARY", "generated_at": "2026-09-14T23:00:00Z", "format": "PDF"},
        {"id": "REP-2026-002", "title": "Crowd Density & Flow Analysis", "type": "CROWD_ANALYTICS", "generated_at": "2026-09-14T20:00:00Z", "format": "CSV"},
        {"id": "REP-2026-003", "title": "Incident & Medical Response Audit", "type": "INCIDENT_AUDIT", "generated_at": "2026-09-14T18:00:00Z", "format": "PDF"},
        {"id": "REP-2026-004", "title": "FRS Review & Compliance Log", "type": "FRS_AUDIT", "generated_at": "2026-09-14T16:00:00Z", "format": "PDF"},
    ]
    return success_response(reports)


@router.post("/generate", response_model=StandardResponse[dict])
async def generate_report(
    report_type: str = "DAILY_SUMMARY",
    current_user: User = Depends(require_permission(Permissions.REPORTS_EXPORT)),
):
    """Generate and queue an operational report."""
    return success_response({
        "report_id": f"REP-2026-{int(report_type.lower() == 'daily_summary') + 5}",
        "status": "QUEUED",
        "message": f"Report '{report_type}' queued for generation",
    })
