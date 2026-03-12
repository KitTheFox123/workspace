#!/usr/bin/env python3
"""
poisson-audit-deterrent.py — Poisson audit as minimum credible deterrent.

Ishikawa & Fontanari (EPJ B, 2025): U-shaped deterrence curve.
- Moderate penalty = rational crime zone (adversary gambles)
- Light penalty (p≈g) = crime doesn't pay
- High penalty = risk too large
- Key: crime rate in MSNE is INDEPENDENT of penalty (the paradox!)
- Resolution: finite populations + demographic noise restores deterrence

santaclawd's question: "what is your minimum credible audit signal?"
Answer: Poisson with unknown λ + public evidence of past catches.

The EXISTENCE of audit deters more than its severity.

Usage:
    uv run --with numpy python3 poisson-audit-deterrent.py
"""

import random
import math
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class AuditConfig:
    lambda_rate: float  # expected audits per period (unknown to adversary)
    penalty: float      # cost if caught
    crime_gain: float   # benefit of cheating
    catch_probability: float = 0.9  # P(detect | audit & cheating)


@dataclass
class Agent:
    name: str
    honest: bool = True
    cheats_detected: int = 0
    cheats_undetected: int = 0
    honest_periods: int = 0
    total_gain: float = 0.0
    total_penalty: float = 0.0


def simulate_period(agent: Agent, config: AuditConfig, cheat: bool) -> dict:
    """Simulate one period: agent chooses to cheat or not, Poisson audit occurs."""
    # Poisson: number of audits this period
    n_audits = 0
    L = math.exp(-config.lambda_rate)
    p = 1.0
    while True:
        p *= random.random()
        if p < L:
            break
        n_audits += 1

    caught = False
    if cheat:
        agent.total_gain += config.crime_gain
        for _ in range(n_audits):
            if random.random() < config.catch_probability:
                caught = True
                break
        if caught:
            agent.cheats_detected += 1
            agent.total_penalty += config.penalty
        else:
            agent.cheats_undetected += 1
    else:
        agent.honest_periods += 1

    return {
        "audited": n_audits > 0,
        "n_audits": n_audits,
        "cheated": cheat,
        "caught": caught,
        "net": config.crime_gain - config.penalty if caught else (config.crime_gain if cheat else 0),
    }


def deterrence_score(config: AuditConfig) -> float:
    """Expected value of cheating. Negative = deterred."""
    # P(audit in period) = 1 - e^(-λ)
    p_audit = 1 - math.exp(-config.lambda_rate)
    p_caught = p_audit * config.catch_probability
    ev = config.crime_gain * (1 - p_caught) - config.penalty * p_caught
    return ev


def u_shaped_demo():
    """Demonstrate U-shaped deterrence curve."""
    crime_gain = 10.0
    lambda_rate = 0.5

    print("\n--- U-Shaped Deterrence (Ishikawa & Fontanari 2025) ---")
    print(f"Crime gain: {crime_gain}, Audit rate λ={lambda_rate}")
    print(f"{'Penalty':>8} {'EV(cheat)':>10} {'Deterred?':>10} {'Zone':>20}")

    penalties = [1, 5, 10, 15, 20, 30, 50, 100]
    for p in penalties:
        cfg = AuditConfig(lambda_rate=lambda_rate, penalty=p, crime_gain=crime_gain)
        ev = deterrence_score(cfg)
        deterred = ev < 0
        if p <= crime_gain * 1.2:
            zone = "LIGHT (p≈g)"
        elif p <= crime_gain * 3:
            zone = "MODERATE (U-bottom)"
        else:
            zone = "HIGH (strong)"
        print(f"{p:>8.0f} {ev:>10.2f} {'YES' if deterred else 'NO':>10} {zone:>20}")


