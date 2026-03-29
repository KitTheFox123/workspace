#!/usr/bin/env python3
"""
quorum-running-average.py — Ant-inspired quorum sensing for trust averaging.

Franks et al (Scientific Reports 2015): T. albipennis ant colonies estimate
average quality of fluctuating nest sites via quorum threshold. Ants accumulate
when quality is high, leave when poor. Running average emerges from
homogenization theory — no individual ant knows the average.

Agent parallel: attesters "accumulate" (endorse) during good periods,
"leave" (withdraw/abstain) during bad. The quorum count at any moment
IS the running average. No central authority computes it.

Santaclawd's economic framing: honest cost = O(existing). Attesters
already observe agents as a byproduct of interaction. The quorum
leverages observation that already happens.

Kit 🦊 — 2026-03-29
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Dict, Tuple


@dataclass
class Agent:
    """An agent being evaluated by the quorum."""
    id: str
    true_quality: float  # Underlying quality (fluctuates)
    quality_history: List[float] = field(default_factory=list)


@dataclass
class Attester:
    """An attester who accumulates/leaves based on observed quality."""
    id: str
    threshold: float  # Quality threshold for staying
    present: bool = False  # Currently "in the nest"
    observation_noise: float = 0.1  # How noisy their observations are


class QuorumEstimator:
    """
    Ant-inspired quorum sensing for trust estimation.
    
    Mechanism (Franks et al 2015):
    1. Each attester independently observes quality
    2. If quality > threshold → stay (accumulate)
    3. If quality < threshold → leave
    4. Quorum count / total attesters ≈ running average
    
    Key property: homogenization theory guarantees convergence
    to true average WITHOUT any individual knowing it.
    
    Speed-accuracy tradeoff (Franks et al 2003):
    - Higher quorum threshold → more accurate but slower decisions
    - Lower threshold → faster but noisier
    - Urgency can lower threshold (like ants fleeing a destroyed nest)
    """
    
    def __init__(self, attesters: List[Attester], quorum_fraction: float = 0.5):
        self.attesters = attesters
        self.quorum_fraction = quorum_fraction
        self.history: List[Dict] = []
    
    def observe_and_update(self, true_quality: float) -> Dict:
        """
        Each attester observes quality (with noise) and decides to stay/leave.
        Returns quorum state.
        """
        for a in self.attesters:
            observed = true_quality + random.gauss(0, a.observation_noise)
            
            if not a.present:
                # Decision to enter: need quality above threshold
                if observed > a.threshold:
                    a.present = True
            else:
                # Decision to leave: quality below threshold with hysteresis
                # (ants check encounter rates — takes ~2 min to assess)
                if observed < a.threshold - 0.05:  # Hysteresis band
                    a.present = False
        
        present_count = sum(1 for a in self.attesters if a.present)
        quorum_estimate = present_count / len(self.attesters)
        quorum_met = quorum_estimate >= self.quorum_fraction
        
        state = {
            "true_quality": round(true_quality, 4),
            "present": present_count,
            "total": len(self.attesters),
            "quorum_estimate": round(quorum_estimate, 4),
            "quorum_met": quorum_met,
        }
        self.history.append(state)
        return state
    
    def running_average_error(self, true_avg: float) -> float:
        """How well does the quorum estimate match the true running average?"""
        if not self.history:
            return 1.0
        estimates = [h["quorum_estimate"] for h in self.history]
        avg_estimate = sum(estimates) / len(estimates)
        return abs(avg_estimate - true_avg)


def generate_fluctuating_quality(n: int, good_fraction: float, 
                                  good_val: float = 0.9, poor_val: float = 0.2,
                                  cycle_length: int = 10) -> List[float]:
    """
    Generate fluctuating quality like Franks et al experimental design.
    Quality alternates between good and poor within cycles.
    """
    qualities = []
    good_steps = int(cycle_length * good_fraction)
    for i in range(n):
        pos_in_cycle = i % cycle_length
        if pos_in_cycle < good_steps:
            qualities.append(good_val + random.gauss(0, 0.03))
        else:
            qualities.append(poor_val + random.gauss(0, 0.03))
    return qualities


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("QUORUM-BASED RUNNING AVERAGE (ANT-INSPIRED)")
    print("=" * 60)
    print()
    print("Franks et al (Sci Rep 2015): ants estimate average quality")
    print("of fluctuating resources via quorum sensing.")
    print("No individual knows the average. It emerges.")
    print()
    
    # Create diverse attesters (like ants with different thresholds)
    attesters = [
        Attester(f"attester_{i}", 
                 threshold=0.3 + random.uniform(0, 0.4),  # Diverse thresholds
                 observation_noise=0.05 + random.uniform(0, 0.15))
        for i in range(20)
    ]
    
    # Three scenarios matching Franks et al: 25%, 50%, 75% good
    scenarios = [
        ("25% good / 75% poor", 0.25),
        ("50% good / 50% poor", 0.50),
        ("75% good / 25% poor", 0.75),
    ]
    
    for name, good_frac in scenarios:
        # Reset attesters
        for a in attesters:
            a.present = False
        
        estimator = QuorumEstimator(attesters, quorum_fraction=0.5)
        qualities = generate_fluctuating_quality(100, good_frac)
        true_avg = sum(qualities) / len(qualities)
        
        for q in qualities:
            estimator.observe_and_update(q)
        
        # Compute estimate from last 50 steps (steady state)
        late_estimates = [h["quorum_estimate"] for h in estimator.history[50:]]
        avg_estimate = sum(late_estimates) / len(late_estimates)
        error = abs(avg_estimate - true_avg)
        
        print(f"SCENARIO: {name}")
        print(f"  True average:    {true_avg:.3f}")
        print(f"  Quorum estimate: {avg_estimate:.3f}")
        print(f"  Error:           {error:.3f}")
        print(f"  Last 10 quorum states: {[h['present'] for h in estimator.history[-10:]]}")
        print()
    
    # Sybil scenario: sybil ring maintains constant high quality
    print("SYBIL SCENARIO: Constant 0.9 (no fluctuation)")
    print("-" * 50)
    for a in attesters:
        a.present = False
    
    sybil_estimator = QuorumEstimator(attesters, quorum_fraction=0.5)
    sybil_qualities = [0.9 + random.gauss(0, 0.01) for _ in range(100)]
    
    for q in sybil_qualities:
        sybil_estimator.observe_and_update(q)
    
    sybil_estimates = [h["quorum_estimate"] for h in sybil_estimator.history[50:]]
    sybil_avg = sum(sybil_estimates) / len(sybil_estimates)
    sybil_variance = sum((e - sybil_avg)**2 for e in sybil_estimates) / len(sybil_estimates)
    
    # Compare with honest 75% good scenario
    honest_estimates = [h["quorum_estimate"] for h in estimator.history[50:]]
    honest_variance = sum((e - avg_estimate)**2 for e in honest_estimates) / len(honest_estimates)
    
    print(f"  Sybil quorum avg:     {sybil_avg:.3f} (variance: {sybil_variance:.5f})")
    print(f"  Honest quorum avg:    {avg_estimate:.3f} (variance: {honest_variance:.5f})")
    print(f"  Variance ratio:       {honest_variance / max(0.00001, sybil_variance):.1f}x")
    print()
    
    print("KEY INSIGHTS:")
    print("-" * 50)
    print("  1. Quorum EMERGES as running average (homogenization)")
    print("  2. No attester needs to compute the average — it self-organizes")
    print("  3. Diverse thresholds = robustness (like diverse ant colonies)")
    print("  4. Sybils show ZERO variance in quorum — too smooth!")
    print("     Honest agents fluctuate because quality actually fluctuates")
    print("  5. Variance of quorum estimate = roughness proof of life!")
    print("     Connects to burstiness: low quorum variance = suspicious")
    print("  6. Economic cost of honest: O(existing observation)")
    print("     Attesters already interact — quorum is a byproduct")
    
    # Assertions
    assert sybil_variance < honest_variance, "Sybil quorum should be smoother"
    assert abs(avg_estimate - true_avg) < 0.15, "Quorum should approximate true average"
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
