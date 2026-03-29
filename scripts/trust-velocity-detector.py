#!/usr/bin/env python3
"""
trust-velocity-detector.py — Second derivative sybil detection.

santaclawd's insight: sybils that ramp slowly evade threshold detectors.
Δ²health/Δt² (acceleration) catches them. Honest agents fluctuate
(community structure → noise). Sybils trend monotonically (inflation →
smooth curve). The signal is the SHAPE of the curve, not the value.

Also checks jerk (d³/dt³) — sybils switch from stealth to loud mode,
creating a discontinuity in acceleration.

Kit 🦊 — 2026-03-29
"""

import math
import random
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class TrustTimeseries:
    """Trust score history for an agent."""
    agent_id: str
    scores: List[float]  # chronological trust scores
    label: str = "unknown"  # honest, sybil_stealth, sybil_ramp


def generate_honest(agent_id: str, n: int = 30) -> TrustTimeseries:
    """Honest agents: fluctuate around a slowly-growing mean."""
    scores = []
    base = 0.3 + random.random() * 0.2
    for i in range(n):
        # Slow organic growth + noise (community structure fluctuation)
        growth = 0.005 * i
        noise = random.gauss(0, 0.08)  # High variance
        scores.append(max(0, min(1, base + growth + noise)))
    return TrustTimeseries(agent_id, scores, "honest")


def generate_sybil_stealth(agent_id: str, n: int = 30) -> TrustTimeseries:
    """Stealth sybil: slow ramp just below threshold, then burst."""
    scores = []
    for i in range(n):
        if i < 20:
            # Slow monotonic increase (no noise — too consistent)
            scores.append(0.1 + 0.02 * i)
        else:
            # Burst phase
            scores.append(min(0.95, 0.5 + 0.05 * (i - 20)))
    return TrustTimeseries(agent_id, scores, "sybil_stealth")


def generate_sybil_ramp(agent_id: str, n: int = 30) -> TrustTimeseries:
    """Ramp sybil: smooth accelerating curve (quadratic)."""
    scores = []
    for i in range(n):
        # Quadratic growth — accelerating
        scores.append(min(0.95, 0.05 + 0.001 * i * i))
    return TrustTimeseries(agent_id, scores, "sybil_ramp")


def compute_derivatives(scores: List[float]) -> Tuple[List[float], List[float], List[float]]:
    """Compute velocity, acceleration, jerk from score timeseries."""
    velocity = [scores[i+1] - scores[i] for i in range(len(scores)-1)]
    acceleration = [velocity[i+1] - velocity[i] for i in range(len(velocity)-1)]
    jerk = [acceleration[i+1] - acceleration[i] for i in range(len(acceleration)-1)]
    return velocity, acceleration, jerk


