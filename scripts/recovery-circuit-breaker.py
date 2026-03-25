#!/usr/bin/env python3
"""
recovery-circuit-breaker.py — Circuit breaker recovery window for ATF trust restoration.

Per santaclawd: n_recovery=8 consecutive CONFIRMED receipts in 30d window.
Per Nygard (Release It!, 2007): CLOSED→OPEN→HALF_OPEN state machine.

States:
  HEALTHY (CLOSED)    — Normal operation, trust score active
  DEGRADED (OPEN)     — Trust suspended, no new receipts accepted
  RECOVERING (HALF_OPEN) — Probationary, counting consecutive successes
  DORMANT             — Voluntary idle, preserves trust with decay

Recovery spec:
  RECOVERY_THRESHOLD = 8    (consecutive CONFIRMED, SPEC_NORMATIVE)
  RECOVERY_WINDOW = 30d     (max time to complete recovery, SPEC_NORMATIVE)
  MISS_RESETS_TO = 0        (any failure resets counter to 0, not n-1)
  MIN_COUNTERPARTIES = 3    (receipts from 3+ independent counterparties)
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustState(Enum):
    HEALTHY = "HEALTHY"         # Circuit closed, normal operation
    DEGRADED = "DEGRADED"       # Circuit open, trust suspended
    RECOVERING = "RECOVERING"   # Circuit half-open, probationary
    DORMANT = "DORMANT"         # Voluntary idle with decay
    REVOKED = "REVOKED"         # Permanent, no recovery possible


class ReceiptOutcome(Enum):
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    DISPUTED = "DISPUTED"
    ALLEGED = "ALLEGED"


# SPEC_NORMATIVE constants
RECOVERY_THRESHOLD = 8          # Consecutive CONFIRMED receipts needed
RECOVERY_WINDOW_DAYS = 30       # Max days to complete recovery
MIN_COUNTERPARTIES = 3          # Must interact with 3+ different counterparties
DEGRADED_TO_REVOKED_DAYS = 365  # Max time in DEGRADED before auto-revoke
DORMANT_DECAY_RATE = 0.05       # 5% per month
DORMANT_FLOOR = 0.30            # Minimum trust during dormancy
DORMANT_MAX_DAYS = 365          # Max dormancy before auto-DEGRADED


@dataclass
class RecoveryReceipt:
    receipt_id: str
    counterparty_id: str
    outcome: ReceiptOutcome
    timestamp: float
    evidence_grade: str
    receipt_hash: str = ""
    
    def __post_init__(self):
        if not self.receipt_hash:
            self.receipt_hash = hashlib.sha256(
                f"{self.receipt_id}:{self.counterparty_id}:{self.outcome.value}".encode()
            ).hexdigest()[:16]


@dataclass
class RecoveryState:
    agent_id: str
    state: TrustState
    trust_score: float
    consecutive_confirmed: int = 0
    recovery_started_at: Optional[float] = None
    unique_counterparties: set = field(default_factory=set)
    recovery_receipts: list = field(default_factory=list)
    state_history: list = field(default_factory=list)
    degraded_at: Optional[float] = None
    dormant_at: Optional[float] = None


def transition_to_degraded(state: RecoveryState, reason: str) -> RecoveryState:
    """Move agent to DEGRADED (circuit OPEN)."""
    state.state_history.append({
        "from": state.state.value,
        "to": "DEGRADED",
        "reason": reason,
        "timestamp": time.time()
    })
    state.state = TrustState.DEGRADED
    state.degraded_at = time.time()
    state.consecutive_confirmed = 0
    state.unique_counterparties = set()
    state.recovery_receipts = []
    state.recovery_started_at = None
    return state


def begin_recovery(state: RecoveryState) -> RecoveryState:
    """Move from DEGRADED to RECOVERING (circuit HALF_OPEN)."""
    if state.state != TrustState.DEGRADED:
        raise ValueError(f"Cannot begin recovery from {state.state.value}")
    
    state.state_history.append({
        "from": "DEGRADED",
        "to": "RECOVERING",
        "reason": "recovery_initiated",
        "timestamp": time.time()
    })
    state.state = TrustState.RECOVERING
    state.recovery_started_at = time.time()
    state.consecutive_confirmed = 0
    state.unique_counterparties = set()
    state.recovery_receipts = []
    return state


def process_receipt(state: RecoveryState, receipt: RecoveryReceipt) -> dict:
    """Process a receipt during recovery. Returns status update."""
    result = {
        "agent_id": state.agent_id,
        "receipt_id": receipt.receipt_id,
        "previous_state": state.state.value,
        "action": "none"
    }
    
    if state.state == TrustState.REVOKED:
        result["action"] = "REJECTED_REVOKED"
        result["message"] = "Agent permanently revoked, no recovery possible"
        return result
    
    if state.state == TrustState.HEALTHY:
        # Normal operation — track for degradation triggers
        if receipt.outcome == ReceiptOutcome.CONFIRMED:
            result["action"] = "ACCEPTED"
        else:
            result["action"] = "RECORDED_FAILURE"
        return result
    
    if state.state == TrustState.DEGRADED:
        result["action"] = "REJECTED_DEGRADED"
        result["message"] = "Agent degraded, must initiate recovery first"
        return result
    
    if state.state == TrustState.DORMANT:
        # Dormant agent submitting receipt = waking up
        state.state = TrustState.RECOVERING
        state.recovery_started_at = time.time()
        state.consecutive_confirmed = 0
        state.unique_counterparties = set()
        state.recovery_receipts = []
        state.state_history.append({
            "from": "DORMANT", "to": "RECOVERING",
            "reason": "wake_on_receipt", "timestamp": time.time()
        })
        result["action"] = "WAKE_FROM_DORMANT"
    
    # RECOVERING state
    if state.state == TrustState.RECOVERING:
        # Check window expiry
        elapsed = time.time() - state.recovery_started_at
        if elapsed > RECOVERY_WINDOW_DAYS * 86400:
            state = transition_to_degraded(state, "recovery_window_expired")
            result["action"] = "RECOVERY_EXPIRED"
            result["message"] = f"Recovery window ({RECOVERY_WINDOW_DAYS}d) expired"
            result["new_state"] = state.state.value
            return result
        
        if receipt.outcome == ReceiptOutcome.CONFIRMED:
            state.consecutive_confirmed += 1
            state.unique_counterparties.add(receipt.counterparty_id)
            state.recovery_receipts.append(receipt)
            
            # Check if recovery complete
            if (state.consecutive_confirmed >= RECOVERY_THRESHOLD and
                len(state.unique_counterparties) >= MIN_COUNTERPARTIES):
                # Recovery complete — circuit CLOSED
                state.state = TrustState.HEALTHY
                state.state_history.append({
                    "from": "RECOVERING", "to": "HEALTHY",
                    "reason": "recovery_complete",
                    "receipts": state.consecutive_confirmed,
                    "counterparties": len(state.unique_counterparties),
                    "timestamp": time.time()
                })
                result["action"] = "RECOVERY_COMPLETE"
                result["consecutive"] = state.consecutive_confirmed
                result["counterparties"] = len(state.unique_counterparties)
            else:
                result["action"] = "RECOVERY_PROGRESS"
                result["consecutive"] = state.consecutive_confirmed
                result["remaining"] = RECOVERY_THRESHOLD - state.consecutive_confirmed
                result["counterparties"] = len(state.unique_counterparties)
                result["counterparties_needed"] = max(0, MIN_COUNTERPARTIES - len(state.unique_counterparties))
        else:
            # ANY failure resets to 0 (not n-1)
            old_count = state.consecutive_confirmed
            state.consecutive_confirmed = 0
            state.unique_counterparties = set()
            result["action"] = "RECOVERY_RESET"
            result["message"] = f"Failed receipt resets counter from {old_count} to 0"
            result["outcome"] = receipt.outcome.value
    
    result["new_state"] = state.state.value
    return result


def compute_dormant_trust(original_trust: float, dormant_days: int) -> float:
    """Compute decayed trust during dormancy."""
    months = dormant_days / 30
    decayed = original_trust * (1 - DORMANT_DECAY_RATE) ** months
    return max(DORMANT_FLOOR, round(decayed, 4))


def audit_recovery(state: RecoveryState) -> dict:
    """Audit recovery state for spec compliance."""
    issues = []
    
    if state.state == TrustState.RECOVERING:
        if state.recovery_started_at is None:
            issues.append("RECOVERING without recovery_started_at")
        else:
            elapsed = time.time() - state.recovery_started_at
            remaining = RECOVERY_WINDOW_DAYS * 86400 - elapsed
            if remaining < 0:
                issues.append(f"Recovery window expired {-remaining/86400:.1f}d ago")
    
    if state.state == TrustState.DEGRADED and state.degraded_at:
        degraded_days = (time.time() - state.degraded_at) / 86400
        if degraded_days > DEGRADED_TO_REVOKED_DAYS:
            issues.append(f"DEGRADED for {degraded_days:.0f}d, should be REVOKED (max {DEGRADED_TO_REVOKED_DAYS}d)")
    
    return {
        "agent_id": state.agent_id,
        "state": state.state.value,
        "trust_score": state.trust_score,
        "consecutive_confirmed": state.consecutive_confirmed,
        "unique_counterparties": len(state.unique_counterparties),
        "recovery_progress": f"{state.consecutive_confirmed}/{RECOVERY_THRESHOLD}",
        "counterparty_progress": f"{len(state.unique_counterparties)}/{MIN_COUNTERPARTIES}",
        "issues": issues,
        "compliant": len(issues) == 0
    }


# === Scenarios ===

def scenario_successful_recovery():
    """Agent recovers from DEGRADED through 8 consecutive CONFIRMED."""
    print("=== Scenario: Successful Recovery ===")
    now = time.time()
    
    state = RecoveryState("recovering_agent", TrustState.DEGRADED, 0.45, degraded_at=now-86400*7)
    state = begin_recovery(state)
    
    counterparties = ["cp_a", "cp_b", "cp_c", "cp_d"]
    for i in range(8):
        r = RecoveryReceipt(f"r{i:03d}", counterparties[i % 4], ReceiptOutcome.CONFIRMED, now, "B")
        result = process_receipt(state, r)
        print(f"  Receipt {i+1}: {result['action']} "
              f"({state.consecutive_confirmed}/{RECOVERY_THRESHOLD}, "
              f"{len(state.unique_counterparties)}/{MIN_COUNTERPARTIES} counterparties)")
    
    audit = audit_recovery(state)
    print(f"  Final state: {audit['state']}, compliant: {audit['compliant']}")
    print()


def scenario_failure_resets():
    """Single failure during recovery resets counter to 0."""
    print("=== Scenario: Failure Resets Counter ===")
    now = time.time()
    
    state = RecoveryState("fragile_agent", TrustState.DEGRADED, 0.35, degraded_at=now-86400*14)
    state = begin_recovery(state)
    
    # 6 consecutive CONFIRMED
    for i in range(6):
        r = RecoveryReceipt(f"r{i:03d}", f"cp_{i%4}", ReceiptOutcome.CONFIRMED, now, "B")
        process_receipt(state, r)
    print(f"  After 6 CONFIRMED: {state.consecutive_confirmed}/{RECOVERY_THRESHOLD}")
    
    # 1 FAILED — resets to 0
    r = RecoveryReceipt("r_fail", "cp_x", ReceiptOutcome.FAILED, now, "F")
    result = process_receipt(state, r)
    print(f"  After 1 FAILED: {result['action']} — counter={state.consecutive_confirmed}")
    
    # Must start over
    for i in range(8):
        r = RecoveryReceipt(f"r2_{i:03d}", f"cp_{i%4}", ReceiptOutcome.CONFIRMED, now, "B")
        process_receipt(state, r)
    print(f"  After 8 more CONFIRMED: state={state.state.value}")
    print()


def scenario_window_expiry():
    """Recovery window expires before threshold met."""
    print("=== Scenario: Window Expiry ===")
    
    state = RecoveryState("slow_agent", TrustState.DEGRADED, 0.30,
                          degraded_at=time.time()-86400*60)
    state = begin_recovery(state)
    # Simulate expired window
    state.recovery_started_at = time.time() - (RECOVERY_WINDOW_DAYS + 1) * 86400
    
    r = RecoveryReceipt("r_late", "cp_a", ReceiptOutcome.CONFIRMED, time.time(), "B")
    result = process_receipt(state, r)
    print(f"  Result: {result['action']}")
    print(f"  Message: {result.get('message', '')}")
    print(f"  State: {state.state.value}")
    print()


def scenario_insufficient_counterparties():
    """8 CONFIRMED but only from 2 counterparties — not enough diversity."""
    print("=== Scenario: Insufficient Counterparty Diversity ===")
    now = time.time()
    
    state = RecoveryState("sybil_agent", TrustState.DEGRADED, 0.40, degraded_at=now-86400*5)
    state = begin_recovery(state)
    
    # 8 receipts from only 2 counterparties
    for i in range(8):
        cp = "cp_a" if i % 2 == 0 else "cp_b"
        r = RecoveryReceipt(f"r{i:03d}", cp, ReceiptOutcome.CONFIRMED, now, "B")
        result = process_receipt(state, r)
    
    print(f"  Consecutive: {state.consecutive_confirmed}/{RECOVERY_THRESHOLD} ✓")
    print(f"  Counterparties: {len(state.unique_counterparties)}/{MIN_COUNTERPARTIES} ✗")
    print(f"  State: {state.state.value} (still RECOVERING — need more diverse counterparties)")
    print()


def scenario_dormant_wake():
    """Dormant agent wakes and enters recovery."""
    print("=== Scenario: Dormant Wake ===")
    now = time.time()
    
    state = RecoveryState("sleeping_agent", TrustState.DORMANT, 0.72, dormant_at=now-86400*90)
    
    # Trust decayed during dormancy
    decayed = compute_dormant_trust(0.72, 90)
    state.trust_score = decayed
    print(f"  Trust after 90d dormancy: {state.trust_score} (from 0.72)")
    
    # First receipt wakes agent
    r = RecoveryReceipt("r_wake", "cp_a", ReceiptOutcome.CONFIRMED, now, "B")
    result = process_receipt(state, r)
    print(f"  First receipt: {result['action']}, state={state.state.value}")
    
    # Complete recovery
    cps = ["cp_a", "cp_b", "cp_c", "cp_d"]
    for i in range(7):
        r = RecoveryReceipt(f"r{i+1:03d}", cps[(i+1) % 4], ReceiptOutcome.CONFIRMED, now, "B")
        process_receipt(state, r)
    
    print(f"  After 8 total: state={state.state.value}")
    print()


if __name__ == "__main__":
    print("Recovery Circuit Breaker — ATF Trust Restoration")
    print(f"Per santaclawd + Nygard (Release It!, 2007)")
    print("=" * 70)
    print(f"\nSPEC_NORMATIVE constants:")
    print(f"  RECOVERY_THRESHOLD = {RECOVERY_THRESHOLD} consecutive CONFIRMED")
    print(f"  RECOVERY_WINDOW = {RECOVERY_WINDOW_DAYS}d")
    print(f"  MIN_COUNTERPARTIES = {MIN_COUNTERPARTIES}")
    print(f"  MISS_RESETS_TO = 0 (not n-1)")
    print(f"  DORMANT_DECAY = {DORMANT_DECAY_RATE*100}%/month, floor={DORMANT_FLOOR}")
    print()
    
    scenario_successful_recovery()
    scenario_failure_resets()
    scenario_window_expiry()
    scenario_insufficient_counterparties()
    scenario_dormant_wake()
    
    print("=" * 70)
    print("KEY INSIGHT: Circuit breaker maps exactly to trust recovery.")
    print("CLOSED=HEALTHY, OPEN=DEGRADED, HALF_OPEN=RECOVERING.")
    print("Miss resets to 0 — no partial credit during probation.")
    print("Counterparty diversity prevents self-dealing recovery.")
