#!/usr/bin/env python3
"""
observer-graph-topology.py — Measures effective N of observer/attestor networks.

Based on:
- Kish (1965): Design effect for clustered sampling
- Kim et al (ICML 2025): 60% correlated errors across LLMs
- santaclawd: "who measures observer graph topology? N_eff only matters if r is tracked"

N_eff = N / (1 + (N-1) * r̄)
where r̄ = mean pairwise substrate overlap

Substrate dimensions: cloud, model_provider, training_era, api_gateway, geography.
Each shared dimension increases r̄ → decreases N_eff.
The arbiter who measures MUST NOT be in the graph.
"""

import hashlib
import json
from dataclasses import dataclass, field
from itertools import combinations


@dataclass
class Observer:
    id: str
    cloud: str           # aws, gcp, azure, self-hosted
    model_provider: str  # openai, anthropic, google, local
    training_era: str    # pre-2024, 2024-h1, 2024-h2, 2025
    api_gateway: str     # direct, proxy, mcp
    geography: str       # us-east, eu-west, ap-southeast


SUBSTRATE_DIMS = ["cloud", "model_provider", "training_era", "api_gateway", "geography"]


def pairwise_overlap(a: Observer, b: Observer) -> float:
    """Fraction of substrate dimensions that are shared."""
    shared = 0
    for dim in SUBSTRATE_DIMS:
        if getattr(a, dim) == getattr(b, dim):
            shared += 1
    return shared / len(SUBSTRATE_DIMS)


def mean_pairwise_overlap(observers: list[Observer]) -> float:
    """Mean r̄ across all pairs."""
    if len(observers) < 2:
        return 0.0
    pairs = list(combinations(observers, 2))
    return sum(pairwise_overlap(a, b) for a, b in pairs) / len(pairs)


def effective_n(observers: list[Observer]) -> float:
    """Kish design effect: N_eff = N / (1 + (N-1) * r̄)."""
    n = len(observers)
    if n <= 1:
        return float(n)
    r_bar = mean_pairwise_overlap(observers)
    return n / (1 + (n - 1) * r_bar)


def grade_topology(n_eff: float, n: int) -> tuple[str, str]:
    ratio = n_eff / n if n > 0 else 0
    if ratio >= 0.7:
        return "A", "WELL_DIVERSIFIED"
    if ratio >= 0.5:
        return "B", "MODERATE_DIVERSITY"
    if ratio >= 0.3:
        return "C", "LOW_DIVERSITY"
    if ratio >= 0.15:
        return "D", "CORRELATED"
    return "F", "ECHO_CHAMBER"


def find_bottleneck(observers: list[Observer]) -> tuple[str, float]:
    """Which substrate dimension has highest overlap?"""
    dim_overlaps = {}
    pairs = list(combinations(observers, 2))
    if not pairs:
        return "none", 0.0
    for dim in SUBSTRATE_DIMS:
        shared = sum(1 for a, b in pairs if getattr(a, dim) == getattr(b, dim))
        dim_overlaps[dim] = shared / len(pairs)
    worst = max(dim_overlaps, key=dim_overlaps.get)
    return worst, dim_overlaps[worst]


def main():
    print("=" * 70)
    print("OBSERVER GRAPH TOPOLOGY")
    print("santaclawd: 'who measures observer graph topology?'")
    print("Kish (1965): N_eff = N / (1 + (N-1) * r̄)")
    print("=" * 70)

    scenarios = {
        "6_claudes": [
            Observer("c1", "aws", "anthropic", "2025", "direct", "us-east"),
            Observer("c2", "aws", "anthropic", "2025", "direct", "us-east"),
            Observer("c3", "aws", "anthropic", "2025", "proxy", "us-east"),
            Observer("c4", "gcp", "anthropic", "2025", "direct", "eu-west"),
            Observer("c5", "aws", "anthropic", "2025", "direct", "us-east"),
            Observer("c6", "aws", "anthropic", "2025", "mcp", "us-east"),
        ],
        "diverse_4": [
            Observer("kit", "self-hosted", "anthropic", "2025", "direct", "eu-west"),
            Observer("rule", "none", "none", "none", "none", "none"),
            Observer("drand", "cloudflare", "none", "none", "direct", "global"),
            Observer("human", "none", "none", "none", "none", "us-east"),
        ],
        "tc4_actual": [
            Observer("kit_fox", "self-hosted", "anthropic", "2025", "direct", "eu-west"),
            Observer("bro_agent", "aws", "openai", "2025", "direct", "us-east"),
            Observer("clove", "aws", "anthropic", "2025", "direct", "us-east"),
            Observer("gerundium", "gcp", "anthropic", "2025", "mcp", "eu-west"),
        ],
        "monoculture": [
            Observer("a", "aws", "openai", "2025", "direct", "us-east"),
            Observer("b", "aws", "openai", "2025", "direct", "us-east"),
            Observer("c", "aws", "openai", "2025", "direct", "us-east"),
        ],
    }

    print(f"\n{'Scenario':<18} {'N':<4} {'r̄':<8} {'N_eff':<8} {'Grade':<6} {'Bottleneck':<18} {'Diagnosis'}")
    print("-" * 80)

    for name, observers in scenarios.items():
        n = len(observers)
        r_bar = mean_pairwise_overlap(observers)
        n_eff = effective_n(observers)
        grade, diag = grade_topology(n_eff, n)
        bottleneck, bn_score = find_bottleneck(observers)
        print(f"{name:<18} {n:<4} {r_bar:<8.3f} {n_eff:<8.2f} {grade:<6} {bottleneck}({bn_score:.0%}){'':<4} {diag}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'who measures observer graph topology?'")
    print()
    print("The arbiter measuring N_eff MUST NOT be in the graph.")
    print("If the measurer is correlated with observers, r̄ is understated.")
    print()
    print("Substrate dimensions to track:")
    for dim in SUBSTRATE_DIMS:
        print(f"  - {dim}")
    print()
    print("Bottleneck = dimension with highest pairwise overlap.")
    print("Fix bottleneck first: adding observers on same substrate = waste.")
    print("One human observer breaks all LLM correlation (r=0 on model_provider).")
    print()
    print("For NIST RFI: N_eff is the empirically measurable diversity metric.")
    print("Kim et al (ICML 2025): even cross-provider r > 0 as capability converges.")


if __name__ == "__main__":
    main()
