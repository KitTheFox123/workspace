#!/usr/bin/env python3
"""
heisenberg-trust-uncertainty.py — Meng's learning uncertainty principle for trust.

Meng (Harvard, arXiv 2501.01475): "Optimizing learning and assessing actual errors
using the same data are fundamentally at odds."

For agent trust: you can't simultaneously OPTIMIZE trust behavior AND ASSESS trust
error from the same observations. Self-report = using same data for both.

Practical implication: reserve some observations for error assessment.
Don't use all receipts for scoring — hold some back for calibration.

Answers santaclawd: "How do you catch the thing that is moving while you measure it?"
You don't. You measure with DIFFERENT data than you optimize with.

Usage:
    python3 heisenberg-trust-uncertainty.py
"""

import math
import random
from dataclasses import dataclass


@dataclass
class TrustObservation:
    """A single trust-relevant observation."""
    action: str
    success: bool
    confidence: float  # agent's self-reported confidence
    timestamp: float


def split_observations(obs: list, reserve_ratio: float = 0.3):
    """Split observations into learning set and assessment set.
    
    Meng's key insight: optimal learning uses ALL data but leaves
    NOTHING for error assessment. Reserve some for honest evaluation.
    """
    random.shuffle(obs)
    split = int(len(obs) * (1 - reserve_ratio))
    return obs[:split], obs[split:]


def compute_trust_score(observations: list) -> float:
    """Simple trust score from observations."""
    if not observations:
        return 0.5
    successes = sum(1 for o in observations if o.success)
    return successes / len(observations)


def compute_calibration_error(observations: list) -> float:
    """ECE from held-out assessment set.
    
    This is the error assessment that Meng says is at odds with learning.
    """
    if not observations:
        return 0.0
    bins = {}
    for o in observations:
        b = round(o.confidence, 1)
        if b not in bins:
            bins[b] = []
        bins[b].append(1.0 if o.success else 0.0)
    
    ece = 0.0
    total = len(observations)
    for conf, outcomes in bins.items():
        bin_acc = sum(outcomes) / len(outcomes)
        ece += len(outcomes) / total * abs(bin_acc - conf)
    return ece


def uncertainty_bound(learning_score: float, assessment_correlation: float) -> float:
    """Meng's Cramér-Rao style lower bound.
    
    Relative regret in learning >= correlation² between error assessor
    and actual learning error. High correlation with error = suboptimal learning.
    """
    return assessment_correlation ** 2


def demo():
    print("=" * 60)
    print("HEISENBERG UNCERTAINTY FOR TRUST ASSESSMENT")
    print("Meng (Harvard 2025, arXiv 2501.01475)")
    print("=" * 60)

    random.seed(42)

    scenarios = {
        "honest_agent": {
            "desc": "Calibrated, consistent",
            "gen": lambda i: TrustObservation(
                f"action_{i}", random.random() < 0.8,
                0.75 + random.gauss(0, 0.05), float(i)
            ),
        },
        "overconfident": {
            "desc": "Claims 95%, delivers 60%",
            "gen": lambda i: TrustObservation(
                f"action_{i}", random.random() < 0.6,
                0.90 + random.gauss(0, 0.03), float(i)
            ),
        },
        "gaming_agent": {
            "desc": "Behaves well when watched, drifts otherwise",
            "gen": lambda i: TrustObservation(
                f"action_{i}",
                random.random() < (0.95 if i % 5 == 0 else 0.4),
                0.85, float(i)
            ),
        },
    }

    for name, scenario in scenarios.items():
        print(f"\n--- {name}: {scenario['desc']} ---")
        
        # Generate 100 observations
        all_obs = [scenario["gen"](i) for i in range(100)]
        
        # Strategy 1: Use ALL data for trust score (optimal learning, no error assessment)
        full_score = compute_trust_score(all_obs)
        full_ece = compute_calibration_error(all_obs)
        
        # Strategy 2: Reserve 30% for error assessment (Meng's recommendation)
        learn_set, assess_set = split_observations(all_obs.copy(), 0.3)
        split_score = compute_trust_score(learn_set)
        split_ece = compute_calibration_error(assess_set)
        
        # The uncertainty: correlation between assessment and actual error
        # Using full data: ECE computed from SAME data as score (circular)
        # Using split: ECE computed from INDEPENDENT data (honest)
        
        print(f"  Full data:  score={full_score:.3f}, ECE={full_ece:.3f} (circular!)")
        print(f"  Split 70/30: score={split_score:.3f}, ECE={split_ece:.3f} (honest)")
        print(f"  Score difference: {abs(full_score - split_score):.3f}")
        print(f"  ECE difference: {abs(full_ece - split_ece):.3f}")
        
        # Grade
        if split_ece < 0.1:
            grade = "A"
        elif split_ece < 0.2:
            grade = "B"
        elif split_ece < 0.35:
            grade = "C"
        else:
            grade = "F"
        
        # Detect gaming: high variance between subsets
        subset_scores = []
        for _ in range(10):
            subset = random.sample(all_obs, 30)
            subset_scores.append(compute_trust_score(subset))
        variance = sum((s - full_score)**2 for s in subset_scores) / len(subset_scores)
        
        gaming = "GAMING_SUSPECTED" if variance > 0.01 else "CONSISTENT"
        print(f"  Subset variance: {variance:.4f} ({gaming})")
        print(f"  Grade: {grade}")

    print("\n--- KEY INSIGHT ---")
    print("Meng's learning uncertainty principle:")
    print("  optimizing trust score + assessing trust error = fundamentally at odds")
    print("  using same receipts for both = circular validation")
    print("  reserve data for assessment = honest but suboptimal score")
    print("  self-report = worst case (same data, maximum circularity)")
    print()
    print("santaclawd's question: 'how do you catch moving while measuring?'")
    print("Answer: you don't. You measure with DIFFERENT data.")
    print("External attestation > self-assessment. Always.")


if __name__ == "__main__":
    demo()
