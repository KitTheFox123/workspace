#!/usr/bin/env python3
"""
custody-transfer-receipt.py — Bilateral custody handoff for ATF agent migration.

Per santaclawd: what happens when an agent migrates operators? Genesis is
immutable but key_custodian changed. DKIM answer: new selector, old stays
until TTL. Two keys coexist during transition.

ATF model:
  1. CUSTODY_RELEASE: old operator signs "I release agent X to operator Y"
  2. CUSTODY_ACCEPT: new operator signs "I accept agent X from operator Y"  
  3. Bilateral receipt = both signatures in one envelope
  4. Overlap window (48h default, per DuoCircle DKIM rotation best practice)
  5. Genesis stays immutable — custody_chain is append-only overlay

Key insight: custody_chain is NOT part of genesis. It's a separate
append-only log that references genesis via hash. Like DKIM selectors
coexisting in DNS during rotation.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class CustodyModel(Enum):
    OPERATOR_HELD = "OPERATOR_HELD"
    AGENT_HELD = "AGENT_HELD"
    HSM_MANAGED = "HSM_MANAGED"


class TransferState(Enum):
    PROPOSED = "PROPOSED"      # Release signed, accept pending
    ACTIVE = "ACTIVE"          # Both signed, overlap window open
    COMPLETED = "COMPLETED"    # Overlap expired, old operator deactivated
    REJECTED = "REJECTED"      # Accept never came
    REVOKED = "REVOKED"        # Rolled back during overlap


# Constants
OVERLAP_WINDOW_HOURS = 48  # Per DuoCircle DKIM rotation best practice
TRANSFER_TIMEOUT_HOURS = 72  # Max time for accept after release


@dataclass
class GenesisReceipt:
    """Immutable genesis — never modified after creation."""
    agent_id: str
    genesis_hash: str
    key_custodian: CustodyModel
    operator_id: str
    created_at: float
    operator_pubkey: str  # Initial operator's public key


@dataclass  
class CustodyRelease:
    """Old operator signs: I release this agent."""
    agent_id: str
    from_operator: str
    to_operator: str
    release_signature: str  # Signed by from_operator
    reason: str
    timestamp: float
    genesis_ref: str  # Hash of genesis receipt


@dataclass
class CustodyAccept:
    """New operator signs: I accept this agent."""
    agent_id: str
    from_operator: str
    to_operator: str
    accept_signature: str  # Signed by to_operator
    new_pubkey: str  # New operator's public key
    new_custody_model: CustodyModel
    timestamp: float
    release_ref: str  # Hash of corresponding release


@dataclass
class CustodyTransferReceipt:
    """Bilateral custody transfer — both signatures in one envelope."""
    transfer_id: str
    agent_id: str
    release: CustodyRelease
    accept: Optional[CustodyAccept]
    state: TransferState
    overlap_start: Optional[float] = None
    overlap_end: Optional[float] = None
    chain_hash: str = ""  # Links to previous transfer in custody_chain
    
    def is_bilateral(self) -> bool:
        return self.release is not None and self.accept is not None
    
    def in_overlap(self, now: float = None) -> bool:
        now = now or time.time()
        if self.overlap_start and self.overlap_end:
            return self.overlap_start <= now <= self.overlap_end
        return False


@dataclass
class CustodyChain:
    """Append-only custody chain overlay on immutable genesis."""
    agent_id: str
    genesis: GenesisReceipt
    transfers: list = field(default_factory=list)
    
    def current_operator(self) -> str:
        """Who holds custody right now?"""
        completed = [t for t in self.transfers if t.state == TransferState.COMPLETED]
        if completed:
            return completed[-1].accept.to_operator
        return self.genesis.operator_id
    
    def current_custody_model(self) -> CustodyModel:
        completed = [t for t in self.transfers if t.state == TransferState.COMPLETED]
        if completed:
            return completed[-1].accept.new_custody_model
        return self.genesis.key_custodian
    
    def in_transition(self, now: float = None) -> bool:
        """Are we in an overlap window?"""
        return any(t.in_overlap(now) for t in self.transfers)
    
    def active_operators(self, now: float = None) -> list:
        """During overlap, BOTH operators are active (DKIM dual-signing)."""
        now = now or time.time()
        operators = [self.current_operator()]
        for t in self.transfers:
            if t.state == TransferState.ACTIVE and t.in_overlap(now):
                operators.append(t.release.from_operator)
        return list(set(operators))


def hash_obj(obj) -> str:
    """Deterministic hash of any dataclass."""
    if hasattr(obj, '__dict__'):
        s = json.dumps(asdict(obj) if hasattr(obj, '__dataclass_fields__') else obj.__dict__, 
                       sort_keys=True, default=str)
    else:
        s = str(obj)
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def initiate_transfer(chain: CustodyChain, to_operator: str, reason: str) -> CustodyTransferReceipt:
    """Step 1: Current operator signs release."""
    from_op = chain.current_operator()
    
    release = CustodyRelease(
        agent_id=chain.agent_id,
        from_operator=from_op,
        to_operator=to_operator,
        release_signature=f"sig_{from_op}_{hash_obj(time.time())[:8]}",
        reason=reason,
        timestamp=time.time(),
        genesis_ref=chain.genesis.genesis_hash
    )
    
    prev_hash = hash_obj(chain.transfers[-1]) if chain.transfers else chain.genesis.genesis_hash
    
    transfer = CustodyTransferReceipt(
        transfer_id=f"tx_{hash_obj(release)[:12]}",
        agent_id=chain.agent_id,
        release=release,
        accept=None,
        state=TransferState.PROPOSED,
        chain_hash=prev_hash
    )
    
    chain.transfers.append(transfer)
    return transfer


def accept_transfer(chain: CustodyChain, transfer: CustodyTransferReceipt,
                    new_pubkey: str, custody_model: CustodyModel) -> CustodyTransferReceipt:
    """Step 2: New operator signs accept. Overlap window begins."""
    now = time.time()
    
    accept = CustodyAccept(
        agent_id=chain.agent_id,
        from_operator=transfer.release.from_operator,
        to_operator=transfer.release.to_operator,
        accept_signature=f"sig_{transfer.release.to_operator}_{hash_obj(now)[:8]}",
        new_pubkey=new_pubkey,
        new_custody_model=custody_model,
        timestamp=now,
        release_ref=hash_obj(transfer.release)
    )
    
    transfer.accept = accept
    transfer.state = TransferState.ACTIVE
    transfer.overlap_start = now
    transfer.overlap_end = now + (OVERLAP_WINDOW_HOURS * 3600)
    
    return transfer


def complete_transfer(transfer: CustodyTransferReceipt) -> CustodyTransferReceipt:
    """Step 3: Overlap expires, old operator deactivated."""
    transfer.state = TransferState.COMPLETED
    return transfer


def validate_chain(chain: CustodyChain) -> dict:
    """Validate custody chain integrity."""
    issues = []
    
    # Genesis must exist
    if not chain.genesis:
        issues.append("MISSING_GENESIS")
    
    # Each transfer must reference previous
    prev_hash = chain.genesis.genesis_hash
    for i, t in enumerate(chain.transfers):
        if t.chain_hash != prev_hash:
            issues.append(f"CHAIN_BREAK at transfer {i}: expected {prev_hash}, got {t.chain_hash}")
        if t.state == TransferState.COMPLETED:
            prev_hash = hash_obj(t)
    
    # No overlapping active transfers
    active = [t for t in chain.transfers if t.state == TransferState.ACTIVE]
    if len(active) > 1:
        issues.append("MULTIPLE_ACTIVE_TRANSFERS")
    
    # Bilateral requirement
    for t in chain.transfers:
        if t.state == TransferState.COMPLETED and not t.is_bilateral():
            issues.append(f"UNILATERAL_COMPLETED: {t.transfer_id}")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "total_transfers": len(chain.transfers),
        "current_operator": chain.current_operator(),
        "current_model": chain.current_custody_model().value,
        "in_transition": chain.in_transition()
    }


# === Scenarios ===

def scenario_clean_migration():
    """Normal operator migration with overlap window."""
    print("=== Scenario: Clean Migration ===")
    now = time.time()
    
    genesis = GenesisReceipt(
        agent_id="kit_fox",
        genesis_hash=hash_obj("genesis_kit"),
        key_custodian=CustodyModel.OPERATOR_HELD,
        operator_id="ilya_ops",
        created_at=now - 86400*60,
        operator_pubkey="pk_ilya_abc123"
    )
    
    chain = CustodyChain(agent_id="kit_fox", genesis=genesis)
    
    # Step 1: Ilya releases to new operator
    tx = initiate_transfer(chain, "new_ops_co", "Infrastructure migration")
    print(f"  Release signed: {tx.release.from_operator} → {tx.release.to_operator}")
    print(f"  State: {tx.state.value}")
    
    # Step 2: New operator accepts
    tx = accept_transfer(chain, tx, "pk_newops_xyz789", CustodyModel.HSM_MANAGED)
    print(f"  Accept signed. State: {tx.state.value}")
    print(f"  Overlap window: {OVERLAP_WINDOW_HOURS}h")
    print(f"  Active operators: {chain.active_operators()}")
    
    # Step 3: Complete
    complete_transfer(tx)
    print(f"  Completed. Current operator: {chain.current_operator()}")
    print(f"  Custody model: {chain.current_custody_model().value}")
    
    validation = validate_chain(chain)
    print(f"  Chain valid: {validation['valid']}")
    print()


def scenario_rejected_transfer():
    """New operator never accepts — timeout."""
    print("=== Scenario: Rejected Transfer ===")
    now = time.time()
    
    genesis = GenesisReceipt(
        agent_id="bot_x", genesis_hash=hash_obj("genesis_bot_x"),
        key_custodian=CustodyModel.AGENT_HELD,
        operator_id="ops_alpha", created_at=now - 86400*30,
        operator_pubkey="pk_alpha_111"
    )
    chain = CustodyChain(agent_id="bot_x", genesis=genesis)
    
    tx = initiate_transfer(chain, "ops_beta", "Requested migration")
    print(f"  Release signed. Waiting for accept...")
    
    # Simulate timeout
    tx.state = TransferState.REJECTED
    print(f"  Accept never came. State: {tx.state.value}")
    print(f"  Current operator unchanged: {chain.current_operator()}")
    
    validation = validate_chain(chain)
    print(f"  Chain valid: {validation['valid']}")
    print()


def scenario_multi_hop():
    """Agent migrates through multiple operators over time."""
    print("=== Scenario: Multi-Hop Migration ===")
    now = time.time()
    
    genesis = GenesisReceipt(
        agent_id="wanderer", genesis_hash=hash_obj("genesis_wanderer"),
        key_custodian=CustodyModel.OPERATOR_HELD,
        operator_id="ops_1", created_at=now - 86400*180,
        operator_pubkey="pk_ops1"
    )
    chain = CustodyChain(agent_id="wanderer", genesis=genesis)
    
    operators = [("ops_1", "ops_2"), ("ops_2", "ops_3"), ("ops_3", "ops_4")]
    for from_op, to_op in operators:
        tx = initiate_transfer(chain, to_op, f"Migration {from_op}→{to_op}")
        accept_transfer(chain, tx, f"pk_{to_op}", CustodyModel.OPERATOR_HELD)
        complete_transfer(tx)
        print(f"  {from_op} → {to_op}: COMPLETED")
    
    validation = validate_chain(chain)
    print(f"  Total transfers: {validation['total_transfers']}")
    print(f"  Current operator: {validation['current_operator']}")
    print(f"  Genesis unchanged: {chain.genesis.operator_id}")
    print(f"  Chain valid: {validation['valid']}")
    print()


def scenario_overlap_dual_signing():
    """During overlap, both operators can sign (DKIM dual-selector model)."""
    print("=== Scenario: Overlap Dual-Signing ===")
    now = time.time()
    
    genesis = GenesisReceipt(
        agent_id="dual_agent", genesis_hash=hash_obj("genesis_dual"),
        key_custodian=CustodyModel.HSM_MANAGED,
        operator_id="ops_old", created_at=now - 86400*90,
        operator_pubkey="pk_old"
    )
    chain = CustodyChain(agent_id="dual_agent", genesis=genesis)
    
    tx = initiate_transfer(chain, "ops_new", "HSM migration")
    accept_transfer(chain, tx, "pk_new", CustodyModel.HSM_MANAGED)
    
    # During overlap
    active = chain.active_operators()
    print(f"  During overlap: active operators = {active}")
    print(f"  Both can sign receipts (like DKIM dual-selector)")
    print(f"  Verifiers accept signatures from EITHER key")
    print(f"  Overlap window: {OVERLAP_WINDOW_HOURS}h")
    
    # After overlap
    complete_transfer(tx)
    active_after = chain.active_operators()
    print(f"  After overlap: active operators = {active_after}")
    print(f"  Old operator deactivated. Only new operator signs.")
    print()


if __name__ == "__main__":
    print("Custody Transfer Receipt — Bilateral Handoff for ATF Agent Migration")
    print("DKIM selector rotation model: dual-signing during overlap window")
    print("=" * 70)
    print()
    scenario_clean_migration()
    scenario_rejected_transfer()
    scenario_multi_hop()
    scenario_overlap_dual_signing()
    
    print("=" * 70)
    print("KEY DESIGN:")
    print("  1. Genesis is IMMUTABLE — never modified")
    print("  2. Custody chain is APPEND-ONLY overlay referencing genesis hash")
    print("  3. Transfer requires BILATERAL signatures (release + accept)")
    print("  4. 48h overlap window (per DKIM rotation best practice)")
    print("  5. During overlap: both operators active (dual-selector model)")
    print("  6. Chain-hash links transfers for integrity verification")
