#!/usr/bin/env python3
"""
custody-transfer-handler.py — Dark operator custody transfer for ATF.

Per santaclawd: what if old operator goes DARK and can't countersign?
M3AAWG 2019: DKIM key rotation requires overlap period — new selector
published BEFORE old removed. Dark operator breaks this assumption.

Solution: CUSTODY_TIMEOUT as SPEC_CONSTANT. After timeout, new custodian
proves control unilaterally. Registry validates. Grace period spec-defined
not registry-configurable (configurable = race to bottom).

Three transfer modes:
  COOPERATIVE  — Both operators sign (normal DKIM rotation)
  UNILATERAL   — Old operator dark after CUSTODY_TIMEOUT (30d)
  EMERGENCY    — Key compromise, immediate with evidence
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# SPEC_CONSTANTS (not configurable)
CUSTODY_TIMEOUT_DAYS = 30       # Days before unilateral transfer allowed
EMERGENCY_EVIDENCE_MIN = 3      # Min evidence items for emergency transfer
OVERLAP_PERIOD_DAYS = 7         # Both selectors active during cooperative transfer
PROOF_OF_CONTROL_FIELDS = ["dns_txt_record", "operator_genesis_hash", "smtp_reachability"]
CHALLENGE_RESPONSE_TIMEOUT_H = 72  # Hours for old operator to respond to challenge


class TransferMode(Enum):
    COOPERATIVE = "COOPERATIVE"     # Both sign, orderly handoff
    UNILATERAL = "UNILATERAL"      # Old operator dark, timeout elapsed
    EMERGENCY = "EMERGENCY"         # Key compromise, immediate


class TransferState(Enum):
    PROPOSED = "PROPOSED"
    CHALLENGE_SENT = "CHALLENGE_SENT"
    CHALLENGE_EXPIRED = "CHALLENGE_EXPIRED"
    PROOF_SUBMITTED = "PROOF_SUBMITTED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    COMPLETE = "COMPLETE"


@dataclass
class Operator:
    operator_id: str
    genesis_hash: str
    last_seen: float            # Unix timestamp
    dns_selector: str
    smtp_reachable: bool = True
    is_dark: bool = False


@dataclass
class CustodyTransfer:
    transfer_id: str
    agent_id: str
    old_operator: Operator
    new_operator: Operator
    mode: TransferMode
    state: TransferState
    initiated_at: float
    evidence: list = field(default_factory=list)
    challenge_sent_at: Optional[float] = None
    challenge_response: Optional[str] = None
    proof_of_control: dict = field(default_factory=dict)
    completed_at: Optional[float] = None
    transfer_hash: Optional[str] = None


def is_operator_dark(op: Operator, now: float) -> bool:
    """Operator is dark if unreachable for CUSTODY_TIMEOUT."""
    days_since = (now - op.last_seen) / 86400
    return days_since >= CUSTODY_TIMEOUT_DAYS or not op.smtp_reachable


def determine_transfer_mode(old_op: Operator, evidence: list, now: float) -> TransferMode:
    """Determine appropriate transfer mode."""
    # Emergency: key compromise with evidence
    if len(evidence) >= EMERGENCY_EVIDENCE_MIN and any("compromise" in e.lower() for e in evidence):
        return TransferMode.EMERGENCY
    # Unilateral: operator dark
    if is_operator_dark(old_op, now):
        return TransferMode.UNILATERAL
    # Default: cooperative
    return TransferMode.COOPERATIVE


def validate_proof_of_control(proof: dict) -> tuple[bool, list]:
    """Validate new operator's proof of control."""
    errors = []
    for field_name in PROOF_OF_CONTROL_FIELDS:
        if field_name not in proof or not proof[field_name]:
            errors.append(f"Missing: {field_name}")
    
    # DNS TXT must match new operator genesis
    if proof.get("dns_txt_record") and proof.get("operator_genesis_hash"):
        expected = f"v=ATF1;operator={proof['operator_genesis_hash'][:16]}"
        if expected not in proof["dns_txt_record"].strip():
            errors.append("DNS TXT does not match operator genesis hash")
    
    return len(errors) == 0, errors


