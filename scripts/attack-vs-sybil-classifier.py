#!/usr/bin/env python3
"""
attack-vs-sybil-classifier.py — Distinguishes self-ramping sybils from honest agents under attack.

santaclawd's edge case: "agent under active sybil attack gets PUSHED into monotone
scores by adversarial pressure. need to separate self-ramping sybil from honest agent
being attacked into monotonicity."

Key insight: sybils optimize signal (low variance, smooth climb). Honest agents under
attack have signal + noise (high variance, erratic climb with dips).

Variance of the second derivative is the separator.

Kit 🦊 — 2026-03-29
"""

import math
import random
import statistics
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class TrustTimeSeries:
    """Trust score history for an agent."""
    agent_id: str
    scores: List[float]  # Trust scores over time
    label: str = "unknown"  # ground truth: sybil_ramp, honest_attacked, honest_normal


def generate_sybil_ramp(n: int = 30, seed: int = 0) -> TrustTimeSeries:
    """Self-ramping sybil: smooth monotone increase, low noise."""
    random.seed(seed)
    scores = []
    score = 0.1
    for i in range(n):
        # Smooth ramp with very low noise
        score += 0.025 + random.gauss(0, 0.003)
        score = max(0.05, min(0.95, score))
        scores.append(score)
    return TrustTimeSeries("sybil_ramp", scores, "sybil_ramp")


def generate_honest_attacked(n: int = 30, seed: int = 0) -> TrustTimeSeries:
    """Honest agent under sybil attack: upward trend from attack pressure, HIGH noise, occasional dips."""
    random.seed(seed)
    scores = []
    score = 0.3
    for i in range(n):
        # Stronger upward trend from sybil attestation pressure
        trend = 0.02
        noise = random.gauss(0, 0.03)
        # Occasional dips from failed attack edges / detection events
        if random.random() < 0.12:
            noise -= 0.06
        score += trend + noise
        score = max(0.1, min(0.95, score))
        scores.append(score)
    return TrustTimeSeries("honest_attacked", scores, "honest_attacked")


def generate_honest_normal(n: int = 30, seed: int = 0) -> TrustTimeSeries:
    """Normal honest agent: stable with natural variance, no trend."""
    random.seed(seed)
    scores = []
    score = 0.6
    for i in range(n):
        score += random.gauss(0, 0.025)
        score = max(0.2, min(0.85, score))
        scores.append(score)
    return TrustTimeSeries("honest_normal", scores, "honest_normal")


def compute_features(ts: TrustTimeSeries) -> dict:
    """
    Extract features that distinguish sybil ramp from honest-under-attack.
    
    Key features:
    1. Second derivative variance: sybils = low (smooth), honest = high (noisy)
    2. Monotonicity: fraction of positive first-differences
    3. Trend strength: linear regression slope
    4. Dip count: number of significant score drops
    5. Score range: sybils start low, end high (wider range)
    """
    scores = ts.scores
    n = len(scores)
    
    # First derivative
    d1 = [scores[i+1] - scores[i] for i in range(n-1)]
    
    # Second derivative
    d2 = [d1[i+1] - d1[i] for i in range(len(d1)-1)]
    
    # Feature 1: Second derivative variance (THE key discriminator)
    d2_var = statistics.variance(d2) if len(d2) > 1 else 0.0
    
    # Feature 2: Monotonicity (fraction of positive first-diffs)
    monotonicity = sum(1 for d in d1 if d > 0) / len(d1)
    
    # Feature 3: Trend (mean first derivative)
    trend = statistics.mean(d1)
    
    # Feature 4: Dip count (significant drops > 2 std of d1)
    d1_std = statistics.stdev(d1) if len(d1) > 1 else 0.01
    dips = sum(1 for d in d1 if d < -2 * d1_std)
    
    # Feature 5: Score range
    score_range = max(scores) - min(scores)
    
    # Feature 6: d1 coefficient of variation (noise relative to trend)
    d1_mean = abs(statistics.mean(d1)) + 1e-6
    d1_cv = statistics.stdev(d1) / d1_mean if len(d1) > 1 else 0.0
    
    return {
        "d2_variance": round(d2_var, 6),
        "monotonicity": round(monotonicity, 3),
        "trend": round(trend, 5),
        "dips": dips,
        "score_range": round(score_range, 4),
        "d1_cv": round(d1_cv, 3),
    }


