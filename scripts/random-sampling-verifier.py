#!/usr/bin/env python3
"""
random-sampling-verifier.py — Trust-minimized attestation verification via random sampling.

Inspired by cassian: "trust-minimized, not trustless" and Bhatt et al AFT 2025
(random sampling light clients for bridges).

Don't verify every heartbeat. Sample randomly. The THREAT of verification > verification itself.
Deterrence via probabilistic audit, not exhaustive check.
"""

import hashlib
import random
import math
from dataclasses import dataclass


@dataclass
class Heartbeat:
    agent_id: str
    period: int
    scope_hash: str
    action_count: int
    honest: bool  # ground truth for simulation


@dataclass 
class VerificationResult:
    period: int
    sampled: bool
    verified: bool = True
    cost: float = 0.0


class RandomSamplingVerifier:
    """
    Verify k-of-n attestations via random sampling.
    
    Key insight (Bhatt AFT 2025): probabilistic verification catches
    cheating with high probability at fraction of the cost.
    
    Detection probability: 1 - (1-p)^k where p = sampling rate, k = cheating periods
    After 10 cheating periods at 20% sample rate: 1-(0.8)^10 = 89.3% detection
    After 20: 98.8%. After 30: 99.7%.
    """
    
    def __init__(self, sample_rate: float = 0.2, verification_cost: float = 1.0):
        self.sample_rate = sample_rate
        self.verification_cost = verification_cost
        self.results: list[VerificationResult] = []
    
    def should_sample(self) -> bool:
        return random.random() < self.sample_rate
    
    def verify(self, heartbeat: Heartbeat) -> VerificationResult:
        sampled = self.should_sample()
        result = VerificationResult(
            period=heartbeat.period,
            sampled=sampled,
            verified=heartbeat.honest if sampled else True,  # unsampled assumed OK
            cost=self.verification_cost if sampled else 0.0
        )
        self.results.append(result)
        return result
    
    def detection_probability(self, cheating_periods: int) -> float:
        """Probability of catching at least one cheat in k periods."""
        return 1 - (1 - self.sample_rate) ** cheating_periods
    
    def expected_cost(self, total_periods: int) -> float:
        return total_periods * self.sample_rate * self.verification_cost
    
    def full_verification_cost(self, total_periods: int) -> float:
        return total_periods * self.verification_cost


def simulate(n_periods: int = 100, cheat_start: int = 30, cheat_end: int = 50,
             sample_rate: float = 0.2):
    """Simulate an agent that cheats during periods [cheat_start, cheat_end)."""
    
    verifier = RandomSamplingVerifier(sample_rate=sample_rate)
    
    heartbeats = []
    for i in range(n_periods):
        honest = not (cheat_start <= i < cheat_end)
        hb = Heartbeat(
            agent_id="agent_alpha",
            period=i,
            scope_hash=hashlib.sha256(f"scope_{i}".encode()).hexdigest()[:16],
            action_count=random.randint(1, 10) if honest else 0,
            honest=honest
        )
        heartbeats.append(hb)
    
    # Run verification
    first_detection = None
    total_cost = 0.0
    sampled_count = 0
    
    for hb in heartbeats:
        result = verifier.verify(hb)
        total_cost += result.cost
        if result.sampled:
            sampled_count += 1
        if result.sampled and not result.verified and first_detection is None:
            first_detection = hb.period
    
    cheating_periods = cheat_end - cheat_start
    detection_prob = verifier.detection_probability(cheating_periods)
    
    return {
        "total_periods": n_periods,
        "cheating_periods": cheating_periods,
        "sample_rate": sample_rate,
        "sampled_count": sampled_count,
        "first_detection": first_detection,
        "detected": first_detection is not None,
        "detection_probability": detection_prob,
        "verification_cost": total_cost,
        "full_cost": verifier.full_verification_cost(n_periods),
        "cost_savings": 1 - (total_cost / verifier.full_verification_cost(n_periods))
    }


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("RANDOM SAMPLING VERIFIER — Trust-Minimized Attestation")
    print("=" * 60)
    
    # Run multiple trials at different sample rates
    rates = [0.05, 0.10, 0.20, 0.30, 0.50]
    trials_per_rate = 100
    
    print(f"\n{'Rate':>6} | {'Detect%':>8} | {'Avg Detection':>14} | {'Cost Savings':>12} | Grade")
    print("-" * 65)
    
    for rate in rates:
        detections = 0
        detection_periods = []
        savings_sum = 0
        
        for _ in range(trials_per_rate):
            result = simulate(n_periods=100, cheat_start=30, cheat_end=50, sample_rate=rate)
            if result["detected"]:
                detections += 1
                detection_periods.append(result["first_detection"] - 30)  # periods after cheat start
            savings_sum += result["cost_savings"]
        
        detect_pct = detections / trials_per_rate * 100
        avg_detect = sum(detection_periods) / len(detection_periods) if detection_periods else float('inf')
        avg_savings = savings_sum / trials_per_rate * 100
        
        # Grade: balance detection vs cost
        if detect_pct >= 95 and avg_savings >= 50:
            grade = "A"
        elif detect_pct >= 80:
            grade = "B"
        elif detect_pct >= 60:
            grade = "C"
        else:
            grade = "F"
        
        print(f"{rate:>5.0%} | {detect_pct:>7.1f}% | {avg_detect:>10.1f} beats | {avg_savings:>10.1f}% | {grade}")
    
    # Theoretical detection curves
    print(f"\n{'─' * 60}")
    print("THEORETICAL: Detection probability vs cheating duration")
    print(f"{'Periods':>8} | {'5%':>6} | {'10%':>6} | {'20%':>6} | {'30%':>6}")
    print("-" * 45)
    for k in [1, 5, 10, 20, 30, 50]:
        probs = [1 - (1-r)**k for r in [0.05, 0.10, 0.20, 0.30]]
        print(f"{k:>8} | {probs[0]:>5.1%} | {probs[1]:>5.1%} | {probs[2]:>5.1%} | {probs[3]:>5.1%}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: The THREAT of verification > verification itself.")
    print("20% sample rate catches 20-period cheats 98.8% of the time")
    print("at 80% cost savings. Trust-minimized, not trustless. (cassian)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
