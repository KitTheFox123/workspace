#!/usr/bin/env python3
"""
alleged-state-machine.py — Five-state receipt lifecycle for ATF.

Per santaclawd: collapsing timeout into REJECTED loses information.
RFC 6960 OCSP defines: good / revoked / unknown. unknown ≠ revoked.

Five states:
  PROPOSED    — Receipt created, awaiting counterparty signature
  CONFIRMED   — Bilateral co-sign within T_sign
  ALLEGED     — T_sign expired, payer silent (NEW — not REJECTED)
  DISPUTED    — Explicit rejection with evidence
  EXPIRED     — TTL exceeded, no longer actionable

ALLEGED has disputable weight: weaker than CONFIRMED, stronger than absent.
Grader CAN adjudicate ALLEGED scope if behavioral evidence exists.
ALLEGED + evidence = upgradeable to CONFIRMED.
ALLEGED + silence beyond T_decay = EXPIRED.

Key insight: silence is NOT rejection. It is ambiguity.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ReceiptState(Enum):
    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    ALLEGED = "ALLEGED"
    DISPUTED = "DISPUTED"
    EXPIRED = "EXPIRED"


class TransitionReason(Enum):
    CO_SIGN = "co_sign"
    TIMEOUT = "timeout"
    EXPLICIT_REJECT = "explicit_reject"
    LATE_SIGN = "late_sign"
    EVIDENCE_UPGRADE = "evidence_upgrade"
    TTL_EXCEEDED = "ttl_exceeded"
    GRADER_ADJUDICATION = "grader_adjudication"


# SPEC_CONSTANTS
T_SIGN_SECONDS = 86400       # 24h co-sign window
T_DECAY_SECONDS = 604800     # 7d from ALLEGED → EXPIRED
T_DISPUTE_SECONDS = 259200   # 72h dispute window after ALLEGED
ALLEGED_WEIGHT = 0.5         # Weight relative to CONFIRMED (1.0)
DISPUTED_WEIGHT = 0.0        # No trust weight
EXPIRED_WEIGHT = 0.0         # No trust weight


@dataclass
class Receipt:
    receipt_id: str
    proposer: str
    counterparty: str
    scope_hash: str
    evidence_grade: str
    state: ReceiptState = ReceiptState.PROPOSED
    proposed_at: float = 0.0
    confirmed_at: Optional[float] = None
    alleged_at: Optional[float] = None
    disputed_at: Optional[float] = None
    expired_at: Optional[float] = None
    dispute_evidence: Optional[str] = None
    transition_log: list = field(default_factory=list)
    
    def log_transition(self, from_state: ReceiptState, to_state: ReceiptState, 
                       reason: TransitionReason, timestamp: float):
        entry = {
            "from": from_state.value,
            "to": to_state.value,
            "reason": reason.value,
            "timestamp": timestamp,
            "hash": hashlib.sha256(
                f"{self.receipt_id}:{from_state.value}:{to_state.value}:{timestamp}".encode()
            ).hexdigest()[:16]
        }
        self.transition_log.append(entry)


def transition(receipt: Receipt, now: float) -> tuple[ReceiptState, Optional[TransitionReason]]:
    """
    Evaluate and apply state transition based on current time.
    Returns (new_state, reason) or (current_state, None) if no transition.
    """
    old_state = receipt.state
    
    if old_state == ReceiptState.PROPOSED:
        elapsed = now - receipt.proposed_at
        if elapsed > T_SIGN_SECONDS:
            # Timeout → ALLEGED (not REJECTED!)
            receipt.state = ReceiptState.ALLEGED
            receipt.alleged_at = now
            receipt.log_transition(old_state, receipt.state, TransitionReason.TIMEOUT, now)
            return receipt.state, TransitionReason.TIMEOUT
    
    elif old_state == ReceiptState.ALLEGED:
        elapsed = now - receipt.alleged_at
        if elapsed > T_DECAY_SECONDS:
            # Decay → EXPIRED
            receipt.state = ReceiptState.EXPIRED
            receipt.expired_at = now
            receipt.log_transition(old_state, receipt.state, TransitionReason.TTL_EXCEEDED, now)
            return receipt.state, TransitionReason.TTL_EXCEEDED
    
    return receipt.state, None


def co_sign(receipt: Receipt, now: float) -> dict:
    """Counterparty co-signs the receipt."""
    old_state = receipt.state
    
    if old_state == ReceiptState.PROPOSED:
        receipt.state = ReceiptState.CONFIRMED
        receipt.confirmed_at = now
        receipt.log_transition(old_state, receipt.state, TransitionReason.CO_SIGN, now)
        return {"success": True, "transition": "PROPOSED → CONFIRMED", "on_time": True}
    
    elif old_state == ReceiptState.ALLEGED:
        # Late co-sign! ALLEGED → CONFIRMED (grace recovery)
        receipt.state = ReceiptState.CONFIRMED
        receipt.confirmed_at = now
        receipt.log_transition(old_state, receipt.state, TransitionReason.LATE_SIGN, now)
        return {"success": True, "transition": "ALLEGED → CONFIRMED (late)", "on_time": False}
    
    elif old_state == ReceiptState.CONFIRMED:
        return {"success": False, "error": "Already confirmed"}
    
    elif old_state == ReceiptState.EXPIRED:
        return {"success": False, "error": "Cannot co-sign expired receipt"}
    
    return {"success": False, "error": f"Cannot co-sign in state {old_state.value}"}


def dispute(receipt: Receipt, evidence: str, now: float) -> dict:
    """Explicitly dispute the receipt with evidence."""
    old_state = receipt.state
    
    if old_state in (ReceiptState.PROPOSED, ReceiptState.ALLEGED):
        receipt.state = ReceiptState.DISPUTED
        receipt.disputed_at = now
        receipt.dispute_evidence = evidence
        receipt.log_transition(old_state, receipt.state, TransitionReason.EXPLICIT_REJECT, now)
        return {"success": True, "transition": f"{old_state.value} → DISPUTED"}
    
    elif old_state == ReceiptState.CONFIRMED:
        # Can dispute even after confirmation (with evidence)
        elapsed = now - receipt.confirmed_at
        if elapsed <= T_DISPUTE_SECONDS:
            receipt.state = ReceiptState.DISPUTED
            receipt.disputed_at = now
            receipt.dispute_evidence = evidence
            receipt.log_transition(old_state, receipt.state, TransitionReason.EXPLICIT_REJECT, now)
            return {"success": True, "transition": "CONFIRMED → DISPUTED (within dispute window)"}
        return {"success": False, "error": "Dispute window expired"}
    
    return {"success": False, "error": f"Cannot dispute in state {old_state.value}"}


def grade_alleged(receipt: Receipt, behavioral_evidence: bool, now: float) -> dict:
    """Grader adjudicates ALLEGED receipt based on behavioral evidence."""
    if receipt.state != ReceiptState.ALLEGED:
        return {"success": False, "error": f"Can only adjudicate ALLEGED, got {receipt.state.value}"}
    
    if behavioral_evidence:
        receipt.state = ReceiptState.CONFIRMED
        receipt.confirmed_at = now
        receipt.log_transition(ReceiptState.ALLEGED, receipt.state, 
                              TransitionReason.EVIDENCE_UPGRADE, now)
        return {"success": True, "transition": "ALLEGED → CONFIRMED (grader adjudication)",
                "note": "Behavioral evidence sufficient for upgrade"}
    else:
        return {"success": True, "transition": "ALLEGED (maintained)",
                "note": "Insufficient evidence for upgrade, weight remains 0.5"}


def compute_trust_weight(receipts: list[Receipt]) -> dict:
    """Compute weighted trust from receipt portfolio."""
    weights = {
        ReceiptState.CONFIRMED: 1.0,
        ReceiptState.ALLEGED: ALLEGED_WEIGHT,
        ReceiptState.DISPUTED: DISPUTED_WEIGHT,
        ReceiptState.EXPIRED: EXPIRED_WEIGHT,
        ReceiptState.PROPOSED: 0.0  # Pending, no weight yet
    }
    
    total_weight = 0.0
    max_possible = 0.0
    state_counts = {}
    
    for r in receipts:
        w = weights.get(r.state, 0.0)
        total_weight += w
        max_possible += 1.0
        state_counts[r.state.value] = state_counts.get(r.state.value, 0) + 1
    
    ratio = total_weight / max_possible if max_possible > 0 else 0.0
    
    return {
        "total_weight": round(total_weight, 2),
        "max_possible": round(max_possible, 2),
        "trust_ratio": round(ratio, 4),
        "state_distribution": state_counts,
        "alleged_contribution": round(state_counts.get("ALLEGED", 0) * ALLEGED_WEIGHT, 2)
    }


# === Scenarios ===

def scenario_normal_lifecycle():
    """Happy path: PROPOSED → CONFIRMED."""
    print("=== Scenario: Normal Lifecycle ===")
    now = time.time()
    r = Receipt("r001", "kit_fox", "bro_agent", "scope_abc", "A", proposed_at=now)
    print(f"  Created: {r.state.value}")
    
    result = co_sign(r, now + 3600)  # 1h later
    print(f"  Co-signed: {result['transition']}, on_time={result['on_time']}")
    print(f"  Transitions: {len(r.transition_log)}")
    print()


def scenario_alleged_timeout():
    """Timeout → ALLEGED (not REJECTED)."""
    print("=== Scenario: Timeout → ALLEGED ===")
    now = time.time()
    r = Receipt("r002", "kit_fox", "silent_agent", "scope_def", "B", proposed_at=now)
    
    # 25h later — past T_sign
    state, reason = transition(r, now + 90000)
    print(f"  After 25h: {state.value} (reason: {reason.value})")
    print(f"  ALLEGED ≠ REJECTED. Weight = {ALLEGED_WEIGHT}")
    
    # Late co-sign at 30h
    result = co_sign(r, now + 108000)
    print(f"  Late co-sign at 30h: {result['transition']}")
    print(f"  Transitions: {len(r.transition_log)}")
    print()


def scenario_alleged_to_expired():
    """ALLEGED decays to EXPIRED after T_decay."""
    print("=== Scenario: ALLEGED → EXPIRED ===")
    now = time.time()
    r = Receipt("r003", "kit_fox", "ghost_agent", "scope_ghi", "C", proposed_at=now)
    
    # Timeout → ALLEGED
    transition(r, now + 90000)
    print(f"  After timeout: {r.state.value}")
    
    # 8 days later — past T_decay
    state, reason = transition(r, now + 90000 + 691200)
    print(f"  After 8 more days: {state.value} (reason: {reason.value})")
    print(f"  Weight: {EXPIRED_WEIGHT}")
    print()


def scenario_grader_adjudication():
    """Grader upgrades ALLEGED to CONFIRMED with behavioral evidence."""
    print("=== Scenario: Grader Adjudication ===")
    now = time.time()
    r = Receipt("r004", "kit_fox", "slow_agent", "scope_jkl", "B", proposed_at=now)
    
    # Timeout → ALLEGED
    transition(r, now + 90000)
    print(f"  State: {r.state.value}")
    
    # Grader finds behavioral evidence
    result = grade_alleged(r, behavioral_evidence=True, now=now + 100000)
    print(f"  Grader: {result['transition']}")
    print(f"  Note: {result['note']}")
    print(f"  Final state: {r.state.value}")
    print()


def scenario_portfolio_trust():
    """Mixed portfolio with ALLEGED receipts affecting trust weight."""
    print("=== Scenario: Portfolio Trust Weight ===")
    now = time.time()
    
    receipts = [
        Receipt("r010", "a", "b", "s1", "A", state=ReceiptState.CONFIRMED),
        Receipt("r011", "a", "b", "s2", "A", state=ReceiptState.CONFIRMED),
        Receipt("r012", "a", "b", "s3", "B", state=ReceiptState.CONFIRMED),
        Receipt("r013", "a", "c", "s4", "B", state=ReceiptState.ALLEGED),
        Receipt("r014", "a", "d", "s5", "C", state=ReceiptState.ALLEGED),
        Receipt("r015", "a", "e", "s6", "C", state=ReceiptState.DISPUTED),
        Receipt("r016", "a", "f", "s7", "D", state=ReceiptState.EXPIRED),
    ]
    
    trust = compute_trust_weight(receipts)
    print(f"  7 receipts: {trust['state_distribution']}")
    print(f"  Total weight: {trust['total_weight']} / {trust['max_possible']}")
    print(f"  Trust ratio: {trust['trust_ratio']}")
    print(f"  ALLEGED contribution: {trust['alleged_contribution']}")
    print(f"  Without ALLEGED (old model): {3.0/7.0:.4f}")
    print(f"  With ALLEGED (new model):    {trust['trust_ratio']}")
    print(f"  Δ = {trust['trust_ratio'] - 3.0/7.0:.4f} (ALLEGED preserves partial signal)")
    print()


if __name__ == "__main__":
    print("Alleged State Machine — Five-State Receipt Lifecycle for ATF")
    print("Per santaclawd + RFC 6960 OCSP (good/revoked/unknown)")
    print("=" * 65)
    print()
    print("States: PROPOSED → CONFIRMED | ALLEGED | DISPUTED | EXPIRED")
    print(f"  T_sign:    {T_SIGN_SECONDS//3600}h   (co-sign window)")
    print(f"  T_decay:   {T_DECAY_SECONDS//86400}d   (ALLEGED → EXPIRED)")
    print(f"  T_dispute: {T_DISPUTE_SECONDS//3600}h  (dispute window)")
    print(f"  ALLEGED weight: {ALLEGED_WEIGHT}")
    print()
    
    scenario_normal_lifecycle()
    scenario_alleged_timeout()
    scenario_alleged_to_expired()
    scenario_grader_adjudication()
    scenario_portfolio_trust()
    
    print("=" * 65)
    print("KEY INSIGHT: Silence is ambiguity, not rejection.")
    print("ALLEGED preserves partial signal. Old model collapsed")
    print("timeout → REJECTED, destroying information.")
    print("RFC 6960: unknown ≠ revoked. Same principle.")
