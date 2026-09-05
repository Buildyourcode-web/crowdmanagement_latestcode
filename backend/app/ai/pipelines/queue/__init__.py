"""
Queue AI Real-Time Detection, Tracking & Queue Analytics Package.
"""

from app.ai.pipelines.queue.models_registry import QueueModelRegistryService, QUEUE_MODEL_REGISTRY
from app.ai.pipelines.queue.config import QueuePipelineConfig, QueueGeometryRequirement, sanitize_rtsp_url
from app.ai.pipelines.queue.analytics import QueueMetricsResult, QueueSpatialAnalytics
from app.ai.pipelines.queue.risk import QueueRiskEngine, QueueRiskEvaluation
from app.ai.pipelines.queue.events import QueueEventEngine, QueueAIEvent
from app.ai.pipelines.queue.pipeline import QueuePipeline
from app.ai.pipelines.queue.registry import QueuePipelineRegistry

__all__ = [
    "QueueModelRegistryService",
    "QUEUE_MODEL_REGISTRY",
    "QueuePipelineConfig",
    "QueueGeometryRequirement",
    "sanitize_rtsp_url",
    "QueueMetricsResult",
    "QueueSpatialAnalytics",
    "QueueRiskEngine",
    "QueueRiskEvaluation",
    "QueueEventEngine",
    "QueueAIEvent",
    "QueuePipeline",
    "QueuePipelineRegistry",
]
