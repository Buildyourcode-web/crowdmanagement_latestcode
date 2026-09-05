from typing import Any, List, Optional
from pydantic import BaseModel, Field


class TimeSeriesData(BaseModel):
    actual: List[List[Any]] = Field(..., description="[time, count] pairs")
    predicted: List[List[Any]] = Field(..., description="[time, count] pairs")
    lower: List[List[Any]] = Field(..., description="95% confidence lower bound")
    upper: List[List[Any]] = Field(..., description="95% confidence upper bound")


class CrowdPredictionResponse(BaseModel):
    status: str = Field(default="MOCK", example="MOCK")
    current: int = Field(..., example=60500)
    forecast_15_min: int = Field(..., example=64200)
    forecast_30_min: int = Field(..., example=68800)
    forecast_45_min: int = Field(..., example=73400)
    forecast_60_min: int = Field(..., example=78200)
    time_series: Optional[dict] = Field(None, alias="timeSeries")

    class Config:
        populate_by_name = True


class QueuePredictionItem(BaseModel):
    gate: str
    current_wait_min: int = Field(..., alias="currentWaitMin")
    predicted_wait_min_30: int = Field(..., alias="predictedWaitMin30")
    trend: str = "rising"

    class Config:
        populate_by_name = True


class ZoneRiskPredictionItem(BaseModel):
    zone: str
    current_risk: str = Field(..., alias="currentRisk")
    predicted_risk_30: str = Field(..., alias="predictedRisk30")
    probability: float = 0.88

    class Config:
        populate_by_name = True
