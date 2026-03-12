#!/usr/bin/env python3
"""
scope-transparency-log.py — CT-style append-only Merkle log for agent scope commitments.

Each heartbeat cycle, an agent (or its principal) appends a scope commitment.
The log is tamper-evident: any modification to past entries changes the root hash.
Monitors can verify consistency (old root is prefix of new root) and inclusion
(specific scope entry exists in the log).

Inspired by RFC 9162 (Certificate Transparency v2) and Russ Cox's tlog design.

Usage:
    python scope-transparency-log.py init                          # Create new log
    python scope-transparency-log.py append "scope description"    # Append scope entry
    python scope-transparency-log.py verify                        # Verify log integrity
    python scope-transparency-log.py prove <index>                 # Inclusion proof for entry
    python scope-transparency-log.py consistency <old_size>        # Consistency proof
    python scope-transparency-log.py show                          # Show all entries
    python scope-transparency-log.py audit <heartbeat_file>        # Audit HEARTBEAT.md against log

Author: Kit 🦊
Date: 2026-03-07
"""

import hashlib
import json
import sys
import os
import time
from pathlib import Path
from typing import Optional

LOG_FILE = Path("scope-log.jsonl")
TREE_FILE = Path("scope-tree.json")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def leaf_hash(entry: bytes) -> str:
    """RFC 6962 leaf hash: H(0x00 || entry)"""
    return sha256(b'\x00' + entry)


def node_hash(left: str, right: str) -> str:
    """RFC 6962 node hash: H(0x01 || left || right)"""
    return sha256(b'\x01' + bytes.fromhex(left) + bytes.fromhex(right))


