"""
risk.py — Deterministic Crowd Risk Engine.

Computes real-time crowd risk scores (0..100) and discrete risk levels
(LOW, MEDIUM, HIGH, CRITICAL) using deterministic safety rules.

Strict Invariants:
- Deterministic rule-based algorithm ONLY.
- NO Large Language Models (LLMs) used for real-time crowd safety scoring.
- Does NOT predict crowd crushes autonomously or make law-enforcement decisions.
"""

from typing import List, Tuple
from app.ai.pipelines.crowd.analytics import CrowdMetricsResult


class CrowdRiskEngine:
    """
    Deterministic safety calculation combining headcount density,
    flow momentum (inflow vs outflow), and sensor reliability.
    """

    @staticmethod
    def calculate_risk(
        metrics: CrowdMetricsResult,
        stream_health: str = "HEALTHY",
    ) -> Tuple[float, str, List[str]]:
        """
        Calculates normalized risk score (0.0 - 100.0) and categorical risk level.
        Returns (risk_score, risk_level, list_of_contributing_factors).
        """
        if not metrics.is_roi_configured:
            return (0.0, "LOW", ["ROI geometry not configured"])

        factors = []
        score = 10.0

        # 1. Density Contribution
        if metrics.density_level == "CRITICAL":
            score = 88.0
            factors.append(f"Density CRITICAL ({metrics.current_count} persons in ROI)")
        elif metrics.density_level == "HIGH":
            score = 72.0
            factors.append(f"Density HIGH ({metrics.current_count} persons in ROI)")
        elif metrics.density_level == "MODERATE":
            score = 42.0
            factors.append(f"Density MODERATE ({metrics.current_count} persons in ROI)")
        else:
            score = 15.0
            factors.append(f"Density LOW ({metrics.current_count} persons in ROI)")

        # 2. Flow Momentum Contribution (Inflow vs Outflow)
        if metrics.inflow_rate is not None and metrics.outflow_rate is not None:
            delta = metrics.inflow_rate - metrics.outflow_rate
            if delta > 30:
                surge_penalty = min(float(delta) * 0.2, 10.0)
                score += surge_penalty
                factors.append(f"Rapid crowd accumulation (+{delta}/min inflow surge)")
            elif delta < -20:
                relief_credit = min(abs(float(delta)) * 0.1, 5.0)
                score -= relief_credit
                factors.append(f"Effective crowd dispersal ({delta}/min net outflow)")

        # 3. Stream Health Reliability
        if stream_health == "DEGRADED":
            score += 5.0
            factors.append("Camera stream degraded (reduced framerate)")
        elif stream_health == "FAILED":
            score = max(score, 75.0)
            factors.append("Camera stream failed / offline")

        # 4. Final Clamping
        final_score = max(0.0, min(100.0, round(score, 1)))

        # 5. Categorical Level Mapping
        if final_score >= 85.0:
            level = "CRITICAL"
        elif final_score >= 65.0:
            level = "HIGH"
        elif final_score >= 35.0:
            level = "MEDIUM"
        else:
            level = "LOW"

        return (final_score, level, factors)
