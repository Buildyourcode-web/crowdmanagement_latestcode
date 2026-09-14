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
    total_entries: int = Field(0, alias="totalEntries")
    total_exits: int = Field(0, alias="totalExits")
    total_footfall: int = Field(0, alias="totalFootfall")
    peak_hour: str = Field(..., alias="peakHour")
    peak_count: int = Field(..., alias="peakCount")
    avg_per_hour: int = Field(..., alias="avgPerHour")
    day_number: Optional[int] = Field(None, alias="dayNumber")
    selected_day_label: Optional[str] = Field(None, alias="selectedDayLabel")
    event_days: List[dict] = Field(default_factory=list, alias="eventDays")
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


# ── Actionable Operational Flow & Clearance Models ─────────────────────────

class ZoneClearanceItem(BaseModel):
    zone_id: Optional[str] = None
    zone_name: str
    zone_code: str
    current_occupancy: int
    capacity: int
    density_pct: int
    risk_level: str  # NORMAL, WARNING, CRITICAL
    clearance_priority: str  # IMMEDIATE (P0), HIGH (P1), MODERATE (P2), NONE
    clearance_needed: bool
    marshals_needed: int
    recommended_action: str


class QueueDirectiveItem(BaseModel):
    queue_id: Optional[str] = None
    queue_name: str
    current_waiting: int
    estimated_wait_min: int
    movement_status: str  # MOVING, SLOW, STOPPED
    is_bottleneck: bool
    diversion_route: Optional[str] = None
    directive: str


class GateBalanceItem(BaseModel):
    gate_name: str
    gate_type: str  # ENTRY, EXIT
    flow_rate_per_min: int
    status: str  # FLOWING, CONGESTED, SLOW
    action: str


class TacticalDirective(BaseModel):
    id: str
    priority: str  # CRITICAL, WARNING, INFO
    category: str  # ZONE_CLEARANCE, QUEUE_DIVERSION, GATE_CONTROL, POLICE_ACTION
    title: str
    action: str
    target_area: str
    reason: str
    impact: str


class OperationalFlowResponse(BaseModel):
    festival_status: str  # OPTIMAL, MODERATE, HIGH_DENSITY, CRITICAL
    net_flow_rate_pax_min: int
    total_inside_festival: int
    top_directives: List[TacticalDirective]
    zones: List[ZoneClearanceItem]
    queues: List[QueueDirectiveItem]
    gates: List[GateBalanceItem]
    generated_at: str


# ── 10-Day Festival Day-Wise Attendance Models ──────────────────────────────

class FestivalDayAttendanceItem(BaseModel):
    day_number: int = Field(..., description="Day number 1 to 10")
    date: str = Field(..., description="Date string YYYY-MM-DD")
    day_name: str = Field(..., description="Monday, Tuesday, etc.")
    label: str = Field(..., description="e.g. Day 1: 07 Sep (Mon)")
    entry_count: int = Field(0, description="Total valid entry crossings")
    exit_count: int = Field(0, description="Total valid exit crossings")
    total_count: int = Field(0, description="Total count = Entry + Exit")
    net_inside: int = Field(0, description="Net count currently inside or peak net inside")
    peak_hour: str = Field("—", description="Peak movement hour e.g. 18:00 - 19:00")
    status: str = Field("UPCOMING", description="COMPLETED, TODAY, or UPCOMING")


class Festival10DaysResponse(BaseModel):
    event_id: Optional[str] = None
    event_name: str = "Khairatabad Ganesh Festival 2026"
    start_date: str
    end_date: str
    current_day: int
    total_entries_10days: int
    total_exits_10days: int
    grand_total_footfall: int = Field(..., description="Total Entry + Total Exit across all 10 days")
    days: List[FestivalDayAttendanceItem]


