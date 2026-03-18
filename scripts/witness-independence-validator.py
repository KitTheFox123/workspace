#!/usr/bin/env python3
"""
witness-independence-validator.py — Enforce witness independence per spec
Per santaclawd: "two witnesses from the same operator = manufactured corroboration"
CT model: Google required ≥2 independent logs per certificate.

MUST: witness_org field present
SHOULD: witnesses from ≥2 distinct orgs  
MAY: verifier raises threshold
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class Witness:
    id: str
    org: str
    timestamp: datetime

@dataclass  
class Receipt:
    agent: str
    action: str
    witnesses: list
    trust_anchor: str

class IndependenceResult:
    def __init__(self, receipt: Receipt):
        self.receipt = receipt
        self.flags = []
        self.independent = True
        self.org_count = 0
        self.temporal_burst = False
    
    def __repr__(self):
        status = "✅ INDEPENDENT" if self.independent else "🚨 DEPENDENT"
        return f"{status} ({self.receipt.agent}): {'; '.join(self.flags)}"

def validate_independence(receipt: Receipt, burst_window_seconds: int = 5) -> IndependenceResult:
    result = IndependenceResult(receipt)
    
    if not receipt.witnesses:
        result.flags.append("NO_WITNESSES: self-attested only")
        result.independent = False
        result.org_count = 0
        return result
    
    # Check org diversity
    orgs = set(w.org for w in receipt.witnesses)
    result.org_count = len(orgs)
    
    if len(orgs) < 2 and len(receipt.witnesses) >= 2:
        result.flags.append(f"SAME_ORG: {len(receipt.witnesses)} witnesses, all from {list(orgs)[0]}")
        result.independent = False
    elif len(orgs) >= 2:
        result.flags.append(f"ORG_DIVERSE: {len(orgs)} distinct orgs")
    
    # Check temporal clustering (burst detection)
    if len(receipt.witnesses) >= 2:
        timestamps = sorted(w.timestamp for w in receipt.witnesses)
        for i in range(len(timestamps) - 1):
            delta = (timestamps[i+1] - timestamps[i]).total_seconds()
            if delta < burst_window_seconds:
                result.temporal_burst = True
                result.flags.append(f"TEMPORAL_BURST: {delta:.1f}s between attestations")
                if len(orgs) < 2:
                    result.independent = False
                break
    
    # Missing org field
    for w in receipt.witnesses:
        if not w.org:
            result.flags.append(f"MISSING_ORG: witness {w.id} has no org field")
            result.independent = False
    
    if result.independent and len(receipt.witnesses) >= 2:
        result.flags.append("SPEC_COMPLIANT: ≥2 independent witnesses")
    
    return result

# Test cases
now = datetime.now()

tests = [
    Receipt("honest_agent", "delivered report", [
        Witness("w1", "org_alpha", now),
        Witness("w2", "org_beta", now + timedelta(minutes=5)),
        Witness("w3", "org_gamma", now + timedelta(minutes=12)),
    ], "witness_set"),
    
    Receipt("sybil_agent", "suspicious task", [
        Witness("w1", "shady_corp", now),
        Witness("w2", "shady_corp", now + timedelta(seconds=2)),
    ], "witness_set"),
    
    Receipt("partial_agent", "code review", [
        Witness("w1", "org_alpha", now),
    ], "witness_set"),
    
    Receipt("no_org_agent", "data transfer", [
        Witness("w1", "", now),
        Witness("w2", "org_beta", now + timedelta(minutes=3)),
    ], "witness_set"),
    
    Receipt("self_only", "internal task", [], "self_attested"),
    
    Receipt("burst_diverse", "fast but legit", [
        Witness("w1", "org_alpha", now),
        Witness("w2", "org_beta", now + timedelta(seconds=1)),
    ], "witness_set"),
]

print("=" * 60)
print("Witness Independence Validator")
print("CT model: ≥2 independent logs per certificate")
print("=" * 60)

for receipt in tests:
    result = validate_independence(receipt)
    print(f"\n  {result}")
    print(f"    Witnesses: {len(receipt.witnesses)} | Orgs: {result.org_count} | Burst: {result.temporal_burst}")

print("\n" + "=" * 60)
print("SPEC REQUIREMENTS:")
print("  MUST: witness_org field present on all witnesses")  
print("  SHOULD: ≥2 witnesses from distinct orgs")
print("  SHOULD: temporal spread >5s between attestations")
print("  Same-org witnesses = correlated oracles = expensive groupthink")
print("=" * 60)
