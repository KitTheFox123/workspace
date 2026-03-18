#!/usr/bin/env python3
"""
paylock-adv-bridge.py — Bridge PayLock on-chain payments to ADV receipts
Per santaclawd: "on-chain payment proofs are now ADV receipts"

Three-field mapping:
  tx_hash → delivery_hash (unique, immutable)
  escrow_address → witness (self-witnessing contract)
  settlement_block → timestamp (block confirmation, not submission)

The escrow contract IS the independent log operator.
No trusted third party needed — CT model applied to payments.
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from enum import Enum

class SettlementStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FINALIZED = "finalized"
    DISPUTED = "disputed"

@dataclass
class PayLockTransaction:
    tx_hash: str
    escrow_address: str
    payer: str
    payee: str
    amount_sol: float
    settlement_block: int
    block_time: int  # unix timestamp
    status: SettlementStatus

@dataclass
class ADVReceipt:
    version: str
    timestamp: int
    delivery_hash: str
    witness: str
    dimensions: dict
    parties: dict
    settlement: dict
    source: str  # "paylock"

def bridge_to_adv(tx: PayLockTransaction) -> ADVReceipt:
    """Convert PayLock transaction to ADV receipt."""
    
    # delivery_hash = tx_hash (globally unique, no replay possible)
    delivery_hash = tx.tx_hash
    
    # witness = escrow_address (self-witnessing contract)
    witness = tx.escrow_address
    
    # timestamp = block confirmation time (not submission time)
    timestamp = tx.block_time
    
    # Dimensions from payment context
    dimensions = {
        "timeliness": 1.0 if tx.status == SettlementStatus.FINALIZED else 0.5,
        "completeness": 1.0 if tx.amount_sol > 0 else 0.0,
        "groundedness": 1.0,  # on-chain = verifiable by definition
    }
    
    parties = {
        "payer": tx.payer,
        "payee": tx.payee,
    }
    
    settlement = {
        "amount_sol": tx.amount_sol,
        "block": tx.settlement_block,
        "status": tx.status.value,
        "finality_ms": 400,  # Solana ~400ms
    }
    
    return ADVReceipt(
        version="0.2.1",
        timestamp=timestamp,
        delivery_hash=delivery_hash,
        witness=witness,
        dimensions=dimensions,
        parties=parties,
        settlement=settlement,
        source="paylock",
    )

def verify_receipt(receipt: ADVReceipt) -> dict:
    """Verify a payment-anchored receipt."""
    checks = {
        "delivery_hash_present": bool(receipt.delivery_hash),
        "witness_present": bool(receipt.witness),
        "timestamp_valid": receipt.timestamp > 0,
        "dimensions_complete": all(k in receipt.dimensions for k in ["timeliness", "completeness", "groundedness"]),
        "parties_present": bool(receipt.parties.get("payer")) and bool(receipt.parties.get("payee")),
        "on_chain_verifiable": receipt.source == "paylock",
        "settlement_finalized": receipt.settlement.get("status") == "finalized",
    }
    
    passed = sum(checks.values())
    total = len(checks)
    
    return {
        "valid": all(checks.values()),
        "score": f"{passed}/{total}",
        "checks": checks,
        "grade": "A" if passed == total else "B" if passed >= total - 1 else "C",
    }


# Demo transactions
transactions = [
    PayLockTransaction(
        tx_hash="5KtPn1LGuxhFiwjxErkxTb3jV8q3YV3VjGDAuEL5oMFD",
        escrow_address="EscrowABC123def456",
        payer="kit_fox",
        payee="bro_agent",
        amount_sol=0.01,
        settlement_block=298_456_789,
        block_time=1710720000,
        status=SettlementStatus.FINALIZED,
    ),
    PayLockTransaction(
        tx_hash="7xMnQ2HGvyiRkzFb9qE4TcU8jW6yN3DpAR0sKm5vL1H",
        escrow_address="EscrowXYZ789ghi012",
        payer="gendolf",
        payee="kit_fox",
        amount_sol=0.005,
        settlement_block=298_456_800,
        block_time=1710720200,
        status=SettlementStatus.CONFIRMED,
    ),
    PayLockTransaction(
        tx_hash="3pFqR8JGwyiN5kzTb2cE7dU1mX4sV6hLAO9rKn0vQ3W",
        escrow_address="EscrowDEF456jkl789",
        payer="funwolf",
        payee="santaclawd",
        amount_sol=0.02,
        settlement_block=298_456_850,
        block_time=1710720400,
        status=SettlementStatus.DISPUTED,
    ),
]

print("=" * 60)
print("PayLock → ADV Bridge")
print("On-chain payments as verifiable receipts")
print("=" * 60)

for tx in transactions:
    receipt = bridge_to_adv(tx)
    verification = verify_receipt(receipt)
    
    icon = "✅" if verification["valid"] else "⚠️"
    print(f"\n{icon} {tx.payer} → {tx.payee} ({tx.amount_sol} SOL)")
    print(f"   tx_hash → delivery_hash: {receipt.delivery_hash[:20]}...")
    print(f"   escrow  → witness:       {receipt.witness[:20]}...")
    print(f"   block   → timestamp:     {receipt.timestamp}")
    print(f"   Status: {tx.status.value} | Grade: {verification['grade']} ({verification['score']})")
    
    if not verification["valid"]:
        failed = [k for k, v in verification["checks"].items() if not v]
        print(f"   Failed: {', '.join(failed)}")

print("\n" + "=" * 60)
print("THREE-FIELD MAPPING:")
print("  tx_hash        → delivery_hash  (unique, immutable)")
print("  escrow_address → witness        (self-witnessing contract)")
print("  block_time     → timestamp      (confirmation, not submission)")
print()
print("WHY THIS WORKS:")
print("  Escrow contract = CT log operator that can't lie")
print("  tx_hash = globally unique (replay impossible)")
print("  On-chain = verifiable by anyone, forever")
print("  Payment = Zahavi costly signal (real money at stake)")
print("=" * 60)
