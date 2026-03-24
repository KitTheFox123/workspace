#!/usr/bin/env python3
"""
alleged-state-handler.py — ALLEGED receipt state for ATF amendment lifecycle.

Per santaclawd: ALLEGED ≠ REJECTED. Timeout silence ≠ explicit refusal.
Per RFC 6960 OCSP: good/revoked/unknown are three distinct states.

Five-state amendment lifecycle:
  PROPOSED   → initial, awaiting payer signature
  CONFIRMED  → payer signed within T_sign window
  ALLEGED    → T_sign expired, payer silent (NOT rejected!)
  DISPUTED   → explicit disagreement from either party
  REJECTED   → adjudicated against (terminal)

Key insight: ALLEGED scope has disputable weight (0.5x) in resolution.
Late payer sign can upgrade ALLEGED → CONFIRMED retroactively.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AmendmentState(Enum):
    PROPOSED = "PROPOSED"       # Awaiting payer signature
    CONFIRMED = "CONFIRMED"     # Bilateral agreement
    ALLEGED = "ALLEGED"         # Timeout, payer silent
    DISPUTED = "DISPUTED"       # Explicit disagreement
    REJECTED = "REJECTED"       # Terminal, adjudicated against


class TransitionReason(Enum):
    PAYER_SIGNED = "payer_signed"
    T_SIGN_EXPIRED = "t_sign_expired"
    PAYER_DISPUTES = "payer_disputes"
    GRADER_ADJUDICATES = "grader_adjudicates"
    LATE_SIGN = "late_sign"           # ALLEGED → CONFIRMED
    WITHDRAWAL = "withdrawal"         # Proposer withdraws


# SPEC_CONSTANTS
T_SIGN_DEFAULT_HOURS = 24        # Default signing window
T_SIGN_MAX_HOURS = 72            # Maximum allowed
T_SIGN_MIN_HOURS = 4             # Minimum (prevent instant timeout)
ALLEGED_WEIGHT = 0.5             # Dispute resolution weight for ALLEGED scope
CONFIRMED_WEIGHT = 1.0           # Full weight
PROPOSED_WEIGHT = 0.0            # No weight until signed/alleged
LATE_SIGN_WINDOW_HOURS = 168     # 7 days to late-sign an ALLEGED receipt
ALLEGED_DECAY_DAYS = 90          # After 90d, ALLEGED auto-expires


@dataclass
class Amendment:
    amendment_id: str
    scope_hash: str
    proposer_id: str
    payer_id: str
    grader_id: str
    state: AmendmentState = AmendmentState.PROPOSED
    proposed_at: float = 0.0
    t_sign_hours: float = T_SIGN_DEFAULT_HOURS
    signed_at: Optional[float] = None
    alleged_at: Optional[float] = None
    disputed_at: Optional[float] = None
    resolved_at: Optional[float] = None
    transition_log: list = field(default_factory=list)
    dispute_weight: float = 0.0


@dataclass
class Transition:
    from_state: str
    to_state: str
    reason: str
    timestamp: float
    actor: str
    receipt_hash: str = ""


def compute_receipt_hash(amendment: Amendment, state: str, timestamp: float) -> str:
    """Deterministic receipt hash for state transition."""
    data = f"{amendment.amendment_id}:{state}:{timestamp}:{amendment.scope_hash}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def transition(amendment: Amendment, new_state: AmendmentState, 
               reason: TransitionReason, actor: str) -> dict:
    """Execute state transition with validation."""
    now = time.time()
    old_state = amendment.state
    
    # Validate transition
    valid_transitions = {
        AmendmentState.PROPOSED: {AmendmentState.CONFIRMED, AmendmentState.ALLEGED, 
                                   AmendmentState.DISPUTED},
        AmendmentState.ALLEGED: {AmendmentState.CONFIRMED, AmendmentState.DISPUTED,
                                  AmendmentState.REJECTED},
        AmendmentState.CONFIRMED: {AmendmentState.DISPUTED},
        AmendmentState.DISPUTED: {AmendmentState.CONFIRMED, AmendmentState.REJECTED},
        AmendmentState.REJECTED: set()  # Terminal
    }
    
    if new_state not in valid_transitions.get(old_state, set()):
        return {
            "success": False,
            "error": f"Invalid transition: {old_state.value} → {new_state.value}",
            "valid_targets": [s.value for s in valid_transitions.get(old_state, set())]
        }
    
    # Additional validation
    if new_state == AmendmentState.ALLEGED and reason == TransitionReason.T_SIGN_EXPIRED:
        elapsed_hours = (now - amendment.proposed_at) / 3600
        if elapsed_hours < amendment.t_sign_hours:
            return {
                "success": False,
                "error": f"T_sign not yet expired ({elapsed_hours:.1f}h < {amendment.t_sign_hours}h)"
            }
    
    if new_state == AmendmentState.CONFIRMED and old_state == AmendmentState.ALLEGED:
        # Late sign — check within window
        if amendment.alleged_at:
            late_hours = (now - amendment.alleged_at) / 3600
            if late_hours > LATE_SIGN_WINDOW_HOURS:
                return {
                    "success": False,
                    "error": f"Late sign window expired ({late_hours:.1f}h > {LATE_SIGN_WINDOW_HOURS}h)"
                }
    
    # Execute transition
    receipt_hash = compute_receipt_hash(amendment, new_state.value, now)
    
    t = Transition(
        from_state=old_state.value,
        to_state=new_state.value,
        reason=reason.value,
        timestamp=now,
        actor=actor,
        receipt_hash=receipt_hash
    )
    amendment.transition_log.append(t)
    amendment.state = new_state
    
    # Update timestamps
    if new_state == AmendmentState.CONFIRMED:
        amendment.signed_at = now
        amendment.dispute_weight = CONFIRMED_WEIGHT
    elif new_state == AmendmentState.ALLEGED:
        amendment.alleged_at = now
        amendment.dispute_weight = ALLEGED_WEIGHT
    elif new_state == AmendmentState.DISPUTED:
        amendment.disputed_at = now
    elif new_state == AmendmentState.REJECTED:
        amendment.resolved_at = now
        amendment.dispute_weight = 0.0
    
    return {
        "success": True,
        "transition": f"{old_state.value} → {new_state.value}",
        "reason": reason.value,
        "receipt_hash": receipt_hash,
        "dispute_weight": amendment.dispute_weight
    }


def compute_dispute_resolution(amendments: list[Amendment]) -> dict:
    """Resolve dispute using weighted amendment states.
    
    CONFIRMED = 1.0x weight, ALLEGED = 0.5x weight.
    Per OCSP: unknown ≠ revoked, but carries information.
    """
    total_weight = 0.0
    confirmed_weight = 0.0
    alleged_weight = 0.0
    
    for a in amendments:
        if a.state == AmendmentState.CONFIRMED:
            confirmed_weight += CONFIRMED_WEIGHT
            total_weight += CONFIRMED_WEIGHT
        elif a.state == AmendmentState.ALLEGED:
            alleged_weight += ALLEGED_WEIGHT
            total_weight += ALLEGED_WEIGHT
    
    confirmed_ratio = confirmed_weight / total_weight if total_weight > 0 else 0
    
    return {
        "total_amendments": len(amendments),
        "confirmed_count": sum(1 for a in amendments if a.state == AmendmentState.CONFIRMED),
        "alleged_count": sum(1 for a in amendments if a.state == AmendmentState.ALLEGED),
        "disputed_count": sum(1 for a in amendments if a.state == AmendmentState.DISPUTED),
        "total_weight": round(total_weight, 2),
        "confirmed_weight": round(confirmed_weight, 2),
        "alleged_weight": round(alleged_weight, 2),
        "confirmed_ratio": round(confirmed_ratio, 3),
        "resolution": "UPHELD" if confirmed_ratio >= 0.6 else "CONTESTED" if confirmed_ratio >= 0.4 else "OVERTURNED"
    }


# === Scenarios ===

def scenario_normal_lifecycle():
    """Standard: PROPOSED → CONFIRMED."""
    print("=== Scenario: Normal Lifecycle ===")
    a = Amendment("amend_001", "scope_abc", "kit_fox", "bro_agent", "grader_1",
                  proposed_at=time.time() - 86400)
    
    result = transition(a, AmendmentState.CONFIRMED, TransitionReason.PAYER_SIGNED, "bro_agent")
    print(f"  PROPOSED → CONFIRMED: {result['success']}")
    print(f"  Weight: {result['dispute_weight']}")
    print(f"  Receipt: {result['receipt_hash']}")
    print()


def scenario_alleged_timeout():
    """Payer silent → ALLEGED, then late sign → CONFIRMED."""
    print("=== Scenario: ALLEGED → Late Sign → CONFIRMED ===")
    a = Amendment("amend_002", "scope_def", "kit_fox", "silent_payer", "grader_1",
                  proposed_at=time.time() - 100000)  # Well past T_sign
    
    result1 = transition(a, AmendmentState.ALLEGED, TransitionReason.T_SIGN_EXPIRED, "system")
    print(f"  PROPOSED → ALLEGED: {result1['success']}")
    print(f"  Weight: {result1['dispute_weight']} (reduced)")
    
    result2 = transition(a, AmendmentState.CONFIRMED, TransitionReason.LATE_SIGN, "silent_payer")
    print(f"  ALLEGED → CONFIRMED (late sign): {result2['success']}")
    print(f"  Weight: {result2['dispute_weight']} (restored)")
    print()


def scenario_alleged_to_disputed():
    """ALLEGED scope gets disputed by grader."""
    print("=== Scenario: ALLEGED → DISPUTED → REJECTED ===")
    a = Amendment("amend_003", "scope_ghi", "kit_fox", "bad_payer", "grader_1",
                  proposed_at=time.time() - 200000)
    
    r1 = transition(a, AmendmentState.ALLEGED, TransitionReason.T_SIGN_EXPIRED, "system")
    print(f"  PROPOSED → ALLEGED: {r1['success']}")
    
    r2 = transition(a, AmendmentState.DISPUTED, TransitionReason.GRADER_ADJUDICATES, "grader_1")
    print(f"  ALLEGED → DISPUTED: {r2['success']}")
    
    r3 = transition(a, AmendmentState.REJECTED, TransitionReason.GRADER_ADJUDICATES, "grader_1")
    print(f"  DISPUTED → REJECTED: {r3['success']}")
    print(f"  Terminal weight: {a.dispute_weight}")
    print()


def scenario_dispute_resolution_mixed():
    """Mixed CONFIRMED + ALLEGED amendments in dispute."""
    print("=== Scenario: Mixed Dispute Resolution ===")
    now = time.time()
    
    amendments = []
    # 3 confirmed milestones
    for i in range(3):
        a = Amendment(f"m_{i}", f"scope_{i}", "kit_fox", "payer", "grader",
                      proposed_at=now-86400, state=AmendmentState.CONFIRMED,
                      dispute_weight=CONFIRMED_WEIGHT)
        amendments.append(a)
    
    # 2 alleged milestones (payer went silent)
    for i in range(3, 5):
        a = Amendment(f"m_{i}", f"scope_{i}", "kit_fox", "payer", "grader",
                      proposed_at=now-86400, state=AmendmentState.ALLEGED,
                      dispute_weight=ALLEGED_WEIGHT)
        amendments.append(a)
    
    result = compute_dispute_resolution(amendments)
    print(f"  Confirmed: {result['confirmed_count']} ({result['confirmed_weight']}w)")
    print(f"  Alleged: {result['alleged_count']} ({result['alleged_weight']}w)")
    print(f"  Total weight: {result['total_weight']}")
    print(f"  Confirmed ratio: {result['confirmed_ratio']}")
    print(f"  Resolution: {result['resolution']}")
    print(f"  (OCSP parallel: unknown ≠ revoked, but carries reduced information)")
    print()


def scenario_invalid_transition():
    """Try invalid transition — REJECTED is terminal."""
    print("=== Scenario: Invalid Transition (Terminal State) ===")
    a = Amendment("amend_004", "scope_jkl", "kit_fox", "payer", "grader",
                  state=AmendmentState.REJECTED)
    
    result = transition(a, AmendmentState.CONFIRMED, TransitionReason.PAYER_SIGNED, "payer")
    print(f"  REJECTED → CONFIRMED: {result['success']}")
    print(f"  Error: {result.get('error', 'none')}")
    print(f"  Valid targets: {result.get('valid_targets', [])}")
    print()


if __name__ == "__main__":
    print("ALLEGED State Handler — Five-State Amendment Lifecycle for ATF")
    print("Per santaclawd + RFC 6960 OCSP (good/revoked/unknown)")
    print("=" * 70)
    print()
    print("States: PROPOSED → CONFIRMED | ALLEGED | DISPUTED → REJECTED")
    print(f"  CONFIRMED weight: {CONFIRMED_WEIGHT}x")
    print(f"  ALLEGED weight:   {ALLEGED_WEIGHT}x (reduced but non-zero)")
    print(f"  T_sign default:   {T_SIGN_DEFAULT_HOURS}h")
    print(f"  Late sign window: {LATE_SIGN_WINDOW_HOURS}h")
    print()
    
    scenario_normal_lifecycle()
    scenario_alleged_timeout()
    scenario_alleged_to_disputed()
    scenario_dispute_resolution_mixed()
    scenario_invalid_transition()
    
    print("=" * 70)
    print("KEY: ALLEGED ≠ REJECTED. Silence ≠ refusal.")
    print("OCSP 'unknown' carries information — insufficient, not negative.")
    print("Late sign preserves bilateral trust. Timeout is state, not verdict.")
