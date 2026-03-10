#!/usr/bin/env python3
"""attestation-noise-floor.py — Estimate Bühlmann k parameter for attestor pools.

Measures within-group vs between-group variance to compute k = σ²(within)/σ²(between).
High k = noisy attestors, need more observations before trusting individual scores.
Low k = consistent attestors, individual track record becomes meaningful faster.

Based on Bühlmann credibility theory (1967) and Loss Data Analytics Ch.9.

Usage:
    python3 attestation-noise-floor.py [--demo]
"""

import argparse
import json
import math
import random
from dataclasses import dataclass, asdict
from typing import List, Dict


@dataclass
class AttestorProfile:
    """Attestor with repeated measurements."""
    name: str
    scores: List[float]  # Repeated scores on same/similar tasks
    mean: float = 0.0
    within_var: float = 0.0


@dataclass
class PoolAnalysis:
    """Analysis of an attestor pool."""
    n_attestors: int
    n_observations_each: int
    grand_mean: float
    within_variance: float   # σ²(within) — measurement noise
    between_variance: float  # σ²(between) — real differences
    k_parameter: float       # Bühlmann k = within/between
    z_at_n: Dict[int, float]  # Z values at different n
    noise_grade: str
    recommendation: str


def compute_within_variance(profiles: List[AttestorProfile]) -> float:
    """Average within-attestor variance (measurement noise)."""
    variances = []
    for p in profiles:
        if len(p.scores) < 2:
            continue
        mean = sum(p.scores) / len(p.scores)
        var = sum((s - mean) ** 2 for s in p.scores) / (len(p.scores) - 1)
        p.mean = mean
        p.within_var = var
        variances.append(var)
    return sum(variances) / len(variances) if variances else 0.0


def compute_between_variance(profiles: List[AttestorProfile], 
                            grand_mean: float) -> float:
    """Between-attestor variance (real differences in quality)."""
    if len(profiles) < 2:
        return 0.0
    n_each = len(profiles[0].scores) if profiles else 1
    # MSB - MSW/n (unbiased estimator)
    msb = sum((p.mean - grand_mean) ** 2 for p in profiles) / (len(profiles) - 1)
    msw = compute_within_variance(profiles)
    between = msb - msw / n_each
    return max(0.0, between)  # Floor at 0


def grade_noise(k: float) -> str:
    """Grade noise level."""
    if k < 1: return "A"    # Low noise, individual scores meaningful quickly
    if k < 5: return "B"    # Moderate noise
    if k < 20: return "C"   # High noise, need many observations
    if k < 100: return "D"  # Very high noise
    return "F"               # Noise dominates signal


def analyze_pool(profiles: List[AttestorProfile]) -> PoolAnalysis:
    """Full Bühlmann analysis of attestor pool."""
    # Compute means
    for p in profiles:
        p.mean = sum(p.scores) / len(p.scores)
    
    grand_mean = sum(p.mean for p in profiles) / len(profiles)
    within_var = compute_within_variance(profiles)
    between_var = compute_between_variance(profiles, grand_mean)
    
    # k = within/between (handle zero between)
    k = within_var / between_var if between_var > 0.001 else 999.0
    
    # Z at different observation counts
    z_values = {}
    for n in [1, 5, 10, 25, 50, 100]:
        z_values[n] = n / (n + k)
    
    grade = grade_noise(k)
    
    if grade == "A":
        rec = "Low noise pool. Individual scores reliable after ~10 observations."
    elif grade == "B":
        rec = "Moderate noise. Need 25+ observations per attestor for Z>0.8."
    elif grade == "C":
        rec = f"High noise. Need {int(4*k)}+ observations for Z>0.8. Consider pool-level scoring."
    else:
        rec = "Noise dominates. Individual scoring unreliable. Use population prior."
    
    return PoolAnalysis(
        n_attestors=len(profiles),
        n_observations_each=len(profiles[0].scores) if profiles else 0,
        grand_mean=round(grand_mean, 4),
        within_variance=round(within_var, 6),
        between_variance=round(between_var, 6),
        k_parameter=round(k, 4),
        z_at_n={str(n): round(z, 4) for n, z in z_values.items()},
        noise_grade=grade,
        recommendation=rec
    )


def demo():
    """Demo with synthetic attestor pool."""
    random.seed(42)
    
    # 6 attestors with different true qualities, each measured 10 times
    true_qualities = {
        "precise_alice": (0.85, 0.03),    # High quality, low noise
        "noisy_bob": (0.80, 0.15),         # Good quality, high noise
        "biased_carol": (0.60, 0.05),      # Low quality, low noise
        "consistent_dave": (0.75, 0.02),   # Medium quality, very low noise
        "erratic_eve": (0.70, 0.20),       # Medium quality, very high noise
        "sybil_frank": (0.61, 0.05),       # Copies carol's pattern (sybil)
    }
    
    profiles = []
    for name, (quality, noise) in true_qualities.items():
        scores = [max(0, min(1, random.gauss(quality, noise))) for _ in range(10)]
        profiles.append(AttestorProfile(name=name, scores=scores))
    
    result = analyze_pool(profiles)
    
    print("=" * 65)
    print("ATTESTATION NOISE FLOOR ANALYSIS (Bühlmann)")
    print("=" * 65)
    print(f"Attestors: {result.n_attestors}, Observations each: {result.n_observations_each}")
    print(f"Grand mean: {result.grand_mean}")
    print()
    
    print(f"σ²(within)  = {result.within_variance:.6f}  (measurement noise)")
    print(f"σ²(between) = {result.between_variance:.6f}  (real quality differences)")
    print(f"k = within/between = {result.k_parameter:.4f}")
    print(f"Noise grade: {result.noise_grade}")
    print()
    
    print("Credibility Z at observation count n:")
    print(f"  {'n':>5}  {'Z':>6}  {'Interpretation'}")
    print(f"  {'-'*5}  {'-'*6}  {'-'*30}")
    for n_str, z in result.z_at_n.items():
        n = int(n_str)
        interp = "population prior dominates" if z < 0.3 else \
                 "blended" if z < 0.7 else "individual dominates"
        print(f"  {n:>5}  {z:>6.4f}  {interp}")
    
    print()
    print(f"Recommendation: {result.recommendation}")
    
    print()
    print("Per-attestor noise:")
    for p in profiles:
        print(f"  {p.name:<20} mean={p.mean:.3f}  σ²={p.within_var:.6f}  "
              f"{'⚠️ HIGH' if p.within_var > 0.02 else '✓'}")
    
    # Sybil detection: carol and frank have similar means + similar low noise
    carol = [p for p in profiles if p.name == "biased_carol"][0]
    frank = [p for p in profiles if p.name == "sybil_frank"][0]
    mean_diff = abs(carol.mean - frank.mean)
    print(f"\n⚠️  Sybil check: carol/frank mean diff = {mean_diff:.4f}, "
          f"both low-noise — suspicious similarity")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bühlmann noise floor estimator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
