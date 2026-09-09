"""
crowd_management.py — Schemas for Unified Crowd Management Dashboard.

Defines response structures for consolidated crowd, queue, zone, camera health,
risk breakdown, trends, and active events.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MovementTrendPoint(BaseModel):
    timestamp_label: str
    entries: int = 0
    exits: int = 0
    people_inside: int = 0


class QueueTrendPoint(BaseModel):
    timestamp_label: str
    queue_count: int = 0
    inflow_rate: int = 0
    outflow_rate: int = 0


class ZoneTrendPoint(BaseModel):
    timestamp_label: str
    densities: Dict[str, float] = Field(default_factory=dict)


class QueueCameraStatus(BaseModel):
    camera_id: Optional[str] = None
    camera_code: str
    camera_name: str
    queue_name: str
    zone_code: Optional[str] = None
    current_people: int = 0
    queue_length: float = 0.0
    queue_length_unit: str = "normalized_extent"
    average_wait_seconds: Optional[int] = None
    inflow_rate: Optional[int] = None
    outflow_rate: Optional[int] = None
    growth_rate: Optional[int] = None
    queue_direction: str = "UNKNOWN"
    risk_level: str = "LOW"
    camera_status: str = "OFFLINE"
    pipeline_status: str = "STOPPED"


class ZoneCameraStatus(BaseModel):
    zone_id: Optional[str] = None
    zone_code: str
    zone_name: str
    camera_id: Optional[str] = None
    camera_code: Optional[str] = None
    current_people: int = 0
    capacity: int = 1000
    density_pct: float = 0.0
    density_level: str = "LOW"
    risk_level: str = "LOW"
    trend: str = "STABLE"
    camera_status: str = "OFFLINE"
    pipeline_status: str = "STOPPED"


class CameraStatusItem(BaseModel):
    camera_id: Optional[str] = None
    camera_code: str
    name: str
    purpose: str = "CROWD"  # QUEUE or ZONE
    stream_status: str = "OFFLINE"
    fps: float = 0.0
    pipeline_status: str = "STOPPED"
    current_people: int = 0
    last_update: Optional[str] = None


class CrowdRiskBreakdown(BaseModel):
    overall_risk: str = "LOW"
    risk_score: float = 0.0
    density_contribution: float = 0.0
    inflow: int = 0
    crowd_growth: int = 0
    highest_risk_queue: Optional[str] = None
    highest_risk_zone: Optional[str] = None


class HighRiskAreaItem(BaseModel):
    name: str
    area_type: str  # QUEUE or ZONE
    current_people: int = 0
    density_pct: Optional[float] = None
    risk_level: str = "LOW"
    trend: str = "STABLE"
    camera_code: str = ""


class ActiveEventItem(BaseModel):
    id: str
    alert_code: str
    title: str
    message: str
    severity: str
    type: str
    camera_code: Optional[str] = None
    zone_code: Optional[str] = None
    detected_at: str
    status: str = "active"


class CrowdManagementSummaryResponse(BaseModel):
    total_people: int = 0
    total_entries: int = 0
    total_exits: int = 0
    net_change: int = 0
    active_cameras: int = 0
    total_cameras: int = 0
    active_queues: int = 0
    high_risk_zones: int = 0
    longest_queue: int = 0
    longest_wait_seconds: int = 0
    overall_risk: str = "LOW"
    time_range: str = "today"
    timestamp: str
    queues: List[QueueCameraStatus] = Field(default_factory=list)
    zones: List[ZoneCameraStatus] = Field(default_factory=list)
    cameras: List[CameraStatusItem] = Field(default_factory=list)
    risk_breakdown: CrowdRiskBreakdown = Field(default_factory=CrowdRiskBreakdown)
    high_risk_areas: List[HighRiskAreaItem] = Field(default_factory=list)
    events: List[ActiveEventItem] = Field(default_factory=list)
    trends: Dict[str, Any] = Field(default_factory=dict)
