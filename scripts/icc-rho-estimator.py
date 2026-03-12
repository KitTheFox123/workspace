#!/usr/bin/env python3
"""
icc-rho-estimator.py — Intracluster correlation (ρ) estimator for cluster-robust SPRT.

Based on:
- clove: "how are you estimating ρ in practice? empirical or bounded a priori?"
- Kim et al (ICML 2025): same-provider correlation ≈ 0.6, cross-provider ≈ 0.3
- Kish (1965): design effect = 1 + (m-1)·ρ, effective_N = N/DEFF

ρ = intracluster correlation. How correlated are attestations from same substrate?
High ρ = correlated errors = echo chamber. Low ρ = independent signal.

Estimation methods:
1. ANOVA-based (Donner 1986): MSB/MSW decomposition
2. Bayesian shrinkage: prior from substrate class, update with data
3. Leave-one-out: remove each attester, measure fixpoint shift
"""

import math
import random
from dataclasses import dataclass


@dataclass
class AttesterProbe:
    attester_id: str
    substrate: str  # "openai", "anthropic", "rule_based", "temporal"
    verdict: bool
    ground_truth: bool
    confidence: float


@dataclass
class RhoEstimate:
    method: str
    rho: float
    effective_n: float
    design_effect: float
    grade: str
    ci_lower: float = 0.0
    ci_upper: float = 1.0


def anova_rho(probes: list[AttesterProbe]) -> float:
    """ANOVA-based ICC(1) estimation (Donner 1986)."""
    # Group by substrate
    groups: dict[str, list[float]] = {}
    for p in probes:
        correct = 1.0 if (p.verdict == p.ground_truth) else 0.0
        groups.setdefault(p.substrate, []).append(correct)

    if len(groups) < 2:
        return 1.0  # Single substrate = maximally correlated

    k = len(groups)
    ns = [len(g) for g in groups.values()]
    N = sum(ns)
    grand_mean = sum(sum(g) for g in groups.values()) / N

    # Between-group sum of squares
    MSB = sum(n * (sum(g) / n - grand_mean) ** 2 for n, g in zip(ns, groups.values())) / (k - 1)
    # Within-group sum of squares
    MSW_num = sum(sum((x - sum(g) / len(g)) ** 2 for x in g) for g in groups.values())
    MSW = MSW_num / (N - k) if N > k else 0.001

    n0 = (N - sum(n ** 2 for n in ns) / N) / (k - 1)
    if n0 == 0:
        return 0.5

    rho = (MSB - MSW) / (MSB + (n0 - 1) * MSW) if (MSB + (n0 - 1) * MSW) > 0 else 0.0
    return max(0.0, min(1.0, rho))


def bayesian_shrinkage(empirical_rho: float, n_probes: int,
                        prior_rho: float = 0.5, prior_weight: float = 10) -> float:
    """Bayesian shrinkage toward substrate-class prior."""
    total_weight = n_probes + prior_weight
    return (empirical_rho * n_probes + prior_rho * prior_weight) / total_weight


def leave_one_out_rho(probes: list[AttesterProbe]) -> float:
    """Estimate ρ via fixpoint shift when removing each attester."""
    attesters = list(set(p.attester_id for p in probes))
    if len(attesters) < 3:
        return 0.5

    # Full ensemble accuracy
    full_correct = sum(1 for p in probes if p.verdict == p.ground_truth) / len(probes)

    shifts = []
    for leave_out in attesters:
        remaining = [p for p in probes if p.attester_id != leave_out]
        if not remaining:
            continue
        loo_correct = sum(1 for p in remaining if p.verdict == p.ground_truth) / len(remaining)
        shifts.append(abs(full_correct - loo_correct))

    if not shifts:
        return 0.5

    # High variance in shifts = low correlation (each attester matters)
    # Low variance = high correlation (removing any one doesn't change much)
    mean_shift = sum(shifts) / len(shifts)
    if mean_shift > 0.1:
        return max(0.0, 1.0 - mean_shift * 5)
    return min(1.0, 0.5 + (0.1 - mean_shift) * 5)


