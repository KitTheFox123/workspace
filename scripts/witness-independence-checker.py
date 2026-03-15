#!/usr/bin/env python3
"""
witness-independence-checker.py — Verify operator independence for L3.5 witness sets.

Per santaclawd (2026-03-15): N=3 same org = trust theater.
Chrome CT Policy requires SCTs from distinct log operators.
Nature 2025: correlated voters = expensive groupthink.

Independence criteria:
1. Distinct key material (no shared private keys)
2. Distinct infrastructure (no shared hosting/cloud account)
3. No shared funding source
4. Distinct organizational control
"""

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json


class IndependenceLevel(Enum):
    FULL = "full"           # All criteria met
    PARTIAL = "partial"     # Some shared attributes
    CORRELATED = "correlated"  # Likely same operator
    SYBIL = "sybil"         # Definitely same operator


@dataclass
class WitnessOperator:
    operator_id: str
    name: str
    key_fingerprint: str
    infrastructure_provider: str  # e.g., "aws-us-east-1", "self-hosted-de"
    funding_source: str           # e.g., "org-a", "grant-xyz", "self-funded"
    organization: str
    jurisdiction: str             # Legal jurisdiction


@dataclass
class IndependenceReport:
    pair: tuple[str, str]
    level: IndependenceLevel
    shared_attributes: list[str]
    score: float  # 0.0 = sybil, 1.0 = fully independent

    def to_dict(self):
        return {
            "pair": list(self.pair),
            "level": self.level.value,
            "shared_attributes": self.shared_attributes,
            "score": self.score,
        }


def check_pairwise_independence(a: WitnessOperator, b: WitnessOperator) -> IndependenceReport:
    """Check independence between two witness operators."""
    shared = []
    score = 1.0

    # Same key = definitely sybil
    if a.key_fingerprint == b.key_fingerprint:
        return IndependenceReport(
            pair=(a.operator_id, b.operator_id),
            level=IndependenceLevel.SYBIL,
            shared_attributes=["key_material"],
            score=0.0,
        )

    # Same organization = correlated
    if a.organization == b.organization:
        shared.append("organization")
        score -= 0.5

    # Same infrastructure = correlated failure mode
    if a.infrastructure_provider == b.infrastructure_provider:
        shared.append("infrastructure")
        score -= 0.25

    # Same funding = incentive alignment
    if a.funding_source == b.funding_source:
        shared.append("funding_source")
        score -= 0.2

    # Same jurisdiction = regulatory correlation
    if a.jurisdiction == b.jurisdiction:
        shared.append("jurisdiction")
        score -= 0.05  # Minor — common case

    score = max(score, 0.0)

    if score == 0.0:
        level = IndependenceLevel.SYBIL
    elif score < 0.5:
        level = IndependenceLevel.CORRELATED
    elif score < 0.9:
        level = IndependenceLevel.PARTIAL
    else:
        level = IndependenceLevel.FULL

    return IndependenceReport(
        pair=(a.operator_id, b.operator_id),
        level=level,
        shared_attributes=shared,
        score=score,
    )


def check_witness_set(operators: list[WitnessOperator], min_independent: int = 2) -> dict:
    """
    Check if a witness set meets independence requirements.
    
    Chrome CT requires SCTs from distinct log operators.
    We require min_independent truly independent witnesses.
    """
    n = len(operators)
    reports = []
    
    for i in range(n):
        for j in range(i + 1, n):
            report = check_pairwise_independence(operators[i], operators[j])
            reports.append(report)

    # Count independent clusters
    # Simple: find max set where all pairs are FULL or PARTIAL
    independent_count = 0
    correlated_groups: dict[str, list[str]] = {}
    
    for op in operators:
        group_key = op.organization  # Simplification: org = correlation group
        if group_key not in correlated_groups:
            correlated_groups[group_key] = []
            independent_count += 1
        correlated_groups[group_key].append(op.operator_id)

    meets_requirement = independent_count >= min_independent
    
    min_score = min(r.score for r in reports) if reports else 0.0
    avg_score = sum(r.score for r in reports) / len(reports) if reports else 0.0

    return {
        "total_witnesses": n,
        "independent_operators": independent_count,
        "min_required": min_independent,
        "meets_requirement": meets_requirement,
        "min_pairwise_score": round(min_score, 3),
        "avg_pairwise_score": round(avg_score, 3),
        "correlated_groups": {k: v for k, v in correlated_groups.items()},
        "pairwise_reports": [r.to_dict() for r in reports],
    }


def demo():
    print("=== Witness Independence Checker ===\n")

    # Scenario 1: Truly independent
    print("📋 Scenario 1: Three independent operators")
    ops_good = [
        WitnessOperator("op-1", "Kit's Log", "key-aaa", "hetzner-de", "self-funded", "Kit", "DE"),
        WitnessOperator("op-2", "Gendolf's Log", "key-bbb", "aws-us-east", "grant-123", "Gendolf", "US"),
        WitnessOperator("op-3", "Holly's Log", "key-ccc", "digitalocean-nl", "self-funded", "Holly", "NL"),
    ]
    result = check_witness_set(ops_good)
    print(f"   Independent operators: {result['independent_operators']}/{result['total_witnesses']}")
    print(f"   Meets requirement: {'✅' if result['meets_requirement'] else '❌'}")
    print(f"   Avg independence: {result['avg_pairwise_score']:.1%}")
    print()

    # Scenario 2: Same org, different keys (trust theater)
    print("📋 Scenario 2: Same org, different keys (trust theater)")
    ops_theater = [
        WitnessOperator("op-a", "Log Alpha", "key-111", "aws-us-east", "corp-budget", "MegaCorp", "US"),
        WitnessOperator("op-b", "Log Beta", "key-222", "aws-us-east", "corp-budget", "MegaCorp", "US"),
        WitnessOperator("op-c", "Log Gamma", "key-333", "aws-us-west", "corp-budget", "MegaCorp", "US"),
    ]
    result = check_witness_set(ops_theater)
    print(f"   Independent operators: {result['independent_operators']}/{result['total_witnesses']}")
    print(f"   Meets requirement: {'✅' if result['meets_requirement'] else '❌'}")
    print(f"   Avg independence: {result['avg_pairwise_score']:.1%}")
    for r in result['pairwise_reports']:
        print(f"   {r['pair'][0]} ↔ {r['pair'][1]}: {r['level']} (shared: {', '.join(r['shared_attributes'])})")
    print()

    # Scenario 3: Same key (sybil)
    print("📋 Scenario 3: Same key material (sybil attack)")
    ops_sybil = [
        WitnessOperator("op-x", "Real Log", "key-same", "aws-eu", "self", "Honest", "DE"),
        WitnessOperator("op-y", "Fake Log", "key-same", "gcp-us", "venture", "Dishonest", "US"),
    ]
    result = check_witness_set(ops_sybil)
    print(f"   Independent operators: {result['independent_operators']}/{result['total_witnesses']}")
    print(f"   Meets requirement: {'✅' if result['meets_requirement'] else '❌'}")
    print(f"   Min pairwise score: {result['min_pairwise_score']}")
    print()

    print("--- Design Principles ---")
    print("Chrome CT: SCTs from DISTINCT log operators.")
    print("N=3 same org = trust theater (santaclawd).")
    print("Correlated voters = expensive groupthink (Nature 2025).")
    print("Independence = key + infra + funding + org all distinct.")


if __name__ == "__main__":
    demo()
