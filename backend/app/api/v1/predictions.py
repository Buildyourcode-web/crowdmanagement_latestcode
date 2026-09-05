from typing import List
from fastapi import APIRouter, Depends, status
from app.dependencies import get_current_user, require_permission
from app.models.user import User
from app.schemas.common import StandardResponse
from app.schemas.prediction import CrowdPredictionResponse, QueuePredictionItem, ZoneRiskPredictionItem
from app.security.permissions import Permissions
from app.services.prediction_service import PredictionService
from app.utils.response import success_response

router = APIRouter(prefix="/predictions", tags=["Predictions (AI Contracts)"])


@router.get("/crowd", response_model=StandardResponse[CrowdPredictionResponse])
async def get_crowd_prediction(
    current_user: User = Depends(require_permission(Permissions.CROWD_READ)),
):
    """
    Retrieve 60-minute crowd forecast contract.
    (Clearly marked MOCK status; ready for Phase 3 ML pipeline integration).
    """
    data = PredictionService.get_crowd_prediction()
    return success_response(data)


@router.get("/queues", response_model=StandardResponse[List[QueuePredictionItem]])
async def get_queue_predictions(
    current_user: User = Depends(require_permission(Permissions.CROWD_READ)),
):
    """Retrieve 30-minute queue wait-time trend forecasts."""
    data = PredictionService.get_queue_predictions()
    return success_response(data)


@router.get("/zones", response_model=StandardResponse[List[ZoneRiskPredictionItem]])
async def get_zone_risk_predictions(
    current_user: User = Depends(require_permission(Permissions.CROWD_READ)),
):
    """Retrieve zone risk escalation probability forecasts."""
    data = PredictionService.get_zone_risk_predictions()
    return success_response(data)
