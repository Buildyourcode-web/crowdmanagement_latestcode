"""
temporal.py — Temporal Evidence Aggregation across frames.

Aggregates recognition evidence over recent observations within a track to stabilize identity decisions.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Union

import numpy as np

try:
    from app.frs_engine.config import MATCH_THRESHOLD, TEMPORAL_WINDOW_SIZE
    from app.frs_engine.recognition.matcher import MatchResult
    from app.frs_engine.recognition.quality import DecisionState, QualityMetrics
    from app.frs_engine.tracking.tracker import TrackState
except ImportError:
    from app.config import MATCH_THRESHOLD, TEMPORAL_WINDOW_SIZE
    from app.recognition.matcher import MatchResult
    from app.recognition.quality import DecisionState, QualityMetrics
    from app.tracking.tracker import TrackState


class TemporalAggregator:
    """
    Aggregates multi-frame similarity evidence for tracked faces.
    """

    def __init__(
        self,
        window_size: int = TEMPORAL_WINDOW_SIZE,
        threshold: float = MATCH_THRESHOLD,
    ) -> None:
        self.window_size = window_size
        self.threshold = threshold

    def aggregate_track_evidence(
        self,
        track: TrackState,
        latest_match: MatchResult,
        quality: QualityMetrics,
    ) -> MatchResult:
        """
        Aggregate recent match observations and quality metrics for a track.
        Updates track state attributes and returns the stabilized MatchResult.
        """
        # Store recent quality and match results
        track.quality_history.append(quality)
        if len(track.quality_history) > self.window_size * 2:
            track.quality_history.pop(0)

        track.match_history.append(latest_match)
        if len(track.match_history) > self.window_size * 2:
            track.match_history.pop(0)

        # Consider valid recent observations
        recent_matches = track.match_history[-self.window_size:]
        recent_qualities = track.quality_history[-self.window_size:]

        # Filter out unusable quality frames from evidence calculation
        valid_pairs = [
            (m, q) for m, q in zip(recent_matches, recent_qualities) if q.is_usable
        ]

        if not valid_pairs:
            # If no recent usable frame, retain existing candidate if recently confirmed
            if track.candidate_id is not None and track.misses < self.window_size:
                return MatchResult(
                    person_id=track.candidate_id,
                    name=track.candidate_name,
                    similarity=track.candidate_similarity,
                    is_known=True,
                    threshold=self.threshold,
                    margin=0.0,
                    is_ambiguous=False,
                )
            return latest_match

        # Group scores by candidate identity
        identity_weights: Dict[Union[int, str], List[Tuple[str, float, float]]] = {}
        for match, q_metric in valid_pairs:
            if match.person_id is None:
                continue
            if match.person_id not in identity_weights:
                identity_weights[match.person_id] = []
            identity_weights[match.person_id].append(
                (match.name, match.similarity, q_metric.quality_score)
            )

        if not identity_weights:
            track.candidate_id = None
            track.candidate_name = "Unknown"
            track.candidate_similarity = latest_match.similarity
            track.decision_state = DecisionState.UNKNOWN
            return latest_match

        # Compute quality-weighted average score per candidate
        candidate_scores: List[Tuple[Union[int, str], str, float, int]] = []
        for pid, observations in identity_weights.items():
            name = observations[0][0]
            total_weight = sum(q_score for _, _, q_score in observations)
            if total_weight > 0:
                weighted_sim = sum(sim * q_score for _, sim, q_score in observations) / total_weight
            else:
                weighted_sim = sum(sim for _, sim, _ in observations) / len(observations)
            candidate_scores.append((pid, name, weighted_sim, len(observations)))

        candidate_scores.sort(key=lambda x: x[2], reverse=True)
        best_pid, best_name, best_sim, count = candidate_scores[0]

        margin = 0.0
        if len(candidate_scores) > 1:
            margin = best_sim - candidate_scores[1][2]

        is_known = (best_sim >= self.threshold) and (count >= 1)

        # Update track candidate state
        track.candidate_id = best_pid if is_known else None
        track.candidate_name = best_name if is_known else "Unknown"
        track.candidate_similarity = float(best_sim)

        return MatchResult(
            person_id=best_pid if is_known else None,
            name=best_name if is_known else "Unknown",
            similarity=float(best_sim),
            is_known=is_known,
            threshold=self.threshold,
            margin=float(margin),
            is_ambiguous=latest_match.is_ambiguous,
        )
