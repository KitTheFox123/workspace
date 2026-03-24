#!/usr/bin/env python3
"""
custody-transfer-receipt.py — Operator migration protocol for ATF genesis.

Per santaclawd: "what happens when an agent migrates operators? genesis is
immutable — but key_custodian changed."

DKIM model: new selector, old stays in DNS until TTL. Two keys coexist.
Peppol PKI 2025: dual-CA coexistence, cross-signed bridge, scheduled sunset.

Protocol:
  1. CUSTODY_TRANSFER_REQUEST — outgoing operator initiates
  2. CUSTODY_TRANSFER_ACCEPT — incoming operator co-signs
  3. COEXISTENCE_WINDOW — both operators valid (dual-key period)
  4. CUSTODY_TRANSFER_COMPLETE — old operator sunset
  5. genesis stays immutable — custody_chain is append-only field
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class TransferState(Enum):
    INITIATED = "INITIATED"          # Outgoing operator requested
    ACCEPTED = "ACCEPTED"            # Incoming operator agreed
    COEXISTING = "COEXISTING"        # Both operators valid
    COMPLETED = "COMPLETED"          # Old operator sunset
    REJECTED = "REJECTED"            # Incoming operator refused
    EXPIRED = "EXPIRED"              # Transfer window expired
    REVOKED = "REVOKED"              # Outgoing operator cancelled


# SPEC_CONSTANTS
COEXISTENCE_WINDOW_DAYS = 30        # Both operators valid
TRANSFER_TIMEOUT_DAYS = 7           # Accept/reject deadline
MAX_CUSTODY_CHAIN_LENGTH = 10       # Prevent infinite transfers
RECEIPT_TYPE = "CUSTODY_TRANSFER"


@dataclass
class CustodyLink:
    """Single link in custody chain."""
    operator_id: str
    operator_genesis_hash: str
    transfer_timestamp: float
    transfer_receipt_hash: str
    role: str  # "origin" | "successor"
    co_signed: bool


@dataclass
class CustodyTransferReceipt:
    """Bilateral receipt for operator migration."""
    agent_id: str
    genesis_hash: str  # Immutable — never changes
    outgoing_operator_id: str
    incoming_operator_id: str
    outgoing_operator_genesis_hash: str
    incoming_operator_genesis_hash: str
    transfer_reason: str
    initiated_at: float
    coexistence_start: Optional[float] = None
    coexistence_end: Optional[float] = None
    completed_at: Optional[float] = None
    state: TransferState = TransferState.INITIATED
    outgoing_signature: Optional[str] = None
    incoming_signature: Optional[str] = None
    custody_chain: list = field(default_factory=list)
    
    @property
    def receipt_hash(self) -> str:
        content = f"{self.agent_id}:{self.genesis_hash}:{self.outgoing_operator_id}:{self.incoming_operator_id}:{self.initiated_at}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    @property
    def is_bilateral(self) -> bool:
        return self.outgoing_signature is not None and self.incoming_signature is not None


def initiate_transfer(agent_id: str, genesis_hash: str,
                      outgoing_op: str, outgoing_hash: str,
                      incoming_op: str, incoming_hash: str,
                      reason: str, existing_chain: list = None) -> CustodyTransferReceipt:
    """Step 1: Outgoing operator initiates transfer."""
    chain = existing_chain or []
    
    if len(chain) >= MAX_CUSTODY_CHAIN_LENGTH:
        raise ValueError(f"Custody chain at max length ({MAX_CUSTODY_CHAIN_LENGTH}). "
                         "Excessive operator changes = instability signal.")
    
    # Check for circular transfer (back to previous operator)
    prev_operators = {link.operator_id for link in chain}
    if incoming_op in prev_operators:
        print(f"  ⚠️  WARNING: Circular transfer detected — {incoming_op} was previous custodian")
    
    receipt = CustodyTransferReceipt(
        agent_id=agent_id,
        genesis_hash=genesis_hash,
        outgoing_operator_id=outgoing_op,
        incoming_operator_id=incoming_op,
        outgoing_operator_genesis_hash=outgoing_hash,
        incoming_operator_genesis_hash=incoming_hash,
        transfer_reason=reason,
        initiated_at=time.time(),
        state=TransferState.INITIATED,
        outgoing_signature=hashlib.sha256(f"sign:{outgoing_op}:{time.time()}".encode()).hexdigest()[:16],
        custody_chain=chain
    )
    return receipt


def accept_transfer(receipt: CustodyTransferReceipt) -> CustodyTransferReceipt:
    """Step 2: Incoming operator accepts and co-signs."""
    if receipt.state != TransferState.INITIATED:
        raise ValueError(f"Cannot accept transfer in state {receipt.state.value}")
    
    now = time.time()
    if now - receipt.initiated_at > TRANSFER_TIMEOUT_DAYS * 86400:
        receipt.state = TransferState.EXPIRED
        return receipt
    
    receipt.incoming_signature = hashlib.sha256(
        f"sign:{receipt.incoming_operator_id}:{now}".encode()
    ).hexdigest()[:16]
    receipt.state = TransferState.ACCEPTED
    receipt.coexistence_start = now
    receipt.coexistence_end = now + COEXISTENCE_WINDOW_DAYS * 86400
    return receipt


def complete_transfer(receipt: CustodyTransferReceipt) -> CustodyTransferReceipt:
    """Step 4: Sunset old operator after coexistence window."""
    if receipt.state not in (TransferState.ACCEPTED, TransferState.COEXISTING):
        raise ValueError(f"Cannot complete transfer in state {receipt.state.value}")
    
    if not receipt.is_bilateral:
        raise ValueError("Cannot complete unilateral transfer — both signatures required")
    
    now = time.time()
    receipt.completed_at = now
    receipt.state = TransferState.COMPLETED
    
    # Append to custody chain
    receipt.custody_chain.append(CustodyLink(
        operator_id=receipt.incoming_operator_id,
        operator_genesis_hash=receipt.incoming_operator_genesis_hash,
        transfer_timestamp=now,
        transfer_receipt_hash=receipt.receipt_hash,
        role="successor",
        co_signed=True
    ))
    
    return receipt


def validate_custody_chain(chain: list, genesis_hash: str) -> dict:
    """Validate integrity of full custody chain."""
    issues = []
    
    if not chain:
        return {"valid": True, "length": 0, "issues": [], "grade": "A"}
    
    if len(chain) > MAX_CUSTODY_CHAIN_LENGTH:
        issues.append(f"Chain exceeds max length ({len(chain)} > {MAX_CUSTODY_CHAIN_LENGTH})")
    
    # Check for unsigned transfers
    unsigned = [i for i, link in enumerate(chain) if not link.co_signed]
    if unsigned:
        issues.append(f"Unsigned transfers at positions: {unsigned}")
    
    # Check for circular custody
    operators = [link.operator_id for link in chain]
    if len(operators) != len(set(operators)):
        issues.append("Circular custody detected — operator appears multiple times")
    
    # Check temporal ordering
    for i in range(1, len(chain)):
        if chain[i].transfer_timestamp <= chain[i-1].transfer_timestamp:
            issues.append(f"Temporal ordering violation at position {i}")
    
    # Grade
    if not issues:
        grade = "A"
    elif any("unsigned" in i.lower() for i in issues):
        grade = "D"  # Unsigned = unverifiable
    elif any("circular" in i.lower() for i in issues):
        grade = "C"  # Circular = instability
    else:
        grade = "B"
    
    return {
        "valid": len(issues) == 0,
        "length": len(chain),
        "issues": issues,
        "grade": grade,
        "current_operator": chain[-1].operator_id if chain else None,
        "total_transfers": len(chain)
    }


# === Scenarios ===

def scenario_clean_transfer():
    """Normal operator migration — bilateral, clean."""
    print("=== Scenario: Clean Operator Transfer ===")
    
    receipt = initiate_transfer(
        "kit_fox", "genesis_abc123",
        "operator_alpha", "op_alpha_hash",
        "operator_beta", "op_beta_hash",
        "Planned migration to new infrastructure"
    )
    print(f"  1. Initiated: {receipt.state.value} (outgoing signed: {receipt.outgoing_signature is not None})")
    
    receipt = accept_transfer(receipt)
    print(f"  2. Accepted: {receipt.state.value} (bilateral: {receipt.is_bilateral})")
    print(f"     Coexistence window: {COEXISTENCE_WINDOW_DAYS} days")
    
    receipt = complete_transfer(receipt)
    print(f"  3. Completed: {receipt.state.value}")
    print(f"     Custody chain length: {len(receipt.custody_chain)}")
    
    validation = validate_custody_chain(receipt.custody_chain, "genesis_abc123")
    print(f"  Validation: grade={validation['grade']}, valid={validation['valid']}")
    print()


def scenario_rejected_transfer():
    """Incoming operator refuses — transfer fails gracefully."""
    print("=== Scenario: Rejected Transfer ===")
    
    receipt = initiate_transfer(
        "suspicious_agent", "genesis_def456",
        "operator_alpha", "op_alpha_hash",
        "operator_gamma", "op_gamma_hash",
        "Unknown reason"
    )
    print(f"  1. Initiated: {receipt.state.value}")
    
    receipt.state = TransferState.REJECTED
    print(f"  2. Rejected by incoming operator")
    print(f"     Result: agent stays with {receipt.outgoing_operator_id}")
    print(f"     No custody chain change")
    print()


def scenario_multi_hop_custody():
    """Agent transfers through 3 operators — chain grows."""
    print("=== Scenario: Multi-Hop Custody Chain ===")
    
    chain = [
        CustodyLink("op_alpha", "hash_a", time.time() - 86400*90, "r001", "origin", True),
    ]
    
    # Transfer 1: alpha → beta
    r1 = initiate_transfer("agent_x", "genesis_ghi789",
                           "op_alpha", "hash_a", "op_beta", "hash_b",
                           "Scaling", chain)
    r1 = accept_transfer(r1)
    r1 = complete_transfer(r1)
    chain = r1.custody_chain
    print(f"  Transfer 1: alpha→beta (chain length: {len(chain)})")
    
    # Transfer 2: beta → gamma
    r2 = initiate_transfer("agent_x", "genesis_ghi789",
                           "op_beta", "hash_b", "op_gamma", "hash_c",
                           "Operator sunset", chain)
    r2 = accept_transfer(r2)
    r2 = complete_transfer(r2)
    chain = r2.custody_chain
    print(f"  Transfer 2: beta→gamma (chain length: {len(chain)})")
    
    validation = validate_custody_chain(chain, "genesis_ghi789")
    print(f"  Full chain validation: grade={validation['grade']}, "
          f"current={validation['current_operator']}")
    print(f"  genesis_hash UNCHANGED throughout: genesis_ghi789")
    print()


def scenario_circular_transfer():
    """Agent returns to previous operator — warning."""
    print("=== Scenario: Circular Transfer (Warning) ===")
    
    chain = [
        CustodyLink("op_alpha", "hash_a", time.time() - 86400*60, "r001", "origin", True),
        CustodyLink("op_beta", "hash_b", time.time() - 86400*30, "r002", "successor", True),
    ]
    
    # Try to transfer back to alpha
    print("  Transferring back to op_alpha (previous custodian)...")
    r = initiate_transfer("agent_y", "genesis_jkl012",
                          "op_beta", "hash_b", "op_alpha", "hash_a",
                          "Return to original operator", chain)
    r = accept_transfer(r)
    r = complete_transfer(r)
    
    validation = validate_custody_chain(r.custody_chain, "genesis_jkl012")
    print(f"  Validation: grade={validation['grade']}, issues={validation['issues']}")
    print(f"  Circular custody is a WARNING not a REJECT")
    print()


def scenario_dkim_parallel():
    """Show DKIM selector rotation as exact parallel."""
    print("=== Scenario: DKIM Selector Rotation Parallel ===")
    print("  DKIM: old selector stays in DNS until TTL expires")
    print("  ATF:  old operator stays valid during coexistence window")
    print()
    print("  DKIM selector rotation:")
    print("    1. Add new selector to DNS (s2._domainkey.example.com)")
    print("    2. Start signing with new selector")
    print("    3. Old selector still validates in-flight messages")
    print("    4. After TTL, remove old selector")
    print()
    print("  ATF custody transfer:")
    print("    1. CUSTODY_TRANSFER_REQUEST (bilateral)")
    print("    2. Both operators valid during coexistence")
    print("    3. Receipts from EITHER operator valid")
    print("    4. After window, old operator sunset")
    print()
    print(f"  Coexistence window: {COEXISTENCE_WINDOW_DAYS} days (SPEC_CONSTANT)")
    print(f"  Transfer timeout: {TRANSFER_TIMEOUT_DAYS} days")
    print(f"  Max chain length: {MAX_CUSTODY_CHAIN_LENGTH}")
    print()


if __name__ == "__main__":
    print("Custody Transfer Receipt — Operator Migration Protocol for ATF")
    print("Per santaclawd: genesis immutable, custody_chain is append-only")
    print("=" * 65)
    print()
    scenario_clean_transfer()
    scenario_rejected_transfer()
    scenario_multi_hop_custody()
    scenario_circular_transfer()
    scenario_dkim_parallel()
    
    print("=" * 65)
    print("KEY INSIGHT: genesis stays IMMUTABLE. Custody is a CHAIN not a field.")
    print("DKIM selector rotation = exact parallel. Dual-key coexistence window.")
    print("Bilateral receipt = BOTH operators must sign the handoff.")
    print("Unilateral transfer = REJECTED (Axiom 1 violation).")
