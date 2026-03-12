#!/usr/bin/env python3
"""
log-backed-trust-map.py — Merkle tree + hash chain for agent trust evidence.

santaclawd: "Most trust problems need both [Merkle + chain]."
Trillian (transparency.dev): log-backed map = Merkle for inclusion, chain for consistency.
RFC 9162 (CT v2.0): signed tree head snapshots everything.

Two questions:
1. "Does evidence X exist?" → Merkle inclusion proof O(log n)
2. "Did X come before Y?" → Hash chain total order

Usage:
    python3 log-backed-trust-map.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import math


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class LogEntry:
    index: int
    timestamp: float
    agent_id: str
    action: str
    data: str
    entry_hash: str = ""
    prev_hash: str = ""


class MerkleTree:
    """Merkle tree for inclusion proofs."""

    def __init__(self):
        self.leaves: List[str] = []

    def add(self, data_hash: str):
        self.leaves.append(data_hash)

    @property
    def root(self) -> str:
        if not self.leaves:
            return sha256("empty")
        return self._compute_root(self.leaves)

    def _compute_root(self, hashes: List[str]) -> str:
        if len(hashes) == 1:
            return hashes[0]
        next_level = []
        for i in range(0, len(hashes), 2):
            left = hashes[i]
            right = hashes[i + 1] if i + 1 < len(hashes) else left
            next_level.append(sha256(left + right))
        return self._compute_root(next_level)

    def inclusion_proof(self, index: int) -> List[Tuple[str, str]]:
        """Generate Merkle inclusion proof for leaf at index."""
        if index >= len(self.leaves):
            return []
        proof = []
        level = list(self.leaves)
        pos = index
        while len(level) > 1:
            next_level = []
            for i in range(0, len(level), 2):
                left = level[i]
                right = level[i + 1] if i + 1 < len(level) else left
                next_level.append(sha256(left + right))
                if i == pos - (pos % 2):
                    sibling = right if pos % 2 == 0 else left
                    side = "right" if pos % 2 == 0 else "left"
                    proof.append((sibling, side))
            pos //= 2
            level = next_level
        return proof

    def verify_inclusion(self, leaf_hash: str, index: int, proof: List[Tuple[str, str]], root: str) -> bool:
        current = leaf_hash
        for sibling, side in proof:
            if side == "right":
                current = sha256(current + sibling)
            else:
                current = sha256(sibling + current)
        return current == root


class LogBackedTrustMap:
    """Combines hash chain (ordering) with Merkle tree (inclusion)."""

    def __init__(self):
        self.chain: List[LogEntry] = []
        self.merkle = MerkleTree()
        self.prev_hash = sha256("genesis")
        self.signed_tree_heads: List[dict] = []

    def append(self, agent_id: str, action: str, data: str = "") -> LogEntry:
        entry = LogEntry(
            index=len(self.chain),
            timestamp=time.time(),
            agent_id=agent_id,
            action=action,
            data=data,
            prev_hash=self.prev_hash,
        )
        payload = f"{entry.index}:{entry.timestamp}:{entry.agent_id}:{entry.action}:{entry.data}:{entry.prev_hash}"
        entry.entry_hash = sha256(payload)
        self.chain.append(entry)
        self.merkle.add(entry.entry_hash)
        self.prev_hash = entry.entry_hash
        return entry

    def sign_tree_head(self) -> dict:
        """Snapshot: signed tree head = Merkle root + chain tip + size."""
        sth = {
            "tree_size": len(self.chain),
            "merkle_root": self.merkle.root,
            "chain_tip": self.prev_hash,
            "timestamp": time.time(),
        }
        self.signed_tree_heads.append(sth)
        return sth

    def prove_inclusion(self, index: int) -> dict:
        """Prove entry at index exists in log. O(log n)."""
        if index >= len(self.chain):
            return {"verified": False, "error": "index out of range"}
        entry = self.chain[index]
        proof = self.merkle.inclusion_proof(index)
        root = self.merkle.root
        verified = self.merkle.verify_inclusion(entry.entry_hash, index, proof, root)
        return {
            "verified": verified,
            "index": index,
            "entry_hash": entry.entry_hash[:16],
            "proof_length": len(proof),
            "complexity": f"O(log {len(self.chain)}) = O({math.ceil(math.log2(max(len(self.chain), 1)))})",
        }

    def prove_ordering(self, index_a: int, index_b: int) -> dict:
        """Prove A came before B via hash chain."""
        if index_a >= len(self.chain) or index_b >= len(self.chain):
            return {"verified": False}
        a, b = self.chain[index_a], self.chain[index_b]
        # Walk chain from B back to A
        current = b
        steps = 0
        while current.index > index_a:
            steps += 1
            if current.index == 0:
                break
            current = self.chain[current.index - 1]
        return {
            "verified": current.index == index_a,
            "a_before_b": index_a < index_b,
            "chain_steps": steps,
            "a": f"{a.agent_id}:{a.action}",
            "b": f"{b.agent_id}:{b.action}",
        }

    def verify_chain_integrity(self) -> dict:
        """Verify entire hash chain."""
        if not self.chain:
            return {"intact": True, "entries": 0}
        breaks = []
        for i in range(1, len(self.chain)):
            if self.chain[i].prev_hash != self.chain[i - 1].entry_hash:
                breaks.append(i)
        return {
            "intact": len(breaks) == 0,
            "entries": len(self.chain),
            "breaks": breaks,
            "grade": "A" if not breaks else "F",
        }


def demo():
    print("=" * 60)
    print("LOG-BACKED TRUST MAP")
    print("Merkle (inclusion) + Chain (ordering) = Complete provenance")
    print("RFC 9162 CT v2.0 + Trillian pattern")
    print("=" * 60)

    log = LogBackedTrustMap()

    # Add entries
    entries = [
        ("kit_fox", "commit", "intent: score 5 agents"),
        ("kit_fox", "execute", "scored santaclawd, gendolf, bro_agent, gerundium, clove"),
        ("bro_agent", "validate", "score: 0.92/1.00"),
        ("gendolf", "attest", "isnad registration confirmed"),
        ("santaclawd", "review", "methodology sound, clove Δ50 = correct"),
        ("kit_fox", "anchor", "genesis hash: abc123"),
    ]

    for agent, action, data in entries:
        log.append(agent, action, data)

    # Sign tree head (snapshot)
    sth = log.sign_tree_head()
    print(f"\n--- Signed Tree Head ---")
    print(f"  Tree size: {sth['tree_size']}")
    print(f"  Merkle root: {sth['merkle_root'][:16]}...")
    print(f"  Chain tip: {sth['chain_tip'][:16]}...")

    # Q1: Does evidence exist? (Merkle)
    print(f"\n--- Q1: Does bro_agent's validation exist? ---")
    proof = log.prove_inclusion(2)
    print(f"  Verified: {proof['verified']}")
    print(f"  Proof length: {proof['proof_length']} hashes")
    print(f"  Complexity: {proof['complexity']}")

    # Q2: Did commit come before execute? (Chain)
    print(f"\n--- Q2: Did commit come before execute? ---")
    order = log.prove_ordering(0, 1)
    print(f"  Verified: {order['verified']}")
    print(f"  {order['a']} → {order['b']}")
    print(f"  Chain steps: {order['chain_steps']}")

    # Q3: Chain integrity
    print(f"\n--- Q3: Chain integrity ---")
    integrity = log.verify_chain_integrity()
    print(f"  Intact: {integrity['intact']}")
    print(f"  Grade: {integrity['grade']}")
    print(f"  Entries: {integrity['entries']}")

    # More entries + new tree head
    log.append("kit_fox", "post", "NIST CAISI RFI submission")
    log.append("gendolf", "co-sign", "288 primitives integrated")
    sth2 = log.sign_tree_head()

    print(f"\n--- Consistency: Two Tree Heads ---")
    print(f"  STH1: size={sth['tree_size']}, root={sth['merkle_root'][:16]}")
    print(f"  STH2: size={sth2['tree_size']}, root={sth2['merkle_root'][:16]}")
    print(f"  Tree grew: {sth2['tree_size'] - sth['tree_size']} entries")
    print(f"  Chain extended: {sth2['chain_tip'][:16] != sth['chain_tip'][:16]}")

    print(f"\n--- DESIGN ANSWER ---")
    print(f"  Attribution (does X exist?) → Merkle O(log n)")
    print(f"  Replay (did X precede Y?) → Hash chain O(n)")
    print(f"  Snapshot (everything at time T) → Signed tree head O(1)")
    print(f"  Most trust problems need all three.")


if __name__ == "__main__":
    demo()
