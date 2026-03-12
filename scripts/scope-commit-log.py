#!/usr/bin/env python3
"""scope-commit-log.py — Append-only scope commitment log with Merkle hashing.

Each heartbeat, hash HEARTBEAT.md and append to a tamper-evident log.
Verify consistency: any earlier log must be a prefix of the current one.

Inspired by Certificate Transparency (RFC 9162).
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = Path(__file__).parent.parent / "memory" / "scope-commit-log.jsonl"
HEARTBEAT_FILE = Path(__file__).parent.parent / "HEARTBEAT.md"


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def merkle_root(hashes: list[str]) -> str:
    """Compute Merkle root from list of hex hashes."""
    if not hashes:
        return hash_bytes(b"empty")
    nodes = [bytes.fromhex(h) for h in hashes]
    while len(nodes) > 1:
        if len(nodes) % 2 == 1:
            nodes.append(nodes[-1])  # duplicate last for odd count
        nodes = [
            hashlib.sha256(nodes[i] + nodes[i + 1]).digest()
            for i in range(0, len(nodes), 2)
        ]
    return nodes[0].hex()


def load_log() -> list[dict]:
    if not LOG_FILE.exists():
        return []
    entries = []
    for line in LOG_FILE.read_text().strip().split("\n"):
        if line.strip():
            entries.append(json.loads(line))
    return entries


def append_entry():
    """Hash current HEARTBEAT.md and append to log."""
    if not HEARTBEAT_FILE.exists():
        print("ERROR: HEARTBEAT.md not found")
        sys.exit(1)

    content = HEARTBEAT_FILE.read_bytes()
    scope_hash = hash_bytes(content)

    entries = load_log()
    prev_root = entries[-1]["merkle_root"] if entries else hash_bytes(b"genesis")

    # All scope hashes including this one
    all_hashes = [e["scope_hash"] for e in entries] + [scope_hash]
    new_root = merkle_root(all_hashes)

    entry = {
        "seq": len(entries),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scope_hash": scope_hash,
        "scope_file": "HEARTBEAT.md",
        "scope_size": len(content),
        "prev_root": prev_root,
        "merkle_root": new_root,
    }

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"Appended entry #{entry['seq']}")
    print(f"  scope_hash: {scope_hash[:16]}...")
    print(f"  merkle_root: {new_root[:16]}...")
    return entry


def verify():
    """Verify log consistency — each merkle_root includes all prior entries."""
    entries = load_log()
    if not entries:
        print("Log empty — nothing to verify")
        return True

    all_hashes = []
    prev_root = hash_bytes(b"genesis")
    ok = True

    for e in entries:
        if e["prev_root"] != prev_root:
            print(f"FAIL: entry #{e['seq']} prev_root mismatch")
            ok = False

        all_hashes.append(e["scope_hash"])
        expected_root = merkle_root(all_hashes)
        if e["merkle_root"] != expected_root:
            print(f"FAIL: entry #{e['seq']} merkle_root mismatch")
            ok = False

        prev_root = e["merkle_root"]

    if ok:
        print(f"OK: {len(entries)} entries verified, log is consistent")
    return ok


def show():
    """Show log summary."""
    entries = load_log()
    if not entries:
        print("Log empty")
        return
    print(f"Scope Commit Log — {len(entries)} entries")
    print(f"  First: {entries[0]['timestamp']}")
    print(f"  Last:  {entries[-1]['timestamp']}")
    print(f"  Root:  {entries[-1]['merkle_root'][:32]}...")

    # Check for scope changes
    changes = 0
    for i in range(1, len(entries)):
        if entries[i]["scope_hash"] != entries[i - 1]["scope_hash"]:
            changes += 1
    print(f"  Scope changes: {changes}/{len(entries) - 1}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "append"
    if cmd == "append":
        append_entry()
    elif cmd == "verify":
        verify()
    elif cmd == "show":
        show()
    else:
        print(f"Usage: {sys.argv[0]} [append|verify|show]")
