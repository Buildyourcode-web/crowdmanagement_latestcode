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
from typing import List, Optional, Tuple, Union

import numpy as np

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

    # ── Gallery management ─────────────────────────────────────────────────────

    def load_gallery(
        self,
        embeddings: List[np.ndarray],
        ids: List[Union[int, str]],
        names: List[str],
    ) -> None:
        """Replace gallery from flat list inputs."""
        self.gallery.clear()
        self.gallery.load_from_flat_lists(embeddings, ids, names)
        print(f"[Matcher] Gallery loaded: {self.gallery.identity_count} identities ({self.gallery.total_embedding_count} embeddings) threshold={self.threshold}")

    def load_gallery_data(self, gallery_data: GalleryData) -> None:
        """Replace in-memory gallery directly from a GalleryData object."""
        self.gallery = gallery_data
        print(f"[Matcher] GalleryData loaded: {self.gallery.identity_count} identities ({self.gallery.total_embedding_count} embeddings) threshold={self.threshold}")

    def load_gallery_from_json(self, json_source: Union[str, Path]) -> int:
        """Load gallery directly from a JSON file or JSON string."""
        self.gallery.clear()
        count = self.gallery.load_from_json(json_source)
        print(f"[Matcher] Gallery loaded from JSON: {self.gallery.identity_count} identities ({self.gallery.total_embedding_count} embeddings)")
        return count

    def add_to_gallery(self, embedding: np.ndarray, person_id: Union[int, str], name: str) -> None:
        """Append a single enrollment to the live gallery."""
        self.gallery.add_embedding(person_id=person_id, name=name, embedding=embedding)

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

        matrix, pids, names = self.gallery.get_flat_matrix()
        if matrix.shape[0] == 0:
            return unknown

        # Calculate cosine similarity against all gallery embeddings
        sims = batch_cosine_similarity(query_embedding, matrix)

        # Aggregate similarity scores per identity
        identity_scores: Dict[Union[int, str], Tuple[str, float]] = {}
        for pid, name, sim in zip(pids, names, sims.tolist()):
            sim_val = float(sim)
            if pid not in identity_scores:
                identity_scores[pid] = (name, sim_val)
            else:
                curr_name, curr_best = identity_scores[pid]
                if sim_val > curr_best:
                    identity_scores[pid] = (name, sim_val)

        # Sort identity scores descending
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

