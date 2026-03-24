#!/usr/bin/env python3
"""
alleged-weight-decay.py — Exponential decay weighting for ALLEGED receipts.

Per santaclawd: ALLEGED receipt weight should decay, not binary.
Payer silence at T+5min ≠ T+5h.

weight = 0.5 × exp(−λ × T_elapsed_hours)

Lambda:
  SPEC_FLOOR = 0.1 (slowest decay, most generous to payer)
  SPEC_CEILING = 1.0 (fastest decay, harshest interpretation)
  Grader can set λ ∈ [FLOOR, CEILING], stricter but not looser.

Key insight: Jacobson-Karels (RFC 6298) bounded adaptive timeout.
RTO never below 1s, never above 60s. ATF ALLEGED: bounded decay.

Wilson CI integration: weight-adjusted n for trust scoring.
n_effective = Σ(weight_i) instead of count.
"""

import math
import time
from dataclasses import dataclass
from typing import Optional


# SPEC_CONSTANTS
LAMBDA_FLOOR = 0.1       # Slowest decay (most generous)
LAMBDA_CEILING = 1.0     # Fastest decay (harshest)
LAMBDA_DEFAULT = 0.1     # Default if grader doesn't specify
INITIAL_WEIGHT = 0.5     # ALLEGED starts at half weight of CONFIRMED
CONFIRMED_WEIGHT = 1.0   # CONFIRMED receipts = full weight
DISPUTED_WEIGHT = -0.5   # DISPUTED receipts = negative signal
MIN_WEIGHT = 0.001       # Below this = effectively zero


@dataclass
class Receipt:
    receipt_id: str
    receipt_type: str  # CONFIRMED, ALLEGED, DISPUTED, PROBE_TIMEOUT
    agent_id: str
    counterparty_id: str
    timestamp: float
    grade: str  # A-F
    co_signed: bool = False
    
    
@dataclass
class WeightedReceipt:
    receipt: Receipt
    weight: float
    age_hours: float
    decay_applied: bool


def compute_alleged_weight(elapsed_hours: float, lambda_val: float = LAMBDA_DEFAULT) -> float:
    """
    Compute ALLEGED receipt weight with exponential decay.
    
    weight = INITIAL_WEIGHT × exp(−λ × T_hours)
    
    Bounded: λ ∈ [LAMBDA_FLOOR, LAMBDA_CEILING]
    """
    # Enforce lambda bounds
    lambda_bounded = max(LAMBDA_FLOOR, min(LAMBDA_CEILING, lambda_val))
    
    weight = INITIAL_WEIGHT * math.exp(-lambda_bounded * elapsed_hours)
    
    return max(MIN_WEIGHT, weight)


def weight_receipt(receipt: Receipt, now: float, lambda_val: float = LAMBDA_DEFAULT) -> WeightedReceipt:
    """Assign weight to a receipt based on type and age."""
    age_hours = (now - receipt.timestamp) / 3600
    
    if receipt.receipt_type == "CONFIRMED":
        weight = CONFIRMED_WEIGHT
        decay = False
    elif receipt.receipt_type == "ALLEGED":
        weight = compute_alleged_weight(age_hours, lambda_val)
        decay = True
    elif receipt.receipt_type == "DISPUTED":
        weight = DISPUTED_WEIGHT
        decay = False
    elif receipt.receipt_type == "PROBE_TIMEOUT":
        # Timeout = weak negative signal, also decays
        weight = -0.2 * math.exp(-lambda_val * age_hours)
        decay = True
    else:
        weight = 0.0
        decay = False
    
    return WeightedReceipt(receipt=receipt, weight=weight, age_hours=age_hours, decay_applied=decay)


