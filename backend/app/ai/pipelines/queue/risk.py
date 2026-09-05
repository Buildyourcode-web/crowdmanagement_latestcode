"""
risk.py — Queue AI Deterministic Risk Assessment Engine.

Computes a deterministic multi-factor queue risk score (0-100) and categorical risk levels
(LOW, MEDIUM, HIGH, CRITICAL) using calibrated occupancy, waiting times, inflow/outflow balance,
and growth surges.
Zero LLM or probabilistic guesswork in real-time safety loops.
"""

from typing import Dict, List, Tuple
from pydantic import BaseModel, Field

from app.ai.pipelines.queue.analytics import QueueMetricsResult


class QueueRiskEvaluation(BaseModel):
    """Result of deterministic queue risk calculation."""

    risk_score: float = Field(..., ge=0.0, le=100.0)
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    sub_scores: Dict[str, float] = Field(default_factory=dict)
    contributing_factors: List[str] = Field(default_factory=list)


class QueueRiskEngine:
    """
    Deterministic Queue Risk Engine.
    Formula:
      Risk = min(100, 0.35*S_occupancy + 0.30*S_wait + 0.20*S_bottleneck + 0.15*S_growth)
    """

    def __init__(
        self,
        weight_occupancy: float = 0.35,
        weight_wait: float = 0.30,
        weight_bottleneck: float = 0.20,
        weight_growth: float = 0.15,
    ):
        self.w_occ = weight_occupancy
        self.w_wait = weight_wait
        self.w_bot = weight_bottleneck
        self.w_growth = weight_growth

    def evaluate(self, metrics: QueueMetricsResult) -> QueueRiskEvaluation:
        factors: List[str] = []

        # 1. Occupancy / Headcount Score (0 - 100)
        if metrics.occupancy_percentage is not None:
            s_occ = min(100.0, max(0.0, float(metrics.occupancy_percentage)))
            if s_occ >= 90.0:
                factors.append(f"Critical occupancy ({metrics.occupancy_percentage}%)")
            elif s_occ >= 75.0:
                factors.append(f"High occupancy ({metrics.occupancy_percentage}%)")
        else:
            # Fallback based on raw count relative to standard sector threshold (80 people)
            s_occ = min(100.0, max(0.0, (metrics.queue_count / 80.0) * 100.0))
            if metrics.queue_count >= 80:
                factors.append(f"Heavy headcount ({metrics.queue_count} persons)")

        # 2. Wait Time Score (0 - 100)
        # 900s (15 min) maps to 100.0
        avg_wait = metrics.average_wait_seconds or 0
        s_wait = min(100.0, max(0.0, (avg_wait / 900.0) * 100.0))
        if avg_wait >= 900:
            factors.append(f"Severe wait time ({avg_wait // 60}m {avg_wait % 60}s)")
        elif avg_wait >= 600:
            factors.append(f"Elevated wait time ({avg_wait // 60}m {avg_wait % 60}s)")

        # 3. Bottleneck / Flow Accumulation Score (0 - 100)
        # Accumulation rate > 25 persons/min maps to 100.0
        s_bot = 0.0
        if metrics.inflow is not None and metrics.outflow is not None:
            accumulation = metrics.inflow - metrics.outflow
            if accumulation > 0:
                s_bot = min(100.0, (accumulation / 25.0) * 100.0)
                if accumulation >= 15:
                    factors.append(f"Queue bottleneck (+{accumulation} persons/min inflow accumulation)")

        # 4. Growth Rate Surge Score (0 - 100)
        # Positive growth >= 20 persons/min maps to 100.0
        s_growth = 0.0
        if metrics.growth_per_minute is not None and metrics.growth_per_minute > 0:
            s_growth = min(100.0, (metrics.growth_per_minute / 20.0) * 100.0)
            if metrics.growth_per_minute >= 15:
                factors.append(f"Rapid queue surge (+{metrics.growth_per_minute} persons/min)")

        # Aggregate weighted score
        raw_score = (
            (self.w_occ * s_occ)
            + (self.w_wait * s_wait)
            + (self.w_bot * s_bot)
            + (self.w_growth * s_growth)
        )
        final_score = round(min(100.0, max(0.0, raw_score)), 1)

        # Classify Level
        if final_score < 40.0:
            level = "LOW"
            if not factors:
                factors.append("Normal queue flow and manageable wait times")
        elif final_score < 70.0:
            level = "MEDIUM"
        elif final_score < 85.0:
            level = "HIGH"
        else:
            level = "CRITICAL"

        return QueueRiskEvaluation(
            risk_score=final_score,
            risk_level=level,
            sub_scores={
                "occupancy": round(s_occ, 1),
                "wait_time": round(s_wait, 1),
                "bottleneck": round(s_bot, 1),
                "growth": round(s_growth, 1),
            },
            contributing_factors=factors,
        )
