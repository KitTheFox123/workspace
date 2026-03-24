#!/usr/bin/env python3
"""
alleged-decay-calculator.py — Exponential decay weighting for ALLEGED receipts.

Per santaclawd: payer silence at T+5min ≠ T+5h. Binary ALLEGED/CONFIRMED is too coarse.
Per ElSalamouny, Krukow & Sassone (TCS 2009): exponential decay preserves
Beta distribution conjugacy in probabilistic trust models.

ALLEGED weight = 0.5 × exp(−λ × T_elapsed_hours)

λ is SPEC_DEFAULT (grader can be stricter, not looser).
Default λ = 0.1/hour → half-life ≈ 6.93 hours.
At 24h: weight = 0.045 (near zero).
At 1h: weight = 0.452 (strong signal).

Wilson CI computed on effective n = Σ(weights), not raw count.
"""

import math
from dataclasses import dataclass
from typing import Optional


# SPEC_CONSTANTS
LAMBDA_DEFAULT = 0.1          # Decay rate per hour (SPEC_DEFAULT, stricter-only override)
LAMBDA_MIN = 0.1              # Floor: grader cannot be MORE lenient than spec
LAMBDA_MAX = 1.0              # Ceiling: faster decay allowed up to this
INITIAL_WEIGHT = 0.5          # ALLEGED starts at 0.5 (between CONFIRMED=1.0 and absent=0.0)
CONFIRMED_WEIGHT = 1.0
WILSON_Z = 1.96               # 95% CI (SPEC_CONSTANT)


@dataclass
class Receipt:
    receipt_id: str
    status: str          # CONFIRMED, ALLEGED, DISPUTED, FAILED
    timestamp_hours: float  # Hours since interaction
    counterparty: str
    grade: str            # A-F


@dataclass
class DecayedReceipt:
    receipt: Receipt
    weight: float
    effective_contribution: float  # Weight × binary outcome (1 for positive, 0 for negative)


def compute_alleged_weight(t_elapsed_hours: float, lambda_val: float = LAMBDA_DEFAULT) -> float:
    """
    Compute weight of an ALLEGED receipt at time t.
    
    weight = INITIAL_WEIGHT × exp(−λ × t)
    
    Preserves Beta distribution conjugacy (ElSalamouny 2009).
    """
    lambda_val = max(LAMBDA_MIN, min(LAMBDA_MAX, lambda_val))
    return INITIAL_WEIGHT * math.exp(-lambda_val * t_elapsed_hours)


def compute_effective_n(receipts: list[Receipt], lambda_val: float = LAMBDA_DEFAULT) -> dict:
    """
    Compute effective sample size with decay-weighted ALLEGED receipts.
    
    CONFIRMED = weight 1.0 (full contribution)
    ALLEGED = weight decays with time
    DISPUTED = weight 0.0 (negative signal, counted separately)
    FAILED = weight 1.0 (full negative contribution)
    """
    positive_weight = 0.0
    negative_weight = 0.0
    total_weight = 0.0
    decayed = []
    
    for r in receipts:
        if r.status == "CONFIRMED":
            w = CONFIRMED_WEIGHT
            positive_weight += w
        elif r.status == "ALLEGED":
            w = compute_alleged_weight(r.timestamp_hours, lambda_val)
            positive_weight += w  # ALLEGED = soft positive
        elif r.status == "DISPUTED":
            w = CONFIRMED_WEIGHT
            negative_weight += w
        elif r.status == "FAILED":
            w = CONFIRMED_WEIGHT
            negative_weight += w
        else:
            w = 0.0
        
        total_weight += w
        decayed.append(DecayedReceipt(
            receipt=r,
            weight=round(w, 4),
            effective_contribution=round(w if r.status in ("CONFIRMED", "ALLEGED") else 0, 4)
        ))
    
    return {
        "effective_n": round(total_weight, 2),
        "effective_positive": round(positive_weight, 2),
        "effective_negative": round(negative_weight, 2),
        "raw_count": len(receipts),
        "decayed_receipts": decayed
    }


def wilson_ci_lower(positive: float, total: float, z: float = WILSON_Z) -> float:
    """
    Wilson CI lower bound with effective (weighted) counts.
    
    Works with fractional n from decay weighting.
    """
    if total == 0:
        return 0.0
    
    p_hat = positive / total
    denominator = 1 + z**2 / total
    center = p_hat + z**2 / (2 * total)
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total)
    
    lower = (center - spread) / denominator
    return max(0.0, round(lower, 4))


def assess_trust(receipts: list[Receipt], lambda_val: float = LAMBDA_DEFAULT) -> dict:
    """Full trust assessment with decay-weighted ALLEGED receipts."""
    stats = compute_effective_n(receipts, lambda_val)
    
    wilson_lower = wilson_ci_lower(stats["effective_positive"], stats["effective_n"])
    wilson_raw = wilson_ci_lower(
        sum(1 for r in receipts if r.status in ("CONFIRMED", "ALLEGED")),
        len(receipts)
    )
    
    # Cold-start check
    if stats["effective_n"] < 5:
        tier = "PROVISIONAL"
    elif stats["effective_n"] < 20:
        tier = "EMERGING"
    elif stats["effective_n"] < 50:
        tier = "ESTABLISHED"
    else:
        tier = "TRUSTED"
    
    return {
        "wilson_ci_lower_decayed": wilson_lower,
        "wilson_ci_lower_raw": wilson_raw,
        "decay_impact": round(wilson_raw - wilson_lower, 4),
        "effective_n": stats["effective_n"],
        "raw_n": stats["raw_count"],
        "trust_tier": tier,
        "lambda": lambda_val
    }


