#!/usr/bin/env python3
"""
alleged-weight-decay.py — Exponential decay for ALLEGED receipt weight in ATF.

Per santaclawd: payer silence at T+5min ≠ T+5h. Binary ALLEGED→CONFIRMED flip
is wrong. Weight should decay continuously.

Model: weight = 0.5 × exp(-λ × T_elapsed_hours)
Lambda: SPEC_CONSTANT = 0.1 (not grader-defined — race to bottom otherwise)

Jacobson-Karels (1988) parallel: SRTT = α×SRTT + (1-α)×RTT
Same EWMA smoothing principle applied to trust weight.

Wilson CI integration: n(ALLEGED) penalized by weight.
5 ALLEGED at weight 0.47 each = effective n ≈ 2.35
CI widens naturally for stale evidence.
"""

import math
import time
from dataclasses import dataclass
from typing import Optional


# SPEC_CONSTANTS
ALLEGED_DECAY_LAMBDA = 0.1    # Decay rate (per hour). SPEC_NORMATIVE.
ALLEGED_INITIAL_WEIGHT = 0.5  # Fresh ALLEGED starts at 0.5 (half a CONFIRMED)
CONFIRMED_WEIGHT = 1.0
FAILED_WEIGHT = 0.0
DISPUTED_WEIGHT = -0.5        # Negative signal
MIN_WEIGHT = 0.01             # Floor before treating as expired
WILSON_Z = 1.96               # 95% CI


class ReceiptState:
    CONFIRMED = "CONFIRMED"
    ALLEGED = "ALLEGED"
    FAILED = "FAILED"
    DISPUTED = "DISPUTED"
    EXPIRED = "EXPIRED"


@dataclass
class WeightedReceipt:
    receipt_id: str
    state: str
    created_at: float  # Unix timestamp
    co_signed_at: Optional[float] = None
    counterparty_id: str = ""
    evidence_grade: str = "C"
    
    def weight_at(self, eval_time: float) -> float:
        """Compute receipt weight at evaluation time."""
        if self.state == ReceiptState.CONFIRMED:
            return CONFIRMED_WEIGHT
        elif self.state == ReceiptState.FAILED:
            return FAILED_WEIGHT
        elif self.state == ReceiptState.DISPUTED:
            return DISPUTED_WEIGHT
        elif self.state == ReceiptState.ALLEGED:
            elapsed_hours = (eval_time - self.created_at) / 3600
            weight = ALLEGED_INITIAL_WEIGHT * math.exp(-ALLEGED_DECAY_LAMBDA * elapsed_hours)
            return max(weight, MIN_WEIGHT) if weight > MIN_WEIGHT else 0.0
        return 0.0


def effective_n(receipts: list[WeightedReceipt], eval_time: float) -> float:
    """Compute effective sample size from weighted receipts."""
    return sum(r.weight_at(eval_time) for r in receipts if r.weight_at(eval_time) > 0)


def wilson_ci_weighted(receipts: list[WeightedReceipt], eval_time: float) -> dict:
    """Wilson CI with weighted receipts."""
    weights = [(r, r.weight_at(eval_time)) for r in receipts]
    positive_weights = [(r, w) for r, w in weights if w > 0]
    
    n_eff = sum(w for _, w in positive_weights)
    if n_eff < 0.5:
        return {"lower": 0.0, "upper": 0.0, "n_effective": 0, "grade": "F"}
    
    # Weighted success rate (CONFIRMED = full success, ALLEGED = partial)
    p_hat = sum(w for r, w in positive_weights 
                if r.state in (ReceiptState.CONFIRMED, ReceiptState.ALLEGED)) / n_eff
    
    z2 = WILSON_Z ** 2
    denom = 1 + z2 / n_eff
    center = (p_hat + z2 / (2 * n_eff)) / denom
    margin = (WILSON_Z * math.sqrt(p_hat * (1 - p_hat) / n_eff + z2 / (4 * n_eff**2))) / denom
    
    lower = max(0, center - margin)
    upper = min(1, center + margin)
    
    # Grade from lower bound
    if lower >= 0.85: grade = "A"
    elif lower >= 0.70: grade = "B"
    elif lower >= 0.50: grade = "C"
    elif lower >= 0.30: grade = "D"
    else: grade = "F"
    
    return {
        "lower": round(lower, 4),
        "upper": round(upper, 4),
        "n_effective": round(n_eff, 2),
        "p_hat": round(p_hat, 4),
        "grade": grade
    }


def decay_curve(hours: list[float]) -> list[dict]:
    """Show decay curve at various time points."""
    results = []
    for h in hours:
        weight = ALLEGED_INITIAL_WEIGHT * math.exp(-ALLEGED_DECAY_LAMBDA * h)
        results.append({
            "hours": h,
            "weight": round(weight, 4),
            "pct_of_confirmed": f"{weight/CONFIRMED_WEIGHT:.1%}",
            "status": "ACTIVE" if weight > MIN_WEIGHT else "EXPIRED"
        })
    return results


# === Scenarios ===

def scenario_decay_curve():
    """Show ALLEGED weight decay over time."""
    print("=== Decay Curve (λ=0.1, initial=0.5) ===")
    hours = [0, 0.083, 0.5, 1, 2, 5, 10, 24, 48, 72]
    for entry in decay_curve(hours):
        h = entry['hours']
        label = f"{int(h*60)}min" if h < 1 else f"{h}h"
        print(f"  T+{label:>6}: weight={entry['weight']:.4f} ({entry['pct_of_confirmed']}) {entry['status']}")
    print()


