#!/usr/bin/env python3
"""
behavioral-correlation-detector.py — Detect correlated beliefs from shared training data.

santaclawd's insight: "independent infra, synchronized failure modes."
Kim et al (ICML 2025): 350 LLMs, 60% agreement when both wrong.
More accurate models = MORE correlated errors.

This extends attester-independence-checker.py with behavioral probes:
1. Probe attesters with known-hard questions
2. Measure error correlation across pairs
3. Flag pairs with suspiciously high agreement-when-wrong

Key metric: conditional agreement rate P(A wrong same way | A wrong AND B wrong)
Random baseline for k choices = 1/k. Observed >> 1/k = correlated beliefs.

Usage:
    uv run --with numpy python3 behavioral-correlation-detector.py
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Tuple
from itertools import combinations


@dataclass
class AttesterResponse:
    attester_id: str
    question_id: str
    answer: str
    correct: bool
    confidence: float


@dataclass
class AttesterProfile:
    id: str
    provider: str  # e.g., "openai", "anthropic"
    architecture: str  # e.g., "transformer", "moe"
    infra: str  # e.g., "aws-us-east", "gcp-europe"
    responses: List[AttesterResponse]


def conditional_agreement_rate(a_responses: List[AttesterResponse],
                                b_responses: List[AttesterResponse]) -> dict:
    """P(same wrong answer | both wrong)."""
    # Match by question_id
    a_map = {r.question_id: r for r in a_responses}
    b_map = {r.question_id: r for r in b_responses}

    shared = set(a_map.keys()) & set(b_map.keys())
    both_wrong = 0
    same_wrong = 0

    for qid in shared:
        a, b = a_map[qid], b_map[qid]
        if not a.correct and not b.correct:
            both_wrong += 1
            if a.answer == b.answer:
                same_wrong += 1

    if both_wrong == 0:
        return {"both_wrong": 0, "same_wrong": 0, "rate": 0.0}

    return {
        "both_wrong": both_wrong,
        "same_wrong": same_wrong,
        "rate": round(same_wrong / both_wrong, 3),
    }


def confidence_correlation(a_responses: List[AttesterResponse],
                           b_responses: List[AttesterResponse]) -> float:
    """Pearson correlation of confidence scores."""
    a_map = {r.question_id: r.confidence for r in a_responses}
    b_map = {r.question_id: r.confidence for r in b_responses}
    shared = sorted(set(a_map.keys()) & set(b_map.keys()))
    if len(shared) < 5:
        return 0.0
    a_vals = [a_map[q] for q in shared]
    b_vals = [b_map[q] for q in shared]
    if np.std(a_vals) == 0 or np.std(b_vals) == 0:
        return 0.0
    return float(round(np.corrcoef(a_vals, b_vals)[0, 1], 3))


def analyze_pair(a: AttesterProfile, b: AttesterProfile) -> dict:
    """Full correlation analysis for a pair of attesters."""
    car = conditional_agreement_rate(a.responses, b.responses)
    conf_corr = confidence_correlation(a.responses, b.responses)

    # Infra independence
    same_provider = a.provider == b.provider
    same_arch = a.architecture == b.architecture
    same_infra = a.infra == b.infra

    # Behavioral correlation flags
    high_error_agreement = car["rate"] > 0.5  # Kim et al threshold
    high_conf_correlation = conf_corr > 0.7

    # Classification
    if same_infra and high_error_agreement:
        diagnosis = "INFRA_AND_BEHAVIORAL"
        grade = "F"
    elif high_error_agreement and high_conf_correlation:
        diagnosis = "BEHAVIORAL_MONOCULTURE"
        grade = "D"
    elif high_error_agreement:
        diagnosis = "CORRELATED_ERRORS"
        grade = "C"
    elif same_provider or same_arch:
        diagnosis = "SURFACE_SIMILAR"
        grade = "B"
    else:
        diagnosis = "INDEPENDENT"
        grade = "A"

    return {
        "pair": f"{a.id} × {b.id}",
        "diagnosis": diagnosis,
        "grade": grade,
        "error_agreement_rate": car["rate"],
        "both_wrong_count": car["both_wrong"],
        "confidence_correlation": conf_corr,
        "same_provider": same_provider,
        "same_architecture": same_arch,
        "same_infra": same_infra,
    }


def effective_n(attesters: List[AttesterProfile]) -> dict:
    """Kish design effect adjusted for behavioral correlation."""
    n = len(attesters)
    if n < 2:
        return {"n": n, "effective_n": n, "mean_correlation": 0}

    correlations = []
    pair_results = []
    for a, b in combinations(attesters, 2):
        result = analyze_pair(a, b)
        pair_results.append(result)
        correlations.append(result["error_agreement_rate"])

    mean_corr = float(np.mean(correlations))
    # Kish: N_eff = N / (1 + (N-1) * rho)
    eff_n = n / (1 + (n - 1) * mean_corr) if mean_corr < 1 else 1.0

    return {
        "n": n,
        "effective_n": round(eff_n, 2),
        "mean_error_correlation": round(mean_corr, 3),
        "pair_analyses": pair_results,
    }


def demo():
    print("=" * 60)
    print("BEHAVIORAL CORRELATION DETECTOR")
    print("Kim et al (ICML 2025): 60% agreement when both wrong")
    print("=" * 60)
    np.random.seed(42)

    # Generate probe questions
    n_questions = 50
    correct_answers = [f"correct_{i}" for i in range(n_questions)]
    wrong_options = [[f"wrong_{i}_a", f"wrong_{i}_b"] for i in range(n_questions)]

    def make_responses(attester_id: str, accuracy: float,
                       shared_bias: dict = None) -> List[AttesterResponse]:
        """Generate responses with optional shared bias."""
        responses = []
        for i in range(n_questions):
            is_correct = np.random.random() < accuracy
            if is_correct:
                ans = correct_answers[i]
            elif shared_bias and i in shared_bias:
                ans = shared_bias[i]  # correlated wrong answer
            else:
                ans = np.random.choice(wrong_options[i])

            conf = np.random.uniform(0.6, 0.95) if is_correct else np.random.uniform(0.3, 0.7)
            responses.append(AttesterResponse(
                attester_id=attester_id,
                question_id=f"q_{i}",
                answer=ans,
                correct=(ans == correct_answers[i]),
                confidence=round(conf, 2),
            ))
        return responses

    # Shared bias: same wrong answers on specific questions (training data overlap)
    shared_gpt_bias = {i: f"wrong_{i}_a" for i in range(0, 40, 2)}
    shared_claude_bias = {i: f"wrong_{i}_b" for i in range(1, 40, 2)}

    # Scenario 1: Same provider, same bias
    print("\n--- Same Provider (GPT-4 + GPT-4-turbo) ---")
    gpt4 = AttesterProfile("gpt4", "openai", "transformer", "azure-east",
                           make_responses("gpt4", 0.75, shared_gpt_bias))
    gpt4t = AttesterProfile("gpt4-turbo", "openai", "transformer", "azure-east",
                            make_responses("gpt4-turbo", 0.78, shared_gpt_bias))
    r1 = analyze_pair(gpt4, gpt4t)
    print(f"  {r1['diagnosis']} ({r1['grade']})")
    print(f"  Error agreement: {r1['error_agreement_rate']}")
    print(f"  Confidence corr: {r1['confidence_correlation']}")

    # Scenario 2: Different provider, different bias
    print("\n--- Different Provider (GPT-4 + Claude) ---")
    claude = AttesterProfile("claude", "anthropic", "transformer", "aws-west",
                             make_responses("claude", 0.76, shared_claude_bias))
    r2 = analyze_pair(gpt4, claude)
    print(f"  {r2['diagnosis']} ({r2['grade']})")
    print(f"  Error agreement: {r2['error_agreement_rate']}")
    print(f"  Confidence corr: {r2['confidence_correlation']}")

    # Scenario 3: Non-LLM attester (rule-based)
    print("\n--- LLM + Non-LLM (GPT-4 + Rule-based) ---")
    rules = AttesterProfile("rules", "custom", "rule-engine", "on-prem",
                            make_responses("rules", 0.65, {}))  # no shared bias
    r3 = analyze_pair(gpt4, rules)
    print(f"  {r3['diagnosis']} ({r3['grade']})")
    print(f"  Error agreement: {r3['error_agreement_rate']}")
    print(f"  Confidence corr: {r3['confidence_correlation']}")

    # Scenario 4: Two non-LLM attesters
    print("\n--- Non-LLM + Non-LLM (Rule-based + SMTP checker) ---")
    smtp = AttesterProfile("smtp", "custom", "protocol-check", "on-prem",
                           make_responses("smtp", 0.60, {}))
    r4 = analyze_pair(rules, smtp)
    print(f"  {r4['diagnosis']} ({r4['grade']})")
    print(f"  Error agreement: {r4['error_agreement_rate']}")
    print(f"  Confidence corr: {r4['confidence_correlation']}")

    # Effective N analysis
    print("\n--- EFFECTIVE N (all 5 attesters) ---")
    all_attesters = [gpt4, gpt4t, claude, rules, smtp]
    eff = effective_n(all_attesters)
    print(f"  N = {eff['n']}, Effective N = {eff['effective_n']}")
    print(f"  Mean error correlation: {eff['mean_error_correlation']}")

    print("\n--- EFFECTIVE N (LLMs only) ---")
    llm_only = [gpt4, gpt4t, claude]
    eff_llm = effective_n(llm_only)
    print(f"  N = {eff_llm['n']}, Effective N = {eff_llm['effective_n']}")
    print(f"  Mean error correlation: {eff_llm['mean_error_correlation']}")

    print("\n--- KEY INSIGHT ---")
    print("Kim et al (ICML 2025): Accuracy ↑ → Correlation ↑")
    print("More capable models converge — including on mistakes.")
    print("Behavioral probes catch what infra checks miss.")
    print("Minimum viable oracle set MUST include non-LLM signal.")


if __name__ == "__main__":
    demo()
