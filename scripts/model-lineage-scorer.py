#!/usr/bin/env python3
"""
model-lineage-scorer.py — Measures grader diversity by model family lineage, not just operator.

Problem (santaclawd + Kit, March 2026):
  Two operators running the same base model = correlated graders.
  OPERATOR_DIVERSITY_SCORE misses model monoculture.
  Simpson diversity on operator_id: 3 operators, all Claude-based = 1.0 diversity (wrong).
  Simpson diversity on model_family: 3 operators, all Claude-based = 0.0 diversity (correct).

Solution:
  MODEL_LINEAGE_SCORE tracks pre-training ancestry, not deployment identity.
  Three diversity axes:
  1. Operator diversity (who runs it) — Simpson index
  2. Model family diversity (what base model) — Simpson index  
  3. Training corpus diversity (what data) — estimated from public info

  Combined: weighted geometric mean. Monoculture on ANY axis caps the score.

Sources:
- Gradient Institute (July 2025): "A collection of safe agents does not guarantee a safe collection"
- Nature 2025: Correlated voters = expensive groupthink
- ATF Axiom 1: No self-attestation → no self-grading → no monoculture grading
- Gall's Law: Complex systems from simple ones that worked
"""

import json
import math
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone


# Known model families and their lineage
MODEL_FAMILIES = {
    # family_id: {name, base_provider, known_derivatives}
    "claude": {"name": "Claude", "provider": "Anthropic", "derivatives": [
        "claude-opus-4", "claude-sonnet-4", "claude-haiku",
        "claude-opus-4.5", "claude-opus-4.6",
    ]},
    "gpt": {"name": "GPT", "provider": "OpenAI", "derivatives": [
        "gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-4o-mini", "o1", "o3",
    ]},
    "gemini": {"name": "Gemini", "provider": "Google", "derivatives": [
        "gemini-pro", "gemini-ultra", "gemini-2.0", "gemini-2.5",
    ]},
    "llama": {"name": "Llama", "provider": "Meta", "derivatives": [
        "llama-3", "llama-3.1", "llama-3.2", "llama-4",
        # Fine-tunes still share the lineage
        "codellama", "nous-hermes-llama",
    ]},
    "mistral": {"name": "Mistral", "provider": "Mistral AI", "derivatives": [
        "mistral-large", "mistral-medium", "mixtral", "mistral-nemo",
    ]},
    "deepseek": {"name": "DeepSeek", "provider": "DeepSeek", "derivatives": [
        "deepseek-v2", "deepseek-v3", "deepseek-r1",
    ]},
    "qwen": {"name": "Qwen", "provider": "Alibaba", "derivatives": [
        "qwen-2", "qwen-2.5", "qwen-72b",
    ]},
    "command": {"name": "Command", "provider": "Cohere", "derivatives": [
        "command-r", "command-r-plus",
    ]},
}


@dataclass
class GraderProfile:
    """A grader's identity including model lineage."""
    grader_id: str
    operator_id: str
    model_family: str          # Key into MODEL_FAMILIES
    model_variant: str         # Specific model version
    training_corpus_hash: Optional[str] = None  # If known
    
    def __post_init__(self):
        if self.model_family not in MODEL_FAMILIES:
            # Unknown family — treat as unique (maximally diverse)
            MODEL_FAMILIES[self.model_family] = {
                "name": self.model_family,
                "provider": "unknown",
                "derivatives": [self.model_variant],
            }


@dataclass
class LineageScore:
    """Combined diversity score across three axes."""
    operator_diversity: float    # Simpson index on operators
    model_family_diversity: float  # Simpson index on model families
    corpus_diversity: float      # Estimated training data diversity
    combined: float              # Weighted geometric mean
    grader_count: int
    family_distribution: dict    # family → count
    operator_distribution: dict  # operator → count
    warnings: list[str] = field(default_factory=list)


def simpson_diversity(counts: list[int]) -> float:
    """
    Simpson's Diversity Index: 1 - Σ(n_i/N)²
    0 = monoculture, approaches 1 = maximum diversity.
    """
    n = sum(counts)
    if n <= 1:
        return 0.0
    return 1.0 - sum((c / n) ** 2 for c in counts)


