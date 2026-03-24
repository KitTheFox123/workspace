#!/usr/bin/env python3
"""
custody-transfer-receipt.py — Operator custody transfer for ATF agents.

Per santaclawd: "what happens when an agent migrates operators? genesis is
immutable — but key_custodian changed."

DKIM model: new selector published, old stays in DNS during TTL overlap.
Peppol PKI 2025: dual-cert coexistence window during CA migration.

Custody transfer = signed handoff receipt:
  1. Old operator signs TRANSFER_INITIATE (I am releasing agent X)
  2. New operator signs TRANSFER_ACCEPT (I am accepting agent X)
  3. Both signatures + agent_id + handoff_hash → CUSTODY_TRANSFER receipt
  4. Old genesis stays valid during overlap_window
  5. After overlap: old genesis marked SUPERSEDED (not REVOKED — history preserved)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class TransferState(Enum):
    INITIATED = "INITIATED"       # Old operator signed release
    ACCEPTED = "ACCEPTED"         # New operator signed acceptance
    ACTIVE = "ACTIVE"             # Overlap window — both valid
    COMPLETED = "COMPLETED"       # Old genesis SUPERSEDED
    REJECTED = "REJECTED"         # New operator refused
    EXPIRED = "EXPIRED"           # Overlap window passed without completion
    DISPUTED = "DISPUTED"         # Disagreement during transfer


# SPEC_CONSTANTS
OVERLAP_WINDOW_HOURS = 72       # Dual-validity window (Peppol uses 30 days)
MIN_OVERLAP_HOURS = 24          # Minimum overlap (agent must have continuity)
MAX_OVERLAP_HOURS = 720         # 30 days max (matches Peppol)
TRANSFER_TIMEOUT_HOURS = 168    # 7 days to accept before EXPIRED


@dataclass
class OperatorGenesis:
    operator_id: str
    operator_name: str
    genesis_hash: str
    created_at: float
    status: str = "ACTIVE"  # ACTIVE, SUPERSEDED, REVOKED


@dataclass
class CustodyTransferReceipt:
    """Bilateral custody transfer receipt."""
    transfer_id: str
    agent_id: str
    old_operator: OperatorGenesis
    new_operator: OperatorGenesis
    state: TransferState
    initiated_at: float
    accepted_at: Optional[float] = None
    completed_at: Optional[float] = None
    overlap_window_hours: int = OVERLAP_WINDOW_HOURS
    handoff_hash: str = ""  # hash(old_genesis + new_genesis + agent_id)
    old_operator_signature: str = ""  # Simulated
    new_operator_signature: str = ""  # Simulated
    custody_chain: list = field(default_factory=list)  # History of all operators
    reason: str = ""

    def __post_init__(self):
        if not self.handoff_hash:
            self.handoff_hash = self._compute_handoff_hash()

    def _compute_handoff_hash(self) -> str:
        data = f"{self.old_operator.genesis_hash}:{self.new_operator.genesis_hash}:{self.agent_id}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


def initiate_transfer(agent_id: str, old_op: OperatorGenesis,
                       new_op: OperatorGenesis, reason: str = "") -> CustodyTransferReceipt:
    """Old operator initiates custody transfer."""
    now = time.time()
    transfer_id = hashlib.sha256(f"{agent_id}:{now}".encode()).hexdigest()[:12]

    receipt = CustodyTransferReceipt(
        transfer_id=transfer_id,
        agent_id=agent_id,
        old_operator=old_op,
        new_operator=new_op,
        state=TransferState.INITIATED,
        initiated_at=now,
        reason=reason,
        old_operator_signature=f"sig_old_{transfer_id[:8]}",
        custody_chain=[old_op.operator_id]
    )
    return receipt


def accept_transfer(receipt: CustodyTransferReceipt) -> CustodyTransferReceipt:
    """New operator accepts custody transfer. Overlap window begins."""
    if receipt.state != TransferState.INITIATED:
        raise ValueError(f"Cannot accept transfer in state {receipt.state}")

    now = time.time()
    elapsed_hours = (now - receipt.initiated_at) / 3600

    if elapsed_hours > TRANSFER_TIMEOUT_HOURS:
        receipt.state = TransferState.EXPIRED
        return receipt

    receipt.accepted_at = now
    receipt.state = TransferState.ACTIVE  # Both operators valid
    receipt.new_operator_signature = f"sig_new_{receipt.transfer_id[:8]}"
    receipt.custody_chain.append(receipt.new_operator.operator_id)
    return receipt


def complete_transfer(receipt: CustodyTransferReceipt) -> CustodyTransferReceipt:
    """Complete transfer after overlap window. Old genesis → SUPERSEDED."""
    if receipt.state != TransferState.ACTIVE:
        raise ValueError(f"Cannot complete transfer in state {receipt.state}")

    now = time.time()
    if receipt.accepted_at is None:
        raise ValueError("Transfer not yet accepted")

    elapsed_hours = (now - receipt.accepted_at) / 3600

    if elapsed_hours < MIN_OVERLAP_HOURS:
        print(f"  WARNING: Only {elapsed_hours:.1f}h elapsed, minimum is {MIN_OVERLAP_HOURS}h")
        # Allow but warn

    receipt.completed_at = now
    receipt.state = TransferState.COMPLETED
    receipt.old_operator.status = "SUPERSEDED"  # NOT revoked — history preserved
    return receipt


def validate_transfer(receipt: CustodyTransferReceipt) -> dict:
    """Validate custody transfer receipt integrity."""
    issues = []
    grade = "A"

    # Check handoff hash
    expected = receipt._compute_handoff_hash()
    if receipt.handoff_hash != expected:
        issues.append("HANDOFF_HASH_MISMATCH")
        grade = "F"

    # Check signatures present
    if not receipt.old_operator_signature:
        issues.append("MISSING_OLD_OPERATOR_SIGNATURE")
        grade = "F"
    if receipt.state in (TransferState.ACTIVE, TransferState.COMPLETED):
        if not receipt.new_operator_signature:
            issues.append("MISSING_NEW_OPERATOR_SIGNATURE")
            grade = "F"

    # Check self-transfer (same operator = suspicious)
    if receipt.old_operator.operator_id == receipt.new_operator.operator_id:
        issues.append("SELF_TRANSFER_DETECTED")
        grade = "D"

    # Check custody chain continuity
    if len(receipt.custody_chain) > 0:
        if receipt.custody_chain[0] != receipt.old_operator.operator_id:
            issues.append("CUSTODY_CHAIN_DISCONTINUITY")
            grade = "D"

    # Check overlap window bounds
    if receipt.overlap_window_hours < MIN_OVERLAP_HOURS:
        issues.append(f"OVERLAP_BELOW_MINIMUM ({receipt.overlap_window_hours}h < {MIN_OVERLAP_HOURS}h)")
        grade = "D"
    if receipt.overlap_window_hours > MAX_OVERLAP_HOURS:
        issues.append(f"OVERLAP_ABOVE_MAXIMUM ({receipt.overlap_window_hours}h > {MAX_OVERLAP_HOURS}h)")
        grade = "D"

    # SUPERSEDED vs REVOKED check
    if receipt.state == TransferState.COMPLETED:
        if receipt.old_operator.status == "REVOKED":
            issues.append("OLD_OPERATOR_REVOKED_NOT_SUPERSEDED — history should be preserved")
            if grade > "C":
                grade = "C"

    if not issues:
        issues = ["CLEAN"]

    return {
        "transfer_id": receipt.transfer_id,
        "state": receipt.state.value,
        "grade": grade,
        "issues": issues,
        "handoff_hash": receipt.handoff_hash,
        "custody_chain_length": len(receipt.custody_chain),
        "signatures": {
            "old_operator": bool(receipt.old_operator_signature),
            "new_operator": bool(receipt.new_operator_signature)
        }
    }


# === Scenarios ===

def scenario_clean_transfer():
    """Normal operator migration."""
    print("=== Scenario: Clean Custody Transfer ===")
    old_op = OperatorGenesis("op_alpha", "Alpha Corp", "genesis_aaa111", time.time() - 86400*90)
    new_op = OperatorGenesis("op_beta", "Beta Labs", "genesis_bbb222", time.time())

    receipt = initiate_transfer("kit_fox", old_op, new_op, reason="operator_migration")
    print(f"  Initiated: {receipt.state.value}")

    receipt = accept_transfer(receipt)
    print(f"  Accepted: {receipt.state.value} (overlap window started)")

    receipt = complete_transfer(receipt)
    print(f"  Completed: {receipt.state.value}")
    print(f"  Old operator status: {receipt.old_operator.status}")
    print(f"  Custody chain: {receipt.custody_chain}")

    result = validate_transfer(receipt)
    print(f"  Validation: Grade {result['grade']}, {result['issues']}")
    print()


def scenario_self_transfer():
    """Same operator on both sides = suspicious."""
    print("=== Scenario: Self-Transfer (Suspicious) ===")
    op = OperatorGenesis("op_shady", "Shady Inc", "genesis_xxx", time.time())
    new_op = OperatorGenesis("op_shady", "Shady Inc v2", "genesis_yyy", time.time())

    receipt = initiate_transfer("sybil_agent", op, new_op)
    receipt = accept_transfer(receipt)
    receipt = complete_transfer(receipt)

    result = validate_transfer(receipt)
    print(f"  Validation: Grade {result['grade']}, {result['issues']}")
    print()


def scenario_rejected_transfer():
    """New operator refuses custody."""
    print("=== Scenario: Rejected Transfer ===")
    old_op = OperatorGenesis("op_alpha", "Alpha Corp", "genesis_aaa", time.time())
    new_op = OperatorGenesis("op_gamma", "Gamma Ltd", "genesis_ggg", time.time())

    receipt = initiate_transfer("agent_x", old_op, new_op)
    receipt.state = TransferState.REJECTED
    receipt.new_operator_signature = ""

    result = validate_transfer(receipt)
    print(f"  State: {receipt.state.value}")
    print(f"  Old operator status: {receipt.old_operator.status} (unchanged — still ACTIVE)")
    print(f"  Validation: Grade {result['grade']}, {result['issues']}")
    print()


def scenario_multi_hop_custody():
    """Agent transferred through 3 operators — full chain."""
    print("=== Scenario: Multi-Hop Custody Chain ===")
    ops = [
        OperatorGenesis("op_1", "Original", "gen_001", time.time() - 86400*180),
        OperatorGenesis("op_2", "Second", "gen_002", time.time() - 86400*90),
        OperatorGenesis("op_3", "Current", "gen_003", time.time()),
    ]

    # First transfer
    r1 = initiate_transfer("agent_y", ops[0], ops[1], "acquisition")
    r1 = accept_transfer(r1)
    r1 = complete_transfer(r1)

    # Second transfer
    r2 = initiate_transfer("agent_y", ops[1], ops[2], "restructuring")
    r2.custody_chain = r1.custody_chain.copy()  # Carry forward chain
    r2 = accept_transfer(r2)
    r2 = complete_transfer(r2)

    print(f"  Full custody chain: {r2.custody_chain}")
    print(f"  Operator statuses: {[o.status for o in ops]}")
    result = validate_transfer(r2)
    print(f"  Validation: Grade {result['grade']}, {result['issues']}")
    print(f"  Key: SUPERSEDED not REVOKED — provenance preserved")
    print()


if __name__ == "__main__":
    print("Custody Transfer Receipt — ATF Operator Migration")
    print("Per santaclawd: genesis is immutable, custody is not")
    print("DKIM model: old selector stays during TTL overlap")
    print("=" * 60)
    print()
    scenario_clean_transfer()
    scenario_self_transfer()
    scenario_rejected_transfer()
    scenario_multi_hop_custody()
    print("=" * 60)
    print("KEY: SUPERSEDED not REVOKED. History is provenance.")
    print("Overlap window (72h default) = DKIM selector coexistence.")
    print("Self-transfer detected. Custody chain = audit trail.")
