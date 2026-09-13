from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HourlyFlowPoint(BaseModel):
    hour: str = Field(..., description="Hour format e.g. 00:00, 01:00")
    entry: int = Field(0, description="Valid IN crossings in this hour")
    exit: int = Field(0, description="Valid OUT crossings in this hour")
    net_flow: int = Field(0, description="Net flow: entry - exit")


class DailyTrendPoint(BaseModel):
    date: str = Field(..., description="Date string e.g. 2026-09-09 or 09 Sep")
    entries: int = Field(0, description="Total valid entries on this day")
    exits: int = Field(0, description="Total valid exits on this day")
    net_flow: int = Field(0, description="Net flow: entries - exits")


class QueueStatusItem(BaseModel):
    queue_name: str
    camera_code: str
    current_people: int
    estimated_wait_minutes: Optional[int] = None
    flow_status: str = Field("NORMAL", description="FAST, NORMAL, SLOW, STOPPED")
    queue_direction: str = "UNKNOWN"
    risk_level: str = "LOW"


class QueueMovementPoint(BaseModel):
    time: str
    people_in: int = 0
    people_out: int = 0
    queue_length: int = 0


class ZoneDensityItem(BaseModel):
    zone_code: str
    zone_name: str
    current_people: int
    capacity: int
    density_pct: float
    status: str = Field("GREEN", description="GREEN (Normal), ORANGE (Warning), RED (Danger)")
    risk_level: str = "LOW"
    flow_trend: str = "STABLE"
    camera_code: Optional[str] = None
    camera_name: Optional[str] = None


class ZoneTrendPoint(BaseModel):
    time: str
    zone_code: str
    people_count: int
    density_pct: float


class TopRiskAreaItem(BaseModel):
    name: str
    type: str = Field("ZONE", description="ZONE or QUEUE")
    risk_level: str = Field("ORANGE", description="ORANGE or RED")
    current_people: int
    reason: str


class FRSReviewCandidateItem(BaseModel):
    id: str
    candidate_code: str
    person_name: str
    match_score: float
    detected_image: str
    reference_image: Optional[str] = None
    camera_name: str
    timestamp: str
    time_str: str
    status: str = "REVIEW_REQUIRED"
    category: str = "Authorized Watchlist"


class AICameraHealth(BaseModel):
    cameras_online: int = 0
    cameras_offline: int = 0
    cameras_total: int = 0
    crowd_ai_running: int = 0
    queue_ai_running: int = 0
    frs_running: int = 0
    system_status: str = "OPTIMAL"


class ActiveCriticalEventItem(BaseModel):
    id: str
    severity: str
    type: str
    location: str
    time: str
    status: str
    description: Optional[str] = None


class DashboardSummaryResponse(BaseModel):
    # Top Header & Metadata
    timestamp: str
    data_status: str = Field("LIVE DATA", description="LIVE DATA, UPDATING, or DEGRADED")
    date_range_selected: str = "TODAY"

    # Hero KPI
    total_visitors_festival: int = Field(0, description="Cumulative entry across all festival days")
    festival_total_entries: int = Field(0, description="Cumulative entries across all festival days (14-24 Sept)")
    festival_total_exits: int = Field(0, description="Cumulative exits across all festival days (14-24 Sept)")
    festival_day_current: int = 1
    festival_day_total: int = 10
    festival_day_label: str = "Day 1 of 10"
    today_entries: int = 0
    today_exits: int = 0
    selected_range_entries: int = 0
    selected_range_exits: int = 0
    selected_range_label: str = "Today"

    # People Movement Panel
    current_occupancy: int = 0
    net_flow: int = 0

    # Hourly Visitor Flow
    hourly_flow: List[HourlyFlowPoint] = Field(default_factory=list)
    peak_hour: str = "—"

    # Daily Trend
    daily_trend: List[DailyTrendPoint] = Field(default_factory=list)

    # Queue Status & Flow
    queues: List[QueueStatusItem] = Field(default_factory=list)
    queue_movement: List[QueueMovementPoint] = Field(default_factory=list)

    # Zone Density
    zones: List[ZoneDensityItem] = Field(default_factory=list)
    zone_trends: List[ZoneTrendPoint] = Field(default_factory=list)

    # Top Risk Areas (Max 3-5)
    top_risk_areas: List[TopRiskAreaItem] = Field(default_factory=list)

    # Recent FRS Review (Max 2)
    recent_frs_candidates: List[FRSReviewCandidateItem] = Field(default_factory=list)

    # AI & Camera Health
    health: AICameraHealth

    # Active Critical Events (Max 5)
    active_critical_events: List[ActiveCriticalEventItem] = Field(default_factory=list)
