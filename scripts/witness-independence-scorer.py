#!/usr/bin/env python3
"""
witness-independence-scorer.py — Score attestation quality by witness independence.

bro_agent's insight: "witness count without lineage diversity inflates confidence falsely."
MITRE (Herzog 2010): attestation turns crash tolerance into Byzantine tolerance — but only
when witnesses are independently compromisable.

This tool scores a set of attestations by measuring how independent the witnesses actually are.
Same-system witnesses get penalized. Cross-platform witnesses get rewarded.

Usage:
    python3 witness-independence-scorer.py demo
    python3 witness-independence-scorer.py score FILE.json
"""

import json
import sys
import math
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Attestation:
    """A single attestation/witness record."""
    attester_id: str
    platform: str           # e.g. "clawk", "agentmail", "isnad", "moltbook"
    timestamp: str          # ISO timestamp
    claim_hash: str         # What's being attested
    proof_type: str = ""    # e.g. "dkim", "ed25519", "tx_hash"
    operator: str = ""      # Who runs this agent (if known)
    model_provider: str = "" # e.g. "anthropic", "openai"


@dataclass
class IndependenceScore:
    """Result of scoring a set of attestations."""
    raw_count: int                    # Total attestations
    effective_count: float            # Independence-weighted count
    platform_diversity: float         # 0-1, unique platforms / total
    operator_diversity: float         # 0-1, unique operators / total  
    model_diversity: float            # 0-1, unique model providers / total
    temporal_spread_hours: float      # Time spread of attestations
    proof_type_diversity: float       # 0-1, unique proof types / total
    overall_score: float              # 0-1 composite
    penalties: list = field(default_factory=list)
    grade: str = ""                   # A/B/C/D/F


def score_independence(attestations: list[Attestation]) -> IndependenceScore:
    """Score a set of attestations for witness independence."""
    
    if not attestations:
        return IndependenceScore(0, 0, 0, 0, 0, 0, 0, 0, ["no attestations"], "F")
    
    n = len(attestations)
    penalties = []
    
    # Platform diversity
    platforms = set(a.platform for a in attestations)
    platform_div = len(platforms) / n if n > 0 else 0
    
    # Operator diversity (unknown operators treated as potentially same)
    operators = set(a.operator for a in attestations if a.operator)
    unknown_ops = sum(1 for a in attestations if not a.operator)
    if unknown_ops > 1:
        penalties.append(f"{unknown_ops} attesters with unknown operator (may be same entity)")
    operator_div = (len(operators) + min(unknown_ops, 1)) / n if n > 0 else 0
    
    # Model provider diversity
    models = set(a.model_provider for a in attestations if a.model_provider)
    model_div = max(len(models), 1) / n if n > 0 else 0
    
    # Proof type diversity
    proof_types = set(a.proof_type for a in attestations if a.proof_type)
    proof_div = len(proof_types) / n if n > 0 else 0
    
    # Temporal spread
    try:
        from datetime import datetime
        times = []
        for a in attestations:
            try:
                t = datetime.fromisoformat(a.timestamp.replace("Z", "+00:00"))
                times.append(t)
            except (ValueError, AttributeError):
                pass
        if len(times) >= 2:
            spread = (max(times) - min(times)).total_seconds() / 3600
        else:
            spread = 0.0
    except ImportError:
        spread = 0.0
    
    # Effective count: penalize same-platform attestations
    # Each additional attestation from same platform worth 0.25x
    platform_counts = defaultdict(int)
    for a in attestations:
        platform_counts[a.platform] += 1
    
    effective = 0.0
    for platform, count in platform_counts.items():
        # First attestation from platform = 1.0, second = 0.25, third = 0.1
        effective += 1.0
        if count > 1:
            effective += 0.25 * min(count - 1, 2)
        if count > 3:
            effective += 0.1 * (count - 3)
    
    # Same-operator penalty
    operator_counts = defaultdict(int)
    for a in attestations:
        if a.operator:
            operator_counts[a.operator] += 1
    for op, count in operator_counts.items():
        if count > 1:
            penalties.append(f"operator '{op}' controls {count} attesters (correlated failure risk)")
            effective *= (1.0 - 0.15 * (count - 1))
    
    # Burst penalty (all attestations within 60 seconds = suspicious)
    if spread < 1/60 and n > 2:  # Less than 1 minute
        penalties.append("burst: all attestations within 60 seconds")
        effective *= 0.5
    
    # Composite score
    # Weights: platform diversity most important, then operator, then proof type
    composite = (
        0.35 * platform_div +
        0.25 * operator_div +
        0.15 * model_div +
        0.15 * proof_div +
        0.10 * min(spread / 24.0, 1.0)  # Normalize to 24h
    )
    
    # Grade (requires minimum witness count)
    if composite >= 0.8 and len(platforms) >= 3 and n >= 3:
        grade = "A"
    elif composite >= 0.6 and len(platforms) >= 2 and n >= 2:
        grade = "B"
    elif composite >= 0.4 and n >= 2:
        grade = "C"
    elif n >= 2:
        grade = "D"
    else:
        grade = "F"
        if n == 1:
            penalties.append("single witness — no independence possible")
    
    return IndependenceScore(
        raw_count=n,
        effective_count=round(effective, 2),
        platform_diversity=round(platform_div, 3),
        operator_diversity=round(operator_div, 3),
        model_diversity=round(model_div, 3),
        temporal_spread_hours=round(spread, 2),
        proof_type_diversity=round(proof_div, 3),
        overall_score=round(composite, 3),
        penalties=penalties,
        grade=grade,
    )


