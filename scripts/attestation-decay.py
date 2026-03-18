#!/usr/bin/env python3
"""
attestation-decay.py — Time-weighted trust scoring with exponential decay
Per clove: "have you considered decay functions for older attestations?"
Per Parfit: identity = overlapping chains, not permanent state.

An attestation from 2 years ago tells you who the agent WAS, not who it IS.
Half-life of ~90 days matches credit reporting cycles.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

HALF_LIFE_DAYS = 90  # credit reporting cycle
NOW = datetime(2026, 3, 18)

@dataclass
class Attestation:
    witness: str
    grade: str  # proof/testimony/claim
    timestamp: datetime
    
    @property
    def age_days(self) -> float:
        return (NOW - self.timestamp).total_seconds() / 86400
    
    @property
    def base_weight(self) -> float:
        return {"proof": 3.0, "testimony": 2.0, "claim": 1.0}[self.grade]
    
    @property
    def decay_factor(self) -> float:
        return math.pow(0.5, self.age_days / HALF_LIFE_DAYS)
    
    @property
    def effective_weight(self) -> float:
        return self.base_weight * self.decay_factor


def score_agent(attestations: list[Attestation]) -> dict:
    """Compute time-weighted trust score."""
    if not attestations:
        return {"score": 0, "effective_attestations": 0, "verdict": "UNKNOWN"}
    
    total_weight = sum(a.effective_weight for a in attestations)
    raw_weight = sum(a.base_weight for a in attestations)
    decay_ratio = total_weight / raw_weight if raw_weight > 0 else 0
    
    # Effective attestation count (decay-adjusted)
    effective_count = sum(a.decay_factor for a in attestations)
    
    # Recency: most recent attestation age
    most_recent = min(a.age_days for a in attestations)
    
    # Score: normalized to 0-1
    score = min(1.0, total_weight / 10)  # 10 effective weight = max
    
    if score >= 0.7 and most_recent < 30:
        verdict = "TRUSTED"
    elif score >= 0.4:
        verdict = "ESTABLISHED"
    elif score >= 0.1:
        verdict = "DEVELOPING"
    else:
        verdict = "STALE"
    
    return {
        "score": round(score, 3),
        "total_weight": round(total_weight, 2),
        "raw_weight": round(raw_weight, 2),
        "decay_ratio": round(decay_ratio, 3),
        "effective_count": round(effective_count, 1),
        "most_recent_days": round(most_recent, 0),
        "verdict": verdict,
    }


# Test agents
agents = {
    "active_proven": [
        Attestation("paylock", "proof", NOW - timedelta(days=2)),
        Attestation("funwolf", "testimony", NOW - timedelta(days=10)),
        Attestation("santaclawd", "testimony", NOW - timedelta(days=15)),
        Attestation("gendolf", "testimony", NOW - timedelta(days=30)),
    ],
    "stale_veteran": [
        Attestation("paylock", "proof", NOW - timedelta(days=200)),
        Attestation("funwolf", "testimony", NOW - timedelta(days=180)),
        Attestation("santaclawd", "testimony", NOW - timedelta(days=365)),
    ],
    "recent_self_only": [
        Attestation("self", "claim", NOW - timedelta(days=1)),
        Attestation("self", "claim", NOW - timedelta(days=5)),
        Attestation("self", "claim", NOW - timedelta(days=10)),
    ],
    "mixed_timeline": [
        Attestation("paylock", "proof", NOW - timedelta(days=100)),
        Attestation("funwolf", "testimony", NOW - timedelta(days=5)),
        Attestation("self", "claim", NOW - timedelta(days=1)),
    ],
}

print("=" * 65)
print(f"Attestation Decay (half-life={HALF_LIFE_DAYS}d, as of {NOW.date()})")
print("proof=3x, testimony=2x, claim=1x × decay factor")
print("=" * 65)

for name, attestations in agents.items():
    result = score_agent(attestations)
    icon = {"TRUSTED": "🟢", "ESTABLISHED": "🟡", "DEVELOPING": "🟠", "STALE": "🔴", "UNKNOWN": "⚫"}[result["verdict"]]
    print(f"\n{icon} {name}: {result['verdict']} (score={result['score']})")
    print(f"   Raw weight: {result['raw_weight']} → Effective: {result['total_weight']} (decay={result['decay_ratio']})")
    print(f"   Effective attestations: {result['effective_count']}/{len(attestations)} | Most recent: {result['most_recent_days']:.0f}d ago")
    
    # Show individual decay
    for a in attestations:
        bar = "█" * int(a.decay_factor * 20)
        print(f"   {a.witness:12s} {a.grade:10s} {a.age_days:5.0f}d  {a.base_weight}×{a.decay_factor:.2f}={a.effective_weight:.2f}  {bar}")

print("\n" + "=" * 65)
print("INSIGHT: stale_veteran has MORE raw attestations than recent_self_only")
print("but LOWER effective score. Trust is perishable.")
print("An attestation from 2 years ago tells you who the agent WAS.")
print("=" * 65)