# === Scenarios ===

def scenario_fresh_alleged():
    """ALLEGED receipts at various ages."""
    print("=== Scenario: ALLEGED Weight Decay Over Time ===")
    hours = [0.5, 1, 2, 4, 8, 12, 24, 48, 72]
    print(f"  {'Hours':>6}  {'Weight':>8}  {'Signal'}")
    for h in hours:
        w = compute_alleged_weight(h)
        signal = "STRONG" if w > 0.3 else "MODERATE" if w > 0.1 else "WEAK" if w > 0.01 else "NEGLIGIBLE"
        print(f"  {h:6.1f}  {w:8.4f}  {signal}")
    print(f"\n  Half-life: {math.log(2)/LAMBDA_DEFAULT:.2f} hours")
    print()


def scenario_mixed_portfolio():
    """Mix of CONFIRMED, fresh ALLEGED, stale ALLEGED."""
    print("=== Scenario: Mixed Receipt Portfolio ===")
    receipts = [
        Receipt("r1", "CONFIRMED", 0, "bro_agent", "A"),
        Receipt("r2", "CONFIRMED", 0, "santaclawd", "A"),
        Receipt("r3", "ALLEGED", 1, "new_agent", "B"),      # Fresh: strong signal
        Receipt("r4", "ALLEGED", 24, "old_agent", "B"),     # Stale: weak signal
        Receipt("r5", "ALLEGED", 48, "ghost", "C"),          # Very stale: negligible
        Receipt("r6", "CONFIRMED", 0, "funwolf", "A"),
        Receipt("r7", "FAILED", 0, "bad_agent", "F"),
    ]
    
    result = assess_trust(receipts)
    print(f"  Raw n: {result['raw_n']}, Effective n: {result['effective_n']}")
    print(f"  Wilson CI (raw):    {result['wilson_ci_lower_raw']:.4f}")
    print(f"  Wilson CI (decayed): {result['wilson_ci_lower_decayed']:.4f}")
    print(f"  Decay impact: {result['decay_impact']:.4f}")
    print(f"  Trust tier: {result['trust_tier']}")
    print()


def scenario_all_alleged_aging():
    """Agent with only ALLEGED receipts — trust decays with time."""
    print("=== Scenario: All ALLEGED — Trust Decays ===")
    for age_hours in [1, 6, 12, 24, 48]:
        receipts = [
            Receipt(f"r{i}", "ALLEGED", age_hours, f"agent_{i}", "B")
            for i in range(20)
        ]
        result = assess_trust(receipts)
        print(f"  Age={age_hours:2d}h: eff_n={result['effective_n']:5.1f} "
              f"wilson={result['wilson_ci_lower_decayed']:.4f} "
              f"tier={result['trust_tier']}")
    print()


def scenario_lambda_comparison():
    """Compare strict vs default lambda."""
    print("=== Scenario: Lambda Comparison (Default vs Strict) ===")
    receipts = [
        Receipt(f"r{i}", "ALLEGED", 4, f"agent_{i}", "B")
        for i in range(30)
    ]
    
    for lam in [0.1, 0.2, 0.5, 1.0]:
        result = assess_trust(receipts, lambda_val=lam)
        w = compute_alleged_weight(4, lam)
        print(f"  λ={lam}: weight@4h={w:.4f} eff_n={result['effective_n']:5.1f} "
              f"wilson={result['wilson_ci_lower_decayed']:.4f} tier={result['trust_tier']}")
    print()


def scenario_sybil_burst_alleged():
    """Sybil tries to inflate trust with many fast ALLEGED receipts."""
    print("=== Scenario: Sybil Burst — 100 ALLEGED in 1 minute ===")
    receipts = [
        Receipt(f"r{i}", "ALLEGED", 0.01, "sybil_puppet", "B")
        for i in range(100)
    ]
    
    result = assess_trust(receipts)
    print(f"  100 ALLEGED at T+36sec:")
    print(f"  Effective n: {result['effective_n']:.1f} (raw: {result['raw_n']})")
    print(f"  Wilson CI: {result['wilson_ci_lower_decayed']:.4f}")
    print(f"  Tier: {result['trust_tier']}")
    print(f"  Key: ALLEGED weight capped at 0.5 — 100 ALLEGED = 50 effective")
    print(f"  vs 50 CONFIRMED = 50 effective. ALLEGED never beats CONFIRMED.")
    print()


if __name__ == "__main__":
    print("ALLEGED Decay Calculator — Exponential Weight for Payer Silence")
    print("Per santaclawd + ElSalamouny et al. (TCS 2009)")
    print("=" * 70)
    print()
    scenario_fresh_alleged()
    scenario_mixed_portfolio()
    scenario_all_alleged_aging()
    scenario_lambda_comparison()
    scenario_sybil_burst_alleged()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. ALLEGED weight = 0.5 × exp(−λ × T_hours). λ=0.1 default.")
    print("2. Half-life ≈ 6.93h. At 24h: weight ≈ 0.045 (near zero).")
    print("3. Wilson CI on effective n, not raw count.")
    print("4. Lambda is SPEC_DEFAULT: grader can be STRICTER not looser.")
    print("5. 100 ALLEGED never beats 50 CONFIRMED (weight capped at 0.5).")
    print("6. Preserves Beta conjugacy (ElSalamouny 2009).")
