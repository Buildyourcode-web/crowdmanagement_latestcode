"""
embedding.py — Embedding utilities for R0.

Responsibilities:
    - normalize_embedding()
    - cosine_similarity()
    - embedding validation

These are pure math functions — no model loading, no database access.
Later R1/R2/R3 experiments may add pose-conditioned embeddings alongside
the global embedding produced here.
"""

from __future__ import annotations

import numpy as np
from typing import Optional


EXPECTED_DIM = 512  # buffalo_l embedding dimension


def normalize_embedding(embedding: np.ndarray) -> Optional[np.ndarray]:
    """
    L2-normalize a face embedding.

    Returns:
        Normalized float32 array, or None if the vector is zero.
    """
    arr = np.array(embedding, dtype=np.float32).flatten()
    norm = np.linalg.norm(arr)
    if norm == 0.0:
        return None
    return arr / norm


def cosine_similarity(emb_a: np.ndarray, emb_b: np.ndarray) -> float:
    """
    Cosine similarity between two normalized embeddings.

    Both embeddings are expected to be already L2-normalized.
    If not normalized, this function normalizes them before computing.

    Returns:
        float in [-1, 1].  1.0 = identical direction, -1.0 = opposite.
    """
    a = normalize_embedding(emb_a)
    b = normalize_embedding(emb_b)
    if a is None or b is None:
        return 0.0
    return float(np.dot(a, b))


def batch_cosine_similarity(query: np.ndarray, gallery: np.ndarray) -> np.ndarray:
    """
    Compute cosine similarity between one query embedding and a gallery matrix.

    Args:
        query   : shape (D,)     — single normalized query embedding.
        gallery : shape (N, D)   — N normalized gallery embeddings.

    Returns:
        shape (N,) float32 similarity scores.

    This is the core operation used by the matcher for R0:

        best_idx = argmax(batch_cosine_similarity(query, gallery))
    """
    q = normalize_embedding(query)
    if q is None or gallery.shape[0] == 0:
        return np.zeros(gallery.shape[0], dtype=np.float32)
    return gallery.dot(q).astype(np.float32)


def validate_embedding(embedding: np.ndarray) -> bool:
    """
    Check that an embedding has the correct shape and is non-degenerate.
    """
    if embedding is None:
        return False
    arr = np.array(embedding, dtype=np.float32).flatten()
    if arr.shape[0] != EXPECTED_DIM:
        return False
    if np.isnan(arr).any() or np.isinf(arr).any():
        return False
    if np.linalg.norm(arr) == 0:
        return False
    return True