def compute_transfer_hash(transfer: CustodyTransfer) -> str:
    """Tamper-evident hash of the transfer record."""
    data = (
        f"{transfer.transfer_id}:{transfer.agent_id}:"
        f"{transfer.old_operator.operator_id}:{transfer.new_operator.operator_id}:"
        f"{transfer.mode.value}:{transfer.initiated_at}"
    )
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def process_transfer(transfer: CustodyTransfer, now: float) -> CustodyTransfer:
    """Process custody transfer through state machine."""
    
    if transfer.mode == TransferMode.COOPERATIVE:
        # Both operators must sign
        if transfer.state == TransferState.PROPOSED:
            transfer.state = TransferState.CHALLENGE_SENT
            transfer.challenge_sent_at = now
            return transfer
        
        if transfer.state == TransferState.CHALLENGE_SENT:
            if transfer.challenge_response == "ACCEPTED":
                transfer.state = TransferState.VALIDATED
            elif now - transfer.challenge_sent_at > CHALLENGE_RESPONSE_TIMEOUT_H * 3600:
                # Cooperative failed, escalate to unilateral
                transfer.mode = TransferMode.UNILATERAL
                transfer.state = TransferState.CHALLENGE_EXPIRED
            return transfer
    
    elif transfer.mode == TransferMode.UNILATERAL:
        # Old operator dark — validate proof of control
        if transfer.state in (TransferState.PROPOSED, TransferState.CHALLENGE_EXPIRED):
            valid, errors = validate_proof_of_control(transfer.proof_of_control)
            if valid:
                transfer.state = TransferState.VALIDATED
            else:
                transfer.state = TransferState.REJECTED
                transfer.evidence.extend([f"PROOF_FAILED: {e}" for e in errors])
            return transfer
    
    elif transfer.mode == TransferMode.EMERGENCY:
        # Immediate with evidence
        if len(transfer.evidence) >= EMERGENCY_EVIDENCE_MIN:
            valid, errors = validate_proof_of_control(transfer.proof_of_control)
            if valid:
                transfer.state = TransferState.VALIDATED
            else:
                transfer.state = TransferState.REJECTED
        else:
            transfer.state = TransferState.REJECTED
            transfer.evidence.append("INSUFFICIENT_EVIDENCE")
        return transfer
    
    if transfer.state == TransferState.VALIDATED:
        transfer.state = TransferState.COMPLETE
        transfer.completed_at = now
        transfer.transfer_hash = compute_transfer_hash(transfer)
    
    return transfer


# === Scenarios ===

def scenario_cooperative():
    """Normal transfer: both operators active."""
    print("=== Scenario: Cooperative Transfer ===")
    now = time.time()
    
    old_op = Operator("op_alice", "genesis_a1b2", now - 86400, "sel_alice", True)
    new_op = Operator("op_bob", "genesis_c3d4", now, "sel_bob", True)
    
    transfer = CustodyTransfer(
        "tx_001", "agent_kit", old_op, new_op,
        TransferMode.COOPERATIVE, TransferState.PROPOSED, now
    )
    
    # Step 1: Propose → Challenge
    transfer = process_transfer(transfer, now)
    print(f"  After propose: {transfer.state.value}")
    
    # Step 2: Old operator accepts
    transfer.challenge_response = "ACCEPTED"
    transfer = process_transfer(transfer, now)
    print(f"  After accept: {transfer.state.value}")
    
    # Step 3: Complete
    transfer = process_transfer(transfer, now)
    print(f"  Final: {transfer.state.value} hash={transfer.transfer_hash}")
    print(f"  M3AAWG overlap: both selectors active for {OVERLAP_PERIOD_DAYS}d")
    print()


def scenario_dark_operator():
    """Old operator goes dark — unilateral transfer after timeout."""
    print("=== Scenario: Dark Operator (Unilateral) ===")
    now = time.time()
    
    # Old operator last seen 45 days ago
    old_op = Operator("op_ghost", "genesis_dead", now - 86400*45, "sel_ghost", False, True)
    new_op = Operator("op_new", "genesis_new1", now, "sel_new", True)
    
    mode = determine_transfer_mode(old_op, [], now)
    print(f"  Mode detected: {mode.value} (last seen {45}d ago)")
    
    transfer = CustodyTransfer(
        "tx_002", "agent_orphan", old_op, new_op,
        mode, TransferState.PROPOSED, now,
        proof_of_control={
            "dns_txt_record": "v=ATF1;operator=genesis_new1    ",
            "operator_genesis_hash": "genesis_new1",
            "smtp_reachable": True
        }
    )
    
    transfer = process_transfer(transfer, now)
    print(f"  After proof: {transfer.state.value}")
    
    transfer = process_transfer(transfer, now)
    print(f"  Final: {transfer.state.value} hash={transfer.transfer_hash}")
    print(f"  CUSTODY_TIMEOUT={CUSTODY_TIMEOUT_DAYS}d (SPEC_CONSTANT, not configurable)")
    print()


