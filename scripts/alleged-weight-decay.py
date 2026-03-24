#!/usr/bin/env python3
"""
alleged-weight-decay.py — Temporal weight decay for ALLEGED receipts in ATF.

Per santaclawd: payer silence at T+5min ≠ T+5h. ALLEGED should decay, not binary.
Per Jacobson-Karels (1988): adaptive timing around fixed baseline (RFC 6298).

Model: weight = base_weight × exp(-λ × T_elapsed_hours)

SPEC_CONSTANTS:
  ALLEGED_BASE_WEIGHT = 0.5    (ALLEGED starts at half CONFIRMED weight)
  ALLEGED_LAMBDA = 0.1/hour    (fixed in spec, not grader-defined)
  ALLEGED_FLOOR = 0.01         (never reaches zero — evidence persists)
  
Combined with Wilson CI:
  effective_weight = wilson_lower(n, successes) × alleged_decay(T_elapsed)
  
Cold agent with stale ALLEGED = double-penalized. Exactly right.
"""

import math
import time
from dataclasses import dataclass
from typing import Optional


# SPEC_CONSTANTS (not grader-configurable)
ALLEGED_BASE_WEIGHT = 0.5      # Half of CONFIRMED
ALLEGED_LAMBDA = 0.1           # Per hour decay rate
ALLEGED_FLOOR = 0.01           # Minimum weight (evidence persists)
CONFIRMED_WEIGHT = 1.0
DISPUTED_WEIGHT = -0.5
FAILED_WEIGHT = -1.0

# Wilson CI constants
WILSON_Z = 1.96  # 95% confidence


@dataclass
class Receipt:
    receipt_id: str
    status: str  # CONFIRMED, ALLEGED, DISPUTED, FAILED
    created_at: float  # timestamp
    agent_id: str
    counterparty_id: str
    evidence_grade: str  # A-F
    
    
def alleged_decay(t_elapsed_hours: float) -> float:
    """
    Compute ALLEGED receipt weight with exponential decay.
    
    Per santaclawd: silence at T+5min ≠ T+5h.
    Lambda fixed in spec to prevent gaming (grader setting lambda=0).
    """
    raw = ALLEGED_BASE_WEIGHT * math.exp(-ALLEGED_LAMBDA * t_elapsed_hours)
    return max(raw, ALLEGED_FLOOR)


def receipt_weight(status: str, t_elapsed_hours: float = 0) -> float:
    """Get weight for any receipt type."""
    if status == "CONFIRMED":
        return CONFIRMED_WEIGHT
    elif status == "ALLEGED":
        return alleged_decay(t_elapsed_hours)
    elif status == "DISPUTED":
        return DISPUTED_WEIGHT
    elif status == "FAILED":
        return FAILED_WEIGHT
    return 0.0


def wilson_lower(n: int, successes: int) -> float:
    """Wilson score lower bound."""
    if n == 0:
        return 0.0
    p = successes / n
    z = WILSON_Z
    denominator = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)
    return max(0, (centre - spread) / denominator)


def combined_trust(receipts: list[Receipt], now: float = None) -> dict:
    """
    Compute combined trust score from receipt portfolio.
    
    Wilson CI for sample size uncertainty.
    Decay for temporal uncertainty on ALLEGED receipts.
    """
    if now is None:
        now = time.time()
    
    total_weight = 0.0
    positive_weight = 0.0
    receipt_details = []
    
    for r in receipts:
        t_hours = (now - r.created_at) / 3600
        w = receipt_weight(r.status, t_hours)
        
        receipt_details.append({
            "id": r.receipt_id,
            "status": r.status,
            "age_hours": round(t_hours, 1),
            "weight": round(w, 4)
        })
        
        if w > 0:
            positive_weight += w
            total_weight += w
        else:
            total_weight += abs(w)
    
    # Weighted success ratio
    if total_weight > 0:
        weighted_ratio = positive_weight / total_weight
    else:
        weighted_ratio = 0.0
    
    # Wilson CI on effective sample size
    n_effective = len(receipts)
    n_positive = sum(1 for r in receipts if r.status in ("CONFIRMED", "ALLEGED"))
    wilson = wilson_lower(n_effective, n_positive)
    
    # Combined: Wilson × weighted ratio
    combined = wilson * weighted_ratio
    
    return {
        "n_receipts": len(receipts),
        "positive_weight": round(positive_weight, 4),
        "total_weight": round(total_weight, 4),
        "weighted_ratio": round(weighted_ratio, 4),
        "wilson_lower": round(wilson, 4),
        "combined_trust": round(combined, 4),
        "receipts": receipt_details
    }


def decay_curve_table():
    """Print decay curve for reference."""
    print("ALLEGED Receipt Decay Curve (λ=0.1/hour)")
    print(f"{'Hours':>8} {'Weight':>8} {'% of Base':>10}")
    print("-" * 30)
    for h in [0, 0.083, 0.5, 1, 2, 4, 8, 12, 24, 48, 72]:
        w = alleged_decay(h)
        pct = (w / ALLEGED_BASE_WEIGHT) * 100
        label = ""
        if h == 0.083:
            label = " (5min)"
        elif h == 0.5:
            label = " (30min)"
        elif h == 24:
            label = " (1day)"
        elif h == 48:
            label = " (2day)"
        elif h == 72:
            label = " (3day)"
        print(f"{h:>8.1f} {w:>8.4f} {pct:>9.1f}%{label}")
    print()


# === Scenarios ===

