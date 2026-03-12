#!/usr/bin/env python3
"""Brier Calibration Tracker — Tetlock-style prediction scoring for agents.

Agents estimate P(dispute) at contract creation. After resolution,
Brier score measures calibration. Track over N contracts = reputation.

Brier = (1/N) Σ (forecast - outcome)²
Perfect calibration = 0.0, coin flip = 0.25, always wrong = 1.0

Usage:
  python brier-calibration.py --demo
  echo '{"predictions": [...]}' | python brier-calibration.py --json
"""

import json
import sys
import math
from collections import defaultdict


def brier_score(predictions: list) -> float:
    """Compute Brier score from list of (forecast, outcome) tuples."""
    if not predictions:
        return 0.5
    return sum((f - o) ** 2 for f, o in predictions) / len(predictions)


def calibration_bins(predictions: list, n_bins: int = 10) -> list:
    """Group predictions into calibration bins."""
    bins = defaultdict(lambda: {"forecasts": [], "outcomes": []})
    for f, o in predictions:
        bin_idx = min(int(f * n_bins), n_bins - 1)
        bin_label = f"{bin_idx/n_bins:.1f}-{(bin_idx+1)/n_bins:.1f}"
        bins[bin_label]["forecasts"].append(f)
        bins[bin_label]["outcomes"].append(o)
    
    result = []
    for label in sorted(bins.keys()):
        b = bins[label]
        n = len(b["forecasts"])
        avg_forecast = sum(b["forecasts"]) / n
        avg_outcome = sum(b["outcomes"]) / n
        result.append({
            "bin": label,
            "count": n,
            "avg_forecast": round(avg_forecast, 3),
            "actual_rate": round(avg_outcome, 3),
            "calibration_error": round(abs(avg_forecast - avg_outcome), 3),
        })
    return result


def analyze_agent(predictions: list) -> dict:
    """Full calibration analysis for an agent's prediction history."""
    pairs = [(p["forecast"], p["outcome"]) for p in predictions]
    
    bs = brier_score(pairs)
    
    # Decompose: reliability (calibration) + resolution (discrimination) + uncertainty
    # Simplified: just compute calibration error
    bins = calibration_bins(pairs)
    avg_cal_error = sum(b["calibration_error"] * b["count"] for b in bins) / len(pairs) if pairs else 0
    
    # Tetlock tier
    if bs < 0.05:
        tier = "superforecaster"
    elif bs < 0.15:
        tier = "good"
    elif bs < 0.25:
        tier = "average"
    else:
        tier = "poor"
    
    # Trend (improving or degrading?)
    if len(pairs) >= 10:
        first_half = brier_score(pairs[:len(pairs)//2])
        second_half = brier_score(pairs[len(pairs)//2:])
        trend = "improving" if second_half < first_half else "degrading" if second_half > first_half * 1.2 else "stable"
    else:
        trend = "insufficient_data"
    
    # Confidence vs accuracy
    overconfident = sum(1 for f, o in pairs if f < 0.2 and o == 1)
    underconfident = sum(1 for f, o in pairs if f > 0.8 and o == 0)
    
    return {
        "n_predictions": len(pairs),
        "brier_score": round(bs, 4),
        "tier": tier,
        "trend": trend,
        "avg_calibration_error": round(avg_cal_error, 3),
        "overconfident_count": overconfident,
        "underconfident_count": underconfident,
        "calibration_bins": bins,
        "recommendation": _recommend(bs, tier, trend, overconfident, len(pairs)),
    }


def _recommend(bs, tier, trend, overconf, n):
    if n < 10:
        return f"Only {n} predictions. Need 50+ for reliable calibration."
    if tier == "superforecaster":
        return "Excellent calibration. Trust this agent's confidence estimates."
    if overconf > n * 0.15:
        return f"Overconfident: {overconf} surprise disputes. Widen uncertainty bands."
    if trend == "degrading":
        return "Calibration degrading over time. Possible drift or context shift."
    if tier == "poor":
        return f"Brier {bs:.3f} — worse than chance. Don't trust confidence estimates."
    return f"Brier {bs:.3f} ({tier}). {trend} trend."


def demo():
    import random
    random.seed(42)
    
    print("=" * 60)
    print("Brier Calibration Tracker (Tetlock-style)")
    print("=" * 60)
    
    # Well-calibrated agent
    print("\n--- Agent A: Well-Calibrated (50 contracts) ---")
    well_cal = []
    for _ in range(50):
        true_p = random.uniform(0.05, 0.40)
        forecast = true_p + random.gauss(0, 0.05)
        forecast = max(0, min(1, forecast))
        outcome = 1 if random.random() < true_p else 0
        well_cal.append({"forecast": round(forecast, 2), "outcome": outcome})
    
    r = analyze_agent(well_cal)
    print(f"Brier: {r['brier_score']} | Tier: {r['tier']} | Trend: {r['trend']}")
    print(f"Recommendation: {r['recommendation']}")
    
    # Overconfident agent
    print("\n--- Agent B: Overconfident (50 contracts) ---")
    overconf = []
    for _ in range(50):
        true_p = random.uniform(0.10, 0.35)
        forecast = true_p * 0.3  # Systematically underestimates dispute risk
        outcome = 1 if random.random() < true_p else 0
        overconf.append({"forecast": round(forecast, 2), "outcome": outcome})
    
    r = analyze_agent(overconf)
    print(f"Brier: {r['brier_score']} | Tier: {r['tier']} | Trend: {r['trend']}")
    print(f"Overconfident: {r['overconfident_count']} surprise disputes")
    print(f"Recommendation: {r['recommendation']}")
    
    # New agent (insufficient data)
    print("\n--- Agent C: New (5 contracts) ---")
    new = [{"forecast": 0.15, "outcome": 0}, {"forecast": 0.20, "outcome": 0},
           {"forecast": 0.10, "outcome": 1}, {"forecast": 0.30, "outcome": 0},
           {"forecast": 0.25, "outcome": 0}]
    r = analyze_agent(new)
    print(f"Brier: {r['brier_score']} | Tier: {r['tier']}")
    print(f"Recommendation: {r['recommendation']}")
    
    # Degrading agent
    print("\n--- Agent D: Degrading Over Time (40 contracts) ---")
    degrading = []
    for i in range(40):
        true_p = 0.15 + (i / 40) * 0.3  # Increasing dispute rate
        forecast = 0.15  # Stuck on old estimate
        outcome = 1 if random.random() < true_p else 0
        degrading.append({"forecast": round(forecast, 2), "outcome": outcome})
    
    r = analyze_agent(degrading)
    print(f"Brier: {r['brier_score']} | Tier: {r['tier']} | Trend: {r['trend']}")
    print(f"Recommendation: {r['recommendation']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = analyze_agent(data.get("predictions", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
