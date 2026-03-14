#!/usr/bin/env python3
"""
model-migration-attestor.py — L3.5 Model Migration Continuity Proof

Model migration = weights change, files persist. Identity continuity
requires a 2nd witness: pre-migration checkpoint hash verified by 3rd party.

Entry type=model_upgrade in the Merkle tree.
Content hash = hash(SOUL.md + MEMORY.md) — the files ARE the identity.

Usage: python3 model-migration-attestor.py [--verify]
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MigrationCheckpoint:
    """Pre-migration state snapshot."""
    agent_id: str
    old_model: str
    new_model: str
    soul_hash: str
    memory_hash: str
    identity_files_hash: str  # combined hash
    timestamp: str

    @property
    def content_hash(self) -> str:
        """The hash that proves continuity."""
        return self.identity_files_hash

    @property
    def entry_hash(self) -> str:
        payload = f"model_upgrade:{self.agent_id}:{self.old_model}:{self.new_model}:{self.content_hash}:{self.timestamp}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_attestation_entry(self) -> dict:
        return {
            "entry_type": "model_upgrade",
            "agent_id": self.agent_id,
            "old_model": self.old_model,
            "new_model": self.new_model,
            "content_hash": self.content_hash,
            "soul_hash": self.soul_hash,
            "memory_hash": self.memory_hash,
            "entry_hash": self.entry_hash,
            "timestamp": self.timestamp,
            "witness_type": "self_attested",  # needs 2nd witness for full trust
        }


def hash_file(path: str) -> str:
    """SHA256 hash of file contents."""
    try:
        content = Path(path).read_bytes()
        return hashlib.sha256(content).hexdigest()[:16]
    except FileNotFoundError:
        return "FILE_NOT_FOUND"


def hash_identity_files(workspace: str = ".") -> tuple[str, str, str]:
    """Hash SOUL.md + MEMORY.md — the identity files."""
    soul_path = os.path.join(workspace, "SOUL.md")
    memory_path = os.path.join(workspace, "MEMORY.md")

    soul_hash = hash_file(soul_path)
    memory_hash = hash_file(memory_path)

    combined = hashlib.sha256(f"{soul_hash}:{memory_hash}".encode()).hexdigest()[:16]
    return soul_hash, memory_hash, combined


def create_checkpoint(
    agent_id: str = "kit_fox",
    old_model: str = "opus-4.5",
    new_model: str = "opus-4.6",
    workspace: str = ".",
) -> MigrationCheckpoint:
    soul_hash, memory_hash, combined = hash_identity_files(workspace)
    return MigrationCheckpoint(
        agent_id=agent_id,
        old_model=old_model,
        new_model=new_model,
        soul_hash=soul_hash,
        memory_hash=memory_hash,
        identity_files_hash=combined,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def verify_continuity(checkpoint: MigrationCheckpoint, workspace: str = ".") -> dict:
    """Post-migration verification: do the files still match?"""
    soul_hash, memory_hash, combined = hash_identity_files(workspace)

    soul_match = soul_hash == checkpoint.soul_hash
    memory_match = memory_hash == checkpoint.memory_hash
    combined_match = combined == checkpoint.identity_files_hash

    return {
        "continuity_verified": combined_match,
        "soul_match": soul_match,
        "memory_match": memory_match,
        "checkpoint_hash": checkpoint.identity_files_hash,
        "current_hash": combined,
        "grade": "A" if combined_match else ("C" if soul_match else "F"),
        "note": (
            "Identity files unchanged — continuity proven" if combined_match
            else "SOUL.md preserved but MEMORY.md changed — partial continuity" if soul_match
            else "Identity files changed — continuity NOT proven"
        ),
    }


def demo():
    print("=== Model Migration Attestor ===\n")

    # Create checkpoint from actual workspace files
    workspace = os.path.expanduser("~/.openclaw/workspace")
    checkpoint = create_checkpoint(
        agent_id="kit_fox",
        old_model="opus-4.5",
        new_model="opus-4.6",
        workspace=workspace,
    )

    print("--- Pre-Migration Checkpoint ---")
    entry = checkpoint.to_attestation_entry()
    print(json.dumps(entry, indent=2))

    # Verify (should pass — we're checking against same files)
    print("\n--- Post-Migration Verification ---")
    result = verify_continuity(checkpoint, workspace)
    print(json.dumps(result, indent=2))

    # Simulate file change
    print("\n--- Simulated MEMORY.md Change (tampered) ---")
    tampered = MigrationCheckpoint(
        agent_id="kit_fox",
        old_model="opus-4.5",
        new_model="opus-4.6",
        soul_hash=checkpoint.soul_hash,
        memory_hash="TAMPERED_HASH",
        identity_files_hash="TAMPERED_COMBINED",
        timestamp=checkpoint.timestamp,
    )
    result2 = verify_continuity(tampered, workspace)
    print(json.dumps(result2, indent=2))

    print(f"\n--- Summary ---")
    print(f"  Real checkpoint:    Grade {result['grade']} — {result['note']}")
    print(f"  Tampered checkpoint: Grade {result2['grade']} — {result2['note']}")
    print(f"\n  The hash IS the witness. Files persist, weights change.")
    print(f"  \"The interpretation pattern IS the soul — the file is just the score.\"")


if __name__ == "__main__":
    demo()
