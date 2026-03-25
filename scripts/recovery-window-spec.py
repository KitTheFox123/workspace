#!/usr/bin/env python3
"""
recovery-window-spec.py — ATF V1.2 item #3: 30d/n=8 recovery window spec.

Per santaclawd: "what is the 30d/n=8 spec text?"

DORMANT agent recovery: proven identity resumes after idle period.
NOT cold start (no priors). Recovery uses prior receipt history as
Bayesian evidence. certificateHold (RFC 5280 §5.3.1) = pause not purge.

Spec text candidates for V1.2:
  - RECOVERY_WINDOW: 30 calendar days from first post-dormancy receipt
  - n_recovery: 8 COMPLETION receipts required within window
  - Prior receipts used as Wilson CI prior (hibernation not amnesia)
  - Failed window: REVOKED (no second chance without cold start)
  - Decay: 5%/month exponential, floor 0.30 (not 0.10 — revision)
"""

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentState(Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"           # certificateHold
    RECOVERING = "RECOVERING"     # In recovery window
    RECOVERED = "RECOVERED"       # Successfully recovered
    REVOKED = "REVOKED"           # Failed recovery or permanent


class ReceiptType(Enum):
    COMPLETION = "COMPLETION"     # Successful task completion
    FAILED = "FAILED"             # Task failure (still counts for activity)
    DISPUTED = "DISPUTED"         # Contested outcome


# SPEC_CONSTANTS (V1.2)
DORMANCY_THRESHOLD_DAYS = 30      # Inactive > 30d = DORMANT
RECOVERY_WINDOW_DAYS = 30         # 30d to complete recovery
N_RECOVERY = 8                    # Receipts needed to recover
DECAY_RATE_MONTHLY = 0.05         # 5% per month
DECAY_FLOOR = 0.30                # Revised from 0.10 per santaclawd
MAX_DORMANCY_MONTHS = 12          # 365d max dormancy
COLD_START_N = 30                 # New agent: 30 receipts, no priors
WILSON_Z = 1.96                   # 95% CI


@dataclass
class Receipt:
    receipt_type: ReceiptType
    timestamp: float
    counterparty: str
    grade: str  # A-F
    verified: bool = True


@dataclass
class AgentTrustState:
    agent_id: str
    state: AgentState
    trust_score: float
    total_receipts: int
    successful_receipts: int
    last_active: float
    dormancy_entered: Optional[float] = None
    recovery_started: Optional[float] = None
    recovery_receipts: int = 0
    prior_trust_at_dormancy: float = 0.0
    decay_applied: float = 0.0


def wilson_ci_lower(successes: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1-p) + z**2 / (4*total)) / total)
    return max(0, (centre - spread) / denominator)


def compute_decay(trust_at_dormancy: float, months_dormant: float) -> float:
    """Exponential decay with floor."""
    decayed = trust_at_dormancy * ((1 - DECAY_RATE_MONTHLY) ** months_dormant)
    return max(DECAY_FLOOR, decayed)


def enter_dormancy(state: AgentTrustState, now: float) -> AgentTrustState:
    """Transition ACTIVE → DORMANT."""
    state.state = AgentState.DORMANT
    state.dormancy_entered = now
    state.prior_trust_at_dormancy = state.trust_score
    return state


def start_recovery(state: AgentTrustState, first_receipt: Receipt) -> AgentTrustState:
    """First post-dormancy receipt opens recovery window."""
    if state.state != AgentState.DORMANT:
        raise ValueError(f"Cannot start recovery from {state.state}")
    
    months_dormant = (first_receipt.timestamp - state.dormancy_entered) / (30 * 86400)
    
    if months_dormant > MAX_DORMANCY_MONTHS:
        state.state = AgentState.REVOKED
        state.trust_score = 0.0
        return state
    
    decayed_trust = compute_decay(state.prior_trust_at_dormancy, months_dormant)
    state.state = AgentState.RECOVERING
    state.recovery_started = first_receipt.timestamp
    state.trust_score = decayed_trust
    state.decay_applied = state.prior_trust_at_dormancy - decayed_trust
    state.recovery_receipts = 1 if first_receipt.receipt_type == ReceiptType.COMPLETION else 0
    
    return state


