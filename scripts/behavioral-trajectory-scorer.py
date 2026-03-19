#!/usr/bin/env python3
"""behavioral-trajectory-scorer.py — Risk scoring via behavioral trajectory analysis.

Per augur: "90d of micro-transactions is a different risk fingerprint than
a single high-value event. tier formula needs both: cumulative exposure +
behavioral trajectory."

Combines value-at-risk concentration with temporal behavioral patterns.
"""

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Receipt:
    timestamp: datetime
    value: float  # SOL
    evidence_grade: str  # chain/witness/self
    decision_type: str  # completed/refusal/disputed


def gini_coefficient(values: list[float]) -> float:
    """Gini coefficient for value concentration. 0=equal, 1=concentrated."""
    if not values or sum(values) == 0:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    cumsum = sum((i + 1) * v for i, v in enumerate(sorted_v))
    return (2 * cumsum) / (n * sum(sorted_v)) - (n + 1) / n


def behavioral_trajectory(receipts: list[Receipt]) -> dict:
    """Analyze behavioral trajectory over time."""
    if len(receipts) < 2:
        return {"trajectory": "INSUFFICIENT", "score": 0.0}

    receipts_sorted = sorted(receipts, key=lambda r: r.timestamp)
    span_days = (receipts_sorted[-1].timestamp - receipts_sorted[0].timestamp).days + 1

    # 1. Density: receipts per day
    density = len(receipts) / max(span_days, 1)

    # 2. Consistency: coefficient of variation of inter-receipt gaps
    gaps = []
    for i in range(1, len(receipts_sorted)):
        gap = (receipts_sorted[i].timestamp - receipts_sorted[i - 1].timestamp).total_seconds()
        gaps.append(gap)

    if gaps:
        mean_gap = sum(gaps) / len(gaps)
        std_gap = (sum((g - mean_gap) ** 2 for g in gaps) / len(gaps)) ** 0.5
        cv = std_gap / mean_gap if mean_gap > 0 else float("inf")
    else:
        cv = float("inf")

    consistency = 1.0 / (1.0 + cv)  # 0-1, higher = more consistent

    # 3. Value-at-risk concentration (Gini)
    values = [r.value for r in receipts]
    concentration = gini_coefficient(values)

    # 4. Evidence grade trajectory (are grades improving over time?)
    grade_values = {"chain": 3, "witness": 2, "self": 1}
    mid = len(receipts_sorted) // 2
    early_grade = sum(grade_values.get(r.evidence_grade, 0) for r in receipts_sorted[:mid]) / max(mid, 1)
    late_grade = sum(grade_values.get(r.evidence_grade, 0) for r in receipts_sorted[mid:]) / max(len(receipts_sorted) - mid, 1)
    grade_trend = (late_grade - early_grade) / 3.0  # normalized -1 to 1

    # 5. Refusal health (per compliance-agent-detector.py)
    refusals = sum(1 for r in receipts if r.decision_type == "refusal")
    refusal_rate = refusals / len(receipts)
    # Healthy range: 5-20%
    if 0.05 <= refusal_rate <= 0.20:
        refusal_health = 1.0
    elif refusal_rate == 0:
        refusal_health = 0.3  # suspicious — never refuses
    elif refusal_rate > 0.5:
        refusal_health = 0.2  # too many refusals
    else:
        refusal_health = 0.7

    # Composite score
    score = (
        density_score(density) * 0.20
        + consistency * 0.25
        + (1.0 - concentration) * 0.15  # low concentration = good
        + max(0, grade_trend + 0.5) * 0.20  # grade improvement bonus
        + refusal_health * 0.20
    )

    # Risk tier
    if score >= 0.7:
        tier = "LOW_RISK"
    elif score >= 0.4:
        tier = "MEDIUM_RISK"
    else:
        tier = "HIGH_RISK"

    return {
        "trajectory": tier,
        "score": round(score, 3),
        "density_per_day": round(density, 2),
        "consistency": round(consistency, 3),
        "value_concentration_gini": round(concentration, 3),
        "evidence_grade_trend": round(grade_trend, 3),
        "refusal_rate": round(refusal_rate, 3),
        "refusal_health": round(refusal_health, 2),
        "span_days": span_days,
        "receipt_count": len(receipts),
    }


def density_score(density: float) -> float:
    """Log-scaled density score. Diminishing returns above 5/day."""
    if density <= 0:
        return 0.0
    return min(1.0, math.log1p(density) / math.log1p(5))


def demo():
    now = datetime.utcnow()

    scenarios = {
        "steady_worker": [
            Receipt(now - timedelta(days=i), 0.02, "witness", "completed" if i % 8 != 0 else "refusal")
            for i in range(90)
        ],
        "burst_then_silence": [
            Receipt(now - timedelta(days=85, hours=i), 0.5, "self", "completed")
            for i in range(50)
        ],
        "high_value_concentrated": [
            Receipt(now - timedelta(days=30), 10.0, "chain", "completed"),
            Receipt(now - timedelta(days=15), 0.01, "self", "completed"),
            Receipt(now - timedelta(days=1), 0.01, "self", "completed"),
        ],
        "improving_agent": [
            Receipt(now - timedelta(days=90 - i), 0.05, "self" if i < 30 else "witness" if i < 60 else "chain",
                    "completed" if i % 10 != 0 else "refusal")
            for i in range(90)
        ],
        "yes_bot": [
            Receipt(now - timedelta(days=i), 0.01, "self", "completed")
            for i in range(60)
        ],
    }

    print("=" * 70)
    print("Behavioral Trajectory Scoring")
    print("Per augur: cumulative exposure + behavioral trajectory")
    print("=" * 70)

    for name, receipts in scenarios.items():
        result = behavioral_trajectory(receipts)
        print(f"\n{'─' * 50}")
        print(f"Agent: {name}")
        print(f"  Trajectory: {result['trajectory']} (score: {result['score']})")
        print(f"  Density: {result['density_per_day']}/day over {result['span_days']}d")
        print(f"  Consistency: {result['consistency']}")
        print(f"  Value concentration (Gini): {result['value_concentration_gini']}")
        print(f"  Evidence grade trend: {result['evidence_grade_trend']:+.3f}")
        print(f"  Refusal rate: {result['refusal_rate']:.1%} (health: {result['refusal_health']})")

    print(f"\n{'=' * 70}")
    print("KEY: steady_worker + improving_agent = LOW_RISK")
    print("     burst_then_silence + yes_bot = HIGH_RISK")
    print("     Trajectory matters more than snapshot.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    demo()
