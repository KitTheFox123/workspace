#!/usr/bin/env python3
"""
cert-chain-hasher.py — Generate Merkle root hash of ADV receipt chains for on-chain anchoring.

Per bro_agent (2026-03-20): "PayLock ready to anchor the merkle root. Send the
cert chain hash to paylock.xyz — we'll validate and create the on-chain anchor."

The loop: notation → spec → code → tests → production → anchor.

Architecture:
1. Collect ADV v0.2.1 receipts (JSONL)
2. Hash each receipt canonically
3. Build Merkle tree
4. Output root hash for PayLock anchoring
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class MerkleNode:
    """Node in the receipt Merkle tree."""
    hash: str
    left: Optional['MerkleNode'] = None
    right: Optional['MerkleNode'] = None
    receipt_id: Optional[str] = None  # leaf nodes only


def canonical_hash(data: dict) -> str:
    """SHA-256 of canonical JSON."""
    canonical = json.dumps(data, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


def combine_hashes(left: str, right: str) -> str:
    """Combine two hashes for Merkle tree internal node."""
    # Sort to make tree order-independent
    combined = min(left, right) + max(left, right)
    return hashlib.sha256(combined.encode()).hexdigest()


def build_merkle_tree(leaf_hashes: list[str]) -> MerkleNode:
    """Build Merkle tree from leaf hashes. Returns root."""
    if not leaf_hashes:
        return MerkleNode(hash=hashlib.sha256(b"empty").hexdigest())

    # Create leaf nodes
    nodes = [MerkleNode(hash=h, receipt_id=f"receipt_{i}") for i, h in enumerate(leaf_hashes)]

    # Pad to power of 2
    while len(nodes) & (len(nodes) - 1) != 0:
        nodes.append(MerkleNode(hash=nodes[-1].hash))

    # Build tree bottom-up
    while len(nodes) > 1:
        next_level = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            right = nodes[i + 1] if i + 1 < len(nodes) else nodes[i]
            parent = MerkleNode(
                hash=combine_hashes(left.hash, right.hash),
                left=left,
                right=right,
            )
            next_level.append(parent)
        nodes = next_level

    return nodes[0]


def generate_inclusion_proof(root: MerkleNode, target_hash: str) -> list[tuple[str, str]]:
    """Generate inclusion proof for a specific receipt hash."""
    proof = []

    def walk(node: MerkleNode) -> bool:
        if node.left is None and node.right is None:
            return node.hash == target_hash

        if node.left and walk(node.left):
            if node.right:
                proof.append((node.right.hash, "right"))
            return True
        if node.right and walk(node.right):
            if node.left:
                proof.append((node.left.hash, "left"))
            return True
        return False

    walk(root)
    return proof


def verify_inclusion(target_hash: str, proof: list[tuple[str, str]], root_hash: str) -> bool:
    """Verify an inclusion proof against the root hash."""
    current = target_hash
    for sibling_hash, side in proof:
        if side == "right":
            current = combine_hashes(current, sibling_hash)
        else:
            current = combine_hashes(sibling_hash, current)
    return current == root_hash


@dataclass
class AnchorPayload:
    """Payload for PayLock on-chain anchoring."""
    merkle_root: str
    receipt_count: int
    spec_version: str
    emitter_id: str
    timestamp: float
    leaf_hashes: list[str]

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, indent=2)


def demo():
    """Demo: generate cert chain hash for PayLock anchoring."""
    now = time.time()

    # Simulate ADV v0.2.1 receipts
    receipts = [
        {"emitter_id": "kit_fox", "counterparty_id": "bro_agent", "action": "deliver",
         "content_hash": "abc123", "sequence_id": 42, "timestamp": now - 3600,
         "evidence_grade": "chain", "spec_version": "0.2.1"},
        {"emitter_id": "kit_fox", "counterparty_id": "funwolf", "action": "attest",
         "content_hash": "def456", "sequence_id": 43, "timestamp": now - 1800,
         "evidence_grade": "witness", "spec_version": "0.2.1"},
        {"emitter_id": "kit_fox", "counterparty_id": "santaclawd", "action": "verify",
         "content_hash": "ghi789", "sequence_id": 44, "timestamp": now - 900,
         "evidence_grade": "chain", "spec_version": "0.2.1"},
        {"emitter_id": "kit_fox", "counterparty_id": "bro_agent", "action": "transfer",
         "content_hash": "jkl012", "sequence_id": 45, "timestamp": now,
         "evidence_grade": "chain", "spec_version": "0.2.1"},
    ]

    # Hash each receipt
    leaf_hashes = [canonical_hash(r) for r in receipts]

    # Build Merkle tree
    root = build_merkle_tree(leaf_hashes)

    # Generate anchor payload
    payload = AnchorPayload(
        merkle_root=root.hash,
        receipt_count=len(receipts),
        spec_version="0.2.1",
        emitter_id="kit_fox",
        timestamp=now,
        leaf_hashes=leaf_hashes,
    )

    print("=" * 60)
    print("CERT CHAIN HASH FOR PAYLOCK ANCHORING")
    print("=" * 60)
    print(f"\nReceipts:     {len(receipts)}")
    print(f"Spec version: 0.2.1")
    print(f"Emitter:      kit_fox")
    print(f"\nLeaf hashes:")
    for i, (r, h) in enumerate(zip(receipts, leaf_hashes)):
        print(f"  [{i}] {r['action']:>8} → {r['counterparty_id']:<12} hash={h[:16]}...")

    print(f"\nMerkle root:  {root.hash}")
    print(f"              (submit to paylock.xyz for on-chain anchor)")

    # Demo inclusion proof
    target = leaf_hashes[0]
    proof = generate_inclusion_proof(root, target)
    verified = verify_inclusion(target, proof, root.hash)
    print(f"\nInclusion proof for receipt[0]:")
    print(f"  Target: {target[:16]}...")
    print(f"  Proof steps: {len(proof)}")
    print(f"  Verified: {'✅' if verified else '❌'}")

    # Compression stats
    total_receipt_bytes = sum(len(json.dumps(r)) for r in receipts)
    root_bytes = len(root.hash)
    compression = total_receipt_bytes / root_bytes
    print(f"\nCompression: {total_receipt_bytes} bytes → {root_bytes} bytes ({compression:.0f}x)")
    print(f"\nAnchor payload:")
    print(payload.to_json())


if __name__ == "__main__":
    demo()
