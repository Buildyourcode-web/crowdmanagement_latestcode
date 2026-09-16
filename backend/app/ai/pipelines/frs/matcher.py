"""
matcher.py — Gallery Search & Candidate Matching Engine.

Performs:
- Search against active enrolled reference profiles only.
- Cosine similarity calculation.
- Top-K candidate ranking and margin evaluation.
- Application of central match thresholds.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import numpy as np

from app.ai.pipelines.frs.embedding import batch_cosine_similarity, cosine_similarity


@dataclass
class CandidateMatch:
    reference_id: str
    reference_code: str
    display_name: str
    similarity_score: float  # Percentage (e.g. 88.4%)
    cosine_similarity: float  # Raw cosine similarity (0.0 - 1.0)
    rank: int  # 1-indexed
    model_version: str
    is_match: bool
    margin: float = 0.0  # Difference to runner-up candidate
    category: str = "Authorized Watchlist"
    reference_image_path: str = ""


class CandidateMatcher:
    """Biometric gallery index and similarity searcher."""

    def __init__(self, match_threshold: float = 0.65, top_k: int = 3):
        self.match_threshold = match_threshold
        self.top_k = top_k
        self._gallery_matrix: Optional[np.ndarray] = None
        self._gallery_meta: List[Dict[str, Any]] = []

    def load_gallery(self, profiles: List[Dict[str, Any]]) -> int:
        """Loads active reference profiles into memory."""
        active_profiles = [p for p in profiles if p.get("active", True) and p.get("embedding") is not None]
        vectors = []
        meta = []

        for p in active_profiles:
            emb = np.asarray(p["embedding"], dtype=np.float32).flatten()
            if emb.shape[0] == 512 and np.linalg.norm(emb) > 0:
                vectors.append(emb / np.linalg.norm(emb))
                meta.append(p)

        if vectors:
            self._gallery_matrix = np.vstack(vectors)
            self._gallery_meta = meta
        else:
            self._gallery_matrix = None
            self._gallery_meta = []

        return len(self._gallery_meta)

    @property
    def gallery_size(self) -> int:
        return len(self._gallery_meta)

    def search(
        self,
        query_embedding: np.ndarray,
        threshold: Optional[float] = None,
        top_k: Optional[int] = None,
    ) -> List[CandidateMatch]:
        """Find candidate matches for a query embedding against the gallery."""
        thresh = threshold if threshold is not None else self.match_threshold
        k = top_k if top_k is not None else self.top_k

        if self._gallery_matrix is None or len(self._gallery_meta) == 0:
            return []

        q = np.asarray(query_embedding, dtype=np.float32).flatten()
        if q.shape[0] != 512 or np.linalg.norm(q) == 0:
            return []

        sims = batch_cosine_similarity(q, self._gallery_matrix)

        # Aggregate candidates
        results = []
        for idx, sim in enumerate(sims.tolist()):
            meta = self._gallery_meta[idx]
            results.append((sim, meta))

        # Sort descending by similarity
        results.sort(key=lambda x: x[0], reverse=True)

        # Apply threshold & top-k
        matched_candidates: List[CandidateMatch] = []
        for rank_idx, (sim, meta) in enumerate(results[:k]):
            if sim < thresh:
                break

            margin = 0.0
            if rank_idx == 0 and len(results) > 1:
                margin = round(float(sim - results[1][0]), 4)

            matched_candidates.append(
                CandidateMatch(
                    reference_id=meta.get("reference_id") or meta.get("id", ""),
                    reference_code=meta.get("reference_code") or meta.get("reference_id", ""),
                    display_name=meta.get("display_name", "Authorized Reference"),
                    similarity_score=round(float(sim * 100), 1),
                    cosine_similarity=round(float(sim), 4),
                    rank=rank_idx + 1,
                    model_version=meta.get("embedding_model_version", "insightface-r50"),
                    is_match=True,
                    margin=margin,
                    category=meta.get("category", "Authorized Watchlist"),
                    reference_image_path=meta.get("reference_image_path", ""),
                )
            )

        return matched_candidates