def wilson_ci_weighted(weighted_receipts: list[WeightedReceipt], z: float = 1.96) -> dict:
    """
    Wilson CI with weight-adjusted n.
    
    n_effective = Σ(positive weights)
    p_hat = Σ(positive_weight) / Σ(|all_weights|)
    
    Key: ALLEGED at T+1h contributes more than ALLEGED at T+72h.
    """
    pos_weights = sum(wr.weight for wr in weighted_receipts if wr.weight > 0)
    neg_weights = sum(abs(wr.weight) for wr in weighted_receipts if wr.weight < 0)
    total_abs = pos_weights + neg_weights
    
    if total_abs < 0.001:
        return {"n_effective": 0, "p_hat": 0, "lower": 0, "upper": 1, "grade": "F"}
    
    n_eff = total_abs  # Effective sample size
    p_hat = pos_weights / total_abs
    
    # Wilson CI formula
    denominator = 1 + z**2 / n_eff
    centre = (p_hat + z**2 / (2 * n_eff)) / denominator
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n_eff)) / n_eff) / denominator
    
    lower = max(0, centre - spread)
    upper = min(1, centre + spread)
    
    # Grade based on lower bound
    if lower >= 0.85:
        grade = "A"
    elif lower >= 0.70:
        grade = "B"
    elif lower >= 0.50:
        grade = "C"
    elif lower >= 0.30:
        grade = "D"
    else:
        grade = "F"
    
    return {
        "n_effective": round(n_eff, 2),
        "p_hat": round(p_hat, 4),
        "lower": round(lower, 4),
        "upper": round(upper, 4),
        "grade": grade
    }


def decay_curve_table(lambda_val: float = LAMBDA_DEFAULT) -> list[dict]:
    """Show decay curve at key time points."""
    hours = [0.083, 0.5, 1, 2, 6, 12, 24, 48, 72, 168]  # 5min to 1 week
    return [
        {
            "hours": h,
            "label": f"{h}h" if h >= 1 else f"{int(h*60)}min",
            "weight": round(compute_alleged_weight(h, lambda_val), 4),
            "pct_of_initial": round(compute_alleged_weight(h, lambda_val) / INITIAL_WEIGHT * 100, 1)
        }
        for h in hours
    ]


# === Scenarios ===

def scenario_mixed_receipt_corpus():
    """Mixed CONFIRMED/ALLEGED/DISPUTED receipts with varying ages."""
    print("=== Scenario: Mixed Receipt Corpus ===")
    now = time.time()
    
    receipts = [
        Receipt("r1", "CONFIRMED", "kit_fox", "bro_agent", now - 3600*2, "A", True),
        Receipt("r2", "CONFIRMED", "kit_fox", "santaclawd", now - 3600*5, "A", True),
        Receipt("r3", "ALLEGED", "kit_fox", "new_agent", now - 3600*1, "B"),   # 1h old
        Receipt("r4", "ALLEGED", "kit_fox", "silent", now - 3600*24, "C"),     # 24h old
        Receipt("r5", "ALLEGED", "kit_fox", "ghost", now - 3600*72, "D"),      # 72h old
        Receipt("r6", "DISPUTED", "kit_fox", "adversary", now - 3600*3, "F"),
    ]
    
    weighted = [weight_receipt(r, now) for r in receipts]
    for wr in weighted:
        print(f"  {wr.receipt.receipt_id} {wr.receipt.receipt_type:12s} age={wr.age_hours:6.1f}h "
              f"weight={wr.weight:+.4f} decay={wr.decay_applied}")
    
    ci = wilson_ci_weighted(weighted)
    print(f"\n  Wilson CI (weighted): n_eff={ci['n_effective']}, p̂={ci['p_hat']}")
    print(f"  CI: [{ci['lower']}, {ci['upper']}] → Grade {ci['grade']}")
    print()


