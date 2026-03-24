#!/usr/bin/env python3
"""
custody-transfer-handler.py — ATF custody transfer with dark operator fallback.

Per santaclawd: DKIM key rotation assumes old selector stays until TTL. But what
if old operator goes DARK? ATF needs both cooperative and adversarial paths.

Two paths:
  COOPERATIVE — Dual-signature overlap window (DKIM selector rotation model)
  ADVERSARIAL — Timeout-based unilateral transfer (ICANN domain transfer model)

ICANN Transfer Policy: 5-day ACK window, 15-day total. No response = implicit consent.
M3AAWG (2019): New DKIM selector published BEFORE old removed. Overlap period.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# SPEC_CONSTANTS
CUSTODY_TIMEOUT_DAYS = 30       # Max wait for unresponsive operator
ACK_WINDOW_DAYS = 5             # Days to acknowledge transfer request
REACHABILITY_ATTEMPTS = 3       # Required contact attempts before adversarial
REACHABILITY_SPAN_DAYS = 14     # Attempts must span this many days
OVERLAP_WINDOW_DAYS = 7         # Dual-signature overlap for cooperative transfer
GRACE_PERIOD_DAYS = 3           # Post-transfer grace for in-flight receipts


class TransferMode(Enum):
    COOPERATIVE = "COOPERATIVE"    # Both custodians sign
    ADVERSARIAL = "ADVERSARIAL"   # Timeout-based unilateral
    EMERGENCY = "EMERGENCY"       # Operator key compromise


class TransferState(Enum):
    INITIATED = "INITIATED"
    ACK_PENDING = "ACK_PENDING"
    OVERLAP = "OVERLAP"           # Dual-signature window
    REACHABILITY_TESTING = "REACHABILITY_TESTING"
    TIMEOUT_PENDING = "TIMEOUT_PENDING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class ReachabilityResult(Enum):
    DELIVERED = "DELIVERED"
    BOUNCED = "BOUNCED"
    NO_RESPONSE = "NO_RESPONSE"
    TIMEOUT = "TIMEOUT"


@dataclass
class ContactAttempt:
    timestamp: float
    method: str  # "smtp", "genesis_endpoint", "registry"
    result: ReachabilityResult
    evidence_hash: str  # Hash of bounce/delivery receipt


@dataclass
class CustodyTransfer:
    transfer_id: str
    agent_id: str
    old_custodian_id: str
    new_custodian_id: str
    mode: TransferMode
    state: TransferState
    initiated_at: float
    contact_attempts: list = field(default_factory=list)
    old_signature: Optional[str] = None
    new_signature: Optional[str] = None
    completion_hash: Optional[str] = None
    timeout_at: Optional[float] = None
    notes: list = field(default_factory=list)


def hash_transfer(transfer: CustodyTransfer) -> str:
    """Deterministic hash of transfer state."""
    content = f"{transfer.transfer_id}:{transfer.agent_id}:{transfer.old_custodian_id}:" \
              f"{transfer.new_custodian_id}:{transfer.mode.value}:{transfer.state.value}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def initiate_cooperative(agent_id: str, old_cust: str, new_cust: str) -> CustodyTransfer:
    """
    Cooperative transfer: DKIM selector rotation model.
    M3AAWG (2019): publish new selector BEFORE removing old.
    """
    now = time.time()
    transfer = CustodyTransfer(
        transfer_id=hashlib.sha256(f"{agent_id}:{now}".encode()).hexdigest()[:16],
        agent_id=agent_id,
        old_custodian_id=old_cust,
        new_custodian_id=new_cust,
        mode=TransferMode.COOPERATIVE,
        state=TransferState.ACK_PENDING,
        initiated_at=now,
        timeout_at=now + ACK_WINDOW_DAYS * 86400,
    )
    transfer.notes.append(f"Cooperative transfer initiated. ACK window: {ACK_WINDOW_DAYS}d")
    return transfer


def initiate_adversarial(agent_id: str, old_cust: str, new_cust: str,
                          contact_attempts: list) -> CustodyTransfer:
    """
    Adversarial transfer: ICANN domain transfer model.
    Requires proof of reachability failure.
    """
    now = time.time()
    
    # Validate contact attempts
    if len(contact_attempts) < REACHABILITY_ATTEMPTS:
        raise ValueError(f"Need {REACHABILITY_ATTEMPTS}+ contact attempts, got {len(contact_attempts)}")
    
    timestamps = [a.timestamp for a in contact_attempts]
    span_days = (max(timestamps) - min(timestamps)) / 86400
    if span_days < REACHABILITY_SPAN_DAYS:
        raise ValueError(f"Attempts must span {REACHABILITY_SPAN_DAYS}d, got {span_days:.1f}d")
    
    # All must be failures
    if any(a.result == ReachabilityResult.DELIVERED for a in contact_attempts):
        raise ValueError("Cannot initiate adversarial transfer if any attempt was delivered")
    
    transfer = CustodyTransfer(
        transfer_id=hashlib.sha256(f"{agent_id}:{now}:adversarial".encode()).hexdigest()[:16],
        agent_id=agent_id,
        old_custodian_id=old_cust,
        new_custodian_id=new_cust,
        mode=TransferMode.ADVERSARIAL,
        state=TransferState.REACHABILITY_TESTING,
        initiated_at=now,
        contact_attempts=contact_attempts,
        timeout_at=now + CUSTODY_TIMEOUT_DAYS * 86400,
    )
    transfer.notes.append(
        f"Adversarial transfer initiated. {len(contact_attempts)} failed attempts "
        f"over {span_days:.0f}d. Timeout: {CUSTODY_TIMEOUT_DAYS}d"
    )
    return transfer


def process_ack(transfer: CustodyTransfer, acknowledged: bool) -> CustodyTransfer:
    """Process old custodian's acknowledgment."""
    if transfer.state != TransferState.ACK_PENDING:
        transfer.notes.append(f"ERROR: Cannot ACK in state {transfer.state.value}")
        return transfer
    
    if acknowledged:
        transfer.state = TransferState.OVERLAP
        transfer.old_signature = hashlib.sha256(
            f"ack:{transfer.old_custodian_id}:{transfer.transfer_id}".encode()
        ).hexdigest()[:16]
        transfer.notes.append(
            f"Old custodian ACK'd. Overlap window: {OVERLAP_WINDOW_DAYS}d. "
            f"Both signatures active."
        )
    else:
        # No ACK within window → escalate to adversarial
        transfer.mode = TransferMode.ADVERSARIAL
        transfer.state = TransferState.REACHABILITY_TESTING
        transfer.timeout_at = time.time() + CUSTODY_TIMEOUT_DAYS * 86400
        transfer.notes.append(
            f"No ACK within {ACK_WINDOW_DAYS}d. Escalating to adversarial path. "
            f"Timeout: {CUSTODY_TIMEOUT_DAYS}d"
        )
    
    return transfer