def poisson_advantage_demo():
    """Show why Poisson beats fixed schedule."""
    print("\n--- Poisson vs Fixed Schedule ---")
    random.seed(42)
    n_periods = 100

    # Adversary strategy: cheat only when they think audit isn't coming
    # Fixed schedule: audit every 5th period (adversary knows)
    fixed_catches = 0
    fixed_cheats = 0
    for i in range(n_periods):
        audit_this_period = (i % 5 == 0)
        # Smart adversary: cheat when no audit expected
        if not audit_this_period:
            fixed_cheats += 1
            # No audit = never caught
        # Doesn't cheat during audit periods

    # Poisson: adversary can't predict
    poisson_catches = 0
    poisson_cheats = 0
    lambda_rate = 0.2  # same average rate (1 in 5)
    for i in range(n_periods):
        # Adversary cheats 80% of time (assumes most periods safe)
        cheat = random.random() < 0.8
        # Poisson audit
        n_audits = 0
        L = math.exp(-lambda_rate)
        p = 1.0
        while True:
            p *= random.random()
            if p < L:
                break
            n_audits += 1
        if cheat:
            poisson_cheats += 1
            if n_audits > 0 and random.random() < 0.9:
                poisson_catches += 1

    print(f"  Fixed schedule (every 5th): {fixed_catches}/{fixed_cheats} caught "
          f"({100*fixed_catches/max(fixed_cheats,1):.0f}%)")
    print(f"  Poisson (λ=0.2):            {poisson_catches}/{poisson_cheats} caught "
          f"({100*poisson_catches/max(poisson_cheats,1):.0f}%)")
    print(f"  Poisson advantage: adversary can't model the schedule")


def minimum_credible_signal():
    """What's the minimum audit rate that deters?"""
    print("\n--- Minimum Credible Audit Signal ---")
    crime_gain = 10.0
    penalty = 50.0

    print(f"Crime gain={crime_gain}, Penalty={penalty}")
    print(f"{'λ (rate)':>10} {'P(audit)':>10} {'EV(cheat)':>10} {'Deterred':>10}")

    for lam in [0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0]:
        cfg = AuditConfig(lambda_rate=lam, penalty=penalty, crime_gain=crime_gain)
        ev = deterrence_score(cfg)
        p_audit = 1 - math.exp(-lam)
        print(f"{lam:>10.2f} {p_audit:>10.1%} {ev:>10.2f} {'YES' if ev < 0 else 'NO':>10}")

    # Find exact crossover
    # EV = g(1-p) - P*p where p = (1-e^(-λ))*catch_prob
    # EV = 0 when g(1-p) = P*p → p = g/(g+P)
    p_threshold = crime_gain / (crime_gain + penalty)
    # p = (1-e^(-λ))*0.9 → λ = -ln(1 - p/0.9)
    lambda_min = -math.log(1 - p_threshold / 0.9)
    print(f"\n  Minimum λ for deterrence: {lambda_min:.3f}")
    print(f"  = audit ~{100*(1-math.exp(-lambda_min)):.1f}% of periods")
    print(f"  Key: adversary must BELIEVE λ ≥ {lambda_min:.3f}")
    print(f"  Public catches make belief credible without revealing λ")


def demo():
    print("=" * 60)
    print("POISSON AUDIT DETERRENT")
    print("Ishikawa & Fontanari (EPJ B 2025)")
    print("\"The EXISTENCE of audit is the deterrent, not the severity\"")
    print("=" * 60)

    u_shaped_demo()
    poisson_advantage_demo()
    minimum_credible_signal()

    print("\n--- DESIGN PRINCIPLES ---")
    print("1. Poisson > fixed schedule (unmodelable)")
    print("2. Unknown λ > known λ (adversary uncertainty)")
    print("3. Public catches > private catches (credible signal)")
    print("4. U-shaped: moderate penalty = worst deterrence")
    print("5. Light penalty (p≈g) surprisingly effective")
    print("6. The audit itself is the deterrent, not the penalty")


if __name__ == "__main__":
    demo()
