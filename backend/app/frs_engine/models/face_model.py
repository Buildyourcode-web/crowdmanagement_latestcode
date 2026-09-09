"""
face_model.py — Clean abstraction over InsightFace buffalo_l.

Design intent:
    This class isolates InsightFace from the rest of the pipeline.
    When we later swap buffalo_l for AdaFace, MagFace, or a custom
    research model (R1/R2/R3), we only change this file — not the
    pipeline, not the matcher, not the database.

R0 backbone: InsightFace buffalo_l (512-D embedding, CUDA or CPU).
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional

import insightface
from insightface.app import FaceAnalysis

try:
    from app.frs_engine.config import MODEL_NAME, DET_SIZE, USE_CUDA
except ImportError:
    from app.config import MODEL_NAME, DET_SIZE, USE_CUDA


@dataclass
class DetectedFace:
    """
    Represents one face detected in an image frame.

    Attributes:
        bbox        : [x1, y1, x2, y2] in pixel coordinates.
        embedding   : Normalized 512-D identity embedding (float32).
        det_score   : Detection confidence score (0–1).
        landmark    : 5-point landmarks if available, else None.
        kps         : Keypoints array from InsightFace (raw).
        pose        : [pitch, yaw, roll] in degrees from 1k3d68, or None.
    """
    bbox: np.ndarray            # shape (4,)
    embedding: np.ndarray       # shape (512,), already normalized
    det_score: float = 0.0
    landmark: Optional[np.ndarray] = None
    kps: Optional[np.ndarray] = None
    pose: Optional[np.ndarray] = None   # [pitch, yaw, roll] degrees
    # Reserved for future use by R2 (3DDFA-V3 geometry) / R5 (local parts)
    extra: dict = field(default_factory=dict)


class FaceModel:
    """
    Wrapper around InsightFace FaceAnalysis.

    Responsibilities:
        - Initialize the backbone once (heavy operation).
        - Expose detect_faces() → List[DetectedFace].
        - Provide get_embedding() for a pre-cropped face if needed.

    What this class does NOT do:
        - Database access
        - Matching / similarity
        - Any pose-aware logic (those go in R1+ experiments)
    """

    def __init__(self) -> None:
        import onnxruntime as ort
        avail = ort.get_available_providers()
        providers = []
        if "DmlExecutionProvider" in avail:
            providers.append("DmlExecutionProvider")
        if "CUDAExecutionProvider" in avail and USE_CUDA:
            providers.append("CUDAExecutionProvider")
        providers.append("CPUExecutionProvider")

        use_gpu = providers[0] != "CPUExecutionProvider"
        self._app = FaceAnalysis(
            name=MODEL_NAME,
            providers=providers,
        )
        self._app.prepare(ctx_id=0 if use_gpu else -1, det_size=(DET_SIZE, DET_SIZE), det_thresh=0.35)
        print(f"[FaceModel] Loaded: {MODEL_NAME}  Providers={providers}  det_size={DET_SIZE}  det_thresh=0.35")

    # ── Public API ─────────────────────────────────────────────────────────────

    def detect_faces(self, rgb_frame: np.ndarray) -> List[DetectedFace]:
        """
        Run face detection + embedding on an RGB image.

        Args:
            rgb_frame : HxWx3 uint8 RGB numpy array.

        Returns:
            List of DetectedFace objects, one per detected face.
            Empty list if no faces found.
        """
        raw_faces = self._app.get(rgb_frame)
        results: List[DetectedFace] = []

        for face in raw_faces:
            emb = self._normalize(face.normed_embedding)
            if emb is None:
                continue

            bbox = face.bbox.astype(int)  # [x1, y1, x2, y2]
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]

            # Filter tiny detections — allow distant faces down to 14px
            if w < 14 or h < 14:
                continue

            det_score = float(face.det_score) if hasattr(face, "det_score") else 0.9

            # --------------------------------------------------------
            # Pose angles: pitch (up/down), yaw (left/right), roll (tilt)
            # Provided by the 1k3d68 3D landmark model in buffalo_l.
            # InsightFace stores pose as [pitch, yaw, roll] in degrees.
            # --------------------------------------------------------
            pose = None
            if hasattr(face, "pose") and face.pose is not None:
                try:
                    p = np.asarray(face.pose, dtype=np.float32).flatten()
                    if len(p) >= 3:
                        pose = p  # [pitch, yaw, roll]
                except Exception:
                    pose = None

            results.append(
                DetectedFace(
                    bbox=bbox,
                    embedding=emb,
                    det_score=det_score,
                    landmark=face.landmark_2d_106 if hasattr(face, "landmark_2d_106") else None,
                    kps=face.kps if hasattr(face, "kps") else None,
                    pose=pose,
                )
            )

        return results

    def get_embedding(self, rgb_face_crop: np.ndarray) -> Optional[np.ndarray]:
        """
        Get embedding from a pre-cropped face patch (rarely needed at R0 level,
        but useful for future R2/R5 local-part experiments).

        Returns normalized 512-D embedding, or None if detection fails.
        """
        faces = self._app.get(rgb_face_crop)
        if not faces:
            return None
        return self._normalize(faces[0].normed_embedding)

    # ── Internal helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _normalize(embedding: np.ndarray) -> Optional[np.ndarray]:
        """L2-normalize an embedding vector. Returns None if zero-vector."""
        arr = np.array(embedding, dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm == 0:
            return None
        return arr / norm
