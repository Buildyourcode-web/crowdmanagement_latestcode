from typing import List
from app.schemas.analytics import (
    AttendanceAnalyticsResponse,
    CameraAnalyticsResponse,
    DailyAttendanceItem,
    HourlyAttendanceItem,
    IncidentAnalyticsResponse,
    IncidentTypeBreakdown,
)


class AnalyticsService:
    @staticmethod
    def get_attendance_analytics() -> AttendanceAnalyticsResponse:
        # No AI/ML data yet — return empty zeros
        return AttendanceAnalyticsResponse(
            totalVisitorsToday=0,
            peakHour="—",
            peakCount=0,
            avgPerHour=0,
            hourly=[HourlyAttendanceItem(hour=f"{h:02d}:00", visitors=0) for h in range(6, 23, 2)],
            daily=[],
        )

    @staticmethod
    def get_incident_analytics() -> IncidentAnalyticsResponse:
        # Real counts come from incidents table via DB query
        # Placeholder zeros until analytics aggregation is wired
        return IncidentAnalyticsResponse(
            total=0,
            resolved=0,
            active=0,
            avgResolutionMin=0,
            byType=[],
        )

    @staticmethod
    def get_camera_analytics() -> CameraAnalyticsResponse:
        return CameraAnalyticsResponse(
            uptime="—",
            totalDetections=0,
            avgFps=0,
            avgLatencyMs=0,
        )