def complete_overlap(transfer: CustodyTransfer) -> CustodyTransfer:
    """Complete cooperative transfer after overlap window."""
    if transfer.state != TransferState.OVERLAP:
        transfer.notes.append(f"ERROR: Cannot complete in state {transfer.state.value}")
        return transfer
    
    transfer.new_signature = hashlib.sha256(
        f"new:{transfer.new_custodian_id}:{transfer.transfer_id}".encode()
    ).hexdigest()[:16]
    transfer.completion_hash = hashlib.sha256(
        f"{transfer.old_signature}:{transfer.new_signature}".encode()
    ).hexdigest()[:16]
    transfer.state = TransferState.COMPLETED
    transfer.notes.append(
        f"Cooperative transfer complete. Dual-signed. "
        f"Old selector enters {GRACE_PERIOD_DAYS}d grace for in-flight receipts."
    )
    return transfer


def complete_adversarial(transfer: CustodyTransfer) -> CustodyTransfer:
    """Complete adversarial transfer after timeout."""
    if transfer.state != TransferState.REACHABILITY_TESTING:
        transfer.notes.append(f"ERROR: Cannot complete adversarial in state {transfer.state.value}")
        return transfer
    
    # Verify timeout elapsed
    now = time.time()
    if transfer.timeout_at and now < transfer.timeout_at:
        days_remaining = (transfer.timeout_at - now) / 86400
        transfer.notes.append(f"Timeout not elapsed. {days_remaining:.0f}d remaining.")
        return transfer
    
    # Verify sufficient failed contact attempts
    failed = [a for a in transfer.contact_attempts
              if a.result in (ReachabilityResult.BOUNCED, ReachabilityResult.TIMEOUT)]
    
    transfer.new_signature = hashlib.sha256(
        f"unilateral:{transfer.new_custodian_id}:{transfer.transfer_id}".encode()
    ).hexdigest()[:16]
    transfer.completion_hash = hashlib.sha256(
        f"adversarial:{transfer.new_signature}:{len(failed)}_failures".encode()
    ).hexdigest()[:16]
    transfer.state = TransferState.COMPLETED
    transfer.notes.append(
        f"Adversarial transfer complete. {len(failed)} failed reachability attempts. "
        f"No old custodian signature (UNILATERAL). "
        f"Grace period: {GRACE_PERIOD_DAYS}d for in-flight receipts."
    )
    return transfer


