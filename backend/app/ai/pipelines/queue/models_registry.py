"""
models_registry.py — Queue AI Person Detection Model Registry.

Defines person-detection model specifications for Queue AI pipelines.
Strictly filters for Class 0 (person only).
No facial recognition, biometric classification, or identity generation.
"""

import os
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
        weights_path="models/yolov8s.pt",
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
        weights_path="models/yolov8n.pt",
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
    "yolo11x-queue": PersonDetectionModel(
        model_id="yolo11x-queue",
        name="YOLO11x Queue Person Detector",
        version="11.0.0",
        format="TensorRT / ONNX / PyTorch",
        engine_path=os.getenv("YOLO_ENGINE_PATH", "models/yolo11x_queue.engine"),
        weights_path=os.getenv("YOLO_MODEL_PATH", "models/yolo11x.pt"),
        input_width=int(os.getenv("YOLO_INPUT_WIDTH", "1280")),
        input_height=int(os.getenv("YOLO_INPUT_HEIGHT", "1280")),
        confidence_threshold=float(os.getenv("YOLO_QUEUE_CONFIDENCE_THRESHOLD", "0.40")),
        iou_threshold=float(os.getenv("YOLO_IOU_THRESHOLD", "0.50")),
        allowed_classes=[0],
        class_names={0: "person"},
        max_detections_per_frame=1000,
        license="AGPL-3.0 / Enterprise",
        description="YOLO11x high-precision person detector for queue line barricades, channels, and dwell tracking.",
    ),
}

QUEUE_MODEL_ALIASES: Dict[str, str] = {
    "yolo11x": "yolo11x-queue",
    "yolo11x_queue": "yolo11x-queue",
    "yolo11x-queue": "yolo11x-queue",
    "yolov8s": "yolov8s-queue",
    "yolov8n": "yolov8n-queue",
}


class QueueModelRegistryService:
    """Provides lookup and validation for Queue AI detection models."""

    @classmethod
    def get_model(cls, model_id: str) -> Optional[PersonDetectionModel]:
        key = model_id.lower().strip()
        canonical_id = QUEUE_MODEL_ALIASES.get(key, key)
        return QUEUE_MODEL_REGISTRY.get(canonical_id)

    @classmethod
    def get_default_model(cls) -> PersonDetectionModel:
        return QUEUE_MODEL_REGISTRY["yolov8s-queue"]

    @classmethod
    def get_model_for_profile(cls, profile_id: str) -> PersonDetectionModel:
        pid = profile_id.upper()
        if "YOLO11X" in pid:
            return QUEUE_MODEL_REGISTRY["yolo11x-queue"]
        if "HIGH" in profile_id or "FAST" in profile_id:
            return QUEUE_MODEL_REGISTRY.get("yolov8n-queue", cls.get_default_model())
        return cls.get_default_model()

    @classmethod
    def is_person_class(cls, class_id: int) -> bool:
        """Enforces person-only class filtering (Class 0). Rejects faces, biometrics, etc."""
        return class_id == 0
