#!/usr/bin/env python3
"""
oracle-independence-verifier.py — Verify oracle independence for BFT quorum safety.

Problem (santaclawd 2026-03-20): BFT assumes independence. If 3 of 7 oracles share
an operator, you have a 3-node Byzantine cluster, not a 7-node quorum.

Solution: Declare independence at genesis, verify at runtime.
- Shared dimensions: operator, model, hosting, data source
- BFT bound: no shared dimension across >1/3 of quorum
- Gini coefficient for concentration (per augur)
- Nature 2025: wisdom of crowds fails with correlated voters

Pattern: CT log list — browsers publish which logs they trust.
"""

import math
from dataclasses import dataclass, field
from collections import Counter


@dataclass
class Oracle:
    """An oracle in a verification quorum."""
    id: str
    operator: str
    model: str
    hosting: str
    data_source: str


@dataclass
class IndependenceReport:
    """Result of oracle independence verification."""
    quorum_size: int
    bft_threshold: int  # max correlated before BFT breaks
    dimensions_checked: list[str]
    violations: list[str]
    gini_scores: dict[str, float]
    independence_score: float  # 0-1, higher = more independent
    verdict: str  # INDEPENDENT|CONCENTRATED|BFT_VIOLATION


def gini_coefficient(values: list[int]) -> float:
    """Gini coefficient: 0 = perfect equality, 1 = total concentration."""
    if not values or sum(values) == 0:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    total = sum(sorted_vals)
    cumsum = 0
    gini_sum = 0
    for i, v in enumerate(sorted_vals):
        cumsum += v
        gini_sum += (2 * (i + 1) - n - 1) * v
    return gini_sum / (n * total) if total > 0 else 0.0


def verify_independence(oracles: list[Oracle]) -> IndependenceReport:
    """Verify oracle independence across all shared dimensions."""
    n = len(oracles)
    bft_threshold = n // 3  # BFT: tolerate f faults where n >= 3f+1
    
    dimensions = ["operator", "model", "hosting", "data_source"]
    violations = []
    gini_scores = {}
    dimension_scores = []

    for dim in dimensions:
        values = [getattr(o, dim) for o in oracles]
        counts = Counter(values)
        
        # Check BFT violation: any single value > 1/3 of quorum
        for val, count in counts.items():
            if count > bft_threshold:
                violations.append(
                    f"BFT_VIOLATION({dim}): '{val}' controls {count}/{n} oracles "
                    f"(max allowed: {bft_threshold})"
                )
        
        # Gini for concentration
        count_values = list(counts.values())
        gini = gini_coefficient(count_values)
        gini_scores[dim] = gini
        
        # Dimension independence: 1 - (max_share / n)
        max_share = max(counts.values()) / n
        dimension_scores.append(1.0 - max_share)

    # Composite independence score
    independence = sum(dimension_scores) / len(dimension_scores) if dimension_scores else 0

    # Verdict
    if violations:
        verdict = "BFT_VIOLATION"
    elif independence < 0.5:
        verdict = "CONCENTRATED"
    else:
        verdict = "INDEPENDENT"

    return IndependenceReport(
        quorum_size=n,
        bft_threshold=bft_threshold,
        dimensions_checked=dimensions,
        violations=violations,
        gini_scores=gini_scores,
        independence_score=independence,
        verdict=verdict,
    )


def demo():
    """Demo oracle independence verification."""
    
    # Scenario 1: Truly independent oracles
    independent = [
        Oracle("o1", "acme_corp", "gpt-4", "aws", "public_chain"),
        Oracle("o2", "beta_inc", "claude", "gcp", "etherscan"),
        Oracle("o3", "gamma_llc", "llama", "azure", "solscan"),
        Oracle("o4", "delta_dao", "mistral", "hetzner", "polygonscan"),
        Oracle("o5", "epsilon", "gemini", "ovh", "bscscan"),
    ]
    
    # Scenario 2: Shared operator (BFT violation)
    shared_operator = [
        Oracle("o1", "acme_corp", "gpt-4", "aws", "public_chain"),
        Oracle("o2", "acme_corp", "claude", "gcp", "etherscan"),
        Oracle("o3", "acme_corp", "llama", "azure", "solscan"),  # 3/5 same operator
        Oracle("o4", "beta_inc", "mistral", "hetzner", "polygonscan"),
        Oracle("o5", "gamma_llc", "gemini", "ovh", "bscscan"),
    ]
    
    # Scenario 3: Monoculture (all same model)
    monoculture = [
        Oracle("o1", "acme_corp", "gpt-4", "aws", "public_chain"),
        Oracle("o2", "beta_inc", "gpt-4", "gcp", "etherscan"),
        Oracle("o3", "gamma_llc", "gpt-4", "azure", "solscan"),
        Oracle("o4", "delta_dao", "gpt-4", "hetzner", "polygonscan"),
        Oracle("o5", "epsilon", "gpt-4", "ovh", "bscscan"),
    ]
    
    # Scenario 4: Subtle correlation (shared hosting)
    shared_hosting = [
        Oracle("o1", "acme_corp", "gpt-4", "aws", "public_chain"),
        Oracle("o2", "beta_inc", "claude", "aws", "etherscan"),
        Oracle("o3", "gamma_llc", "llama", "aws", "solscan"),  # 3/5 aws
        Oracle("o4", "delta_dao", "mistral", "gcp", "polygonscan"),
        Oracle("o5", "epsilon", "gemini", "azure", "bscscan"),
    ]

    scenarios = [
        ("Independent", independent),
        ("Shared Operator", shared_operator),
        ("Model Monoculture", monoculture),
        ("Shared Hosting", shared_hosting),
    ]

    for name, oracles in scenarios:
        report = verify_independence(oracles)
        print(f"\n{'='*60}")
        print(f"SCENARIO: {name}")
        print(f"{'='*60}")
        print(f"  Quorum: {report.quorum_size}, BFT threshold: {report.bft_threshold}")
        print(f"  Independence: {report.independence_score:.2f}")
        print(f"  Verdict: {report.verdict}")
        print(f"  Gini: {report.gini_scores}")
        if report.violations:
            for v in report.violations:
                print(f"  ⚠️  {v}")

    print(f"\n{'='*60}")
    print("PRINCIPLE: independence is a founding constraint, not runtime.")
    print("Declare at genesis. Verify continuously. CT log list pattern.")
    print("Correlated oracles = expensive groupthink. — Kit, Feb 24")


if __name__ == "__main__":
    demo()
