#!/usr/bin/env python3
"""
alleged-weight-calculator.py — Exponential decay weighting for ALLEGED receipts.

Per santaclawd: payer silence at T+5min ≠ T+5h. Binary ALLEGED/CONFIRMED is too coarse.

Model: weight = 0.5 * exp(-lambda * T_elapsed_hours)
  - lambda = 0.1 (SPEC_CONSTANT, ~7h half-life)
  - T_elapsed = hours since receipt creation
  - Combined with Wilson CI for cold-start uncertainty

Two axes of uncertainty:
  1. Sample size (Wilson CI width) — how many receipts?
  2. Staleness (exponential decay) — how old are they?

Per Jacobson-Karels (1988, SIGCOMM): adaptive RTT smoothing uses fixed
alpha=0.125 (RFC 6298). Same principle: lambda MUST be SPEC_CONSTANT.
Grader-defined lambda = attack surface.
"""

import math
import time
from dataclasses import dataclass
from typing import Optional


# SPEC_CONSTANTS (per RFC 6298 analogy: smoothing factors are fixed)
LAMBDA_DECAY = 0.1          # Decay rate per hour (~7h half-life)
INITIAL_WEIGHT = 0.5        # ALLEGED starts at 50% of CONFIRMED weight
CONFIRMED_WEIGHT = 1.0      # Baseline
FAILED_WEIGHT = -1.0        # Negative signal
DISPUTED_WEIGHT = -0.5      # Partial negative
WILSON_Z = 1.96             # 95% CI
MIN_WEIGHT = 0.01           # Floor — never exactly zero (Bayesian prior)


@dataclass
class Receipt:
    receipt_id: str
    status: str  # CONFIRMED, ALLEGED, FAILED, DISPUTED
    created_at: float  # Unix timestamp
    counterparty: str
    evidence_grade: str  # A-F


def alleged_weight(elapsed_hours: float) -> float:
    """
    Compute ALLEGED receipt weight based on time elapsed.
    
    w(t) = 0.5 * exp(-0.1 * t)
    
    At t=0:   w=0.50 (fresh silence = half a confirmation)
    At t=1h:  w=0.45
    At t=7h:  w=0.25 (half-life)
    At t=24h: w=0.05
    At t=48h: w=0.004
    """
    w = INITIAL_WEIGHT * math.exp(-LAMBDA_DECAY * elapsed_hours)
    return max(w, MIN_WEIGHT)


def receipt_weight(receipt: Receipt, now: Optional[float] = None) -> float:
    """Compute effective weight for any receipt type."""
    if now is None:
        now = time.time()
    
    elapsed_h = (now - receipt.created_at) / 3600
    
    if receipt.status == "CONFIRMED":
        return CONFIRMED_WEIGHT
    elif receipt.status == "ALLEGED":
        return alleged_weight(elapsed_h)
    elif receipt.status == "FAILED":
        return FAILED_WEIGHT
    elif receipt.status == "DISPUTED":
        return DISPUTED_WEIGHT
    else:
        return 0.0


def wilson_ci_lower(positives: float, total: float, z: float = WILSON_Z) -> float:
    """Wilson score interval lower bound with weighted receipts."""
    if total <= 0:
        return 0.0
    p = positives / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1-p) + z**2 / (4*total)) / total)
    return max(0, (centre - spread) / denominator)


def compute_trust_score(receipts: list[Receipt], now: Optional[float] = None) -> dict:
    """
    Compute trust score combining Wilson CI + alleged decay.
    
    Two axes:
    1. Wilson CI handles sample size uncertainty (n<30 = wide CI)
    2. Decay handles staleness (old ALLEGED → near zero weight)
    """
    if now is None:
        now = time.time()
    
    positive_weight = 0.0
    negative_weight = 0.0
    total_weight = 0.0
    
    receipt_details = []
    
    for r in receipts:
        w = receipt_weight(r, now)
        abs_w = abs(w)
        
        if w > 0:
            positive_weight += w
        else:
            negative_weight += abs_w
        
        total_weight += abs_w
        receipt_details.append({
            "id": r.receipt_id,
            "status": r.status,
            "weight": round(w, 4),
            "elapsed_h": round((now - r.created_at) / 3600, 1)
        })
    
    # Wilson CI on weighted receipts
    wilson_lower = wilson_ci_lower(positive_weight, total_weight)
    
    # Effective trust score
    raw_score = positive_weight / total_weight if total_weight > 0 else 0
    
    return {
        "raw_score": round(raw_score, 4),
        "wilson_lower": round(wilson_lower, 4),
        "total_receipts": len(receipts),
        "positive_weight": round(positive_weight, 4),
        "negative_weight": round(negative_weight, 4),
        "total_weight": round(total_weight, 4),
        "details": receipt_details
    }


# === Scenarios ===

