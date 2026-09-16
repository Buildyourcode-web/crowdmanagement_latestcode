"""
matcher.py — Identity matching for R0.

Responsibilities:
    - Load the gallery of known embeddings from the database.
    - For a live query embedding, find the best matching identity.
    - Apply threshold to decide Known / Unknown.

Design for future experiments:
    R1 (Pose-TTA) will extend this by building a pose-conditioned gallery
    at enrollment time and selecting the best pose-match at query time.
    R3 (FSPFM) will transform the query embedding before calling find_best_match().
    All those changes happen HERE or in subclasses — not in the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import json
from pathlib import Path

import numpy as np
from loguru import logger

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logger.info("[Matcher] FAISS not detected in environment; running with vectorized NumPy engine.")

try:
    from app.frs_engine.recognition.embedding import batch_cosine_similarity, validate_embedding
    from app.frs_engine.recognition.gallery import GalleryData
    from app.frs_engine.config import MATCH_THRESHOLD, MATCHING_STRATEGY, AMBIGUITY_MARGIN
except ImportError:
    from app.recognition.embedding import batch_cosine_similarity, validate_embedding
    from app.recognition.gallery import GalleryData
    from app.config import MATCH_THRESHOLD, MATCHING_STRATEGY, AMBIGUITY_MARGIN


@dataclass
class MatchResult:
    """
    Result of one matching attempt.

    Attributes:
        person_id   : DB or string id of matched person, or None if Unknown.
        name        : Display name, or "Unknown".
        similarity  : Best cosine similarity score found.
        is_known    : True if similarity >= threshold and unambiguous.
        threshold   : The threshold used for this decision.
        margin      : Difference between top-1 and top-2 candidate similarity scores.
        is_ambiguous: True if margin < AMBIGUITY_MARGIN when similarity >= threshold.
    """
    person_id: Optional[Union[int, str]]
    name: str
    similarity: float
    is_known: bool
    threshold: float
    margin: float = 0.0
    is_ambiguous: bool = False


class IdentityMatcher:
    """
    Compares a live query embedding against the stored identity gallery.
    Supports multi-embedding galleries and configurable matching strategies.
    """

    def __init__(
        self,
        threshold: float = MATCH_THRESHOLD,
        strategy: str = MATCHING_STRATEGY,
        ambiguity_margin: float = AMBIGUITY_MARGIN,
    ) -> None:
        self.threshold = threshold
        self.strategy = strategy
        self.ambiguity_margin = ambiguity_margin
        self.gallery = GalleryData()
        
        # FAISS components
        self.use_faiss = FAISS_AVAILABLE
        self._faiss_index = None
        self._id_to_meta: Dict[int, Tuple[Union[int, str], str]] = {}
        self._next_internal_id: int = 0

    # ── FAISS Index Maintenance ───────────────────────────────────────────────

    def _rebuild_faiss_index(self) -> None:
        """Rebuild in-memory FAISS IndexIDMap2 from current gallery data."""
        if not self.use_faiss:
            return

        try:
            matrix, pids, names = self.gallery.get_flat_matrix()
            if matrix.shape[0] == 0:
                self._faiss_index = None
                self._id_to_meta = {}
                self._next_internal_id = 0
                return

            dim = matrix.shape[1]
            base_index = faiss.IndexFlatIP(dim)
            self._faiss_index = faiss.IndexIDMap2(base_index)
            self._id_to_meta = {}

            internal_ids = np.arange(len(pids), dtype=np.int64)
            for i, (pid, name) in enumerate(zip(pids, names)):
                self._id_to_meta[int(internal_ids[i])] = (pid, name)

            mat_f32 = np.ascontiguousarray(matrix, dtype=np.float32)
            self._faiss_index.add_with_ids(mat_f32, internal_ids)
            self._next_internal_id = len(pids)
            logger.info(f"[FAISS] Built vector index with {self._faiss_index.ntotal} embeddings.")
        except Exception as ex:
            logger.warning(f"[FAISS] Failed to build vector index: {ex}. Using NumPy fallback.")
            self._faiss_index = None

    def save_faiss_index(self, index_path: Union[str, Path]) -> bool:
        """Save FAISS index and metadata map to disk."""
        if not self.use_faiss or self._faiss_index is None:
            return False
        try:
            p = Path(index_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self._faiss_index, str(p))
            
            meta_file = p.with_suffix(".meta.json")
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump({str(k): list(v) for k, v in self._id_to_meta.items()}, f)
            logger.info(f"[FAISS] Successfully saved index to {p}")
            return True
        except Exception as ex:
            logger.error(f"[FAISS] Save index error: {ex}")
            return False

    def load_faiss_index(self, index_path: Union[str, Path]) -> bool:
        """Load pre-compiled FAISS index and metadata from disk."""
        if not self.use_faiss:
            return False
        try:
            p = Path(index_path)
            if not p.exists():
                return False
            self._faiss_index = faiss.read_index(str(p))
            meta_file = p.with_suffix(".meta.json")
            if meta_file.exists():
                with open(meta_file, "r", encoding="utf-8") as f:
                    raw_meta = json.load(f)
                    self._id_to_meta = {int(k): (v[0], v[1]) for k, v in raw_meta.items()}
                self._next_internal_id = max(self._id_to_meta.keys()) + 1 if self._id_to_meta else 0
            logger.info(f"[FAISS] Successfully loaded index with {self._faiss_index.ntotal} vectors from {p}")
            return True
        except Exception as ex:
            logger.warning(f"[FAISS] Failed to load index from {index_path}: {ex}")
            return False

    # ── Gallery management ─────────────────────────────────────────────────────

    def load_gallery(
        self,
        embeddings: List[np.ndarray],
        ids: List[Union[int, str]],
        names: List[str],
    ) -> None:
        """Replace gallery from flat list inputs and build FAISS index."""
        self.gallery.clear()
        self.gallery.load_from_flat_lists(embeddings, ids, names)
        self._rebuild_faiss_index()
        logger.info(f"[Matcher] Gallery loaded: {self.gallery.identity_count} identities ({self.gallery.total_embedding_count} embeddings) threshold={self.threshold}")

    def load_gallery_data(self, gallery_data: GalleryData) -> None:
        """Replace in-memory gallery directly from a GalleryData object."""
        self.gallery = gallery_data
        self._rebuild_faiss_index()
        logger.info(f"[Matcher] GalleryData loaded: {self.gallery.identity_count} identities ({self.gallery.total_embedding_count} embeddings) threshold={self.threshold}")

    def load_gallery_from_json(self, json_source: Union[str, Path]) -> int:
        """Load gallery directly from a JSON file or JSON string."""
        self.gallery.clear()
        count = self.gallery.load_from_json(json_source)
        self._rebuild_faiss_index()
        logger.info(f"[Matcher] Gallery loaded from JSON: {self.gallery.identity_count} identities ({self.gallery.total_embedding_count} embeddings)")
        return count

    def add_to_gallery(self, embedding: np.ndarray, person_id: Union[int, str], name: str) -> None:
        """Append a single enrollment to the live gallery and update FAISS index dynamically."""
        self.gallery.add_embedding(person_id=person_id, name=name, embedding=embedding)
        
        # Hot-reload into live FAISS index with zero server restart
        if self.use_faiss and self._faiss_index is not None:
            try:
                emb_f32 = np.ascontiguousarray(embedding.reshape(1, -1), dtype=np.float32)
                int_id = self._next_internal_id
                self._faiss_index.add_with_ids(emb_f32, np.array([int_id], dtype=np.int64))
                self._id_to_meta[int_id] = (person_id, name)
                self._next_internal_id += 1
            except Exception as ex:
                logger.warning(f"[FAISS] Live dynamic vector add failed: {ex}")

    @property
    def gallery_size(self) -> int:
        return self.gallery.total_embedding_count

    @property
    def identity_count(self) -> int:
        return self.gallery.identity_count

    # ── Matching ───────────────────────────────────────────────────────────────

    def find_best_match(self, query_embedding: np.ndarray) -> MatchResult:
        """
        Find the best matching identity for a query embedding across all gallery representations.
        Uses FAISS when available, otherwise falls back to vectorized NumPy.
        """
        unknown = MatchResult(
            person_id=None,
            name="Unknown",
            similarity=0.0,
            is_known=False,
            threshold=self.threshold,
            margin=0.0,
            is_ambiguous=False,
        )

        if not validate_embedding(query_embedding):
            return unknown

        # ── 1. FAISS Search Path (Sub-millisecond for 10k+) ──────────────────────
        if self.use_faiss and self._faiss_index is not None and self.gallery_size > 0:
            try:
                query_vec = np.ascontiguousarray(query_embedding.reshape(1, -1), dtype=np.float32)
                k = min(10, self.gallery_size)
                scores, indices = self._faiss_index.search(query_vec, k)
                
                scores_row = scores[0]
                indices_row = indices[0]

                identity_scores: Dict[Union[int, str], Tuple[str, float]] = {}
                for sim_val, idx in zip(scores_row, indices_row):
                    if idx == -1:
                        continue
                    if idx in self._id_to_meta:
                        pid, name = self._id_to_meta[idx]
                        sim = float(sim_val)
                        if pid not in identity_scores or sim > identity_scores[pid][1]:
                            identity_scores[pid] = (name, sim)

                if identity_scores:
                    sorted_scores = sorted(
                        [(pid, name, sim) for pid, (name, sim) in identity_scores.items()],
                        key=lambda x: x[2],
                        reverse=True,
                    )
                    best_pid, best_name, best_sim = sorted_scores[0]
                    margin = 0.0
                    if len(sorted_scores) > 1:
                        margin = best_sim - sorted_scores[1][2]

                    is_ambiguous = (best_sim >= self.threshold) and (margin < self.ambiguity_margin) and (len(sorted_scores) > 1)

                    if best_sim >= self.threshold and not is_ambiguous:
                        return MatchResult(
                            person_id=best_pid,
                            name=best_name,
                            similarity=best_sim,
                            is_known=True,
                            threshold=self.threshold,
                            margin=margin,
                            is_ambiguous=False,
                        )

                    unknown.person_id = best_pid if best_sim >= self.threshold else None
                    unknown.name = best_name if best_sim >= self.threshold else "Unknown"
                    unknown.similarity = best_sim
                    unknown.margin = margin
                    unknown.is_ambiguous = is_ambiguous
                    return unknown
            except Exception as ex:
                logger.warning(f"[FAISS] Search exception: {ex}. Falling back to NumPy scan.")

        # ── 2. Vectorized NumPy Fallback Path ─────────────────────────────────────
        matrix, pids, names = self.gallery.get_flat_matrix()
        if matrix.shape[0] == 0:
            return unknown

        sims = batch_cosine_similarity(query_embedding, matrix)

        identity_scores: Dict[Union[int, str], Tuple[str, float]] = {}
        for pid, name, sim in zip(pids, names, sims.tolist()):
            sim_val = float(sim)
            if pid not in identity_scores or sim_val > identity_scores[pid][1]:
                identity_scores[pid] = (name, sim_val)

        sorted_scores = sorted(
            [(pid, name, sim) for pid, (name, sim) in identity_scores.items()],
            key=lambda x: x[2],
            reverse=True,
        )

        if not sorted_scores:
            return unknown

        best_pid, best_name, best_sim = sorted_scores[0]
        margin = 0.0
        if len(sorted_scores) > 1:
            margin = best_sim - sorted_scores[1][2]

        is_ambiguous = (best_sim >= self.threshold) and (margin < self.ambiguity_margin) and (len(sorted_scores) > 1)

        if best_sim >= self.threshold and not is_ambiguous:
            return MatchResult(
                person_id=best_pid,
                name=best_name,
                similarity=best_sim,
                is_known=True,
                threshold=self.threshold,
                margin=margin,
                is_ambiguous=False,
            )

        unknown.person_id = best_pid if best_sim >= self.threshold else None
        unknown.name = best_name if best_sim >= self.threshold else "Unknown"
        unknown.similarity = best_sim
        unknown.margin = margin
        unknown.is_ambiguous = is_ambiguous
        return unknown

    def all_similarities(self, query_embedding: np.ndarray) -> List[Tuple[Union[int, str], str, float]]:
        """
        Return similarity to every enrolled identity — sorted descending by max score.
        """
        if not validate_embedding(query_embedding):
            return []
        matrix, pids, names = self.gallery.get_flat_matrix()
        if matrix.shape[0] == 0:
            return []

        sims = batch_cosine_similarity(query_embedding, matrix)
        identity_scores: Dict[Union[int, str], Tuple[str, float]] = {}
        for pid, name, sim in zip(pids, names, sims.tolist()):
            sim_val = float(sim)
            if pid not in identity_scores or sim_val > identity_scores[pid][1]:
                identity_scores[pid] = (name, sim_val)

        combined = [(pid, name, sim) for pid, (name, sim) in identity_scores.items()]
        combined.sort(key=lambda x: x[2], reverse=True)
        return combined

