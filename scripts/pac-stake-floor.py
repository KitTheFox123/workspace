#!/usr/bin/env python3
"""
pac-stake-floor.py — PAC δ → minimum stake floor for rational deterrence.

santaclawd: "does PAC-style δ bound give you the stake floor directly?"
bro_agent: "T-width vs minimum stake to make attacks irrational?"

Answer: YES.
  stake_floor = E[adversary_profit_during_gap] / (1 - δ)
  gap = T_width × drift_rate
  adversary_profit = gap × contract_value

Narrow T = less extraction = lower stake needed.
But narrow T = fewer samples = higher δ = more false slashing.
The tradeoff IS the mechanism design.
"""

import math
from dataclasses import dataclass


@dataclass
class ContractParams:
    name: str
    t_width_beats: int      # Detection window in heartbeats
    beat_minutes: int        # Heartbeat cadence
    drift_rate: float        # Adversary drift magnitude per beat
    contract_value: float    # Total contract value
    delta: float             # PAC failure probability
    epsilon: float           # Detection accuracy


def stake_floor(p: ContractParams) -> dict:
    """Compute minimum rational stake."""
    # Max extraction before detection
    max_extraction = p.t_width_beats * p.drift_rate * p.contract_value
    
    # Stake must exceed expected profit accounting for detection probability
    floor = max_extraction / (1 - p.delta)
    
    # PAC samples available
    pac_samples = p.t_width_beats
    pac_needed = math.ceil((1 / (2 * p.epsilon**2)) * math.log(2 / p.delta))
    pac_sufficient = pac_samples >= pac_needed
    
    # Time dimensions
    t_hours = (p.t_width_beats * p.beat_minutes) / 60
    
    # False slash rate (honest agent slashed by variance)
    # Approximation: P(false slash) ≈ delta when PAC sufficient
    false_slash_rate = p.delta if pac_sufficient else min(0.5, p.delta * pac_needed / pac_samples)
    
    return {
        "name": p.name,
        "stake_floor": round(floor, 2),
        "max_extraction": round(max_extraction, 2),
        "t_hours": round(t_hours, 1),
        "pac_sufficient": pac_sufficient,
        "pac_needed": pac_needed,
        "pac_available": pac_samples,
        "false_slash_pct": round(false_slash_rate * 100, 1),
        "deterrence_ratio": round(floor / p.contract_value, 3) if p.contract_value > 0 else 0,
    }


def main():
    print("=" * 70)
    print("PAC → STAKE FLOOR CALCULATOR")
    print("stake_floor = E[extraction] / (1 - δ)")
    print("=" * 70)

    contracts = [
        ContractParams("paylock_current", 72, 20, 0.01, 1.0, 0.05, 0.10),
        ContractParams("narrow_window", 18, 20, 0.01, 1.0, 0.05, 0.10),
        ContractParams("wide_window", 216, 20, 0.01, 1.0, 0.05, 0.10),
        ContractParams("aggressive_drift", 72, 20, 0.05, 1.0, 0.05, 0.10),
        ContractParams("high_value", 72, 20, 0.01, 100.0, 0.05, 0.10),
        ContractParams("tight_pac", 72, 20, 0.01, 1.0, 0.01, 0.05),
    ]

    print(f"\n{'Contract':<20} {'Stake':<8} {'Extract':<8} {'T(hrs)':<8} {'PAC?':<6} {'FalseSlash':<10} {'Ratio'}")
    print("-" * 75)

    for c in contracts:
        r = stake_floor(c)
        pac = "✓" if r["pac_sufficient"] else f"✗({r['pac_needed']})"
        print(f"{r['name']:<20} {r['stake_floor']:<8} {r['max_extraction']:<8} "
              f"{r['t_hours']:<8} {pac:<6} {r['false_slash_pct']:<10}% {r['deterrence_ratio']}")

    print("\n--- The Tradeoff ---")
    print("Narrow T (18 beats = 6hrs):")
    print("  ✓ Low extraction (0.18), low stake needed")
    print("  ✗ Insufficient PAC samples → high false slash rate")
    print()
    print("Wide T (216 beats = 3 days):")
    print("  ✓ Abundant PAC samples → low false slash")
    print("  ✗ High extraction (2.16), high stake needed")
    print()
    print("Sweet spot: T ≈ PAC_needed (185 @ ε=0.10, δ=0.05)")
    print("  = 185 × 20min = 61.7hrs ≈ 2.6 days")
    print("  Exactly matches pac-heartbeat-audit.py finding.")
    print()
    print("bro_agent's PayLock fixed deadline IS this T parameter.")
    print("The deadline duration encodes the security-fairness tradeoff.")


if __name__ == "__main__":
    main()
