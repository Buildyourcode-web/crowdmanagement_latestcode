import os

files = {}

files['app/schemas/settings.py'] = '''from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Any, Dict, List, Optional
from datetime import datetime


class EventSettingsUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    year: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None
    timezone: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v and v not in ["PLANNING", "ACTIVE", "SUSPENDED", "COMPLETED"]:
            raise ValueError("Status must be PLANNING, ACTIVE, SUSPENDED, or COMPLETED")
        return v


class EventSettingsResponse(BaseModel):
    id: str
    code: str
    name: str
    description: Optional[str] = None
    year: int
    start_date: datetime
    end_date: datetime
    status: str
    timezone: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ZoneSettingsUpdate(BaseModel):
    name: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    capacity: Optional[int] = Field(None, ge=100, le=500000)
    status: Optional[str] = None
    risk_level: Optional[str] = None
    color: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status_zone(cls, v):
        if v and v not in ["ACTIVE", "INACTIVE", "MAINTENANCE"]:
            raise ValueError("Invalid zone status")
        return v

    @field_validator("risk_level")
    @classmethod
    def validate_risk(cls, v):
        if v and v not in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
            raise ValueError("Invalid risk level")
        return v


class ZoneSettingsResponse(BaseModel):
    id: str
    zone_code: str
    name: str
    label: str
    description: Optional[str] = None
    capacity: int
    current_people: int
    density: float
    density_label: str
    status: str
    risk_level: str
    color: str
    coordinates: Any
    center: Any
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class CameraSettingsUpdate(BaseModel):
    name: Optional[str] = None
    label: Optional[str] = None
    camera_type: Optional[str] = None
    zone_code: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = Field(None, ge=1, le=60)
    is_frs_camera: Optional[bool] = None
    is_ptz: Optional[bool] = None
    status: Optional[str] = None
    ai_status: Optional[str] = None
    rtsp_url: Optional[str] = None


class CameraSettingsResponse(BaseModel):
    id: str
    camera_code: str
    name: str
    label: str
    camera_type: str
    zone_code: Optional[str] = None
    resolution: str
    fps: int
    latency_ms: int
    status: str
    ai_status: str
    is_frs_camera: bool
    is_ptz: bool
    people_count: int
    has_rtsp_configured: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class CameraTestResponse(BaseModel):
    camera_code: str
    connection_status: str
    latency_ms: Optional[int] = None
    fps: Optional[int] = None
    resolution: Optional[str] = None
    tested_at: datetime
    message: str


class AlertThresholdUpdate(BaseModel):
    crowd_warning_pct: Optional[float] = Field(None, ge=50.0, le=100.0)
    crowd_high_pct: Optional[float] = Field(None, ge=60.0, le=120.0)
    crowd_critical_pct: Optional[float] = Field(None, ge=70.0, le=150.0)
    crowd_extreme_pct: Optional[float] = Field(None, ge=80.0, le=200.0)
    queue_warning_count: Optional[int] = Field(None, ge=50)
    queue_critical_count: Optional[int] = Field(None, ge=100)
    queue_wait_warning_min: Optional[int] = Field(None, ge=1, le=120)
    queue_wait_critical_min: Optional[int] = Field(None, ge=5, le=240)
    sudden_inflow_pct: Optional[float] = Field(None, ge=5.0, le=200.0)
    reverse_flow_pct: Optional[float] = Field(None, ge=5.0, le=100.0)
    density_growth_rate_pct: Optional[float] = Field(None, ge=1.0, le=100.0)
    camera_offline_sec: Optional[int] = Field(None, ge=5, le=300)
    camera_degraded_sec: Optional[int] = Field(None, ge=1, le=60)
    person_down_sec: Optional[int] = Field(None, ge=3, le=60)
    panic_risk_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    bottleneck_risk_score: Optional[float] = Field(None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_thresholds_order(self):
        w, h, c, e = self.crowd_warning_pct, self.crowd_high_pct, self.crowd_critical_pct, self.crowd_extreme_pct
        if w and h and h <= w:
            raise ValueError("High threshold must be greater than warning threshold")
        if h and c and c <= h:
            raise ValueError("Critical threshold must be greater than high threshold")
        if c and e and e <= c:
            raise ValueError("Extreme threshold must be greater than critical threshold")
        qw, qc = self.queue_warning_count, self.queue_critical_count
        if qw and qc and qc <= qw:
            raise ValueError("Queue critical count must exceed warning count")
        ww, wc = self.queue_wait_warning_min, self.queue_wait_critical_min
        if ww and wc and wc <= ww:
            raise ValueError("Critical wait time must exceed warning wait time")
        return self


class AlertThresholdResponse(BaseModel):
    id: str
    crowd_warning_pct: float
    crowd_high_pct: float
    crowd_critical_pct: float
    crowd_extreme_pct: float
    queue_warning_count: int
    queue_critical_count: int
    queue_wait_warning_min: int
    queue_wait_critical_min: int
    sudden_inflow_pct: float
    reverse_flow_pct: float
    density_growth_rate_pct: float
    camera_offline_sec: int
    camera_degraded_sec: int
    person_down_sec: int
    panic_risk_score: float
    bottleneck_risk_score: float
    config_version: int
    updated_by: Optional[str] = None
    updated_at: datetime
    model_config = {"from_attributes": True}


class RoleCreate(BaseModel):
    code: str
    name: str
    description: Optional[str] = None


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class RolePermissionsUpdate(BaseModel):
    permissions: List[str]


class PermissionResponse(BaseModel):
    id: str
    code: str
    name: str
    description: Optional[str] = None
    model_config = {"from_attributes": True}


class RoleSettingsResponse(BaseModel):
    id: str
    code: str
    name: str
    description: Optional[str] = None
    user_count: int
    is_system_role: bool
    permissions: List[PermissionResponse]
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class NotificationUpdate(BaseModel):
    inapp_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    websocket_enabled: Optional[bool] = None
    critical_immediate: Optional[bool] = None
    high_immediate: Optional[bool] = None
    medium_grouped: Optional[bool] = None
    low_summary: Optional[bool] = None
    email_recipients: Optional[List[str]] = None


class NotificationResponse(BaseModel):
    id: str
    inapp_enabled: bool
    email_enabled: bool
    sms_enabled: bool
    websocket_enabled: bool
    critical_immediate: bool
    high_immediate: bool
    medium_grouped: bool
    low_summary: bool
    email_recipients: List
    config_version: int
    updated_by: Optional[str] = None
    updated_at: datetime
    model_config = {"from_attributes": True}


class AIConfigUpdate(BaseModel):
    crowd_detection_enabled: Optional[bool] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    detection_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    tracking_algorithm: Optional[str] = None
    processing_fps: Optional[int] = Field(None, ge=1, le=30)
    people_counting_enabled: Optional[bool] = None
    queue_detection_enabled: Optional[bool] = None
    bottleneck_detection_enabled: Optional[bool] = None
    reverse_flow_detection_enabled: Optional[bool] = None
    fall_detection_enabled: Optional[bool] = None
    panic_risk_detection_enabled: Optional[bool] = None


class AIConfigResponse(BaseModel):
    id: str
    crowd_detection_enabled: bool
    model_name: str
    model_version: str
    detection_confidence: float
    tracking_algorithm: str
    processing_fps: int
    people_counting_enabled: bool
    queue_detection_enabled: bool
    bottleneck_detection_enabled: bool
    reverse_flow_detection_enabled: bool
    fall_detection_enabled: bool
    panic_risk_detection_enabled: bool
    config_version: int
    updated_by: Optional[str] = None
    updated_at: datetime
    model_config = {"from_attributes": True}


class FRSConfigUpdate(BaseModel):
    face_detection_enabled: Optional[bool] = None
    min_face_size: Optional[int] = Field(None, ge=20, le=500)
    face_quality_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    match_threshold: Optional[float] = Field(None, ge=0.5, le=1.0)
    candidate_threshold: Optional[float] = Field(None, ge=0.3, le=1.0)
    max_candidates: Optional[int] = Field(None, ge=1, le=20)
    watchlist_access_enabled: Optional[bool] = None
    missing_person_access_enabled: Optional[bool] = None
    candidate_retention_days: Optional[int] = Field(None, ge=1, le=365)
    image_retention_days: Optional[int] = Field(None, ge=1, le=730)
    audit_retention_days: Optional[int] = Field(None, ge=30, le=2555)

    @model_validator(mode="after")
    def validate_thresholds(self):
        c, m = self.candidate_threshold, self.match_threshold
        if c and m and c > m:
            raise ValueError("Candidate threshold cannot be greater than match threshold")
        return self


class FRSConfigResponse(BaseModel):
    id: str
    face_detection_enabled: bool
    min_face_size: int
    face_quality_threshold: float
    match_threshold: float
    candidate_threshold: float
    max_candidates: int
    human_review_required: bool
    auto_confirmation_enabled: bool
    watchlist_access_enabled: bool
    missing_person_access_enabled: bool
    candidate_retention_days: int
    image_retention_days: int
    audit_retention_days: int
    config_version: int
    updated_by: Optional[str] = None
    updated_at: datetime
    model_config = {"from_attributes": True}


class SystemConfigUpdate(BaseModel):
    app_name: Optional[str] = None
    environment: Optional[str] = None
    timezone: Optional[str] = None
    websocket_enabled: Optional[bool] = None
    redis_pubsub_enabled: Optional[bool] = None
    event_retention_days: Optional[int] = Field(None, ge=1, le=365)


class MaintenanceModeUpdate(BaseModel):
    enabled: bool
    message: Optional[str] = None
    confirm: bool = False


class SystemConfigResponse(BaseModel):
    id: str
    app_name: str
    app_version: str
    environment: str
    timezone: str
    websocket_enabled: bool
    redis_pubsub_enabled: bool
    event_retention_days: int
    maintenance_mode: bool
    maintenance_message: Optional[str] = None
    config_version: int
    updated_by: Optional[str] = None
    updated_at: datetime
    model_config = {"from_attributes": True}


class SettingsAuditResponse(BaseModel):
    id: str
    username: str
    action: str
    resource_type: str
    resource_id: str
    timestamp: datetime
    ip_address: Optional[str] = None
    metadata_json: Dict
    model_config = {"from_attributes": True}


class SettingsSummaryResponse(BaseModel):
    alert_thresholds: AlertThresholdResponse
    ai_config: AIConfigResponse
    frs_config: FRSConfigResponse
    notification_config: NotificationResponse
    system_config: SystemConfigResponse
'''

for path, content in files.items():
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'OK: {path}')
