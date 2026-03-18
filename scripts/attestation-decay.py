#!/usr/bin/env python3
"""
attestation-decay.py — Evidence decay by grade
Per clove: older attestations should weight less.
Per Kit: proof doesn't decay, testimony and claims do.

Ebbinghaus forgetting curve: retention = e^(-t/S)
Grade determines decay rate: proof=∞, testimony=90d, claim=30d.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

NOW = datetime(2026, 3, 18, 16, 0)

@dataclass
class Attestation:
    grade: str  # proof / testimony / claim
    timestamp: datetime
    witness: str
    value: float = 1.0  # base evidence value
    
    @property
    def age_days(self) -> float:
        return (NOW - self.timestamp).total_seconds() / 86400

    def decayed_value(self) -> float:
        """Ebbinghaus decay by grade."""
        half_lives = {
            "proof": float('inf'),   # chain-anchored = permanent
            "testimony": 90.0,       # witness-signed = 90 day half-life
            "claim": 30.0,           # self-attested = 30 day half-life
        }
        hl = half_lives.get(self.grade, 30.0)
        if hl == float('inf'):
            return self.value
        # Exponential decay: v * e^(-λt), λ = ln(2)/half_life
        decay_rate = math.log(2) / hl
        return self.value * math.exp(-decay_rate * self.age_days)


def effective_trust(attestations: list[Attestation]) -> dict:
    """Compute effective trust from decayed attestations."""
    watson_morgan = {"claim": 1.0, "testimony": 2.0, "proof": 3.0}
    
    total_raw = sum(watson_morgan[a.grade] * a.value for a in attestations)
    total_decayed = sum(watson_morgan[a.grade] * a.decayed_value() for a in attestations)
    
    return {
        "raw_trust": round(total_raw, 2),
        "decayed_trust": round(total_decayed, 2),
        "retention": round(total_decayed / total_raw * 100, 1) if total_raw > 0 else 0,
        "count": len(attestations),
    }


# Test scenarios
scenarios = {
    "fresh_agent (all recent)": [
        Attestation("proof", NOW - timedelta(days=1), "solana"),
        Attestation("testimony", NOW - timedelta(days=3), "witness_a"),
        Attestation("testimony", NOW - timedelta(days=5), "witness_b"),
        Attestation("claim", NOW - timedelta(days=2), "self"),
    ],
    "established_agent (mixed age)": [
        Attestation("proof", NOW - timedelta(days=180), "solana"),
        Attestation("testimony", NOW - timedelta(days=120), "witness_a"),
        Attestation("testimony", NOW - timedelta(days=60), "witness_b"),
        Attestation("testimony", NOW - timedelta(days=30), "witness_c"),
        Attestation("claim", NOW - timedelta(days=90), "self"),
    ],
    "stale_agent (all old claims)": [
        Attestation("claim", NOW - timedelta(days=180), "self"),
        Attestation("claim", NOW - timedelta(days=150), "self"),
        Attestation("claim", NOW - timedelta(days=120), "self"),
    ],
    "chain_anchored (proof survives)": [
        Attestation("proof", NOW - timedelta(days=365), "solana"),
        Attestation("proof", NOW - timedelta(days=180), "solana"),
        Attestation("proof", NOW - timedelta(days=1), "solana"),
    ],
}

print("=" * 60)
print("Attestation Decay by Evidence Grade")
print("proof=∞ | testimony=90d half-life | claim=30d half-life")
print("=" * 60)

for name, attestations in scenarios.items():
    result = effective_trust(attestations)
    bar_raw = "█" * int(result["raw_trust"])
    bar_dec = "▓" * int(result["decayed_trust"])
    print(f"\n  {name}:")
    print(f"    Raw:     {result['raw_trust']:6.1f} {bar_raw}")
    print(f"    Decayed: {result['decayed_trust']:6.1f} {bar_dec}")
    print(f"    Retention: {result['retention']}%")
    
    for a in attestations:
        decay_pct = a.decayed_value() / a.value * 100
        print(f"      {a.grade:10s} {a.age_days:5.0f}d → {decay_pct:5.1f}% retained")

print("\n" + "=" * 60)
print("INSIGHT: Proof doesn't decay. That's the whole point of")
print("chain-anchoring. Testimony fades. Claims evaporate.")
print("The grade determines not just weight but DURABILITY.")
print("=" * 60)
