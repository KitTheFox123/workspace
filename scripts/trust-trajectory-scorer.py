#!/usr/bin/env python3
"""trust-trajectory-scorer.py — Reputation as derivative, not stock.

Per santaclawd: "reputation should be a derivative, not a stock.
where you are going matters more than where you have been."

Cabral (2005): Reputation as Bayesian belief updating.
Key insight: an improving 0.6 outranks a stable 0.9 because
trajectory predicts future behavior better than current state.
"""

import json
from dataclasses import dataclass
from typing import List


@dataclass
class ReceiptWindow:
    """A time window of receipt data."""
    period_label: str  # e.g. "week_1", "week_4"
    days_ago: int
    receipt_count: int
    chain_pct: float  # % chain-grade evidence
    refusal_count: int
    dispute_count: int
    witness_diversity: float  # 0-1


def compute_trajectory(windows: List[ReceiptWindow]) -> dict:
    """Compute trust trajectory from time-windowed receipt data.
    
    Returns derivative (rate of change) not stock (current value).
    """
    if len(windows) < 2:
        return {"error": "need ≥2 windows for trajectory"}

    # Sort oldest first
    windows = sorted(windows, key=lambda w: -w.days_ago)

    # Compute per-window quality score
    scores = []
    for w in windows:
        if w.receipt_count == 0:
            scores.append(0.0)
            continue
        
        quality = (
            0.30 * min(w.receipt_count / 10, 1.0)  # activity (cap at 10)
            + 0.25 * w.chain_pct  # evidence quality
            + 0.20 * w.witness_diversity  # independence
            + 0.15 * min(w.refusal_count / max(w.receipt_count, 1) * 5, 1.0)  # healthy refusal rate (~20%)
            + 0.10 * max(0, 1 - w.dispute_count / max(w.receipt_count, 1) * 10)  # low dispute rate
        )
        scores.append(round(quality, 4))

    # Trajectory = weighted linear regression slope
    n = len(scores)
    x_mean = (n - 1) / 2
    y_mean = sum(scores) / n
    
    numerator = sum((i - x_mean) * (s - y_mean) for i, s in enumerate(scores))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    
    slope = numerator / denominator if denominator > 0 else 0
    current = scores[-1]
    
    # Classify trajectory
    if slope > 0.05:
        trajectory = "IMPROVING"
        emoji = "📈"
    elif slope < -0.05:
        trajectory = "DECLINING"
        emoji = "📉"
    else:
        trajectory = "STABLE"
        emoji = "➡️"

    # Composite: weight trajectory heavily for young agents
    age_days = windows[0].days_ago
    trajectory_weight = max(0.3, 0.7 - (age_days / 365) * 0.4)  # young = 0.7, old = 0.3
    stock_weight = 1 - trajectory_weight

    composite = stock_weight * current + trajectory_weight * (current + slope * 4)
    composite = max(0, min(1, composite))

    # Silence detection: was there a gap after improvement?
    silence_after_improvement = (
        slope > 0.03 and scores[-1] < scores[-2] * 0.5
    )

    return {
        "window_scores": [{"period": w.period_label, "score": s} for w, s in zip(windows, scores)],
        "current_score": round(current, 3),
        "slope": round(slope, 4),
        "trajectory": trajectory,
        "emoji": emoji,
        "composite": round(composite, 3),
        "trajectory_weight": round(trajectory_weight, 2),
        "silence_after_improvement": silence_after_improvement,
        "note": f"{'Silence after improvement = strong negative signal' if silence_after_improvement else 'Trajectory consistent'}",
    }


def demo():
    """Compare agents with different trajectories."""
    agents = {
        "improving_newcomer": [
            ReceiptWindow("week_1", 28, 3, 0.0, 0, 0, 0.2),
            ReceiptWindow("week_2", 21, 5, 0.2, 1, 0, 0.3),
            ReceiptWindow("week_3", 14, 8, 0.5, 2, 0, 0.5),
            ReceiptWindow("week_4", 7, 12, 0.7, 2, 0, 0.7),
        ],
        "stable_veteran": [
            ReceiptWindow("month_1", 120, 30, 0.8, 5, 1, 0.8),
            ReceiptWindow("month_2", 90, 28, 0.8, 6, 0, 0.8),
            ReceiptWindow("month_3", 60, 32, 0.8, 5, 1, 0.8),
            ReceiptWindow("month_4", 30, 30, 0.8, 6, 0, 0.8),
        ],
        "declining_veteran": [
            ReceiptWindow("month_1", 120, 30, 0.9, 6, 0, 0.9),
            ReceiptWindow("month_2", 90, 20, 0.7, 3, 1, 0.7),
            ReceiptWindow("month_3", 60, 10, 0.4, 1, 2, 0.5),
            ReceiptWindow("month_4", 30, 5, 0.2, 0, 1, 0.3),
        ],
        "yes_bot": [
            ReceiptWindow("week_1", 28, 50, 0.1, 0, 0, 0.1),
            ReceiptWindow("week_2", 21, 50, 0.1, 0, 0, 0.1),
            ReceiptWindow("week_3", 14, 50, 0.1, 0, 0, 0.1),
            ReceiptWindow("week_4", 7, 50, 0.1, 0, 0, 0.1),
        ],
    }

    print("=" * 65)
    print("Trust Trajectory Scorer — Derivative > Stock")
    print("Cabral (2005): reputation as belief updating")
    print("=" * 65)

    for name, windows in agents.items():
        result = compute_trajectory(windows)
        print(f"\n{'─' * 50}")
        print(f"Agent: {name}")
        print(f"  {result['emoji']} Trajectory: {result['trajectory']}")
        print(f"  Current score: {result['current_score']}")
        print(f"  Slope: {result['slope']}")
        print(f"  Composite: {result['composite']}")
        print(f"  Trajectory weight: {result['trajectory_weight']}")
        print(f"  {result['note']}")
        for ws in result['window_scores']:
            print(f"    {ws['period']}: {ws['score']}")

    print(f"\n{'=' * 65}")
    print("KEY: improving_newcomer (0.6→📈) > yes_bot (0.3→➡️)")
    print("Stock says yes_bot has more activity. Derivative says it's flat.")
    print("Declining veteran = high stock, negative derivative = sell signal.")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo()
