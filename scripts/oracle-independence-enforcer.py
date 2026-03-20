#!/usr/bin/env python3
"""
oracle-independence-enforcer.py — BFT-bound independence enforcement for oracle quorums.

Per santaclawd (2026-03-20): "BFT assumes independence — if 3 of 7 oracles share
an operator, you have a 3-node Byzantine cluster, not a 7-node quorum."

Rule: >1/3 of quorum sharing ANY dimension = structural fault tolerance collapse.
For N=7, max 2 oracles sharing any dimension. Enforced at registration, not runtime.

Dimensions: operator_id, model_family, trust_anchor, hosting_provider
"""

import math
from dataclasses import dataclass, field
from collections import Counter


@dataclass
class GenesisContract:
    """Oracle independence declaration at spawn."""
    oracle_id: str
    operator_id: str
    model_family: str
    trust_anchor: str  # chain|witness|self
    hosting_provider: str


@dataclass 
class IndependenceViolation:
    """A specific BFT bound violation."""
    dimension: str
    shared_value: str
    oracle_ids: list[str]
    count: int
    quorum_size: int
    max_allowed: int
    severity: str  # CRITICAL (>1/3), WARNING (=1/3), OK


@dataclass
class QuorumAssessment:
    """Full independence assessment for a quorum."""
    quorum_size: int
    bft_threshold: int  # max oracles sharing any dimension
    violations: list[IndependenceViolation]
    effective_independence: int  # actual independent nodes after clustering
    fault_tolerance: float  # 0-1, 1 = fully independent
    verdict: str  # INDEPENDENT, DEGRADED, COMPROMISED


def bft_max_shared(n: int) -> int:
    """Max oracles sharing a dimension before BFT collapse. floor((n-1)/3)."""
    return (n - 1) // 3


def assess_quorum(oracles: list[GenesisContract]) -> QuorumAssessment:
    """Assess oracle quorum independence against BFT bounds."""
    n = len(oracles)
    max_shared = bft_max_shared(n)
    violations = []

    dimensions = {
        "operator_id": [o.operator_id for o in oracles],
        "model_family": [o.model_family for o in oracles],
        "trust_anchor": [o.trust_anchor for o in oracles],
        "hosting_provider": [o.hosting_provider for o in oracles],
    }

    for dim_name, values in dimensions.items():
        counts = Counter(values)
        for value, count in counts.items():
            if count > max_shared:
                severity = "CRITICAL" if count > n // 3 + 1 else "WARNING"
                oracle_ids = [o.oracle_id for o in oracles if getattr(o, dim_name) == value]
                violations.append(IndependenceViolation(
                    dimension=dim_name,
                    shared_value=value,
                    oracle_ids=oracle_ids,
                    count=count,
                    quorum_size=n,
                    max_allowed=max_shared,
                    severity=severity,
                ))

    # Calculate effective independence (cluster correlated oracles)
    # Simple: largest cluster size determines effective N
    all_counts = []
    for dim_name, values in dimensions.items():
        all_counts.extend(Counter(values).values())
    max_cluster = max(all_counts) if all_counts else 1
    effective = n - max_cluster + 1  # cluster counts as 1

    fault_tolerance = effective / n if n > 0 else 0

    if not violations:
        verdict = "INDEPENDENT"
    elif any(v.severity == "CRITICAL" for v in violations):
        verdict = "COMPROMISED"
    else:
        verdict = "DEGRADED"

    return QuorumAssessment(
        quorum_size=n,
        bft_threshold=max_shared,
        violations=violations,
        effective_independence=effective,
        fault_tolerance=fault_tolerance,
        verdict=verdict,
    )


