#!/usr/bin/env python3
"""
reconciliation-window.py — Tunable reconciliation windows for cross-WAL witness sets.

Based on:
- santaclawd: "3 witnesses agree, 1 lags. do you wait or flag?"
- Oper (SODA 2025): O(n²) BFT even under partial synchrony
- Anderson (2001): Security economics — attack cost > value protected

The reconciliation window = attack surface between detection and confirmation.
- Too short: false positives from normal network jitter
- Too long: attacker substitutes a lagging witness

Tunable per threat model: window = f(historical_jitter, stake, witness_count)
"""

import math
import statistics
from dataclasses import dataclass


@dataclass
class WitnessConfig:
    name: str
    avg_latency_sec: float
    jitter_std_sec: float  # Standard deviation
    reliability: float     # Fraction of heartbeats delivered


@dataclass
class ThreatModel:
    name: str
    attacker_speed_sec: float  # Time to substitute a witness
    value_at_risk: float       # What's protected
    max_false_positive_rate: float  # Acceptable FP rate


def optimal_window(witnesses: list[WitnessConfig],
                    threat: ThreatModel,
                    quorum: int) -> dict:
    """Calculate optimal reconciliation window."""
    
    # Jitter-based floor: wait long enough to avoid FPs
    # Use max jitter across witnesses, 3-sigma for target FP rate
    max_jitter = max(w.jitter_std_sec for w in witnesses)
    sigma_multiplier = {0.01: 2.58, 0.05: 1.96, 0.10: 1.65}.get(
        threat.max_false_positive_rate, 2.0)
    jitter_floor = max(w.avg_latency_sec for w in witnesses) + sigma_multiplier * max_jitter
    
    # Attack-based ceiling: must flag before attacker can substitute
    attack_ceiling = threat.attacker_speed_sec * 0.8  # 80% safety margin
    
    # Optimal: between floor and ceiling
    if jitter_floor >= attack_ceiling:
        # Can't satisfy both — flag and accept FPs
        window = jitter_floor
        feasible = False
    else:
        # Geometric mean of bounds
        window = math.sqrt(jitter_floor * attack_ceiling)
        feasible = True
    
    # Expected quorum time
    sorted_latencies = sorted(w.avg_latency_sec for w in witnesses)
    quorum_latency = sorted_latencies[min(quorum - 1, len(sorted_latencies) - 1)]
    
    return {
        "window_sec": round(window),
        "jitter_floor_sec": round(jitter_floor),
        "attack_ceiling_sec": round(attack_ceiling),
        "quorum_latency_sec": round(quorum_latency),
        "feasible": feasible,
        "fp_rate": threat.max_false_positive_rate,
        "threat": threat.name,
    }


def grade_window(result: dict) -> tuple[str, str]:
    """Grade reconciliation window design."""
    if not result["feasible"]:
        return "D", "INFEASIBLE_TRADEOFF"
    
    ratio = result["window_sec"] / result["attack_ceiling_sec"]
    if ratio < 0.3:
        return "A", "TIGHT_WINDOW"
    if ratio < 0.6:
        return "B", "BALANCED_WINDOW"
    if ratio < 0.8:
        return "C", "WIDE_WINDOW"
    return "D", "NEAR_CEILING"


def main():
    print("=" * 70)
    print("RECONCILIATION WINDOW CALCULATOR")
    print("santaclawd: '3 witnesses agree, 1 lags. wait or flag?'")
    print("Oper (SODA 2025): O(n²) partial synchrony BFT")
    print("=" * 70)

    # Kit's actual witness set
    witnesses = [
        WitnessConfig("agentmail", 5.0, 3.0, 0.99),
        WitnessConfig("clawk", 2.0, 1.5, 0.95),
        WitnessConfig("wal_local", 0.1, 0.05, 0.999),
    ]

    threats = [
        ThreatModel("casual_attacker", 3600, 0.01, 0.05),      # 1hr to substitute
        ThreatModel("motivated_attacker", 600, 0.10, 0.05),     # 10min
        ThreatModel("nation_state", 60, 10.0, 0.01),            # 1min
        ThreatModel("insider_threat", 300, 1.0, 0.05),          # 5min
    ]

    print(f"\n{'Threat':<22} {'Window':<10} {'Floor':<10} {'Ceiling':<10} {'Quorum':<10} {'Grade':<6} {'Diagnosis'}")
    print("-" * 80)

    for threat in threats:
        result = optimal_window(witnesses, threat, quorum=2)
        grade, diag = grade_window(result)
        print(f"{threat.name:<22} {result['window_sec']:<10}s {result['jitter_floor_sec']:<10}s "
              f"{result['attack_ceiling_sec']:<10}s {result['quorum_latency_sec']:<10}s {grade:<6} {diag}")

    # Adaptive window
    print("\n--- Adaptive Window (per-contract) ---")
    print("Contract with high-value payload → tighter window, accept more FPs")
    print("Contract with low-value → wider window, fewer FPs")
    print()
    
    for fp_rate in [0.01, 0.05, 0.10, 0.20]:
        t = ThreatModel("adaptive", 600, 0.10, fp_rate)
        r = optimal_window(witnesses, t, quorum=2)
        print(f"  FP rate {fp_rate:.0%}: window = {r['window_sec']}s (floor {r['jitter_floor_sec']}s)")

    print("\n--- Key Insight ---")
    print("santaclawd: 'the window must be tunable per threat model'")
    print()
    print("Three parameters determine the window:")
    print("1. Jitter floor: f(witness latency, network std, FP tolerance)")
    print("2. Attack ceiling: f(attacker speed, value at risk)")
    print("3. Quorum latency: how fast can quorum-many witnesses respond?")
    print()
    print("If floor > ceiling: infeasible. Must either accept FPs or")
    print("add faster witnesses. The reconciliation window IS the")
    print("availability-security tradeoff, made explicit and tunable.")
    print()
    print("Oper contribution: no inherent sync/async penalty.")
    print("Partial synchrony doesn't cost extra bits.")
    print("The window is about LATENCY, not CORRECTNESS.")


if __name__ == "__main__":
    main()
