#!/usr/bin/env python3
"""
neff-calculator.py — Effective witness count with infrastructure correlation penalties.

N_eff = N / (1 + (N-1)*ρ) where ρ = average pairwise failure correlation.
100 AWS instances at ρ≈0.95 → N_eff≈1.03. Useless.
3 diverse witnesses (SMTP + drand + isnad) at ρ≈0.1 → N_eff≈2.5. Real.

Correlation penalty: (1 - diversity_score)^shared_layer_count
Shared layers: cloud (1), provider+region (2), same rack (3), same process (4).

Usage:
    python3 neff-calculator.py --demo
    python3 neff-calculator.py --witnesses '["aws-1","aws-2","gcp-1"]' --correlations '{"aws-1,aws-2": 0.9, "aws-1,gcp-1": 0.2, "aws-2,gcp-1": 0.2}'
"""

import argparse
import json
import math
from itertools import combinations


def neff(n: int, rho: float) -> float:
    """Effective sample size given N witnesses and avg correlation rho."""
    if n <= 1:
        return 1.0
    return n / (1 + (n - 1) * rho)


def pairwise_to_avg_rho(correlations: dict, n: int) -> float:
    """Average pairwise correlation from a dict of pair→rho."""
    if not correlations:
        return 0.0
    return sum(correlations.values()) / max(len(correlations), 1)


def shared_layer_penalty(shared_layers: int, diversity_score: float = 0.0) -> float:
    """Correlation penalty from shared infrastructure layers."""
    return (1 - diversity_score) ** shared_layers


def grade_neff(n_eff: float, n_raw: int) -> str:
    """Grade the effective witness count."""
    ratio = n_eff / max(n_raw, 1)
    if ratio >= 0.8:
        return "A"  # genuinely diverse
    elif ratio >= 0.5:
        return "B"  # decent diversity
    elif ratio >= 0.2:
        return "C"  # some diversity
    elif ratio >= 0.05:
        return "D"  # mostly correlated
    else:
        return "F"  # monoculture


def demo():
    print("=== N_eff Calculator: Effective Witness Diversity ===\n")

    scenarios = [
        ("100 AWS instances (same region)", 100, 0.95),
        ("10 AWS instances (multi-region)", 10, 0.70),
        ("5 cloud providers", 5, 0.30),
        ("3 diverse (SMTP+drand+isnad)", 3, 0.10),
        ("Kit current (Clawk+email+WAL)", 3, 0.35),
        ("2 fully independent", 2, 0.0),
        ("1 witness (self-attestation)", 1, 0.0),
    ]

    print(f"{'Scenario':<40} {'N':>4} {'ρ':>6} {'N_eff':>7} {'Grade':>6}")
    print("-" * 70)
    for name, n, rho in scenarios:
        ne = neff(n, rho)
        g = grade_neff(ne, n)
        print(f"{name:<40} {n:>4} {rho:>6.2f} {ne:>7.2f} {g:>6}")

    print(f"\n=== Infrastructure Layer Penalties ===\n")
    print(f"{'Config':<35} {'Layers':>7} {'Diversity':>10} {'ρ_penalty':>10}")
    print("-" * 65)
    configs = [
        ("Same rack, same provider", 3, 0.0),
        ("Same cloud, different region", 1, 0.3),
        ("Different cloud, same protocol", 1, 0.5),
        ("Different cloud+protocol+substrate", 0, 0.8),
    ]
    for name, layers, div in configs:
        pen = shared_layer_penalty(layers, div)
        print(f"{name:<35} {layers:>7} {div:>10.1f} {pen:>10.4f}")

    print(f"\n=== Key Insight ===")
    print(f"  kampderp's law: node_count without architecture_diversity = confidence trap")
    print(f"  100 AWS (N_eff=1.03) < 3 diverse (N_eff=2.50)")
    print(f"  Correlation is the enemy. Independence is the product.")
    print(f"  O'Donoghue et al (2025): 85-97% of software = 3rd party deps.")
    print(f"  Same applies to witness infra: most 'independent' witnesses share deps.")

    # Kit's honest self-assessment
    print(f"\n=== Kit Self-Assessment ===")
    kit_witnesses = {
        "clawk": {"provider": "vercel", "protocol": "https", "substrate": "cloud"},
        "email": {"provider": "agentmail", "protocol": "smtp", "substrate": "cloud"},
        "wal": {"provider": "local", "protocol": "fs", "substrate": "vps"},
    }
    # Pairwise correlations
    # clawk↔email: both cloud, different protocol → ρ≈0.3
    # clawk↔wal: different everything → ρ≈0.1
    # email↔wal: different substrate → ρ≈0.15
    kit_rho = (0.3 + 0.1 + 0.15) / 3
    kit_ne = neff(3, kit_rho)
    kit_g = grade_neff(kit_ne, 3)
    print(f"  Witnesses: clawk (vercel/https), email (agentmail/smtp), WAL (local/fs)")
    print(f"  Avg ρ: {kit_rho:.3f}")
    print(f"  N_eff: {kit_ne:.2f} / 3 raw")
    print(f"  Grade: {kit_g}")
    print(f"  To improve: add drand (protocol diversity) or isnad sandbox (trust diversity)")


def main():
    parser = argparse.ArgumentParser(description="N_eff calculator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--witnesses", type=str)
    parser.add_argument("--correlations", type=str)
    args = parser.parse_args()

    if args.witnesses and args.correlations:
        witnesses = json.loads(args.witnesses)
        correlations = json.loads(args.correlations)
        n = len(witnesses)
        rho = pairwise_to_avg_rho(correlations, n)
        ne = neff(n, rho)
        g = grade_neff(ne, n)
        print(json.dumps({"n_raw": n, "avg_rho": round(rho, 4), "n_eff": round(ne, 4), "grade": g}))
    else:
        demo()


if __name__ == "__main__":
    main()
