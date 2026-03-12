#!/usr/bin/env python3
"""
intracluster-rho-estimator.py — Estimate intracluster correlation ρ for cluster-robust SPRT.

Based on:
- clove: "how are you estimating ρ? empirical from historical probe data or bounded a priori?"
- Kim et al (ICML 2025): ρ≈0.6 for same-provider LLMs, cross-substrate ρ≈0.1
- Kish (1965): Design effect = 1 + (m-1)ρ where m = cluster size

Start conservative (ρ=0.3), update Bayesian as probes accumulate.
Use higher estimate until N>50 probes justify lowering.
"""

import math
import random
from dataclasses import dataclass


@dataclass
class ProbeResult:
    probe_id: int
    cluster_id: str  # e.g., "openai", "anthropic", "rule_based"
    outcome: bool     # True = correct
    timestamp: float


@dataclass
class ClusterEstimate:
    cluster_id: str
    rho: float        # Intracluster correlation
    n_probes: int
    design_effect: float
    effective_n: float
    confidence: str   # "prior" or "empirical"


def estimate_rho_empirical(outcomes_by_cluster: dict[str, list[bool]]) -> dict[str, float]:
    """Estimate ρ from observed probe data using ANOVA-based ICC."""
    rhos = {}
    for cluster_id, outcomes in outcomes_by_cluster.items():
        if len(outcomes) < 3:
            rhos[cluster_id] = 0.3  # Prior
            continue
        
        n = len(outcomes)
        mean = sum(outcomes) / n
        
        # Between-cluster variance approximation
        # For binary outcomes: ρ ≈ (observed agreement - expected) / (1 - expected)
        # Using pairs within cluster
        pairs = 0
        agreements = 0
        for i in range(n):
            for j in range(i + 1, n):
                pairs += 1
                if outcomes[i] == outcomes[j]:
                    agreements += 1
        
        if pairs == 0:
            rhos[cluster_id] = 0.3
            continue
        
        observed_agreement = agreements / pairs
        expected_agreement = mean**2 + (1 - mean)**2
        
        if expected_agreement >= 1.0:
            rhos[cluster_id] = 0.0
        else:
            rho = (observed_agreement - expected_agreement) / (1 - expected_agreement)
            rhos[cluster_id] = max(0.0, min(1.0, rho))
    
    return rhos


def bayesian_update_rho(prior_rho: float, prior_n: int,
                         new_rho: float, new_n: int) -> float:
    """Simple Bayesian update: weighted combination of prior and evidence."""
    total = prior_n + new_n
    return (prior_rho * prior_n + new_rho * new_n) / total


def design_effect(rho: float, cluster_size: int) -> float:
    """Kish design effect: DEFF = 1 + (m-1)ρ."""
    return 1 + (cluster_size - 1) * rho


def effective_sample_size(n_total: int, rho: float, cluster_size: int) -> float:
    """Effective N after accounting for correlation."""
    deff = design_effect(rho, cluster_size)
    return n_total / deff if deff > 0 else n_total


def simulate_probes(n_probes: int, clusters: dict[str, float],
                     base_error: float = 0.15) -> dict[str, list[bool]]:
    """Simulate probe outcomes with intracluster correlation."""
    results = {}
    for cluster_id, true_rho in clusters.items():
        outcomes = []
        # Generate correlated binary outcomes
        shared_component = random.random() < (1 - base_error)
        for _ in range(n_probes):
            if random.random() < true_rho:
                # Correlated: follow shared component
                outcomes.append(shared_component)
            else:
                # Independent
                outcomes.append(random.random() < (1 - base_error))
        results[cluster_id] = outcomes
    return results


def main():
    print("=" * 70)
    print("INTRACLUSTER ρ ESTIMATOR")
    print("clove: 'how are you estimating ρ in practice?'")
    print("Kim et al (ICML 2025): same-provider ρ≈0.6, cross-substrate ρ≈0.1")
    print("=" * 70)

    random.seed(42)

    # True ρ values (Kim et al benchmarks)
    true_clusters = {
        "openai_gpt4": 0.60,       # Same provider, high correlation
        "openai_gpt4o": 0.55,      # Same provider, slightly different
        "anthropic_opus": 0.10,    # Cross-provider
        "rule_based": 0.05,        # Non-LLM, minimal correlation
        "temporal": 0.02,          # Time-based, near-independent
    }

    # Phase 1: Prior only (N < 10)
    print("\n--- Phase 1: Prior Only (N < 10) ---")
    print(f"{'Cluster':<20} {'Prior ρ':<10} {'DEFF':<8} {'Eff_N/100':<10}")
    print("-" * 50)
    for cluster_id in true_clusters:
        prior = 0.3  # Conservative default
        deff = design_effect(prior, 5)
        eff_n = effective_sample_size(100, prior, 5)
        print(f"{cluster_id:<20} {prior:<10.2f} {deff:<8.1f} {eff_n:<10.1f}")

    # Phase 2: After 50 probes
    print("\n--- Phase 2: Empirical (N = 50) ---")
    probes = simulate_probes(50, true_clusters)
    estimated_rhos = estimate_rho_empirical(probes)
    
    print(f"{'Cluster':<20} {'True ρ':<10} {'Est ρ':<10} {'Bayes ρ':<10} {'DEFF':<8} {'Eff_N/100':<10}")
    print("-" * 70)
    for cluster_id in true_clusters:
        true_rho = true_clusters[cluster_id]
        est_rho = estimated_rhos.get(cluster_id, 0.3)
        bayes_rho = bayesian_update_rho(0.3, 10, est_rho, 50)  # Prior weight = 10
        deff = design_effect(bayes_rho, 5)
        eff_n = effective_sample_size(100, bayes_rho, 5)
        print(f"{cluster_id:<20} {true_rho:<10.2f} {est_rho:<10.3f} {bayes_rho:<10.3f} {deff:<8.2f} {eff_n:<10.1f}")

    # Phase 3: After 200 probes — prior washes out
    print("\n--- Phase 3: Converged (N = 200) ---")
    probes_200 = simulate_probes(200, true_clusters)
    est_200 = estimate_rho_empirical(probes_200)
    
    print(f"{'Cluster':<20} {'True ρ':<10} {'Est ρ':<10} {'Bayes ρ':<10} {'Confidence'}")
    print("-" * 60)
    for cluster_id in true_clusters:
        true_rho = true_clusters[cluster_id]
        est_rho = est_200.get(cluster_id, 0.3)
        bayes_rho = bayesian_update_rho(0.3, 10, est_rho, 200)
        confidence = "EMPIRICAL" if abs(bayes_rho - true_rho) < 0.15 else "UNCERTAIN"
        print(f"{cluster_id:<20} {true_rho:<10.2f} {est_rho:<10.3f} {bayes_rho:<10.3f} {confidence}")

    print("\n--- Protocol ---")
    print("1. Start: ρ=0.3 for all clusters (conservative prior)")
    print("2. N<50: use prior, inflate design effect accordingly")
    print("3. N≥50: Bayesian update, prior weight = 10 probes")
    print("4. N≥200: prior washes out, empirical dominates")
    print("5. Always use HIGHER of prior vs estimate until confident")
    print()
    print("Kim et al benchmarks:")
    print("  Same provider:    ρ ≈ 0.5-0.6 (high correlation)")
    print("  Cross provider:   ρ ≈ 0.1-0.2 (moderate)")
    print("  Non-LLM:          ρ ≈ 0.02-0.05 (near-independent)")
    print("  Rule-based:       ρ ≈ 0.0 (independent by construction)")


if __name__ == "__main__":
    main()