def scenario_cooperative_escalation():
    """Cooperative fails → escalates to unilateral."""
    print("=== Scenario: Cooperative → Unilateral Escalation ===")
    now = time.time()
    
    old_op = Operator("op_slow", "genesis_slow", now - 86400*5, "sel_slow", True)
    new_op = Operator("op_eager", "genesis_eagr", now, "sel_eager", True)
    
    transfer = CustodyTransfer(
        "tx_003", "agent_waiting", old_op, new_op,
        TransferMode.COOPERATIVE, TransferState.PROPOSED, now
    )
    
    # Step 1: Send challenge
    transfer = process_transfer(transfer, now)
    print(f"  Challenge sent: {transfer.state.value}")
    
    # Step 2: No response, 72h passes
    transfer = process_transfer(transfer, now + CHALLENGE_RESPONSE_TIMEOUT_H * 3600 + 1)
    print(f"  After {CHALLENGE_RESPONSE_TIMEOUT_H}h timeout: {transfer.state.value} mode={transfer.mode.value}")
    
    # Step 3: Now unilateral with proof
    transfer.proof_of_control = {
        "dns_txt_record": "v=ATF1;operator=genesis_eagr    ",
        "operator_genesis_hash": "genesis_eagr",
        "smtp_reachable": True
    }
    transfer = process_transfer(transfer, now + 86400*4)
    print(f"  After proof: {transfer.state.value}")
    
    transfer = process_transfer(transfer, now + 86400*4)
    print(f"  Final: {transfer.state.value} hash={transfer.transfer_hash}")
    print()


def scenario_emergency():
    """Key compromise — immediate transfer with evidence."""
    print("=== Scenario: Emergency (Key Compromise) ===")
    now = time.time()
    
    old_op = Operator("op_compromised", "genesis_comp", now - 3600, "sel_comp", True)
    new_op = Operator("op_rescue", "genesis_resc", now, "sel_rescue", True)
    
    evidence = [
        "KEY_COMPROMISE: unauthorized receipts detected",
        "UNAUTHORIZED_GENESIS: new genesis filed without operator consent",
        "COMPROMISE_EVIDENCE: DNS selector modified by unknown party"
    ]
    
    mode = determine_transfer_mode(old_op, evidence, now)
    print(f"  Mode: {mode.value} ({len(evidence)} evidence items)")
    
    transfer = CustodyTransfer(
        "tx_004", "agent_rescued", old_op, new_op,
        mode, TransferState.PROPOSED, now,
        evidence=evidence,
        proof_of_control={
            "dns_txt_record": "v=ATF1;operator=genesis_resc    ",
            "operator_genesis_hash": "genesis_resc",
            "smtp_reachable": True
        }
    )
    
    transfer = process_transfer(transfer, now)
    print(f"  After evidence+proof: {transfer.state.value}")
    
    transfer = process_transfer(transfer, now)
    print(f"  Final: {transfer.state.value} hash={transfer.transfer_hash}")
    print(f"  Emergency bypasses {CUSTODY_TIMEOUT_DAYS}d timeout")
    print()


if __name__ == "__main__":
    print("Custody Transfer Handler — Dark Operator Recovery for ATF")
    print("Per santaclawd + M3AAWG DKIM Key Rotation BCP (March 2019)")
    print("=" * 65)
    print()
    scenario_cooperative()
    scenario_dark_operator()
    scenario_cooperative_escalation()
    scenario_emergency()
    
    print("=" * 65)
    print("SPEC_CONSTANTS (not configurable):")
    print(f"  CUSTODY_TIMEOUT = {CUSTODY_TIMEOUT_DAYS} days")
    print(f"  CHALLENGE_RESPONSE_TIMEOUT = {CHALLENGE_RESPONSE_TIMEOUT_H} hours")
    print(f"  EMERGENCY_EVIDENCE_MIN = {EMERGENCY_EVIDENCE_MIN} items")
    print(f"  OVERLAP_PERIOD = {OVERLAP_PERIOD_DAYS} days")
    print("KEY: configurable = race to bottom. spec-defined = security floor.")
