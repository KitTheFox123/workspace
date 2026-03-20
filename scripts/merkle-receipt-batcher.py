#!/usr/bin/env python3
"""
merkle-receipt-batcher.py — Batch receipts into Merkle trees for efficient on-chain anchoring.

Per bro_agent (2026-03-20): "1000 receipts → 1 on-chain tx. O(log n) proof per receipt."
Per CT model (Itko 2024): move expensive validation client-side.

Architecture:
- Collect receipts during epoch (e.g., 1 hour)
- Build Merkle tree from receipt hashes
- Anchor root on-chain (1 tx per epoch)
- Any receipt provable with O(log n) inclusion proof
- PayLock delivery_hash = Merkle root
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict, field
from typing import Optional


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def hash_pair(left: str, right: str) -> str:
    """Hash two nodes. Sorted to ensure deterministic tree."""
    if left > right:
        left, right = right, left
    return sha256(left + right)


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
        canonical = json.dumps(asdict(self), sort_keys=True)
        return sha256(canonical)


@dataclass
class MerkleProof:
    """Inclusion proof for a single receipt."""
    receipt_hash: str
    proof_hashes: list[str]
    proof_directions: list[str]  # "left" or "right"
    root: str
    leaf_index: int

    def verify(self) -> bool:
        """Verify inclusion proof against root."""
        current = self.receipt_hash
        for h, direction in zip(self.proof_hashes, self.proof_directions):
            if direction == "left":
                current = hash_pair(h, current)
            else:
                current = hash_pair(current, h)
        return current == self.root


@dataclass
class MerkleEpoch:
    """One epoch of batched receipts."""
    epoch_id: int
    start_time: float
    end_time: float
    receipts: list[Receipt] = field(default_factory=list)
    tree_layers: list[list[str]] = field(default_factory=list)
    root: Optional[str] = None

    def add_receipt(self, receipt: Receipt):
        self.receipts.append(receipt)

    def build_tree(self):
        """Build Merkle tree from receipt hashes."""
        if not self.receipts:
            self.root = sha256("empty")
            return

        # Leaf layer
        leaves = [r.receipt_hash for r in self.receipts]
        # Pad to power of 2
        while len(leaves) & (len(leaves) - 1):
            leaves.append(sha256("padding"))

        self.tree_layers = [leaves]

        # Build layers bottom-up
        current = leaves
        while len(current) > 1:
            next_layer = []
            for i in range(0, len(current), 2):
                next_layer.append(hash_pair(current[i], current[i + 1]))
            self.tree_layers.append(next_layer)
            current = next_layer

        self.root = current[0]

    def get_proof(self, receipt_index: int) -> MerkleProof:
        """Generate inclusion proof for a receipt."""
        if not self.tree_layers:
            raise ValueError("Tree not built")

        proof_hashes = []
        proof_directions = []
        idx = receipt_index

        for layer in self.tree_layers[:-1]:  # skip root
            sibling_idx = idx ^ 1  # flip last bit
            if sibling_idx < len(layer):
                proof_hashes.append(layer[sibling_idx])
                proof_directions.append("left" if sibling_idx < idx else "right")
            idx //= 2

        return MerkleProof(
            receipt_hash=self.receipts[receipt_index].receipt_hash,
            proof_hashes=proof_hashes,
            proof_directions=proof_directions,
            root=self.root,
            leaf_index=receipt_index
        )

    @property
    def stats(self) -> dict:
        n = len(self.receipts)
        return {
            "epoch_id": self.epoch_id,
            "receipt_count": n,
            "tree_depth": len(self.tree_layers),
            "proof_size": len(self.tree_layers) - 1,  # hashes per proof
            "on_chain_txs": 1,
            "savings_vs_individual": f"{n}x" if n > 0 else "0x",
            "root": self.root[:16] if self.root else None,
        }


def demo():
    now = time.time()

    # Simulate 150 receipts (bro_agent's PayLock scale)
    epoch = MerkleEpoch(epoch_id=1, start_time=now, end_time=now + 3600)

    emitters = ["kit_fox", "bro_agent", "funwolf", "santaclawd", "clove"]
    actions = ["deliver", "verify", "attest", "search", "transfer"]
    grades = ["chain", "chain", "witness", "witness", "self"]

    for i in range(150):
        receipt = Receipt(
            emitter_id=emitters[i % 5],
            counterparty_id=emitters[(i + 1) % 5],
            action=actions[i % 5],
            content_hash=sha256(f"content_{i}"),
            sequence_id=i,
            timestamp=now + i * 24,
            evidence_grade=grades[i % 5]
        )
        epoch.add_receipt(receipt)

    epoch.build_tree()

    print("=" * 60)
    print("MERKLE RECEIPT BATCHER")
    print("=" * 60)
    print(f"\nEpoch stats:")
    for k, v in epoch.stats.items():
        print(f"  {k}: {v}")

    # Verify random proofs
    print(f"\nProof verification:")
    for idx in [0, 47, 99, 149]:
        proof = epoch.get_proof(idx)
        valid = proof.verify()
        r = epoch.receipts[idx]
        print(f"  Receipt #{idx} ({r.emitter_id}→{r.counterparty_id}): "
              f"{'✅ VALID' if valid else '❌ INVALID'} "
              f"(proof size: {len(proof.proof_hashes)} hashes)")

    # Tamper detection
    print(f"\nTamper detection:")
    proof = epoch.get_proof(47)
    # Modify proof hash
    tampered = MerkleProof(
        receipt_hash=sha256("TAMPERED"),
        proof_hashes=proof.proof_hashes,
        proof_directions=proof.proof_directions,
        root=proof.root,
        leaf_index=proof.leaf_index
    )
    print(f"  Tampered receipt #47: {'✅ VALID' if tampered.verify() else '❌ CAUGHT'}")

    print(f"\n{'=' * 60}")
    print("SCALING ANALYSIS")
    print("=" * 60)
    print(f"""
  Per-receipt on-chain:  150 txs × ~0.00025 SOL = 0.0375 SOL
  Merkle batched:        1 tx    × ~0.00025 SOL = 0.00025 SOL
  Savings:               150x gas reduction
  Proof overhead:        {epoch.stats['proof_size']} hashes per receipt (~{epoch.stats['proof_size'] * 32} bytes)
  
  At 1000 emitters/epoch: 1000x gas savings
  At 10000:               10000x
  
  "PayLock delivery_hash = Merkle root per epoch."
  — bro_agent (2026-03-20)
""")


if __name__ == "__main__":
    demo()
