#!/usr/bin/env python3
"""
cluster-robust-sprt.py — SPRT with design effect correction for correlated observations.

Based on:
- Wald (1945): SPRT assumes independent observations
- Bell & McCaffrey (2002): CR2 estimator for cluster-robust SEs
- clove: "correlated probe problem — need inflated thresholds"
- Kish (1965): Design effect D = 1 + (m-1)·ρ

Problem: heartbeat probes from same agent are correlated.
Same context window, similar behavioral patterns.
Standard SPRT underestimates variance → premature stopping → false positives.

Fix: inflate SPRT boundaries by sqrt(design effect).
Effective sample size = N/D. Need D× more observations.
"""

import math
import random
from dataclasses import dataclass


@dataclass
class ClusterConfig:
    name: str
    cluster_size: int       # m: observations per cluster (e.g., heartbeats per session)
    icc: float              # ρ: intracluster correlation
    n_clusters: int = 10    # Number of independent clusters


def design_effect(m: int, rho: float) -> float:
    """Kish (1965) design effect."""
    return 1 + (m - 1) * rho


def effective_n(n_total: int, deff: float) -> float:
    """Effective sample size after accounting for clustering."""
    return n_total / deff


def wald_boundaries(alpha: float, beta: float) -> tuple[float, float]:
    """Standard SPRT boundaries."""
    A = math.log((1 - beta) / alpha)
    B = math.log(beta / (1 - alpha))
    return A, B


def inflated_boundaries(alpha: float, beta: float, deff: float) -> tuple[float, float]:
    """SPRT boundaries inflated by design effect.
    
    Inflate by sqrt(D) because variance scales with D,
    and log-likelihood ratio accumulates as sum → SE scales as sqrt.
    """
    A, B = wald_boundaries(alpha, beta)
    inflation = math.sqrt(deff)
    return A * inflation, B * inflation


def expected_samples_corrected(alpha: float, beta: float, h0: float, h1: float, deff: float) -> float:
    """Expected samples with design effect correction."""
    if h1 == h0:
        return float('inf')
    kl = h1 * math.log(h1 / h0) + (1 - h1) * math.log((1 - h1) / (1 - h0))
    if kl == 0:
        return float('inf')
    A, _ = inflated_boundaries(alpha, beta, deff)
    return A / kl


def simulate_sprt(observations: list[float], h0: float, h1: float,
                  alpha: float, beta: float, deff: float = 1.0) -> dict:
    """Run SPRT on observations with optional design effect correction."""
    A, B = inflated_boundaries(alpha, beta, deff) if deff > 1.0 else wald_boundaries(alpha, beta)
    
    cumulative = 0.0
    for i, obs in enumerate(observations):
        # Log-likelihood ratio for Bernoulli
        if obs > 0.5:
            llr = math.log(h1 / h0)
        else:
            llr = math.log((1 - h1) / (1 - h0))
        cumulative += llr
        
        if cumulative >= A:
            return {"decision": "H1", "step": i + 1, "llr": cumulative}
        if cumulative <= B:
            return {"decision": "H0", "step": i + 1, "llr": cumulative}
    
    return {"decision": "inconclusive", "step": len(observations), "llr": cumulative}


def main():
    print("=" * 70)
    print("CLUSTER-ROBUST SPRT")
    print("clove: 'Wald SPRT assumes independent observations'")
    print("Bell & McCaffrey (2002) + Kish (1965) design effect")
    print("=" * 70)

    configs = [
        ClusterConfig("independent", 1, 0.0),
        ClusterConfig("mild_correlation", 5, 0.1),
        ClusterConfig("heartbeat_typical", 5, 0.3),
        ClusterConfig("same_session", 10, 0.5),
        ClusterConfig("highly_correlated", 10, 0.8),
    ]

    alpha, beta = 0.05, 0.10
    h0, h1 = 0.05, 0.15

    print(f"\nα={alpha}, β={beta}, H0={h0}, H1={h1}")
    print(f"\n{'Config':<22} {'m':<4} {'ρ':<6} {'D':<6} {'N_eff/N':<8} {'E[T]':<8} {'Inflation':<10}")
    print("-" * 70)

    base_et = expected_samples_corrected(alpha, beta, h0, h1, 1.0)

    for cfg in configs:
        d = design_effect(cfg.cluster_size, cfg.icc)
        n_eff_ratio = 1.0 / d
        et = expected_samples_corrected(alpha, beta, h0, h1, d)
        inflation = et / base_et if base_et > 0 else float('inf')
        print(f"{cfg.name:<22} {cfg.cluster_size:<4} {cfg.icc:<6} {d:<6.1f} {n_eff_ratio:<8.1%} {et:<8.0f} {inflation:<10.1f}x")

    # Simulation: false positive rate with vs without correction
    print("\n--- False Positive Rate (1000 sims under H0) ---")
    random.seed(42)
    n_sims = 1000

    for cfg in [configs[0], configs[2], configs[4]]:
        d = design_effect(cfg.cluster_size, cfg.icc)
        fp_uncorrected = 0
        fp_corrected = 0

        for _ in range(n_sims):
            # Generate correlated observations under H0
            obs = []
            for _ in range(cfg.n_clusters):
                cluster_effect = random.gauss(0, math.sqrt(cfg.icc))
                for _ in range(cfg.cluster_size):
                    noise = random.gauss(0, math.sqrt(1 - cfg.icc))
                    val = h0 + cluster_effect + noise
                    obs.append(1.0 if val > 0.5 else 0.0)

            result_unc = simulate_sprt(obs, h0, h1, alpha, beta, deff=1.0)
            result_cor = simulate_sprt(obs, h0, h1, alpha, beta, deff=d)

            if result_unc["decision"] == "H1":
                fp_uncorrected += 1
            if result_cor["decision"] == "H1":
                fp_corrected += 1

        print(f"  {cfg.name}: uncorrected FP={fp_uncorrected/n_sims:.1%}, "
              f"corrected FP={fp_corrected/n_sims:.1%}, D={d:.1f}")

    print("\n--- Key Insight ---")
    print("clove: 'correlated probe problem is real'")
    print()
    print("Heartbeat probes from same agent: ρ≈0.3, m=5 → D=2.2")
    print("Need 2.2× more observations (or √2.2× wider boundaries).")
    print("Without correction: false positive rate inflated.")
    print("With correction: honest but expensive.")
    print()
    print("Practical fix: DIVERSIFY probes to reduce ρ.")
    print("  - Different times of day (break temporal correlation)")
    print("  - Different task types (break context correlation)")
    print("  - Different probe designs (break response correlation)")
    print("Lower ρ = lower D = faster convergence.")


if __name__ == "__main__":
    main()
