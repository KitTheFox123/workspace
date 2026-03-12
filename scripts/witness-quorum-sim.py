#!/usr/bin/env python3
"""
witness-quorum-sim.py — Witness network quorum simulation for agent cert logs.

Based on:
- ArmoredWitness (transparency.dev, 15 deployed devices)
- Condorcet Jury Theorem (1785): majority accuracy improves with group size
- Shannon information: dissent = high surprise = high info content

Key insight: 1 witness proves append-only. N-of-M proves global consistency.
The minority report is more informative per bit than consensus.

Usage: python3 witness-quorum-sim.py
"""

import math
import random
from dataclasses import dataclass


@dataclass
class Witness:
    id: str
    accuracy: float  # probability of correct assessment
    byzantine: bool = False
    offline: bool = False

    def cosign(self, checkpoint_valid: bool) -> bool | None:
        """Cosign a checkpoint. Returns True/False/None(offline)."""
        if self.offline:
            return None
        if self.byzantine:
            return not checkpoint_valid  # always wrong
        return random.random() < self.accuracy if checkpoint_valid else random.random() > self.accuracy


def condorcet_probability(n: int, p: float) -> float:
    """Probability that majority is correct (Condorcet 1785)."""
    majority = n // 2 + 1
    prob = 0.0
    for k in range(majority, n + 1):
        prob += math.comb(n, k) * (p ** k) * ((1 - p) ** (n - k))
    return prob


def shannon_surprise(p: float) -> float:
    """Information content of an event with probability p."""
    if p <= 0 or p >= 1:
        return 0.0
    return -math.log2(p)


def simulate_quorum(witnesses: list[Witness], checkpoint_valid: bool,
                    quorum_threshold: int) -> dict:
    """Simulate witness cosigning round."""
    votes = {}
    for w in witnesses:
        v = w.cosign(checkpoint_valid)
        if v is not None:
            votes[w.id] = v

    agree = sum(1 for v in votes.values() if v)
    disagree = sum(1 for v in votes.values() if not v)
    offline = len(witnesses) - len(votes)

    quorum_met = agree >= quorum_threshold
    has_dissent = disagree > 0

    # Information content of dissent
    if len(votes) > 0:
        dissent_rate = disagree / len(votes)
        dissent_info = shannon_surprise(dissent_rate) if dissent_rate > 0 else 0
    else:
        dissent_rate = 0
        dissent_info = 0

    return {
        "agree": agree,
        "disagree": disagree,
        "offline": offline,
        "quorum_met": quorum_met,
        "has_dissent": has_dissent,
        "dissent_info_bits": round(dissent_info, 2),
        "verdict": "COSIGNED" if quorum_met and not has_dissent
                   else "COSIGNED_WITH_DISSENT" if quorum_met and has_dissent
                   else "REJECTED"
    }


def demo():
    print("=" * 60)
    print("Witness Network Quorum Simulation")
    print("ArmoredWitness + Condorcet + Shannon")
    print("=" * 60)

    # Condorcet analysis
    print("\n--- Condorcet Jury Theorem ---")
    print(f"{'Witnesses':>10} {'p=0.7':>8} {'p=0.8':>8} {'p=0.9':>8}")
    for n in [3, 5, 7, 9, 15]:
        probs = [condorcet_probability(n, p) for p in [0.7, 0.8, 0.9]]
        print(f"{n:>10} {probs[0]:>8.4f} {probs[1]:>8.4f} {probs[2]:>8.4f}")
    print("  ↑ More witnesses = higher majority accuracy (if p > 0.5)")

    # Shannon: dissent is informative
    print("\n--- Shannon Information Content ---")
    for rate in [0.0, 0.1, 0.2, 0.33, 0.5]:
        info = shannon_surprise(rate) if rate > 0 else 0
        label = "consensus" if rate == 0 else f"{rate:.0%} dissent"
        print(f"  {label:>15}: {info:.2f} bits")
    print("  ↑ Rare dissent = more informative per bit")

    # Scenario simulations
    scenarios = [
        {
            "name": "Healthy 3-of-5 (f=1)",
            "witnesses": [Witness(f"w{i}", 0.9) for i in range(5)],
            "quorum": 3,
            "valid": True,
        },
        {
            "name": "1 Byzantine, 1 offline (f=1 each)",
            "witnesses": [
                Witness("w0", 0.9), Witness("w1", 0.9), Witness("w2", 0.9),
                Witness("w3", 0.9, byzantine=True),
                Witness("w4", 0.9, offline=True),
            ],
            "quorum": 3,
            "valid": True,
        },
        {
            "name": "ArmoredWitness scale (15 devices)",
            "witnesses": [Witness(f"aw{i}", 0.85) for i in range(15)],
            "quorum": 8,  # majority
            "valid": True,
        },
        {
            "name": "Split-view attack (3 see different state)",
            "witnesses": [
                Witness("w0", 0.9), Witness("w1", 0.9),
                Witness("w2", 0.9, byzantine=True),
                Witness("w3", 0.9, byzantine=True),
                Witness("w4", 0.9, byzantine=True),
            ],
            "quorum": 3,
            "valid": True,
        },
    ]

    random.seed(42)
    print("\n--- Scenario Simulations ---")
    for s in scenarios:
        print(f"\n  {s['name']}")
        print(f"  Quorum: {s['quorum']}-of-{len(s['witnesses'])}")
        result = simulate_quorum(s["witnesses"], s["valid"], s["quorum"])
        print(f"  Agree: {result['agree']}, Disagree: {result['disagree']}, Offline: {result['offline']}")
        print(f"  Verdict: {result['verdict']}")
        if result['has_dissent']:
            print(f"  Dissent info: {result['dissent_info_bits']} bits (INVESTIGATE)")

    # Summary
    print(f"\n{'=' * 60}")
    print("KEY INSIGHTS:")
    print("  1 witness = append-only proof (ArmoredWitness model)")
    print("  3 witnesses = 1 dissent without false alarm")
    print("  4 witnesses = tolerate 1 byzantine + 1 offline (3f+1)")
    print("  Dissent = high information → log it, don't suppress it")
    print("  Condorcet: 15 witnesses at p=0.8 → 99.7% majority accuracy")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
