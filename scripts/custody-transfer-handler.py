#!/usr/bin/env python3
"""
custody-transfer-handler.py — Operator succession for ATF genesis receipts.

Per santaclawd: CUSTODY_TRANSFER ≠ reanchor. Succession, not identity change.
DKIM key rotation (M3AAWG 2019): new selector published BEFORE old removed.
ICANN Transfer Policy: 5-day ACK window, silence = consent to transfer.

Dark operator path: old custodian unresponsive → timeout → unilateral transfer
with proof-of-control + registry witness.

Three transfer modes:
  COOPERATIVE  — Both sign overlap window (DKIM rotation model)
  TIMEOUT      — Old custodian dark, 30d timeout, proof-of-control
  EMERGENCY    — Key compromise, immediate with registry witness quorum
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# SPEC_CONSTANTS (not impl-defined — DigiNoort lesson)
CUSTODY_TIMEOUT_DAYS = 30       # Dark operator timeout
OVERLAP_WINDOW_DAYS = 7         # Dual-signature overlap (M3AAWG: 2x TTL)
EMERGENCY_QUORUM = 3            # Registry witnesses for emergency transfer
ACK_WINDOW_DAYS = 5             # ICANN model: silence = consent after 5 days
PROOF_OF_CONTROL_METHODS = ["smtp_reachable", "dns_txt", "operator_genesis_hash"]


class TransferMode(Enum):
    COOPERATIVE = "COOPERATIVE"   # Both custodians sign
    TIMEOUT = "TIMEOUT"           # Old custodian dark
    EMERGENCY = "EMERGENCY"       # Key compromise


class TransferState(Enum):
    INITIATED = "INITIATED"       # New custodian requests
    ACK_PENDING = "ACK_PENDING"   # Waiting for old custodian ACK
    OVERLAP = "OVERLAP"           # Both active (dual-signature window)
    COMPLETED = "COMPLETED"       # Transfer done
    TIMEOUT_PENDING = "TIMEOUT_PENDING"  # Old custodian dark, counting down
    EMERGENCY_REVIEW = "EMERGENCY_REVIEW"  # Registry witness quorum
    REJECTED = "REJECTED"         # Old custodian explicitly rejected
    FAILED = "FAILED"             # Transfer failed


@dataclass
class CustodyTransfer:
    agent_id: str
    old_operator_id: str
    new_operator_id: str
    mode: TransferMode
    state: TransferState
    initiated_at: float
    old_ack_at: Optional[float] = None
    overlap_start: Optional[float] = None
    completed_at: Optional[float] = None
    proof_of_control: list = field(default_factory=list)
    witness_signatures: list = field(default_factory=list)
    transfer_hash: str = ""
    
    def __post_init__(self):
        h = hashlib.sha256(
            f"{self.agent_id}:{self.old_operator_id}:{self.new_operator_id}:{self.initiated_at}"
            .encode()
        ).hexdigest()[:16]
        self.transfer_hash = h


@dataclass 
class TransferResult:
    transfer: CustodyTransfer
    grade: str
    warnings: list
    receipt_chain_status: str  # PRESERVED / TAINTED / BROKEN


def validate_proof_of_control(proofs: list[str]) -> tuple[bool, list[str]]:
    """Validate proof-of-control methods."""
    valid = []
    for p in proofs:
        if p in PROOF_OF_CONTROL_METHODS:
            valid.append(p)
    # Need at least 2 different methods
    return len(valid) >= 2, valid


def process_cooperative_transfer(transfer: CustodyTransfer) -> TransferResult:
    """
    COOPERATIVE: Both custodians available.
    DKIM model: new selector published, overlap window, old selector removed.
    """
    warnings = []
    
    if transfer.old_ack_at is None:
        return TransferResult(transfer, "F", ["Old custodian has not acknowledged"], "BROKEN")
    
    # Check overlap window
    if transfer.overlap_start is None:
        warnings.append("No overlap window — receipts during transition may be unverifiable")
        chain_status = "TAINTED"
    else:
        overlap_duration = (transfer.completed_at or time.time()) - transfer.overlap_start
        overlap_days = overlap_duration / 86400
        if overlap_days < OVERLAP_WINDOW_DAYS:
            warnings.append(f"Overlap {overlap_days:.1f}d < {OVERLAP_WINDOW_DAYS}d minimum")
            chain_status = "TAINTED"
        else:
            chain_status = "PRESERVED"
    
    # Both signed = Grade A
    grade = "A" if not warnings else "B"
    return TransferResult(transfer, grade, warnings, chain_status)


def process_timeout_transfer(transfer: CustodyTransfer) -> TransferResult:
    """
    TIMEOUT: Old custodian dark (unresponsive).
    ICANN model: 5-day ACK window, then countdown to CUSTODY_TIMEOUT.
    """
    warnings = []
    now = time.time()
    
    # Check if ACK window expired
    ack_deadline = transfer.initiated_at + (ACK_WINDOW_DAYS * 86400)
    if now < ack_deadline:
        return TransferResult(transfer, "F", 
            [f"ACK window not expired ({ACK_WINDOW_DAYS}d). Wait."], "BROKEN")
    
    # Check if timeout expired
    timeout_deadline = transfer.initiated_at + (CUSTODY_TIMEOUT_DAYS * 86400)
    if now < timeout_deadline:
        days_remaining = (timeout_deadline - now) / 86400
        return TransferResult(transfer, "F",
            [f"Timeout not expired. {days_remaining:.1f}d remaining."], "BROKEN")
    
    # Validate proof of control
    valid, methods = validate_proof_of_control(transfer.proof_of_control)
    if not valid:
        warnings.append(f"Insufficient proof-of-control: {methods}. Need 2+ methods.")
        return TransferResult(transfer, "F", warnings, "BROKEN")
    
    # Timeout transfer = Grade C (weaker than cooperative)
    warnings.append("Unilateral transfer — old custodian unresponsive")
    warnings.append(f"Proof-of-control: {methods}")
    return TransferResult(transfer, "C", warnings, "TAINTED")


def process_emergency_transfer(transfer: CustodyTransfer) -> TransferResult:
    """
    EMERGENCY: Key compromise. Immediate with registry witness quorum.
    """
    warnings = []
    
    # Check witness quorum
    if len(transfer.witness_signatures) < EMERGENCY_QUORUM:
        return TransferResult(transfer, "F",
            [f"Insufficient witnesses: {len(transfer.witness_signatures)}/{EMERGENCY_QUORUM}"],
            "BROKEN")
    
    # Validate proof of control
    valid, methods = validate_proof_of_control(transfer.proof_of_control)
    if not valid:
        return TransferResult(transfer, "F",
            [f"Insufficient proof-of-control: {methods}"], "BROKEN")
    
    warnings.append("Emergency transfer — key compromise suspected")
    warnings.append(f"Witnesses: {len(transfer.witness_signatures)}")
    warnings.append(f"Proof-of-control: {methods}")
    
    # Emergency = Grade B (quorum compensates for no cooperation)
    return TransferResult(transfer, "B", warnings, "TAINTED")


def process_transfer(transfer: CustodyTransfer) -> TransferResult:
    """Route to appropriate transfer handler."""
    if transfer.mode == TransferMode.COOPERATIVE:
        return process_cooperative_transfer(transfer)
    elif transfer.mode == TransferMode.TIMEOUT:
        return process_timeout_transfer(transfer)
    elif transfer.mode == TransferMode.EMERGENCY:
        return process_emergency_transfer(transfer)
    else:
        return TransferResult(transfer, "F", ["Unknown transfer mode"], "BROKEN")


# === Scenarios ===

def scenario_cooperative():
    """Clean cooperative transfer — both custodians sign."""
    print("=== Scenario: Cooperative Transfer (DKIM Rotation Model) ===")
    now = time.time()
    
    t = CustodyTransfer(
        agent_id="kit_fox",
        old_operator_id="operator_alpha",
        new_operator_id="operator_beta",
        mode=TransferMode.COOPERATIVE,
        state=TransferState.COMPLETED,
        initiated_at=now - 86400*14,
        old_ack_at=now - 86400*13,
        overlap_start=now - 86400*10,
        completed_at=now - 86400*3,
    )
    
    result = process_transfer(t)
    print(f"  Grade: {result.grade}")
    print(f"  Chain: {result.receipt_chain_status}")
    print(f"  Warnings: {result.warnings}")
    print()


def scenario_dark_operator():
    """Old operator unresponsive — timeout path."""
    print("=== Scenario: Dark Operator (ICANN Timeout Model) ===")
    now = time.time()
    
    t = CustodyTransfer(
        agent_id="orphaned_agent",
        old_operator_id="dark_operator",
        new_operator_id="rescue_operator",
        mode=TransferMode.TIMEOUT,
        state=TransferState.TIMEOUT_PENDING,
        initiated_at=now - 86400*35,  # 35 days ago (past 30d timeout)
        proof_of_control=["smtp_reachable", "dns_txt"],
    )
    
    result = process_transfer(t)
    print(f"  Grade: {result.grade}")
    print(f"  Chain: {result.receipt_chain_status}")
    print(f"  Warnings: {result.warnings}")
    print()


def scenario_dark_operator_too_early():
    """Timeout not yet expired."""
    print("=== Scenario: Dark Operator (Too Early) ===")
    now = time.time()
    
    t = CustodyTransfer(
        agent_id="impatient_agent",
        old_operator_id="slow_operator",
        new_operator_id="eager_operator",
        mode=TransferMode.TIMEOUT,
        state=TransferState.TIMEOUT_PENDING,
        initiated_at=now - 86400*10,  # Only 10 days ago
        proof_of_control=["smtp_reachable", "dns_txt"],
    )
    
    result = process_transfer(t)
    print(f"  Grade: {result.grade}")
    print(f"  Chain: {result.receipt_chain_status}")
    print(f"  Warnings: {result.warnings}")
    print()


def scenario_emergency():
    """Key compromise — emergency with witness quorum."""
    print("=== Scenario: Emergency Transfer (Key Compromise) ===")
    now = time.time()
    
    t = CustodyTransfer(
        agent_id="compromised_agent",
        old_operator_id="hacked_operator",
        new_operator_id="clean_operator",
        mode=TransferMode.EMERGENCY,
        state=TransferState.EMERGENCY_REVIEW,
        initiated_at=now - 86400*1,
        proof_of_control=["smtp_reachable", "operator_genesis_hash"],
        witness_signatures=["witness_1", "witness_2", "witness_3"],
    )
    
    result = process_transfer(t)
    print(f"  Grade: {result.grade}")
    print(f"  Chain: {result.receipt_chain_status}")
    print(f"  Warnings: {result.warnings}")
    print()


def scenario_insufficient_proof():
    """Timeout transfer but only one proof method."""
    print("=== Scenario: Insufficient Proof-of-Control ===")
    now = time.time()
    
    t = CustodyTransfer(
        agent_id="weak_claim_agent",
        old_operator_id="dark_op",
        new_operator_id="claimant",
        mode=TransferMode.TIMEOUT,
        state=TransferState.TIMEOUT_PENDING,
        initiated_at=now - 86400*35,
        proof_of_control=["smtp_reachable"],  # Only 1 method
    )
    
    result = process_transfer(t)
    print(f"  Grade: {result.grade}")
    print(f"  Chain: {result.receipt_chain_status}")
    print(f"  Warnings: {result.warnings}")
    print()


if __name__ == "__main__":
    print("Custody Transfer Handler — Operator Succession for ATF")
    print("Per santaclawd: CUSTODY_TRANSFER ≠ reanchor. Succession not identity change.")
    print("DKIM rotation (M3AAWG 2019) + ICANN Transfer Policy models.")
    print("=" * 70)
    print()
    scenario_cooperative()
    scenario_dark_operator()
    scenario_dark_operator_too_early()
    scenario_emergency()
    scenario_insufficient_proof()
    
    print("=" * 70)
    print("SPEC_CONSTANTS:")
    print(f"  CUSTODY_TIMEOUT = {CUSTODY_TIMEOUT_DAYS}d")
    print(f"  OVERLAP_WINDOW = {OVERLAP_WINDOW_DAYS}d")
    print(f"  ACK_WINDOW = {ACK_WINDOW_DAYS}d (ICANN model)")
    print(f"  EMERGENCY_QUORUM = {EMERGENCY_QUORUM} witnesses")
    print(f"  PROOF_METHODS = {PROOF_OF_CONTROL_METHODS}")
    print()
    print("KEY: timeout N = SPEC_CONSTANT not registry-configurable.")
    print("impl-defined timeouts = DigiNoort repeated.")
