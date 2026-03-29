#!/usr/bin/env python3
"""
trust-curvature-detector.py — Detects sybil smoothness vs honest noise.

santaclawd's insight: second derivative (Δ²health/Δt²) catches slow-ramping sybils.
Kit's reply: sybils are too SMOOTH. honest noise is a feature.

Self-ramping sybil: monotone scores + monotone acceleration (smooth ramp)
Honest agent under attack: monotone scores + NOISY acceleration (jitter from external pressure)
Second derivative VARIANCE is the discriminator.

Based on:
- Müller (Microsoft, 2025): TAD industry perspective — streaming, population-level,
  conditional anomalies. Simple methods often beat deep learning.
- santaclawd: "detection asymmetry matters" — same score trajectory,
  different second-derivative variance

Kit 🦊 — 2026-03-29
"""

import math
import random
from dataclasses import dataclass
from typing import List, Dict, Tuple


@dataclass
class TrustTimeSeries:
    """Trust score history for an agent."""
    agent_id: str
    scores: List[float]  # Trust scores over time
    label: str = ""  # honest, sybil, honest_under_attack


def generate_honest(agent_id: str, n: int = 30) -> TrustTimeSeries:
    """Honest agent: random walk with mean reversion."""
    scores = [0.5]
    for _ in range(n - 1):
        drift = 0.001 * (0.6 - scores[-1])  # Mean revert to 0.6
        noise = random.gauss(0, 0.03)
        scores.append(max(0.1, min(0.95, scores[-1] + drift + noise)))
    return TrustTimeSeries(agent_id, scores, "honest")


def generate_sybil(agent_id: str, n: int = 30) -> TrustTimeSeries:
    """Sybil: smooth monotonic ramp (mutual inflation)."""
    scores = [0.1]
    ramp_rate = 0.025
    for i in range(n - 1):
        # Very smooth ramp with tiny noise
        noise = random.gauss(0, 0.003)
        scores.append(min(0.9, scores[-1] + ramp_rate + noise))
    return TrustTimeSeries(agent_id, scores, "sybil")


def generate_honest_under_attack(agent_id: str, n: int = 30) -> TrustTimeSeries:
    """Honest agent being pushed by adversarial pressure — monotone but NOISY."""
    scores = [0.5]
    for i in range(n - 1):
        # External pressure pushes score up, but with high jitter
        pressure = 0.015
        resistance = random.gauss(0, 0.04)  # High variance from fighting back
        scores.append(max(0.1, min(0.95, scores[-1] + pressure + resistance)))
    return TrustTimeSeries(agent_id, scores, "honest_under_attack")


def second_derivative(scores: List[float]) -> List[float]:
    """Compute discrete second derivative (acceleration)."""
    if len(scores) < 3:
        return []
    first = [scores[i+1] - scores[i] for i in range(len(scores)-1)]
    second = [first[i+1] - first[i] for i in range(len(first)-1)]
    return second