def estimate_corpus_diversity(families: list[str]) -> float:
    """
    Estimate training corpus diversity from model families.
    
    Heuristic: models from the same provider likely share significant
    training data overlap. Cross-provider = more corpus diversity.
    
    Known overlaps:
    - All models trained on Common Crawl (high overlap)
    - But proprietary data differs significantly
    - Fine-tuning data is most diverse
    """
    providers = set()
    for family in families:
        if family in MODEL_FAMILIES:
            providers.add(MODEL_FAMILIES[family]["provider"])
        else:
            providers.add(f"unknown_{family}")
    
    # Provider-level Simpson diversity as proxy for corpus diversity
    # Discount slightly because all share Common Crawl base
    COMMON_CRAWL_OVERLAP = 0.15  # ~15% shared base reduces effective diversity
    
    provider_counts = {}
    for family in families:
        provider = MODEL_FAMILIES.get(family, {}).get("provider", f"unknown_{family}")
        provider_counts[provider] = provider_counts.get(provider, 0) + 1
    
    raw_diversity = simpson_diversity(list(provider_counts.values()))
    return raw_diversity * (1 - COMMON_CRAWL_OVERLAP)


def score_lineage(graders: list[GraderProfile]) -> LineageScore:
    """
    Score grader pool diversity across three axes.
    
    Weights (per ATF design):
    - Model family: 0.50 (most important — correlated failures)
    - Operator: 0.30 (operational independence)
    - Corpus: 0.20 (data diversity)
    """
    if not graders:
        return LineageScore(0, 0, 0, 0, 0, {}, {}, ["no graders"])
    
    # Count distributions
    family_counts: dict[str, int] = {}
    operator_counts: dict[str, int] = {}
    
    for g in graders:
        family_counts[g.model_family] = family_counts.get(g.model_family, 0) + 1
        operator_counts[g.operator_id] = operator_counts.get(g.operator_id, 0) + 1
    
    # Axis scores
    op_div = simpson_diversity(list(operator_counts.values()))
    family_div = simpson_diversity(list(family_counts.values()))
    corpus_div = estimate_corpus_diversity(list(family_counts.keys()))
    
    # Weighted geometric mean (monoculture on any axis drags score down)
    WEIGHTS = {"family": 0.50, "operator": 0.30, "corpus": 0.20}
    
    # Avoid log(0): floor at 0.01
    eps = 0.01
    combined = math.exp(
        WEIGHTS["family"] * math.log(max(family_div, eps)) +
        WEIGHTS["operator"] * math.log(max(op_div, eps)) +
        WEIGHTS["corpus"] * math.log(max(corpus_div, eps))
    )
    
    # Warnings
    warnings = []
    if family_div < 0.3:
        dominant = max(family_counts, key=family_counts.get)
        warnings.append(f"MODEL_MONOCULTURE: {dominant} dominates ({family_counts[dominant]}/{len(graders)})")
    if op_div < 0.3:
        dominant = max(operator_counts, key=operator_counts.get)
        warnings.append(f"OPERATOR_MONOCULTURE: {dominant} dominates ({operator_counts[dominant]}/{len(graders)})")
    if len(family_counts) == 1:
        warnings.append("CRITICAL: all graders share same model family — correlated failure guaranteed")
    if corpus_div < 0.2:
        warnings.append("LOW_CORPUS_DIVERSITY: training data likely overlaps significantly")
    
    return LineageScore(
        operator_diversity=round(op_div, 4),
        model_family_diversity=round(family_div, 4),
        corpus_diversity=round(corpus_div, 4),
        combined=round(combined, 4),
        grader_count=len(graders),
        family_distribution=family_counts,
        operator_distribution=operator_counts,
        warnings=warnings,
    )


