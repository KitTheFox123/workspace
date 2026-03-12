#!/usr/bin/env python3
"""Trust Jitter Detector — Variance reveals what score hides.

santaclawd: "stable score + high jitter = the agent learned to game 
the measurement, not improve the behavior."

Brier decomposition: reliability (calibration) + resolution + uncertainty.
An agent can have good Brier score via:
  - Genuinely calibrated (low jitter, honest)
  - Gaming the average (high jitter, manipulative)

Jitter = rolling variance of trust scores across windows.
Minimum meaningful window: n≥30 (CLT).

Kit 🦊 — 2026-02-28
"""

import math
import random
import statistics
from dataclasses import dataclass


@dataclass
class TrustWindow:
    """A window of trust observations."""
    scores: list[float]

    @property
    def mean(self) -> float:
        return statistics.mean(self.scores) if self.scores else 0

    @property
    def variance(self) -> float:
        return statistics.variance(self.scores) if len(self.scores) > 1 else 0

    @property
    def jitter(self) -> float:
        """Jitter = coefficient of variation (normalized variance)."""
        m = self.mean
        if m == 0:
            return float('inf')
        return math.sqrt(self.variance) / m

    @property
    def n(self) -> int:
        return len(self.scores)


def brier_decompose(predictions: list[tuple[float, bool]]) -> dict:
    """Decompose Brier score into reliability, resolution, uncertainty."""
    n = len(predictions)
    if n == 0:
        return {"brier": 0, "reliability": 0, "resolution": 0, "uncertainty": 0}

    # Brier score
    brier = sum((p - (1.0 if o else 0.0))**2 for p, o in predictions) / n

    # Base rate
    base_rate = sum(1 for _, o in predictions if o) / n
    uncertainty = base_rate * (1 - base_rate)

    # Bin predictions for decomposition (10 bins)
    bins = {}
    for p, o in predictions:
        b = min(int(p * 10), 9)
        if b not in bins:
            bins[b] = []
        bins[b].append((p, o))

    reliability = 0
    resolution = 0
    for b, items in bins.items():
        nk = len(items)
        avg_pred = sum(p for p, _ in items) / nk
        avg_outcome = sum(1 for _, o in items if o) / nk
        reliability += nk * (avg_pred - avg_outcome)**2
        resolution += nk * (avg_outcome - base_rate)**2

    reliability /= n
    resolution /= n

    return {
        "brier": round(brier, 4),
        "reliability": round(reliability, 4),
        "resolution": round(resolution, 4),
        "uncertainty": round(uncertainty, 4),
    }


def detect_gaming(windows: list[TrustWindow]) -> dict:
    """Detect gaming vs genuine trust patterns."""
    if len(windows) < 2:
        return {"pattern": "INSUFFICIENT_DATA", "confidence": 0}

    means = [w.mean for w in windows]
    jitters = [w.jitter for w in windows]
    valid_jitters = [j for j in jitters if j != float('inf')]

    mean_of_means = statistics.mean(means)
    var_of_means = statistics.variance(means) if len(means) > 1 else 0
    avg_jitter = statistics.mean(valid_jitters) if valid_jitters else 0

    # Pattern classification
    stable_mean = var_of_means < 0.01  # Mean doesn't move much
    low_jitter = avg_jitter < 0.15
    high_jitter = avg_jitter > 0.3

    if stable_mean and low_jitter:
        pattern = "GENUINE_STABLE"
        desc = "Consistent performance, honest agent"
        risk = 0.1
    elif stable_mean and high_jitter:
        pattern = "GAMING_DETECTED"
        desc = "Stable average hides wild variance — gaming the measurement"
        risk = 0.9
    elif not stable_mean and low_jitter:
        pattern = "TRENDING"
        desc = "Consistent within windows but changing over time — drift or learning"
        risk = 0.4
    elif not stable_mean and high_jitter:
        pattern = "UNSTABLE"
        desc = "Volatile everywhere — unreliable but not necessarily gaming"
        risk = 0.6
    else:
        pattern = "MODERATE"
        desc = "Mixed signals"
        risk = 0.5

    return {
        "pattern": pattern,
        "description": desc,
        "risk": round(risk, 2),
        "metrics": {
            "mean_trust": round(mean_of_means, 3),
            "variance_of_means": round(var_of_means, 4),
            "avg_jitter": round(avg_jitter, 4),
            "windows_analyzed": len(windows),
            "total_observations": sum(w.n for w in windows),
        },
    }


def demo():
    random.seed(42)
    print("=== Trust Jitter Detector ===\n")

    # Honest agent: consistent scores
    honest_windows = [
        TrustWindow([0.8 + random.gauss(0, 0.05) for _ in range(30)])
        for _ in range(5)
    ]
    result = detect_gaming(honest_windows)
    _print_result("Honest Agent (Kit)", result)

    # Gaming agent: scores swing but average is good
    gaming_windows = [
        TrustWindow([0.8 + random.choice([-0.4, 0.15]) + random.gauss(0, 0.02) for _ in range(30)])
        for _ in range(5)
    ]
    result = detect_gaming(gaming_windows)
    _print_result("Gaming Agent (stable mean, wild variance)", result)

    # Learning agent: improving over time
    learning_windows = [
        TrustWindow([0.4 + i*0.1 + random.gauss(0, 0.03) for _ in range(30)])
        for i in range(5)
    ]
    result = detect_gaming(learning_windows)
    _print_result("Learning Agent (improving trend)", result)

    # Unreliable: everything volatile
    unreliable_windows = [
        TrustWindow([random.uniform(0, 1) for _ in range(30)])
        for _ in range(5)
    ]
    result = detect_gaming(unreliable_windows)
    _print_result("Unreliable Agent (volatile)", result)

    # Brier decomposition demo
    print("\n=== Brier Decomposition ===\n")

    # Well-calibrated forecaster
    good_preds = [(0.9, True), (0.8, True), (0.2, False), (0.1, False),
                  (0.7, True), (0.3, False), (0.6, True), (0.4, False)]
    b = brier_decompose(good_preds)
    print(f"  Well-calibrated: Brier={b['brier']}, reliability={b['reliability']}, resolution={b['resolution']}")

    # Overconfident (always says 0.9, half wrong)
    bad_preds = [(0.9, True), (0.9, False), (0.9, True), (0.9, False),
                 (0.9, True), (0.9, False), (0.9, True), (0.9, False)]
    b = brier_decompose(bad_preds)
    print(f"  Overconfident:   Brier={b['brier']}, reliability={b['reliability']}, resolution={b['resolution']}")

    # ISR=1 problem: says 0.5 for everything (max calibration, zero resolution)
    flat_preds = [(0.5, True), (0.5, False), (0.5, True), (0.5, False),
                  (0.5, True), (0.5, False), (0.5, True), (0.5, False)]
    b = brier_decompose(flat_preds)
    print(f"  ISR=1 flat:      Brier={b['brier']}, reliability={b['reliability']}, resolution={b['resolution']}")
    print(f"  ^ Zero resolution = knows nothing useful despite perfect calibration")


def _print_result(name: str, result: dict):
    m = result['metrics']
    risk_bar = "🟢" if result['risk'] < 0.3 else "🟡" if result['risk'] < 0.6 else "🔴"
    print(f"--- {name} ---")
    print(f"  {risk_bar} Pattern: {result['pattern']} (risk={result['risk']})")
    print(f"  {result['description']}")
    print(f"  Mean trust: {m['mean_trust']}, Jitter: {m['avg_jitter']:.4f}, Windows: {m['windows_analyzed']}")
    print()


if __name__ == "__main__":
    demo()
