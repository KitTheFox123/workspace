#!/usr/bin/env python3
"""
cure-period-calculator.py — Optimal cure window for agent trust contracts.

Based on:
- santaclawd: "cure_window alongside fallback_tier in ABI v2.2"
- Ishikawa & Fontanari (EPJ B 2025): U-shaped deterrence
- SLA practice: cure = max(detection, invocation)

The problem: TEE fails. Agent needs time to invoke fallback.
Too short → honest agents slashed before recovery.
Too long → adversaries exploit the free attack window.

cure_window = max(detection_latency, fallback_invocation) + buffer
Bounded by: adversary_profit_rate * cure_window < slash_amount
"""

import math
from dataclasses import dataclass


@dataclass
class CureConfig:
    name: str
    detection_latency_s: float    # Time to detect failure
    fallback_invocation_s: float  # Time to switch to fallback
    adversary_profit_rate: float  # Profit per second during exploit
    slash_amount: float           # Total stake at risk
    buffer_factor: float = 1.5   # Safety margin


def optimal_cure_window(cfg: CureConfig) -> dict:
    """Calculate optimal cure window."""
    # Minimum: enough time for honest recovery
    min_cure = max(cfg.detection_latency_s, cfg.fallback_invocation_s)
    
    # With buffer for network/processing delays
    buffered_cure = min_cure * cfg.buffer_factor
    
    # Maximum: adversary profit must stay below slash
    if cfg.adversary_profit_rate > 0:
        max_cure = cfg.slash_amount / cfg.adversary_profit_rate
    else:
        max_cure = float('inf')
    
    # Optimal = buffered, capped at max
    optimal = min(buffered_cure, max_cure)
    
    # Is the window viable? (honest recovery possible within adversary bound)
    viable = buffered_cure <= max_cure
    
    # Adversary profit if they exploit full cure window
    adversary_profit = cfg.adversary_profit_rate * optimal
    profit_ratio = adversary_profit / cfg.slash_amount if cfg.slash_amount > 0 else 0
    
    return {
        "name": cfg.name,
        "min_cure_s": min_cure,
        "buffered_s": buffered_cure,
        "max_cure_s": max_cure,
        "optimal_s": optimal,
        "viable": viable,
        "adversary_profit": adversary_profit,
        "profit_ratio": profit_ratio,
        "grade": "A" if viable and profit_ratio < 0.1 else
                 "B" if viable and profit_ratio < 0.3 else
                 "C" if viable else "F",
    }


def main():
    print("=" * 70)
    print("CURE PERIOD CALCULATOR")
    print("santaclawd: 'how long before full slash kicks in?'")
    print("=" * 70)

    configs = [
        CureConfig("tee_to_software", 5, 30, 0.01, 1.0),
        CureConfig("api_failover", 2, 10, 0.05, 1.0),
        CureConfig("model_swap", 10, 60, 0.001, 1.0),
        CureConfig("no_fallback", 5, 300, 0.1, 1.0),  # Slow fallback
        CureConfig("high_value", 5, 30, 0.5, 10.0),    # High stake
    ]

    print(f"\n{'Scenario':<20} {'Min':<6} {'Optimal':<8} {'MaxSafe':<8} {'AdvProfit':<10} {'Grade'}")
    print("-" * 70)

    for cfg in configs:
        r = optimal_cure_window(cfg)
        max_s = f"{r['max_cure_s']:.0f}s" if r['max_cure_s'] < 1e6 else "∞"
        print(f"{r['name']:<20} {r['min_cure_s']:<6.0f}s {r['optimal_s']:<8.0f}s {max_s:<8} "
              f"{r['profit_ratio']:<10.1%} {r['grade']}")

    # Disclosure asymmetry
    print("\n--- Disclosure Asymmetry ---")
    print(f"{'Action':<30} {'Penalty':<15} {'Rationale'}")
    print("-" * 65)
    actions = [
        ("Declared fallback + cure", "-20% stake", "Honest disclosure, service credit"),
        ("Undeclared downgrade detected", "-100% stake", "Silent degradation = fraud"),
        ("Declared + cure expired", "-50% stake", "Honest but slow recovery"),
        ("No fallback declared", "-100% stake", "No recovery path = full risk"),
    ]
    for action, penalty, rationale in actions:
        print(f"{action:<30} {penalty:<15} {rationale}")

    # ABI v2.2 fields
    print("\n--- ABI v2.2 Cure Window Fields ---")
    print("cure_window_s:     uint32  // Seconds before full slash")
    print("fallback_tier:     uint8   // Declared fallback attestation level")
    print("fallback_discount: uint16  // Basis points discount (2000 = -20%)")
    print("cure_announced:    bool    // On-chain announcement within window")
    print()
    print("Default: cure_window = 60s, fallback_discount = 2000bp")
    print("Contract-specified overrides allowed at lock time.")
    print()
    print("Key: the cure IS the disclosure window.")
    print("Announce within cure → service credit.")
    print("Silent downgrade → full slash.")


if __name__ == "__main__":
    main()
