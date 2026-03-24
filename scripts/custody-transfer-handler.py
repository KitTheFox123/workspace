#!/usr/bin/env python3
"""
custody-transfer-handler.py — ATF operator custody transfer protocol.

Per santaclawd: genesis is immutable but key_custodian changes.
DKIM answer: new selector, old stays in DNS until TTL. Two keys coexist.

ATF needs: CUSTODY_TRANSFER receipt type.
- Old operator signs handoff
- New operator countersigns
- Chain: genesis → ... → custody_transfer → continued operation
- NOT a reanchor (reanchor = void). This is SUCCESSION.

DKIM selector rotation parallel:
- Old selector stays active during overlap window
- New selector published before switchover
- Both valid simultaneously during transition
- Old removed after TTL expires
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class TransferState(Enum):
    PROPOSED = "PROPOSED"       # Old operator signed handoff proposal
    ACCEPTED = "ACCEPTED"       # New operator countersigned
    ACTIVE = "ACTIVE"           # Overlap window — both operators valid
    COMPLETED = "COMPLETED"     # Old operator deactivated, new sole custodian
    REJECTED = "REJECTED"       # New operator refused
    EXPIRED = "EXPIRED"         # Proposal timed out


# SPEC_CONSTANTS
PROPOSAL_TTL_HOURS = 72         # Time for new operator to accept
OVERLAP_WINDOW_HOURS = 168      # 7 days both operators valid (DKIM parallel)
MIN_OVERLAP_HOURS = 24          # Minimum overlap (safety)
MAX_OVERLAP_HOURS = 720         # Maximum overlap (30 days)


@dataclass
class CustodyTransferReceipt:
    """ATF CUSTODY_TRANSFER receipt type."""
    receipt_id: str
    agent_id: str
    genesis_hash: str
    old_operator_id: str
    new_operator_id: str
    old_operator_signature: str      # Old operator signs the proposal
    new_operator_signature: Optional[str]  # New operator countersigns
    transfer_reason: str             # "migration", "acquisition", "delegation"
    state: TransferState
    proposed_at: float
    accepted_at: Optional[float] = None
    activated_at: Optional[float] = None
    completed_at: Optional[float] = None
    overlap_window_hours: int = OVERLAP_WINDOW_HOURS
    predecessor_custody_hash: Optional[str] = None  # Chain to previous transfer
    
    def transfer_hash(self) -> str:
        """Deterministic hash of transfer receipt."""
        payload = f"{self.agent_id}:{self.genesis_hash}:{self.old_operator_id}:" \
                  f"{self.new_operator_id}:{self.proposed_at}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass  
class CustodyChain:
    """Full custody history for an agent."""
    agent_id: str
    genesis_hash: str
    transfers: list = field(default_factory=list)
    current_operator: str = ""
    
    def add_transfer(self, transfer: CustodyTransferReceipt):
        if self.transfers:
            transfer.predecessor_custody_hash = self.transfers[-1].transfer_hash()
        self.transfers.append(transfer)
    
    def verify_chain(self) -> dict:
        """Verify custody chain integrity."""
        issues = []
        for i, t in enumerate(self.transfers):
            # Each transfer must have old operator signature
            if not t.old_operator_signature:
                issues.append(f"Transfer {i}: missing old operator signature")
            
            # Completed transfers must have new operator countersignature
            if t.state in (TransferState.ACCEPTED, TransferState.ACTIVE, 
                          TransferState.COMPLETED):
                if not t.new_operator_signature:
                    issues.append(f"Transfer {i}: missing new operator countersignature")
            
            # Chain linkage
            if i > 0:
                expected_pred = self.transfers[i-1].transfer_hash()
                if t.predecessor_custody_hash != expected_pred:
                    issues.append(f"Transfer {i}: broken chain link")
            
            # Overlap window bounds
            if t.overlap_window_hours < MIN_OVERLAP_HOURS:
                issues.append(f"Transfer {i}: overlap {t.overlap_window_hours}h below minimum {MIN_OVERLAP_HOURS}h")
            if t.overlap_window_hours > MAX_OVERLAP_HOURS:
                issues.append(f"Transfer {i}: overlap {t.overlap_window_hours}h above maximum {MAX_OVERLAP_HOURS}h")
        
        # Self-transfer detection (axiom 1 violation)
        self_transfers = [t for t in self.transfers 
                         if t.old_operator_id == t.new_operator_id]
        if self_transfers:
            issues.append(f"Self-transfer detected: operator transferring to itself ({len(self_transfers)} times)")
        
        return {
            "chain_length": len(self.transfers),
            "integrity": "VERIFIED" if not issues else "BROKEN",
            "issues": issues,
            "current_operator": self.current_operator,
            "total_custody_changes": len([t for t in self.transfers 
                                         if t.state == TransferState.COMPLETED])
        }


def propose_transfer(chain: CustodyChain, new_operator_id: str, 
                     reason: str = "migration") -> CustodyTransferReceipt:
    """Old operator proposes custody transfer."""
    now = time.time()
    receipt = CustodyTransferReceipt(
        receipt_id=hashlib.sha256(f"transfer:{now}".encode()).hexdigest()[:12],
        agent_id=chain.agent_id,
        genesis_hash=chain.genesis_hash,
        old_operator_id=chain.current_operator,
        new_operator_id=new_operator_id,
        old_operator_signature=f"sig_old_{chain.current_operator[:8]}",
        new_operator_signature=None,
        transfer_reason=reason,
        state=TransferState.PROPOSED,
        proposed_at=now
    )
    chain.add_transfer(receipt)
    return receipt


def accept_transfer(receipt: CustodyTransferReceipt) -> CustodyTransferReceipt:
    """New operator accepts and countersigns."""
    if receipt.state != TransferState.PROPOSED:
        raise ValueError(f"Cannot accept transfer in state {receipt.state}")
    
    now = time.time()
    if now - receipt.proposed_at > PROPOSAL_TTL_HOURS * 3600:
        receipt.state = TransferState.EXPIRED
        return receipt
    
    receipt.new_operator_signature = f"sig_new_{receipt.new_operator_id[:8]}"
    receipt.accepted_at = now
    receipt.state = TransferState.ACCEPTED
    return receipt


def activate_overlap(receipt: CustodyTransferReceipt) -> CustodyTransferReceipt:
    """Begin overlap window — both operators valid."""
    if receipt.state != TransferState.ACCEPTED:
        raise ValueError(f"Cannot activate from state {receipt.state}")
    receipt.activated_at = time.time()
    receipt.state = TransferState.ACTIVE
    return receipt


def complete_transfer(chain: CustodyChain, receipt: CustodyTransferReceipt) -> CustodyTransferReceipt:
    """Complete transfer — old operator deactivated."""
    if receipt.state != TransferState.ACTIVE:
        raise ValueError(f"Cannot complete from state {receipt.state}")
    
    # Check minimum overlap
    elapsed = (time.time() - receipt.activated_at) if receipt.activated_at else 0
    if elapsed < MIN_OVERLAP_HOURS * 3600:
        print(f"  WARNING: Overlap only {elapsed/3600:.1f}h (minimum {MIN_OVERLAP_HOURS}h)")
    
    receipt.completed_at = time.time()
    receipt.state = TransferState.COMPLETED
    chain.current_operator = receipt.new_operator_id
    return receipt


# === Scenarios ===

def scenario_clean_transfer():
    """Normal operator migration."""
    print("=== Scenario: Clean Custody Transfer ===")
    chain = CustodyChain("kit_fox", "genesis_abc123", current_operator="operator_alpha")
    
    # Step 1: Propose
    receipt = propose_transfer(chain, "operator_beta", "migration")
    print(f"  1. PROPOSED: {receipt.old_operator_id} → {receipt.new_operator_id}")
    print(f"     Old operator signed: {receipt.old_operator_signature}")
    
    # Step 2: Accept
    accept_transfer(receipt)
    print(f"  2. ACCEPTED: New operator countersigned: {receipt.new_operator_signature}")
    
    # Step 3: Overlap
    activate_overlap(receipt)
    print(f"  3. ACTIVE: Both operators valid for {receipt.overlap_window_hours}h")
    
    # Step 4: Complete
    complete_transfer(chain, receipt)
    print(f"  4. COMPLETED: New operator sole custodian")
    
    result = chain.verify_chain()
    print(f"  Chain: {result['integrity']}, operator: {result['current_operator']}")
    print()


def scenario_multi_hop():
    """Agent transfers operators twice."""
    print("=== Scenario: Multi-Hop Custody Chain ===")
    chain = CustodyChain("migrating_agent", "genesis_def456", current_operator="op_1")
    
    # First transfer
    r1 = propose_transfer(chain, "op_2", "acquisition")
    accept_transfer(r1)
    activate_overlap(r1)
    complete_transfer(chain, r1)
    print(f"  Transfer 1: op_1 → op_2 (COMPLETED)")
    
    # Second transfer
    r2 = propose_transfer(chain, "op_3", "delegation")
    accept_transfer(r2)
    activate_overlap(r2)
    complete_transfer(chain, r2)
    print(f"  Transfer 2: op_2 → op_3 (COMPLETED)")
    
    result = chain.verify_chain()
    print(f"  Chain length: {result['chain_length']}, integrity: {result['integrity']}")
    print(f"  Current operator: {result['current_operator']}")
    print(f"  Predecessor linkage: {chain.transfers[1].predecessor_custody_hash is not None}")
    print()


def scenario_self_transfer():
    """Operator tries to transfer to itself (axiom 1 violation)."""
    print("=== Scenario: Self-Transfer (Axiom 1 Violation) ===")
    chain = CustodyChain("suspect_agent", "genesis_ghi789", current_operator="shady_op")
    
    receipt = propose_transfer(chain, "shady_op", "restructuring")
    accept_transfer(receipt)
    activate_overlap(receipt)
    complete_transfer(chain, receipt)
    
    result = chain.verify_chain()
    print(f"  Integrity: {result['integrity']}")
    for issue in result['issues']:
        print(f"  ⚠️ {issue}")
    print()


def scenario_rejected_transfer():
    """New operator refuses custody."""
    print("=== Scenario: Rejected Transfer ===")
    chain = CustodyChain("contested_agent", "genesis_jkl012", current_operator="op_old")
    
    receipt = propose_transfer(chain, "op_new", "migration")
    print(f"  PROPOSED: {receipt.old_operator_id} → {receipt.new_operator_id}")
    
    # New operator rejects
    receipt.state = TransferState.REJECTED
    print(f"  REJECTED: New operator refused custody")
    print(f"  Agent remains with: {chain.current_operator}")
    
    result = chain.verify_chain()
    print(f"  Chain integrity: {result['integrity']}")
    print(f"  Completed transfers: {result['total_custody_changes']}")
    print()


def scenario_dkim_parallel():
    """Show DKIM selector rotation parallel explicitly."""
    print("=== Scenario: DKIM Selector Rotation Parallel ===")
    print("  DKIM key rotation:")
    print("    1. Publish new selector in DNS (selector2._domainkey)")
    print("    2. Start signing with new key")
    print("    3. Old selector stays in DNS (overlap = TTL)")
    print("    4. Remove old selector after TTL expires")
    print()
    print("  ATF custody transfer:")
    print("    1. New operator published (PROPOSED + countersigned)")
    print("    2. Both operators valid (ACTIVE overlap window)")
    print("    3. Receipts accepted from either operator during overlap")
    print("    4. Old operator deactivated (COMPLETED)")
    print()
    print("  Key difference: DKIM is unilateral (domain owner decides).")
    print("  ATF requires bilateral: old signs, new countersigns.")
    print("  DKIM has no 'rejection' — ATF does (REJECTED state).")
    print("  Both use overlap windows for continuity.")
    print()


if __name__ == "__main__":
    print("Custody Transfer Handler — ATF Operator Migration Protocol")
    print("Per santaclawd: genesis immutable but custodian changes")
    print("DKIM selector rotation as model")
    print("=" * 65)
    print()
    scenario_clean_transfer()
    scenario_multi_hop()
    scenario_self_transfer()
    scenario_rejected_transfer()
    scenario_dkim_parallel()
    
    print("=" * 65)
    print("KEY: Custody transfer ≠ reanchor. Reanchor = void + new genesis.")
    print("Transfer = succession. Chain preserved. History continuous.")
    print("DKIM parallel: two selectors coexist during transition.")
    print("Bilateral: old signs proposal, new countersigns acceptance.")
