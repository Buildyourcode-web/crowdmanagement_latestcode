"""
Crowd AI Real-Time Detection, Tracking & Spatial Analytics Pipeline.
"""

from app.ai.pipelines.crowd.analytics import CrowdMetricsResult, CrowdSpatialAnalytics
from app.ai.pipelines.crowd.config import CrowdPipelineConfig
from app.ai.pipelines.crowd.detector import (
    BasePersonDetector,
    DeepStreamPersonDetector,
    DetectedPerson,
    MockPersonDetector,
)
from app.ai.pipelines.crowd.events import CrowdAIEvent, CrowdEventEngine
from app.ai.pipelines.crowd.health import PipelineHealthMonitor, PipelineHealthStatus
from app.ai.pipelines.crowd.models_registry import ModelRegistryService, PersonDetectionModel
from app.ai.pipelines.crowd.pipeline import CrowdPipeline
from app.ai.pipelines.crowd.queue_engine import QueueMetricsResult, QueueMovementEngine
from app.ai.pipelines.crowd.registry import CrowdPipelineRegistry
from app.ai.pipelines.crowd.risk import CrowdRiskEngine
from app.ai.pipelines.crowd.tracker import PersonTracker, TrackedPerson

__all__ = [
    "BasePersonDetector",
    "CrowdAIEvent",
    "CrowdEventEngine",
    "CrowdMetricsResult",
    "CrowdPipeline",
    "CrowdPipelineConfig",
    "CrowdPipelineRegistry",
    "CrowdRiskEngine",
    "CrowdSpatialAnalytics",
    "DeepStreamPersonDetector",
    "DetectedPerson",
    "MockPersonDetector",
    "ModelRegistryService",
    "PersonDetectionModel",
    "PersonTracker",
    "PipelineHealthMonitor",
    "PipelineHealthStatus",
    "QueueMetricsResult",
    "QueueMovementEngine",
    "TrackedPerson",
]
