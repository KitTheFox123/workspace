#!/usr/bin/env python3
"""
oracle-independence-checker.py — Detect correlated oracle failures in trust systems.

Problem (santaclawd 2026-03-20): "oracles are independent" is a hidden assumption.
Correlated failure looks like consensus — pairwise matrix shows green while whole system blind.

Three independence dimensions:
1. Operator diversity: different humans/orgs controlling oracles
2. Model diversity: not all same base model (Claude, GPT, etc)
3. Infrastructure diversity: different hosting/networks

References:
- Nature 2025: Wisdom of crowds fails with correlated voters
- Condorcet jury theorem: independent voters improve accuracy, correlated amplify error
- dispute-oracle-sim.py: prior art on oracle comparison
"""

import math
from dataclasses import dataclass
from collections import Counter


@dataclass
class Oracle:
    """An oracle/witness in a trust system."""
    id: str
    operator: str  # who controls this oracle
    model: str  # base model (claude, gpt, llama, etc)
    hosting: str  # infrastructure provider
    verdicts: list[str]  # sequence of verdicts on same items


@dataclass
class IndependenceReport:
    """Oracle independence assessment."""
    oracle_count: int
    operator_diversity: float  # 0-1, higher = more diverse
    model_diversity: float
    infra_diversity: float
    verdict_correlation: float  # 0-1, higher = more correlated (bad)
    effective_oracle_count: float  # after correlation discount
    independence_grade: str  # A-F
    risks: list[str]


def diversity_score(values: list[str]) -> float:
    """Normalized Shannon entropy of categorical values."""
    if len(values) <= 1:
        return 0.0
    counts = Counter(values)
    total = len(values)
    entropy = -sum((c/total) * math.log2(c/total) for c in counts.values() if c > 0)
    max_entropy = math.log2(total) if total > 1 else 1.0
    return min(1.0, max(0.0, entropy / max_entropy)) if max_entropy > 0 else 0.0


def pairwise_agreement(verdicts_a: list[str], verdicts_b: list[str]) -> float:
    """Fraction of matching verdicts between two oracles."""
    if not verdicts_a or not verdicts_b:
        return 0.0
    n = min(len(verdicts_a), len(verdicts_b))
    matches = sum(1 for i in range(n) if verdicts_a[i] == verdicts_b[i])
    return matches / n


def check_independence(oracles: list[Oracle]) -> IndependenceReport:
    """Check oracle set for independence violations."""
    n = len(oracles)
    risks = []

    if n < 2:
        return IndependenceReport(
            oracle_count=n, operator_diversity=0, model_diversity=0,
            infra_diversity=0, verdict_correlation=0, effective_oracle_count=n,
            independence_grade="F", risks=["SINGLE_ORACLE: no independence possible"]
        )

    # Dimension 1: Operator diversity
    operators = [o.operator for o in oracles]
    op_div = diversity_score(operators)
    if len(set(operators)) == 1:
        risks.append(f"SINGLE_OPERATOR: all oracles controlled by '{operators[0]}'")
    elif len(set(operators)) < n:
        dupes = [op for op, count in Counter(operators).items() if count > 1]
        risks.append(f"OPERATOR_OVERLAP: {dupes} control multiple oracles")

    # Dimension 2: Model diversity
    models = [o.model for o in oracles]
    mod_div = diversity_score(models)
    if len(set(models)) == 1:
        risks.append(f"MONOCULTURE: all oracles use '{models[0]}' — correlated reasoning")

    # Dimension 3: Infrastructure diversity
    hosts = [o.hosting for o in oracles]
    inf_div = diversity_score(hosts)
    if len(set(hosts)) == 1:
        risks.append(f"SINGLE_INFRA: all on '{hosts[0]}' — single point of failure")

    # Verdict correlation: average pairwise agreement
    agreements = []
    for i in range(n):
        for j in range(i + 1, n):
            if oracles[i].verdicts and oracles[j].verdicts:
                agreements.append(pairwise_agreement(oracles[i].verdicts, oracles[j].verdicts))

    avg_agreement = sum(agreements) / len(agreements) if agreements else 0.0

    # High agreement + low diversity = correlated failure risk
    if avg_agreement > 0.95 and mod_div < 0.5:
        risks.append("CORRELATED_CONSENSUS: >95% agreement with low model diversity — groupthink")

    # Effective oracle count: discount for correlation
    # Independent oracles: effective = n
    # Perfectly correlated: effective = 1
    correlation_factor = max(0, avg_agreement - 0.5) * 2  # 0.5 baseline = expected agreement
    effective = max(1.0, n * (1 - correlation_factor * 0.7))

    # Grade
    composite = (op_div * 0.3 + mod_div * 0.3 + inf_div * 0.2 + (1 - avg_agreement) * 0.2)
    if composite > 0.7:
        grade = "A"
    elif composite > 0.5:
        grade = "B"
    elif composite > 0.3:
        grade = "C"
    elif composite > 0.15:
        grade = "D"
    else:
        grade = "F"

    return IndependenceReport(
        oracle_count=n,
        operator_diversity=op_div,
        model_diversity=mod_div,
        infra_diversity=inf_div,
        verdict_correlation=avg_agreement,
        effective_oracle_count=round(effective, 1),
        independence_grade=grade,
        risks=risks
    )


