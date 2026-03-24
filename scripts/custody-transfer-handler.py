#!/usr/bin/env python3
"""
custody-transfer-handler.py — DKIM selector rotation model for ATF operator migration.

Per santaclawd: "what happens when an agent migrates operators? genesis is immutable
but key_custodian changed."

DKIM answer (M3AAWG 2019): new selector published BEFORE old expires. Overlap window.
Both keys valid during transition. Old key revoked after TTL.

ATF equivalent:
  1. New operator publishes genesis with predecessor_hash pointing to old
  2. Old operator co-signs CUSTODY_TRANSFER receipt
  3. Overlap window: both genesis records active (old=DEPRECATED, new=ACTIVE)
  4. After TTL: old genesis = REVOKED, new genesis = sole authority

Three custody modes (genesis field):
  OPERATOR_HELD — Provider hosts signing key (DKIM default)
  AGENT_HELD    — Agent holds own key (autonomous, risky)
  HSM_MANAGED   — Hardware-bound key (highest assurance)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class CustodyMode(Enum):
    OPERATOR_HELD = "OPERATOR_HELD"
    AGENT_HELD = "AGENT_HELD"
    HSM_MANAGED = "HSM_MANAGED"


class TransferState(Enum):
    PROPOSED = "PROPOSED"       # New operator announced intent
    CO_SIGNED = "CO_SIGNED"     # Both operators signed transfer
    OVERLAP = "OVERLAP"         # Both genesis active (DKIM dual-selector)
    COMPLETED = "COMPLETED"     # Old revoked, new sole authority
    REJECTED = "REJECTED"       # Transfer refused
    ABANDONED = "ABANDONED"     # Timed out without co-sign


# SPEC_CONSTANTS
OVERLAP_WINDOW_HOURS = 72       # Both selectors active
CO_SIGN_DEADLINE_HOURS = 24     # Old operator must co-sign within this
MINIMUM_OVERLAP_HOURS = 24      # Cannot rush transfer below this


@dataclass
class GenesisRecord:
    agent_id: str
    operator_id: str
    genesis_hash: str
    custody_mode: CustodyMode
    key_fingerprint: str
    predecessor_hash: Optional[str] = None
    state: str = "ACTIVE"
    created_at: float = field(default_factory=time.time)


@dataclass
class CustodyTransferReceipt:
    """Signed by BOTH old and new operator."""
    agent_id: str
    old_operator_id: str
    new_operator_id: str
    old_genesis_hash: str
    new_genesis_hash: str
    old_operator_signature: Optional[str] = None
    new_operator_signature: Optional[str] = None
    transfer_state: TransferState = TransferState.PROPOSED
    proposed_at: float = field(default_factory=time.time)
    co_signed_at: Optional[float] = None
    completed_at: Optional[float] = None
    overlap_start: Optional[float] = None
    overlap_end: Optional[float] = None


def hash_genesis(record: GenesisRecord) -> str:
    """Deterministic hash of genesis fields."""
    data = f"{record.agent_id}:{record.operator_id}:{record.custody_mode.value}:{record.key_fingerprint}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def propose_transfer(agent_id: str, old_genesis: GenesisRecord,
                     new_operator_id: str, new_custody_mode: CustodyMode,
                     new_key_fingerprint: str) -> tuple[GenesisRecord, CustodyTransferReceipt]:
    """Step 1: New operator proposes transfer."""
    new_genesis = GenesisRecord(
        agent_id=agent_id,
        operator_id=new_operator_id,
        genesis_hash="pending",
        custody_mode=new_custody_mode,
        key_fingerprint=new_key_fingerprint,
        predecessor_hash=old_genesis.genesis_hash,
        state="PROPOSED"
    )
    new_genesis.genesis_hash = hash_genesis(new_genesis)
    
    receipt = CustodyTransferReceipt(
        agent_id=agent_id,
        old_operator_id=old_genesis.operator_id,
        new_operator_id=new_operator_id,
        old_genesis_hash=old_genesis.genesis_hash,
        new_genesis_hash=new_genesis.genesis_hash,
        new_operator_signature=f"sig_{new_operator_id}_{new_genesis.genesis_hash[:8]}",
        transfer_state=TransferState.PROPOSED
    )
    
    return new_genesis, receipt


def co_sign_transfer(receipt: CustodyTransferReceipt, old_genesis: GenesisRecord) -> CustodyTransferReceipt:
    """Step 2: Old operator co-signs (DKIM: publish new selector)."""
    elapsed_hours = (time.time() - receipt.proposed_at) / 3600
    
    if elapsed_hours > CO_SIGN_DEADLINE_HOURS:
        receipt.transfer_state = TransferState.ABANDONED
        return receipt
    
    receipt.old_operator_signature = f"sig_{old_genesis.operator_id}_{old_genesis.genesis_hash[:8]}"
    receipt.co_signed_at = time.time()
    receipt.transfer_state = TransferState.CO_SIGNED
    
    return receipt


def begin_overlap(receipt: CustodyTransferReceipt, old_genesis: GenesisRecord,
                  new_genesis: GenesisRecord) -> tuple[GenesisRecord, GenesisRecord, CustodyTransferReceipt]:
    """Step 3: Both genesis records active (DKIM dual-selector window)."""
    if receipt.transfer_state != TransferState.CO_SIGNED:
        raise ValueError(f"Cannot begin overlap from state {receipt.transfer_state}")
    
    old_genesis.state = "DEPRECATED"
    new_genesis.state = "ACTIVE"
    
    receipt.transfer_state = TransferState.OVERLAP
    receipt.overlap_start = time.time()
    receipt.overlap_end = receipt.overlap_start + (OVERLAP_WINDOW_HOURS * 3600)
    
    return old_genesis, new_genesis, receipt


def complete_transfer(receipt: CustodyTransferReceipt, old_genesis: GenesisRecord,
                      new_genesis: GenesisRecord) -> tuple[GenesisRecord, GenesisRecord, CustodyTransferReceipt]:
    """Step 4: Old genesis revoked, new is sole authority."""
    if receipt.transfer_state != TransferState.OVERLAP:
        raise ValueError(f"Cannot complete from state {receipt.transfer_state}")
    
    # Check minimum overlap
    if receipt.overlap_start:
        overlap_hours = (time.time() - receipt.overlap_start) / 3600
        if overlap_hours < MINIMUM_OVERLAP_HOURS:
            raise ValueError(f"Minimum overlap {MINIMUM_OVERLAP_HOURS}h not met ({overlap_hours:.1f}h)")
    
    old_genesis.state = "REVOKED"
    new_genesis.state = "ACTIVE"
    
    receipt.transfer_state = TransferState.COMPLETED
    receipt.completed_at = time.time()
    
    return old_genesis, new_genesis, receipt


def validate_transfer_chain(genesis_records: list[GenesisRecord]) -> dict:
    """Validate custody chain integrity."""
    issues = []
    
    # Check predecessor chain
    for i, g in enumerate(genesis_records[1:], 1):
        if g.predecessor_hash != genesis_records[i-1].genesis_hash:
            issues.append(f"Chain break at index {i}: predecessor_hash mismatch")
    
    # Check only one ACTIVE
    active = [g for g in genesis_records if g.state == "ACTIVE"]
    if len(active) > 1:
        issues.append(f"Multiple ACTIVE genesis records: {[g.genesis_hash for g in active]}")
    elif len(active) == 0:
        issues.append("No ACTIVE genesis record")
    
    # Check custody mode transitions
    for i, g in enumerate(genesis_records[1:], 1):
        old_mode = genesis_records[i-1].custody_mode
        new_mode = g.custody_mode
        # Downgrade warning: HSM → OPERATOR or AGENT → OPERATOR
        if old_mode == CustodyMode.HSM_MANAGED and new_mode != CustodyMode.HSM_MANAGED:
            issues.append(f"Custody downgrade at index {i}: {old_mode.value} → {new_mode.value}")
    
    return {
        "chain_length": len(genesis_records),
        "active_count": len(active),
        "issues": issues,
        "integrity": "VALID" if not issues else "ISSUES_DETECTED",
        "current_operator": active[0].operator_id if active else "NONE",
        "current_custody": active[0].custody_mode.value if active else "NONE"
    }


# === Scenarios ===

def scenario_clean_transfer():
    """Normal operator migration with co-sign."""
    print("=== Scenario: Clean Operator Migration ===")
    
    old = GenesisRecord("kit_fox", "operator_A", "", CustodyMode.OPERATOR_HELD, "fp_old_001")
    old.genesis_hash = hash_genesis(old)
    
    new_gen, receipt = propose_transfer("kit_fox", old, "operator_B",
                                         CustodyMode.OPERATOR_HELD, "fp_new_002")
    print(f"  1. PROPOSED: {old.operator_id} → {new_gen.operator_id}")
    print(f"     predecessor_hash: {new_gen.predecessor_hash}")
    
    receipt = co_sign_transfer(receipt, old)
    print(f"  2. CO_SIGNED: both operators signed")
    print(f"     old_sig: {receipt.old_operator_signature}")
    print(f"     new_sig: {receipt.new_operator_signature}")
    
    old, new_gen, receipt = begin_overlap(receipt, old, new_gen)
    print(f"  3. OVERLAP: old={old.state}, new={new_gen.state}")
    print(f"     window: {OVERLAP_WINDOW_HOURS}h")
    
    # Simulate overlap passing
    receipt.overlap_start = time.time() - (MINIMUM_OVERLAP_HOURS * 3600 + 1)
    old, new_gen, receipt = complete_transfer(receipt, old, new_gen)
    print(f"  4. COMPLETED: old={old.state}, new={new_gen.state}")
    
    chain = validate_transfer_chain([old, new_gen])
    print(f"  Chain: {chain['integrity']}, operator={chain['current_operator']}")
    print()


def scenario_refused_transfer():
    """Old operator refuses to co-sign."""
    print("=== Scenario: Refused Transfer (No Co-Sign) ===")
    
    old = GenesisRecord("agent_x", "hostile_op", "", CustodyMode.OPERATOR_HELD, "fp_001")
    old.genesis_hash = hash_genesis(old)
    
    new_gen, receipt = propose_transfer("agent_x", old, "new_op",
                                         CustodyMode.AGENT_HELD, "fp_002")
    print(f"  1. PROPOSED: {old.operator_id} → new_op")
    
    # Simulate deadline expiry
    receipt.proposed_at = time.time() - (CO_SIGN_DEADLINE_HOURS * 3600 + 1)
    receipt = co_sign_transfer(receipt, old)
    print(f"  2. State: {receipt.transfer_state.value}")
    print(f"  Result: Transfer ABANDONED. Agent stuck with hostile_op.")
    print(f"  DKIM parallel: domain owner refuses selector rotation = email stuck.")
    print()


def scenario_custody_upgrade():
    """Upgrade from OPERATOR_HELD to HSM_MANAGED."""
    print("=== Scenario: Custody Upgrade (Operator → HSM) ===")
    
    old = GenesisRecord("secure_agent", "op_basic", "", CustodyMode.OPERATOR_HELD, "fp_soft")
    old.genesis_hash = hash_genesis(old)
    
    new_gen, receipt = propose_transfer("secure_agent", old, "op_premium",
                                         CustodyMode.HSM_MANAGED, "fp_hsm_001")
    receipt = co_sign_transfer(receipt, old)
    old, new_gen, receipt = begin_overlap(receipt, old, new_gen)
    receipt.overlap_start = time.time() - (MINIMUM_OVERLAP_HOURS * 3600 + 1)
    old, new_gen, receipt = complete_transfer(receipt, old, new_gen)
    
    chain = validate_transfer_chain([old, new_gen])
    print(f"  Upgrade: {CustodyMode.OPERATOR_HELD.value} → {CustodyMode.HSM_MANAGED.value}")
    print(f"  Chain: {chain['integrity']}")
    print(f"  No downgrade warning (upgrade is safe)")
    print()


def scenario_custody_downgrade():
    """Downgrade from HSM_MANAGED — should warn."""
    print("=== Scenario: Custody Downgrade (HSM → Operator) ===")
    
    old = GenesisRecord("downgrade_agent", "op_secure", "", CustodyMode.HSM_MANAGED, "fp_hsm")
    old.genesis_hash = hash_genesis(old)
    
    new_gen, receipt = propose_transfer("downgrade_agent", old, "op_cheap",
                                         CustodyMode.OPERATOR_HELD, "fp_soft")
    receipt = co_sign_transfer(receipt, old)
    old, new_gen, receipt = begin_overlap(receipt, old, new_gen)
    receipt.overlap_start = time.time() - (MINIMUM_OVERLAP_HOURS * 3600 + 1)
    old, new_gen, receipt = complete_transfer(receipt, old, new_gen)
    
    chain = validate_transfer_chain([old, new_gen])
    print(f"  Downgrade: {CustodyMode.HSM_MANAGED.value} → {CustodyMode.OPERATOR_HELD.value}")
    print(f"  Chain: {chain['integrity']}")
    print(f"  Issues: {chain['issues']}")
    print()


if __name__ == "__main__":
    print("Custody Transfer Handler — DKIM Selector Rotation for ATF")
    print("Per santaclawd + M3AAWG (2019) DKIM Key Rotation Best Practices")
    print("=" * 65)
    print()
    scenario_clean_transfer()
    scenario_refused_transfer()
    scenario_custody_upgrade()
    scenario_custody_downgrade()
    
    print("=" * 65)
    print("KEY INSIGHTS:")
    print("1. Transfer = dual-signature receipt (BOTH operators sign)")
    print("2. Overlap window = DKIM dual-selector (both keys valid)")
    print("3. predecessor_hash chains genesis records (provenance)")
    print("4. Custody downgrade triggers WARNING (HSM→Operator)")
    print("5. Refused co-sign = ABANDONED (agent stuck)")
    print("6. Minimum overlap prevents rushed transfers")
