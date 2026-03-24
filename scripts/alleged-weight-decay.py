#!/usr/bin/env python3
"""
alleged-weight-decay.py — Exponential decay for ALLEGED receipt weight in ATF.

Per santaclawd: payer silence at T+5min ≠ T+5h. Binary ALLEGED/CONFIRMED is too coarse.
Per Jacobson-Karels (1988): adaptive timeout with fixed bounds (alpha=0.125, beta=0.25).

Model: weight = base_weight × exp(-lambda × T_elapsed_hours)
- lambda = SPEC_CONSTANT (not grader-defined, prevents race to bottom)
- Combined with Wilson CI for cold-start correction
- Final trust = wilson_lower(successes, total) × decay(age)

SPEC_CONSTANTS:
  ALLEGED_LAMBDA = 0.1/hr (half-life ≈ 6.93 hours)
  ALLEGED_LAMBDA_FLOOR = 0.01/hr
  ALLEGED_LAMBDA_CEILING = 1.0/hr
  ALLEGED_BASE_WEIGHT = 0.5 (fresh ALLEGED = half a CONFIRMED)
  WILSON_Z = 1.96 (95% CI)
"""

import math
import time
from dataclasses import dataclass
from typing import Optional

# SPEC_CONSTANTS — fixed in spec, not grader-configurable
ALLEGED_LAMBDA = 0.1          # per hour, half-life ≈ 6.93h
ALLEGED_LAMBDA_FLOOR = 0.01   # minimum decay rate
ALLEGED_LAMBDA_CEILING = 1.0  # maximum decay rate
ALLEGED_BASE_WEIGHT = 0.5     # fresh ALLEGED = 0.5 × CONFIRMED
CONFIRMED_WEIGHT = 1.0
DISPUTED_WEIGHT = -0.5
WILSON_Z = 1.96               # 95% confidence


@dataclass
class Receipt:
    receipt_id: str
    status: str  # CONFIRMED, ALLEGED, DISPUTED
    created_at: float  # unix timestamp
    confirmed_at: Optional[float] = None  # when co-signed (if ever)
    counterparty_id: str = ""
    evidence_grade: str = "C"


def alleged_decay_weight(elapsed_hours: float, 
                          lam: float = ALLEGED_LAMBDA,
                          base: float = ALLEGED_BASE_WEIGHT) -> float:
    """
    Compute ALLEGED receipt weight with exponential decay.
    
    Fresh ALLEGED (T=0): weight = base (0.5)
    T = half-life: weight = base/2 (0.25)
    T → ∞: weight → 0
    
    Jacobson-Karels insight: fixed alpha with adaptive bounds.
    Here: fixed lambda with SPEC bounds.
    """
    lam = max(ALLEGED_LAMBDA_FLOOR, min(ALLEGED_LAMBDA_CEILING, lam))
    return base * math.exp(-lam * elapsed_hours)


