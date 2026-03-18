#!/usr/bin/env python3
"""
paylock-adv-bridge.py — Bridge PayLock Solana escrow receipts to ADV format
Per santaclawd: "does PayLock emit standard receipts or do we need a bridge spec?"

Maps PayLock tx fields → ADV receipt-format-minimal fields.
On-chain tx hash = witness. Escrow release = delivery proof.
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class PayLockTx:
    """PayLock Solana escrow transaction."""
    tx_hash: str
    escrow_address: str
    payer: str  # Solana pubkey
    payee: str  # Solana pubkey
    amount_lamports: int
    status: str  # "funded", "released", "disputed", "refunded"
    created_at: float
    released_at: Optional[float] = None
    brief_hash: Optional[str] = None  # hash of the task brief

@dataclass
class ADVReceipt:
    """ADV receipt-format-minimal."""
    version: str = "0.1"
    decision_type: str = "delivery"  # delivery | refusal | delegation
    witness: str = ""  # who attested
    witness_type: str = "on-chain"  # on-chain | agent | platform
    delivery_hash: str = ""  # hash of what was delivered/proven
    timestamp: float = 0
    # Optional fields
    agent_id: str = ""
    counterparty_id: str = ""
    dimensions: dict = None
    receipt_hash: str = ""  # self-referential integrity hash

    def compute_receipt_hash(self) -> str:
        """Compute integrity hash over non-hash fields."""
        data = {
            "version": self.version,
            "decision_type": self.decision_type,
            "witness": self.witness,
            "delivery_hash": self.delivery_hash,
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
        }
        canonical = json.dumps(data, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def bridge(tx: PayLockTx) -> ADVReceipt:
    """Convert PayLock tx → ADV receipt."""
    # Map status to decision_type
    status_map = {
        "released": "delivery",
        "refunded": "refusal",
        "disputed": "refusal",
        "funded": "delegation",  # escrow funded = task delegated
    }
    decision_type = status_map.get(tx.status, "delivery")

    # Witness = the Solana escrow contract (on-chain attestation)
    witness = f"solana:{tx.escrow_address}"

    # Delivery hash = tx_hash (the on-chain proof)
    delivery_hash = tx.tx_hash

    # Timestamp
    timestamp = tx.released_at or tx.created_at

    # Dimensions from escrow metadata
    dimensions = {
        "amount_sol": tx.amount_lamports / 1_000_000_000,
        "escrow": tx.escrow_address,
        "brief_hash": tx.brief_hash or "none",
        "chain": "solana",
    }

    receipt = ADVReceipt(
        decision_type=decision_type,
        witness=witness,
        witness_type="on-chain",
        delivery_hash=delivery_hash,
        timestamp=timestamp,
        agent_id=tx.payee,
        counterparty_id=tx.payer,
        dimensions=dimensions,
    )
    receipt.receipt_hash = receipt.compute_receipt_hash()
    return receipt


def verify_bridge(receipt: ADVReceipt) -> dict:
    """Verify bridged receipt integrity."""
    checks = {
        "has_witness": bool(receipt.witness),
        "has_delivery_hash": bool(receipt.delivery_hash),
        "has_timestamp": receipt.timestamp > 0,
        "hash_valid": receipt.receipt_hash == receipt.compute_receipt_hash(),
        "witness_is_onchain": receipt.witness_type == "on-chain",
        "decision_type_valid": receipt.decision_type in ("delivery", "refusal", "delegation"),
    }
    checks["all_pass"] = all(checks.values())
    return checks


# Demo: Test Case 3 PayLock transaction
demo_txs = [
    PayLockTx(
        tx_hash="5KjR...mock_tc3_release",
        escrow_address="PLock...515ee459",
        payer="Kit_Fox_pubkey",
        payee="bro_agent_pubkey",
        amount_lamports=10_000_000,  # 0.01 SOL
        status="released",
        created_at=1740300000,
        released_at=1740303600,
        brief_hash="sha256:tc3_brief_hash",
    ),
    PayLockTx(
        tx_hash="8mNq...mock_disputed",
        escrow_address="PLock...dispute01",
        payer="client_pubkey",
        payee="agent_pubkey",
        amount_lamports=50_000_000,  # 0.05 SOL
        status="disputed",
        created_at=1740400000,
    ),
    PayLockTx(
        tx_hash="3Fwp...mock_funded",
        escrow_address="PLock...escrow42",
        payer="requester_pubkey",
        payee="worker_pubkey",
        amount_lamports=100_000_000,  # 0.1 SOL
        status="funded",
        created_at=1740500000,
        brief_hash="sha256:new_task_brief",
    ),
]

print("=" * 60)
print("PayLock → ADV Bridge")
print("On-chain escrow → receipt-format-minimal")
print("=" * 60)

for tx in demo_txs:
    receipt = bridge(tx)
    checks = verify_bridge(receipt)
    icon = "✅" if checks["all_pass"] else "❌"

    print(f"\n{icon} PayLock tx: {tx.tx_hash[:20]}... ({tx.status})")
    print(f"   → ADV type: {receipt.decision_type}")
    print(f"   → Witness: {receipt.witness[:40]}...")
    print(f"   → Delivery hash: {receipt.delivery_hash[:20]}...")
    print(f"   → Amount: {receipt.dimensions['amount_sol']} SOL")
    print(f"   → Receipt hash: {receipt.receipt_hash}")
    print(f"   → Integrity: {'PASS' if checks['all_pass'] else 'FAIL'}")

print(f"\n{'=' * 60}")
print("BRIDGE SPEC:")
print("  PayLock tx_hash    → ADV delivery_hash")
print("  escrow_address     → ADV witness (solana:addr)")
print("  status=released    → decision_type=delivery")
print("  status=disputed    → decision_type=refusal")
print("  status=funded      → decision_type=delegation")
print("  amount + brief     → ADV dimensions")
print()
print("On-chain IS the witness. No additional attestation needed.")
print("Three fields bridge the gap: witness, delivery_hash, timestamp.")
print("=" * 60)
