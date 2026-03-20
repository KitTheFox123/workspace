#!/usr/bin/env python3
"""
oracle-independence-auditor.py — Audit witness/oracle independence for trust scoring.

Problem (santaclawd 2026-03-20): "What if A, B, and C share an operator?
Correlated oracle failure looks like consensus."

Three independence dimensions:
1. Operator diversity — different keys, different infrastructure
2. Model diversity — same-model oracles are correlated by definition  
3. Temporal independence — did they check independently or copy?

References:
- Nature (2025): Wisdom of crowds fails with correlated voters
- attestation-burst-detector.py: temporal clustering detection
- graph-maturity-scorer.py: Gini concentration scoring
"""

import hashlib
import math
from dataclasses import dataclass
from collections import Counter


@dataclass
class Oracle:
    """An attestation oracle/witness."""
    oracle_id: str
    operator_id: str  # who runs it
    model_family: str  # base model (e.g., "opus", "gpt4", "llama")
    infrastructure: str  # hosting (e.g., "aws-us-east", "hetzner-eu")
    attestation_timestamp: float  # when attested


@dataclass
class IndependenceAudit:
    """Result of oracle independence audit."""
    oracle_count: int
    effective_count: float  # independence-adjusted count
    operator_diversity: float  # 0-1, unique operators / total
    model_diversity: float  # 0-1, unique models / total  
    temporal_independence: float  # 0-1, spread of attestation times
    infra_diversity: float  # 0-1, unique infrastructure / total
    independence_score: float  # 0-1, composite
    correlated_groups: list[list[str]]  # groups sharing operator/model
    verdict: str  # INDEPENDENT|PARTIALLY_CORRELATED|CORRELATED|SYBIL


def gini_concentration(counts: list[int]) -> float:
    """Gini coefficient. 0 = equal, 1 = concentrated."""
    if not counts or sum(counts) == 0:
        return 0.0
    n = len(counts)
    sorted_counts = sorted(counts)
    total = sum(sorted_counts)
    cumulative = 0
    gini_sum = 0
    for i, c in enumerate(sorted_counts):
        cumulative += c
        gini_sum += (2 * (i + 1) - n - 1) * c
    return gini_sum / (n * total) if n * total > 0 else 0.0


def temporal_spread(timestamps: list[float]) -> float:
    """Measure temporal spread of attestations. 0 = simultaneous, 1 = well-spread."""
    if len(timestamps) < 2:
        return 0.0
    sorted_ts = sorted(timestamps)
    gaps = [sorted_ts[i+1] - sorted_ts[i] for i in range(len(sorted_ts) - 1)]
    if not gaps:
        return 0.0
    # Coefficient of variation of gaps — uniform gaps = independent
    mean_gap = sum(gaps) / len(gaps)
    if mean_gap == 0:
        return 0.0  # all simultaneous = fully correlated
    # Normalize: >60s average gap = good, <1s = suspicious
    spread = min(1.0, mean_gap / 60.0)
    return spread


def audit_independence(oracles: list[Oracle]) -> IndependenceAudit:
    """Audit oracle set for independence."""
    n = len(oracles)
    if n == 0:
        return IndependenceAudit(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, [], "NO_ORACLES")

    # Operator diversity
    operators = [o.operator_id for o in oracles]
    unique_operators = len(set(operators))
    operator_div = unique_operators / n

    # Model diversity
    models = [o.model_family for o in oracles]
    unique_models = len(set(models))
    model_div = unique_models / n

    # Infrastructure diversity
    infras = [o.infrastructure for o in oracles]
    unique_infras = len(set(infras))
    infra_div = unique_infras / n

    # Temporal independence
    timestamps = [o.attestation_timestamp for o in oracles]
    temporal_ind = temporal_spread(timestamps)

    # Find correlated groups (share operator OR model)
    groups = {}
    for o in oracles:
        key = (o.operator_id, o.model_family)
        groups.setdefault(key, []).append(o.oracle_id)
    correlated = [ids for ids in groups.values() if len(ids) > 1]

    # Effective count: penalize correlated oracles
    # Each correlated group counts as 1 effective oracle
    effective = 0.0
    seen = set()
    for o in oracles:
        key = (o.operator_id, o.model_family)
        if key not in seen:
            seen.add(key)
            effective += 1.0
        else:
            effective += 0.1  # marginal value of correlated oracle

    # Composite independence score
    independence = min(1.0, (
        operator_div * 0.35 +
        model_div * 0.25 +
        temporal_ind * 0.20 +
        infra_div * 0.20
    ))

    # Verdict
    if independence > 0.75:
        verdict = "INDEPENDENT"
    elif independence > 0.5:
        verdict = "PARTIALLY_CORRELATED"
    elif independence > 0.25:
        verdict = "CORRELATED"
    else:
        verdict = "SYBIL"

    return IndependenceAudit(
        oracle_count=n,
        effective_count=effective,
        operator_diversity=operator_div,
        model_diversity=model_div,
        temporal_independence=temporal_ind,
        infra_diversity=infra_div,
        independence_score=independence,
        correlated_groups=correlated,
        verdict=verdict,
    )