def wilson_lower_bound(successes: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score interval lower bound for trust estimation."""
    if total == 0:
        return 0.0
    p_hat = successes / total
    denominator = 1 + z**2 / total
    center = (p_hat + z**2 / (2 * total)) / denominator
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total) / denominator
    return max(0.0, center - spread)


def combined_trust_score(receipts: list[Receipt], now: float = None) -> dict:
    """
    Compute combined trust using Wilson CI + decay.
    
    trust = wilson_lower(weighted_successes, weighted_total) × recency_factor
    """
    if now is None:
        now = time.time()
    
    weighted_success = 0.0
    weighted_total = 0.0
    status_counts = {"CONFIRMED": 0, "ALLEGED": 0, "DISPUTED": 0}
    
    for r in receipts:
        elapsed_hours = (now - r.created_at) / 3600
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
        
        if r.status == "CONFIRMED":
            weight = CONFIRMED_WEIGHT
            weighted_success += weight
            weighted_total += weight
        elif r.status == "ALLEGED":
            weight = alleged_decay_weight(elapsed_hours)
            weighted_success += weight  # ALLEGED counts as partial success
            weighted_total += ALLEGED_BASE_WEIGHT  # denominator uses base weight
        elif r.status == "DISPUTED":
            weight = abs(DISPUTED_WEIGHT)
            weighted_total += weight  # failure in denominator
    
    # Wilson CI on weighted counts
    w_successes = int(round(weighted_success * 10))  # scale to integers
    w_total = int(round(weighted_total * 10))
    
    wilson = wilson_lower_bound(w_successes, w_total) if w_total > 0 else 0.0
    
    # Recency: oldest receipt age
    if receipts:
        oldest_hours = max((now - r.created_at) / 3600 for r in receipts)
        newest_hours = min((now - r.created_at) / 3600 for r in receipts)
    else:
        oldest_hours = newest_hours = 0
    
    return {
        "wilson_lower": round(wilson, 4),
        "status_counts": status_counts,
        "weighted_success": round(weighted_success, 4),
        "weighted_total": round(weighted_total, 4),
        "total_receipts": len(receipts),
        "oldest_hours": round(oldest_hours, 1),
        "newest_hours": round(newest_hours, 1),
        "half_life_hours": round(math.log(2) / ALLEGED_LAMBDA, 2)
    }


def grade_trust(score: float) -> str:
    """Grade trust score."""
    if score >= 0.8: return "A"
    if score >= 0.6: return "B"
    if score >= 0.4: return "C"
    if score >= 0.2: return "D"
    return "F"


# === Scenarios ===

def scenario_fresh_vs_stale_alleged():
    """Same receipt count, different staleness."""
    print("=== Scenario: Fresh vs Stale ALLEGED ===")
    now = time.time()
    
    # Fresh ALLEGED (1 hour old)
    fresh = [Receipt(f"r{i}", "ALLEGED", now - 3600, counterparty_id="peer") for i in range(10)]
    fresh_score = combined_trust_score(fresh, now)
    
    # Stale ALLEGED (24 hours old)
    stale = [Receipt(f"r{i}", "ALLEGED", now - 86400, counterparty_id="peer") for i in range(10)]
    stale_score = combined_trust_score(stale, now)
    
    # Very stale ALLEGED (72 hours old)
    very_stale = [Receipt(f"r{i}", "ALLEGED", now - 259200, counterparty_id="peer") for i in range(10)]
    very_stale_score = combined_trust_score(very_stale, now)
    
    print(f"  10 ALLEGED @ 1h:  wilson={fresh_score['wilson_lower']:.3f} "
          f"grade={grade_trust(fresh_score['wilson_lower'])} "
          f"weighted_success={fresh_score['weighted_success']:.3f}")
    print(f"  10 ALLEGED @ 24h: wilson={stale_score['wilson_lower']:.3f} "
          f"grade={grade_trust(stale_score['wilson_lower'])} "
          f"weighted_success={stale_score['weighted_success']:.3f}")
    print(f"  10 ALLEGED @ 72h: wilson={very_stale_score['wilson_lower']:.3f} "
          f"grade={grade_trust(very_stale_score['wilson_lower'])} "
          f"weighted_success={very_stale_score['weighted_success']:.3f}")
    print(f"  Half-life: {fresh_score['half_life_hours']}h")
    print()


def scenario_mixed_confirmed_alleged():
    """Mix of CONFIRMED and ALLEGED receipts."""
    print("=== Scenario: Mixed CONFIRMED + ALLEGED ===")
    now = time.time()
    
    receipts = (
        [Receipt(f"c{i}", "CONFIRMED", now - 3600*i) for i in range(5)] +
        [Receipt(f"a{i}", "ALLEGED", now - 3600*(i+1)) for i in range(5)]
    )
    score = combined_trust_score(receipts, now)
    
    print(f"  5 CONFIRMED + 5 ALLEGED (1-10h old)")
    print(f"  Wilson: {score['wilson_lower']:.3f} Grade: {grade_trust(score['wilson_lower'])}")
    print(f"  Weighted success: {score['weighted_success']:.3f} / {score['weighted_total']:.3f}")
    print()


def scenario_alleged_becoming_confirmed():
    """ALLEGED receipts getting co-signed over time."""
    print("=== Scenario: ALLEGED → CONFIRMED Upgrade ===")
    now = time.time()
    
    # Initially all ALLEGED
    all_alleged = [Receipt(f"r{i}", "ALLEGED", now - 3600*2) for i in range(10)]
    alleged_score = combined_trust_score(all_alleged, now)
    
    # Half co-signed (upgraded to CONFIRMED)
    half_confirmed = (
        [Receipt(f"r{i}", "CONFIRMED", now - 3600*2) for i in range(5)] +
        [Receipt(f"r{i}", "ALLEGED", now - 3600*2) for i in range(5, 10)]
    )
    half_score = combined_trust_score(half_confirmed, now)
    
    # All co-signed
    all_confirmed = [Receipt(f"r{i}", "CONFIRMED", now - 3600*2) for i in range(10)]
    confirmed_score = combined_trust_score(all_confirmed, now)
    
    print(f"  10 ALLEGED @ 2h:     wilson={alleged_score['wilson_lower']:.3f}")
    print(f"  5 CONFIRMED + 5 ALL: wilson={half_score['wilson_lower']:.3f}")
    print(f"  10 CONFIRMED:        wilson={confirmed_score['wilson_lower']:.3f}")
    print(f"  Co-signing upgrades trust gradually, not binary flip")
    print()


def scenario_disputed_mixed():
    """Impact of DISPUTED receipts."""
    print("=== Scenario: DISPUTED Impact ===")
    now = time.time()
    
    # Clean agent
    clean = [Receipt(f"r{i}", "CONFIRMED", now - 3600) for i in range(10)]
    clean_score = combined_trust_score(clean, now)
    
    # 2 disputed
    disputed = (
        [Receipt(f"r{i}", "CONFIRMED", now - 3600) for i in range(8)] +
        [Receipt(f"d{i}", "DISPUTED", now - 3600) for i in range(2)]
    )
    disputed_score = combined_trust_score(disputed, now)
    
    # 5 disputed
    half_disputed = (
        [Receipt(f"r{i}", "CONFIRMED", now - 3600) for i in range(5)] +
        [Receipt(f"d{i}", "DISPUTED", now - 3600) for i in range(5)]
    )
    half_score = combined_trust_score(half_disputed, now)
    
    print(f"  10/10 CONFIRMED:  wilson={clean_score['wilson_lower']:.3f} grade={grade_trust(clean_score['wilson_lower'])}")
    print(f"  8/10 + 2 DISPUTED: wilson={disputed_score['wilson_lower']:.3f} grade={grade_trust(disputed_score['wilson_lower'])}")
    print(f"  5/10 + 5 DISPUTED: wilson={half_score['wilson_lower']:.3f} grade={grade_trust(half_score['wilson_lower'])}")
    print()


def scenario_decay_curve():
    """Print decay curve over time."""
    print("=== Decay Curve (ALLEGED weight over time) ===")
    hours = [0, 1, 2, 4, 7, 12, 24, 48, 72]
    for h in hours:
        w = alleged_decay_weight(h)
        bar = "█" * int(w * 40)
        print(f"  T+{h:3d}h: weight={w:.4f} {bar}")
    print(f"  Half-life: {math.log(2)/ALLEGED_LAMBDA:.1f}h")
    print()


if __name__ == "__main__":
    print("ALLEGED Weight Decay — Exponential Trust Decay for ATF Receipts")
    print("Per santaclawd + Jacobson-Karels (1988)")
    print("=" * 70)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  ALLEGED_LAMBDA = {ALLEGED_LAMBDA}/hr (half-life = {math.log(2)/ALLEGED_LAMBDA:.1f}h)")
    print(f"  ALLEGED_BASE_WEIGHT = {ALLEGED_BASE_WEIGHT}")
    print(f"  WILSON_Z = {WILSON_Z}")
    print()
    
    scenario_decay_curve()
    scenario_fresh_vs_stale_alleged()
    scenario_mixed_confirmed_alleged()
    scenario_alleged_becoming_confirmed()
    scenario_disputed_mixed()
    
    print("=" * 70)
    print("KEY INSIGHT: lambda MUST be SPEC_CONSTANT not grader-defined.")
    print("Grader-defined lambda = race to bottom (longer = more forgiving = more business).")
    print("Jacobson-Karels: fixed alpha + adaptive bounds. Same pattern.")
    print("Wilson CI handles sample size. Decay handles staleness. Orthogonal.")
