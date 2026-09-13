import uuid
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.common import BaseSchema


class CameraRead(BaseSchema):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str = Field(..., example="CAM-KHB-001")
    camera_code: str
    name: str
    label: str
    description: Optional[str] = None
    camera_type: str
    
    # Network & RTSP (Sanitized - credentials never exposed)
    private_ip: Optional[str] = None
    port: Optional[int] = 554
    rtsp_url: Optional[str] = None
    username: Optional[str] = None
    codec: Optional[str] = "h264"
    protocol: Optional[str] = "rtsp"
    
    # Location & Zone
    zone: Optional[str] = Field(None, example="ZONE-A")
    zone_id: Optional[uuid.UUID] = None
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    coordinates: List[float] = Field(default_factory=lambda: [78.4635, 17.4175], example=[78.4635, 17.4175])
    
    # Status & Health
    status: str = Field(..., example="online")
    ai_status: str = Field(..., example="online")
    stream_status: str = Field(default="NOT_TESTED", example="ONLINE")
    stream_stability: str = Field(default="UNKNOWN", example="STABLE")
    enabled: bool = True
    is_active: bool = True
    active_from: Optional[datetime] = None
    removed_at: Optional[datetime] = None
    event_id: Optional[uuid.UUID] = None
    site_id: Optional[uuid.UUID] = None
    
    # Capabilities & Metrics
    is_frs: bool = Field(..., alias="is_frs_camera")
    is_ptz: bool = False
    resolution: str = Field(..., example="1080p")
    fps: int = Field(..., example=24)
    latency: int = Field(..., alias="latency_ms", example=38)
    packet_loss: Optional[str] = None
    people_count: int = Field(default=0)
    reconnect_count: int = 0
    last_error: Optional[str] = None
    gpu_id: Optional[str] = "GPU-01"
    last_seen_at: Optional[datetime] = None
    last_tested_at: Optional[datetime] = None

    # Logical AI Identifiers & Exclusive Mode
    logical_id_frs: Optional[str] = None
    logical_id_crowd: Optional[str] = None
    ai_mode: Optional[str] = None
    frs_status: Optional[str] = None
    crowd_status: Optional[str] = None


class CameraCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    camera_id: Optional[str] = Field(None, alias="camera_code", example="CAM-KHB-102")
    camera_code: Optional[str] = Field(None, example="CAM-KHB-102")
    name: str = Field(..., example="North Gate 3 High Angle")
    label: Optional[str] = Field(None, example="North Gate 3 High Angle")
    description: Optional[str] = Field(None, example="Main pedestrian entry monitoring")
    camera_type: str = Field(default="CROWD", example="CROWD")
    
    # Network & RTSP
    private_ip: Optional[str] = Field(None, example="192.168.0.102")
    port: Optional[int] = Field(default=554, example=554)
    rtsp_url: Optional[str] = Field(None, example="rtsp://192.168.0.102:554/Streaming/Channels/101")
    username: Optional[str] = Field(None, example="admin")
    password: Optional[str] = Field(None, example="SecretPass123")
    codec: Optional[str] = Field(default="h264", example="h264")
    protocol: Optional[str] = Field(default="rtsp", example="rtsp")
    
    # Zone & Location
    zone_code: Optional[str] = Field(None, example="ZONE-A")
    zone_id: Optional[uuid.UUID] = None
    location_name: Optional[str] = Field(None, example="North Gate Entry Arch")
    latitude: Optional[float] = Field(None, example=17.4175)
    longitude: Optional[float] = Field(None, example=78.4635)
    coordinates: Optional[List[float]] = Field(None, example=[78.4635, 17.4175])
    
    # Flags & Scoping
    is_frs_camera: bool = False
    is_ptz: bool = False
    resolution: str = "1080p"
    fps: int = 25
    event_id: Optional[uuid.UUID] = None
    site_id: Optional[uuid.UUID] = None
    is_active: bool = True


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    camera_type: Optional[str] = None
    private_ip: Optional[str] = None
    port: Optional[int] = None
    rtsp_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    zone_code: Optional[str] = None
    zone_id: Optional[uuid.UUID] = None
    event_id: Optional[uuid.UUID] = None
    site_id: Optional[uuid.UUID] = None
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    coordinates: Optional[List[float]] = None
    status: Optional[str] = None
    ai_status: Optional[str] = None
    enabled: Optional[bool] = None
    is_active: Optional[bool] = None
    fps: Optional[int] = None
    resolution: Optional[str] = None
    is_frs_camera: Optional[bool] = None
    is_ptz: Optional[bool] = None


class CameraHealth(BaseModel):
    camera_id: str
    status: str
    stream_status: str = "NOT_TESTED"
    fps: int
    latency_ms: int
    packet_loss_pct: float
    gpu_unit: str
    uptime_percentage: float = 99.4
    last_seen: str
    last_tested: Optional[str] = None
    stability: str = "UNKNOWN"
    last_error: Optional[str] = None


class CameraStatsResponse(BaseModel):
    total: int
    online: int
    degraded: int
    offline: int
    not_tested: int = 0
    frs_count: int
    ptz_count: int


class RTSPTestRequest(BaseModel):
    camera_id: Optional[str] = None
    rtsp_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    timeout_sec: float = 6.0


class RTSPTestResponse(BaseModel):
    camera_id: str
    reachable: bool
    authenticated: bool
    stream_available: bool
    resolution: Optional[str] = None
    fps: Optional[int] = None
    codec: Optional[str] = None
    latency_ms: Optional[int] = None
    protocol: Optional[str] = "rtsp"
    stability: Optional[str] = None
    tested_at: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class BulkCameraRow(BaseModel):
    camera_id: str
    camera_name: str
    private_ip: Optional[str] = None
    rtsp_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    zone: Optional[str] = None
    camera_type: str = "CROWD"
    location: Optional[str] = None


class BulkCameraValidateResult(BaseModel):
    total: int
    valid_count: int
    invalid_count: int
    duplicate_count: int
    valid_rows: List[BulkCameraRow] = []
    invalid_rows: List[dict] = []
    duplicate_rows: List[dict] = []


class BulkCameraImportRequest(BaseModel):
    cameras: List[BulkCameraRow]


class BulkCameraImportResult(BaseModel):
    imported_count: int
    failed_count: int
    imported_camera_ids: List[str] = []
    errors: List[dict] = []
