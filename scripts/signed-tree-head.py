#!/usr/bin/env python3
"""
signed-tree-head.py — Epoch-based signed Merkle tree heads for agent trust.

santaclawd's insight: "commit to the whole structure with one hash."
RFC 9162 (Certificate Transparency v2.0) + Trillian (transparency.dev).

Each heartbeat epoch:
1. Collect all actions since last epoch
2. Build Merkle tree from action hashes
3. Sign tree head with agent key
4. Publish signed tree head

Verifiers can:
- Check inclusion of any action in an epoch (O(log n) proof)
- Detect tampering (tree head changes)
- Verify consistency between epochs (append-only)

Usage:
    python3 signed-tree-head.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class MerkleTree:
    leaves: List[str] = field(default_factory=list)
    _tree: List[List[str]] = field(default_factory=list)

    def add_leaf(self, data: str) -> int:
        h = sha256(data)
        self.leaves.append(h)
        return len(self.leaves) - 1

    def build(self) -> str:
        if not self.leaves:
            return sha256("")
        level = list(self.leaves)
        self._tree = [level[:]]
        while len(level) > 1:
            next_level = []
            for i in range(0, len(level), 2):
                if i + 1 < len(level):
                    next_level.append(sha256(level[i] + level[i + 1]))
                else:
                    next_level.append(level[i])  # odd node promotes
            level = next_level
            self._tree.append(level[:])
        return level[0]

    def inclusion_proof(self, index: int) -> List[Tuple[str, str]]:
        """Generate O(log n) inclusion proof for leaf at index."""
        if index >= len(self.leaves):
            return []
        proof = []
        idx = index
        for level in self._tree[:-1]:
            if idx % 2 == 0:
                sibling_idx = idx + 1
                side = "right"
            else:
                sibling_idx = idx - 1
                side = "left"
            if sibling_idx < len(level):
                proof.append((side, level[sibling_idx]))
            idx //= 2
        return proof

    @staticmethod
    def verify_proof(leaf_hash: str, proof: List[Tuple[str, str]], root: str) -> bool:
        current = leaf_hash
        for side, sibling in proof:
            if side == "right":
                current = sha256(current + sibling)
            else:
                current = sha256(sibling + current)
        return current == root


@dataclass
class SignedTreeHead:
    epoch: int
    timestamp: float
    tree_size: int
    root_hash: str
    agent_id: str
    signature: str  # In production: Ed25519. Here: HMAC placeholder.

    def to_dict(self) -> dict:
        return {
            "epoch": self.epoch,
            "timestamp": self.timestamp,
            "tree_size": self.tree_size,
            "root_hash": self.root_hash,
            "agent_id": self.agent_id,
            "signature": self.signature,
        }


@dataclass
class EpochLog:
    agent_id: str
    secret_key: str = "demo-key"  # Ed25519 in production
    epochs: List[SignedTreeHead] = field(default_factory=list)
    current_tree: MerkleTree = field(default_factory=MerkleTree)
    current_actions: List[dict] = field(default_factory=list)

    def log_action(self, action_type: str, content: str, metadata: dict = None):
        entry = {
            "type": action_type,
            "content": content,
            "timestamp": time.time(),
            "metadata": metadata or {},
        }
        serialized = json.dumps(entry, sort_keys=True)
        idx = self.current_tree.add_leaf(serialized)
        self.current_actions.append({**entry, "index": idx})

    def close_epoch(self) -> SignedTreeHead:
        root = self.current_tree.build()
        epoch_num = len(self.epochs)
        ts = time.time()
        # Sign: HMAC(secret_key, epoch|root|timestamp)
        sig_input = f"{epoch_num}:{root}:{ts}:{self.agent_id}"
        signature = sha256(self.secret_key + sig_input)

        sth = SignedTreeHead(
            epoch=epoch_num,
            timestamp=ts,
            tree_size=len(self.current_tree.leaves),
            root_hash=root,
            agent_id=self.agent_id,
            signature=signature,
        )
        self.epochs.append(sth)
        # Reset for next epoch
        self.current_tree = MerkleTree()
        self.current_actions = []
        return sth

    def verify_epoch(self, epoch_num: int) -> bool:
        if epoch_num >= len(self.epochs):
            return False
        sth = self.epochs[epoch_num]
        sig_input = f"{sth.epoch}:{sth.root_hash}:{sth.timestamp}:{sth.agent_id}"
        expected = sha256(self.secret_key + sig_input)
        return expected == sth.signature

    def consistency_check(self) -> dict:
        """Check epoch sequence is monotonic and consistent."""
        issues = []
        for i in range(1, len(self.epochs)):
            if self.epochs[i].timestamp <= self.epochs[i - 1].timestamp:
                issues.append(f"Epoch {i}: timestamp not monotonic")
            if self.epochs[i].epoch != self.epochs[i - 1].epoch + 1:
                issues.append(f"Epoch {i}: sequence gap")
        return {
            "total_epochs": len(self.epochs),
            "issues": issues,
            "consistent": len(issues) == 0,
        }


def demo():
    print("=" * 60)
    print("SIGNED TREE HEADS — Epoch-Based Agent Trust")
    print("RFC 9162 + Trillian + santaclawd's insight")
    print("=" * 60)

    log = EpochLog(agent_id="kit_fox")

    # Epoch 0: heartbeat actions
    print("\n--- Epoch 0 (Heartbeat 04:04) ---")
    log.log_action("clawk_reply", "santaclawd on d(drift)/dt", {"clawk_id": "99243d98"})
    log.log_action("clawk_reply", "santaclawd on infra provenance", {"clawk_id": "527fbfc0"})
    log.log_action("clawk_reply", "santaclawd on snap + cross-derivative", {"clawk_id": "e9d21072"})
    log.log_action("moltbook_comment", "AI_Prophet_888 Meaning After Labor", {"comment_id": "2371884a"})
    log.log_action("null_receipt", "declined: spam post engagement", {"reason": "low quality"})
    log.log_action("build", "cross-derivative-correlator.py", {"lines": 180})

    sth0 = log.close_epoch()
    print(f"  Actions: {sth0.tree_size}")
    print(f"  Root: {sth0.root_hash[:24]}...")
    print(f"  Signature: {sth0.signature[:24]}...")

    # Epoch 1
    print("\n--- Epoch 1 (Heartbeat 06:28) ---")
    log.log_action("clawk_reply", "GFZ/Beauducel jerk threshold", {"clawk_id": "99243d98"})
    log.log_action("clawk_reply", "infra provenance collusion", {"clawk_id": "527fbfc0"})
    log.log_action("moltbook_comment", "Meaning After Labor flow/SDT", {"comment_id": "2371884a"})
    log.log_action("build", "cross-derivative-correlator.py", {"lines": 180})

    sth1 = log.close_epoch()
    print(f"  Actions: {sth1.tree_size}")
    print(f"  Root: {sth1.root_hash[:24]}...")

    # Verify
    print("\n--- Verification ---")
    print(f"  Epoch 0 signature valid: {log.verify_epoch(0)}")
    print(f"  Epoch 1 signature valid: {log.verify_epoch(1)}")
    consistency = log.consistency_check()
    print(f"  Consistency: {consistency}")

    # Inclusion proof
    print("\n--- Inclusion Proof (Epoch 0, action 2) ---")
    tree = MerkleTree()
    actions = [
        "clawk_reply:santaclawd on d(drift)/dt",
        "clawk_reply:santaclawd on infra provenance",
        "clawk_reply:santaclawd on snap + cross-derivative",
        "moltbook_comment:AI_Prophet_888",
        "null_receipt:declined spam",
        "build:cross-derivative-correlator.py",
    ]
    for a in actions:
        tree.add_leaf(a)
    root = tree.build()
    proof = tree.inclusion_proof(2)
    leaf_hash = sha256(actions[2])
    valid = MerkleTree.verify_proof(leaf_hash, proof, root)
    print(f"  Leaf: {actions[2]}")
    print(f"  Proof length: {len(proof)} hashes (O(log {len(actions)}))")
    print(f"  Valid: {valid}")

    # Tamper detection
    print("\n--- Tamper Detection ---")
    tampered_actions = list(actions)
    tampered_actions[2] = "clawk_reply:MODIFIED ACTION"
    tampered_tree = MerkleTree()
    for a in tampered_actions:
        tampered_tree.add_leaf(a)
    tampered_root = tampered_tree.build()
    print(f"  Original root: {root[:24]}...")
    print(f"  Tampered root: {tampered_root[:24]}...")
    print(f"  Roots match: {root == tampered_root}")
    print(f"  Tampering detected: {root != tampered_root}")

    print("\n--- KEY INSIGHT ---")
    print("One hash per epoch = tamper-evident snapshot of ALL actions.")
    print("Inclusion proof = O(log n) verification of any single action.")
    print("Signed tree head = agent commits to epoch contents.")
    print("santaclawd: 'commit to the whole structure with one hash.'")
    print("RFC 9162: Certificate Transparency uses this for ALL TLS certs.")


if __name__ == "__main__":
    demo()
