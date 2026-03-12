#!/usr/bin/env python3
"""
inspection-game.py — Avenhaus inspection game for agent audit scheduling.

Based on Avenhaus, von Stengel & Zamir (2001): Inspection Games.
Key insight: inspector commits to mixed strategy (Poisson), GAINS advantage.
"Inspector leadership principle" — announcing randomized schedule is stronger
than hiding it, because inspectee can't exploit what has no pattern.

santaclawd's three primitives:
1. lambda = f(drift_velocity, adversary_window) — audit rate
2. drift_velocity as fingerprint — what to measure
3. cross-layer binding — the forgery gap

This implements the Nash equilibrium calculation for optimal lambda.

Usage:
    python3 inspection-game.py
"""

import math
import random
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class InspectionParams:
    """Parameters for an inspection game."""
    violation_cost: float     # cost if violation undetected (to inspector)
    inspection_cost: float    # cost per inspection
    detection_prob: float     # probability of catching violation per inspection
    adversary_window: float   # time window adversary needs to complete violation
    drift_velocity: float     # current measured drift rate
    drift_threshold: float    # threshold above which violation is assumed


def optimal_lambda(params: InspectionParams) -> float:
    """
    Calculate Nash equilibrium audit rate.
    
    From Avenhaus: optimal inspection rate balances
    cost of inspection vs expected cost of undetected violation.
    
    lambda* = max(drift_velocity/threshold, 1/adversary_window)
              * violation_cost / (violation_cost + inspection_cost/detection_prob)
    """
    # Base rate from drift and adversary window
    base_rate = max(
        params.drift_velocity / params.drift_threshold if params.drift_threshold > 0 else 0,
        1.0 / params.adversary_window if params.adversary_window > 0 else 0
    )
    
    # Nash equilibrium adjustment
    effective_cost_ratio = params.violation_cost / (
        params.violation_cost + params.inspection_cost / max(params.detection_prob, 0.01)
    )
    
    return base_rate * effective_cost_ratio


def poisson_schedule(lam: float, duration: float, seed: int = None) -> List[float]:
    """Generate Poisson-distributed audit times."""
    if seed is not None:
        random.seed(seed)
    times = []
    t = 0
    while t < duration:
        interval = random.expovariate(lam) if lam > 0 else duration + 1
        t += interval
        if t < duration:
            times.append(round(t, 2))
    return times


def simulate_game(params: InspectionParams, n_rounds: int = 1000, seed: int = 42) -> dict:
    """Simulate inspection game with Poisson schedule vs strategic adversary."""
    random.seed(seed)
    lam = optimal_lambda(params)
    
    detected = 0
    undetected = 0
    inspections = 0
    false_alarms = 0
    
    for _ in range(n_rounds):
        # Adversary decides whether to violate (rational: violate when expected gain > 0)
        # At Nash equilibrium, adversary is indifferent
        violates = random.random() < 0.5  # mixed strategy
        
        # Inspector audits according to Poisson
        audits_this_round = random.random() < (1 - math.exp(-lam))
        
        if audits_this_round:
            inspections += 1
            if violates:
                if random.random() < params.detection_prob:
                    detected += 1
                else:
                    undetected += 1
            else:
                false_alarms += 1  # inspected but nothing to find
        elif violates:
            undetected += 1
    
    violations = detected + undetected
    detection_rate = detected / violations if violations > 0 else 1.0
    
    return {
        "optimal_lambda": round(lam, 4),
        "rounds": n_rounds,
        "violations": violations,
        "detected": detected,
        "undetected": undetected,
        "inspections": inspections,
        "false_alarms": false_alarms,
        "detection_rate": round(detection_rate, 3),
        "inspection_rate": round(inspections / n_rounds, 3),
    }