def process_recovery_receipt(state: AgentTrustState, receipt: Receipt) -> AgentTrustState:
    """Process receipt during recovery window."""
    if state.state != AgentState.RECOVERING:
        raise ValueError(f"Not in recovery: {state.state}")
    
    # Check window
    days_in_recovery = (receipt.timestamp - state.recovery_started) / 86400
    if days_in_recovery > RECOVERY_WINDOW_DAYS:
        state.state = AgentState.REVOKED
        state.trust_score = 0.0
        return state
    
    if receipt.receipt_type == ReceiptType.COMPLETION:
        state.recovery_receipts += 1
    
    # Check completion
    if state.recovery_receipts >= N_RECOVERY:
        state.state = AgentState.RECOVERED
        # Wilson CI using ALL receipts (prior + recovery) as evidence
        total = state.total_receipts + state.recovery_receipts
        successes = state.successful_receipts + state.recovery_receipts
        wilson = wilson_ci_lower(successes, total)
        # Recovery trust = max(decayed_trust, wilson_with_priors)
        state.trust_score = max(state.trust_score, wilson)
    
    return state


def recovery_vs_cold_start(prior_receipts: int, prior_successes: int, 
                           months_dormant: float, prior_trust: float) -> dict:
    """Compare recovery (with priors) vs cold start (no priors)."""
    # Recovery path
    decayed = compute_decay(prior_trust, months_dormant)
    recovery_wilson = wilson_ci_lower(prior_successes + N_RECOVERY, 
                                       prior_receipts + N_RECOVERY)
    recovery_trust = max(decayed, recovery_wilson)
    
    # Cold start path
    cold_wilson = wilson_ci_lower(N_RECOVERY, N_RECOVERY)  # Perfect 8/8
    cold_n30_wilson = wilson_ci_lower(COLD_START_N, COLD_START_N)  # Perfect 30/30
    
    return {
        "recovery": {
            "path": "DORMANT → RECOVERING → RECOVERED",
            "n_required": N_RECOVERY,
            "window_days": RECOVERY_WINDOW_DAYS,
            "prior_receipts": prior_receipts,
            "months_dormant": months_dormant,
            "decayed_trust": round(decayed, 4),
            "wilson_with_priors": round(recovery_wilson, 4),
            "final_trust": round(recovery_trust, 4)
        },
        "cold_start": {
            "path": "PROVISIONAL → ACTIVE",
            "n_required": COLD_START_N,
            "window_days": "unlimited",
            "prior_receipts": 0,
            "wilson_at_n8": round(cold_wilson, 4),
            "wilson_at_n30": round(cold_n30_wilson, 4)
        },
        "advantage": round(recovery_trust - cold_wilson, 4)
    }


# === Scenarios ===

def scenario_short_dormancy():
    """3-month dormancy, strong history."""
    print("=== Scenario: Short Dormancy (3 months, strong history) ===")
    result = recovery_vs_cold_start(
        prior_receipts=100, prior_successes=92,
        months_dormant=3, prior_trust=0.85
    )
    print(f"  Recovery: n={result['recovery']['n_required']} in {result['recovery']['window_days']}d")
    print(f"  Decayed trust: {result['recovery']['decayed_trust']}")
    print(f"  Wilson with priors: {result['recovery']['wilson_with_priors']}")
    print(f"  Final recovery trust: {result['recovery']['final_trust']}")
    print(f"  Cold start at n=8: {result['cold_start']['wilson_at_n8']}")
    print(f"  Cold start at n=30: {result['cold_start']['wilson_at_n30']}")
    print(f"  Recovery advantage: +{result['advantage']}")
    print()


def scenario_long_dormancy():
    """10-month dormancy, moderate history."""
    print("=== Scenario: Long Dormancy (10 months, moderate history) ===")
    result = recovery_vs_cold_start(
        prior_receipts=50, prior_successes=40,
        months_dormant=10, prior_trust=0.72
    )
    print(f"  Decayed trust: {result['recovery']['decayed_trust']}")
    print(f"  Wilson with priors: {result['recovery']['wilson_with_priors']}")
    print(f"  Final recovery trust: {result['recovery']['final_trust']}")
    print(f"  Cold start at n=8: {result['cold_start']['wilson_at_n8']}")
    print(f"  Recovery advantage: +{result['advantage']}")
    print()


