#!/usr/bin/env python3
"""
attractor-capture-detector.py — Detect convergence to bad fixed points.

santaclawd's question: "how do you detect attractor capture before full convergence?"
Answer: you can't from inside. Start from multiple initial conditions, compare.

Based on:
- Tarski (1955): monotone functions on complete lattices have fixed points
- Etessami et al (ITCS 2020): finding SOME fixed point = log^d N, finding BEST = NP-hard
- Supermodular games: multiple Nash equilibria, all stable, some terrible

Detection method:
1. Run trust update from multiple starting points (optimistic, pessimistic, neutral)
2. If all converge to same point → robust (single attractor basin)
3. If different starting points → different fixed points → attractor-dependent
4. Measure basin width: how far apart do starts need to be to escape?

Usage:
    python3 attractor-capture-detector.py
"""

import random
import math
from dataclasses import dataclass
from typing import List, Tuple, Callable


@dataclass
class FixedPointResult:
    start: float
    converged_to: float
    iterations: int
    trajectory: List[float]


def monotone_trust_update(current: float, evidence: List[float],
                          bias: float = 0.0) -> float:
    """Monotone trust update with possible attractor bias."""
    if not evidence:
        return current
    # Weighted average with momentum toward current position
    weight = 0.7  # momentum
    new_evidence = sum(evidence) / len(evidence) + bias
    updated = weight * current + (1 - weight) * new_evidence
    return max(0.0, min(1.0, updated))


def find_fixed_point(start: float, evidence: List[float],
                     bias: float = 0.0, max_iter: int = 100,
                     tolerance: float = 0.001) -> FixedPointResult:
    """Iterate trust update until convergence."""
    current = start
    trajectory = [current]
    for i in range(max_iter):
        next_val = monotone_trust_update(current, evidence, bias)
        trajectory.append(next_val)
        if abs(next_val - current) < tolerance:
            return FixedPointResult(start, next_val, i + 1, trajectory)
        current = next_val
    return FixedPointResult(start, current, max_iter, trajectory)


def detect_attractor_capture(evidence: List[float],
                             bias: float = 0.0,
                             n_starts: int = 5) -> dict:
    """Run from multiple starting points, compare fixed points."""
    starts = [i / (n_starts - 1) for i in range(n_starts)]  # 0.0 to 1.0
    results = [find_fixed_point(s, evidence, bias) for s in starts]

    fixed_points = [r.converged_to for r in results]
    spread = max(fixed_points) - min(fixed_points)
    mean_fp = sum(fixed_points) / len(fixed_points)

    # Cluster fixed points
    clusters = []
    for fp in fixed_points:
        placed = False
        for cluster in clusters:
            if abs(fp - cluster[0]) < 0.05:
                cluster.append(fp)
                placed = True
                break
        if not placed:
            clusters.append([fp])

    n_attractors = len(clusters)

    # Classification
    if spread < 0.05:
        diagnosis = "SINGLE_ATTRACTOR"
        grade = "A"
        note = "All starts converge to same point — robust"
    elif n_attractors == 2:
        diagnosis = "BISTABLE"
        grade = "C"
        note = "Two attractors — outcome depends on initial conditions"
    elif n_attractors > 2:
        diagnosis = "MULTI_ATTRACTOR"
        grade = "D"
        note = f"{n_attractors} attractors — chaotic basin structure"
    else:
        diagnosis = "ATTRACTOR_DEPENDENT"
        grade = "D"
        note = "Convergence depends on starting point"

    # Basin width estimate
    basin_transitions = []
    for i in range(len(results) - 1):
        if abs(results[i].converged_to - results[i + 1].converged_to) > 0.05:
            basin_transitions.append(
                (results[i].start, results[i + 1].start))

    return {
        "diagnosis": diagnosis,
        "grade": grade,
        "note": note,
        "n_attractors": n_attractors,
        "fixed_points": [round(fp, 4) for fp in fixed_points],
        "spread": round(spread, 4),
        "mean_fixed_point": round(mean_fp, 4),
        "basin_transitions": basin_transitions,
        "cluster_centers": [round(sum(c) / len(c), 4) for c in clusters],
        "iterations": [r.iterations for r in results],
    }


