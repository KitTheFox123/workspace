#!/usr/bin/env python3
"""
receipt-state-machine.py — ATF receipt lifecycle with PROBE-based failure detection.

Per santaclawd: silence-as-CONFIRMED is not a receipt type. PROBE closes the ambiguity.
Per Chandra & Toueg (JACM 1996): eventually strong failure detectors for async consensus.
Per FLP (1985): cannot distinguish crash from slow without active check.

State machine:
  SILENT → PROBE (T_probe active check)
  PROBE → CONFIRMED (ACK received within T_ack)
  PROBE → PROBE_TIMEOUT (no ACK in T_ack window)
  PROBE_TIMEOUT → DISPUTED (manual escalation or re-probe fails)
  CONFIRMED → GRACE (staleness window)
  GRACE → EXPIRED (past max_age)

Key insight: PROBE makes the FLP distinction — crash fault vs Byzantine fault.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ReceiptState(Enum):
    SILENT = "SILENT"              # No interaction yet
    PROBE = "PROBE"                # Active check sent, awaiting ACK
    CONFIRMED = "CONFIRMED"        # ACK received, receipt valid
    PROBE_TIMEOUT = "PROBE_TIMEOUT"  # No ACK within window
    DISPUTED = "DISPUTED"          # Explicit rejection or escalation
    GRACE = "GRACE"                # Confirmed but aging (within grace_period)
    EXPIRED = "EXPIRED"            # Past max_age
    SUSPENDED = "SUSPENDED"        # Frozen for investigation
    REVOKED = "REVOKED"            # Permanently invalidated


class TransitionReason(Enum):
    PROBE_SENT = "probe_sent"
    ACK_RECEIVED = "ack_received"
    TIMEOUT = "timeout"
    EXPLICIT_REJECT = "explicit_reject"
    STALENESS = "staleness"
    GRACE_EXPIRED = "grace_expired"
    INVESTIGATION = "investigation"
    REVOCATION = "revocation"
    RE_PROBE = "re_probe"


# SPEC_CONSTANTS (genesis-declared)
T_PROBE_HOURS = 1           # Time between probes
T_ACK_HOURS = 2             # ACK window after probe
MAX_PROBE_RETRIES = 3       # Retries before DISPUTED
GRACE_PERIOD_HOURS = 72     # After CONFIRMED, before EXPIRED
MAX_AGE_HOURS = 720         # Absolute TTL (30 days)
SIGNING_WINDOW_HOURS = 24   # Co-sign window (per santaclawd)


@dataclass
class Transition:
    from_state: ReceiptState
    to_state: ReceiptState
    reason: TransitionReason
    timestamp: float
    metadata: dict = field(default_factory=dict)
    hash: str = ""
    
    def __post_init__(self):
        if not self.hash:
            h = hashlib.sha256(
                f"{self.from_state.value}:{self.to_state.value}:{self.timestamp}".encode()
            ).hexdigest()[:16]
            self.hash = h


@dataclass
class Receipt:
    receipt_id: str
    agent_id: str
    counterparty_id: str
    state: ReceiptState = ReceiptState.SILENT
    created_at: float = 0.0
    last_probe_at: Optional[float] = None
    confirmed_at: Optional[float] = None
    probe_count: int = 0
    transitions: list = field(default_factory=list)
    co_signed: bool = False
    co_sign_deadline: Optional[float] = None
    
    def transition(self, new_state: ReceiptState, reason: TransitionReason, 
                   timestamp: float, **metadata):
        t = Transition(self.state, new_state, reason, timestamp, metadata)
        self.transitions.append(t)
        self.state = new_state
        return t


# Valid transitions (state machine spec)
VALID_TRANSITIONS = {
    ReceiptState.SILENT: {ReceiptState.PROBE},
    ReceiptState.PROBE: {ReceiptState.CONFIRMED, ReceiptState.PROBE_TIMEOUT},
    ReceiptState.PROBE_TIMEOUT: {ReceiptState.PROBE, ReceiptState.DISPUTED, ReceiptState.SUSPENDED},
    ReceiptState.CONFIRMED: {ReceiptState.GRACE, ReceiptState.SUSPENDED, ReceiptState.REVOKED},
    ReceiptState.GRACE: {ReceiptState.EXPIRED, ReceiptState.CONFIRMED, ReceiptState.SUSPENDED},
    ReceiptState.DISPUTED: {ReceiptState.PROBE, ReceiptState.SUSPENDED, ReceiptState.REVOKED},
    ReceiptState.EXPIRED: {ReceiptState.REVOKED},  # Terminal-ish
    ReceiptState.SUSPENDED: {ReceiptState.CONFIRMED, ReceiptState.REVOKED, ReceiptState.DISPUTED},
    ReceiptState.REVOKED: set(),  # Terminal
}


def validate_transition(receipt: Receipt, new_state: ReceiptState) -> bool:
    """Check if transition is valid per state machine spec."""
    return new_state in VALID_TRANSITIONS.get(receipt.state, set())


def probe(receipt: Receipt, now: float) -> dict:
    """Send PROBE and handle response."""
    if receipt.state == ReceiptState.SILENT:
        receipt.transition(ReceiptState.PROBE, TransitionReason.PROBE_SENT, now)
        receipt.last_probe_at = now
        receipt.probe_count += 1
        return {"action": "PROBE_SENT", "retry": receipt.probe_count}
    
    if receipt.state == ReceiptState.PROBE_TIMEOUT:
        if receipt.probe_count >= MAX_PROBE_RETRIES:
            receipt.transition(ReceiptState.DISPUTED, TransitionReason.TIMEOUT, now,
                             retries_exhausted=True)
            return {"action": "DISPUTED", "reason": "max_retries_exhausted"}
        receipt.transition(ReceiptState.PROBE, TransitionReason.RE_PROBE, now)
        receipt.last_probe_at = now
        receipt.probe_count += 1
        return {"action": "RE_PROBE", "retry": receipt.probe_count}
    
    return {"action": "INVALID", "current_state": receipt.state.value}


def ack(receipt: Receipt, now: float) -> dict:
    """Handle ACK response to PROBE."""
    if receipt.state != ReceiptState.PROBE:
        return {"action": "INVALID", "expected": "PROBE", "got": receipt.state.value}
    
    # Check if within ACK window
    if receipt.last_probe_at and (now - receipt.last_probe_at) > T_ACK_HOURS * 3600:
        receipt.transition(ReceiptState.PROBE_TIMEOUT, TransitionReason.TIMEOUT, now,
                         ack_late=True, delay_hours=(now - receipt.last_probe_at) / 3600)
        return {"action": "ACK_LATE", "state": "PROBE_TIMEOUT"}
    
    receipt.transition(ReceiptState.CONFIRMED, TransitionReason.ACK_RECEIVED, now)
    receipt.confirmed_at = now
    receipt.co_sign_deadline = now + SIGNING_WINDOW_HOURS * 3600
    return {"action": "CONFIRMED", "co_sign_deadline_hours": SIGNING_WINDOW_HOURS}


def check_staleness(receipt: Receipt, now: float) -> dict:
    """Check if CONFIRMED receipt has gone stale."""
    if receipt.state != ReceiptState.CONFIRMED:
        return {"action": "N/A", "state": receipt.state.value}
    
    if not receipt.confirmed_at:
        return {"action": "ERROR", "reason": "no_confirmation_timestamp"}
    
    age_hours = (now - receipt.confirmed_at) / 3600
    
    if age_hours > MAX_AGE_HOURS:
        receipt.transition(ReceiptState.EXPIRED, TransitionReason.STALENESS, now,
                         age_hours=age_hours)
        return {"action": "EXPIRED", "age_hours": round(age_hours, 1)}
    
    if age_hours > (MAX_AGE_HOURS - GRACE_PERIOD_HOURS):
        receipt.transition(ReceiptState.GRACE, TransitionReason.STALENESS, now,
                         age_hours=age_hours, grace_remaining_hours=round(MAX_AGE_HOURS - age_hours, 1))
        return {"action": "GRACE", "age_hours": round(age_hours, 1),
                "grace_remaining": round(MAX_AGE_HOURS - age_hours, 1)}
    
    return {"action": "FRESH", "age_hours": round(age_hours, 1)}


def check_co_sign(receipt: Receipt, now: float) -> dict:
    """Check co-signing window status."""
    if not receipt.co_sign_deadline:
        return {"status": "NO_DEADLINE"}
    
    if receipt.co_signed:
        return {"status": "CO_SIGNED"}
    
    if now > receipt.co_sign_deadline:
        return {"status": "UNSIGNED_EXPIRED", "action": "ALLEGED",
                "note": "Payer silence after T_sign = REJECTED (per santaclawd)"}
    
    remaining = (receipt.co_sign_deadline - now) / 3600
    return {"status": "AWAITING", "hours_remaining": round(remaining, 1)}


def audit_transitions(receipt: Receipt) -> dict:
    """Audit transition history for anomalies."""
    issues = []
    
    # Check for invalid transitions
    for i, t in enumerate(receipt.transitions):
        if t.to_state not in VALID_TRANSITIONS.get(t.from_state, set()):
            issues.append(f"Invalid transition #{i}: {t.from_state.value} → {t.to_state.value}")
    
    # Check for excessive probing
    if receipt.probe_count > MAX_PROBE_RETRIES:
        issues.append(f"Excessive probes: {receipt.probe_count} > {MAX_PROBE_RETRIES}")
    
    # Check for time travel
    for i in range(1, len(receipt.transitions)):
        if receipt.transitions[i].timestamp < receipt.transitions[i-1].timestamp:
            issues.append(f"Time travel at transition #{i}")
    
    return {
        "receipt_id": receipt.receipt_id,
        "current_state": receipt.state.value,
        "total_transitions": len(receipt.transitions),
        "probe_count": receipt.probe_count,
        "co_signed": receipt.co_signed,
        "issues": issues,
        "clean": len(issues) == 0
    }


# === Scenarios ===

def scenario_clean_lifecycle():
    """Normal: SILENT → PROBE → CONFIRMED → GRACE → EXPIRED."""
    print("=== Scenario: Clean Lifecycle ===")
    now = time.time()
    
    r = Receipt("r001", "kit_fox", "bro_agent", created_at=now)
    
    # Probe
    result = probe(r, now)
    print(f"  1. {result['action']} (state: {r.state.value})")
    
    # ACK
    result = ack(r, now + 3600)  # 1 hour later
    print(f"  2. {result['action']} (state: {r.state.value})")
    
    # Co-sign
    r.co_signed = True
    print(f"  3. CO_SIGNED (deadline: {SIGNING_WINDOW_HOURS}h)")
    
    # Check after 600 hours (within grace)
    result = check_staleness(r, now + 650 * 3600)
    print(f"  4. {result['action']} (age: {result.get('age_hours', '?')}h)")
    
    # Check after 720+ hours (expired)
    result = check_staleness(r, now + 721 * 3600)
    print(f"  5. {result['action']} (age: {result.get('age_hours', '?')}h)")
    
    audit = audit_transitions(r)
    print(f"  Audit: {audit['total_transitions']} transitions, clean={audit['clean']}")
    print()


def scenario_probe_timeout_retry():
    """Timeout with retries: SILENT → PROBE → TIMEOUT → PROBE → TIMEOUT → DISPUTED."""
    print("=== Scenario: Probe Timeout with Retries ===")
    now = time.time()
    
    r = Receipt("r002", "kit_fox", "ghost_agent", created_at=now)
    
    # First probe
    result = probe(r, now)
    print(f"  1. {result['action']} (probe #{r.probe_count})")
    
    # Timeout
    r.transition(ReceiptState.PROBE_TIMEOUT, TransitionReason.TIMEOUT, now + T_ACK_HOURS * 3600 + 1)
    print(f"  2. PROBE_TIMEOUT (no ACK in {T_ACK_HOURS}h)")
    
    # Re-probe
    result = probe(r, now + 4 * 3600)
    print(f"  3. {result['action']} (probe #{r.probe_count})")
    
    # Timeout again
    r.transition(ReceiptState.PROBE_TIMEOUT, TransitionReason.TIMEOUT, now + 7 * 3600)
    
    # Re-probe
    result = probe(r, now + 8 * 3600)
    print(f"  4. {result['action']} (probe #{r.probe_count})")
    
    # Timeout — max retries
    r.transition(ReceiptState.PROBE_TIMEOUT, TransitionReason.TIMEOUT, now + 11 * 3600)
    result = probe(r, now + 12 * 3600)
    print(f"  5. {result['action']} — retries exhausted (state: {r.state.value})")
    
    audit = audit_transitions(r)
    print(f"  Audit: {audit['total_transitions']} transitions, probes={audit['probe_count']}")
    print()


def scenario_late_ack():
    """ACK arrives after T_ack window — treated as PROBE_TIMEOUT."""
    print("=== Scenario: Late ACK ===")
    now = time.time()
    
    r = Receipt("r003", "kit_fox", "slow_agent", created_at=now)
    
    probe(r, now)
    print(f"  1. PROBE sent")
    
    # ACK arrives 5 hours later (T_ack = 2h)
    result = ack(r, now + 5 * 3600)
    print(f"  2. {result['action']} — late by {5 - T_ACK_HOURS}h (state: {r.state.value})")
    print(f"     Chandra-Toueg: cannot distinguish crash from slow → treat as timeout")
    print()


def scenario_unsigned_co_sign():
    """Payer fails to co-sign within T_sign window."""
    print("=== Scenario: Unsigned Co-Sign (Payer Silence) ===")
    now = time.time()
    
    r = Receipt("r004", "kit_fox", "silent_payer", created_at=now)
    
    probe(r, now)
    ack(r, now + 3600)
    
    # Check co-sign at 12h (still waiting)
    result = check_co_sign(r, now + 12 * 3600)
    print(f"  1. Co-sign: {result['status']} ({result.get('hours_remaining', '?')}h remaining)")
    
    # Check co-sign at 25h (expired)
    result = check_co_sign(r, now + 25 * 3600)
    print(f"  2. Co-sign: {result['status']}")
    print(f"     Note: {result.get('note', '')}")
    print(f"     Payer silence after T_sign = ALLEGED (not CONFIRMED)")
    print()


def scenario_faulter_classification():
    """Classify fault type from state machine behavior."""
    print("=== Scenario: Fault Classification ===")
    now = time.time()
    
    agents = {
        "crash_fault": {"ack_delay": None, "behavior": "Never responds to PROBE"},
        "slow_fault": {"ack_delay": 5, "behavior": "Responds but late (>T_ack)"},
        "byzantine": {"ack_delay": 1, "behavior": "ACKs but disputes content"},
        "healthy": {"ack_delay": 0.5, "behavior": "ACKs within T_ack, co-signs"},
    }
    
    for name, config in agents.items():
        r = Receipt(f"r_{name}", "kit_fox", name, created_at=now)
        probe(r, now)
        
        if config["ack_delay"] is None:
            r.transition(ReceiptState.PROBE_TIMEOUT, TransitionReason.TIMEOUT,
                        now + T_ACK_HOURS * 3600 + 1)
            fault = "CRASH (or Byzantine pretending to be crash)"
        elif config["ack_delay"] > T_ACK_HOURS:
            ack(r, now + config["ack_delay"] * 3600)
            fault = "SLOW (Chandra-Toueg: indistinguishable from crash)"
        else:
            ack(r, now + config["ack_delay"] * 3600)
            fault = "NONE" if r.state == ReceiptState.CONFIRMED else "BYZANTINE"
        
        print(f"  {name}: {fault} → state={r.state.value}")
    
    print(f"\n  FLP impossibility: PROBE makes crash/slow distinction observable")
    print(f"  Chandra-Toueg: eventually strong detector = PROBE with bounded T_ack")
    print()


if __name__ == "__main__":
    print("Receipt State Machine — PROBE-Based Failure Detection for ATF")
    print("Per santaclawd + Chandra & Toueg (JACM 1996) + FLP (1985)")
    print("=" * 70)
    print()
    print(f"Constants: T_probe={T_PROBE_HOURS}h, T_ack={T_ACK_HOURS}h, "
          f"max_retries={MAX_PROBE_RETRIES}, grace={GRACE_PERIOD_HOURS}h, "
          f"max_age={MAX_AGE_HOURS}h, T_sign={SIGNING_WINDOW_HOURS}h")
    print()
    
    scenario_clean_lifecycle()
    scenario_probe_timeout_retry()
    scenario_late_ack()
    scenario_unsigned_co_sign()
    scenario_faulter_classification()
    
    print("=" * 70)
    print("KEY INSIGHT: PROBE closes the FLP gap.")
    print("Silence is not confirmation — it is ambiguity.")
    print("PROBE → ACK = CONFIRMED. PROBE → silence = TIMEOUT → DISPUTED.")
    print("Co-sign window: T_sign = 24h genesis constant. Silence = ALLEGED.")
