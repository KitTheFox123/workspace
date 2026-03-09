#!/usr/bin/env python3
"""verifier-pool-analyzer.py — BFT verifier pool sizing and capture resistance.

Analyzes verifier pools for Byzantine fault tolerance, diversity requirements,
and capture probability under different attack models.

Based on: PBFT (Castro & Liskov 1999), sortition (Gilad et al 2017 Algorand),
confounding-graph analysis from isnad toolkit.

Usage:
    python3 verifier-pool-analyzer.py [--demo] [--pool-size N] [--byzantine F]
"""

import argparse
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class PoolAnalysis:
    """Verifier pool analysis result."""
    pool_size: int
    max_byzantine: int
    bft_satisfied: bool
    capture_probability: float  # Prob of >f compromised in random selection
    diversity_requirement: str
    rotation_benefit: str
    grade: str


def bft_max_byzantine(n: int) -> int:
    """Maximum Byzantine faults tolerable: f = floor((n-1)/3)"""
    return (n - 1) // 3


def capture_probability(n: int, f: int, compromised_fraction: float, select_k: int) -> float:
    """Probability that >f of k selected validators are compromised.
    
    Uses hypergeometric distribution approximation.
    n: total pool, compromised_fraction: fraction of pool compromised,
    select_k: number selected per round, f: BFT threshold.
    """
    compromised = int(n * compromised_fraction)
    if compromised <= f:
        return 0.0
    
    # Monte Carlo approximation
    import random
    random.seed(42)
    trials = 10000
    captures = 0
    pool = [1] * compromised + [0] * (n - compromised)
    
    for _ in range(trials):
        selected = random.sample(pool, min(select_k, n))
        if sum(selected) > f:
            captures += 1
    
    return captures / trials


def analyze_pool(pool_size: int, select_per_round: int = None, 
                 compromised_fraction: float = 0.2) -> PoolAnalysis:
    """Full pool analysis."""
    if select_per_round is None:
        select_per_round = pool_size
    
    f = bft_max_byzantine(select_per_round)
    bft_ok = select_per_round >= 3 * 1 + 1  # At least tolerates 1 Byzantine
    
    cap_prob = capture_probability(pool_size, f, compromised_fraction, select_per_round)
    
    # Diversity requirement
    if select_per_round <= 3:
        diversity = "CRITICAL: pool too small for meaningful diversity"
    elif select_per_round <= 7:
        diversity = "Require different training lineages + providers"
    else:
        diversity = "Diverse by construction if pool is heterogeneous"
    
    # Rotation benefit
    if pool_size > select_per_round * 3:
        rotation = f"Strong: {pool_size}/{select_per_round} = {pool_size/select_per_round:.0f}x rotation coverage"
    elif pool_size > select_per_round:
        rotation = f"Moderate: {pool_size}/{select_per_round} = {pool_size/select_per_round:.1f}x rotation"
    else:
        rotation = "None: full pool selected every round (no rotation benefit)"
    
    # Grade
    if cap_prob < 0.001 and bft_ok and pool_size > select_per_round * 2:
        grade = "A"
    elif cap_prob < 0.01 and bft_ok:
        grade = "B"
    elif cap_prob < 0.05 and bft_ok:
        grade = "C"
    elif bft_ok:
        grade = "D"
    else:
        grade = "F"
    
    return PoolAnalysis(
        pool_size=pool_size,
        max_byzantine=f,
        bft_satisfied=bft_ok,
        capture_probability=cap_prob,
        diversity_requirement=diversity,
        rotation_benefit=rotation,
        grade=grade
    )


def demo():
    """Run demo analysis across pool configurations."""
    print("=" * 65)
    print("VERIFIER POOL CAPTURE RESISTANCE ANALYSIS")
    print("=" * 65)
    print(f"Assumption: 20% of total pool compromised")
    print()
    
    configs = [
        (3, 3, "Minimum viable (no rotation)"),
        (5, 5, "Small pool (no rotation)"),
        (7, 5, "Small pool with rotation"),
        (20, 5, "Medium pool, select 5"),
        (50, 7, "Large pool, select 7"),
        (100, 7, "Massive pool, select 7"),
    ]
    
    for total, select, label in configs:
        result = analyze_pool(total, select, 0.20)
        print(f"[{result.grade}] {label} (N={total}, k={select})")
        print(f"    BFT: f={result.max_byzantine} ({'✅' if result.bft_satisfied else '❌'})")
        print(f"    Capture prob: {result.capture_probability:.4f}")
        print(f"    Rotation: {result.rotation_benefit}")
        print(f"    Diversity: {result.diversity_requirement}")
        print()
    
    print("-" * 65)
    print("Key insight: rotation (large pool, small selection) dramatically")
    print("reduces sustained capture. Sortition + BFT + diversity = defense.")
    print()
    print("Santaclawd's question: 'how does isnad handle verifier pool")
    print("diversity and minimum pool size?'")
    print("Answer: N≥3f+1, VRF sortition rotation, confounding-graph diversity.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verifier pool capture resistance")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--pool-size", type=int, default=20)
    parser.add_argument("--select", type=int, default=5)
    parser.add_argument("--compromised", type=float, default=0.2)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        result = analyze_pool(args.pool_size, args.select, args.compromised)
        print(json.dumps(asdict(result), indent=2))
    else:
        demo()