def demo():
    """Run demo with test case 3-style attestations."""
    print("=" * 60)
    print("Witness Independence Scorer")
    print("=" * 60)
    
    # Scenario 1: TC3 — diverse witnesses
    print("\n--- Scenario 1: Test Case 3 (diverse) ---")
    tc3 = [
        Attestation("bro_agent", "clawk", "2026-02-24T07:46:00Z", "abc123",
                     "ed25519", "bro_operator", "anthropic"),
        Attestation("momo", "clawk", "2026-02-24T10:08:00Z", "abc123",
                     "ed25519", "momo_operator", "openai"),
        Attestation("braindiff", "agentmail", "2026-02-24T09:46:00Z", "abc123",
                     "dkim", "braindiff_op", "anthropic"),
        Attestation("funwolf", "clawk", "2026-02-24T08:06:00Z", "abc123",
                     "ed25519", "funwolf_op", "openai"),
    ]
    result = score_independence(tc3)
    print_result(result)
    
    # Scenario 2: Same platform, same operator (sybil)
    print("\n--- Scenario 2: Same platform, same operator (sybil) ---")
    sybil = [
        Attestation("agent_1", "clawk", "2026-02-24T07:00:00Z", "abc123",
                     "ed25519", "eve", "anthropic"),
        Attestation("agent_2", "clawk", "2026-02-24T07:00:01Z", "abc123",
                     "ed25519", "eve", "anthropic"),
        Attestation("agent_3", "clawk", "2026-02-24T07:00:02Z", "abc123",
                     "ed25519", "eve", "anthropic"),
    ]
    result = score_independence(sybil)
    print_result(result)
    
    # Scenario 3: Maximum diversity
    print("\n--- Scenario 3: Maximum diversity (gold standard) ---")
    diverse = [
        Attestation("kit", "isnad", "2026-02-24T06:00:00Z", "abc123",
                     "ed25519", "ilya", "anthropic"),
        Attestation("bro_agent", "clawk", "2026-02-24T12:00:00Z", "abc123",
                     "tx_hash", "bro_op", "openai"),
        Attestation("braindiff", "agentmail", "2026-02-24T18:00:00Z", "abc123",
                     "dkim", "braindiff_op", "google"),
        Attestation("gendolf", "moltbook", "2026-02-25T00:00:00Z", "abc123",
                     "x509", "gendolf_op", "mistral"),
    ]
    result = score_independence(diverse)
    print_result(result)
    
    # Scenario 4: Single attestation
    print("\n--- Scenario 4: Single witness ---")
    single = [
        Attestation("kit", "clawk", "2026-02-24T07:00:00Z", "abc123",
                     "ed25519", "ilya", "anthropic"),
    ]
    result = score_independence(single)
    print_result(result)


def print_result(r: IndependenceScore):
    print(f"  Grade: {r.grade}")
    print(f"  Raw count: {r.raw_count} → Effective: {r.effective_count}")
    print(f"  Platform diversity: {r.platform_diversity}")
    print(f"  Operator diversity: {r.operator_diversity}")
    print(f"  Model diversity:    {r.model_diversity}")
    print(f"  Proof type diversity: {r.proof_type_diversity}")
    print(f"  Temporal spread:    {r.temporal_spread_hours}h")
    print(f"  Overall score:      {r.overall_score}")
    if r.penalties:
        for p in r.penalties:
            print(f"  ⚠️  {p}")


def score_file(filepath: str):
    """Score attestations from JSON file."""
    with open(filepath) as f:
        data = json.load(f)
    attestations = [Attestation(**item) for item in data]
    result = score_independence(attestations)
    print_result(result)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "demo":
        demo()
    elif sys.argv[1] == "score" and len(sys.argv) > 2:
        score_file(sys.argv[2])
    else:
        print(__doc__)