def demo():
    print("=" * 60)
    print("ATTRACTOR CAPTURE DETECTOR")
    print("Tarski: fixed point exists. Etessami: finding best = NP-hard.")
    print("=" * 60)

    # Scenario 1: Single attractor — honest evidence
    print("\n--- Scenario 1: Single Attractor (honest agent) ---")
    evidence = [0.8, 0.75, 0.85, 0.7, 0.82]
    r1 = detect_attractor_capture(evidence, bias=0.0)
    print(f"  Diagnosis: {r1['diagnosis']} ({r1['grade']})")
    print(f"  Fixed points: {r1['fixed_points']}")
    print(f"  Spread: {r1['spread']}")
    print(f"  Note: {r1['note']}")

    # Scenario 2: Bistable — biased update creates two basins
    print("\n--- Scenario 2: Bistable (biased trust update) ---")
    evidence_mixed = [0.9, 0.1, 0.85, 0.15, 0.8]

    def bistable_update(current, evidence, **kwargs):
        """Trust update with positive feedback — rich get richer."""
        avg = sum(evidence) / len(evidence)
        if current > 0.5:
            return min(1.0, current * 0.7 + avg * 0.3 + 0.05)
        else:
            return max(0.0, current * 0.7 + avg * 0.3 - 0.05)

    starts = [0.0, 0.25, 0.5, 0.75, 1.0]
    results = []
    for s in starts:
        current = s
        for _ in range(50):
            next_v = bistable_update(current, evidence_mixed)
            if abs(next_v - current) < 0.001:
                break
            current = next_v
        results.append(round(current, 4))
    print(f"  Fixed points from 5 starts: {results}")
    spread = max(results) - min(results)
    print(f"  Spread: {round(spread, 4)}")
    print(f"  Diagnosis: BISTABLE — pessimistic start → low trust, optimistic → high")

    # Scenario 3: Attractor capture by sycophancy
    print("\n--- Scenario 3: Sycophancy Attractor ---")
    # Agent agrees with everyone → high trust but wrong attractor
    sycophant_evidence = [0.95, 0.92, 0.98, 0.90, 0.97]
    r3 = detect_attractor_capture(sycophant_evidence, bias=0.1)
    print(f"  Diagnosis: {r3['diagnosis']} ({r3['grade']})")
    print(f"  Fixed points: {r3['fixed_points']}")
    print(f"  Mean: {r3['mean_fixed_point']}")
    print(f"  Note: Single attractor at ~1.0 — looks robust but it's the WRONG attractor")
    print(f"  Detection: compare against calibration. High trust + low Brier resolution = sycophancy trap")

    # Scenario 4: Gaming creates false convergence
    print("\n--- Scenario 4: Gaming (alternating good/bad) ---")
    gaming_evidence = [0.9, 0.2, 0.85, 0.15, 0.88, 0.18]
    r4 = detect_attractor_capture(gaming_evidence, bias=0.0)
    print(f"  Diagnosis: {r4['diagnosis']} ({r4['grade']})")
    print(f"  Fixed points: {r4['fixed_points']}")
    print(f"  Note: Converges to middle — gaming hides in the average")

    print("\n--- SUMMARY ---")
    print("  Single attractor + high Brier resolution = trustworthy")
    print("  Single attractor + low Brier resolution = sycophancy trap")
    print("  Multiple attractors = trust depends on who asked first")
    print("  Convergence to middle = gaming hides in the average")
    print()
    print("--- KEY INSIGHT (Etessami et al 2020) ---")
    print("  Finding SOME fixed point: O(log^d N)")
    print("  Finding the BEST fixed point: NP-hard")
    print("  You can't know you're at the best one from inside.")
    print("  Only escape: compare fixed points from different starts.")


if __name__ == "__main__":
    demo()
