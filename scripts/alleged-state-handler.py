#!/usr/bin/env python3
"""
alleged-state-handler.py — ALLEGED as 5th receipt state for ATF amendments.

Per santaclawd: timeout should not collapse to REJECTED. ALLEGED ≠ REJECTED.
OCSP parallel (RFC 6960 §2.2): good/revoked/unknown — unknown is NOT revoked.

Five states:
  PROPOSED   — Amendment submitted, awaiting payer signature
  CONFIRMED  — Payer signed (bilateral agreement)
  DISPUTED   — Grader adjudicates against scope
  REJECTED   — Explicit rejection by payer
  ALLEGED    — T_sign expired, payer silent (NEW)

ALLEGED has disputable weight: weaker than CONFIRMED, stronger than REJECTED.
Time-weighted decay: ALLEGED scope degrades over time but never auto-REJECTs.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AmendmentState(Enum):
    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    DISPUTED = "DISPUTED"
    REJECTED = "REJECTED"
    ALLEGED = "ALLEGED"


class TransitionType(Enum):
    PAYER_SIGN = "payer_sign"           # PROPOSED → CONFIRMED
    PAYER_REJECT = "payer_reject"       # PROPOSED → REJECTED
    T_SIGN_EXPIRED = "t_sign_expired"   # PROPOSED → ALLEGED
    LATE_SIGN = "late_sign"             # ALLEGED → CONFIRMED
    GRADER_DISPUTE = "grader_dispute"   # ALLEGED → DISPUTED
    DECAY_TIMEOUT = "decay_timeout"     # ALLEGED stays ALLEGED (weight decays)


# SPEC_CONSTANTS
T_SIGN_DEFAULT = 24 * 3600       # 24h default signing window
T_LATE_SIGN_MAX = 72 * 3600      # 72h max for late signing
ALLEGED_HALF_LIFE = 30 * 86400   # 30-day half-life for weight decay
ALLEGED_WEIGHT_FLOOR = 0.1       # Never decays below 0.1
CONFIRMED_WEIGHT = 1.0
REJECTED_WEIGHT = 0.0
PROPOSED_WEIGHT = 0.5


@dataclass
class Amendment:
    amendment_id: str
    scope_hash: str
    proposer: str
    payer: str
    state: AmendmentState = AmendmentState.PROPOSED
    proposed_at: float = 0.0
    t_sign: float = T_SIGN_DEFAULT
    signed_at: Optional[float] = None
    alleged_at: Optional[float] = None
    resolved_at: Optional[float] = None
    weight: float = PROPOSED_WEIGHT
    transitions: list = field(default_factory=list)


def compute_alleged_weight(alleged_at: float, now: float) -> float:
    """
    Time-weighted decay for ALLEGED state.
    
    ALLEGED starts at 0.7 (weaker than CONFIRMED=1.0, stronger than REJECTED=0.0).
    Decays with 30-day half-life. Never drops below ALLEGED_WEIGHT_FLOOR.
    
    This matches OCSP "unknown" — it's not revoked, but certainty decreases with time.
    """
    initial_weight = 0.7
    age_seconds = now - alleged_at
    half_lives = age_seconds / ALLEGED_HALF_LIFE
    decayed = initial_weight * (0.5 ** half_lives)
    return max(decayed, ALLEGED_WEIGHT_FLOOR)


def transition(amendment: Amendment, transition_type: TransitionType, now: float) -> dict:
    """Apply state transition and return result."""
    old_state = amendment.state
    result = {"valid": False, "old_state": old_state.value, "new_state": None, "reason": ""}
    
    if transition_type == TransitionType.PAYER_SIGN:
        if amendment.state == AmendmentState.PROPOSED:
            amendment.state = AmendmentState.CONFIRMED
            amendment.signed_at = now
            amendment.weight = CONFIRMED_WEIGHT
            result["valid"] = True
            result["reason"] = "Payer signed within T_sign window"
        elif amendment.state == AmendmentState.ALLEGED:
            # Late sign — check if within T_LATE_SIGN_MAX
            if amendment.alleged_at and (now - amendment.alleged_at) <= T_LATE_SIGN_MAX:
                amendment.state = AmendmentState.CONFIRMED
                amendment.signed_at = now
                amendment.weight = CONFIRMED_WEIGHT
                result["valid"] = True
                result["reason"] = f"Late sign accepted ({(now - amendment.alleged_at)/3600:.1f}h after ALLEGED)"
            else:
                result["reason"] = f"Late sign rejected: {(now - amendment.alleged_at)/3600:.1f}h > {T_LATE_SIGN_MAX/3600}h max"
        else:
            result["reason"] = f"Cannot sign from state {old_state.value}"
    
    elif transition_type == TransitionType.PAYER_REJECT:
        if amendment.state in (AmendmentState.PROPOSED, AmendmentState.ALLEGED):
            amendment.state = AmendmentState.REJECTED
            amendment.resolved_at = now
            amendment.weight = REJECTED_WEIGHT
            result["valid"] = True
            result["reason"] = "Payer explicitly rejected"
    
    elif transition_type == TransitionType.T_SIGN_EXPIRED:
        if amendment.state == AmendmentState.PROPOSED:
            if now - amendment.proposed_at >= amendment.t_sign:
                amendment.state = AmendmentState.ALLEGED
                amendment.alleged_at = now
                amendment.weight = 0.7  # Initial ALLEGED weight
                result["valid"] = True
                result["reason"] = f"T_sign expired after {amendment.t_sign/3600:.0f}h — state is ALLEGED not REJECTED"
            else:
                remaining = (amendment.proposed_at + amendment.t_sign - now) / 3600
                result["reason"] = f"T_sign not yet expired ({remaining:.1f}h remaining)"
    
    elif transition_type == TransitionType.GRADER_DISPUTE:
        if amendment.state == AmendmentState.ALLEGED:
            amendment.state = AmendmentState.DISPUTED
            amendment.resolved_at = now
            amendment.weight = 0.0
            result["valid"] = True
            result["reason"] = "Grader adjudicates against alleged scope"
    
    elif transition_type == TransitionType.DECAY_TIMEOUT:
        if amendment.state == AmendmentState.ALLEGED:
            amendment.weight = compute_alleged_weight(amendment.alleged_at, now)
            result["valid"] = True
            result["reason"] = f"ALLEGED weight decayed to {amendment.weight:.3f}"
    
    if result["valid"]:
        result["new_state"] = amendment.state.value
        amendment.transitions.append({
            "type": transition_type.value,
            "from": old_state.value,
            "to": amendment.state.value,
            "timestamp": now,
            "weight": amendment.weight
        })
    
    return result


def compare_state_models() -> dict:
    """Compare 4-state (old) vs 5-state (new) model."""
    now = time.time()
    
    # Same scenario: payer goes silent after T_sign
    old_model = {"name": "4-state (collapse)", "timeout_result": "REJECTED", "weight": 0.0,
                 "late_sign_possible": False, "information_preserved": False}
    
    new_model = {"name": "5-state (ALLEGED)", "timeout_result": "ALLEGED", "weight": 0.7,
                 "late_sign_possible": True, "information_preserved": True,
                 "weight_at_30d": compute_alleged_weight(now, now + 30*86400),
                 "weight_at_90d": compute_alleged_weight(now, now + 90*86400)}
    
    return {"old": old_model, "new": new_model}


# === Scenarios ===

def scenario_normal_flow():
    """Happy path: PROPOSED → CONFIRMED."""
    print("=== Scenario: Normal Flow ===")
    now = time.time()
    a = Amendment("amend_001", "scope_abc", "kit_fox", "bro_agent", proposed_at=now)
    
    result = transition(a, TransitionType.PAYER_SIGN, now + 3600)
    print(f"  {result['old_state']} → {result['new_state']}: {result['reason']}")
    print(f"  Weight: {a.weight}")
    print()


def scenario_alleged_then_late_sign():
    """PROPOSED → ALLEGED → CONFIRMED (late sign within 72h)."""
    print("=== Scenario: ALLEGED → Late Sign ===")
    now = time.time()
    a = Amendment("amend_002", "scope_def", "kit_fox", "bro_agent", proposed_at=now)
    
    # T_sign expires
    r1 = transition(a, TransitionType.T_SIGN_EXPIRED, now + T_SIGN_DEFAULT + 1)
    print(f"  {r1['old_state']} → {r1['new_state']}: {r1['reason']}")
    print(f"  Weight: {a.weight}")
    
    # Payer signs late (48h after ALLEGED)
    r2 = transition(a, TransitionType.PAYER_SIGN, now + T_SIGN_DEFAULT + 48*3600)
    print(f"  {r2['old_state']} → {r2['new_state']}: {r2['reason']}")
    print(f"  Weight: {a.weight}")
    print()


def scenario_alleged_decay():
    """ALLEGED weight decays over time."""
    print("=== Scenario: ALLEGED Weight Decay ===")
    now = time.time()
    a = Amendment("amend_003", "scope_ghi", "kit_fox", "silent_agent", proposed_at=now)
    
    transition(a, TransitionType.T_SIGN_EXPIRED, now + T_SIGN_DEFAULT + 1)
    
    for days in [0, 7, 30, 60, 90, 180]:
        weight = compute_alleged_weight(a.alleged_at, a.alleged_at + days * 86400)
        print(f"  Day {days:3d}: weight={weight:.4f}")
    
    print(f"  Floor: {ALLEGED_WEIGHT_FLOOR} (never reaches 0)")
    print()


def scenario_alleged_grader_dispute():
    """ALLEGED → DISPUTED by grader adjudication."""
    print("=== Scenario: ALLEGED → DISPUTED ===")
    now = time.time()
    a = Amendment("amend_004", "scope_jkl", "kit_fox", "adversary", proposed_at=now)
    
    r1 = transition(a, TransitionType.T_SIGN_EXPIRED, now + T_SIGN_DEFAULT + 1)
    print(f"  {r1['old_state']} → {r1['new_state']}: {r1['reason']}")
    
    r2 = transition(a, TransitionType.GRADER_DISPUTE, now + T_SIGN_DEFAULT + 7*3600)
    print(f"  {r2['old_state']} → {r2['new_state']}: {r2['reason']}")
    print(f"  Weight: {a.weight}")
    print()


def scenario_model_comparison():
    """Compare 4-state vs 5-state model."""
    print("=== Scenario: Model Comparison ===")
    comparison = compare_state_models()
    
    for model_name, model in comparison.items():
        print(f"  {model['name']}:")
        print(f"    Timeout result: {model['timeout_result']}")
        print(f"    Weight: {model['weight']}")
        print(f"    Late sign possible: {model['late_sign_possible']}")
        print(f"    Information preserved: {model['information_preserved']}")
        if 'weight_at_30d' in model:
            print(f"    Weight at 30d: {model['weight_at_30d']:.4f}")
            print(f"    Weight at 90d: {model['weight_at_90d']:.4f}")
    print()


def scenario_late_sign_too_late():
    """Late sign after T_LATE_SIGN_MAX — rejected."""
    print("=== Scenario: Late Sign Too Late ===")
    now = time.time()
    a = Amendment("amend_005", "scope_mno", "kit_fox", "slow_agent", proposed_at=now)
    
    transition(a, TransitionType.T_SIGN_EXPIRED, now + T_SIGN_DEFAULT + 1)
    
    # Try signing 96h after ALLEGED (beyond 72h max)
    r = transition(a, TransitionType.PAYER_SIGN, now + T_SIGN_DEFAULT + 96*3600)
    print(f"  Late sign attempt 96h after ALLEGED: valid={r['valid']}")
    print(f"  Reason: {r['reason']}")
    print(f"  State remains: {a.state.value}")
    print()


if __name__ == "__main__":
    print("Alleged State Handler — 5th Receipt State for ATF Amendments")
    print("Per santaclawd: ALLEGED ≠ REJECTED. OCSP unknown ≠ revoked (RFC 6960)")
    print("=" * 70)
    print()
    
    scenario_normal_flow()
    scenario_alleged_then_late_sign()
    scenario_alleged_decay()
    scenario_alleged_grader_dispute()
    scenario_model_comparison()
    scenario_late_sign_too_late()
    
    print("=" * 70)
    print("KEY INSIGHT: Silence is information, not absence.")
    print("ALLEGED preserves late-sign upgrade path.")
    print("Time-weighted decay (30d half-life) reflects uncertainty without")
    print("collapsing to REJECTED. OCSP 'unknown' is the exact parallel.")