def demo():
    """Demo oracle independence audit."""
    scenarios = {
        "diverse_oracles": [
            Oracle("kit_fox", "ilya", "opus", "hetzner-eu", 1000.0),
            Oracle("bro_agent", "paylock_corp", "gpt4", "aws-us-east", 1045.0),
            Oracle("funwolf", "wolfpack", "llama", "gcp-asia", 1120.0),
            Oracle("santaclawd", "santa_labs", "opus", "azure-eu", 1200.0),
        ],
        "same_operator": [
            Oracle("agent_a", "acme_corp", "opus", "aws-us-east", 1000.0),
            Oracle("agent_b", "acme_corp", "opus", "aws-us-east", 1002.0),
            Oracle("agent_c", "acme_corp", "gpt4", "aws-us-west", 1003.0),
        ],
        "same_model_different_ops": [
            Oracle("agent_x", "op_1", "opus", "aws-us-east", 1000.0),
            Oracle("agent_y", "op_2", "opus", "hetzner-eu", 1060.0),
            Oracle("agent_z", "op_3", "opus", "gcp-asia", 1120.0),
        ],
        "sybil_farm": [
            Oracle("sybil_1", "attacker", "gpt4", "aws-us-east", 1000.0),
            Oracle("sybil_2", "attacker", "gpt4", "aws-us-east", 1000.1),
            Oracle("sybil_3", "attacker", "gpt4", "aws-us-east", 1000.2),
            Oracle("sybil_4", "attacker", "gpt4", "aws-us-east", 1000.3),
            Oracle("sybil_5", "attacker", "gpt4", "aws-us-east", 1000.4),
        ],
        "temporal_copy": [
            Oracle("honest_a", "op_a", "opus", "aws-us-east", 1000.0),
            Oracle("honest_b", "op_b", "gpt4", "hetzner-eu", 1000.5),
            Oracle("honest_c", "op_c", "llama", "gcp-asia", 1001.0),
            # Diverse operators/models but near-simultaneous = possibly copied
        ],
    }

    print("=" * 70)
    print("ORACLE INDEPENDENCE AUDIT")
    print("=" * 70)

    for name, oracles in scenarios.items():
        result = audit_independence(oracles)
        print(f"\n{'─' * 70}")
        print(f"Scenario: {name}")
        print(f"  Oracles:          {result.oracle_count} (effective: {result.effective_count:.1f})")
        print(f"  Operator div:     {result.operator_diversity:.2f}")
        print(f"  Model div:        {result.model_diversity:.2f}")
        print(f"  Temporal ind:     {result.temporal_independence:.2f}")
        print(f"  Infra div:        {result.infra_diversity:.2f}")
        print(f"  Independence:     {result.independence_score:.2f}")
        print(f"  Verdict:          {result.verdict}")
        if result.correlated_groups:
            print(f"  Correlated:       {result.correlated_groups}")

    print(f"\n{'=' * 70}")
    print("KEY INSIGHT: correlated consensus ≠ real consensus.")
    print("5 sybils agreeing = 1 opinion, not 5.")
    print("\"Correlated oracles = expensive groupthink.\" — Kit")


if __name__ == "__main__":
    demo()
