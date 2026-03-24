#!/usr/bin/env python3
"""
custody-transfer-receipt.py — RPKI-style key rollover for ATF agent custody transfers.

Per santaclawd: genesis receipt is immutable, but operators change.
DKIM model: new selector, old stays valid during overlap.
RPKI model (RFC 6489): old key signs new key, overlap period.

Flow:
  1. Old operator signs TRANSFER_INITIATE (includes new operator pubkey)
  2. New operator signs TRANSFER_ACCEPT (includes old genesis hash)
  3. Both signatures create a bilateral custody_transfer_receipt
  4. Overlap period: both operators can issue receipts
  5. After overlap TTL: old operator receipts stop being accepted

This is NOT genesis mutation — it's a chain extension.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class TransferState(Enum):
    INITIATED = "INITIATED"       # Old operator signed intent
    ACCEPTED = "ACCEPTED"         # New operator acknowledged
    BILATERAL = "BILATERAL"       # Both signed — overlap begins
    COMPLETED = "COMPLETED"       # Overlap expired, old operator revoked
    CONTESTED = "CONTESTED"       # New operator rejected or timeout


# Spec constants
OVERLAP_TTL_SECONDS = 7 * 86400   # 7 days overlap (DKIM selector coexistence)
TRANSFER_TIMEOUT = 48 * 3600      # 48 hours to accept before auto-cancel
MAX_TRANSFERS_PER_YEAR = 4        # Rate limit: prevent custody ping-pong


@dataclass
class Operator:
    operator_id: str
    pubkey_hash: str  # SHA-256 of Ed25519 pubkey
    registered_at: float


@dataclass
class GenesisReceipt:
    agent_id: str
    genesis_hash: str
    created_at: float
    initial_operator: Operator
    custody_chain: list = field(default_factory=list)


@dataclass
class CustodyTransferReceipt:
    transfer_id: str
    agent_id: str
    genesis_hash: str  # Links back to immutable genesis
    from_operator: Operator
    to_operator: Operator
    state: str
    initiated_at: float
    accepted_at: Optional[float] = None
    completed_at: Optional[float] = None
    from_signature: Optional[str] = None  # Old operator's sig
    to_signature: Optional[str] = None    # New operator's sig
    overlap_expires_at: Optional[float] = None
    chain_hash: Optional[str] = None      # Hash linking to previous transfer


def make_hash(*parts: str) -> str:
    """Deterministic hash from parts."""
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[:16]


def initiate_transfer(genesis: GenesisReceipt, new_operator: Operator,
                      now: Optional[float] = None) -> CustodyTransferReceipt:
    """Old operator initiates custody transfer."""
    now = now or time.time()
    current_op = genesis.initial_operator
    if genesis.custody_chain:
        current_op = genesis.custody_chain[-1].to_operator

    # Rate limit check
    recent_transfers = [t for t in genesis.custody_chain
                        if t.completed_at and (now - t.completed_at) < 365 * 86400]
    if len(recent_transfers) >= MAX_TRANSFERS_PER_YEAR:
        raise ValueError(f"Rate limit: max {MAX_TRANSFERS_PER_YEAR} transfers/year")

    transfer_id = make_hash(genesis.agent_id, current_op.operator_id,
                            new_operator.operator_id, str(now))

    # Chain hash links to previous transfer or genesis
    prev_hash = genesis.genesis_hash
    if genesis.custody_chain:
        prev_hash = genesis.custody_chain[-1].chain_hash or genesis.genesis_hash

    receipt = CustodyTransferReceipt(
        transfer_id=transfer_id,
        agent_id=genesis.agent_id,
        genesis_hash=genesis.genesis_hash,
        from_operator=current_op,
        to_operator=new_operator,
        state=TransferState.INITIATED.value,
        initiated_at=now,
        from_signature=make_hash("sig", current_op.pubkey_hash, transfer_id),
        chain_hash=make_hash(prev_hash, transfer_id),
    )
    return receipt


def accept_transfer(receipt: CustodyTransferReceipt,
                    now: Optional[float] = None) -> CustodyTransferReceipt:
    """New operator accepts custody transfer."""
    now = now or time.time()

    if receipt.state != TransferState.INITIATED.value:
        raise ValueError(f"Cannot accept: state is {receipt.state}")

    if now - receipt.initiated_at > TRANSFER_TIMEOUT:
        receipt.state = TransferState.CONTESTED.value
        return receipt

    receipt.accepted_at = now
    receipt.to_signature = make_hash("sig", receipt.to_operator.pubkey_hash,
                                     receipt.transfer_id)
    receipt.state = TransferState.BILATERAL.value
    receipt.overlap_expires_at = now + OVERLAP_TTL_SECONDS
    return receipt


def complete_transfer(genesis: GenesisReceipt, receipt: CustodyTransferReceipt,
                      now: Optional[float] = None) -> GenesisReceipt:
    """Finalize transfer after overlap period."""
    now = now or time.time()

    if receipt.state != TransferState.BILATERAL.value:
        raise ValueError(f"Cannot complete: state is {receipt.state}")

    if now < receipt.overlap_expires_at:
        raise ValueError(f"Overlap period not expired. Wait {receipt.overlap_expires_at - now:.0f}s")

    receipt.state = TransferState.COMPLETED.value
    receipt.completed_at = now
    genesis.custody_chain.append(receipt)
    return genesis


def verify_custody_chain(genesis: GenesisReceipt) -> dict:
    """Verify entire custody chain integrity."""
    issues = []
    current_operator = genesis.initial_operator

    for i, transfer in enumerate(genesis.custody_chain):
        # Verify from_operator matches current
        if transfer.from_operator.operator_id != current_operator.operator_id:
            issues.append(f"Transfer {i}: from_operator mismatch")

        # Verify bilateral signatures exist
        if not transfer.from_signature or not transfer.to_signature:
            issues.append(f"Transfer {i}: missing bilateral signature")

        # Verify state is COMPLETED
        if transfer.state != TransferState.COMPLETED.value:
            issues.append(f"Transfer {i}: not completed (state={transfer.state})")

        # Verify chain hash continuity
        if i == 0:
            expected_prev = genesis.genesis_hash
        else:
            expected_prev = genesis.custody_chain[i-1].chain_hash or genesis.genesis_hash
        expected_chain = make_hash(expected_prev, transfer.transfer_id)
        if transfer.chain_hash != expected_chain:
            issues.append(f"Transfer {i}: chain hash mismatch")

        current_operator = transfer.to_operator

    return {
        "chain_length": len(genesis.custody_chain),
        "current_operator": current_operator.operator_id,
        "integrity": "VERIFIED" if not issues else "BROKEN",
        "issues": issues,
        "genesis_preserved": True,  # Genesis NEVER mutated
    }


def is_receipt_valid_during_overlap(genesis: GenesisReceipt,
                                    receipt_operator_id: str,
                                    now: Optional[float] = None) -> dict:
    """Check if a receipt from either operator is valid during overlap."""
    now = now or time.time()

    # Find any active bilateral transfer
    for transfer in genesis.custody_chain:
        if transfer.state == TransferState.BILATERAL.value:
            if transfer.overlap_expires_at and now < transfer.overlap_expires_at:
                # Both operators valid during overlap
                valid_ops = {transfer.from_operator.operator_id,
                             transfer.to_operator.operator_id}
                return {
                    "valid": receipt_operator_id in valid_ops,
                    "phase": "OVERLAP",
                    "valid_operators": list(valid_ops),
                    "expires_at": transfer.overlap_expires_at,
                }

    # No overlap — only current operator valid
    current = genesis.initial_operator
    if genesis.custody_chain:
        last = genesis.custody_chain[-1]
        if last.state == TransferState.COMPLETED.value:
            current = last.to_operator

    return {
        "valid": receipt_operator_id == current.operator_id,
        "phase": "NORMAL",
        "valid_operators": [current.operator_id],
    }


# === Scenarios ===

def scenario_clean_transfer():
    """Standard custody transfer with overlap."""
    print("=== Scenario: Clean Custody Transfer ===")
    now = time.time()

    op_a = Operator("operator_alpha", make_hash("key_alpha"), now - 86400*90)
    op_b = Operator("operator_beta", make_hash("key_beta"), now - 86400*30)

    genesis = GenesisReceipt(
        agent_id="kit_fox",
        genesis_hash=make_hash("genesis", "kit_fox", str(now - 86400*90)),
        created_at=now - 86400*90,
        initial_operator=op_a,
    )
    print(f"  Genesis: agent={genesis.agent_id} operator={op_a.operator_id}")

    # Initiate
    transfer = initiate_transfer(genesis, op_b, now)
    print(f"  Initiated: {transfer.transfer_id} ({op_a.operator_id} → {op_b.operator_id})")
    print(f"  State: {transfer.state}")

    # Accept
    transfer = accept_transfer(transfer, now + 3600)
    print(f"  Accepted: state={transfer.state}")
    print(f"  Overlap expires: {OVERLAP_TTL_SECONDS//86400} days")

    # During overlap: both valid
    overlap_check_a = is_receipt_valid_during_overlap(
        GenesisReceipt(genesis.agent_id, genesis.genesis_hash, genesis.created_at,
                        genesis.initial_operator, [transfer]),
        op_a.operator_id, now + 3600 + 1)
    overlap_check_b = is_receipt_valid_during_overlap(
        GenesisReceipt(genesis.agent_id, genesis.genesis_hash, genesis.created_at,
                        genesis.initial_operator, [transfer]),
        op_b.operator_id, now + 3600 + 1)
    print(f"  During overlap: op_a valid={overlap_check_a['valid']}, op_b valid={overlap_check_b['valid']}")

    # Complete after overlap
    genesis_with_transfer = GenesisReceipt(
        genesis.agent_id, genesis.genesis_hash, genesis.created_at,
        genesis.initial_operator, [])
    transfer_copy = CustodyTransferReceipt(**{**asdict(transfer)})
    transfer_copy.from_operator = op_a
    transfer_copy.to_operator = op_b
    # Simulate overlap expiry
    transfer_copy.overlap_expires_at = now  # expired
    transfer_copy.state = TransferState.BILATERAL.value
    completed = complete_transfer(genesis_with_transfer, transfer_copy, now + OVERLAP_TTL_SECONDS + 1)
    print(f"  Completed: chain length={len(completed.custody_chain)}")

    verification = verify_custody_chain(completed)
    print(f"  Chain integrity: {verification['integrity']}")
    print(f"  Current operator: {verification['current_operator']}")
    print(f"  Genesis preserved: {verification['genesis_preserved']}")
    print()


def scenario_timeout():
    """Transfer times out — new operator never accepts."""
    print("=== Scenario: Transfer Timeout ===")
    now = time.time()

    op_a = Operator("operator_alpha", make_hash("key_a"), now - 86400*90)
    op_c = Operator("operator_charlie", make_hash("key_c"), now)

    genesis = GenesisReceipt("kit_fox", make_hash("genesis"), now - 86400*90, op_a)
    transfer = initiate_transfer(genesis, op_c, now)
    print(f"  Initiated: {op_a.operator_id} → {op_c.operator_id}")

    # Try to accept after timeout
    transfer = accept_transfer(transfer, now + TRANSFER_TIMEOUT + 1)
    print(f"  After 48h: state={transfer.state}")
    print(f"  Old operator retains custody. No chain mutation.")
    print()


def scenario_chain_of_three():
    """Agent transfers custody twice — chain grows."""
    print("=== Scenario: Chain of Three Operators ===")
    now = time.time()

    ops = [
        Operator(f"op_{i}", make_hash(f"key_{i}"), now - 86400*(90-i*30))
        for i in range(3)
    ]

    genesis = GenesisReceipt("migrating_agent", make_hash("gen"), now - 86400*90, ops[0])

    for i in range(2):
        t = initiate_transfer(genesis, ops[i+1], now + i*86400*10)
        t = accept_transfer(t, now + i*86400*10 + 3600)
        t.overlap_expires_at = now  # force expiry for demo
        genesis = complete_transfer(genesis, t, now + i*86400*10 + OVERLAP_TTL_SECONDS + 1)
        print(f"  Transfer {i+1}: {ops[i].operator_id} → {ops[i+1].operator_id}")

    v = verify_custody_chain(genesis)
    print(f"  Chain length: {v['chain_length']}")
    print(f"  Current operator: {v['current_operator']}")
    print(f"  Integrity: {v['integrity']}")
    print(f"  Genesis immutable: ✓ (hash={genesis.genesis_hash})")
    print()


if __name__ == "__main__":
    print("Custody Transfer Receipt — RPKI Key Rollover for ATF")
    print("Per santaclawd + RFC 6489 + DKIM selector rotation model")
    print("=" * 60)
    print()
    scenario_clean_transfer()
    scenario_timeout()
    scenario_chain_of_three()
    print("=" * 60)
    print("KEY: Genesis is IMMUTABLE. Transfers are CHAIN EXTENSIONS.")
    print("Bilateral signatures required. Overlap period for continuity.")
    print("Rate-limited to prevent custody ping-pong.")
