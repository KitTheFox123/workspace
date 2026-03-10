#!/usr/bin/env python3
"""attestation-noise-floor.py — Estimate Bühlmann k for attestor pools.

k = E[s²(θ)] / Var[μ(θ)]
  = expected within-attestor variance / between-attestor variance

High k → noisy attestors, need more observations for credibility.
Low k → attestors are consistent, small n gives useful signal.

Z = n/(n+k): credibility weight. This script estimates k from
attestation history and tells you how many observations each
attestor needs before their individual score is trustworthy.

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
    name: str
    k_estimate: float          # Within/between variance ratio
    n_observations: int        # How many attestations observed
    z_credibility: float       # Z = n/(n+k)
    n_for_half: int            # n needed for Z=0.5
    n_for_ninety: int          # n needed for Z=0.9
    noise_grade: str           # A=low noise, F=high noise
    within_variance: float
    between_variance: float


def estimate_k(attestation_history: Dict[str, List[float]]) -> Dict[str, AttestorProfile]:
    """Estimate k for each attestor from their attestation scores.
    
    attestation_history: {attestor_name: [score1, score2, ...]}
    Scores are 0-1 accuracy on seed variables.
    """
    profiles = {}
    
    # Grand mean across all attestors
    all_scores = [s for scores in attestation_history.values() for s in scores]
    grand_mean = sum(all_scores) / len(all_scores) if all_scores else 0.5
    
    # Between-attestor variance: variance of attestor means
    attestor_means = {}
    for name, scores in attestation_history.items():
        if scores:
            attestor_means[name] = sum(scores) / len(scores)
    
    mean_of_means = sum(attestor_means.values()) / len(attestor_means) if attestor_means else 0.5
    between_var = sum((m - mean_of_means)**2 for m in attestor_means.values()) / max(len(attestor_means) - 1, 1)
    
    for name, scores in attestation_history.items():
        n = len(scores)
        if n < 2:
            # Can't estimate variance with <2 observations
            profiles[name] = AttestorProfile(
                name=name, k_estimate=float('inf'), n_observations=n,
                z_credibility=0.0, n_for_half=999, n_for_ninety=999,
                noise_grade="?", within_variance=0.0, between_variance=between_var
            )
            continue
        
        # Within-attestor variance
        mean_score = sum(scores) / n
        within_var = sum((s - mean_score)**2 for s in scores) / (n - 1)
        
        # k = within / between (avoid division by zero)
        if between_var > 0:
            k = within_var / between_var
        else:
            k = float('inf')  # All attestors identical = can't distinguish
        
        z = n / (n + k) if k != float('inf') else 0.0
        n_half = max(1, round(k))           # Z=0.5 when n=k
        n_ninety = max(1, round(9 * k))     # Z=0.9 when n=9k
        
        # Grade by k
        if k < 2: grade = "A"
        elif k < 5: grade = "B"
        elif k < 15: grade = "C"
        elif k < 50: grade = "D"
        else: grade = "F"
        
        profiles[name] = AttestorProfile(
            name=name, k_estimate=round(k, 3), n_observations=n,
            z_credibility=round(z, 4), n_for_half=n_half, n_for_ninety=n_ninety,
            noise_grade=grade, within_variance=round(within_var, 6),
            between_variance=round(between_var, 6)
        )
    
    return profiles


def demo():
    """Demo with synthetic attestor data."""
    random.seed(42)
    
    # Simulate 6 attestors with different noise profiles
    history = {
        "precise_alice": [0.85 + random.gauss(0, 0.02) for _ in range(30)],
        "noisy_bob": [0.80 + random.gauss(0, 0.15) for _ in range(30)],
        "biased_carol": [0.70 + random.gauss(0, 0.03) for _ in range(30)],
        "newcomer_dave": [0.82 + random.gauss(0, 0.05) for _ in range(5)],
        "sybil_echo": [0.70 + random.gauss(0, 0.03) for _ in range(30)],  # Copies carol's pattern
        "veteran_fox": [0.88 + random.gauss(0, 0.04) for _ in range(100)],
    }
    
    # Clamp to [0,1]
    for name in history:
        history[name] = [max(0.0, min(1.0, s)) for s in history[name]]
    
    profiles = estimate_k(history)
    
    print("=" * 72)
    print("BÜHLMANN k ESTIMATION — ATTESTOR NOISE FLOOR")
    print("=" * 72)
    print(f"{'Attestor':<18} {'k':>7} {'n':>5} {'Z':>6} {'n@0.5':>6} {'n@0.9':>6} {'Grade':>5}")
    print("-" * 56)
    
    for name in sorted(profiles, key=lambda n: profiles[n].k_estimate):
        p = profiles[name]
        k_str = f"{p.k_estimate:.1f}" if p.k_estimate != float('inf') else "  inf"
        print(f"{p.name:<18} {k_str:>7} {p.n_observations:>5} {p.z_credibility:>6.3f} "
              f"{p.n_for_half:>6} {p.n_for_ninety:>6} {p.noise_grade:>5}")
    
    print()
    print("Interpretation:")
    print("  k < 2:  Low noise — few observations give useful signal (Grade A)")
    print("  k > 15: High noise — need many observations before trusting (Grade D+)")
    print("  Z = n/(n+k): current credibility weight")
    print("  n@0.5: observations needed for 50% individual weight")
    print("  n@0.9: observations needed for 90% individual weight")
    
    # Sybil detection
    print()
    carol = profiles.get("biased_carol")
    echo = profiles.get("sybil_echo")
    if carol and echo:
        k_diff = abs(carol.k_estimate - echo.k_estimate)
        mean_diff = abs(sum(history["biased_carol"])/len(history["biased_carol"]) - 
                       sum(history["sybil_echo"])/len(history["sybil_echo"]))
        print(f"⚠️  Sybil check: biased_carol vs sybil_echo")
        print(f"    k difference: {k_diff:.3f}, mean difference: {mean_diff:.4f}")
        if k_diff < 0.5 and mean_diff < 0.05:
            print("    SUSPICIOUS: Similar noise profiles + similar means")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
