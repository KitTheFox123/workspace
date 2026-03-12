#!/usr/bin/env python3
"""
hallucination-correlation-detector.py — Detects correlated hallucination across multi-model verification.

Based on:
- Kim et al (ICML 2025, arXiv 2506.07962): 60% agreement when BOTH wrong
- Alansari & Luqman (arXiv 2510.06265, Oct 2025): Causes across full LLM pipeline
- Kirchhof et al (ICLR 2025): Source-wise uncertainty > aleatoric/epistemic dichotomy

The problem: "multiple models checking each other blind" (TriallAI's claim)
has a ceiling. Same training data → correlated hallucinations.
Agreement ≠ correctness. Need uncorrelated substrates.
"""

import hashlib
import json
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VerificationResult:
    model: str
    substrate: str  # e.g., "openai", "anthropic", "local", "rule_based"
    claim: str
    verdict: bool  # True = claim is correct
    confidence: float
    is_actually_correct: Optional[bool] = None  # Ground truth


@dataclass
class CorrelationAnalysis:
    total_claims: int = 0
    both_right: int = 0
    both_wrong: int = 0
    disagree: int = 0
    agreement_when_wrong: float = 0.0  # Kim et al's key metric
    effective_n: float = 0.0
    grade: str = "F"
    diagnosis: str = ""


def compute_pairwise_correlation(results_a: list[VerificationResult],
                                  results_b: list[VerificationResult]) -> CorrelationAnalysis:
    """Compute Kim et al correlation between two verifiers."""
    analysis = CorrelationAnalysis()

    for ra, rb in zip(results_a, results_b):
        analysis.total_claims += 1
        a_correct = ra.verdict == ra.is_actually_correct
        b_correct = rb.verdict == rb.is_actually_correct

        if a_correct and b_correct:
            analysis.both_right += 1
        elif not a_correct and not b_correct:
            analysis.both_wrong += 1
        else:
            analysis.disagree += 1

    # Kim et al's metric: P(both wrong | at least one wrong)
    wrong_cases = analysis.both_wrong + analysis.disagree
    if wrong_cases > 0:
        analysis.agreement_when_wrong = analysis.both_wrong / wrong_cases
    else:
        analysis.agreement_when_wrong = 0.0

    # Effective N (Kish design effect)
    r = analysis.agreement_when_wrong
    n = 2  # Two verifiers
    if r < 1.0:
        analysis.effective_n = n / (1 + (n - 1) * r)
    else:
        analysis.effective_n = 1.0

    # Grade
    if analysis.agreement_when_wrong < 0.2:
        analysis.grade = "A"
        analysis.diagnosis = "LOW_CORRELATION"
    elif analysis.agreement_when_wrong < 0.4:
        analysis.grade = "B"
        analysis.diagnosis = "MODERATE_CORRELATION"
    elif analysis.agreement_when_wrong < 0.6:
        analysis.grade = "C"
        analysis.diagnosis = "HIGH_CORRELATION"
    elif analysis.agreement_when_wrong < 0.8:
        analysis.grade = "D"
        analysis.diagnosis = "CORRELATED_HALLUCINATION"
    else:
        analysis.grade = "F"
        analysis.diagnosis = "ECHO_CHAMBER"

    return analysis


def simulate_verification_set(model: str, substrate: str,
                               claims: list[tuple[str, bool]],
                               error_rate: float,
                               correlation_seed: Optional[int] = None) -> list[VerificationResult]:
    """Simulate a verifier with given error rate and optional correlation."""
    rng = random.Random(correlation_seed) if correlation_seed else random.Random()
    results = []
    for claim_text, ground_truth in claims:
        # Model sometimes gets it wrong
        if rng.random() < error_rate:
            verdict = not ground_truth  # Wrong answer
        else:
            verdict = ground_truth  # Right answer
        confidence = 0.7 + rng.random() * 0.25  # 0.7-0.95
        results.append(VerificationResult(
            model=model, substrate=substrate,
            claim=claim_text, verdict=verdict,
            confidence=confidence, is_actually_correct=ground_truth
        ))
    return results


def main():
    print("=" * 70)
    print("HALLUCINATION CORRELATION DETECTOR")
    print("Kim et al (ICML 2025): 60% agreement when both wrong")
    print("=" * 70)

    # Generate test claims
    random.seed(42)
    claims = [(f"claim_{i}", random.random() > 0.3) for i in range(100)]

    scenarios = {
        # Same substrate, same seed = maximally correlated
        "same_provider_correlated": {
            "a": ("gpt-4", "openai", 0.15, 42),
            "b": ("gpt-4-turbo", "openai", 0.15, 42),
        },
        # Same substrate, different seed = moderately correlated
        "same_provider_independent": {
            "a": ("gpt-4", "openai", 0.15, 42),
            "b": ("gpt-4-turbo", "openai", 0.15, 43),
        },
        # Different substrates = lower correlation
        "cross_provider": {
            "a": ("gpt-4", "openai", 0.15, 42),
            "b": ("claude-opus", "anthropic", 0.15, 99),
        },
        # LLM + rule-based = minimal correlation
        "llm_plus_rules": {
            "a": ("gpt-4", "openai", 0.15, 42),
            "b": ("regex_checker", "rule_based", 0.20, 777),
        },
        # TriallAI's claim: "multiple models checking blind"
        "triallai_approach": {
            "a": ("model_1", "openai", 0.15, 42),
            "b": ("model_2", "openai", 0.15, 42),  # Same substrate = correlated
        },
    }

    print(f"\n{'Scenario':<30} {'Grade':<6} {'Agree-Wrong':<12} {'EffN':<6} {'Diagnosis'}")
    print("-" * 70)

    for name, config in scenarios.items():
        a = config["a"]
        b = config["b"]
        results_a = simulate_verification_set(a[0], a[1], claims, a[2], a[3])
        results_b = simulate_verification_set(b[0], b[1], claims, b[2], b[3])
        analysis = compute_pairwise_correlation(results_a, results_b)
        print(f"{name:<30} {analysis.grade:<6} {analysis.agreement_when_wrong:<12.1%} "
              f"{analysis.effective_n:<6.2f} {analysis.diagnosis}")

    # Key insight
    print("\n--- Key Insight ---")
    print("TriallAI: 'multiple models checking each other blind'")
    print("Kim et al: 60% agreement when BOTH wrong (random = 33%)")
    print()
    print("Same training data → correlated errors → agreement ≠ correctness")
    print("Fix: uncorrelated substrates (LLM + rules + temporal + human)")
    print("      Not just more models from the same provider.")
    print()
    print("Alansari & Luqman (2025) traced hallucination across 6 pipeline stages.")
    print("External verification only catches inference-stage hallucinations.")
    print("Data-stage and architecture-stage causes survive cross-checking")
    print("because all models share the same training distribution.")


if __name__ == "__main__":
    main()
