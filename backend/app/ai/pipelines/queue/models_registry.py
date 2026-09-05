"""
models_registry.py — Queue AI Person Detection Model Registry.

Defines person-detection model specifications for Queue AI pipelines.
Strictly filters for Class 0 (person only).
No facial recognition, biometric classification, or identity generation.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from app.ai.pipelines.crowd.models_registry import PersonDetectionModel


# Pre-registered Queue AI person detection models
QUEUE_MODEL_REGISTRY: Dict[str, PersonDetectionModel] = {
    "yolov8s-queue": PersonDetectionModel(
        model_id="yolov8s-queue",
        name="YOLOv8s Queue Person Detector",
        version="8.2.0",
        format="TensorRT",
        engine_path="models/yolov8s_queue_fp16.engine",
        input_width=640,
        input_height=640,
        confidence_threshold=0.50,
        iou_threshold=0.45,
        allowed_classes=[0],
        class_names={0: "person"},
        max_detections_per_frame=400,
        license="AGPL-3.0 / Enterprise",
        description="Standard person detector optimized for queue line barricades and pedestrian channels.",
    ),
    "yolov8n-queue": PersonDetectionModel(
        model_id="yolov8n-queue",
        name="YOLOv8n Queue Person Detector",
        version="8.2.0",
        format="TensorRT",
        engine_path="models/yolov8n_queue_fp16.engine",
        input_width=640,
        input_height=640,
        confidence_threshold=0.45,
        iou_threshold=0.45,
        allowed_classes=[0],
        class_names={0: "person"},
        max_detections_per_frame=300,
        license="AGPL-3.0 / Enterprise",
        description="Lightweight person detector for high-frame-rate entry/exit line counting.",
    ),
}


class QueueModelRegistryService:
    """Provides lookup and validation for Queue AI detection models."""

    @classmethod
    def get_model(cls, model_id: str) -> Optional[PersonDetectionModel]:
        return QUEUE_MODEL_REGISTRY.get(model_id)

    @classmethod
    def get_default_model(cls) -> PersonDetectionModel:
        return QUEUE_MODEL_REGISTRY["yolov8s-queue"]

    @classmethod
    def get_model_for_profile(cls, profile_id: str) -> PersonDetectionModel:
        if "HIGH" in profile_id or "FAST" in profile_id:
            return QUEUE_MODEL_REGISTRY.get("yolov8n-queue", cls.get_default_model())
        return cls.get_default_model()

    @classmethod
    def is_person_class(cls, class_id: int) -> bool:
        """Enforces person-only class filtering (Class 0). Rejects faces, biometrics, etc."""
        return class_id == 0
