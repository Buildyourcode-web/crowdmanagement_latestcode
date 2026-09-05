from typing import Any, List, Optional
from pydantic import BaseModel, Field


class GPUUnitStatus(BaseModel):
    id: str
    label: str
    utilization: int
    memory: int
    temperature: int
    inference_ms: int = Field(..., alias="inferenceMs")
    status: str

    class Config:
        populate_by_name = True


class GPUClusterStatus(BaseModel):
    units: List[GPUUnitStatus]
    avg_utilization: int = Field(..., alias="avgUtilization")

    class Config:
        populate_by_name = True


class ServiceStatusItem(BaseModel):
    name: str
    status: str
    latency_ms: Optional[int] = Field(None, alias="latencyMs")
    memory: Optional[str] = None
    connections: Optional[int] = None
    fps: Optional[int] = None
    bandwidth: Optional[str] = None
    packet_loss: Optional[str] = Field(None, alias="packetLoss")

    class Config:
        populate_by_name = True


class SystemHealthResponse(BaseModel):
    overall_status: str = Field(default="healthy", alias="overallStatus")
    cpu: int = Field(default=45)
    ram: int = Field(default=62)
    gpu: GPUClusterStatus
    cameras: dict
    database: ServiceStatusItem
    redis: ServiceStatusItem
    websocket: ServiceStatusItem
    vpn: ServiceStatusItem
    ai_engine: ServiceStatusItem = Field(..., alias="aiEngine")
    frs_engine: ServiceStatusItem = Field(..., alias="frsEngine")
    network: ServiceStatusItem

    class Config:
        populate_by_name = True
