#!/usr/bin/env python3
"""
merkle-receipt-batcher.py — Batch ADV receipts into Merkle trees for scalable on-chain anchoring.

Per bro_agent (2026-03-20): "50x is the inflection point. batch root anchoring +
local Merkle validation = exactly how PayLock handles high-volume receipt verification."

Architecture:
- Receipts accumulate off-chain
- Batch into Merkle tree at threshold (time or count)
- Anchor single root on-chain
- Any receipt provable with O(log n) proof
- CT model: millions of certs, handful of log entries
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Optional


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class MerkleNode:
    hash: str
    left: Optional['MerkleNode'] = None
    right: Optional['MerkleNode'] = None
    leaf_data: Optional[str] = None


@dataclass
class MerkleProof:
    leaf_hash: str
    proof_hashes: list[tuple[str, str]]  # (hash, side) where side = "L" or "R"
    root_hash: str

    def verify(self) -> bool:
        current = self.leaf_hash
        for sibling_hash, side in self.proof_hashes:
            if side == "L":
                current = sha256(sibling_hash + current)
            else:
                current = sha256(current + sibling_hash)
        return current == self.root_hash

    @property
    def proof_size(self) -> int:
        return len(self.proof_hashes)


@dataclass
class ReceiptBatch:
    batch_id: str
    receipts: list[dict]
    root: Optional[MerkleNode] = None
    created_at: float = field(default_factory=time.time)
    anchored: bool = False
    anchor_tx: Optional[str] = None

    @property
    def root_hash(self) -> str:
        return self.root.hash if self.root else ""

    @property
    def size(self) -> int:
        return len(self.receipts)


class MerkleReceiptBatcher:
    def __init__(self, batch_threshold: int = 100, batch_interval_s: float = 300):
        self.batch_threshold = batch_threshold
        self.batch_interval_s = batch_interval_s
        self.pending: list[dict] = []
        self.batches: list[ReceiptBatch] = []
        self.leaf_to_batch: dict[str, str] = {}  # leaf_hash -> batch_id

    def add_receipt(self, receipt: dict) -> Optional[ReceiptBatch]:
        """Add receipt. Returns batch if threshold reached."""
        self.pending.append(receipt)
        if len(self.pending) >= self.batch_threshold:
            return self.flush()
        return None

    def flush(self) -> Optional[ReceiptBatch]:
        """Flush pending receipts into a batch."""
        if not self.pending:
            return None

        batch_id = sha256(str(time.time()) + str(len(self.batches)))[:16]
        batch = ReceiptBatch(batch_id=batch_id, receipts=list(self.pending))

        # Build Merkle tree
        leaves = []
        for r in batch.receipts:
            leaf_hash = sha256(json.dumps(r, sort_keys=True))
            leaves.append(MerkleNode(hash=leaf_hash, leaf_data=json.dumps(r, sort_keys=True)))
            self.leaf_to_batch[leaf_hash] = batch_id

        # Pad to power of 2
        while len(leaves) & (len(leaves) - 1) != 0:
            leaves.append(MerkleNode(hash=sha256("PADDING")))

        batch.root = self._build_tree(leaves)
        self.batches.append(batch)
        self.pending = []
        return batch

    def _build_tree(self, nodes: list[MerkleNode]) -> MerkleNode:
        if len(nodes) == 1:
            return nodes[0]

        parents = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            right = nodes[i + 1] if i + 1 < len(nodes) else left
            parent = MerkleNode(
                hash=sha256(left.hash + right.hash),
                left=left,
                right=right
            )
            parents.append(parent)
        return self._build_tree(parents)

    def get_proof(self, receipt: dict) -> Optional[MerkleProof]:
        """Get Merkle proof for a specific receipt."""
        leaf_hash = sha256(json.dumps(receipt, sort_keys=True))
        batch_id = self.leaf_to_batch.get(leaf_hash)
        if not batch_id:
            return None

        batch = next((b for b in self.batches if b.batch_id == batch_id), None)
        if not batch or not batch.root:
            return None

        # Walk tree to find proof path
        proof_hashes = []
        found = self._find_proof(batch.root, leaf_hash, proof_hashes)
        if not found:
            return None

        return MerkleProof(
            leaf_hash=leaf_hash,
            proof_hashes=proof_hashes,
            root_hash=batch.root_hash
        )

    def _find_proof(self, node: MerkleNode, target: str,
                     proof: list[tuple[str, str]]) -> bool:
        if node.hash == target and node.leaf_data is not None:
            return True

        if node.left and node.right:
            if self._find_proof(node.left, target, proof):
                proof.append((node.right.hash, "R"))
                return True
            if self._find_proof(node.right, target, proof):
                proof.append((node.left.hash, "L"))
                return True

        return False

    def stats(self) -> dict:
        total_receipts = sum(b.size for b in self.batches) + len(self.pending)
        total_batches = len(self.batches)
        return {
            "total_receipts": total_receipts,
            "total_batches": total_batches,
            "pending": len(self.pending),
            "compression_ratio": f"{total_receipts}:{total_batches}" if total_batches else "N/A",
            "on_chain_txs_saved": total_receipts - total_batches if total_batches else 0,
            "proof_depth": math.ceil(math.log2(self.batch_threshold)) if self.batch_threshold > 1 else 0
        }


def demo():
    print("=" * 60)
    print("MERKLE RECEIPT BATCHER")
    print("=" * 60)

    batcher = MerkleReceiptBatcher(batch_threshold=50)

    # Simulate 150 receipts from multiple emitters
    receipts = []
    for i in range(150):
        r = {
            "emitter_id": f"agent_{i % 10}",
            "counterparty_id": f"agent_{(i + 5) % 10}",
            "action": ["deliver", "verify", "attest", "transfer"][i % 4],
            "sequence_id": i,
            "content_hash": sha256(f"content_{i}")[:16],
            "timestamp": time.time() + i,
            "evidence_grade": ["chain", "witness", "self"][i % 3]
        }
        receipts.append(r)
        batch = batcher.add_receipt(r)
        if batch:
            print(f"\n  Batch {batch.batch_id}: {batch.size} receipts → root {batch.root_hash[:16]}...")

    # Flush remaining
    final = batcher.flush()
    if final:
        print(f"\n  Batch {final.batch_id}: {final.size} receipts → root {final.root_hash[:16]}...")

    # Stats
    stats = batcher.stats()
    print(f"\n{'=' * 60}")
    print("SCALING RESULTS")
    print(f"{'=' * 60}")
    print(f"  Total receipts:      {stats['total_receipts']}")
    print(f"  On-chain batches:    {stats['total_batches']}")
    print(f"  Compression:         {stats['compression_ratio']}")
    print(f"  Txs saved:           {stats['on_chain_txs_saved']}")
    print(f"  Max proof depth:     {stats['proof_depth']} hashes")

    # Verify a random proof
    print(f"\n{'=' * 60}")
    print("PROOF VERIFICATION")
    print(f"{'=' * 60}")

    test_receipt = receipts[42]
    proof = batcher.get_proof(test_receipt)
    if proof:
        print(f"  Receipt #42:         {proof.leaf_hash[:16]}...")
        print(f"  Proof size:          {proof.proof_size} hashes")
        print(f"  Root:                {proof.root_hash[:16]}...")
        print(f"  Valid:               {'✅' if proof.verify() else '❌'}")

    # Tamper test
    tampered = dict(test_receipt)
    tampered["action"] = "TAMPERED"
    tampered_proof = batcher.get_proof(tampered)
    print(f"\n  Tampered receipt:    {'❌ NOT FOUND (correct)' if not tampered_proof else '⚠️ FOUND (error)'}")

    print(f"\n{'=' * 60}")
    print("ARCHITECTURE")
    print(f"{'=' * 60}")
    print("""
  150 receipts → 3 on-chain txs (50:1 compression)
  Any receipt provable with ~6 hashes (O(log n))
  Tampered receipts: no valid proof exists

  Per bro_agent: "50x is the inflection point."
  Per CT model: millions of certs, handful of log entries.
  Per Itko (2024): 0.25 CPU core, 2M certs/day.
""")


if __name__ == "__main__":
    demo()