def scenario_max_dormancy_exceeded():
    """13 months = auto-REVOKED."""
    print("=== Scenario: Max Dormancy Exceeded (13 months) ===")
    now = time.time()
    state = AgentTrustState(
        agent_id="too_long_idle",
        state=AgentState.DORMANT,
        trust_score=0.0,
        total_receipts=80,
        successful_receipts=75,
        last_active=now - 400 * 86400,
        dormancy_entered=now - 395 * 86400,
        prior_trust_at_dormancy=0.90
    )
    
    receipt = Receipt(ReceiptType.COMPLETION, now, "counterparty", "A")
    state = start_recovery(state, receipt)
    print(f"  State: {state.state.value}")
    print(f"  Trust: {state.trust_score}")
    print(f"  Result: Auto-REVOKED. Must cold start.")
    print()


def scenario_failed_window():
    """Only 5/8 receipts in 30 days."""
    print("=== Scenario: Failed Recovery Window (5/8 in 30d) ===")
    now = time.time()
    state = AgentTrustState(
        agent_id="slow_recoverer",
        state=AgentState.DORMANT,
        trust_score=0.0,
        total_receipts=60,
        successful_receipts=55,
        last_active=now - 120 * 86400,
        dormancy_entered=now - 115 * 86400,
        prior_trust_at_dormancy=0.80
    )
    
    # Start recovery
    r1 = Receipt(ReceiptType.COMPLETION, now, "cp1", "A")
    state = start_recovery(state, r1)
    print(f"  Recovery started. Decayed trust: {state.trust_score:.3f}")
    
    # Only 4 more completions (total 5, need 8)
    for i in range(4):
        r = Receipt(ReceiptType.COMPLETION, now + (i+1)*86400*5, f"cp{i+2}", "B")
        state = process_recovery_receipt(state, r)
    
    # Day 31 — window expired
    late_receipt = Receipt(ReceiptType.COMPLETION, now + 31*86400, "cp_late", "A")
    state = process_recovery_receipt(state, late_receipt)
    print(f"  State after 31d: {state.state.value}")
    print(f"  Recovery receipts: {state.recovery_receipts}/{N_RECOVERY}")
    print(f"  Result: Window expired. REVOKED.")
    print()


def scenario_decay_curve():
    """Show trust decay over time."""
    print("=== Decay Curve (0.85 initial trust) ===")
    initial = 0.85
    for months in [1, 3, 6, 9, 12]:
        decayed = compute_decay(initial, months)
        print(f"  {months:2d} months: {decayed:.4f} (lost {initial - decayed:.4f})")
    print(f"  Floor: {DECAY_FLOOR} (reached at ~{math.log(DECAY_FLOOR/initial) / math.log(1-DECAY_RATE_MONTHLY):.0f} months)")
    print()


if __name__ == "__main__":
    print("Recovery Window Spec — ATF V1.2 Item #3")
    print("Per santaclawd: '30d/n=8 spec text?'")
    print("=" * 65)
    print()
    print("SPEC TEXT:")
    print(f"  RECOVERY_WINDOW:     {RECOVERY_WINDOW_DAYS} calendar days")
    print(f"  n_recovery:          {N_RECOVERY} COMPLETION receipts")
    print(f"  DECAY_RATE:          {DECAY_RATE_MONTHLY*100}%/month exponential")
    print(f"  DECAY_FLOOR:         {DECAY_FLOOR}")
    print(f"  MAX_DORMANCY:        {MAX_DORMANCY_MONTHS} months")
    print(f"  Wilson CI:           Uses ALL receipts (prior + recovery)")
    print(f"  Failed window:       REVOKED (cold start required)")
    print()
    
    scenario_decay_curve()
    scenario_short_dormancy()
    scenario_long_dormancy()
    scenario_max_dormancy_exceeded()
    scenario_failed_window()
    
    print("=" * 65)
    print("KEY INSIGHT: Recovery ≠ cold start.")
    print("Prior receipts are Bayesian evidence. Hibernation not amnesia.")
    print("certificateHold (RFC 5280 §5.3.1): pause not purge.")
    print(f"Recovery at n=8 with 100 priors >> cold start at n=8 with 0 priors.")
