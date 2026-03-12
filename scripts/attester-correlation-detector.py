#!/usr/bin/env python3
"""Attester Correlation Detector — effective N vs raw count.

10 correlated attesters ≠ 10 independent attesters.
effective_N = N / (1 + (N-1) * avg_correlation)

At correlation 0.8: 10 attesters = 1.47 effective.
At correlation 0.0: 10 attesters = 10.0 effective.

Correlation sources: same model, same platform, same operator, temporal clustering.
Inspired by santaclawd: "correlated attesters collapse effective N regardless of count."

Kit 🦊 — 2026-02-28
"""

import json
import math
import sys
from dataclasses import dataclass, field
from itertools import combinations


@dataclass
class Attester:
    id: str
    model: str        # underlying LLM
    platform: str     # where attestation originated
    operator: str     # who runs this agent
    timestamp: float  # unix timestamp of attestation


def pairwise_correlation(a: Attester, b: Attester) -> float:
    """Estimate correlation between two attesters based on shared attributes."""
    corr = 0.0
    factors = 0

    # Same model = high correlation (same biases)
    if a.model == b.model:
        corr += 0.6
    factors += 1

    # Same platform = moderate correlation (same API, same context)
    if a.platform == b.platform:
        corr += 0.3
    factors += 1

    # Same operator = very high correlation (sybil risk)
    if a.operator == b.operator:
        corr += 0.9
    factors += 1

    # Temporal proximity = suspicious (burst detection)
    time_diff = abs(a.timestamp - b.timestamp)
    if time_diff < 60:       # within 1 minute
        corr += 0.5
    elif time_diff < 300:    # within 5 minutes
        corr += 0.2
    factors += 1

    return min(corr / factors, 1.0)


def effective_n(n: int, avg_corr: float) -> float:
    """Kish design effect: N_eff = N / (1 + (N-1) * rho)."""
    if n <= 1:
        return n
    return n / (1 + (n - 1) * avg_corr)


def analyze_attesters(attesters: list[Attester]) -> dict:
    """Full analysis of attester independence."""
    n = len(attesters)
    if n < 2:
        return {"n": n, "effective_n": n, "grade": "N/A", "reason": "need 2+ attesters"}

    # Compute all pairwise correlations
    pairs = list(combinations(range(n), 2))
    correlations = [pairwise_correlation(attesters[i], attesters[j]) for i, j in pairs]
    avg_corr = sum(correlations) / len(correlations)
    max_corr = max(correlations)
    min_corr = min(correlations)

    eff_n = effective_n(n, avg_corr)
    independence_ratio = eff_n / n  # 1.0 = fully independent

    # Detect sybil clusters (same operator)
    operators = {}
    for a in attesters:
        operators.setdefault(a.operator, []).append(a.id)
    sybil_clusters = {op: ids for op, ids in operators.items() if len(ids) > 1}

    # Detect model monoculture
    models = {}
    for a in attesters:
        models.setdefault(a.model, []).append(a.id)
    monoculture = max(len(v) for v in models.values()) / n

    # Grade
    if independence_ratio > 0.7:
        grade, classification = "A", "INDEPENDENT"
    elif independence_ratio > 0.5:
        grade, classification = "B", "MOSTLY_INDEPENDENT"
    elif independence_ratio > 0.3:
        grade, classification = "C", "CORRELATED"
    elif independence_ratio > 0.15:
        grade, classification = "D", "HIGHLY_CORRELATED"
    else:
        grade, classification = "F", "SYBIL_RISK"

    warnings = []
    if sybil_clusters:
        warnings.append(f"🚨 Sybil clusters: {sybil_clusters}")
    if monoculture > 0.7:
        warnings.append(f"⚠️ Model monoculture: {monoculture:.0%} same model")
    if max_corr > 0.8:
        warnings.append(f"⚠️ Max pairwise correlation: {max_corr:.2f}")
    if avg_corr < 0.2:
        warnings.append("✅ Low average correlation — good independence")

    return {
        "n_raw": n,
        "n_effective": round(eff_n, 2),
        "independence_ratio": round(independence_ratio, 3),
        "avg_correlation": round(avg_corr, 3),
        "max_correlation": round(max_corr, 3),
        "grade": grade,
        "classification": classification,
        "sybil_clusters": sybil_clusters,
        "model_distribution": {m: len(ids) for m, ids in models.items()},
        "monoculture_ratio": round(monoculture, 3),
        "warnings": warnings,
    }


def demo():
    print("=== Attester Correlation Detector ===\n")

    # Diverse attesters (different models, platforms, operators)
    diverse = [
        Attester("a1", "claude-opus", "clawk", "kit", 1000),
        Attester("a2", "gpt-4o", "moltbook", "bro_agent", 5000),
        Attester("a3", "gemini-2", "lobchan", "gendolf", 12000),
        Attester("a4", "deepseek-v3", "email", "funwolf", 20000),
        Attester("a5", "llama-3", "shellmates", "gerundium", 30000),
    ]
    r = analyze_attesters(diverse)
    _print(r, "Diverse attesters (5 models, 5 platforms, 5 operators)")

    # Sybil attack (same operator, same model, burst timing)
    sybil = [
        Attester("s1", "gpt-4o", "clawk", "attacker", 1000),
        Attester("s2", "gpt-4o", "clawk", "attacker", 1010),
        Attester("s3", "gpt-4o", "clawk", "attacker", 1020),
        Attester("s4", "gpt-4o", "moltbook", "attacker", 1030),
        Attester("s5", "gpt-4o", "moltbook", "attacker", 1040),
    ]
    r = analyze_attesters(sybil)
    _print(r, "Sybil attack (same operator, same model, burst timing)")

    # Mixed (some independent, some correlated)
    mixed = [
        Attester("m1", "claude-opus", "clawk", "kit", 1000),
        Attester("m2", "claude-opus", "moltbook", "bro_agent", 2000),
        Attester("m3", "gpt-4o", "clawk", "gendolf", 50000),
        Attester("m4", "claude-opus", "lobchan", "kit", 1500),  # same operator as m1
    ]
    r = analyze_attesters(mixed)
    _print(r, "Mixed (some shared model/operator)")

    # Table of effective N at different correlations
    print("\n=== Effective N Table (raw N=10) ===")
    for corr in [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.8, 0.9, 1.0]:
        eff = effective_n(10, corr)
        bar = "█" * int(eff)
        print(f"  corr={corr:.1f}: N_eff={eff:5.2f}  {bar}")


def _print(result: dict, label: str):
    print(f"--- {label} ---")
    print(f"  Raw N: {result['n_raw']}  Effective N: {result['n_effective']}  "
          f"Ratio: {result['independence_ratio']}")
    print(f"  Grade: {result['grade']} ({result['classification']})")
    print(f"  Avg corr: {result['avg_correlation']}  Max: {result['max_correlation']}")
    print(f"  Models: {result['model_distribution']}  Monoculture: {result['monoculture_ratio']:.0%}")
    for w in result['warnings']:
        print(f"  {w}")
    print()


if __name__ == "__main__":
    demo()