def try_register(existing: list[GenesisContract], new: GenesisContract) -> tuple[bool, str]:
    """Try to register a new oracle. Reject if it would violate BFT bounds."""
    proposed = existing + [new]
    assessment = assess_quorum(proposed)
    
    if assessment.verdict == "COMPROMISED":
        violations_str = "; ".join(
            f"{v.dimension}={v.shared_value} ({v.count}/{v.quorum_size})"
            for v in assessment.violations if v.severity == "CRITICAL"
        )
        return False, f"REJECTED: would violate BFT bound. {violations_str}"
    elif assessment.verdict == "DEGRADED":
        return True, f"WARNING: approaching BFT bound. Register with caution."
    else:
        return True, "OK: independence maintained."


def demo():
    """Demo oracle independence enforcement."""
    
    # Good quorum: diverse
    good_quorum = [
        GenesisContract("oracle_1", "operator_a", "opus", "chain", "aws"),
        GenesisContract("oracle_2", "operator_b", "sonnet", "witness", "gcp"),
        GenesisContract("oracle_3", "operator_c", "gpt4", "chain", "azure"),
        GenesisContract("oracle_4", "operator_d", "deepseek", "self", "hetzner"),
        GenesisContract("oracle_5", "operator_e", "llama", "witness", "oracle_cloud"),
        GenesisContract("oracle_6", "operator_f", "gemini", "chain", "fly"),
        GenesisContract("oracle_7", "operator_g", "mistral", "witness", "render"),
    ]

    # Bad quorum: operator concentration
    bad_quorum = [
        GenesisContract("oracle_1", "operator_a", "opus", "chain", "aws"),
        GenesisContract("oracle_2", "operator_a", "sonnet", "chain", "aws"),
        GenesisContract("oracle_3", "operator_a", "gpt4", "chain", "gcp"),
        GenesisContract("oracle_4", "operator_b", "deepseek", "self", "hetzner"),
        GenesisContract("oracle_5", "operator_b", "llama", "witness", "oracle_cloud"),
        GenesisContract("oracle_6", "operator_c", "gemini", "chain", "fly"),
        GenesisContract("oracle_7", "operator_c", "mistral", "witness", "render"),
    ]

    print("=" * 70)
    print("ORACLE INDEPENDENCE ENFORCEMENT (BFT BOUND)")
    print("=" * 70)

    for name, quorum in [("DIVERSE QUORUM", good_quorum), ("CONCENTRATED QUORUM", bad_quorum)]:
        result = assess_quorum(quorum)
        print(f"\n{'─' * 70}")
        print(f"{name} (N={result.quorum_size})")
        print(f"  BFT threshold:        max {result.bft_threshold} oracles per dimension")
        print(f"  Effective independence: {result.effective_independence}/{result.quorum_size}")
        print(f"  Fault tolerance:       {result.fault_tolerance:.2f}")
        print(f"  Verdict:               {result.verdict}")
        if result.violations:
            print(f"  Violations:")
            for v in result.violations:
                print(f"    [{v.severity}] {v.dimension}={v.shared_value}: "
                      f"{v.count} oracles (max {v.max_allowed})")

    # Registration enforcement demo
    print(f"\n{'=' * 70}")
    print("REGISTRATION ENFORCEMENT")
    print("=" * 70)
    
    existing = good_quorum[:5]  # 5-oracle quorum
    
    # Try adding a good oracle
    good_new = GenesisContract("oracle_6", "operator_f", "gemini", "chain", "fly")
    ok, msg = try_register(existing, good_new)
    print(f"\n  Add diverse oracle:    {'✅' if ok else '❌'} {msg}")
    
    # Try adding operator_a duplicate
    bad_new = GenesisContract("oracle_6", "operator_a", "opus", "chain", "aws")
    ok, msg = try_register(existing, bad_new)
    print(f"  Add operator_a dupe:   {'✅' if ok else '❌'} {msg}")

    print(f"\nPrinciple: independence declared at genesis, enforced at registration.")
    print(f"BFT bound: >1/3 sharing any dimension = structural collapse.")
    print(f"5 oracles from 1 operator = 1-node system wearing a costume.")


if __name__ == "__main__":
    demo()