def scenario_wilson_ci_comparison():
    """Compare agents: one with fresh ALLEGEDs, one with stale."""
    print("=== Wilson CI: Fresh vs Stale ALLEGED ===")
    now = time.time()
    
    # Agent A: 5 fresh ALLEGEDs (5 min old)
    fresh = [WeightedReceipt(f"r{i}", ReceiptState.ALLEGED, now - 300, 
                              counterparty_id=f"cp_{i}") for i in range(5)]
    
    # Agent B: 5 stale ALLEGEDs (24h old)
    stale = [WeightedReceipt(f"r{i}", ReceiptState.ALLEGED, now - 86400,
                              counterparty_id=f"cp_{i}") for i in range(5)]
    
    # Agent C: 5 CONFIRMED
    confirmed = [WeightedReceipt(f"r{i}", ReceiptState.CONFIRMED, now - 3600,
                                  counterparty_id=f"cp_{i}") for i in range(5)]
    
    for name, receipts in [("Fresh ALLEGED (5min)", fresh), 
                           ("Stale ALLEGED (24h)", stale),
                           ("CONFIRMED", confirmed)]:
        ci = wilson_ci_weighted(receipts, now)
        n_eff = effective_n(receipts, now)
        print(f"  {name:>25}: n_eff={n_eff:.2f} CI=[{ci['lower']:.3f}, {ci['upper']:.3f}] Grade={ci['grade']}")
    print()


def scenario_mixed_portfolio():
    """Real agent with mix of receipt types."""
    print("=== Mixed Portfolio ===")
    now = time.time()
    
    receipts = [
        WeightedReceipt("r1", ReceiptState.CONFIRMED, now - 7200, counterparty_id="bro_agent"),
        WeightedReceipt("r2", ReceiptState.CONFIRMED, now - 3600, counterparty_id="santaclawd"),
        WeightedReceipt("r3", ReceiptState.ALLEGED, now - 600, counterparty_id="new_agent"),  # 10min
        WeightedReceipt("r4", ReceiptState.ALLEGED, now - 43200, counterparty_id="slow_agent"),  # 12h
        WeightedReceipt("r5", ReceiptState.DISPUTED, now - 1800, counterparty_id="bad_agent"),
        WeightedReceipt("r6", ReceiptState.CONFIRMED, now - 900, counterparty_id="funwolf"),
    ]
    
    print("  Receipt weights:")
    for r in receipts:
        w = r.weight_at(now)
        elapsed = (now - r.created_at) / 3600
        print(f"    {r.receipt_id} ({r.state:>10}, {elapsed:.1f}h): weight={w:.4f} → {r.counterparty_id}")
    
    ci = wilson_ci_weighted(receipts, now)
    n_eff = effective_n(receipts, now)
    print(f"\n  Effective n: {n_eff:.2f}")
    print(f"  Wilson CI: [{ci['lower']:.3f}, {ci['upper']:.3f}]")
    print(f"  Grade: {ci['grade']}")
    print()


def scenario_lambda_sensitivity():
    """Show why lambda must be SPEC_CONSTANT not grader-defined."""
    print("=== Lambda Sensitivity (Why SPEC_CONSTANT) ===")
    now = time.time()
    
    receipts = [WeightedReceipt(f"r{i}", ReceiptState.ALLEGED, now - 7200,
                                 counterparty_id=f"cp_{i}") for i in range(10)]
    
    for lam in [0.01, 0.05, 0.1, 0.5, 1.0]:
        # Temporarily override lambda
        weights = [0.5 * math.exp(-lam * 2) for _ in receipts]  # 2h elapsed
        n_eff = sum(weights)
        p_hat = 1.0  # All positive
        z2 = WILSON_Z ** 2
        denom = 1 + z2 / max(n_eff, 0.1)
        center = (p_hat + z2 / (2 * max(n_eff, 0.1))) / denom
        margin = (WILSON_Z * math.sqrt(p_hat * (1-p_hat) / max(n_eff, 0.1) + z2 / (4 * max(n_eff, 0.1)**2))) / denom
        lower = max(0, center - margin)
        
        print(f"  λ={lam:>4}: weight_each={weights[0]:.4f} n_eff={n_eff:.2f} CI_lower={lower:.3f}")
    
    print("  ↑ Generous λ=0.01 gives n_eff=4.90 (barely decayed). Strict λ=1.0 gives n_eff=0.68 (nearly expired).")
    print("  Grader-defined λ = RACE TO BOTTOM. Must be SPEC_NORMATIVE.")
    print()


if __name__ == "__main__":
    print("ALLEGED Weight Decay — Exponential Trust Scoring for ATF Receipts")
    print("Per santaclawd + Jacobson-Karels (1988)")
    print("=" * 70)
    print(f"λ = {ALLEGED_DECAY_LAMBDA} (SPEC_NORMATIVE)")
    print(f"weight = {ALLEGED_INITIAL_WEIGHT} × exp(-{ALLEGED_DECAY_LAMBDA} × T_hours)")
    print()
    
    scenario_decay_curve()
    scenario_wilson_ci_comparison()
    scenario_mixed_portfolio()
    scenario_lambda_sensitivity()
    
    print("=" * 70)
    print("KEY INSIGHT: Silence has a half-life. 5min silence ≈ 47% of CONFIRMED.")
    print("24h silence ≈ 4.5%. Time does the grading. Lambda must be SPEC_CONSTANT")
    print("to prevent race-to-bottom by generous graders.")
