"""
models_registry.py — Crowd AI Person Detection Model Registry.

Defines person-detection model specifications, input dimensions,
TensorRT engine profiles, and strict person-class-only filtering.
No facial recognition or identity classification.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class PersonDetectionModel(BaseModel):
    """Configuration specification for a person detection model."""
    model_id: str
    name: str
    version: str
    format: str = "TensorRT"  # TensorRT, ONNX, PyTorch
    engine_path: Optional[str] = None
    input_width: int = 640
    input_height: int = 640
    confidence_threshold: float = 0.45
    iou_threshold: float = 0.45
    allowed_classes: List[int] = Field(default_factory=lambda: [0])  # COCO Class 0: Person only
    class_names: Dict[int, str] = Field(default_factory=lambda: {0: "person"})
    max_detections_per_frame: int = 1500
    license: str = "AGPL-3.0 / Enterprise"
    description: str


# Pre-registered crowd person detection models
CROWD_MODEL_REGISTRY: Dict[str, PersonDetectionModel] = {
    "yolov8n-crowd": PersonDetectionModel(
        model_id="yolov8n-crowd",
        name="YOLOv8n Crowd Person Detector",
        version="8.2.0",
        format="TensorRT",
        engine_path="models/yolov8n_crowd_fp16.engine",
        input_width=640,
        input_height=640,
        confidence_threshold=0.45,
        iou_threshold=0.45,
        allowed_classes=[0],
        class_names={0: "person"},
        max_detections_per_frame=600,
        license="AGPL-3.0 / Enterprise",
        description="Lightweight person detector optimized for standard flow and queue sectors.",
    ),
    "yolov8x-crowd": PersonDetectionModel(
        model_id="yolov8x-crowd",
        name="YOLOv8x High-Density Crowd Person Detector",
        version="8.2.0",
        format="TensorRT",
        engine_path="models/yolov8x_crowd_fp16.engine",
        input_width=1280,
        input_height=1280,
        confidence_threshold=0.35,
        iou_threshold=0.50,
        allowed_classes=[0],
        class_names={0: "person"},
        max_detections_per_frame=2500,
        license="AGPL-3.0 / Enterprise",
        description="High-resolution heavy model for dense sanctum clusters and bottlenecks.",
    ),
}


class ModelRegistryService:
    """Manages model selection and class verification."""

    @staticmethod
    def get_model(model_id: str) -> Optional[PersonDetectionModel]:
        return CROWD_MODEL_REGISTRY.get(model_id.lower())

    @classmethod
    def get_default_model(cls) -> PersonDetectionModel:
        return CROWD_MODEL_REGISTRY["yolov8n-crowd"]

    @staticmethod
    def get_model_for_profile(profile_id: str) -> PersonDetectionModel:
        """Resolves optimal model for a given AI profile."""
        pid = profile_id.upper()
        if "HIGH_DENSITY" in pid:
            return CROWD_MODEL_REGISTRY["yolov8x-crowd"]
        return CROWD_MODEL_REGISTRY["yolov8n-crowd"]

    @staticmethod
    def list_models() -> List[PersonDetectionModel]:
        return list(CROWD_MODEL_REGISTRY.values())

    @staticmethod
    def is_person_class(class_id: int) -> bool:
        """Strict person-class gate: Only Class 0 is permitted."""
        return class_id == 0
