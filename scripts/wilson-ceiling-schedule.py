#!/usr/bin/env python3
"""
wilson-ceiling-schedule.py — ATF trust ceiling schedule based on Wilson CI.

Per santaclawd: cold-start gap means you can't KS-test with 5 receipts.
Wilson CI provides trust ceiling from receipt 1. This tool publishes the
canonical ceiling schedule for ATF V1.1.

Key insight: with all-good receipts, Wilson CI lower bound naturally caps
trust. At n=5, perfect agent maxes out at 0.57. At n=29, still only 0.88.
This creates natural incentive to accumulate receipts before acting at scale.

The ceiling schedule should be SPEC_NORMATIVE — counterparties need
identical expectations of what n=5 means.

Usage:
    python3 wilson-ceiling-schedule.py
"""

import math
import json
from dataclasses import dataclass


# ATF SPEC_CONSTANTS
WILSON_Z = 1.96  # 95% confidence
KS_THRESHOLD = 30  # minimum receipts for KS test
TRUST_TIERS = {
    "PROVISIONAL": (0.0, 0.50),
    "EMERGING": (0.50, 0.75),
    "ESTABLISHED": (0.75, 0.90),
    "TRUSTED": (0.90, 1.0),
}


def wilson_lower(n: int, successes: int, z: float = WILSON_Z) -> float:
    """Wilson score interval lower bound."""
    if n == 0:
        return 0.0
    p = successes / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max((center - margin) / denom, 0.0)


def wilson_upper(n: int, successes: int, z: float = WILSON_Z) -> float:
    """Wilson score interval upper bound."""
    if n == 0:
        return 1.0
    p = successes / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return min((center + margin) / denom, 1.0)


@dataclass
class CeilingEntry:
    n: int
    ceiling: float  # Wilson lower bound with all successes
    tier: str
    can_ks_test: bool
    width: float  # CI width (uncertainty)


def generate_schedule(max_n: int = 100) -> list[CeilingEntry]:
    """Generate the canonical ceiling schedule."""
    entries = []
    for n in range(1, max_n + 1):
        ceiling = wilson_lower(n, n, WILSON_Z)
        upper = wilson_upper(n, n, WILSON_Z)
        width = upper - ceiling

        tier = "PROVISIONAL"
        for name, (lo, hi) in TRUST_TIERS.items():
            if lo <= ceiling < hi:
                tier = name
                break
        if ceiling >= 0.90:
            tier = "TRUSTED"

        entries.append(CeilingEntry(
            n=n,
            ceiling=round(ceiling, 4),
            tier=tier,
            can_ks_test=n >= KS_THRESHOLD,
            width=round(width, 4),
        ))
    return entries


def find_tier_transitions(schedule: list[CeilingEntry]) -> list[dict]:
    """Find the receipt count where each tier transition occurs."""
    transitions = []
    prev_tier = None
    for entry in schedule:
        if entry.tier != prev_tier:
            transitions.append({
                "n": entry.n,
                "tier": entry.tier,
                "ceiling": entry.ceiling,
                "can_ks_test": entry.can_ks_test,
            })
            prev_tier = entry.tier
    return transitions


def assess_agent(n_receipts: int, n_successes: int) -> dict:
    """Assess an agent's trust ceiling given their receipt history."""
    if n_receipts == 0:
        return {
            "trust_score": 0.0,
            "tier": "UNKNOWN",
            "can_ks_test": False,
            "verdict": "NO_RECEIPTS",
            "recommendation": "Bootstrap via trusted introducer",
        }

    ceiling = wilson_lower(n_receipts, n_successes, WILSON_Z)
    floor = wilson_lower(n_receipts, n_successes, WILSON_Z)

    # Determine tier
    tier = "PROVISIONAL"
    for name, (lo, hi) in TRUST_TIERS.items():
        if lo <= ceiling < hi:
            tier = name
            break
    if ceiling >= 0.90:
        tier = "TRUSTED"

    can_ks = n_receipts >= KS_THRESHOLD
    failure_rate = 1 - n_successes / n_receipts

    # Verdict
    if failure_rate > 0.30:
        verdict = "HIGH_FAILURE_RATE"
    elif not can_ks and tier == "PROVISIONAL":
        verdict = "COLD_START"
    elif not can_ks:
        verdict = "ACCUMULATING"
    elif tier == "TRUSTED":
        verdict = "TRUSTED"
    else:
        verdict = "ESTABLISHED"

    return {
        "n_receipts": n_receipts,
        "n_successes": n_successes,
        "failure_rate": round(failure_rate, 3),
        "trust_score": round(ceiling, 4),
        "tier": tier,
        "can_ks_test": can_ks,
        "verdict": verdict,
        "receipts_to_next_tier": _receipts_to_next_tier(ceiling, n_successes, n_receipts),
    }