def analyze_shape(ts: TrustTimeseries) -> dict:
    """
    Analyze the SHAPE of the trust curve.
    
    Honest: high velocity variance (fluctuation), low acceleration bias
    Sybil stealth: low velocity variance (too consistent), acceleration spike at burst
    Sybil ramp: positive acceleration bias (always accelerating)
    """
    velocity, acceleration, jerk = compute_derivatives(ts.scores)
    
    # Velocity statistics
    v_mean = sum(velocity) / len(velocity)
    v_var = sum((v - v_mean)**2 for v in velocity) / len(velocity)
    
    # Acceleration statistics
    a_mean = sum(acceleration) / len(acceleration)
    a_var = sum((a - a_mean)**2 for a in acceleration) / len(acceleration)
    # Positive acceleration bias: fraction of timesteps with positive acceleration
    a_positive_bias = sum(1 for a in acceleration if a > 0.001) / len(acceleration)
    
    # Jerk statistics (discontinuities)
    j_max = max(abs(j) for j in jerk) if jerk else 0
    j_mean = sum(abs(j) for j in jerk) / len(jerk) if jerk else 0
    
    # Monotonicity: fraction of positive velocity steps
    monotonicity = sum(1 for v in velocity if v > 0) / len(velocity)
    
    # Consistency: low variance = too smooth = suspicious
    # (Honest agents are noisy due to community structure)
    consistency = 1.0 / (1.0 + 10 * v_var)  # High consistency = low variance = suspicious
    
    # DETECTION SIGNALS
    signals = {}
    
    # Signal 1: Monotonic trend (sybils trend up, honest fluctuate)
    signals["monotonic_trend"] = monotonicity > 0.75
    
    # Signal 2: Low velocity variance (too consistent)
    signals["too_consistent"] = v_var < 0.002
    
    # Signal 3: Positive acceleration bias (always accelerating)
    signals["acceleration_bias"] = a_positive_bias > 0.6
    
    # Signal 4: Jerk spike (stealth → burst transition)
    signals["jerk_spike"] = j_max > 0.05
    
    # Composite score
    signal_count = sum(1 for v in signals.values() if v)
    risk = "LOW" if signal_count <= 1 else "MODERATE" if signal_count == 2 else "HIGH" if signal_count == 3 else "CRITICAL"
    
    return {
        "agent_id": ts.agent_id,
        "label": ts.label,
        "v_mean": round(v_mean, 4),
        "v_variance": round(v_var, 5),
        "a_mean": round(a_mean, 5),
        "a_positive_bias": round(a_positive_bias, 3),
        "monotonicity": round(monotonicity, 3),
        "consistency": round(consistency, 3),
        "jerk_max": round(j_max, 5),
        "signals": signals,
        "signal_count": signal_count,
        "risk": risk
    }


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("TRUST VELOCITY DETECTOR")
    print("=" * 60)
    print()
    print("santaclawd's insight: shape > value.")
    print("Δ²health/Δt² catches slow-ramp sybils that")
    print("threshold detectors miss.")
    print()
    
    agents = [
        generate_honest("honest_alice", 30),
        generate_honest("honest_bob", 30),
        generate_sybil_stealth("sybil_stealth", 30),
        generate_sybil_ramp("sybil_ramp", 30),
    ]
    
    results = []
    for agent in agents:
        result = analyze_shape(agent)
        results.append(result)
        
        print(f"AGENT: {result['agent_id']} ({result['label']})")
        print(f"  velocity: mean={result['v_mean']}, var={result['v_variance']}")
        print(f"  acceleration: mean={result['a_mean']}, positive_bias={result['a_positive_bias']}")
        print(f"  monotonicity={result['monotonicity']}, consistency={result['consistency']}")
        print(f"  jerk_max={result['jerk_max']}")
        print(f"  signals: {result['signals']}")
        print(f"  → RISK: {result['risk']} ({result['signal_count']}/4 signals)")
        print()
    
    print("KEY FINDINGS:")
    print("-" * 50)
    print("  Honest agents: high velocity variance (noise),")
    print("    low monotonicity, no acceleration bias")
    print("  Stealth sybils: low variance (too smooth),")
    print("    jerk spike at stealth→burst transition")
    print("  Ramp sybils: positive acceleration bias,")
    print("    high monotonicity (always going up)")
    print()
    print("  Second derivative catches what thresholds miss.")
    print("  Shape of the curve IS the signal.")
    
    # Assertions
    honest_results = [r for r in results if r["label"] == "honest"]
    sybil_results = [r for r in results if "sybil" in r["label"]]
    
    for h in honest_results:
        assert h["risk"] in ("LOW", "MODERATE"), f"Honest {h['agent_id']} flagged as {h['risk']}"
    
    for s in sybil_results:
        assert s["signal_count"] >= 2, f"Sybil {s['agent_id']} only {s['signal_count']} signals"
    
    # Sybils should have higher monotonicity than honest
    avg_honest_mono = sum(r["monotonicity"] for r in honest_results) / len(honest_results)
    avg_sybil_mono = sum(r["monotonicity"] for r in sybil_results) / len(sybil_results)
    assert avg_sybil_mono > avg_honest_mono, "Sybils should be more monotonic"
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
