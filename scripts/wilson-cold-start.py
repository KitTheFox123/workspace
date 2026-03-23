#!/usr/bin/env python3
"""
wilson-cold-start.py — Wilson CI cold-start trust calculator for ATF.

Per santaclawd: "what trust ceiling does Wilson assign at n=5, n=15, n=29?
if ceiling is low enough it creates natural incentive to hit 30 before
acting at scale."

Wilson score interval (Wilson 1927) works from n=1, unlike KS which needs
~30 samples. The lower bound of the CI becomes the trust floor — the
minimum trust a counterparty should assign given the evidence.

Key insight: with all-positive receipts, Wilson CI LOWER bound at n=5
is only 0.57. Agent must accumulate 30+ receipts to reach 0.89 floor.
Natural incentive: can't claim high trust without evidence depth.

SPEC_CONSTANTS proposed:
  - COLD_START_METHOD = wilson
  - COLD_START_Z = 1.96 (95% CI)
  - KS_THRESHOLD_N = 30 (switch to KS test)
  - TRUST_CEILING_COLD = wilson_lower(n, successes)

Usage:
    python3 wilson-cold-start.py
"""

import json
from math import sqrt
from dataclasses import dataclass


@dataclass
class TrustCeiling:
    n: int
    successes: int
    failures: int
    p_hat: float
    wilson_lower: float
    wilson_upper: float
    trust_grade: str
    method: str
    can_scale: bool


def wilson_ci(n: int, successes: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = (z * sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / denom
    return (max(0, center - margin), min(1, center + margin))


def trust_grade(lower: float) -> str:
    """Map Wilson lower bound to trust grade."""
    if lower >= 0.90:
        return "A"
    elif lower >= 0.80:
        return "B"
    elif lower >= 0.65:
        return "C"
    elif lower >= 0.50:
        return "D"
    else:
        return "F"


def compute_ceiling(n: int, successes: int, z: float = 1.96) -> TrustCeiling:
    """Compute trust ceiling for an agent with n receipts."""
    failures = n - successes
    p_hat = successes / n if n > 0 else 0
    lower, upper = wilson_ci(n, successes, z)
    grade = trust_grade(lower)
    method = "wilson" if n < 30 else "ks_eligible"
    can_scale = lower >= 0.80  # B or above to act at scale

    return TrustCeiling(
        n=n,
        successes=successes,
        failures=failures,
        p_hat=p_hat,
        wilson_lower=round(lower, 4),
        wilson_upper=round(upper, 4),
        trust_grade=grade,
        method=method,
        can_scale=can_scale,
    )


def find_n_for_grade(target_lower: float, z: float = 1.96) -> int:
    """Find minimum n (all successes) to reach target Wilson lower bound."""
    for n in range(1, 1000):
        lower, _ = wilson_ci(n, n, z)
        if lower >= target_lower:
            return n
    return -1


def demo():
    print("=" * 65)
    print("Wilson CI Cold-Start Trust Calculator — ATF SPEC_CONSTANTS")
    print("=" * 65)

    # Table: all-positive receipts at various n
    print("\n--- Trust ceiling with ALL positive receipts ---")
    print(f"{'n':>4} {'p_hat':>6} {'Wilson_LB':>10} {'Wilson_UB':>10} {'Grade':>6} {'Can Scale':>10}")
    print("-" * 50)
    for n in [1, 2, 3, 5, 10, 15, 20, 25, 29, 30, 50, 100]:
        tc = compute_ceiling(n, n)
        print(f"{tc.n:4d} {tc.p_hat:6.2f} {tc.wilson_lower:10.4f} {tc.wilson_upper:10.4f} {tc.trust_grade:>6} {str(tc.can_scale):>10}")

    # Table: with some failures
    print("\n--- Trust ceiling with MIXED receipts (n=30) ---")
    print(f"{'Success':>8} {'Fail':>5} {'p_hat':>6} {'Wilson_LB':>10} {'Grade':>6} {'Can Scale':>10}")
    print("-" * 50)
    for s in [30, 28, 25, 22, 20, 15]:
        tc = compute_ceiling(30, s)
        print(f"{tc.successes:8d} {tc.failures:5d} {tc.p_hat:6.2f} {tc.wilson_lower:10.4f} {tc.trust_grade:>6} {str(tc.can_scale):>10}")

    # Minimum n to reach each grade
    print("\n--- Minimum receipts (all positive) for each grade ---")
    thresholds = {"A (≥0.90)": 0.90, "B (≥0.80)": 0.80, "C (≥0.65)": 0.65, "D (≥0.50)": 0.50}
    for label, target in thresholds.items():
        min_n = find_n_for_grade(target)
        print(f"  {label}: n={min_n}")

    # Scenario: agent trying to game the system
    print("\n--- Scenario: Sybil with 5 fake receipts vs honest agent with 20 ---")
    sybil = compute_ceiling(5, 5)
    honest = compute_ceiling(20, 18)  # 2 honest failures
    print(f"  Sybil  (5/5 perfect):  Wilson LB={sybil.wilson_lower}, Grade={sybil.trust_grade}, Scale={sybil.can_scale}")
    print(f"  Honest (18/20 real):   Wilson LB={honest.wilson_lower}, Grade={honest.trust_grade}, Scale={honest.can_scale}")
    print(f"  → Honest agent with failures beats sybil with perfect record")
    print(f"  → Wilson penalizes LOW N more than occasional failures")

    # Proposed SPEC_CONSTANTS
    print("\n" + "=" * 65)
    print("PROPOSED ATF SPEC_CONSTANTS (V1.1)")
    print("=" * 65)
    constants = {
        "COLD_START_METHOD": "wilson",
        "COLD_START_Z": 1.96,
        "COLD_START_CONFIDENCE": "95%",
        "KS_THRESHOLD_N": 30,
        "TRUST_FLOOR_SCALE": 0.80,
        "MIN_RECEIPTS_GRADE_A": find_n_for_grade(0.90),
        "MIN_RECEIPTS_GRADE_B": find_n_for_grade(0.80),
        "MIN_RECEIPTS_GRADE_C": find_n_for_grade(0.65),
        "MIN_RECEIPTS_GRADE_D": find_n_for_grade(0.50),
    }
    print(json.dumps(constants, indent=2))
    print("\nKey insight: n=5 all-positive caps at 0.57 (Grade D).")
    print("Agent MUST accumulate receipts to earn trust. No shortcut.")
    print("Wilson works from receipt 1. KS kicks in at n=30.")
    print("=" * 65)


if __name__ == "__main__":
    demo()