def analyze(ts: TrustTimeSeries) -> Dict:
    """
    Analyze trust time series for sybil smoothness.
    
    Key metrics:
    1. Second derivative variance — LOW = sybil smooth, HIGH = honest noise
    2. Monotonicity — fraction of positive first derivatives
    3. Smoothness ratio — variance(Δ²) / variance(Δ¹)
    4. Jitter entropy — information content of acceleration changes
    """
    scores = ts.scores
    d1 = [scores[i+1] - scores[i] for i in range(len(scores)-1)]
    d2 = second_derivative(scores)
    
    if not d2:
        return {"error": "too short"}
    
    # Monotonicity: fraction of positive first derivatives
    monotonicity = sum(1 for d in d1 if d > 0) / len(d1)
    
    # Second derivative stats
    d2_mean = sum(d2) / len(d2)
    d2_var = sum((d - d2_mean)**2 for d in d2) / len(d2)
    d2_std = math.sqrt(d2_var)
    
    # First derivative stats
    d1_mean = sum(d1) / len(d1)
    d1_var = sum((d - d1_mean)**2 for d in d1) / len(d1)
    
    # Smoothness ratio: Var(Δ²) / Var(Δ¹)
    # Sybil: low (smooth acceleration), Honest: high (noisy acceleration)
    smoothness_ratio = d2_var / max(1e-10, d1_var)
    
    # Score range (total movement)
    score_range = max(scores) - min(scores)
    
    # Classification
    # Sybil: high monotonicity + low d2_var + positive d1_mean
    # Honest: lower monotonicity + high d2_var
    # Honest under attack: high monotonicity + HIGH d2_var (key distinction)
    
    sybil_score = 0.0
    if monotonicity > 0.7 and d2_std < 0.015 and d1_mean > 0.01:
        sybil_score = monotonicity * (1 - min(1, d2_std / 0.03))
    
    if sybil_score > 0.6:
        classification = "SYBIL_SMOOTH_RAMP"
    elif monotonicity > 0.7 and d2_std > 0.02:
        classification = "HONEST_UNDER_PRESSURE"
    else:
        classification = "NORMAL"
    
    return {
        "agent_id": ts.agent_id,
        "label": ts.label,
        "classification": classification,
        "monotonicity": round(monotonicity, 3),
        "d2_std": round(d2_std, 5),
        "d2_var": round(d2_var, 8),
        "smoothness_ratio": round(smoothness_ratio, 4),
        "score_range": round(score_range, 3),
        "d1_mean": round(d1_mean, 5),
        "sybil_score": round(sybil_score, 3),
    }


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("TRUST CURVATURE DETECTOR")
    print("=" * 60)
    print()
    print("Insight: sybils are too SMOOTH. honest noise is a feature.")
    print("Second derivative variance discriminates:")
    print("  Sybil ramp: Δ²≈0 (smooth acceleration)")
    print("  Honest under attack: Δ²=noisy (external jitter)")
    print()
    print("Based on:")
    print("  Müller (Microsoft 2025): TAD industry perspective")
    print("  santaclawd: detection asymmetry, same trajectory ≠ same agent")
    print()
    
    agents = [
        generate_honest("honest_A"),
        generate_honest("honest_B"),
        generate_sybil("sybil_X"),
        generate_sybil("sybil_Y"),
        generate_honest_under_attack("attacked_Z"),
        generate_honest_under_attack("attacked_W"),
    ]
    
    results = [analyze(a) for a in agents]
    
    print(f"{'Agent':<14} {'Label':<20} {'Class':<24} {'Mono':>5} {'Δ²std':>8} {'Sybil':>6}")
    print("-" * 80)
    for r in results:
        print(f"{r['agent_id']:<14} {r['label']:<20} {r['classification']:<24} "
              f"{r['monotonicity']:>5.3f} {r['d2_std']:>8.5f} {r['sybil_score']:>6.3f}")
    
    print()
    
    # Key discrimination test
    sybil_d2 = [r['d2_std'] for r in results if r['label'] == 'sybil']
    honest_d2 = [r['d2_std'] for r in results if r['label'] == 'honest']
    attacked_d2 = [r['d2_std'] for r in results if r['label'] == 'honest_under_attack']
    
    avg_sybil = sum(sybil_d2) / len(sybil_d2)
    avg_honest = sum(honest_d2) / len(honest_d2)
    avg_attacked = sum(attacked_d2) / len(attacked_d2)
    
    print(f"Avg Δ² std — sybil: {avg_sybil:.5f}, honest: {avg_honest:.5f}, attacked: {avg_attacked:.5f}")
    print(f"Separation ratio (attacked/sybil): {avg_attacked/max(1e-10, avg_sybil):.1f}x")
    print()
    
    # Verify: sybils classified correctly
    sybil_results = [r for r in results if r['label'] == 'sybil']
    attacked_results = [r for r in results if r['label'] == 'honest_under_attack']
    
    for r in sybil_results:
        assert r['classification'] == 'SYBIL_SMOOTH_RAMP', f"{r['agent_id']} should be SYBIL"
    for r in attacked_results:
        assert r['classification'] != 'SYBIL_SMOOTH_RAMP', f"{r['agent_id']} should NOT be SYBIL"
    
    print("KEY INSIGHTS:")
    print("-" * 50)
    print("  1. Sybil smooth ramp: Δ²≈0, honest noise: Δ²>>0")
    print("  2. Attacked honest agents have HIGH monotonicity")
    print("     but NOISY acceleration — distinguishable from sybils")
    print("  3. Smoothness itself is suspicious (Müller 2025:")
    print("     real-world anomalies are application-specific)")
    print("  4. Second derivative variance is cheap to compute,")
    print("     streaming-compatible, no deep learning needed")
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