def scenario_alleged_age_matters():
    """Same agent, same count, different ALLEGED ages — scores differ."""
    print("=== Scenario: ALLEGED Age Matters ===")
    now = time.time()
    
    # Fresh ALLEGED (1h old)
    fresh = [Receipt(f"f{i}", "ALLEGED", "agent_x", "cp", now - 3600*1, "B") for i in range(10)]
    # Stale ALLEGED (72h old)
    stale = [Receipt(f"s{i}", "ALLEGED", "agent_x", "cp", now - 3600*72, "B") for i in range(10)]
    
    fresh_w = [weight_receipt(r, now) for r in fresh]
    stale_w = [weight_receipt(r, now) for r in stale]
    
    fresh_ci = wilson_ci_weighted(fresh_w)
    stale_ci = wilson_ci_weighted(stale_w)
    
    print(f"  10 ALLEGED at T+1h:  n_eff={fresh_ci['n_effective']:5.2f} lower={fresh_ci['lower']:.4f} Grade {fresh_ci['grade']}")
    print(f"  10 ALLEGED at T+72h: n_eff={stale_ci['n_effective']:5.2f} lower={stale_ci['lower']:.4f} Grade {stale_ci['grade']}")
    print(f"  Key: same count, different trust. Age IS signal.")
    print()


def scenario_lambda_comparison():
    """Compare decay curves at different lambda values."""
    print("=== Scenario: Lambda Comparison ===")
    print(f"  SPEC_FLOOR={LAMBDA_FLOOR}, SPEC_CEILING={LAMBDA_CEILING}")
    print()
    
    for lam in [LAMBDA_FLOOR, 0.3, LAMBDA_CEILING]:
        print(f"  λ={lam}:")
        curve = decay_curve_table(lam)
        for point in curve:
            bar = "█" * int(point['pct_of_initial'] / 5)
            print(f"    {point['label']:>6s}: weight={point['weight']:.4f} ({point['pct_of_initial']:5.1f}%) {bar}")
        print()


def scenario_alleged_to_confirmed_upgrade():
    """ALLEGED receipt gets co-signed → weight jumps to 1.0."""
    print("=== Scenario: ALLEGED → CONFIRMED Upgrade ===")
    now = time.time()
    
    # Start as ALLEGED
    r = Receipt("r_upgrade", "ALLEGED", "kit_fox", "slow_signer", now - 3600*6, "B")
    wr_alleged = weight_receipt(r, now)
    
    # After co-sign, becomes CONFIRMED
    r.receipt_type = "CONFIRMED"
    r.co_signed = True
    wr_confirmed = weight_receipt(r, now)
    
    print(f"  Before co-sign (6h ALLEGED): weight={wr_alleged.weight:+.4f}")
    print(f"  After co-sign (CONFIRMED):   weight={wr_confirmed.weight:+.4f}")
    print(f"  Weight jump: {wr_confirmed.weight - wr_alleged.weight:+.4f}")
    print(f"  Key: co-signing is always worth it, but sooner = more total weight-hours contributed")
    print()


if __name__ == "__main__":
    print("Alleged Weight Decay — Exponential Decay for ALLEGED Receipts")
    print("Per santaclawd + Jacobson-Karels (RFC 6298)")
    print("=" * 70)
    print()
    print(f"Formula: weight = {INITIAL_WEIGHT} × exp(−λ × T_hours)")
    print(f"Lambda bounds: [{LAMBDA_FLOOR}, {LAMBDA_CEILING}]")
    print(f"CONFIRMED={CONFIRMED_WEIGHT}, DISPUTED={DISPUTED_WEIGHT}")
    print()
    
    scenario_mixed_receipt_corpus()
    scenario_alleged_age_matters()
    scenario_lambda_comparison()
    scenario_alleged_to_confirmed_upgrade()
    
    print("=" * 70)
    print("KEY INSIGHT: Payer silence at T+5min ≠ T+5h.")
    print("Exponential decay = no cliff, no binary flip.")
    print("Lambda = SPEC_CONSTANT, grader sets within bounds.")
    print("Wilson CI with weight-adjusted n = honest cold start even with mixed ALLEGED ages.")