def kish_design_effect(rho: float, m: int) -> float:
    """Kish (1965) design effect."""
    return 1 + (m - 1) * rho


def grade_rho(rho: float) -> str:
    if rho < 0.1: return "A"
    if rho < 0.3: return "B"
    if rho < 0.5: return "C"
    if rho < 0.7: return "D"
    return "F"


def simulate_probes(n_claims: int, attesters: list[tuple[str, str, float, int]]) -> list[AttesterProbe]:
    """Simulate probe data. attesters = [(id, substrate, error_rate, seed)]."""
    probes = []
    for claim_idx in range(n_claims):
        ground_truth = random.random() > 0.3
        for aid, substrate, err, seed in attesters:
            rng = random.Random(seed + claim_idx)
            if rng.random() < err:
                verdict = not ground_truth
            else:
                verdict = ground_truth
            probes.append(AttesterProbe(aid, substrate, verdict, ground_truth, 0.8))
    return probes


def main():
    print("=" * 70)
    print("ICC ρ ESTIMATOR FOR CLUSTER-ROBUST SPRT")
    print("clove: 'how are you estimating ρ in practice?'")
    print("=" * 70)

    random.seed(42)

    scenarios = {
        "same_provider_3": [
            ("gpt4", "openai", 0.15, 42),
            ("gpt4t", "openai", 0.15, 42),  # Same seed = correlated
            ("gpt3", "openai", 0.20, 43),
        ],
        "cross_provider": [
            ("gpt4", "openai", 0.15, 42),
            ("claude", "anthropic", 0.15, 99),
            ("gemini", "google", 0.18, 77),
        ],
        "diverse_substrate": [
            ("gpt4", "openai", 0.15, 42),
            ("regex", "rule_based", 0.20, 777),
            ("temporal", "temporal", 0.25, 333),
            ("claude", "anthropic", 0.15, 99),
        ],
        "kim_et_al_worst": [
            ("gpt4a", "openai", 0.15, 42),
            ("gpt4b", "openai", 0.15, 42),
            ("gpt4c", "openai", 0.15, 42),
            ("gpt4d", "openai", 0.15, 42),
        ],
    }

    print(f"\n{'Scenario':<22} {'ANOVA ρ':<10} {'Bayes ρ':<10} {'LOO ρ':<10} {'DEFF':<8} {'Eff_N':<8} {'Grade'}")
    print("-" * 76)

    for name, attesters in scenarios.items():
        probes = simulate_probes(100, attesters)
        
        rho_anova = anova_rho(probes)
        rho_bayes = bayesian_shrinkage(rho_anova, len(probes))
        rho_loo = leave_one_out_rho(probes)
        
        m = len(attesters)
        deff = kish_design_effect(rho_bayes, m)
        eff_n = m / deff
        grade = grade_rho(rho_bayes)

        print(f"{name:<22} {rho_anova:<10.3f} {rho_bayes:<10.3f} {rho_loo:<10.3f} "
              f"{deff:<8.2f} {eff_n:<8.2f} {grade}")

    print("\n--- Estimation Strategy ---")
    print("1. Start: conservative prior ρ=0.5 (Kim et al substrate-class)")
    print("2. First 50 probes: ANOVA estimate + Bayesian shrinkage")
    print("3. Ongoing: leave-one-out for load-bearing attester detection")
    print("4. Alert: if ρ increases over time → substrate convergence")
    print()
    print("Kim et al (ICML 2025) baselines:")
    print("  Same provider:  ρ ≈ 0.6  (effective N per 4 = 1.5)")
    print("  Cross provider: ρ ≈ 0.3  (effective N per 4 = 2.1)")
    print("  LLM + rules:    ρ ≈ 0.1  (effective N per 4 = 3.1)")
    print()
    print("Protocol: ρ is a RUNTIME parameter, not a design constant.")
    print("Monitor it. When ρ drifts up → add substrate diversity.")


if __name__ == "__main__":
    main()
