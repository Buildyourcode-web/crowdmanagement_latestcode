"""
embedding.py — 512-D ArcFace Face Embedding Engine.

Extracts normalized 512-dimensional biometric feature embeddings
and calculates cosine similarity.
"""

from typing import Callable, List, Optional

import numpy as np
from loguru import logger


def normalize_l2(vector: np.ndarray) -> np.ndarray:
    """L2 unit normalization."""
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return vector / norm


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Cosine similarity between two 1D vectors."""
    if vec1 is None or vec2 is None:
        return 0.0
    v1 = np.asarray(vec1, dtype=np.float32).flatten()
    v2 = np.asarray(vec2, dtype=np.float32).flatten()
    if v1.shape != v2.shape or v1.size == 0:
        return 0.0
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


def batch_cosine_similarity(query: np.ndarray, gallery: np.ndarray) -> np.ndarray:
    """Batch cosine similarity of query (512,) against gallery (N, 512)."""
    q = np.asarray(query, dtype=np.float32).flatten()
    g = np.asarray(gallery, dtype=np.float32)
    if g.ndim == 1:
        g = g.reshape(1, -1)
    q_norm = np.linalg.norm(q)
    g_norms = np.linalg.norm(g, axis=1)
    valid = (q_norm > 0) & (g_norms > 0)
    sims = np.zeros(g.shape[0], dtype=np.float32)
    if np.any(valid) and q_norm > 0:
        sims[valid] = np.dot(g[valid], q) / (g_norms[valid] * q_norm)
    return sims


class FaceEmbeddingEngine:
    """ArcFace 512-D embedding generator with custom injection support."""

    def __init__(
        self,
        embedding_dim: int = 512,
        custom_embedder: Optional[Callable[[np.ndarray], np.ndarray]] = None,
    ):
        self.embedding_dim = embedding_dim
        self._custom_embedder = custom_embedder
        self._app = None

        if self._custom_embedder is None:
            self._init_insightface()

    def _init_insightface(self):
        try:
            from insightface.app import FaceAnalysis
            app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
            app.prepare(ctx_id=-1, det_size=(640, 640))
            self._app = app
            logger.info("FaceEmbeddingEngine: InsightFace model loaded.")
        except Exception as e:
            logger.warning(f"FaceEmbeddingEngine: InsightFace unavailable ({e}).")
            self._app = None

    def compute_embedding(self, face_crop: np.ndarray) -> Optional[np.ndarray]:
        """Compute L2-normalized 512-D identity embedding."""
        if face_crop is None or face_crop.size == 0:
            return None

        if self._custom_embedder is not None:
            emb = self._custom_embedder(face_crop)
            if emb is not None:
                emb = normalize_l2(np.asarray(emb, dtype=np.float32).flatten())
                if emb.shape[0] == self.embedding_dim:
                    return emb
            return None

        if self._app is None:
            return None

        try:
            faces = self._app.get(face_crop)
            if faces and hasattr(faces[0], "normed_embedding"):
                emb = faces[0].normed_embedding
                return normalize_l2(np.asarray(emb, dtype=np.float32))
            return None
        except Exception as e:
            logger.error(f"FaceEmbeddingEngine: error computing embedding: {e}")
            return None