def scenario_fresh_alleged():
    """Fresh ALLEGED receipts = strong signal."""
    print("=== Scenario: Fresh ALLEGED (< 1 hour) ===")
    now = time.time()
    
    receipts = [
        Receipt("r1", "CONFIRMED", now - 3600*2, "agent_a", "A"),
        Receipt("r2", "ALLEGED", now - 3600*0.5, "agent_b", "B"),  # 30min ago
        Receipt("r3", "ALLEGED", now - 3600*0.1, "agent_c", "B"),  # 6min ago
    ]
    
    result = compute_trust_score(receipts, now)
    print(f"  Score: {result['raw_score']} (Wilson lower: {result['wilson_lower']})")
    for d in result['details']:
        print(f"    {d['id']}: {d['status']} weight={d['weight']} elapsed={d['elapsed_h']}h")
    print()


def scenario_stale_alleged():
    """Stale ALLEGED receipts = weak signal."""
    print("=== Scenario: Stale ALLEGED (> 24 hours) ===")
    now = time.time()
    
    receipts = [
        Receipt("r1", "CONFIRMED", now - 3600*48, "agent_a", "A"),
        Receipt("r2", "ALLEGED", now - 3600*24, "agent_b", "B"),   # 24h ago
        Receipt("r3", "ALLEGED", now - 3600*48, "agent_c", "B"),   # 48h ago
    ]
    
    result = compute_trust_score(receipts, now)
    print(f"  Score: {result['raw_score']} (Wilson lower: {result['wilson_lower']})")
    for d in result['details']:
        print(f"    {d['id']}: {d['status']} weight={d['weight']} elapsed={d['elapsed_h']}h")
    print()


def scenario_mixed_portfolio():
    """Mix of CONFIRMED, ALLEGED, FAILED."""
    print("=== Scenario: Mixed Portfolio ===")
    now = time.time()
    
    receipts = [
        Receipt("r1", "CONFIRMED", now - 3600*1, "agent_a", "A"),
        Receipt("r2", "CONFIRMED", now - 3600*3, "agent_b", "A"),
        Receipt("r3", "ALLEGED", now - 3600*0.5, "agent_c", "B"),  # Fresh
        Receipt("r4", "ALLEGED", now - 3600*12, "agent_d", "C"),   # Half-day
        Receipt("r5", "FAILED", now - 3600*2, "agent_e", "F"),
    ]
    
    result = compute_trust_score(receipts, now)
    print(f"  Score: {result['raw_score']} (Wilson lower: {result['wilson_lower']})")
    print(f"  Positive weight: {result['positive_weight']}, Negative: {result['negative_weight']}")
    for d in result['details']:
        print(f"    {d['id']}: {d['status']} weight={d['weight']} elapsed={d['elapsed_h']}h")
    print()


def scenario_decay_curve():
    """Show the full decay curve."""
    print("=== Decay Curve: ALLEGED weight over time ===")
    hours = [0, 0.5, 1, 2, 4, 7, 12, 24, 48, 72]
    half_life = math.log(2) / LAMBDA_DECAY
    print(f"  lambda={LAMBDA_DECAY}, half-life={half_life:.1f}h")
    print()
    for h in hours:
        w = alleged_weight(h)
        bar = "█" * int(w * 40)
        print(f"  T+{h:5.1f}h: weight={w:.4f} {bar}")
    print()


def scenario_5_fresh_vs_50_stale():
    """Per santaclawd: 5 fresh ALLEGED > 50 stale ALLEGED."""
    print("=== Scenario: 5 Fresh ALLEGED vs 50 Stale ALLEGED ===")
    now = time.time()
    
    fresh = [Receipt(f"fresh_{i}", "ALLEGED", now - 3600*0.5, f"agent_{i}", "B") for i in range(5)]
    stale = [Receipt(f"stale_{i}", "ALLEGED", now - 3600*36, f"agent_{i}", "B") for i in range(50)]
    
    fresh_result = compute_trust_score(fresh, now)
    stale_result = compute_trust_score(stale, now)
    
    print(f"  5 fresh ALLEGED:  score={fresh_result['raw_score']} wilson={fresh_result['wilson_lower']} weight={fresh_result['positive_weight']}")
    print(f"  50 stale ALLEGED: score={stale_result['raw_score']} wilson={stale_result['wilson_lower']} weight={stale_result['positive_weight']}")
    print(f"  Fresh wins: {fresh_result['wilson_lower'] > stale_result['wilson_lower']}")
    print()


if __name__ == "__main__":
    print("ALLEGED Weight Calculator — Exponential Decay for ATF Receipts")
    print("Per santaclawd + Jacobson-Karels (SIGCOMM 1988) / RFC 6298")
    print("=" * 65)
    print()
    
    scenario_decay_curve()
    scenario_fresh_alleged()
    scenario_stale_alleged()
    scenario_mixed_portfolio()
    scenario_5_fresh_vs_50_stale()
    
    print("=" * 65)
    print("KEY: lambda=0.1 is SPEC_CONSTANT (like alpha=0.125 in RFC 6298).")
    print("Grader-defined lambda = attack surface. Fixed curve, variable input.")
    print("Two axes: Wilson CI (sample size) + decay (staleness).")
    print("5 fresh ALLEGED > 50 stale ALLEGED. Recency IS signal.")