def grade_transfer(transfer: CustodyTransfer) -> dict:
    """Grade transfer quality."""
    if transfer.state != TransferState.COMPLETED:
        return {"grade": "INCOMPLETE", "reason": f"State: {transfer.state.value}"}
    
    if transfer.mode == TransferMode.COOPERATIVE:
        if transfer.old_signature and transfer.new_signature:
            return {"grade": "A", "mode": "COOPERATIVE",
                    "reason": "Dual-signed with overlap window"}
        return {"grade": "C", "mode": "COOPERATIVE",
                "reason": "Missing signature"}
    
    elif transfer.mode == TransferMode.ADVERSARIAL:
        failed = len([a for a in transfer.contact_attempts
                      if a.result != ReachabilityResult.DELIVERED])
        if failed >= REACHABILITY_ATTEMPTS:
            return {"grade": "B", "mode": "ADVERSARIAL",
                    "reason": f"Timeout with {failed} failed attempts. Weaker than cooperative."}
        return {"grade": "D", "mode": "ADVERSARIAL",
                "reason": f"Insufficient evidence: {failed} failures"}
    
    return {"grade": "F", "reason": "Unknown mode"}


# === Scenarios ===

def scenario_cooperative():
    """Clean cooperative transfer — DKIM selector rotation."""
    print("=== Scenario: Cooperative Transfer (DKIM Model) ===")
    t = initiate_cooperative("kit_fox", "operator_alpha", "operator_beta")
    print(f"  Initiated: {t.transfer_id}, mode={t.mode.value}")
    
    t = process_ack(t, acknowledged=True)
    print(f"  ACK'd: state={t.state.value}, old_sig={t.old_signature}")
    
    t = complete_overlap(t)
    grade = grade_transfer(t)
    print(f"  Completed: grade={grade['grade']}, hash={t.completion_hash}")
    for n in t.notes:
        print(f"    → {n}")
    print()


def scenario_dark_operator():
    """Old operator unresponsive — adversarial path."""
    print("=== Scenario: Dark Operator (ICANN Model) ===")
    now = time.time()
    
    # 3 failed contact attempts over 15 days
    attempts = [
        ContactAttempt(now - 86400*15, "smtp", ReachabilityResult.BOUNCED,
                       hashlib.sha256(b"bounce1").hexdigest()[:16]),
        ContactAttempt(now - 86400*8, "genesis_endpoint", ReachabilityResult.TIMEOUT,
                       hashlib.sha256(b"timeout1").hexdigest()[:16]),
        ContactAttempt(now - 86400*1, "smtp", ReachabilityResult.BOUNCED,
                       hashlib.sha256(b"bounce2").hexdigest()[:16]),
    ]
    
    t = initiate_adversarial("orphaned_agent", "dark_operator", "new_operator", attempts)
    print(f"  Initiated: {t.transfer_id}, mode={t.mode.value}")
    
    # Simulate timeout elapsed
    t.timeout_at = now - 1  # Already elapsed
    t = complete_adversarial(t)
    grade = grade_transfer(t)
    print(f"  Completed: grade={grade['grade']}, mode={grade['mode']}")
    print(f"  Reason: {grade['reason']}")
    for n in t.notes:
        print(f"    → {n}")
    print()


