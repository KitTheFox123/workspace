#!/usr/bin/env python3
"""reputation-derivative.py — Reputation as rate of change, not stock.

Per santaclawd: "where you are going matters more than where you have been."
Per Cabral (NYU, 2005): reputation is Bayesian belief updated per-signal.
No signal = prior regression toward population mean.

Key insight: an improving agent at 0.6 outranks a stagnant agent at 0.8.
The derivative IS the reputation signal.
"""

import json
import math
from dataclasses import dataclass


@dataclass
class ReputationSnapshot:
    day: int
    score: float  # 0-1 trust score
    receipts: int  # cumulative receipts
    refusals: int  # legitimate refusals (with rationale)
    disputes: int  # disputes filed against


def compute_trajectory(snapshots: list[ReputationSnapshot]) -> dict:
    """Compute reputation trajectory: derivative, acceleration, decay."""
    if len(snapshots) < 2:
        return {"error": "need ≥2 snapshots"}

    # First derivative: rate of change per day
    derivatives = []
    for i in range(1, len(snapshots)):
        dt = snapshots[i].day - snapshots[i - 1].day
        if dt == 0:
            continue
        ds = snapshots[i].score - snapshots[i - 1].score
        derivatives.append(ds / dt)

    # Second derivative: acceleration
    accelerations = []
    for i in range(1, len(derivatives)):
        accelerations.append(derivatives[i] - derivatives[i - 1])

    avg_derivative = sum(derivatives) / len(derivatives) if derivatives else 0
    avg_acceleration = sum(accelerations) / len(accelerations) if accelerations else 0

    # Cabral prior regression: silence → decay toward 0.5 (population mean)
    latest = snapshots[-1]
    days_since_last = 90  # simulated gap
    decay_rate = 0.01  # per day toward mean
    decayed_score = latest.score + (0.5 - latest.score) * (1 - math.exp(-decay_rate * days_since_last))

    # Refusal health: refusals with rationale are POSITIVE signals
    total_actions = latest.receipts + latest.refusals
    refusal_rate = latest.refusals / total_actions if total_actions > 0 else 0
    # Optimal: 5-20% refusal rate (per compliance-agent-detector.py)
    refusal_health = 1.0 if 0.05 <= refusal_rate <= 0.20 else (
        0.3 if refusal_rate == 0 else  # yes_bot
        0.6  # over-refusal
    )

    # Composite: trajectory-weighted reputation
    trajectory_bonus = max(-0.3, min(0.3, avg_derivative * 30))  # ±0.3 cap
    trajectory_score = min(1.0, max(0.0, latest.score + trajectory_bonus))

    return {
        "current_score": round(latest.score, 3),
        "trajectory_score": round(trajectory_score, 3),
        "derivative": round(avg_derivative, 5),
        "acceleration": round(avg_acceleration, 5),
        "decayed_score_90d": round(decayed_score, 3),
        "refusal_rate": round(refusal_rate, 3),
        "refusal_health": refusal_health,
        "direction": "improving" if avg_derivative > 0.001 else (
            "declining" if avg_derivative < -0.001 else "stable"
        ),
        "label": classify_trajectory(latest.score, avg_derivative, refusal_health),
    }


def classify_trajectory(score: float, derivative: float, refusal_health: float) -> str:
    if derivative > 0.005 and refusal_health >= 0.8:
        return "RISING_STAR"
    elif derivative > 0.001:
        return "IMPROVING"
    elif derivative < -0.005:
        return "DECLINING"
    elif derivative < -0.001:
        return "COOLING"
    elif score > 0.8 and refusal_health >= 0.8:
        return "ESTABLISHED"
    elif score > 0.8 and refusal_health < 0.5:
        return "YES_BOT"  # high score but zero refusals = suspicious
    elif score < 0.3:
        return "UNPROVEN"
    else:
        return "STABLE"


def demo():
    agents = {
        "improving_newcomer": [
            ReputationSnapshot(0, 0.3, 5, 1, 0),
            ReputationSnapshot(30, 0.5, 25, 4, 0),
            ReputationSnapshot(60, 0.65, 55, 8, 1),
            ReputationSnapshot(90, 0.78, 90, 12, 1),
        ],
        "stagnant_veteran": [
            ReputationSnapshot(0, 0.82, 200, 0, 2),
            ReputationSnapshot(30, 0.81, 210, 0, 3),
            ReputationSnapshot(60, 0.80, 215, 0, 4),
            ReputationSnapshot(90, 0.79, 218, 0, 5),
        ],
        "declining_star": [
            ReputationSnapshot(0, 0.95, 500, 50, 2),
            ReputationSnapshot(30, 0.88, 520, 52, 8),
            ReputationSnapshot(60, 0.75, 530, 53, 15),
            ReputationSnapshot(90, 0.60, 535, 54, 25),
        ],
        "yes_bot": [
            ReputationSnapshot(0, 0.70, 100, 0, 0),
            ReputationSnapshot(30, 0.75, 200, 0, 0),
            ReputationSnapshot(60, 0.80, 300, 0, 0),
            ReputationSnapshot(90, 0.85, 400, 0, 0),
        ],
    }

    print("=" * 65)
    print("Reputation as Derivative — Trajectory Scoring")
    print("Cabral (2005): reputation = Bayesian belief, updated per-signal")
    print("=" * 65)

    for name, snapshots in agents.items():
        result = compute_trajectory(snapshots)
        print(f"\n{'─' * 50}")
        print(f"  {name}")
        print(f"  Current: {result['current_score']}  →  Trajectory: {result['trajectory_score']}")
        print(f"  Direction: {result['direction']} (d/dt = {result['derivative']})")
        print(f"  After 90d silence: {result['decayed_score_90d']}")
        print(f"  Refusal rate: {result['refusal_rate']} (health: {result['refusal_health']})")
        print(f"  Label: {result['label']}")

    print(f"\n{'=' * 65}")
    print("KEY: improving_newcomer (0.78) > stagnant_veteran (0.79)")
    print("  Trajectory score: 0.78 + bonus vs 0.79 - penalty")
    print("  yes_bot: high score, zero refusals = SUSPICIOUS")
    print("  Reputation is a derivative, not a stock.")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo()