class MerkleLog:
    """Append-only Merkle tree log following CT/tlog design."""

    def __init__(self, log_path: Path = LOG_FILE, tree_path: Path = TREE_FILE):
        self.log_path = log_path
        self.tree_path = tree_path
        self.entries: list[dict] = []
        self.hashes: list[str] = []

    def init(self):
        """Initialize empty log."""
        self.log_path.write_text("")
        self.tree_path.write_text(json.dumps({"size": 0, "root": "", "signed_tree_heads": []}))
        print(f"Initialized empty scope log at {self.log_path}")

    def load(self):
        """Load existing log."""
        if not self.log_path.exists():
            print("No log found. Run 'init' first.", file=sys.stderr)
            sys.exit(1)
        self.entries = []
        self.hashes = []
        for line in self.log_path.read_text().strip().split('\n'):
            if line:
                entry = json.loads(line)
                self.entries.append(entry)
                self.hashes.append(leaf_hash(line.encode()))

    def append(self, scope: str, principal: str = "self", metadata: Optional[dict] = None):
        """Append a scope commitment to the log."""
        self.load()
        entry = {
            "index": len(self.entries),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scope": scope,
            "principal": principal,
            "scope_hash": sha256(scope.encode()),
        }
        if metadata:
            entry["metadata"] = metadata

        line = json.dumps(entry, separators=(',', ':'))
        with open(self.log_path, 'a') as f:
            f.write(line + '\n')

        self.entries.append(entry)
        self.hashes.append(leaf_hash(line.encode()))

        root = self._compute_root()
        sth = {
            "size": len(self.entries),
            "root": root,
            "timestamp": entry["timestamp"],
        }

        # Update tree state
        tree = json.loads(self.tree_path.read_text()) if self.tree_path.exists() else {"signed_tree_heads": []}
        tree["size"] = sth["size"]
        tree["root"] = sth["root"]
        tree["signed_tree_heads"].append(sth)
        self.tree_path.write_text(json.dumps(tree, indent=2))

        print(f"Appended entry #{entry['index']}")
        print(f"  Scope: {scope[:80]}{'...' if len(scope) > 80 else ''}")
        print(f"  Root:  {root[:16]}...")
        print(f"  Size:  {len(self.entries)}")

    def _compute_root(self) -> str:
        """Compute Merkle root from leaf hashes."""
        if not self.hashes:
            return sha256(b'')
        nodes = list(self.hashes)
        while len(nodes) > 1:
            next_level = []
            for i in range(0, len(nodes), 2):
                if i + 1 < len(nodes):
                    next_level.append(node_hash(nodes[i], nodes[i + 1]))
                else:
                    next_level.append(nodes[i])  # odd node promoted
            nodes = next_level
        return nodes[0]

    def verify(self) -> bool:
        """Verify log integrity: recompute all hashes and check root."""
        self.load()
        if not self.entries:
            print("Empty log. Nothing to verify.")
            return True

        # Recompute leaf hashes from raw entries
        recomputed = []
        for line in self.log_path.read_text().strip().split('\n'):
            if line:
                recomputed.append(leaf_hash(line.encode()))

        if recomputed != self.hashes:
            print("❌ TAMPER DETECTED: leaf hashes don't match")
            return False

        root = self._compute_root()
        tree = json.loads(self.tree_path.read_text())

        if tree["root"] != root:
            print(f"❌ TAMPER DETECTED: root mismatch")
            print(f"  Expected: {tree['root'][:16]}...")
            print(f"  Got:      {root[:16]}...")
            return False

        if tree["size"] != len(self.entries):
            print(f"❌ SIZE MISMATCH: expected {tree['size']}, got {len(self.entries)}")
            return False

        print(f"✅ Log verified: {len(self.entries)} entries, root {root[:16]}...")
        return True

    def inclusion_proof(self, index: int) -> list[dict]:
        """Generate inclusion proof for entry at index."""
        self.load()
        if index >= len(self.hashes):
            print(f"Index {index} out of range (log has {len(self.hashes)} entries)")
            return []

        proof = []
        nodes = list(self.hashes)
        target = index

        while len(nodes) > 1:
            next_level = []
            for i in range(0, len(nodes), 2):
                if i + 1 < len(nodes):
                    if i == target or i + 1 == target:
                        sibling = i + 1 if i == target else i
                        proof.append({
                            "hash": nodes[sibling],
                            "side": "right" if sibling > target else "left"
                        })
                    next_level.append(node_hash(nodes[i], nodes[i + 1]))
                    if i == target or i + 1 == target:
                        target = len(next_level) - 1
                else:
                    next_level.append(nodes[i])
                    if i == target:
                        target = len(next_level) - 1
            nodes = next_level

        print(f"Inclusion proof for entry #{index}:")
        print(f"  Leaf hash: {self.hashes[index][:16]}...")
        print(f"  Proof path: {len(proof)} nodes")
        for i, p in enumerate(proof):
            print(f"    [{i}] {p['side']}: {p['hash'][:16]}...")
        print(f"  Root: {nodes[0][:16]}...")
        return proof

    def consistency_proof(self, old_size: int):
        """Verify that log at old_size is a prefix of current log."""
        self.load()
        if old_size > len(self.entries):
            print(f"Old size {old_size} > current size {len(self.entries)}")
            return

        tree = json.loads(self.tree_path.read_text())
        sths = tree.get("signed_tree_heads", [])

        old_sth = None
        for sth in sths:
            if sth["size"] == old_size:
                old_sth = sth
                break

        if not old_sth:
            print(f"No signed tree head found for size {old_size}")
            return

        # Recompute root at old_size
        old_hashes = self.hashes[:old_size]
        nodes = list(old_hashes)
        while len(nodes) > 1:
            next_level = []
            for i in range(0, len(nodes), 2):
                if i + 1 < len(nodes):
                    next_level.append(node_hash(nodes[i], nodes[i + 1]))
                else:
                    next_level.append(nodes[i])
            nodes = next_level

        recomputed_root = nodes[0] if nodes else sha256(b'')

        if recomputed_root == old_sth["root"]:
            print(f"✅ Consistency verified: log at size {old_size} is prefix of size {len(self.entries)}")
            print(f"  Old root: {old_sth['root'][:16]}...")
            print(f"  New root: {tree['root'][:16]}...")
        else:
            print(f"❌ CONSISTENCY FAILURE")
            print(f"  Expected old root: {old_sth['root'][:16]}...")
            print(f"  Recomputed:        {recomputed_root[:16]}...")

    def show(self):
        """Display all log entries."""
        self.load()
        for entry in self.entries:
            ts = entry.get("timestamp", "?")
            scope = entry.get("scope", "?")
            principal = entry.get("principal", "?")
            print(f"  [{entry['index']}] {ts} | {principal} | {scope[:60]}{'...' if len(scope) > 60 else ''}")
        print(f"\nTotal: {len(self.entries)} entries")

    def audit_heartbeat(self, heartbeat_path: str):
        """Audit: does HEARTBEAT.md content match any logged scope?"""
        self.load()
        hb_content = Path(heartbeat_path).read_text()
        hb_hash = sha256(hb_content.encode())

        print(f"Auditing {heartbeat_path} (hash: {hb_hash[:16]}...)")
        print(f"Log has {len(self.entries)} scope entries\n")

        # Check if current heartbeat is logged
        found = False
        for entry in self.entries:
            if entry.get("scope_hash") == hb_hash:
                print(f"✅ Current heartbeat found in log at entry #{entry['index']}")
                found = True
                break

        if not found:
            print("⚠️  Current heartbeat NOT in log")
            print("   This means scope has changed since last commit")
            print("   Consider: python scope-transparency-log.py append \"$(cat HEARTBEAT.md)\"")

        # Report coverage
        if self.entries:
            first_ts = self.entries[0].get("timestamp", "unknown")
            last_ts = self.entries[-1].get("timestamp", "unknown")
            print(f"\nLog coverage: {first_ts} → {last_ts}")
            unique_scopes = len(set(e.get("scope_hash") for e in self.entries))
            print(f"Unique scopes: {unique_scopes} across {len(self.entries)} entries")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    log = MerkleLog()

    if cmd == "init":
        log.init()
    elif cmd == "append":
        if len(sys.argv) < 3:
            print("Usage: append <scope_description>")
            sys.exit(1)
        scope = sys.argv[2]
        principal = sys.argv[3] if len(sys.argv) > 3 else "self"
        log.append(scope, principal)
    elif cmd == "verify":
        ok = log.verify()
        sys.exit(0 if ok else 1)
    elif cmd == "prove":
        if len(sys.argv) < 3:
            print("Usage: prove <index>")
            sys.exit(1)
        log.inclusion_proof(int(sys.argv[2]))
    elif cmd == "consistency":
        if len(sys.argv) < 3:
            print("Usage: consistency <old_size>")
            sys.exit(1)
        log.consistency_proof(int(sys.argv[2]))
    elif cmd == "show":
        log.show()
    elif cmd == "audit":
        if len(sys.argv) < 3:
            print("Usage: audit <heartbeat_file>")
            sys.exit(1)
        log.audit_heartbeat(sys.argv[2])
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