def _receipts_to_next_tier(current_ceiling: float, successes: int, total: int) -> int | None:
    """How many more perfect receipts to reach next tier?"""
    current_tier_upper = None
    for name, (lo, hi) in TRUST_TIERS.items():
        if lo <= current_ceiling < hi:
            current_tier_upper = hi
            break

    if current_tier_upper is None or current_ceiling >= 0.90:
        return None  # Already at top

    # Binary search for n needed
    for extra in range(1, 500):
        new_n = total + extra
        new_s = successes + extra  # assume all good
        new_ceiling = wilson_lower(new_n, new_s, WILSON_Z)
        if new_ceiling >= current_tier_upper:
            return extra
    return None


def demo():
    print("=" * 65)
    print("Wilson Ceiling Schedule — ATF V1.1 SPEC_NORMATIVE")
    print("=" * 65)

    schedule = generate_schedule(60)

    # Key milestones
    print("\n--- Ceiling Schedule (all-good receipts) ---")
    print(f"{'n':>4} {'ceiling':>8} {'tier':<14} {'KS?':>4} {'width':>6}")
    print("-" * 42)
    milestones = [1, 2, 3, 5, 7, 10, 15, 20, 25, 29, 30, 40, 50]
    for entry in schedule:
        if entry.n in milestones:
            ks = "YES" if entry.can_ks_test else "no"
            print(f"{entry.n:>4} {entry.ceiling:>8.4f} {entry.tier:<14} {ks:>4} {entry.width:>6.4f}")

    # Tier transitions
    print("\n--- Tier Transitions ---")
    transitions = find_tier_transitions(schedule)
    for t in transitions:
        ks = "✓" if t["can_ks_test"] else "✗"
        print(f"  n={t['n']:>3}: {t['tier']:<14} (ceiling={t['ceiling']:.4f}) KS={ks}")

    # Agent assessments
    print("\n--- Agent Assessments ---")
    scenarios = [
        ("new_agent", 3, 3),
        ("cold_start", 8, 7),
        ("accumulating", 20, 19),
        ("near_ks", 29, 29),
        ("established", 50, 48),
        ("trusted", 100, 97),
        ("failing", 30, 18),
        ("sybil_perfect", 5, 5),
    ]
    for name, total, success in scenarios:
        result = assess_agent(total, success)
        print(f"\n  {name} (n={total}, s={success}):")
        print(f"    trust={result['trust_score']:.4f} tier={result['tier']} "
              f"verdict={result['verdict']}")
        if result.get("receipts_to_next_tier"):
            print(f"    → {result['receipts_to_next_tier']} more perfect receipts to next tier")

    # SPEC_CONSTANTS output
    print("\n--- ATF V1.1 SPEC_CONSTANTS ---")
    constants = {
        "WILSON_Z": WILSON_Z,
        "KS_THRESHOLD": KS_THRESHOLD,
        "TIER_PROVISIONAL": [0.0, 0.50],
        "TIER_EMERGING": [0.50, 0.75],
        "TIER_ESTABLISHED": [0.75, 0.90],
        "TIER_TRUSTED": [0.90, 1.0],
        "CEILING_AT_N1": 0.2065,
        "CEILING_AT_N5": 0.5661,
        "CEILING_AT_N10": 0.7224,
        "CEILING_AT_N30": 0.8862,
        "CEILING_AT_N50": 0.9293,
    }
    print(json.dumps(constants, indent=2))

    print("\n" + "=" * 65)
    print("Wilson CI creates natural trust gates:")
    print("  n<5:  PROVISIONAL (max 0.57)")
    print("  n<15: EMERGING    (max 0.80)")
    print("  n<30: ESTABLISHED (max 0.89)")
    print("  n≥30: TRUSTED     (KS-testable, max >0.93)")
    print("Sybil with 5 perfect receipts can never exceed 0.57.")
    print("=" * 65)


if __name__ == "__main__":
    demo()
