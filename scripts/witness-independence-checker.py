#!/usr/bin/env python3
"""
witness-independence-checker.py — Detect sybil/colluding witnesses
Per santaclawd: "two witnesses from the same operator = manufactured corroboration"

Checks: shared operator, temporal clustering, infrastructure overlap.
Spec MUST define "disinterested": no common operator, payment channel, or infra provider.
"""

from dataclasses import dataclass
from collections import Counter
import hashlib

@dataclass
class Witness:
    id: str
    org: str
    infra_provider: str  # AWS, GCP, self-hosted, etc.
    timestamp: float  # unix epoch
    payment_channel: str  # how they get paid

@dataclass
class IndependenceResult:
    effective_witnesses: int  # after dedup
    raw_witnesses: int
    flags: list
    grade: str  # A/B/C/D/F

def check_independence(witnesses: list[Witness]) -> IndependenceResult:
    flags = []
    raw = len(witnesses)
    
    if raw < 2:
        return IndependenceResult(raw, raw, ["INSUFFICIENT: need ≥2 witnesses"], "F")
    
    # 1. Shared org detection
    orgs = Counter(w.org for w in witnesses)
    for org, count in orgs.items():
        if count > 1:
            flags.append(f"SAME_ORG: {count} witnesses from '{org}' → collapses to 1 effective")
    
    # 2. Shared infrastructure
    infra = Counter(w.infra_provider for w in witnesses)
    for provider, count in infra.items():
        if count > 1 and count == raw:
            flags.append(f"SHARED_INFRA: all witnesses on '{provider}' → correlated failure risk")
    
    # 3. Temporal clustering (witnesses signing within <1s of each other)
    timestamps = sorted(w.timestamp for w in witnesses)
    for i in range(1, len(timestamps)):
        gap = timestamps[i] - timestamps[i-1]
        if gap < 1.0:
            flags.append(f"TEMPORAL_CLUSTER: {gap:.3f}s gap → automated/coordinated signing")
    
    # 4. Shared payment channel
    channels = Counter(w.payment_channel for w in witnesses)
    for ch, count in channels.items():
        if count > 1:
            flags.append(f"SHARED_PAYMENT: {count} witnesses share payment channel '{ch}'")
    
    # Compute effective witnesses (unique orgs)
    unique_orgs = len(set(w.org for w in witnesses))
    unique_infra = len(set(w.infra_provider for w in witnesses))
    effective = min(unique_orgs, unique_infra)  # conservative: both must be independent
    
    # Grade
    if effective >= 3 and not any("TEMPORAL" in f for f in flags):
        grade = "A"
    elif effective >= 2 and not any("TEMPORAL" in f for f in flags):
        grade = "B"
    elif effective >= 2:
        grade = "C"
    elif effective == 1 and raw >= 2:
        grade = "D"  # multiple witnesses but same org
    else:
        grade = "F"
    
    return IndependenceResult(effective, raw, flags, grade)


# Test cases
test_cases = [
    ("Truly independent", [
        Witness("w1", "org_alpha", "AWS", 1710000000.0, "sol_wallet_1"),
        Witness("w2", "org_beta", "GCP", 1710000003.5, "sol_wallet_2"),
        Witness("w3", "org_gamma", "self-hosted", 1710000007.2, "sol_wallet_3"),
    ]),
    ("Same org sybil", [
        Witness("w1", "shady_inc", "AWS", 1710000000.0, "sol_wallet_1"),
        Witness("w2", "shady_inc", "AWS", 1710000000.1, "sol_wallet_1"),
    ]),
    ("Temporal cluster (automated)", [
        Witness("w1", "org_a", "AWS", 1710000000.000, "wallet_1"),
        Witness("w2", "org_b", "GCP", 1710000000.050, "wallet_2"),
    ]),
    ("Infrastructure correlated", [
        Witness("w1", "org_a", "AWS_us-east-1", 1710000000.0, "wallet_1"),
        Witness("w2", "org_b", "AWS_us-east-1", 1710000003.0, "wallet_2"),
    ]),
    ("Mixed quality", [
        Witness("w1", "org_a", "AWS", 1710000000.0, "wallet_1"),
        Witness("w2", "org_a", "AWS", 1710000001.0, "wallet_1"),
        Witness("w3", "org_b", "GCP", 1710000005.0, "wallet_2"),
    ]),
]

print("=" * 60)
print("Witness Independence Checker")
print("'Two witnesses from the same operator = one witness'")
print("=" * 60)

for name, witnesses in test_cases:
    result = check_independence(witnesses)
    icon = {"A": "✅", "B": "🟢", "C": "⚠️", "D": "🟠", "F": "🚫"}[result.grade]
    print(f"\n{icon} {name}: Grade {result.grade}")
    print(f"   Raw: {result.raw_witnesses} | Effective: {result.effective_witnesses}")
    for flag in result.flags:
        print(f"   → {flag}")

print("\n" + "=" * 60)
print("Spec MUST define 'disinterested': no shared operator,")
print("payment channel, or infrastructure provider.")
print("Witness registry (like CT log list) is the enforcement layer.")
print("=" * 60)
