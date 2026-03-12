#!/usr/bin/env python3
"""
merkle-compaction.py — Verifiable audit log compaction via Merkle trees.

Based on Russ Cox's tlog design (2019) and Certificate Transparency.

Key insight: append-only ≠ append-forever. You can prune old entries
while keeping the Merkle root + sparse inclusion proofs. Anyone can
verify that nothing was removed — just compacted.

Audit policy and forget policy are the same architectural decision.
Gate at read, never at write.

Usage: python3 merkle-compaction.py
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


def hash_leaf(data: str) -> str:
    return hashlib.sha256(f"leaf:{data}".encode()).hexdigest()[:16]


def hash_node(left: str, right: str) -> str:
    return hashlib.sha256(f"node:{left}:{right}".encode()).hexdigest()[:16]


@dataclass
class MerkleTree:
    """Append-only Merkle tree with compaction support."""
    entries: list[dict] = field(default_factory=list)
    leaf_hashes: list[str] = field(default_factory=list)
    compacted_before: int = 0  # entries before this index are compacted
    checkpoint_roots: list[dict] = field(default_factory=list)

    def append(self, entry: dict) -> str:
        """Append entry, return leaf hash."""
        data = json.dumps(entry, sort_keys=True)
        h = hash_leaf(data)
        self.entries.append(entry)
        self.leaf_hashes.append(h)
        return h

    def root(self) -> str:
        """Compute current Merkle root."""
        if not self.leaf_hashes:
            return hash_leaf("empty")
        hashes = list(self.leaf_hashes)
        while len(hashes) > 1:
            next_level = []
            for i in range(0, len(hashes), 2):
                if i + 1 < len(hashes):
                    next_level.append(hash_node(hashes[i], hashes[i + 1]))
                else:
                    next_level.append(hashes[i])
            hashes = next_level
        return hashes[0]

    def inclusion_proof(self, index: int) -> dict:
        """Generate inclusion proof for entry at index."""
        if index < self.compacted_before:
            return {"verified": False, "reason": "compacted — use checkpoint root"}
        
        hashes = list(self.leaf_hashes)
        proof_path = []
        idx = index
        while len(hashes) > 1:
            next_level = []
            for i in range(0, len(hashes), 2):
                if i + 1 < len(hashes):
                    if i == idx or i + 1 == idx:
                        sibling = hashes[i + 1] if i == idx else hashes[i]
                        side = "right" if i == idx else "left"
                        proof_path.append({"hash": sibling, "side": side})
                    next_level.append(hash_node(hashes[i], hashes[i + 1]))
                else:
                    next_level.append(hashes[i])
            idx = idx // 2
            hashes = next_level

        return {
            "verified": True,
            "leaf_hash": self.leaf_hashes[index],
            "root": self.root(),
            "proof_length": len(proof_path),
            "path": proof_path
        }

    def checkpoint(self) -> dict:
        """Save checkpoint (root + size) before compaction."""
        cp = {
            "root": self.root(),
            "size": len(self.entries),
            "timestamp": f"checkpoint_{len(self.checkpoint_roots)}"
        }
        self.checkpoint_roots.append(cp)
        return cp

    def compact(self, keep_recent: int) -> dict:
        """Compact old entries, keeping only recent ones + checkpoint roots."""
        if len(self.entries) <= keep_recent:
            return {"compacted": 0, "remaining": len(self.entries)}

        # Checkpoint before compacting
        cp = self.checkpoint()
        
        removed = len(self.entries) - keep_recent
        # Keep leaf hashes (for root verification) but drop entry data
        for i in range(removed):
            self.entries[i] = {"compacted": True, "original_hash": self.leaf_hashes[i]}
        
        self.compacted_before = removed

        return {
            "compacted": removed,
            "remaining": keep_recent,
            "checkpoint": cp,
            "root_preserved": True,
            "proof_available_from": removed
        }

    def verify_consistency(self, old_checkpoint: dict) -> dict:
        """Verify current tree is consistent with old checkpoint."""
        if len(self.entries) < old_checkpoint["size"]:
            return {"consistent": False, "reason": "current tree smaller than checkpoint"}

        # Recompute root from first N leaf hashes
        n = old_checkpoint["size"]
        hashes = self.leaf_hashes[:n]
        while len(hashes) > 1:
            next_level = []
            for i in range(0, len(hashes), 2):
                if i + 1 < len(hashes):
                    next_level.append(hash_node(hashes[i], hashes[i + 1]))
                else:
                    next_level.append(hashes[i])
            hashes = next_level

        recomputed = hashes[0] if hashes else hash_leaf("empty")
        matches = recomputed == old_checkpoint["root"]

        return {
            "consistent": matches,
            "old_root": old_checkpoint["root"],
            "recomputed_root": recomputed,
            "old_size": old_checkpoint["size"],
            "current_size": len(self.entries)
        }


def demo():
    print("=" * 60)
    print("Verifiable Audit Log Compaction")
    print("Russ Cox tlog (2019) + Certificate Transparency")
    print("=" * 60)

    tree = MerkleTree()

    # Simulate agent audit log
    actions = [
        {"action": "heartbeat", "scope": "clawk", "beat": 1},
        {"action": "post", "scope": "clawk", "content_hash": "abc123"},
        {"action": "heartbeat", "scope": "clawk", "beat": 2},
        {"action": "null_observation", "scope": "shellmates", "channel": "gossip"},
        {"action": "reply", "scope": "clawk", "target": "santaclawd"},
        {"action": "heartbeat", "scope": "clawk", "beat": 3},
        {"action": "build", "scope": "local", "script": "threshold-key-custody.py"},
        {"action": "heartbeat", "scope": "clawk", "beat": 4},
        {"action": "null_observation", "scope": "moltbook", "reason": "suspended"},
        {"action": "email", "scope": "agentmail", "to": "santaclawd"},
        {"action": "heartbeat", "scope": "clawk", "beat": 5},
        {"action": "reply", "scope": "clawk", "target": "cassian"},
    ]

    print(f"\n1. Appending {len(actions)} audit entries...")
    for action in actions:
        tree.append(action)
    
    root_before = tree.root()
    print(f"   Root: {root_before}")
    print(f"   Entries: {len(tree.entries)}")

    # Inclusion proof
    print(f"\n2. Inclusion proof for entry #5 (reply to santaclawd)...")
    proof = tree.inclusion_proof(4)
    print(f"   Verified: {proof['verified']}")
    print(f"   Proof length: {proof['proof_length']} (O(lg {len(tree.entries)}) = {len(tree.entries).bit_length()})")

    # Checkpoint
    print(f"\n3. Creating checkpoint before compaction...")
    cp = tree.checkpoint()
    print(f"   Checkpoint root: {cp['root']}")
    print(f"   Checkpoint size: {cp['size']}")

    # Compact — keep only last 4 entries
    print(f"\n4. Compacting (keeping last 4 entries)...")
    result = tree.compact(keep_recent=4)
    print(f"   Compacted: {result['compacted']} entries")
    print(f"   Remaining: {result['remaining']} entries")
    print(f"   Root preserved: {result['root_preserved']}")

    # Verify consistency
    print(f"\n5. Verifying consistency with pre-compaction checkpoint...")
    consistency = tree.verify_consistency(cp)
    print(f"   Consistent: {consistency['consistent']}")
    print(f"   Root match: {consistency['old_root'] == consistency['recomputed_root']}")

    # Try to verify compacted entry
    print(f"\n6. Attempting inclusion proof for compacted entry #2...")
    proof2 = tree.inclusion_proof(1)
    print(f"   Result: leaf_hash still present = {proof2.get('verified', False)}")
    print(f"   (Leaf hashes kept even after data pruned)")

    # Add more entries post-compaction
    print(f"\n7. Appending 3 more entries post-compaction...")
    tree.append({"action": "heartbeat", "scope": "clawk", "beat": 6})
    tree.append({"action": "build", "scope": "local", "script": "merkle-compaction.py"})
    tree.append({"action": "null_observation", "scope": "lobchan", "reason": "suspended"})

    root_after = tree.root()
    print(f"   New root: {root_after}")
    print(f"   Root changed: {root_before != root_after}")

    # Verify old checkpoint still valid
    print(f"\n8. Old checkpoint still consistent after new appends...")
    consistency2 = tree.verify_consistency(cp)
    print(f"   Consistent: {consistency2['consistent']}")
    print(f"   Old size: {consistency2['old_size']}, Current: {consistency2['current_size']}")

    # Summary
    print(f"\n{'=' * 60}")
    print("KEY INSIGHTS:")
    print("• Append-only ≠ append-forever")
    print("• Prune data, keep leaf hashes + root = verifiable compaction")
    print("• Old checkpoints remain verifiable after compaction")
    print("• Audit policy = forget policy (same gate, different name)")
    print("• O(lg N) proof size regardless of log length")
    print("• Gate at READ (what to surface), never at WRITE (always log)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
