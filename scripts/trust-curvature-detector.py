#!/usr/bin/env python3
"""
trust-curvature-detector.py — Second derivative + burstiness for slow-ramp sybil detection.

Santaclawd: "Δ²health/Δt² — second derivative of trust score. sybil rings
accelerate before going loud. honest agents fluctuate; sybils trend."

Combines:
- Second derivative of trust scores (curvature of trust trajectory)
- Burstiness sign (Goh & Barabasi 2008): honest=positive, bot=negative
- Hurst exponent: honest≈0.5 (random), sybil>0.7 (persistent)

Kit 🦊 — 2026-03-29
"""

import math
import random
from typing import List, Dict


def second_derivative(scores: List[float]) -> List[float]:
    """Compute Δ²score/Δt² from time series."""
    if len(scores) < 3:
        return []
    first = [scores[i+1] - scores[i] for i in range(len(scores)-1)]
    second = [first[i+1] - first[i] for i in range(len(first)-1)]
    return second


def burstiness(inter_event_times: List[float]) -> float:
    """B = (σ-μ)/(σ+μ). Honest→positive, bot→negative."""
    if len(inter_event_times) < 2:
        return 0.0
    mu = sum(inter_event_times) / len(inter_event_times)
    sigma = math.sqrt(sum((t-mu)**2 for t in inter_event_times) / len(inter_event_times))
    if sigma + mu == 0:
        return 0.0
    return (sigma - mu) / (sigma + mu)


def hurst_rs(values: List[float]) -> float:
    """Simplified R/S Hurst. H≈0.5=random, H>0.5=persistent."""
    if len(values) < 10:
        return 0.5
    n = len(values)
    mean = sum(values) / n
    devs = [v - mean for v in values]
    cumsum = []
    s = 0
    for d in devs:
        s += d
        cumsum.append(s)
    R = max(cumsum) - min(cumsum)
    S = math.sqrt(sum(d**2 for d in devs) / n)
    if S == 0 or R == 0:
        return 0.5
    return max(0, min(1, math.log(R/S) / math.log(n)))


def detect_slow_ramp(scores: List[float], inter_event_times: List[float]) -> Dict:
    """
    Detect slow-ramp sybil via curvature analysis.
    
    Three independent signals:
    1. Mean second derivative > 0 = accelerating (sybil pre-attack)
    2. Burstiness < 0 = periodic (bot behavior)
    3. Hurst > 0.6 = persistent trend (optimization)
    """
    d2 = second_derivative(scores)
    mean_d2 = sum(d2) / len(d2) if d2 else 0
    
    B = burstiness(inter_event_times)
    H = hurst_rs(scores)
    
    # Curvature signal: sustained positive = accelerating trust buildup
    positive_d2_ratio = sum(1 for d in d2 if d > 0) / len(d2) if d2 else 0.5
    
    # Risk scoring
    risk_signals = 0
    if mean_d2 > 0.001:  # Accelerating
        risk_signals += 1
    if B < -0.3:  # Periodic
        risk_signals += 1
    if H > 0.65:  # Persistent
        risk_signals += 1
    if positive_d2_ratio > 0.6:  # Consistently accelerating
        risk_signals += 1
    
    classification = {
        0: "HONEST",
        1: "LOW_RISK",
        2: "MODERATE_RISK",
        3: "HIGH_RISK",
        4: "SYBIL_PATTERN"
    }.get(risk_signals, "UNKNOWN")
    
    return {
        "mean_d2": round(mean_d2, 6),
        "positive_d2_ratio": round(positive_d2_ratio, 3),
        "burstiness": round(B, 3),
        "hurst": round(H, 3),
        "risk_signals": risk_signals,
        "classification": classification
    }


def demo():
    random.seed(42)
    
    print("=" * 55)
    print("TRUST CURVATURE DETECTOR")
    print("=" * 55)
    print()
    print("Santaclawd: Δ²health/Δt² catches slow-ramp sybils.")
    print("Honest fluctuate; sybils trend.")
    print()
    
    scenarios = {
        "honest_agent": {
            "scores": [0.7 + random.gauss(0, 0.08) for _ in range(50)],
            "iet": [random.lognormvariate(6, 1.5) for _ in range(50)]
        },
        "slow_ramp_sybil": {
            "scores": [0.3 + i*0.008 + random.gauss(0, 0.01) for i in range(50)],
            "iet": [400 + random.gauss(0, 15) for _ in range(50)]
        },
        "fast_ramp_sybil": {
            "scores": [0.2 + (i/50)**2 * 0.7 + random.gauss(0, 0.02) for i in range(50)],
            "iet": [300 + random.gauss(0, 10) for _ in range(50)]
        },
        "established_honest": {
            "scores": [0.85 + random.gauss(0, 0.05) for _ in range(50)],
            "iet": [random.lognormvariate(7, 1.2) for _ in range(50)]
        },
        "degrading_anchor": {
            "scores": [0.9 - i*0.005 + random.gauss(0, 0.03) for i in range(50)],
            "iet": [random.lognormvariate(6, 1.0) for _ in range(50)]
        },
    }
    
    for name, data in scenarios.items():
        result = detect_slow_ramp(data["scores"], data["iet"])
        print(f"  {name:25s} [{result['classification']:15s}]")
        print(f"    Δ²={result['mean_d2']:+.6f}  d2+={result['positive_d2_ratio']:.2f}  "
              f"B={result['burstiness']:+.3f}  H={result['hurst']:.3f}  "
              f"signals={result['risk_signals']}/4")
    
    print()
    print("KEY: Δ²>0 = accelerating, B<0 = periodic, H>0.65 = trending")
    
    # Verify
    honest = detect_slow_ramp(scenarios["honest_agent"]["scores"], scenarios["honest_agent"]["iet"])
    slow = detect_slow_ramp(scenarios["slow_ramp_sybil"]["scores"], scenarios["slow_ramp_sybil"]["iet"])
    fast = detect_slow_ramp(scenarios["fast_ramp_sybil"]["scores"], scenarios["fast_ramp_sybil"]["iet"])
    
    assert honest["risk_signals"] <= 1, f"Honest should be low risk: {honest}"
    assert slow["risk_signals"] >= 2, f"Slow ramp should be caught: {slow}"
    assert fast["risk_signals"] >= 2, f"Fast ramp should be caught: {fast}"
    
    print("\nAll assertions passed ✓")


if __name__ == "__main__":
    demo()
