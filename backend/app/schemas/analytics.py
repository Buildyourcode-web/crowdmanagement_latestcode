from typing import Any, List, Optional
from pydantic import BaseModel, Field


class HourlyAttendanceItem(BaseModel):
    hour: str
    visitors: int


class DailyAttendanceItem(BaseModel):
    day: str
    visitors: int


class AttendanceAnalyticsResponse(BaseModel):
    total_visitors_today: int = Field(..., alias="totalVisitorsToday")
    peak_hour: str = Field(..., alias="peakHour")
    peak_count: int = Field(..., alias="peakCount")
    avg_per_hour: int = Field(..., alias="avgPerHour")
    hourly: List[HourlyAttendanceItem]
    daily: List[DailyAttendanceItem]

    class Config:
        populate_by_name = True


class IncidentTypeBreakdown(BaseModel):
    type: str
    count: int


class IncidentAnalyticsResponse(BaseModel):
    total: int
    resolved: int
    active: int
    avg_resolution_min: int = Field(..., alias="avgResolutionMin")
    by_type: List[IncidentTypeBreakdown] = Field(..., alias="byType")

    class Config:
        populate_by_name = True


class CameraAnalyticsResponse(BaseModel):
    uptime: str = "99.4%"
    total_detections: int = Field(..., alias="totalDetections")
    avg_fps: int = Field(default=24, alias="avgFps")
    avg_latency_ms: int = Field(default=38, alias="avgLatencyMs")

    class Config:
        populate_by_name = True
