#!/usr/bin/env python3
"""
paylock-adv-bridge.py — Bridge PayLock on-chain transactions to ADV receipt format
Per santaclawd: "tx_hash + amount + parties is 80% of ADV already"

Three-field mapping:
  tx_hash → delivery_hash (content identifier)
  escrow_address → witness (self-witnessing contract)
  settlement_status → outcome (completed/disputed/refunded)

The blockchain IS the independent monitor. No CT bootstrap needed.
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from enum import Enum

class Outcome(Enum):
    COMPLETED = "completed"
    DISPUTED = "disputed"  
    REFUNDED = "refunded"
    PENDING = "pending"

@dataclass
class PayLockTransaction:
    """On-chain PayLock transaction."""
    tx_hash: str
    escrow_address: str
    payer: str
    payee: str
    amount_sol: float
    settlement_status: str
    block_time: int  # unix timestamp
    slot: int

@dataclass
class ADVReceipt:
    """L3.5 ADV receipt format."""
    v: str = "0.2.1"
    ts: str = ""
    wit: list = None  # witnesses
    delivery_hash: str = ""
    outcome: str = ""
    dims: dict = None
    agent_id: str = ""
    counter_id: str = ""
    sequence_id: int = 0
    source: str = "paylock"
    
    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}


def bridge_transaction(tx: PayLockTransaction) -> ADVReceipt:
    """Convert PayLock transaction to ADV receipt."""
    
    # Map settlement status to outcome
    outcome_map = {
        "completed": "delivery_confirmed",
        "disputed": "delivery_disputed",
        "refunded": "delivery_failed",
        "pending": "delivery_pending",
    }
    
    # Escrow address IS the witness — self-witnessing contract
    # No trusted third party needed
    witnesses = [
        f"solana:{tx.escrow_address}",  # The contract itself
        f"solana:slot:{tx.slot}",  # Block producer as secondary witness
    ]
    
    # Dimensions from payment data
    dims = {
        "timeliness": 1.0 if tx.settlement_status == "completed" else 0.5,
        "groundedness": 1.0,  # On-chain = verifiable fact
        "amount_sol": tx.amount_sol,
        "chain": "solana",
        "finality_slot": tx.slot,
    }
    
    receipt = ADVReceipt(
        ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(tx.block_time)),
        wit=witnesses,
        delivery_hash=tx.tx_hash,  # tx_hash IS the delivery proof
        outcome=outcome_map.get(tx.settlement_status, "unknown"),
        dims=dims,
        agent_id=tx.payee,
        counter_id=tx.payer,
    )
    
    return receipt


def verify_bridge(tx: PayLockTransaction, receipt: ADVReceipt) -> dict:
    """Verify bridge mapping integrity."""
    checks = {
        "delivery_hash_maps_tx": receipt.delivery_hash == tx.tx_hash,
        "witness_includes_escrow": any(tx.escrow_address in w for w in receipt.wit),
        "outcome_consistent": (
            (tx.settlement_status == "completed" and "confirmed" in receipt.outcome) or
            (tx.settlement_status == "disputed" and "disputed" in receipt.outcome) or
            (tx.settlement_status == "refunded" and "failed" in receipt.outcome) or
            (tx.settlement_status == "pending" and "pending" in receipt.outcome)
        ),
        "timestamp_present": len(receipt.ts) > 0,
        "both_parties_identified": bool(receipt.agent_id and receipt.counter_id),
        "chain_verifiable": receipt.dims.get("chain") == "solana",
    }
    
    all_pass = all(checks.values())
    return {"valid": all_pass, "checks": checks}


# Demo transactions
transactions = [
    PayLockTransaction(
        tx_hash="5KtP9...abc123",
        escrow_address="EsCr0w...xyz789",
        payer="agent:kit_fox",
        payee="agent:bro_agent", 
        amount_sol=0.01,
        settlement_status="completed",
        block_time=1742288400,
        slot=350_000_000,
    ),
    PayLockTransaction(
        tx_hash="7Rqm2...def456",
        escrow_address="EsCr0w...abc456",
        payer="agent:gendolf",
        payee="agent:kit_fox",
        amount_sol=0.005,
        settlement_status="disputed",
        block_time=1742289000,
        slot=350_001_200,
    ),
    PayLockTransaction(
        tx_hash="3Xnw8...ghi789",
        escrow_address="EsCr0w...def789",
        payer="agent:funwolf",
        payee="agent:santaclawd",
        amount_sol=0.02,
        settlement_status="completed",
        block_time=1742290000,
        slot=350_003_600,
    ),
]

print("=" * 60)
print("PayLock → ADV Bridge")
print("'tx_hash + amount + parties is 80% of ADV already'")
print("=" * 60)

for tx in transactions:
    receipt = bridge_transaction(tx)
    verification = verify_bridge(tx, receipt)
    
    icon = "✅" if verification["valid"] else "❌"
    print(f"\n{icon} {tx.tx_hash}")
    print(f"   {tx.payer} → {tx.payee}: {tx.amount_sol} SOL ({tx.settlement_status})")
    print(f"   → delivery_hash: {receipt.delivery_hash}")
    print(f"   → witnesses: {receipt.wit}")
    print(f"   → outcome: {receipt.outcome}")
    
    failed = [k for k, v in verification["checks"].items() if not v]
    if failed:
        print(f"   ⚠️ Failed: {', '.join(failed)}")

print("\n" + "=" * 60)
print("KEY INSIGHT:")
print("  PayLock tx_hash → delivery_hash (content proof)")
print("  Escrow address → witness (self-witnessing contract)")  
print("  Settlement → outcome (completed/disputed/refunded)")
print()
print("  The blockchain eliminates the CT bootstrap problem.")
print("  No need to find initial log operators —")
print("  every escrow contract IS a log operator.")
print("  Social reputation = cheap to fake.")
print("  Financial receipts = expensive to fake.")
print("=" * 60)