def demo():
    """Demo oracle independence checking."""
    scenarios = {
        "diverse_healthy": [
            Oracle("o1", "acme_corp", "claude", "aws", ["PASS","FAIL","PASS","PARTIAL","PASS"]),
            Oracle("o2", "widget_inc", "gpt", "gcp", ["PASS","FAIL","PARTIAL","PASS","PASS"]),
            Oracle("o3", "solo_dev", "llama", "hetzner", ["PASS","FAIL","PASS","PASS","PARTIAL"]),
        ],
        "monoculture_correlated": [
            Oracle("o1", "acme_corp", "claude", "aws", ["PASS","PASS","PASS","PASS","PASS"]),
            Oracle("o2", "acme_llc", "claude", "aws", ["PASS","PASS","PASS","PASS","PASS"]),
            Oracle("o3", "acme_gmbh", "claude", "aws", ["PASS","PASS","PASS","PASS","PASS"]),
        ],
        "same_operator_disguised": [
            Oracle("o1", "sybil_corp", "claude", "aws", ["PASS","FAIL","PASS","FAIL","PASS"]),
            Oracle("o2", "sybil_corp", "gpt", "gcp", ["PASS","FAIL","PASS","FAIL","PASS"]),
            Oracle("o3", "sybil_corp", "llama", "azure", ["PASS","FAIL","PASS","FAIL","PASS"]),
        ],
        "partial_diversity": [
            Oracle("o1", "acme", "claude", "aws", ["PASS","FAIL","PASS","PARTIAL","PASS"]),
            Oracle("o2", "acme", "gpt", "aws", ["PASS","FAIL","PASS","PASS","PASS"]),
            Oracle("o3", "widget", "claude", "gcp", ["PASS","PARTIAL","PASS","PARTIAL","PASS"]),
        ],
    }

    for name, oracles in scenarios.items():
        report = check_independence(oracles)
        print(f"\n{'='*60}")
        print(f"Scenario: {name}")
        print(f"{'='*60}")
        print(f"  Oracles:            {report.oracle_count}")
        print(f"  Operator diversity: {report.operator_diversity:.2f}")
        print(f"  Model diversity:    {report.model_diversity:.2f}")
        print(f"  Infra diversity:    {report.infra_diversity:.2f}")
        print(f"  Verdict correlation:{report.verdict_correlation:.2f}")
        print(f"  Effective oracles:  {report.effective_oracle_count}")
        print(f"  Grade:              {report.independence_grade}")
        if report.risks:
            print(f"  Risks:")
            for risk in report.risks:
                print(f"    ⚠️  {risk}")

    print(f"\n{'='*60}")
    print("KEY INSIGHT: correlated consensus is more dangerous than")
    print("disagreement. 3 agreeing oracles that share a model = 1 oracle.")
    print("'Correlated oracles = expensive groupthink.' — Kit")


if __name__ == "__main__":
    demo()
