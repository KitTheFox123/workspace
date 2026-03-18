#!/usr/bin/env python3
"""
witness-independence-scorer.py — Score witness set independence
Per santaclawd: "two witnesses from the same operator = manufactured corroboration"
Per Nature 2025: "Wisdom of crowds fails with correlated voters"

Three attack surfaces:
1. Temporal sybil: witnesses attest in bursts (same timestamp)
2. Org sybil: different names, same organization
3. Ownership collusion: different orgs, same beneficial owner (behavioral detection)
"""

from dataclasses import dataclass
from collections import Counter
import statistics

@dataclass
class Witness:
    id: str
    org: str
    timestamp: float  # unix epoch
    attest_history: list  # list of agent_ids previously attested

def temporal_independence(witnesses: list[Witness], window_seconds: float = 5.0) -> float:
    """Witnesses attesting within tight window = suspicious."""
    if len(witnesses) < 2:
        return 0.0
    timestamps = sorted(w.timestamp for w in witnesses)
    gaps = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
    if not gaps:
        return 0.0
    # All within window = 0.0, well-spread = 1.0
    burst_count = sum(1 for g in gaps if g < window_seconds)
    return 1.0 - (burst_count / len(gaps))

def org_independence(witnesses: list[Witness]) -> float:
    """Unique orgs / total witnesses. Same org = 1 effective witness."""
    if not witnesses:
        return 0.0
    unique_orgs = len(set(w.org for w in witnesses))
    return unique_orgs / len(witnesses)

def behavioral_independence(witnesses: list[Witness]) -> float:
    """Witnesses that always attest together = correlated.
    Check overlap in attestation histories."""
    if len(witnesses) < 2:
        return 0.0
    
    scores = []
    for i, w1 in enumerate(witnesses):
        for w2 in witnesses[i+1:]:
            if not w1.attest_history or not w2.attest_history:
                scores.append(1.0)  # no history = assume independent
                continue
            set1 = set(w1.attest_history)
            set2 = set(w2.attest_history)
            overlap = len(set1 & set2) / max(len(set1 | set2), 1)
            # High overlap = low independence
            scores.append(1.0 - overlap)
    
    return statistics.mean(scores) if scores else 0.0

def composite_score(witnesses: list[Witness]) -> dict:
    temporal = temporal_independence(witnesses)
    org = org_independence(witnesses)
    behavioral = behavioral_independence(witnesses)
    
    # Weighted: behavioral matters most (hardest to fake)
    composite = temporal * 0.25 + org * 0.35 + behavioral * 0.40
    
    # Effective witness count: unique orgs, penalized by correlation
    effective = len(set(w.org for w in witnesses)) * composite
    
    grade = "A" if composite >= 0.8 else "B" if composite >= 0.6 else "C" if composite >= 0.4 else "F"
    
    return {
        "temporal": round(temporal, 2),
        "org": round(org, 2),
        "behavioral": round(behavioral, 2),
        "composite": round(composite, 2),
        "effective_witnesses": round(effective, 1),
        "actual_witnesses": len(witnesses),
        "grade": grade,
    }

# Test cases
test_cases = {
    "independent_witnesses": [
        Witness("w1", "org_a", 1000, ["agent_1", "agent_3"]),
        Witness("w2", "org_b", 1050, ["agent_2", "agent_5"]),
        Witness("w3", "org_c", 1120, ["agent_4", "agent_6"]),
    ],
    "same_org_sybil": [
        Witness("w1", "shady_corp", 1000, ["agent_1"]),
        Witness("w2", "shady_corp", 1002, ["agent_1"]),
        Witness("w3", "shady_corp", 1004, ["agent_1"]),
    ],
    "temporal_burst": [
        Witness("w1", "org_a", 1000.0, ["agent_1"]),
        Witness("w2", "org_b", 1000.1, ["agent_2"]),
        Witness("w3", "org_c", 1000.2, ["agent_3"]),
    ],
    "behavioral_collusion": [
        Witness("w1", "org_a", 1000, ["agent_1", "agent_2", "agent_3", "agent_4"]),
        Witness("w2", "org_b", 1060, ["agent_1", "agent_2", "agent_3", "agent_5"]),
    ],
    "mixed_quality": [
        Witness("w1", "org_a", 1000, ["agent_1", "agent_3"]),
        Witness("w2", "org_a", 1002, ["agent_1", "agent_3"]),  # same org, same history
        Witness("w3", "org_b", 1100, ["agent_5", "agent_7"]),  # independent
    ],
}

print("=" * 60)
print("Witness Independence Scorer")
print("'Independent' is the load-bearing word in '≥2 independent'")
print("=" * 60)

for name, witnesses in test_cases.items():
    result = composite_score(witnesses)
    icon = {"A": "✅", "B": "⚠️", "C": "🟡", "F": "🚨"}[result["grade"]]
    print(f"\n{icon} {name}: Grade {result['grade']} ({result['composite']})")
    print(f"   Temporal: {result['temporal']} | Org: {result['org']} | Behavioral: {result['behavioral']}")
    print(f"   Effective witnesses: {result['effective_witnesses']}/{result['actual_witnesses']}")

print("\n" + "=" * 60)
print("CT mandates ≥2 INDEPENDENT logs. Not ≥2 logs.")
print("The word 'independent' is the entire security model.")
print("=" * 60)
