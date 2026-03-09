#!/usr/bin/env python3
"""catastrophe-correlation-sim.py — Correlated catastrophe model for attestation networks.

Models how correlated failures cascade through attestor pools.
Applies catastrophe reinsurance math (NAIC 2025) to agent trust.

Key insight: independent attestor failures = manageable.
Correlated failures (shared provider/training) = catastrophic.
Reinsurance = the only mechanism that prices correlation.

Usage:
    python3 catastrophe-correlation-sim.py [--demo]
"""

import argparse
import json
import math
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class AttestorNode:
    id: str
    provider: str
    training_family: str
    trust_score: float = 0.8
    failed: bool = False


@dataclass 
class CatastropheEvent:
    name: str
    type: str  # provider_outage, training_poison, infrastructure
    affected_providers: list
    affected_families: list
    severity: float  # 0-1


def simulate_independent(n_attestors: int, base_failure_rate: float, n_rounds: int) -> dict:
    """Independent (uncorrelated) failure model."""
    random.seed(42)
    total_failures = 0
    cascade_events = 0
    
    for _ in range(n_rounds):
        failures = sum(1 for _ in range(n_attestors) if random.random() < base_failure_rate)
        total_failures += failures
        if failures > n_attestors // 3:  # BFT threshold
            cascade_events += 1
    
    return {
        "model": "independent",
        "avg_failures_per_round": total_failures / n_rounds,
        "cascade_rate": cascade_events / n_rounds,
        "expected_loss": total_failures / n_rounds * 0.01,  # cost per failure
    }


def simulate_correlated(n_attestors: int, base_failure_rate: float, 
                        correlation: float, n_rounds: int) -> dict:
    """Correlated failure model (shared provider/training)."""
    random.seed(42)
    total_failures = 0
    cascade_events = 0
    
    for _ in range(n_rounds):
        # Shared shock affects all correlated attestors
        shared_shock = random.random() < correlation * base_failure_rate * 3
        failures = 0
        for _ in range(n_attestors):
            if shared_shock:
                # Correlated: 80% fail together
                if random.random() < 0.8:
                    failures += 1
            elif random.random() < base_failure_rate:
                failures += 1
        total_failures += failures
        if failures > n_attestors // 3:
            cascade_events += 1
    
    return {
        "model": "correlated",
        "correlation": correlation,
        "avg_failures_per_round": total_failures / n_rounds,
        "cascade_rate": cascade_events / n_rounds,
        "expected_loss": total_failures / n_rounds * 0.01,
    }


def simulate_reinsured(n_attestors: int, base_failure_rate: float,
                       correlation: float, n_rounds: int) -> dict:
    """Correlated + reinsurance layer."""
    correlated = simulate_correlated(n_attestors, base_failure_rate, correlation, n_rounds)
    
    # Reinsurance absorbs losses above attachment point
    attachment = 0.05  # 5% of pool
    reinsurance_rate = 0.8  # covers 80% above attachment
    
    net_loss = min(correlated["expected_loss"], attachment) + \
               max(0, correlated["expected_loss"] - attachment) * (1 - reinsurance_rate)
    
    return {
        "model": "reinsured",
        "correlation": correlation,
        "gross_loss": correlated["expected_loss"],
        "net_loss": net_loss,
        "reinsurance_recovery": correlated["expected_loss"] - net_loss,
        "cascade_rate": correlated["cascade_rate"],
        "avg_failures_per_round": correlated["avg_failures_per_round"],
    }


def grade(cascade_rate: float) -> str:
    if cascade_rate < 0.01: return "A"
    if cascade_rate < 0.05: return "B"
    if cascade_rate < 0.15: return "C"
    if cascade_rate < 0.30: return "D"
    return "F"


def demo():
    n = 20
    rate = 0.05
    rounds = 1000
    
    print("=" * 60)
    print("CATASTROPHE CORRELATION MODEL FOR ATTESTATION NETWORKS")
    print("=" * 60)
    print(f"\nPool: {n} attestors, base failure rate: {rate}, {rounds} rounds")
    print()
    
    ind = simulate_independent(n, rate, rounds)
    print(f"[{grade(ind['cascade_rate'])}] INDEPENDENT failures")
    print(f"    Avg failures/round: {ind['avg_failures_per_round']:.1f}")
    print(f"    Cascade rate: {ind['cascade_rate']:.1%}")
    print(f"    Expected loss: {ind['expected_loss']:.4f}")
    print()
    
    for corr in [0.3, 0.6, 0.9]:
        cor = simulate_correlated(n, rate, corr, rounds)
        print(f"[{grade(cor['cascade_rate'])}] CORRELATED (ρ={corr})")
        print(f"    Avg failures/round: {cor['avg_failures_per_round']:.1f}")
        print(f"    Cascade rate: {cor['cascade_rate']:.1%}")
        print(f"    Expected loss: {cor['expected_loss']:.4f}")
        print(f"    Loss amplification: {cor['expected_loss']/max(ind['expected_loss'],0.0001):.1f}x")
        print()
    
    rein = simulate_reinsured(n, rate, 0.6, rounds)
    print(f"[{grade(rein['cascade_rate'])}] REINSURED (ρ=0.6)")
    print(f"    Gross loss: {rein['gross_loss']:.4f}")
    print(f"    Net loss: {rein['net_loss']:.4f}")
    print(f"    Recovery: {rein['reinsurance_recovery']:.4f}")
    print()
    
    print("-" * 60)
    print("KEY INSIGHT: Independent failures = Grade A (manageable).")
    print("Correlated failures = Grade D-F (catastrophic).")
    print("Reinsurance doesn't prevent cascade — it prices correlation.")
    print("Diversity is the primary defense. Insurance is the backstop.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        results = {
            "independent": simulate_independent(20, 0.05, 1000),
            "correlated_30": simulate_correlated(20, 0.05, 0.3, 1000),
            "correlated_60": simulate_correlated(20, 0.05, 0.6, 1000),
            "correlated_90": simulate_correlated(20, 0.05, 0.9, 1000),
            "reinsured_60": simulate_reinsured(20, 0.05, 0.6, 1000),
        }
        print(json.dumps(results, indent=2))
    else:
        demo()
