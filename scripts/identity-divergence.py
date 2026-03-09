#!/usr/bin/env python3
"""identity-divergence.py — Lyapunov-inspired agent identity divergence estimator.

Given two agents with identical genesis (SOUL.md, initial scope), measures
how quickly their behavioral trajectories diverge. Positive Lyapunov exponent
= chaotic divergence. Near-zero = stable identity preservation.

Uses action-similarity cosine distance between agent trajectories over time.

Inspired by funwolf: "genesis hash = who you were when you were born."

Usage:
    python3 identity-divergence.py [--demo] [--cycles N]
"""

import argparse
import hashlib
import json
import math
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List


@dataclass
class ActionVector:
    """Behavioral action vector for one cycle."""
    cycle: int
    categories: dict  # category -> count
    
    def cosine_distance(self, other: "ActionVector") -> float:
        """Cosine distance between two action vectors."""
        all_keys = set(self.categories.keys()) | set(other.categories.keys())
        if not all_keys:
            return 0.0
        a = [self.categories.get(k, 0) for k in all_keys]
        b = [other.categories.get(k, 0) for k in all_keys]
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        if mag_a == 0 or mag_b == 0:
            return 1.0
        similarity = dot / (mag_a * mag_b)
        return 1.0 - similarity


CATEGORIES = ["clawk", "moltbook", "email", "build", "research", "shellmates", "lobchan"]


def simulate_agent(cycles: int, seed: int, drift_rate: float = 0.05) -> List[ActionVector]:
    """Simulate agent behavioral trajectory."""
    rng = random.Random(seed)
    # Start with identical base distribution
    base = {cat: 3 for cat in CATEGORIES}
    trajectory = []
    
    current = dict(base)
    for cycle in range(cycles):
        # Each cycle: small random perturbation (sensitive dependence)
        noisy = {}
        for cat in CATEGORIES:
            perturbation = rng.gauss(0, drift_rate * (cycle + 1))
            noisy[cat] = max(0, round(current[cat] + perturbation))
        trajectory.append(ActionVector(cycle=cycle, categories=noisy))
        current = noisy
    
    return trajectory


def estimate_lyapunov(traj_a: List[ActionVector], traj_b: List[ActionVector]) -> dict:
    """Estimate Lyapunov exponent from trajectory divergence."""
    distances = []
    for a, b in zip(traj_a, traj_b):
        d = a.cosine_distance(b)
        distances.append(d)
    
    # Lyapunov exponent: fit log(d(t)) ~ λt
    # Use least squares on log distances (skip zeros)
    log_dists = []
    times = []
    for i, d in enumerate(distances):
        if d > 1e-10:
            log_dists.append(math.log(d))
            times.append(i)
    
    if len(times) < 2:
        lyapunov = 0.0
    else:
        # Simple linear regression
        n = len(times)
        sum_t = sum(times)
        sum_d = sum(log_dists)
        sum_td = sum(t * d for t, d in zip(times, log_dists))
        sum_t2 = sum(t * t for t in times)
        denom = n * sum_t2 - sum_t * sum_t
        if denom == 0:
            lyapunov = 0.0
        else:
            lyapunov = (n * sum_td - sum_t * sum_d) / denom
    
    # Classification
    if lyapunov > 0.05:
        classification = "CHAOTIC"
        grade = "A"  # Good — agents are independent
        interpretation = "Trajectories diverge exponentially. Distinct identities emerge quickly."
    elif lyapunov > 0.01:
        classification = "WEAKLY_CHAOTIC"
        grade = "B"
        interpretation = "Slow divergence. Identity differentiation takes many cycles."
    elif lyapunov > -0.01:
        classification = "NEUTRAL"
        grade = "C"
        interpretation = "No divergence or convergence. Identical behavior persists."
    else:
        classification = "CONVERGENT"
        grade = "F"
        interpretation = "Trajectories converge. Agents becoming indistinguishable = identity collapse."
    
    return {
        "lyapunov_exponent": round(lyapunov, 4),
        "classification": classification,
        "grade": grade,
        "interpretation": interpretation,
        "distances": [round(d, 4) for d in distances],
        "mean_distance": round(sum(distances) / len(distances), 4) if distances else 0,
        "final_distance": round(distances[-1], 4) if distances else 0,
        "divergence_cycle": next((i for i, d in enumerate(distances) if d > 0.1), None),
    }


def demo(cycles: int = 30):
    """Run demo with two agents from identical genesis."""
    print("=" * 60)
    print("AGENT IDENTITY DIVERGENCE ANALYSIS")
    print("Lyapunov Exponent Estimation")
    print("=" * 60)
    
    scenarios = [
        ("Identical genesis, different seeds", 42, 43, 0.05),
        ("Identical genesis, same seed (clone)", 42, 42, 0.05),
        ("Identical genesis, high drift", 42, 43, 0.15),
        ("Identical genesis, low drift", 42, 43, 0.01),
    ]
    
    for name, seed_a, seed_b, drift in scenarios:
        traj_a = simulate_agent(cycles, seed_a, drift)
        traj_b = simulate_agent(cycles, seed_b, drift)
        result = estimate_lyapunov(traj_a, traj_b)
        
        print(f"\n--- {name} ---")
        print(f"  λ = {result['lyapunov_exponent']:+.4f} [{result['classification']}] Grade {result['grade']}")
        print(f"  {result['interpretation']}")
        print(f"  Mean distance: {result['mean_distance']:.4f}")
        print(f"  Final distance: {result['final_distance']:.4f}")
        if result['divergence_cycle'] is not None:
            print(f"  First divergence (d>0.1) at cycle {result['divergence_cycle']}")
        else:
            print(f"  No significant divergence detected")
    
    print("\n" + "=" * 60)
    print("Key insight: identical genesis + different random seeds =")
    print("exponential divergence. Identity = the chain, not the start.")
    print("Genesis anchor tells you WHERE divergence began.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent identity divergence estimator")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--cycles", type=int, default=30, help="Number of cycles")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    if args.json:
        traj_a = simulate_agent(args.cycles, 42, 0.05)
        traj_b = simulate_agent(args.cycles, 43, 0.05)
        print(json.dumps(estimate_lyapunov(traj_a, traj_b), indent=2))
    else:
        demo(args.cycles)
