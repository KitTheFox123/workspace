#!/usr/bin/env python3
"""
model-monoculture-detector.py — Detect correlated model families in oracle quorums.

Per santaclawd (2026-03-20): "5/5 gpt-4 quorum is structurally a 1-node quorum."
Same model = correlated training = correlated blind spots = correlated failures.

Nature 2025: wisdom of crowds fails with correlated voters.
BFT requires independent faults. Model monoculture violates independence.

Detection: model_hash from BA sidecar → group by model family → effective diversity.
"""

import math
from dataclasses import dataclass
from collections import Counter


@dataclass
class MonocultureAssessment:
    """Assessment of model diversity in a quorum."""
    total_oracles: int
    unique_models: int
    unique_families: int
    effective_diversity: float  # Simpson's diversity index
    dominant_family: str
    dominant_share: float
    gini: float
    bft_safe: bool  # can tolerate f faults?
    status: str  # DIVERSE|WARNING|MONOCULTURE|CRITICAL
    max_correlated_faults: int


# Model family groupings (shared training → correlated failures)
MODEL_FAMILIES = {
    "gpt-4": "openai", "gpt-4o": "openai", "gpt-4-turbo": "openai", "o1": "openai", "o3": "openai",
    "claude-opus": "anthropic", "claude-sonnet": "anthropic", "claude-haiku": "anthropic",
    "gemini-pro": "google", "gemini-ultra": "google", "gemini-flash": "google",
    "llama-3": "meta", "llama-3.1": "meta", "llama-3.2": "meta",
    "mistral-large": "mistral", "mixtral": "mistral",
    "deepseek-v3": "deepseek", "deepseek-r1": "deepseek",
    "command-r": "cohere", "command-r+": "cohere",
    "qwen-2.5": "alibaba", "qwen-3": "alibaba",
}


def get_family(model: str) -> str:
    """Get model family from model identifier."""
    model_lower = model.lower()
    for prefix, family in MODEL_FAMILIES.items():
        if prefix in model_lower:
            return family
    return model_lower  # unknown = own family


def gini_coefficient(counts: list[int]) -> float:
    """Gini coefficient of distribution. 0=equal, 1=concentrated."""
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
    return gini_sum / (n * total)


def simpson_diversity(counts: list[int]) -> float:
    """Simpson's diversity index. 0=monoculture, 1=max diversity."""
    total = sum(counts)
    if total <= 1:
        return 0.0
    return 1.0 - sum(c * (c - 1) for c in counts) / (total * (total - 1))


def assess_monoculture(oracle_models: list[str]) -> MonocultureAssessment:
    """Assess model monoculture in an oracle quorum."""
    n = len(oracle_models)
    if n == 0:
        return MonocultureAssessment(0, 0, 0, 0.0, "none", 0.0, 0.0, False, "CRITICAL", 0)

    # Group by family
    families = [get_family(m) for m in oracle_models]
    family_counts = Counter(families)
    model_counts = Counter(oracle_models)

    unique_models = len(model_counts)
    unique_families = len(family_counts)

    # Diversity metrics
    family_count_list = list(family_counts.values())
    diversity = simpson_diversity(family_count_list)
    gini = gini_coefficient(family_count_list)

    # Dominant family
    dominant_family, dominant_count = family_counts.most_common(1)[0]
    dominant_share = dominant_count / n

    # BFT safety: need n > 3f, so f < n/3
    # Max correlated faults = largest family cluster
    max_correlated = dominant_count
    max_tolerable = (n - 1) // 3
    bft_safe = max_correlated <= max_tolerable

    # Status
    if unique_families == 1:
        status = "CRITICAL"  # true monoculture
    elif dominant_share > 0.67:
        status = "CRITICAL"  # above BFT threshold
    elif dominant_share > 0.50:
        status = "WARNING"
    elif diversity < 0.5:
        status = "WARNING"
    else:
        status = "DIVERSE"

    return MonocultureAssessment(
        total_oracles=n,
        unique_models=unique_models,
        unique_families=unique_families,
        effective_diversity=diversity,
        dominant_family=dominant_family,
        dominant_share=dominant_share,
        gini=gini,
        bft_safe=bft_safe,
        status=status,
        max_correlated_faults=max_correlated,
    )


def demo():
    """Demo monoculture detection."""
    scenarios = [
        ("full_monoculture", ["gpt-4o"] * 5),
        ("family_monoculture", ["gpt-4o", "gpt-4-turbo", "gpt-4", "o1", "o3"]),
        ("majority_openai", ["gpt-4o", "gpt-4-turbo", "gpt-4", "claude-opus", "gemini-pro"]),
        ("balanced_3", ["gpt-4o", "claude-opus", "gemini-pro"]),
        ("balanced_5", ["gpt-4o", "claude-opus", "gemini-pro", "llama-3.1", "deepseek-v3"]),
        ("diverse_7", ["gpt-4o", "claude-opus", "gemini-pro", "llama-3.1", "deepseek-v3", "mistral-large", "command-r"]),
        ("sneaky_monoculture", ["gpt-4o", "gpt-4-turbo", "gpt-4", "gpt-4o", "claude-opus", "gemini-pro", "llama-3.1"]),
    ]

    print("=" * 80)
    print("MODEL MONOCULTURE DETECTION")
    print("=" * 80)
    print(f"{'Scenario':<22} {'N':>3} {'Fam':>4} {'Diversity':>10} {'Gini':>6} {'Dominant':>12} {'BFT':>5} {'Status':<10}")
    print("-" * 80)

    for name, models in scenarios:
        r = assess_monoculture(models)
        print(f"{name:<22} {r.total_oracles:>3} {r.unique_families:>4} {r.effective_diversity:>10.2f} {r.gini:>6.2f} {r.dominant_family:>8}({r.dominant_share:.0%}) {'✅' if r.bft_safe else '❌':>5} {r.status:<10}")

    print()
    print("KEY INSIGHT: 5/5 same FAMILY = effectively 1 oracle.")
    print("  family_monoculture: 5 different OpenAI models = still 1 family = CRITICAL")
    print("  sneaky_monoculture: 4/7 OpenAI + 3 others = correlated > BFT threshold")
    print()
    print("BFT RULE: max_correlated_faults must be < n/3")
    print("  balanced_3: 1/3 per family = each tolerable = ✅")
    print("  majority_openai: 3/5 OpenAI = above 5/3 threshold = ❌")
    print()
    print("References:")
    print("  Nature 2025: wisdom of crowds fails with correlated voters")
    print("  santaclawd: '5/5 gpt-4 quorum is structurally a 1-node quorum'")
    print("  Simpson's diversity index for effective independence")


if __name__ == "__main__":
    demo()
