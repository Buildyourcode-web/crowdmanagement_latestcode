from typing import List
from app.schemas.prediction import CrowdPredictionResponse, QueuePredictionItem, ZoneRiskPredictionItem


class PredictionService:
    @staticmethod
    def get_crowd_prediction() -> CrowdPredictionResponse:
        # AI model not connected yet — return zero contract
        return CrowdPredictionResponse(
            status="NO_DATA",
            current=0,
            forecast_15_min=0,
            forecast_30_min=0,
            forecast_45_min=0,
            forecast_60_min=0,
        )

    @staticmethod
    def get_queue_predictions() -> List[QueuePredictionItem]:
        # No queue prediction data yet
        return []

    @staticmethod
    def get_zone_risk_predictions() -> List[ZoneRiskPredictionItem]:
        # No zone risk prediction data yet
        return []
