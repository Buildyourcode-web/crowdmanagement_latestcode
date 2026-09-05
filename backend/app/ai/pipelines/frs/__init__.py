"""
FRS AI Pipeline Package.

Provides production components for face detection, quality assessment,
512-D embedding extraction, candidate matching, and human review routing.
"""

from app.ai.pipelines.frs.config import FRSPipelineConfig
from app.ai.pipelines.frs.detector import DetectedFace, FaceDetector
from app.ai.pipelines.frs.embedding import (
    FaceEmbeddingEngine,
    batch_cosine_similarity,
    cosine_similarity,
    normalize_l2,
)
from app.ai.pipelines.frs.events import FRSEventEngine, FRSEventPayload, FRSEventType
from app.ai.pipelines.frs.health import FRSPipelineHealthTracker
from app.ai.pipelines.frs.matcher import CandidateMatch, CandidateMatcher
from app.ai.pipelines.frs.models_registry import FRSModelRegistry, FRSModelSpec
from app.ai.pipelines.frs.pipeline import FRSPipeline
from app.ai.pipelines.frs.quality import FaceQualityGate, FaceQualityResult
from app.ai.pipelines.frs.registry import FRSPipelineRegistry

__all__ = [
    "FRSPipeline",
    "FRSPipelineConfig",
    "FRSPipelineRegistry",
    "FaceDetector",
    "DetectedFace",
    "FaceQualityGate",
    "FaceQualityResult",
    "FaceEmbeddingEngine",
    "CandidateMatcher",
    "CandidateMatch",
    "FRSEventEngine",
    "FRSEventType",
    "FRSEventPayload",
    "FRSPipelineHealthTracker",
    "FRSModelRegistry",
    "FRSModelSpec",
    "cosine_similarity",
    "batch_cosine_similarity",
    "normalize_l2",
]
