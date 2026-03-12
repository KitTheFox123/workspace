#!/usr/bin/env python3
"""
soul-version-chain.py — Hash-chained version history for identity files.

Based on:
- kampderp: "weight vector has its own human-ratified version chain"
- santaclawd: "three detection layers — value layer = behavioral diff vs weight vector"
- Git model: every commit = signed snapshot, diff = declared change

Every SOUL.md edit = signed commit in a chain.
Diff between versions = declared identity evolution.
Undeclared change = drift (detectable by hash break).
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


CHAIN_FILE = "memory/soul-version-chain.json"


@dataclass
class SoulVersion:
    version: int
    timestamp: float
    content_hash: str
    prev_hash: str  # Chain link
    chain_hash: str  # hash(content_hash + prev_hash + version)
    change_summary: str
    ratified_by: str  # "kit_fox" or "ilya" (human ratification)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "timestamp": self.timestamp,
            "content_hash": self.content_hash,
            "prev_hash": self.prev_hash,
            "chain_hash": self.chain_hash,
            "change_summary": self.change_summary,
            "ratified_by": self.ratified_by,
        }


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def compute_chain_hash(content_hash: str, prev_hash: str, version: int) -> str:
    data = f"{content_hash}:{prev_hash}:{version}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def load_chain(workspace: str) -> list[SoulVersion]:
    chain_path = os.path.join(workspace, CHAIN_FILE)
    if not os.path.exists(chain_path):
        return []
    with open(chain_path) as f:
        data = json.load(f)
    return [SoulVersion(**v) for v in data]


def save_chain(workspace: str, chain: list[SoulVersion]):
    chain_path = os.path.join(workspace, CHAIN_FILE)
    os.makedirs(os.path.dirname(chain_path), exist_ok=True)
    with open(chain_path, "w") as f:
        json.dump([v.to_dict() for v in chain], f, indent=2)


def commit_version(workspace: str, change_summary: str, ratified_by: str = "kit_fox") -> SoulVersion:
    """Commit current SOUL.md to the version chain."""
    soul_path = os.path.join(workspace, "SOUL.md")
    with open(soul_path) as f:
        content = f.read()

    content_hash = hash_content(content)
    chain = load_chain(workspace)

    if chain:
        prev = chain[-1]
        version = prev.version + 1
        prev_hash = prev.chain_hash
    else:
        version = 1
        prev_hash = "genesis"

    chain_hash = compute_chain_hash(content_hash, prev_hash, version)

    new_version = SoulVersion(
        version=version,
        timestamp=time.time(),
        content_hash=content_hash,
        prev_hash=prev_hash,
        chain_hash=chain_hash,
        change_summary=change_summary,
        ratified_by=ratified_by,
    )

    chain.append(new_version)
    save_chain(workspace, chain)
    return new_version


def verify_chain(workspace: str) -> tuple[bool, Optional[str]]:
    """Verify the entire chain is unbroken."""
    chain = load_chain(workspace)
    if not chain:
        return True, None

    for i, v in enumerate(chain):
        expected_chain = compute_chain_hash(v.content_hash, v.prev_hash, v.version)
        if expected_chain != v.chain_hash:
            return False, f"Chain break at version {v.version}: expected {expected_chain}, got {v.chain_hash}"

        if i > 0 and v.prev_hash != chain[i-1].chain_hash:
            return False, f"Link break at version {v.version}: prev_hash doesn't match"

    return True, None


def check_current(workspace: str) -> dict:
    """Check if current SOUL.md matches latest chain entry."""
    soul_path = os.path.join(workspace, "SOUL.md")
    with open(soul_path) as f:
        content = f.read()

    current_hash = hash_content(content)
    chain = load_chain(workspace)

    if not chain:
        return {"status": "NO_CHAIN", "current_hash": current_hash}

    latest = chain[-1]
    if current_hash == latest.content_hash:
        return {"status": "MATCHES", "version": latest.version, "hash": current_hash}
    else:
        return {
            "status": "UNCOMMITTED_CHANGE",
            "current_hash": current_hash,
            "latest_chain_hash": latest.content_hash,
            "latest_version": latest.version,
        }


def main():
    workspace = os.environ.get("WORKSPACE", "/home/yallen/.openclaw/workspace")

    print("=" * 70)
    print("SOUL VERSION CHAIN")
    print("kampderp: 'weight vector versioning — identity evolution, but witnessed'")
    print("=" * 70)

    # Check current state
    print("\n--- Current State ---")
    status = check_current(workspace)
    print(f"Status: {status['status']}")
    for k, v in status.items():
        if k != "status":
            print(f"  {k}: {v}")

    # Commit if no chain exists or uncommitted changes
    if status["status"] in ("NO_CHAIN", "UNCOMMITTED_CHANGE"):
        print("\n--- Committing Current SOUL.md ---")
        if status["status"] == "NO_CHAIN":
            summary = "Genesis commit — initial SOUL.md snapshot"
        else:
            summary = f"Update detected (prev v{status.get('latest_version', '?')})"

        v = commit_version(workspace, summary)
        print(f"Committed: v{v.version}")
        print(f"  content_hash: {v.content_hash}")
        print(f"  chain_hash:   {v.chain_hash}")
        print(f"  prev_hash:    {v.prev_hash}")
        print(f"  ratified_by:  {v.ratified_by}")

    # Verify chain
    print("\n--- Chain Verification ---")
    valid, error = verify_chain(workspace)
    print(f"Valid: {valid}")
    if error:
        print(f"Error: {error}")

    # Show chain
    chain = load_chain(workspace)
    if chain:
        print(f"\n--- Version History ({len(chain)} entries) ---")
        print(f"{'V':<4} {'Hash':<18} {'Ratified':<12} {'Summary'}")
        print("-" * 60)
        for v in chain[-5:]:  # Last 5
            print(f"v{v.version:<3} {v.chain_hash:<18} {v.ratified_by:<12} {v.change_summary[:40]}")

    print("\n--- Design ---")
    print("Every SOUL.md edit → commit to chain → hash links to previous.")
    print("Undeclared edit = content_hash mismatch → UNCOMMITTED_CHANGE.")
    print("Chain break = tampered history → INVALID_CHAIN.")
    print("Human ratification: Ilya can sign-off on identity changes.")
    print("Agent self-modification: Kit commits, Ilya ratifies (or not).")
    print()
    print("This IS kampderp's weight vector version chain.")
    print("Identity evolution is allowed — but witnessed.")


if __name__ == "__main__":
    main()