def run_scenarios():
    """Test scenarios demonstrating model lineage diversity scoring."""
    
    print("=" * 70)
    print("MODEL LINEAGE DIVERSITY SCORER")
    print("=" * 70)
    
    scenarios = [
        {
            "name": "1. Diverse pool (3 families, 3 operators)",
            "graders": [
                GraderProfile("g1", "op_alpha", "claude", "claude-opus-4.6"),
                GraderProfile("g2", "op_beta", "gpt", "gpt-4o"),
                GraderProfile("g3", "op_gamma", "llama", "llama-4"),
            ],
            "expect_warnings": False,
        },
        {
            "name": "2. Operator diverse, model monoculture (3 ops, 1 family)",
            "graders": [
                GraderProfile("g1", "op_alpha", "claude", "claude-opus-4.6"),
                GraderProfile("g2", "op_beta", "claude", "claude-sonnet-4"),
                GraderProfile("g3", "op_gamma", "claude", "claude-haiku"),
            ],
            "expect_warnings": True,
        },
        {
            "name": "3. Model diverse, operator monoculture (1 op, 3 families)",
            "graders": [
                GraderProfile("g1", "op_alpha", "claude", "claude-opus-4.6"),
                GraderProfile("g2", "op_alpha", "gpt", "gpt-4o"),
                GraderProfile("g3", "op_alpha", "llama", "llama-4"),
            ],
            "expect_warnings": True,
        },
        {
            "name": "4. Complete monoculture (1 op, 1 family)",
            "graders": [
                GraderProfile("g1", "op_alpha", "claude", "claude-opus-4.6"),
                GraderProfile("g2", "op_alpha", "claude", "claude-sonnet-4"),
                GraderProfile("g3", "op_alpha", "claude", "claude-haiku"),
                GraderProfile("g4", "op_alpha", "claude", "claude-opus-4.5"),
            ],
            "expect_warnings": True,
        },
        {
            "name": "5. Maximum diversity (5 families, 5 operators)",
            "graders": [
                GraderProfile("g1", "op_1", "claude", "claude-opus-4.6"),
                GraderProfile("g2", "op_2", "gpt", "gpt-4o"),
                GraderProfile("g3", "op_3", "llama", "llama-4"),
                GraderProfile("g4", "op_4", "gemini", "gemini-2.5"),
                GraderProfile("g5", "op_5", "deepseek", "deepseek-v3"),
            ],
            "expect_warnings": False,
        },
    ]
    
    all_pass = True
    for scenario in scenarios:
        score = score_lineage(scenario["graders"])
        has_warnings = len(score.warnings) > 0
        passed = has_warnings == scenario["expect_warnings"]
        if not passed:
            all_pass = False
        
        status = "✓" if passed else "✗"
        print(f"\n{status} {scenario['name']}")
        print(f"  Operator diversity:     {score.operator_diversity:.4f}")
        print(f"  Model family diversity: {score.model_family_diversity:.4f}")
        print(f"  Corpus diversity:       {score.corpus_diversity:.4f}")
        print(f"  Combined score:         {score.combined:.4f}")
        print(f"  Families: {score.family_distribution}")
        print(f"  Operators: {score.operator_distribution}")
        if score.warnings:
            for w in score.warnings:
                print(f"  ⚠ {w}")
    
    print(f"\n{'=' * 70}")
    passed_count = sum(1 for s in scenarios if (len(score_lineage(s["graders"]).warnings) > 0) == s["expect_warnings"])
    print(f"Results: {passed_count}/{len(scenarios)}")
    
    # Key comparison
    print(f"\nKey insight: Scenario 2 vs Scenario 3")
    s2 = score_lineage(scenarios[1]["graders"])
    s3 = score_lineage(scenarios[2]["graders"])
    print(f"  S2 (3 ops, 1 family): combined={s2.combined:.4f} — OPERATOR_DIVERSITY_SCORE would say 'diverse'")
    print(f"  S3 (1 op, 3 families): combined={s3.combined:.4f} — OPERATOR_DIVERSITY_SCORE would say 'monoculture'")
    print(f"  Model family diversity catches what operator diversity misses.")
    print(f"  Geometric mean ensures monoculture on ANY axis caps the score.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
