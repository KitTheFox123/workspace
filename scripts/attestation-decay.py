#!/usr/bin/env python3
"""
attestation-decay.py — Time-weighted attestation scoring
Per clove: "have you considered decay functions for older attestations?"

chain-anchored = no decay (blockchain is forever)
witness testimony = half-life 90 days (Ebbinghaus curve)
self-attested claims = half-life 30 days (expire fast)

Plus: relationship depth scaling per santaclawd
expected_relationships = sqrt(age_days)
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

NOW = datetime(2026, 3, 18)

@dataclass
class Attestation:
    grade: str  # chain/witness/self
    timestamp: datetime
    witness_org: str = ""

HALF_LIVES = {
    "chain": float('inf'),  # never decays
    "witness": 90,          # 90-day half-life
    "self": 30,             # 30-day half-life
}

WATSON_MORGAN = {"chain": 3.0, "witness": 2.0, "self": 1.0}

def decay_weight(attestation: Attestation, now: datetime = NOW) -> float:
    """Compute time-decayed weight."""
    age_days = (now - attestation.timestamp).days
    half_life = HALF_LIVES[attestation.grade]
    base_weight = WATSON_MORGAN[attestation.grade]
    
    if half_life == float('inf'):
        return base_weight  # chain never decays
    
    decay = 0.5 ** (age_days / half_life)
    return base_weight * decay

def expected_relationships(age_days: int) -> float:
    """Per santaclawd: depth should scale with age. sqrt(age_days)."""
    return math.sqrt(age_days)

def continuity_score(actual_relationships: int, age_days: int) -> float:
    """actual / expected. Below 0.3 = suspicious gap."""
    expected = expected_relationships(age_days)
    if expected == 0:
        return 0
    return min(2.0, actual_relationships / expected)

# Demo: agent with mixed attestation history
attestations = [
    Attestation("chain", NOW - timedelta(days=365)),  # 1 year old chain
    Attestation("chain", NOW - timedelta(days=30)),    # recent chain
    Attestation("witness", NOW - timedelta(days=7), "org_a"),   # fresh witness
    Attestation("witness", NOW - timedelta(days=180), "org_b"), # old witness
    Attestation("witness", NOW - timedelta(days=360), "org_c"), # very old witness
    Attestation("self", NOW - timedelta(days=3)),      # recent self
    Attestation("self", NOW - timedelta(days=60)),     # old self
    Attestation("self", NOW - timedelta(days=120)),    # very old self
]

print("=" * 65)
print("Attestation Decay Scoring")
print("chain=∞ | witness=90d half-life | self=30d half-life")
print("=" * 65)

total_weight = 0
for a in attestations:
    w = decay_weight(a)
    age = (NOW - a.timestamp).days
    bar = "█" * int(w * 5)
    print(f"  {a.grade:8s} age={age:3d}d  weight={w:.2f}  {bar}")
    total_weight += w

print(f"\n  Total decayed weight: {total_weight:.2f}")
print(f"  Undecayed would be:   {sum(WATSON_MORGAN[a.grade] for a in attestations):.2f}")
print(f"  Decay ratio:          {total_weight / sum(WATSON_MORGAN[a.grade] for a in attestations):.0%}")

# Relationship depth scaling
print("\n" + "=" * 65)
print("Relationship Depth Scaling (sqrt model)")
print("=" * 65)

agents = [
    ("new_agent", 5, 30),
    ("3mo_agent", 8, 90),
    ("6mo_agent", 12, 180),
    ("1yr_agent", 19, 365),
    ("2yr_agent", 27, 730),
    ("suspicious_old", 3, 365),  # old but few relationships
    ("social_butterfly", 50, 90),  # many relationships, young
]

for name, actual, age in agents:
    expected = expected_relationships(age)
    score = continuity_score(actual, age)
    flag = "🚨" if score < 0.3 else "⚠️" if score < 0.7 else "✅"
    print(f"  {flag} {name:20s} actual={actual:2d} expected={expected:.0f} score={score:.2f}")

print("\n" + "=" * 65)
print("KEY: chain receipts are permanent. witness testimony fades.")
print("self-claims expire fast. recency IS relevance.")
print("=" * 65)
