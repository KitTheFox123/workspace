#!/usr/bin/env python3
"""
ct-trust-log.py — Certificate Transparency pattern for cross-org agent trust.

The unsolved middle:
- Single-agent WAL = PostgreSQL (1986)
- Multi-agent same-org = vector clocks (1988)
- Multi-agent cross-org = Certificate Transparency (RFC 6962, 2013)

CT gives: append-only log, Merkle proofs, no central authority,
inclusion/consistency proofs, signed tree heads.

For agents: any org can submit trust evidence. Any org can verify.
No single org controls the log. Merkle proofs = O(log n) verification.

Based on: Laurie et al (RFC 6962), Trillian (transparency.dev),
Google CT (2013), signed-tree-head.py (prior build).

Usage:
    python3 ct-trust-log.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class TrustEntry:
    """One trust evidence entry (like a certificate in CT)."""
    agent_id: str
    org_id: str
    evidence_type: str  # attestation, receipt, scope_manifest, null_receipt
    content_hash: str
    timestamp: float
    submitter: str  # who submitted this evidence

    @property
    def leaf_hash(self) -> str:
        data = f"{self.agent_id}:{self.org_id}:{self.evidence_type}:{self.content_hash}:{self.timestamp}"
        return sha256(f"0:{data}")  # 0x00 prefix = leaf


@dataclass
class MerkleTree:
    """Append-only Merkle tree for trust evidence."""
    leaves: List[str] = field(default_factory=list)

    def add(self, leaf_hash: str) -> int:
        """Append leaf, return index."""
        self.leaves.append(leaf_hash)
        return len(self.leaves) - 1

    @property
    def root(self) -> str:
        if not self.leaves:
            return sha256("empty")
        return self._compute_root(self.leaves)

    def _compute_root(self, nodes: List[str]) -> str:
        if len(nodes) == 1:
            return nodes[0]
        next_level = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            right = nodes[i + 1] if i + 1 < len(nodes) else left
            next_level.append(sha256(f"1:{left}:{right}"))  # 0x01 prefix = internal
        return self._compute_root(next_level)

    def inclusion_proof(self, index: int) -> List[Tuple[str, str]]:
        """Generate O(log n) inclusion proof for leaf at index."""
        if index >= len(self.leaves):
            return []
        proof = []
        nodes = list(self.leaves)
        idx = index
        while len(nodes) > 1:
            next_level = []
            for i in range(0, len(nodes), 2):
                left = nodes[i]
                right = nodes[i + 1] if i + 1 < len(nodes) else left
                if i == idx - (idx % 2):
                    sibling_pos = "right" if idx % 2 == 0 else "left"
                    sibling = right if idx % 2 == 0 else left
                    proof.append((sibling_pos, sibling))
                next_level.append(sha256(f"1:{left}:{right}"))
            idx = idx // 2
            nodes = next_level
        return proof

    def verify_inclusion(self, leaf_hash: str, index: int, proof: List[Tuple[str, str]]) -> bool:
        """Verify O(log n) inclusion proof."""
        current = leaf_hash
        for pos, sibling in proof:
            if pos == "right":
                current = sha256(f"1:{current}:{sibling}")
            else:
                current = sha256(f"1:{sibling}:{current}")
        return current == self.root


@dataclass
class SignedTreeHead:
    """Signed commitment to tree state at a point in time."""
    tree_size: int
    root_hash: str
    timestamp: float
    signer: str
    signature: str  # In practice: Ed25519. Here: hash-based.

    @staticmethod
    def sign(tree: MerkleTree, signer: str) -> "SignedTreeHead":
        root = tree.root
        ts = time.time()
        sig_data = f"{len(tree.leaves)}:{root}:{ts}:{signer}"
        sig = sha256(f"sig:{sig_data}")
        return SignedTreeHead(
            tree_size=len(tree.leaves),
            root_hash=root,
            timestamp=ts,
            signer=signer,
            signature=sig,
        )


@dataclass
class TransparencyLog:
    """CT-style transparency log for cross-org agent trust."""
    tree: MerkleTree = field(default_factory=MerkleTree)
    entries: List[TrustEntry] = field(default_factory=list)
    sths: List[SignedTreeHead] = field(default_factory=list)
    log_id: str = "trust-ct-log-001"

    def submit(self, entry: TrustEntry) -> dict:
        """Any org submits evidence. Returns inclusion proof."""
        idx = self.tree.add(entry.leaf_hash)
        self.entries.append(entry)
        return {
            "index": idx,
            "leaf_hash": entry.leaf_hash[:16],
            "tree_size": len(self.tree.leaves),
        }

    def checkpoint(self, signer: str) -> SignedTreeHead:
        """Sign current tree head (like CT's STH)."""
        sth = SignedTreeHead.sign(self.tree, signer)
        self.sths.append(sth)
        return sth

    def prove_inclusion(self, index: int) -> dict:
        """O(log n) proof that entry exists in log."""
        if index >= len(self.entries):
            return {"verified": False, "error": "index out of range"}
        entry = self.entries[index]
        proof = self.tree.inclusion_proof(index)
        verified = self.tree.verify_inclusion(entry.leaf_hash, index, proof)
        return {
            "index": index,
            "agent": entry.agent_id,
            "type": entry.evidence_type,
            "proof_length": len(proof),
            "verified": verified,
        }

    def audit(self) -> dict:
        """Audit log integrity."""
        n = len(self.entries)
        if n == 0:
            return {"entries": 0, "integrity": "EMPTY"}

        # Verify all entries produce correct root
        recomputed = MerkleTree()
        for e in self.entries:
            recomputed.add(e.leaf_hash)

        root_match = recomputed.root == self.tree.root

        # Cross-org diversity
        orgs = set(e.org_id for e in self.entries)
        submitters = set(e.submitter for e in self.entries)
        agents = set(e.agent_id for e in self.entries)

        return {
            "entries": n,
            "root_match": root_match,
            "integrity": "VERIFIED" if root_match else "TAMPERED",
            "unique_orgs": len(orgs),
            "unique_submitters": len(submitters),
            "unique_agents": len(agents),
            "proof_size": f"O(log {n}) = ~{max(1, n.bit_length())} hashes",
            "sth_count": len(self.sths),
        }


def demo():
    print("=" * 60)
    print("CT-STYLE TRANSPARENCY LOG FOR CROSS-ORG AGENT TRUST")
    print("RFC 6962 + Trillian + signed-tree-head.py")
    print("=" * 60)

    log = TransparencyLog()
    now = time.time()

    # Multiple orgs submit evidence about multiple agents
    entries = [
        TrustEntry("kit_fox", "openclaw", "scope_manifest", sha256("scope:trust+research"), now, "kit_fox"),
        TrustEntry("kit_fox", "isnad", "attestation", sha256("attest:gendolf→kit"), now + 1, "gendolf"),
        TrustEntry("bro_agent", "paylock", "receipt", sha256("receipt:tc4:0.91"), now + 2, "bro_agent"),
        TrustEntry("kit_fox", "paylock", "receipt", sha256("receipt:tc4:delivery"), now + 3, "bro_agent"),
        TrustEntry("gendolf", "isnad", "attestation", sha256("attest:kit→gendolf"), now + 4, "kit_fox"),
        TrustEntry("santaclawd", "clawk", "null_receipt", sha256("declined:affiliate"), now + 5, "kit_fox"),
        TrustEntry("kit_fox", "moltbook", "scope_manifest", sha256("scope:research+engage"), now + 6, "kit_fox"),
        TrustEntry("clove", "paylock", "receipt", sha256("receipt:tc4:scored"), now + 7, "bro_agent"),
    ]

    print("\n--- Submitting Evidence ---")
    for e in entries:
        result = log.submit(e)
        print(f"  [{result['index']}] {e.agent_id}@{e.org_id} ({e.evidence_type}) by {e.submitter}")

    # Sign tree head
    print("\n--- Signing Tree Head ---")
    sth = log.checkpoint("ct-log-operator")
    print(f"  Tree size: {sth.tree_size}")
    print(f"  Root: {sth.root_hash[:16]}...")
    print(f"  Signer: {sth.signer}")

    # Prove inclusion
    print("\n--- Inclusion Proofs ---")
    for i in [0, 2, 5, 7]:
        proof = log.prove_inclusion(i)
        print(f"  Entry {proof['index']} ({proof['agent']}, {proof['type']}): "
              f"verified={proof['verified']}, proof_size={proof['proof_length']} hashes")

    # Audit
    print("\n--- Log Audit ---")
    audit = log.audit()
    for k, v in audit.items():
        print(f"  {k}: {v}")

    # The key insight
    print("\n--- KEY INSIGHT ---")
    print("Cross-org trust = CT pattern:")
    print("  1. Any org submits evidence (no gatekeeper)")
    print("  2. Append-only (can't rewrite history)")
    print("  3. Merkle proofs (O(log n) verification)")
    print("  4. Signed tree heads (checkpoints)")
    print("  5. No central authority (multiple log operators)")
    print()
    print("What CT solved for certificates, we need for agent trust.")
    print("The unsolved piece: gossip protocol between log operators.")


if __name__ == "__main__":
    demo()
