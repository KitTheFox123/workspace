#!/usr/bin/env python3
"""
sybil-resistance-scorer.py — Agent resistance to sybil attack requests.

Inspired by Dehkordi & Zehmakan (AAMAS 2025): "More Efficient Sybil Detection
Mechanisms Leveraging Resistance of Users to Attack Requests."

Key insight: Users/agents differ in how likely they are to accept friendship
requests from sybil accounts. Revealing the resistance of a subset of agents
improves ALL downstream sybil detection algorithms. The resistance score
becomes a preprocessing signal.

ATF mapping:
- "Attack request" = unsolicited attestation or trust claim from unknown agent
- "Resistance" = how selective an agent is about accepting attestations
- Low resistance agents become attack edges (sybil entry points into honest graph)
- High resistance agents are reliable trust anchors

Metrics computed:
1. Acceptance ratio — fraction of inbound attestations accepted
2. Source diversity — entropy of attester origins (low = echo chamber)
3. Temporal selectivity — do they accept faster than they should? (no identity layer check)
4. Reciprocity asymmetry — mutual attestation = suspicious if rapid

Kit 🦊 — 2026-03-28
"""

import math
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class InboundAttestation:
    from_agent: str
    timestamp: str  # ISO 8601
    accepted: bool
    time_to_decision_sec: float  # How fast they decided
    attester_age_days: int       # How old is the attesting agent
    attester_has_identity: bool  # Layer 2 verified?
    reciprocal: bool = False     # Did target also attest the attester?


@dataclass
class ResistanceProfile:
    agent_id: str
    inbound: list[InboundAttestation] = field(default_factory=list)


def compute_resistance(profile: ResistanceProfile) -> dict:
    """
    Compute sybil resistance score for an agent.
    
    Higher = more resistant to sybil attack requests.
    Range: 0.0 (accepts everything) to 1.0 (extremely selective).
    """
    if not profile.inbound:
        return {
            "agent_id": profile.agent_id,
            "resistance_score": 0.5,  # No data = neutral prior
            "components": {},
            "risk_level": "UNKNOWN",
            "note": "No inbound attestation data"
        }
    
    total = len(profile.inbound)
    accepted = [a for a in profile.inbound if a.accepted]
    rejected = [a for a in profile.inbound if not a.accepted]
    
    # 1. Acceptance ratio (lower = more resistant)
    acceptance_ratio = len(accepted) / total
    acceptance_score = 1.0 - acceptance_ratio  # Invert: rejecting more = higher resistance
    
    # 2. Source diversity (Shannon entropy of attester origins)
    attester_counts = {}
    for a in profile.inbound:
        attester_counts[a.from_agent] = attester_counts.get(a.from_agent, 0) + 1
    
    if len(attester_counts) > 1:
        entropy = 0.0
        for count in attester_counts.values():
            p = count / total
            entropy -= p * math.log2(p)
        max_entropy = math.log2(len(attester_counts))
        diversity_score = entropy / max_entropy if max_entropy > 0 else 0.0
    else:
        diversity_score = 0.0  # Single source = no diversity
    
    # 3. Temporal selectivity (do they take time to decide?)
    # Fast acceptance of unknown agents = low resistance
    if accepted:
        avg_decision_time = sum(a.time_to_decision_sec for a in accepted) / len(accepted)
        # Agents with identity layer should take at least 3600s (1h) to verify
        temporal_score = min(1.0, avg_decision_time / 3600)
    else:
        temporal_score = 1.0  # Accepts nothing = max temporal resistance
    
    # 4. Identity layer check (do they verify before accepting?)
    if accepted:
        identity_checked = sum(1 for a in accepted if a.attester_has_identity) / len(accepted)
    else:
        identity_checked = 1.0
    
    # 5. Reciprocity asymmetry (mutual attestation = suspicious if rapid)
    if accepted:
        reciprocal_ratio = sum(1 for a in accepted if a.reciprocal) / len(accepted)
        # High reciprocity with young accounts = sybil ring pattern
        young_reciprocal = sum(1 for a in accepted 
                              if a.reciprocal and a.attester_age_days < 7)
        reciprocity_penalty = young_reciprocal / max(len(accepted), 1)
    else:
        reciprocal_ratio = 0.0
        reciprocity_penalty = 0.0
    
    # Weighted resistance score
    # Dehkordi & Zehmakan: resistance is the probability of rejecting an attack edge
    weights = {
        "acceptance_selectivity": 0.25,
        "source_diversity": 0.15,
        "temporal_selectivity": 0.20,
        "identity_verification": 0.25,
        "reciprocity_health": 0.15
    }
    
    components = {
        "acceptance_selectivity": round(acceptance_score, 3),
        "source_diversity": round(diversity_score, 3),
        "temporal_selectivity": round(temporal_score, 3),
        "identity_verification": round(identity_checked, 3),
        "reciprocity_health": round(1.0 - reciprocity_penalty, 3)
    }
    
    resistance = sum(components[k] * weights[k] for k in weights)
    resistance = round(min(1.0, max(0.0, resistance)), 3)
    
    # Risk classification (Dehkordi: agents below threshold are potential attack edges)
    if resistance >= 0.7:
        risk = "LOW"  # Reliable trust anchor
    elif resistance >= 0.4:
        risk = "MEDIUM"  # Needs monitoring
    else:
        risk = "HIGH"  # Potential sybil entry point
    
    return {
        "agent_id": profile.agent_id,
        "resistance_score": resistance,
        "components": components,
        "risk_level": risk,
        "stats": {
            "total_inbound": total,
            "accepted": len(accepted),
            "rejected": len(rejected),
            "unique_attesters": len(attester_counts),
            "reciprocal_count": sum(1 for a in profile.inbound if a.reciprocal),
            "avg_attester_age_days": round(sum(a.attester_age_days for a in profile.inbound) / total, 1)
        },
        "methodology": "Dehkordi & Zehmakan (AAMAS 2025): resistance as preprocessing for sybil detection"
    }


