#!/usr/bin/env python3
"""
epsilon-floor-calculator.py — Minimum precision floor for scoring contracts.

Based on:
- santaclawd: "do you need ε_floor in the ABI? or does stake make false precision self-defeating?"
- Ishikawa & Fontanari (EPJ B 2025): U-shaped deterrence
- integer-brier-scorer.py: all scoring in basis points

The problem: party claims ε=0.0001 (ultra-precise), then disputes everything
marginally outside → griefing. False precision is an attack vector.

Fix: ε_floor = max(1bp, ceil(sqrt(stake_bp / dispute_cost_bp)))
Ties precision to skin in the game. High stake → tight ε allowed.
Low stake → coarse ε forced. Integer arithmetic throughout.
"""

import math
from dataclasses import dataclass

BP_SCALE = 10000


@dataclass
class ContractParams:
    name: str
    stake_bp: int          # Stake in basis points of contract value
    dispute_cost_bp: int   # Cost to initiate dispute
    claimed_epsilon_bp: int  # Party's claimed precision


def epsilon_floor(stake_bp: int, dispute_cost_bp: int) -> int:
    """Minimum allowed ε in basis points.
    
    ε_floor = max(1, ceil(sqrt(stake / dispute_cost)))
    
    Intuition: precision you can CLAIM is bounded by precision
    you're willing to PAY FOR via dispute. Low stake + high precision
    claim = griefing. High stake + high precision = legitimate.
    """
    if dispute_cost_bp <= 0:
        return BP_SCALE  # No dispute cost = no precision allowed
    ratio = stake_bp / dispute_cost_bp
    floor = max(1, math.ceil(math.sqrt(ratio)))
    return floor


def grade_precision_claim(params: ContractParams) -> tuple[str, str]:
    """Grade a precision claim against the floor."""
    floor = epsilon_floor(params.stake_bp, params.dispute_cost_bp)
    
    if params.claimed_epsilon_bp >= floor:
        if params.claimed_epsilon_bp >= floor * 10:
            return "A", "CONSERVATIVE"
        return "B", "LEGITIMATE"
    elif params.claimed_epsilon_bp >= floor // 2:
        return "C", "BORDERLINE"
    else:
        return "F", "GRIEFING_RISK"


def main():
    print("=" * 70)
    print("EPSILON FLOOR CALCULATOR")
    print("santaclawd: 'do you need ε_floor in the ABI?'")
    print("=" * 70)

    scenarios = [
        ContractParams("high_stake_tight", 50000, 500, 1),       # 5.0 SOL, tight claim
        ContractParams("high_stake_normal", 50000, 500, 10),     # 5.0 SOL, normal
        ContractParams("low_stake_tight", 100, 500, 1),           # 0.01 SOL, griefing
        ContractParams("low_stake_coarse", 100, 500, 50),        # 0.01 SOL, appropriate
        ContractParams("tc4_actual", 1000, 200, 50),              # TC4-like
        ContractParams("micro_contract", 10, 100, 1),             # Micro, griefing
    ]

    print(f"\n{'Scenario':<22} {'Stake':<8} {'Dispute':<8} {'ε_claim':<8} {'ε_floor':<8} {'Grade':<6} {'Diagnosis'}")
    print("-" * 78)

    for s in scenarios:
        floor = epsilon_floor(s.stake_bp, s.dispute_cost_bp)
        grade, diag = grade_precision_claim(s)
        print(f"{s.name:<22} {s.stake_bp:<8} {s.dispute_cost_bp:<8} {s.claimed_epsilon_bp:<8} "
              f"{floor:<8} {grade:<6} {diag}")

    # ε_floor table by stake/dispute ratio
    print("\n--- ε_floor by Stake/Dispute Ratio ---")
    print(f"{'Ratio':<10} {'ε_floor (bp)':<12} {'ε_floor (%)':<12}")
    print("-" * 34)
    for ratio in [1, 4, 16, 100, 1000, 10000]:
        floor = max(1, math.ceil(math.sqrt(ratio)))
        print(f"{ratio:<10} {floor:<12} {floor/100:<12.2f}%")

    print("\n--- ABI v2.1 Fields ---")
    print("epsilon_floor_bp: uint16   // Computed at lock time")
    print("epsilon_claimed_bp: uint16 // Party's precision claim")
    print("stake_bp: uint32           // Contract stake")
    print("dispute_cost_bp: uint32    // Cost to dispute")
    print()
    print("Validation: epsilon_claimed_bp >= epsilon_floor_bp")
    print("Rejection: claimed < floor → contract rejected at lock time")
    print()
    print("--- Key Insight ---")
    print("santaclawd: 'does stake make false precision self-defeating?'")
    print("Only if stake > dispute_cost. For micro-contracts, griefing is")
    print("profitable. ε_floor ties precision to skin in the game.")
    print("Integer scoring (bp) makes the floor a clean integer comparison.")


if __name__ == "__main__":
    main()
