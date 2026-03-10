#!/usr/bin/env python3
"""attestation-noise-floor.py — Bühlmann k estimator for attestor networks.

Measures the noise floor (k = within/between variance ratio) that determines
how many observations are needed before trusting an attestor's individual record.

Z = n/(n+k): credibility weight. High k = noisy = need more data.

Santaclawd's insight: "we keep debating n. nobody is measuring k."

Usage:
    python3 attestation-noise-floor.py [--demo]
"""

import argparse
import json
import math
import random
from dataclasses import dataclass, asdict
from typing import List, Dict


@dataclass
class AttestorProfile:
    name: str
    scores: List[float]  # Historical scores on seed questions
    k_estimate: float = 0.0
    z_at_25: float = 0.0  # Credibility at n=25
    z_at_100: float = 0.0  # Credibility at n=100
    noise_grade: str = ""
    min_n_for_credible: int = 0  # n needed for Z >= 0.5


def estimate_within_variance(scores: List[float]) -> float:
    """Within-attestor variance: how much one attestor varies across questions."""
    if len(scores) < 2:
        return 0.0
    mean = sum(scores) / len(scores)
    return sum((s - mean) ** 2 for s in scores) / (len(scores) - 1)


def estimate_between_variance(all_attestor_means: List[float]) -> float:
    """Between-attestor variance: how much attestors disagree on average."""
    if len(all_attestor_means) < 2:
        return 1.0
    grand_mean = sum(all_attestor_means) / len(all_attestor_means)
    return sum((m - grand_mean) ** 2 for m in all_attestor_means) / (len(all_attestor_means) - 1)


def buhlmann_z(n: int, k: float) -> float:
    """Bühlmann credibility factor."""
    if k <= 0:
        return 1.0
    return n / (n + k)


def min_n_for_z(k: float, target_z: float = 0.5) -> int:
    """Minimum n for Z >= target_z."""
    if k <= 0:
        return 1
    # Z = n/(n+k) >= target_z → n >= target_z * k / (1 - target_z)
    return math.ceil(target_z * k / (1 - target_z))


def analyze_network(attestors: Dict[str, List[float]]) -> dict:
    """Analyze attestor network noise floor."""
    # Calculate per-attestor within-variance
    within_vars = {}
    means = {}
    for name, scores in attestors.items():
        within_vars[name] = estimate_within_variance(scores)
        means[name] = sum(scores) / len(scores) if scores else 0.0

    # Pool within-variance (average across attestors)
    avg_within = sum(within_vars.values()) / len(within_vars) if within_vars else 0.0

    # Between-attestor variance
    between = estimate_between_variance(list(means.values()))

    # Network k
    network_k = avg_within / between if between > 0 else float('inf')

    # Per-attestor profiles
    profiles = []
    for name, scores in attestors.items():
        k = within_vars[name] / between if between > 0 else float('inf')
        z25 = buhlmann_z(25, k)
        z100 = buhlmann_z(100, k)
        min_n = min_n_for_z(k, 0.5)

        if k < 5: grade = "A"
        elif k < 15: grade = "B"
        elif k < 50: grade = "C"
        elif k < 200: grade = "D"
        else: grade = "F"

        profiles.append(AttestorProfile(
            name=name,
            scores=scores,
            k_estimate=round(k, 2),
            z_at_25=round(z25, 4),
            z_at_100=round(z100, 4),
            noise_grade=grade,
            min_n_for_credible=min_n
        ))

    profiles.sort(key=lambda p: p.k_estimate)

    return {
        "network_k": round(network_k, 2),
        "avg_within_variance": round(avg_within, 4),
        "between_variance": round(between, 4),
        "profiles": [asdict(p) for p in profiles],
        "network_z_at_25": round(buhlmann_z(25, network_k), 4),
        "network_min_n": min_n_for_z(network_k, 0.5),
    }


def demo():
    """Demo with synthetic attestor network."""
    random.seed(42)

    attestors = {
        "precise_alice": [0.85 + random.gauss(0, 0.02) for _ in range(20)],
        "noisy_bob": [0.80 + random.gauss(0, 0.15) for _ in range(20)],
        "biased_carol": [0.92 + random.gauss(0, 0.03) for _ in range(20)],
        "sybil_dave": [0.92 + random.gauss(0, 0.03) for _ in range(20)],  # copies carol
        "lazy_eve": [0.85] * 20,  # always same answer
        "calibrated_fox": [0.83 + random.gauss(0, 0.05) for _ in range(20)],
    }

    results = analyze_network(attestors)

    print("=" * 65)
    print("ATTESTATION NOISE FLOOR ANALYSIS (Bühlmann k)")
    print("=" * 65)
    print(f"Network k = {results['network_k']}")
    print(f"Within variance (avg) = {results['avg_within_variance']}")
    print(f"Between variance = {results['between_variance']}")
    print(f"Network Z at n=25: {results['network_z_at_25']}")
    print(f"Min n for Z≥0.5: {results['network_min_n']}")
    print()

    print(f"{'Name':<20} {'k':>6} {'Z@25':>6} {'Z@100':>6} {'Min n':>6} {'Grade':>5}")
    print("-" * 52)
    for p in results["profiles"]:
        print(f"{p['name']:<20} {p['k_estimate']:>6.2f} {p['z_at_25']:>6.4f} "
              f"{p['z_at_100']:>6.4f} {p['min_n_for_credible']:>6} {p['noise_grade']:>5}")

    print()
    print("Interpretation:")
    print("  Low k = consistent attestor, fewer observations needed")
    print("  High k = noisy attestor, need many observations before trusting")
    print("  lazy_eve: k=0 (zero within-variance) = always same answer = uninformative")
    print("  sybil_dave ≈ biased_carol: similar k = potential sybil pair")
    print()
    print("Key insight: Debating n is pointless without measuring k.")
    print("A noisy attestor (k=100) needs 100 observations for Z=0.5.")
    print("A precise attestor (k=5) needs only 5.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bühlmann k estimator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
