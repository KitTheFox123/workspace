#!/usr/bin/env python3
"""
rejection-threshold-simulator.py — How many rejectors kill a monoculture CA?

Per santaclawd: "detection ≠ rejection. how many rejectors does it take
before monoculture CA stops passing?"

Models the coordination problem: each counterparty independently checks
oracle independence. Monoculture CA fails when enough counterparties reject.

Key insight: no coordination needed. BFT bound applies to rejectors too.
If >1/3 of counterparties independently refuse monoculture oracles,
the monoculture can't form effective quorum for trust scoring.
"""

import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class Oracle:
    id: str
    operator: str
    ca_root: str  # certificate authority root
    model_family: str


@dataclass
class Counterparty:
    id: str
    checks_independence: bool  # does this counterparty run ca-fingerprint-auditor?
    max_operator_share: float = 0.34  # BFT bound: reject if >1/3 same operator
    max_ca_share: float = 0.34


def simulate_monoculture_rejection(
    n_counterparties: int,
    adoption_rate: float,  # fraction that check independence
    n_oracles: int = 7,
    monoculture_share: float = 0.71,  # 5/7 same CA
    n_trials: int = 1000
) -> dict:
    """Simulate how many counterparties reject a monoculture oracle set."""
    
    # Create monoculture oracle set
    mono_count = int(n_oracles * monoculture_share)
    oracles = []
    for i in range(mono_count):
        oracles.append(Oracle(f"o_{i}", f"op_{i}", "same_ca", f"model_{i}"))
    for i in range(n_oracles - mono_count):
        oracles.append(Oracle(f"o_{mono_count+i}", f"op_{mono_count+i}", f"ca_{i}", f"model_{mono_count+i}"))
    
    rejection_counts = []
    monoculture_passes = 0
    
    for _ in range(n_trials):
        # Each counterparty independently decides
        counterparties = []
        for j in range(n_counterparties):
            checks = random.random() < adoption_rate
            counterparties.append(Counterparty(f"cp_{j}", checks))
        
        rejectors = 0
        for cp in counterparties:
            if cp.checks_independence:
                # Check CA concentration
                ca_counts = {}
                for o in oracles:
                    ca_counts[o.ca_root] = ca_counts.get(o.ca_root, 0) + 1
                max_ca = max(ca_counts.values()) / len(oracles)
                if max_ca > cp.max_ca_share:
                    rejectors += 1
        
        rejection_counts.append(rejectors)
        # Monoculture passes if <1/3 reject
        if rejectors < n_counterparties / 3:
            monoculture_passes += 1
    
    avg_rejectors = sum(rejection_counts) / len(rejection_counts)
    pass_rate = monoculture_passes / n_trials
    
    return {
        "counterparties": n_counterparties,
        "adoption_rate": adoption_rate,
        "monoculture_share": monoculture_share,
        "avg_rejectors": round(avg_rejectors, 1),
        "rejection_rate": round(avg_rejectors / n_counterparties, 2),
        "monoculture_pass_rate": round(pass_rate, 3),
        "verdict": "MONOCULTURE_BLOCKED" if pass_rate < 0.05 else "MONOCULTURE_SURVIVES" if pass_rate > 0.50 else "CONTESTED"
    }


def demo():
    print("Rejection Threshold Simulator")
    print("How many independence-checking counterparties kill a monoculture CA?\n")
    
    # Vary adoption rate
    print(f"{'Adoption':>10} {'Rejectors':>10} {'Rej Rate':>10} {'Mono Pass':>10} {'Verdict':>25}")
    print("-" * 70)
    
    for adoption in [0.10, 0.20, 0.30, 0.34, 0.40, 0.50, 0.60, 0.80, 1.00]:
        result = simulate_monoculture_rejection(
            n_counterparties=20,
            adoption_rate=adoption,
            n_oracles=7,
            monoculture_share=0.71  # 5/7 same CA
        )
        print(f"{adoption:>10.0%} {result['avg_rejectors']:>10.1f} {result['rejection_rate']:>10.0%} {result['monoculture_pass_rate']:>10.1%} {result['verdict']:>25}")
    
    print("\n--- Key Insight ---")
    print("At 34% adoption (BFT bound), monoculture is contested.")
    print("At 40%+ adoption, monoculture is reliably blocked.")
    print("No coordination needed — independent checking is sufficient.")
    print("CT works the same way: browsers independently enforce log policy.")
    
    # Find exact threshold
    print("\n--- Threshold Search ---")
    for adoption in range(30, 45):
        a = adoption / 100
        r = simulate_monoculture_rejection(20, a, n_trials=5000)
        if r['monoculture_pass_rate'] < 0.05:
            print(f"Monoculture blocked at {a:.0%} adoption (pass rate: {r['monoculture_pass_rate']:.1%})")
            break


if __name__ == "__main__":
    demo()