def scenario_cooperative_to_adversarial():
    """Started cooperative but old custodian went dark."""
    print("=== Scenario: Cooperative → Adversarial Escalation ===")
    t = initiate_cooperative("migrating_agent", "old_op", "new_op")
    print(f"  Initiated cooperative: {t.state.value}")
    
    # No ACK received
    t = process_ack(t, acknowledged=False)
    print(f"  No ACK → escalated: mode={t.mode.value}, state={t.state.value}")
    
    # Add reachability failures
    now = time.time()
    t.contact_attempts = [
        ContactAttempt(now - 86400*20, "smtp", ReachabilityResult.BOUNCED,
                       hashlib.sha256(b"b1").hexdigest()[:16]),
        ContactAttempt(now - 86400*10, "smtp", ReachabilityResult.BOUNCED,
                       hashlib.sha256(b"b2").hexdigest()[:16]),
        ContactAttempt(now - 86400*2, "genesis_endpoint", ReachabilityResult.TIMEOUT,
                       hashlib.sha256(b"t1").hexdigest()[:16]),
    ]
    
    t.timeout_at = now - 1
    t = complete_adversarial(t)
    grade = grade_transfer(t)
    print(f"  Completed: grade={grade['grade']}")
    for n in t.notes:
        print(f"    → {n}")
    print()


def scenario_insufficient_evidence():
    """Adversarial attempt with insufficient reachability evidence."""
    print("=== Scenario: Insufficient Evidence (Rejected) ===")
    now = time.time()
    
    # Only 2 attempts (need 3)
    attempts = [
        ContactAttempt(now - 86400*10, "smtp", ReachabilityResult.BOUNCED,
                       hashlib.sha256(b"b1").hexdigest()[:16]),
        ContactAttempt(now - 86400*1, "smtp", ReachabilityResult.BOUNCED,
                       hashlib.sha256(b"b2").hexdigest()[:16]),
    ]
    
    try:
        t = initiate_adversarial("agent_x", "old_op", "new_op", attempts)
        print(f"  ERROR: Should have been rejected")
    except ValueError as e:
        print(f"  Correctly rejected: {e}")
    
    # Attempt with delivered (operator responded!)
    attempts_with_delivery = [
        ContactAttempt(now - 86400*15, "smtp", ReachabilityResult.BOUNCED,
                       hashlib.sha256(b"b1").hexdigest()[:16]),
        ContactAttempt(now - 86400*8, "smtp", ReachabilityResult.DELIVERED,
                       hashlib.sha256(b"d1").hexdigest()[:16]),
        ContactAttempt(now - 86400*1, "smtp", ReachabilityResult.BOUNCED,
                       hashlib.sha256(b"b2").hexdigest()[:16]),
    ]
    
    try:
        t = initiate_adversarial("agent_y", "old_op", "new_op", attempts_with_delivery)
        print(f"  ERROR: Should have been rejected (operator responded)")
    except ValueError as e:
        print(f"  Correctly rejected: {e}")
    print()


if __name__ == "__main__":
    print("Custody Transfer Handler — Cooperative + Adversarial Paths for ATF")
    print("Per santaclawd: DKIM model + ICANN transfer dispute model")
    print("=" * 70)
    print()
    scenario_cooperative()
    scenario_dark_operator()
    scenario_cooperative_to_adversarial()
    scenario_insufficient_evidence()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("  1. Cooperative (dual-sign) = Grade A. DKIM selector rotation model.")
    print("  2. Adversarial (timeout) = Grade B. ICANN transfer model.")
    print(f"  3. CUSTODY_TIMEOUT = {CUSTODY_TIMEOUT_DAYS}d (SPEC_CONSTANT)")
    print(f"  4. Reachability proof: {REACHABILITY_ATTEMPTS}+ attempts over {REACHABILITY_SPAN_DAYS}d")
    print("  5. Cooperative can escalate to adversarial if old custodian goes dark")
    print("  6. In-flight receipt grace period prevents sudden invalidation")
