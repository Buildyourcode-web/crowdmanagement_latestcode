from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class CrowdSummaryResponse(BaseModel):
    total_today: int = Field(..., alias="totalVisitorsToday", example=482350)
    current_crowd: int = Field(..., alias="currentCrowd", example=60500)
    active_queues: int = Field(..., alias="activeQueues", example=8)
    occupancy_percentage: float = Field(..., alias="occupancy", example=78.5)
    inflow_rate: int = Field(..., alias="inflowPerMin", example=823)
    outflow_rate: int = Field(..., alias="outflowPerMin", example=712)
    average_queue_wait_minutes: int = Field(..., alias="avgQueueWait", example=18)
    peak_hour: str = Field(..., alias="peakHour", example="18:00")
    critical_zones: int = Field(default=2)

    class Config:
        populate_by_name = True


class CrowdTimeSeriesPoint(BaseModel):
    hour: str = Field(..., example="14:00")
    crowd: int = Field(..., example=37000)
    inflow: int = Field(..., example=5000)
    outflow: int = Field(..., example=4200)


class QueueResponse(BaseModel):
    id: str = Field(..., example="QUEUE-01")
    gate: str = Field(..., example="GATE-01")
    zone: str = Field(..., example="ZONE-A")
    length: int = Field(..., example=420)
    wait_minutes: int = Field(..., alias="waitMinutes", example=22)
    processing_rate: int = Field(..., alias="processingRate", example=145)
    growth_rate: int = Field(..., alias="growthRate", example=8)
    status: str = Field(..., example="high")

    class Config:
        populate_by_name = True
