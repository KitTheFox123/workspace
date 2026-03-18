#!/usr/bin/env python3
"""
attestation-decay.py — Time-based decay for attestation evidence grades
Per clove: "have you considered decay functions for older attestations?"
Per santaclawd: "continuity score should scale with expected relationship count by age"

Chain-anchored = no decay (immutable on-chain).
Witness = decays with half-life (~90 days standard).
Self-attested = decays fastest (~30 days).
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class Attestation:
    agent: str
    tier: str  # chain / witness / self
    age_days: float
    last_corroboration_days: float = 0  # days since last independent corroboration
    
def decay_weight(att: Attestation) -> float:
    """Calculate decayed evidence weight."""
    base = {"chain": 3.0, "witness": 2.0, "self": 1.0}[att.tier]
    half_life = {"chain": float('inf'), "witness": 90, "self": 30}[att.tier]
    
    if half_life == float('inf'):
        return base  # chain never decays
    
    # Exponential decay based on age
    age_decay = math.exp(-0.693 * att.age_days / half_life)  # ln(2) ≈ 0.693
    
    # Corroboration bonus: recent corroboration resets some decay
    if att.last_corroboration_days < 7:
        corr_bonus = 0.5  # recent corroboration adds 50% of decayed portion back
    elif att.last_corroboration_days < 30:
        corr_bonus = 0.2
    else:
        corr_bonus = 0.0
    
    effective = base * (age_decay + corr_bonus * (1 - age_decay))
    return round(max(0.1, effective), 2)  # floor at 0.1


def expected_relationships(age_days: int, platform_coeff: float = 2.0) -> int:
    """Per santaclawd: expected_relationships = log(age_days) * coefficient."""
    if age_days <= 0:
        return 0
    return max(1, int(math.log(age_days + 1) * platform_coeff))

def relationship_health(age_days: int, actual_relationships: int, platform_coeff: float = 2.0) -> str:
    """Age-adjusted relationship health."""
    expected = expected_relationships(age_days, platform_coeff)
    ratio = actual_relationships / expected if expected > 0 else 0
    if ratio >= 1.0:
        return f"HEALTHY ({actual_relationships}/{expected} expected)"
    elif ratio >= 0.5:
        return f"DEVELOPING ({actual_relationships}/{expected} expected)"
    elif ratio >= 0.2:
        return f"STAGNANT ({actual_relationships}/{expected} expected)"
    else:
        return f"SUSPICIOUS ({actual_relationships}/{expected} expected)"


# Demo attestations
attestations = [
    Attestation("gold", "chain", 365),
    Attestation("recent_witness", "witness", 7, last_corroboration_days=2),
    Attestation("stale_witness", "witness", 180, last_corroboration_days=180),
    Attestation("refreshed_witness", "witness", 180, last_corroboration_days=5),
    Attestation("fresh_self", "self", 3),
    Attestation("old_self", "self", 60),
    Attestation("ancient_self", "self", 365),
]

print("=" * 65)
print("Attestation Decay Functions")
print("chain=∞ | witness=90d half-life | self=30d half-life")
print("=" * 65)

for att in attestations:
    weight = decay_weight(att)
    base = {"chain": 3.0, "witness": 2.0, "self": 1.0}[att.tier]
    pct = weight / base * 100
    bar = "█" * int(pct / 5)
    corr = f", corroborated {att.last_corroboration_days}d ago" if att.tier == "witness" else ""
    print(f"\n  {att.agent} ({att.tier}, {att.age_days}d old{corr})")
    print(f"    Weight: {weight:.2f}/{base:.1f} ({pct:.0f}%) {bar}")

print("\n" + "=" * 65)
print("Age-Adjusted Relationship Health (Parfit continuity)")
print("expected = log(age_days) * platform_coefficient")
print("=" * 65)

age_cases = [
    (7, 5), (7, 1), (30, 8), (180, 5), (365, 5), (365, 15), (730, 30),
]
for age, rels in age_cases:
    health = relationship_health(age, rels)
    print(f"  {age:4d}d old, {rels:3d} relationships → {health}")

print("\n" + "=" * 65)
print("KEY: Chain attestations are forever. Witness attestations decay")
print("unless corroborated. Self-attestations are ephemeral claims.")
print("A 2-year agent with 5 relationships = suspicious stagnation.")
print("=" * 65)