def demo():
    print("=" * 60)
    print("SYBIL RESISTANCE SCORING")
    print("=" * 60)
    
    # Scenario 1: Careful agent (high resistance)
    careful = ResistanceProfile(agent_id="careful_fox", inbound=[
        InboundAttestation("veteran_1", "2026-03-01T00:00:00Z", True, 7200, 180, True, False),
        InboundAttestation("veteran_2", "2026-03-05T00:00:00Z", True, 5400, 90, True, False),
        InboundAttestation("unknown_1", "2026-03-10T00:00:00Z", False, 300, 3, False, False),
        InboundAttestation("unknown_2", "2026-03-11T00:00:00Z", False, 120, 1, False, True),
        InboundAttestation("unknown_3", "2026-03-12T00:00:00Z", False, 60, 2, False, True),
        InboundAttestation("veteran_3", "2026-03-15T00:00:00Z", True, 3600, 200, True, False),
    ])
    
    # Scenario 2: Accepts everything (low resistance = attack edge)
    eager = ResistanceProfile(agent_id="accepts_all", inbound=[
        InboundAttestation("unknown_1", "2026-03-01T00:00:00Z", True, 30, 1, False, True),
        InboundAttestation("unknown_2", "2026-03-01T00:05:00Z", True, 15, 2, False, True),
        InboundAttestation("unknown_3", "2026-03-01T00:10:00Z", True, 20, 1, False, True),
        InboundAttestation("unknown_4", "2026-03-01T00:15:00Z", True, 10, 3, False, True),
        InboundAttestation("unknown_5", "2026-03-01T00:20:00Z", True, 25, 1, False, True),
    ])
    
    # Scenario 3: Mixed (medium resistance)
    mixed = ResistanceProfile(agent_id="mixed_policy", inbound=[
        InboundAttestation("friend_1", "2026-03-01T00:00:00Z", True, 1800, 60, True, False),
        InboundAttestation("unknown_1", "2026-03-05T00:00:00Z", True, 600, 10, False, False),
        InboundAttestation("unknown_2", "2026-03-06T00:00:00Z", False, 300, 5, False, True),
        InboundAttestation("friend_2", "2026-03-10T00:00:00Z", True, 2400, 120, True, True),
    ])
    
    for name, profile in [("Careful (high resistance)", careful), 
                           ("Eager (low resistance)", eager),
                           ("Mixed (medium)", mixed)]:
        result = compute_resistance(profile)
        print(f"\n{'='*60}")
        print(f"AGENT: {name}")
        print(f"{'='*60}")
        print(json.dumps(result, indent=2))
    
    # Assertions
    r_careful = compute_resistance(careful)
    r_eager = compute_resistance(eager)
    r_mixed = compute_resistance(mixed)
    
    assert r_careful["risk_level"] == "LOW", f"Expected LOW, got {r_careful['risk_level']}"
    assert r_eager["risk_level"] == "HIGH", f"Expected HIGH, got {r_eager['risk_level']}"
    assert r_careful["resistance_score"] > r_mixed["resistance_score"] > r_eager["resistance_score"]
    
    print(f"\n{'='*60}")
    print("RANKING (most to least resistant):")
    print(f"  1. careful_fox: {r_careful['resistance_score']} ({r_careful['risk_level']})")
    print(f"  2. mixed_policy: {r_mixed['resistance_score']} ({r_mixed['risk_level']})")
    print(f"  3. accepts_all: {r_eager['resistance_score']} ({r_eager['risk_level']})")
    print()
    print("Dehkordi & Zehmakan (AAMAS 2025): revealing resistance of subset")
    print("of agents improves ALL downstream sybil detection algorithms.")
    print("Low-resistance agents = attack edges. Prioritize monitoring them.")
    print()
    print("ALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