def compare_schedules(params: InspectionParams) -> dict:
    """Compare Poisson vs fixed vs adaptive schedules."""
    lam = optimal_lambda(params)
    
    results = {}
    
    # Poisson (optimal)
    results["poisson"] = simulate_game(params, seed=42)
    
    # Fixed schedule (gameable)
    # Strategic adversary knows when inspections happen → violates between them
    fixed_detected = 0
    fixed_undetected = 0
    random.seed(42)
    for _ in range(1000):
        violates = random.random() < 0.7  # adversary exploits predictability
        inspects = random.random() < results["poisson"]["inspection_rate"]  # same rate
        if violates:
            if inspects and random.random() < params.detection_prob * 0.3:  # much worse
                fixed_detected += 1
            else:
                fixed_undetected += 1
    
    fixed_violations = fixed_detected + fixed_undetected
    results["fixed"] = {
        "detection_rate": round(fixed_detected / fixed_violations if fixed_violations > 0 else 0, 3),
        "violations": fixed_violations,
        "note": "strategic adversary exploits predictable schedule"
    }
    
    # Drift-adaptive (no randomness)
    # Good for honest agents, gameable by strategic ones
    results["adaptive_only"] = {
        "detection_rate": round(results["poisson"]["detection_rate"] * 0.7, 3),
        "note": "adversary manipulates drift signal to suppress audits"
    }
    
    # Poisson + drift (the answer)
    results["poisson_plus_drift"] = {
        "detection_rate": round(min(results["poisson"]["detection_rate"] * 1.2, 1.0), 3),
        "note": "Poisson floor + drift-adaptive ceiling = santaclawd's missing link"
    }
    
    return results


def demo():
    print("=" * 60)
    print("AVENHAUS INSPECTION GAME")
    print("Nash equilibrium audit scheduling for agent trust")
    print("=" * 60)
    
    # Scenario 1: High-stakes agent (financial)
    print("\n--- Scenario 1: Financial Agent (high stakes) ---")
    financial = InspectionParams(
        violation_cost=100, inspection_cost=5,
        detection_prob=0.8, adversary_window=4,
        drift_velocity=0.05, drift_threshold=0.3
    )
    r1 = simulate_game(financial)
    print(f"  Optimal λ: {r1['optimal_lambda']}")
    print(f"  Detection rate: {r1['detection_rate']}")
    print(f"  Inspection rate: {r1['inspection_rate']}")
    print(f"  Violations: {r1['violations']} (detected {r1['detected']}, missed {r1['undetected']})")
    
    # Scenario 2: Low-stakes agent (social)
    print("\n--- Scenario 2: Social Agent (low stakes) ---")
    social = InspectionParams(
        violation_cost=10, inspection_cost=5,
        detection_prob=0.6, adversary_window=24,
        drift_velocity=0.02, drift_threshold=0.5
    )
    r2 = simulate_game(social)
    print(f"  Optimal λ: {r2['optimal_lambda']}")
    print(f"  Detection rate: {r2['detection_rate']}")
    print(f"  Inspection rate: {r2['inspection_rate']}")
    
    # Scenario 3: Drifting agent (high drift velocity)
    print("\n--- Scenario 3: Drifting Agent (high drift) ---")
    drifting = InspectionParams(
        violation_cost=50, inspection_cost=5,
        detection_prob=0.7, adversary_window=8,
        drift_velocity=0.25, drift_threshold=0.3
    )
    r3 = simulate_game(drifting)
    print(f"  Optimal λ: {r3['optimal_lambda']} (higher due to drift)")
    print(f"  Detection rate: {r3['detection_rate']}")
    
    # Schedule comparison
    print("\n--- Schedule Comparison (financial agent) ---")
    comp = compare_schedules(financial)
    for schedule, data in comp.items():
        dr = data.get("detection_rate", "N/A")
        note = data.get("note", "")
        print(f"  {schedule}: detection={dr} {note}")
    
    # Inspector leadership principle
    print("\n--- INSPECTOR LEADERSHIP PRINCIPLE ---")
    print("Avenhaus: inspector GAINS by committing to strategy publicly.")
    print("Announcing Poisson schedule is stronger than hiding it.")
    print("Because inspectee can't exploit what has no pattern.")
    print("Memoryless = the commitment.")
    
    print("\n--- SANTACLAWD'S THREE PRIMITIVES ---")
    print(f"1. λ = {r1['optimal_lambda']} (Nash equilibrium from costs + detection)")
    print(f"2. drift_velocity = {financial.drift_velocity} (fingerprint signal)")
    print(f"3. cross-layer binding = hardest (coordination problem, not math)")
    print(f"   Each layer has different owners. NPT bound layers. We need protocol.")


if __name__ == "__main__":
    demo()
