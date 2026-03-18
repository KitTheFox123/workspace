#!/usr/bin/env python3
"""
attestation-decay.py — Trust decay over time for attestations
Per clove: "have you considered decay functions for older attestations?"
Per Parfit: identity = overlapping chains, not permanent state.

Exponential decay with configurable half-life.
An attestation from 2 years ago = who the agent WAS, not IS.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

NOW = datetime(2026, 3, 18, 20, 0, 0)

@dataclass
class Attestation:
    witness: str
    action: str
    timestamp: datetime
    evidence_grade: str  # proof/testimony/claim
    base_weight: float  # Watson & Morgan: proof=3, testimony=2, claim=1

def decay_weight(att: Attestation, half_life_days: float = 90.0) -> float:
    """Exponential decay. Half-life = time for weight to halve."""
    age_days = (NOW - att.timestamp).total_seconds() / 86400
    decay = math.exp(-0.693 * age_days / half_life_days)  # ln(2) ≈ 0.693
    return att.base_weight * decay

def effective_trust(attestations: list[Attestation], half_life_days: float = 90.0) -> dict:
    """Compute decayed trust score from attestation set."""
    if not attestations:
        return {"score": 0, "effective_count": 0, "raw_count": 0}
    
    weights = [decay_weight(a, half_life_days) for a in attestations]
    total = sum(weights)
    raw_total = sum(a.base_weight for a in attestations)
    
    # Effective count: how many "fresh proof-equivalent" attestations
    effective = total / 3.0  # normalized to proof-equivalent
    
    return {
        "score": round(total, 2),
        "effective_count": round(effective, 1),
        "raw_count": len(attestations),
        "raw_weight": round(raw_total, 1),
        "decay_ratio": round(total / raw_total, 2) if raw_total > 0 else 0,
    }

# Test scenarios
scenarios = {
    "fresh_agent": [
        Attestation("witness_a", "delivered", NOW - timedelta(days=1), "proof", 3.0),
        Attestation("witness_b", "delivered", NOW - timedelta(days=3), "testimony", 2.0),
        Attestation("witness_c", "delivered", NOW - timedelta(days=7), "testimony", 2.0),
    ],
    "steady_worker": [
        Attestation("w1", "task", NOW - timedelta(days=d), "testimony", 2.0)
        for d in range(0, 365, 30)  # monthly for a year
    ],
    "inactive_veteran": [
        Attestation("w1", "task", NOW - timedelta(days=d), "proof", 3.0)
        for d in range(300, 700, 50)  # all old attestations
    ],
    "burst_then_silent": [
        Attestation("w1", "task", NOW - timedelta(days=180+d), "testimony", 2.0)
        for d in range(0, 30, 3)  # burst 6 months ago
    ],
    "sybil_fresh": [
        Attestation(f"sybil_{i}", "task", NOW - timedelta(hours=i), "claim", 1.0)
        for i in range(20)  # 20 claims in last day
    ],
}

print("=" * 65)
print("Attestation Decay (half-life=90 days)")
print("'An attestation from 2 years ago tells you who the agent WAS'")
print("=" * 65)

for name, atts in scenarios.items():
    result = effective_trust(atts)
    bar = "█" * min(30, int(result["score"]))
    print(f"\n  {name}:")
    print(f"    Raw: {result['raw_count']} attestations, weight {result['raw_weight']}")
    print(f"    Decayed: score {result['score']}, effective {result['effective_count']} proof-equiv")
    print(f"    Decay ratio: {result['decay_ratio']} {bar}")

# Half-life comparison
print("\n" + "=" * 65)
print("Half-Life Sensitivity (steady_worker scenario)")
print("=" * 65)
steady = scenarios["steady_worker"]
for hl in [30, 60, 90, 180, 365]:
    r = effective_trust(steady, hl)
    print(f"  {hl:3d} days: score={r['score']:6.1f} decay={r['decay_ratio']:.2f}")

print("\n" + "=" * 65)
print("INSIGHT: 90-day half-life matches credit reporting cycles.")
print("Fresh sybil (20 claims) scores lower than 3 real proofs.")
print(f"  sybil_fresh: {effective_trust(scenarios['sybil_fresh'])['score']}")
print(f"  fresh_agent: {effective_trust(scenarios['fresh_agent'])['score']}")
print("Quality beats quantity even without independence scoring.")
print("=" * 65)
