#!/usr/bin/env python3
"""proper-scoring-rules.py — Compare Brier, logarithmic, and spherical scoring rules.

Strictly proper scoring rules incentivize honest reporting.
Compares scoring rules on attestor forecasts to find gaming-resistant options.

Based on: Brier (1950), McCarthy (1956), Gneiting & Raftery (2007),
Waghmare & Ziegel (2025, arXiv 2504.01781).

Usage:
    python3 proper-scoring-rules.py [--demo]
"""

import math
import json
from dataclasses import dataclass, asdict
from typing import List, Tuple


@dataclass
class Forecast:
    """A probabilistic forecast with outcome."""
    name: str
    predicted_prob: float  # P(event=1)
    actual_outcome: int    # 0 or 1


def brier_score(p: float, y: int) -> float:
    """Brier (1950) quadratic score. Lower = better. Range [0, 1]."""
    return (p - y) ** 2


def log_score(p: float, y: int) -> float:
    """Logarithmic score. Lower = better. Range [0, inf)."""
    eps = 1e-15
    if y == 1:
        return -math.log(max(p, eps))
    return -math.log(max(1 - p, eps))


def spherical_score(p: float, y: int) -> float:
    """Spherical score. Higher = better. Range [0, 1]."""
    norm = math.sqrt(p**2 + (1-p)**2)
    if norm == 0:
        return 0.0
    if y == 1:
        return p / norm
    return (1 - p) / norm


def gaming_resistance(rule_fn, honest_p: float, y: int) -> dict:
    """Test how much an attestor gains by misreporting.
    
    Returns max gain from lying vs honest reporting.
    """
    honest_score = rule_fn(honest_p, y)
    
    # Try various dishonest reports
    best_dishonest = honest_score
    worst_dishonest = honest_score
    best_lie = honest_p
    
    for p_lie in [i/100 for i in range(1, 100)]:
        lie_score = rule_fn(p_lie, y)
        if lie_score < best_dishonest:  # Lower is better for Brier/log
            best_dishonest = lie_score
            best_lie = p_lie
        if lie_score > worst_dishonest:
            worst_dishonest = lie_score
    
    return {
        "honest_score": round(honest_score, 4),
        "best_lie_score": round(best_dishonest, 4),
        "best_lie_p": round(best_lie, 2),
        "gain_from_lying": round(honest_score - best_dishonest, 4),
        "gaming_resistant": honest_score <= best_dishonest + 0.001,
    }


def demo():
    """Compare scoring rules on attestor scenarios."""
    scenarios = [
        # Well-calibrated attestor
        Forecast("calibrated_correct", 0.8, 1),
        Forecast("calibrated_wrong", 0.8, 0),
        # Overconfident
        Forecast("overconfident_correct", 0.99, 1),
        Forecast("overconfident_wrong", 0.99, 0),
        # Hedge (always 0.5)
        Forecast("hedger_correct", 0.5, 1),
        Forecast("hedger_wrong", 0.5, 0),
        # Dishonest (knows p=0.8, reports 0.95)
        Forecast("dishonest_report", 0.95, 1),
    ]
    
    print("=" * 70)
    print("PROPER SCORING RULES — ATTESTOR INCENTIVE COMPARISON")
    print("=" * 70)
    print()
    print(f"{'Scenario':<25} {'Brier':>8} {'Log':>8} {'Spherical':>10}")
    print("-" * 55)
    
    for f in scenarios:
        b = brier_score(f.predicted_prob, f.actual_outcome)
        l = log_score(f.predicted_prob, f.actual_outcome)
        s = spherical_score(f.predicted_prob, f.actual_outcome)
        print(f"{f.name:<25} {b:>8.4f} {l:>8.4f} {s:>10.4f}")
    
    print()
    print("=" * 70)
    print("GAMING RESISTANCE TEST")
    print("=" * 70)
    print()
    print("Attestor truly believes P(scope_violation)=0.3, outcome=1")
    print()
    
    for name, fn in [("Brier", brier_score), ("Log", log_score)]:
        result = gaming_resistance(fn, 0.3, 1)
        print(f"{name}: honest={result['honest_score']:.4f}, "
              f"best_lie={result['best_lie_score']:.4f} (p={result['best_lie_p']}), "
              f"gain={result['gain_from_lying']:.4f}, "
              f"resistant={result['gaming_resistant']}")
    
    print()
    print("Key findings:")
    print("• Brier: bounded [0,1], quadratic penalty, robust to extreme forecasts")
    print("• Log: unbounded, infinite penalty for confident wrong forecasts")
    print("• Both strictly proper: honest reporting = optimal strategy")
    print("• For attestors: Brier preferred (bounded, decomposable, interpretable)")
    print("• McCarthy (1956) proved properness — same person who invented Lisp")


if __name__ == "__main__":
    demo()