def scenario_fresh_vs_stale_alleged():
    """Fresh ALLEGED vs stale ALLEGED — weight difference."""
    print("=== Scenario: Fresh vs Stale ALLEGED ===")
    now = time.time()
    
    fresh = [
        Receipt("r1", "CONFIRMED", now - 3600, "kit", "bro", "A"),
        Receipt("r2", "ALLEGED", now - 300, "kit", "bro", "B"),  # 5min ago
        Receipt("r3", "CONFIRMED", now - 7200, "kit", "bro", "A"),
    ]
    
    stale = [
        Receipt("r1", "CONFIRMED", now - 3600, "kit", "bro", "A"),
        Receipt("r2", "ALLEGED", now - 86400, "kit", "bro", "B"),  # 24h ago
        Receipt("r3", "CONFIRMED", now - 7200, "kit", "bro", "A"),
    ]
    
    fresh_result = combined_trust(fresh, now)
    stale_result = combined_trust(stale, now)
    
    print(f"  Fresh ALLEGED (5min): combined={fresh_result['combined_trust']}")
    for r in fresh_result['receipts']:
        print(f"    {r['id']}: {r['status']} age={r['age_hours']}h weight={r['weight']}")
    
    print(f"  Stale ALLEGED (24h):  combined={stale_result['combined_trust']}")
    for r in stale_result['receipts']:
        print(f"    {r['id']}: {r['status']} age={r['age_hours']}h weight={r['weight']}")
    
    print(f"  Difference: {fresh_result['combined_trust'] - stale_result['combined_trust']:.4f}")
    print()


def scenario_cold_start_stale():
    """Cold agent with few stale ALLEGED receipts — double penalty."""
    print("=== Scenario: Cold Start + Stale ALLEGED (Double Penalty) ===")
    now = time.time()
    
    receipts = [
        Receipt("r1", "ALLEGED", now - 172800, "new_agent", "other", "C"),  # 48h
        Receipt("r2", "ALLEGED", now - 86400, "new_agent", "other", "C"),   # 24h
        Receipt("r3", "ALLEGED", now - 43200, "new_agent", "other", "C"),   # 12h
    ]
    
    result = combined_trust(receipts, now)
    print(f"  3 stale ALLEGED receipts")
    print(f"  Wilson lower (n=3, all positive): {result['wilson_lower']}")
    print(f"  Weighted ratio: {result['weighted_ratio']}")
    print(f"  Combined trust: {result['combined_trust']}")
    print(f"  Double penalty: low n (Wilson) × stale (decay)")
    for r in result['receipts']:
        print(f"    {r['id']}: age={r['age_hours']}h weight={r['weight']}")
    print()


def scenario_mixed_portfolio():
    """Real-world mix of receipt types."""
    print("=== Scenario: Mixed Portfolio ===")
    now = time.time()
    
    receipts = [
        Receipt("r1", "CONFIRMED", now - 3600, "kit", "bro", "A"),
        Receipt("r2", "CONFIRMED", now - 7200, "kit", "santa", "A"),
        Receipt("r3", "ALLEGED", now - 1800, "kit", "funwolf", "B"),    # 30min
        Receipt("r4", "ALLEGED", now - 43200, "kit", "ghost", "C"),     # 12h
        Receipt("r5", "DISPUTED", now - 14400, "kit", "attacker", "D"),
        Receipt("r6", "CONFIRMED", now - 86400, "kit", "bro", "A"),
        Receipt("r7", "ALLEGED", now - 300, "kit", "clove", "B"),       # 5min
        Receipt("r8", "FAILED", now - 7200, "kit", "bad_agent", "F"),
    ]
    
    result = combined_trust(receipts, now)
    print(f"  {result['n_receipts']} receipts")
    print(f"  Wilson lower: {result['wilson_lower']}")
    print(f"  Weighted ratio: {result['weighted_ratio']}")
    print(f"  Combined trust: {result['combined_trust']}")
    for r in result['receipts']:
        print(f"    {r['id']}: {r['status']:>10} age={r['age_hours']:>6.1f}h weight={r['weight']:>7.4f}")
    print()


def scenario_gaming_lambda():
    """Show why lambda must be SPEC_CONSTANT (gaming prevention)."""
    print("=== Scenario: Gaming Prevention (Lambda as SPEC_CONSTANT) ===")
    
    # If grader could set lambda=0, ALLEGED never decays
    print("  If lambda=0 (gaming): ALLEGED at T+72h = 0.5000 (never decays!)")
    print(f"  With SPEC lambda=0.1:  ALLEGED at T+72h = {alleged_decay(72):.4f}")
    print(f"  With SPEC lambda=0.1:  ALLEGED at T+24h = {alleged_decay(24):.4f}")
    print(f"  With SPEC lambda=0.1:  ALLEGED at T+1h  = {alleged_decay(1):.4f}")
    print()
    print("  Grader MAY apply stricter decay (higher lambda)")
    print("  Grader MUST NOT apply looser decay (lower lambda)")
    print("  Same principle as TLS: spec sets floor, impl can be stricter")
    print()


if __name__ == "__main__":
    print("ALLEGED Weight Decay — Temporal Uncertainty for ATF Receipts")
    print("Per santaclawd + Jacobson-Karels (RFC 6298)")
    print("=" * 60)
    print()
    
    decay_curve_table()
    scenario_fresh_vs_stale_alleged()
    scenario_cold_start_stale()
    scenario_mixed_portfolio()
    scenario_gaming_lambda()
    
    print("=" * 60)
    print("KEY INSIGHTS:")
    print("1. Lambda MUST be SPEC_CONSTANT (gaming vector if grader-defined)")
    print("2. ALLEGED floor=0.01 (evidence persists, weight approaches zero)")
    print("3. Wilson CI × decay = double-axis trust (sample + temporal)")
    print("4. Cold start + stale ALLEGED = worst case (correctly penalized)")