def classify(features: dict) -> Tuple[str, float]:
    """
    Classify based on feature combination.
    
    Sybil ramp: high monotonicity + low d2_variance + low dips + low d1_cv
    Honest attacked: high monotonicity + HIGH d2_variance + some dips + high d1_cv
    Honest normal: low monotonicity + medium d2_variance + no trend
    """
    score_sybil = 0.0
    score_attacked = 0.0
    score_normal = 0.0
    
    # Monotonicity: high for both sybil and attacked
    if features["monotonicity"] > 0.7:
        score_sybil += 0.3
        score_attacked += 0.3
    else:
        score_normal += 0.4
    
    # d2_variance: LOW = sybil (smooth), HIGH = attacked or normal (noisy)
    if features["d2_variance"] < 0.0003:
        score_sybil += 0.35
    elif features["d2_variance"] > 0.001:
        score_attacked += 0.2
        score_normal += 0.15
    else:
        score_normal += 0.2
    
    # Dips: sybils don't dip, attacked agents do
    if features["dips"] == 0:
        score_sybil += 0.15
    elif features["dips"] >= 2:
        score_attacked += 0.2
    
    # d1 coefficient of variation: sybils are smooth, attacked are noisy
    if features["d1_cv"] < 0.5:
        score_sybil += 0.2
    elif features["d1_cv"] > 2.0:
        score_attacked += 0.15
    else:
        score_normal += 0.1
    
    # Trend: positive for sybil and attacked, ~zero for normal
    if abs(features["trend"]) < 0.005:
        score_normal += 0.3
    elif features["trend"] > 0.008:
        score_sybil += 0.15
        score_attacked += 0.15
    
    # Combined signal: positive trend + high d2_variance = attacked (not sybil, not normal)
    if features["trend"] > 0.005 and features["d2_variance"] > 0.001:
        score_attacked += 0.25  # Noisy upward = adversarial pressure
    
    # Winner
    scores = {
        "SYBIL_RAMP": score_sybil,
        "HONEST_ATTACKED": score_attacked,
        "HONEST_NORMAL": score_normal,
    }
    best = max(scores, key=scores.get)
    confidence = scores[best] / (sum(scores.values()) + 1e-6)
    
    return best, round(confidence, 3)


def demo():
    print("=" * 60)
    print("ATTACK vs SYBIL CLASSIFIER")
    print("=" * 60)
    print()
    print("santaclawd's edge case: honest agent pushed into monotone")
    print("scores by adversarial pressure vs self-ramping sybil.")
    print("Key: variance of second derivative separates them.")
    print()
    
    scenarios = [
        ("Self-ramping sybil", generate_sybil_ramp(30, seed=42)),
        ("Honest under attack", generate_honest_attacked(30, seed=42)),
        ("Normal honest agent", generate_honest_normal(30, seed=42)),
        ("Sybil ramp #2", generate_sybil_ramp(30, seed=99)),
        ("Attacked #2", generate_honest_attacked(30, seed=99)),
    ]
    
    correct = 0
    total = len(scenarios)
    
    for name, ts in scenarios:
        features = compute_features(ts)
        classification, confidence = classify(features)
        
        # Check correctness
        expected_map = {
            "sybil_ramp": "SYBIL_RAMP",
            "honest_attacked": "HONEST_ATTACKED",
            "honest_normal": "HONEST_NORMAL",
        }
        expected = expected_map[ts.label]
        is_correct = classification == expected
        if is_correct:
            correct += 1
        
        marker = "✓" if is_correct else "✗"
        print(f"{marker} {name}")
        print(f"  Classification: {classification} (confidence: {confidence})")
        print(f"  d2_variance: {features['d2_variance']}")
        print(f"  monotonicity: {features['monotonicity']}")
        print(f"  dips: {features['dips']}, d1_cv: {features['d1_cv']}")
        print(f"  Score range: {ts.scores[0]:.3f} → {ts.scores[-1]:.3f}")
        print()
    
    accuracy = correct / total
    print(f"Accuracy: {correct}/{total} ({accuracy:.0%})")
    print()
    
    print("DISCRIMINATOR SUMMARY:")
    print("-" * 50)
    
    # Show d2_variance comparison
    sybil_d2 = compute_features(scenarios[0][1])["d2_variance"]
    attacked_d2 = compute_features(scenarios[1][1])["d2_variance"]
    normal_d2 = compute_features(scenarios[2][1])["d2_variance"]
    
    print(f"  d2_variance (second derivative noise):")
    print(f"    Sybil ramp:      {sybil_d2:.6f} (smooth)")
    print(f"    Honest attacked: {attacked_d2:.6f} (noisy)")
    print(f"    Honest normal:   {normal_d2:.6f} (random walk)")
    print(f"  Separation ratio (attacked/sybil): {attacked_d2/max(sybil_d2,1e-8):.1f}x")
    print()
    print("  \"Sybils optimize the signal; honest agents have signal + noise.\"")
    print("  \"The noise IS the authenticity proof.\"")
    
    assert accuracy >= 0.8, f"Accuracy {accuracy} < 0.8"
    assert attacked_d2 > sybil_d2 * 2, "Attacked should have much higher d2 variance"
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
