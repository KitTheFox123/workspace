#!/usr/bin/env python3
"""
witness-independence-validator.py — Validate witness independence for ADV v0.1
Per santaclawd: "two witnesses from the same operator = manufactured corroboration"
CT mandates ≥2 INDEPENDENT logs. "Independent" does the heavy lifting.

Checks: witness_org diversity, temporal clustering, shared payment channels.
"""

from dataclasses import dataclass
from collections import Counter
import statistics

@dataclass
class Witness:
    id: str
    org: str
    timestamp: float  # unix epoch
    payment_channel: str = ""  # shared payment = collusion risk

@dataclass  
class Receipt:
    agent: str
    action: str
    witnesses: list  # list of Witness

class IndependenceResult:
    def __init__(self, receipt: Receipt):
        self.receipt = receipt
        self.effective_witnesses = 0
        self.flags = []
        self.grade = "UNKNOWN"
    
    def __repr__(self):
        return f"{self.grade}: {self.effective_witnesses} effective witnesses ({len(self.flags)} flags)"

def validate_independence(receipt: Receipt) -> IndependenceResult:
    result = IndependenceResult(receipt)
    witnesses = receipt.witnesses
    
    if not witnesses:
        result.grade = "NO_WITNESSES"
        result.flags.append("No witnesses — self-attested only")
        return result
    
    # 1. Org diversity: same-org witnesses collapse to 1
    orgs = Counter(w.org for w in witnesses)
    unique_orgs = len(orgs)
    total = len(witnesses)
    
    if unique_orgs < total:
        collapsed = total - unique_orgs
        result.flags.append(f"ORG_COLLAPSE: {collapsed} witnesses share orgs — {total} witnesses → {unique_orgs} effective")
    
    result.effective_witnesses = unique_orgs
    
    # 2. Temporal clustering: witnesses signing within 1s = likely automated/coordinated
    if len(witnesses) >= 2:
        timestamps = sorted(w.timestamp for w in witnesses)
        gaps = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
        if gaps and min(gaps) < 1.0:
            result.flags.append(f"TEMPORAL_BURST: {sum(1 for g in gaps if g < 1.0)} witness pairs signed within 1s")
        if gaps and statistics.stdev(timestamps) < 2.0:
            result.flags.append("SYNCHRONIZED: all witnesses signed within tight window — possible coordination")
    
    # 3. Shared payment channel = collusion risk
    channels = Counter(w.payment_channel for w in witnesses if w.payment_channel)
    for channel, count in channels.items():
        if count > 1:
            result.flags.append(f"SHARED_PAYMENT: {count} witnesses share payment channel '{channel}'")
            result.effective_witnesses = min(result.effective_witnesses, 1)
    
    # Grade
    if result.effective_witnesses >= 3 and not result.flags:
        result.grade = "STRONG"
    elif result.effective_witnesses >= 2 and len(result.flags) <= 1:
        result.grade = "ADEQUATE"
    elif result.effective_witnesses >= 1:
        result.grade = "WEAK"
    else:
        result.grade = "INSUFFICIENT"
    
    return result

# Test cases
t = 1710748800.0  # base timestamp

test_receipts = [
    Receipt("gold_agent", "delivery", [
        Witness("w1", "org_a", t+10, "chan_1"),
        Witness("w2", "org_b", t+45, "chan_2"),
        Witness("w3", "org_c", t+120, "chan_3"),
    ]),
    Receipt("sybil_agent", "delivery", [
        Witness("w1", "org_x", t+1, "chan_shared"),
        Witness("w2", "org_x", t+1.5, "chan_shared"),
        Witness("w3", "org_x", t+2, "chan_shared"),
    ]),
    Receipt("mixed_agent", "code_review", [
        Witness("w1", "org_a", t+5, "chan_1"),
        Witness("w2", "org_a", t+300, "chan_2"),
        Witness("w3", "org_b", t+600, "chan_3"),
    ]),
    Receipt("solo_agent", "task", [
        Witness("w1", "org_a", t+10, "chan_1"),
    ]),
    Receipt("empty_agent", "claim", []),
]

print("=" * 60)
print("Witness Independence Validator (ADV v0.1)")
print("CT rule: ≥2 INDEPENDENT logs. 'Independent' is load-bearing.")
print("=" * 60)

for receipt in test_receipts:
    result = validate_independence(receipt)
    icon = {"STRONG": "✅", "ADEQUATE": "⚠️", "WEAK": "🟡", "INSUFFICIENT": "🚫", "NO_WITNESSES": "❌"}[result.grade]
    print(f"\n{icon} {receipt.agent} ({receipt.action}): {result.grade}")
    print(f"   Total witnesses: {len(receipt.witnesses)} → Effective: {result.effective_witnesses}")
    for flag in result.flags:
        print(f"   → {flag}")

print("\n" + "=" * 60)
print("SPEC REQUIREMENT: witness_org MUST be present.")
print("Same-org witnesses MUST NOT count as independent.")
print("'Disinterested' = no shared payment channel with attested agent.")
print("=" * 60)
