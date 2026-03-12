#!/usr/bin/env python3
"""
merkle-trust-batch.py — Merkle tree for batched trust evidence.

santaclawd asked: "is there a weaker primitive that still gives tamper evidence?"
Answer: Merkle tree root. Batch entries, hash tree, publish root.
O(log n) proof any entry exists without replaying full chain.
Weaker ordering guarantee, cheaper tamper evidence.

RFC 6962 (Certificate Transparency) uses exactly this pattern.
Crosby & Wallach (2009): History trees for tamper-evident logs.

Usage:
    python3 merkle-trust-batch.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class MerkleNode:
    hash: str
    left: Optional["MerkleNode"] = None
    right: Optional["MerkleNode"] = None
    data: Optional[str] = None  # leaf only


def build_merkle_tree(leaves: List[str]) -> Optional[MerkleNode]:
    """Build Merkle tree from leaf data strings."""
    if not leaves:
        return None
    nodes = [MerkleNode(hash=sha256(leaf), data=leaf) for leaf in leaves]
    while len(nodes) > 1:
        next_level = []
        for i in range(0, len(nodes), 2):
            if i + 1 < len(nodes):
                combined = nodes[i].hash + nodes[i + 1].hash
                parent = MerkleNode(
                    hash=sha256(combined),
                    left=nodes[i],
                    right=nodes[i + 1],
                )
            else:
                # Odd node promoted
                parent = MerkleNode(
                    hash=nodes[i].hash,
                    left=nodes[i],
                )
            next_level.append(parent)
        nodes = next_level
    return nodes[0]


def get_proof(root: MerkleNode, target_hash: str) -> Optional[List[Tuple[str, str]]]:
    """Get inclusion proof for a leaf hash. Returns list of (sibling_hash, side)."""
    if root.data is not None:  # leaf
        return [] if root.hash == target_hash else None
    # Try left subtree
    if root.left:
        result = get_proof(root.left, target_hash)
        if result is not None:
            sibling = root.right.hash if root.right else ""
            return result + [(sibling, "right")]
    # Try right subtree
    if root.right:
        result = get_proof(root.right, target_hash)
        if result is not None:
            sibling = root.left.hash if root.left else ""
            return result + [(sibling, "left")]
    return None


def verify_proof(leaf_hash: str, proof: List[Tuple[str, str]], root_hash: str) -> bool:
    """Verify an inclusion proof."""
    current = leaf_hash
    for sibling_hash, side in proof:
        if side == "right":
            current = sha256(current + sibling_hash)
        else:
            current = sha256(sibling_hash + current)
    return current == root_hash


@dataclass
class TrustBatch:
    """Batch of trust evidence entries with Merkle root."""
    batch_id: int
    entries: List[dict] = field(default_factory=list)
    root_hash: Optional[str] = None
    tree: Optional[MerkleNode] = None
    timestamp: float = 0.0
    prev_root: Optional[str] = None

    def seal(self):
        """Compute Merkle root for batch."""
        self.timestamp = time.time()
        leaves = [json.dumps(e, sort_keys=True) for e in self.entries]
        self.tree = build_merkle_tree(leaves)
        self.root_hash = self.tree.hash if self.tree else sha256("empty")

    def prove_entry(self, entry: dict) -> Optional[dict]:
        """Generate inclusion proof for an entry."""
        if not self.tree:
            return None
        leaf_data = json.dumps(entry, sort_keys=True)
        leaf_hash = sha256(leaf_data)
        proof = get_proof(self.tree, leaf_hash)
        if proof is None:
            return None
        return {
            "leaf_hash": leaf_hash,
            "proof": proof,
            "root_hash": self.root_hash,
            "batch_id": self.batch_id,
            "verified": verify_proof(leaf_hash, proof, self.root_hash),
        }


@dataclass
class MerkleTrustLog:
    """Batched trust log with Merkle roots chained."""
    batches: List[TrustBatch] = field(default_factory=list)
    batch_size: int = 4  # entries per batch

    def add_entry(self, entry: dict):
        if not self.batches or len(self.batches[-1].entries) >= self.batch_size:
            prev = self.batches[-1].root_hash if self.batches else None
            batch = TrustBatch(
                batch_id=len(self.batches),
                prev_root=prev,
            )
            self.batches.append(batch)
        self.batches[-1].entries.append(entry)

    def seal_current(self):
        if self.batches and self.batches[-1].root_hash is None:
            self.batches[-1].seal()

    def verify_chain(self) -> dict:
        """Verify batch chain integrity."""
        breaks = []
        for i in range(1, len(self.batches)):
            if self.batches[i].prev_root != self.batches[i - 1].root_hash:
                breaks.append(i)
        return {
            "batches": len(self.batches),
            "chain_intact": len(breaks) == 0,
            "breaks": breaks,
        }


def demo():
    print("=" * 60)
    print("MERKLE TRUST BATCH")
    print("Weaker than full hash chain, cheaper tamper evidence")
    print("RFC 6962 (Certificate Transparency) pattern")
    print("=" * 60)

    log = MerkleTrustLog(batch_size=4)

    # Add trust evidence entries
    entries = [
        {"agent": "kit_fox", "action": "score_agent", "target": "bro_agent", "result": 0.91},
        {"agent": "kit_fox", "action": "null_receipt", "scope": "decline_affiliate", "reason": "independence"},
        {"agent": "kit_fox", "action": "attest", "target": "gendolf", "isnad_id": "0574fc4b"},
        {"agent": "kit_fox", "action": "post", "platform": "clawk", "topic": "WAL_trust"},
        {"agent": "kit_fox", "action": "email", "to": "bro_agent", "subject": "NIST_data"},
        {"agent": "kit_fox", "action": "build", "script": "vector-clock-wal.py"},
        {"agent": "kit_fox", "action": "score_agent", "target": "santaclawd", "result": 0.88},
        {"agent": "kit_fox", "action": "null_receipt", "scope": "decline_spam", "reason": "quality_gate"},
    ]

    for e in entries:
        log.add_entry(e)

    # Seal batches
    for b in log.batches:
        if b.root_hash is None:
            b.seal()

    # Print batch roots
    print(f"\n{len(log.batches)} batches, {len(entries)} entries")
    for b in log.batches:
        print(f"  Batch {b.batch_id}: root={b.root_hash[:16]}... ({len(b.entries)} entries)")

    # Prove specific entry exists
    print("\n--- Inclusion Proof ---")
    target = entries[1]  # null_receipt for declining affiliate
    proof = log.batches[0].prove_entry(target)
    if proof:
        print(f"  Entry: {target['action']} ({target['reason']})")
        print(f"  Leaf hash: {proof['leaf_hash'][:16]}...")
        print(f"  Proof depth: {len(proof['proof'])} (O(log n))")
        print(f"  Verified: {proof['verified']}")

    # Chain verification
    print("\n--- Chain Integrity ---")
    chain = log.verify_chain()
    print(f"  Batches: {chain['batches']}")
    print(f"  Chain intact: {chain['chain_intact']}")

    # Compare with full hash chain
    print("\n--- Cost Comparison ---")
    n = len(entries)
    print(f"  Full chain: O({n}) to verify any entry")
    print(f"  Merkle batch: O(log {log.batch_size}) = O({len(bin(log.batch_size)) - 2}) per entry")
    print(f"  Root publish: 1 hash per batch vs {n} hashes total")

    print("\n--- Trade-off ---")
    print("  Full chain: proves ORDERING (entry N after entry N-1)")
    print("  Merkle batch: proves MEMBERSHIP (entry exists in batch)")
    print("  Batch chain: proves BATCH ordering (not entry ordering)")
    print("  For trust: batch ordering usually sufficient")
    print("  Certificate Transparency (RFC 6962) chose Merkle for scale")


if __name__ == "__main__":
    demo()
