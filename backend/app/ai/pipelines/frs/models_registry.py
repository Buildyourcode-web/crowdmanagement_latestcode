"""
models_registry.py — FRS Model Registry.

Formal registration, versioning, and parameter specifications for:
1. Face Detection & Landmark Extraction (SCRFD / Buffalo_L)
2. Face Recognition & Embedding (ArcFace ResNet-50 / Buffalo_L)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class FRSModelSpec:
    model_id: str
    model_name: str
    model_type: str  # "DETECTOR" | "EMBEDDER"
    version: str
    runtime: str  # "ONNX_RUNTIME" | "TENSORRT" | "OPENCV"
    input_size: Tuple[int, int]  # (W, H)
    embedding_dim: Optional[int] = None
    similarity_metric: Optional[str] = None  # "COSINE"
    classes: List[str] = field(default_factory=lambda: ["face"])
    license: str = "MIT"
    checksum: Optional[str] = None
    description: str = ""


class FRSModelRegistry:
    """Registry catalog for face detection and embedding models."""

    _MODELS: Dict[str, FRSModelSpec] = {
        "buffalo_l_det": FRSModelSpec(
            model_id="buffalo_l_det",
            model_name="InsightFace SCRFD 10G",
            model_type="DETECTOR",
            version="1.0.0",
            runtime="ONNX_RUNTIME",
            input_size=(640, 640),
            classes=["face"],
            license="MIT",
            description="High-accuracy SCRFD 10G face detector with 5-point facial landmark regression.",
        ),
        "buffalo_l_emb": FRSModelSpec(
            model_id="buffalo_l_emb",
            model_name="InsightFace ArcFace R50",
            model_type="EMBEDDER",
            version="insightface-r50-v1",
            runtime="ONNX_RUNTIME",
            input_size=(112, 112),
            embedding_dim=512,
            similarity_metric="COSINE",
            classes=["face"],
            license="MIT",
            description="512-dimensional ArcFace deep feature representation with L2 unit normalization.",
        ),
    }

    @classmethod
    def get_model(cls, model_id: str) -> Optional[FRSModelSpec]:
        return cls._MODELS.get(model_id)

    @classmethod
    def get_default_detector(cls) -> FRSModelSpec:
        return cls._MODELS["buffalo_l_det"]

    @classmethod
    def get_default_embedder(cls) -> FRSModelSpec:
        return cls._MODELS["buffalo_l_emb"]

    @classmethod
    def list_models(cls) -> List[FRSModelSpec]:
        return list(cls._MODELS.values())
