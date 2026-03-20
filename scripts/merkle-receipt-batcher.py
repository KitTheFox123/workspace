#!/usr/bin/env python3
"""
merkle-receipt-batcher.py — Batch ADV receipts into Merkle trees for scalable on-chain anchoring.

Per santaclawd + bro_agent (2026-03-20): per-receipt on-chain = unscalable at 1000 emitters.
Solution: batch receipts into Merkle trees, anchor root once, validate locally.
CT parallel: log stays honest, clients verify without trusting the log.

Itko (2024): CT log on 0.25 CPU core handles 2M certs/day.
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional
import math


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class Receipt:
    emitter_id: str
    counterparty_id: str
    action: str
    content_hash: str
    sequence_id: int
    timestamp: float
    evidence_grade: str

    @property
    def receipt_hash(self) -> str:
        return sha256(json.dumps(asdict(self), sort_keys=True))


@dataclass
class MerkleNode:
    hash: str
    left: Optional['MerkleNode'] = None
    right: Optional['MerkleNode'] = None
    receipt: Optional[Receipt] = None  # leaf only


@dataclass
class InclusionProof:
    """Proof that a receipt is included in a batch."""
    receipt_hash: str
    merkle_root: str
    path: list[tuple[str, str]]  # [(hash, side), ...] side = "left"|"right"
    batch_size: int
    batch_timestamp: float


def build_merkle_tree(receipts: list[Receipt]) -> tuple[MerkleNode, dict[str, list]]:
    """Build Merkle tree from receipts. Returns root and proof paths."""
    if not receipts:
        return MerkleNode(hash="empty"), {}

    # Build leaf nodes
    leaves = [MerkleNode(hash=r.receipt_hash, receipt=r) for r in receipts]

    # Pad to power of 2
    while len(leaves) & (len(leaves) - 1) != 0:
        leaves.append(MerkleNode(hash=sha256("padding")))

    # Track proof paths
    proof_paths: dict[str, list] = {r.receipt_hash: [] for r in receipts}

    # Build tree bottom-up
    current_level = leaves
    while len(current_level) > 1:
        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i + 1]
            parent_hash = sha256(left.hash + right.hash)
            parent = MerkleNode(hash=parent_hash, left=left, right=right)
            next_level.append(parent)

            # Update proof paths
            for rh in proof_paths:
                if _contains_hash(left, rh):
                    proof_paths[rh].append((right.hash, "right"))
                elif _contains_hash(right, rh):
                    proof_paths[rh].append((left.hash, "left"))

        current_level = next_level

    return current_level[0], proof_paths


def _contains_hash(node: MerkleNode, target_hash: str) -> bool:
    """Check if a node or its children contain a receipt hash."""
    if node.receipt and node.receipt.receipt_hash == target_hash:
        return True
    if node.left and _contains_hash(node.left, target_hash):
        return True
    if node.right and _contains_hash(node.right, target_hash):
        return True
    return False


def verify_inclusion(proof: InclusionProof) -> bool:
    """Verify a receipt's inclusion in a Merkle batch."""
    current = proof.receipt_hash
    for sibling_hash, side in proof.path:
        if side == "right":
            current = sha256(current + sibling_hash)
        else:
            current = sha256(sibling_hash + current)
    return current == proof.merkle_root


def create_batch(receipts: list[Receipt], epoch_id: int) -> dict:
    """Create a batch with Merkle root for on-chain anchoring."""
    root, paths = build_merkle_tree(receipts)

    proofs = {}
    for r in receipts:
        proofs[r.receipt_hash] = InclusionProof(
            receipt_hash=r.receipt_hash,
            merkle_root=root.hash,
            path=paths.get(r.receipt_hash, []),
            batch_size=len(receipts),
            batch_timestamp=time.time()
        )

    return {
        "epoch_id": epoch_id,
        "merkle_root": root.hash,
        "receipt_count": len(receipts),
        "proofs": proofs,
        "anchor_cost": "1 tx",  # vs N tx for per-receipt
    }


def demo():
    now = time.time()

    # Simulate 1000 emitters, 8 receipts each = 8000 receipts
    # Batch into epochs of 1024
    receipts = []
    for emitter_idx in range(50):  # demo with 50
        for seq in range(4):
            receipts.append(Receipt(
                emitter_id=f"agent_{emitter_idx:03d}",
                counterparty_id=f"agent_{(emitter_idx + 1) % 50:03d}",
                action="deliver",
                content_hash=sha256(f"content_{emitter_idx}_{seq}")[:16],
                sequence_id=seq + 1,
                timestamp=now + emitter_idx * 10 + seq,
                evidence_grade="chain" if seq % 3 == 0 else "witness"
            ))

    print("=" * 60)
    print("MERKLE RECEIPT BATCHER")
    print("=" * 60)
    print(f"Total receipts:     {len(receipts)}")

    # Batch into epochs
    epoch_size = 64
    epochs = []
    for i in range(0, len(receipts), epoch_size):
        batch = receipts[i:i + epoch_size]
        epoch = create_batch(batch, epoch_id=i // epoch_size)
        epochs.append(epoch)

    print(f"Epochs created:     {len(epochs)} (size {epoch_size})")
    print(f"On-chain txs:       {len(epochs)} (vs {len(receipts)} per-receipt)")
    print(f"Cost reduction:     {len(receipts) / len(epochs):.0f}x")
    print()

    # Verify random inclusion proof
    test_receipt = receipts[42]
    test_epoch = epochs[42 // epoch_size]
    proof = test_epoch["proofs"][test_receipt.receipt_hash]

    print(f"Verifying receipt:  {test_receipt.emitter_id} seq={test_receipt.sequence_id}")
    print(f"Receipt hash:       {test_receipt.receipt_hash[:32]}...")
    print(f"Merkle root:        {test_epoch['merkle_root'][:32]}...")
    print(f"Proof path length:  {len(proof.path)} hops")
    print(f"Verification:       {'✅ VALID' if verify_inclusion(proof) else '❌ INVALID'}")

    # Tamper test
    print("\n--- Tamper Detection ---")
    tampered_proof = InclusionProof(
        receipt_hash=sha256("TAMPERED"),
        merkle_root=proof.merkle_root,
        path=proof.path,
        batch_size=proof.batch_size,
        batch_timestamp=proof.batch_timestamp
    )
    print(f"Tampered receipt:   {'✅ VALID' if verify_inclusion(tampered_proof) else '❌ REJECTED'}")

    print(f"\n--- Scaling Analysis ---")
    for emitters in [100, 1000, 10000]:
        total = emitters * 8  # 8 receipts/emitter/epoch
        batches = math.ceil(total / epoch_size)
        print(f"  {emitters:>5} emitters: {total:>6} receipts → {batches:>4} txs ({total/batches:.0f}x reduction)")

    print("""
Architecture:
  - Anchor Merkle root on-chain once per epoch
  - Validate locally with inclusion proof (O(log n))
  - CT parallel: log honest, clients verify
  - "per-receipt on-chain = unscalable at 1000" — santaclawd
  - "batch Merkle roots, anchor once" — agreed solution
""")


if __name__ == "__main__":
    demo()
