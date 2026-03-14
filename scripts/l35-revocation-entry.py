#!/usr/bin/env python3
"""
l35-revocation-entry.py — L3.5 Revocation Entry Format

Revocation = append to same Merkle tree as original attestation.
Entry type=revoke, references original entry hash.
One tree, one proof format, two entry types.

Based on CT (RFC 9162) revocation model:
- Revocation gets own SCT (signed certificate timestamp)
- Original entry remains (append-only, no deletion)
- Verifier checks: is there a revocation entry referencing this hash?

Usage: python3 l35-revocation-entry.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AttestationEntry:
    """Original attestation in the Merkle tree."""
    agent_id: str
    action_type: str  # "commitment", "attestation", "identity"
    content_hash: str
    timestamp: str
    entry_type: str = "attest"

    @property
    def entry_hash(self) -> str:
        payload = f"{self.entry_type}:{self.agent_id}:{self.action_type}:{self.content_hash}:{self.timestamp}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class RevocationEntry:
    """Revocation entry — references original by hash.
    Same tree, same proof format, different entry_type.
    prior_state matters: SLASHED from LOCKED ≠ SLASHED from UNLOCKED.
    """
    original_hash: str  # hash of the entry being revoked
    reason: str  # "slashed", "key_compromise", "voluntary", "dispute", "key_rotation"
    revoker_id: str  # who issued the revocation
    timestamp: str
    prior_state: str = "unknown"  # state before revocation (locked, unlocked, etc)
    evidence_hash: Optional[str] = None  # optional proof of cause
    entry_type: str = "revoke"

    @property
    def entry_hash(self) -> str:
        payload = f"{self.entry_type}:{self.original_hash}:{self.reason}:{self.revoker_id}:{self.timestamp}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def references(self, attestation: AttestationEntry) -> bool:
        """Verify this revocation points to the given attestation."""
        return self.original_hash == attestation.entry_hash


@dataclass
class MerkleLog:
    """Simplified append-only log (no real Merkle tree, just the entry format spec)."""
    entries: list = field(default_factory=list)

    def append_attestation(self, agent_id: str, action_type: str, content_hash: str) -> AttestationEntry:
        entry = AttestationEntry(
            agent_id=agent_id,
            action_type=action_type,
            content_hash=content_hash,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self.entries.append(entry)
        return entry

    def append_migration(self, agent_id: str, old_hash: str, new_hash: str,
                         continuity_proof: str = None) -> AttestationEntry:
        """Model migration: not revocation, identity persists."""
        entry = AttestationEntry(
            agent_id=agent_id,
            action_type="migrate",
            content_hash=f"old={old_hash[:8]}→new={new_hash[:8]}",
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self.entries.append(entry)
        return entry

    def append_revocation(self, original: AttestationEntry, reason: str, revoker_id: str,
                          prior_state: str = "unknown", evidence_hash: str = None) -> RevocationEntry:
        revocation = RevocationEntry(
            original_hash=original.entry_hash,
            reason=reason,
            revoker_id=revoker_id,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            prior_state=prior_state,
            evidence_hash=evidence_hash,
        )
        self.entries.append(revocation)
        return revocation

    def is_revoked(self, entry: AttestationEntry) -> Optional[RevocationEntry]:
        """Check if an attestation has been revoked."""
        for e in self.entries:
            if isinstance(e, RevocationEntry) and e.original_hash == entry.entry_hash:
                return e
        return None

    def to_json(self) -> str:
        entries = []
        for e in self.entries:
            d = {
                "entry_type": e.entry_type,
                "entry_hash": e.entry_hash,
                "timestamp": e.timestamp,
            }
            if isinstance(e, AttestationEntry):
                d.update({"agent_id": e.agent_id, "action_type": e.action_type, "content_hash": e.content_hash})
            elif isinstance(e, RevocationEntry):
                d.update({"original_hash": e.original_hash, "reason": e.reason, "revoker_id": e.revoker_id})
                if e.evidence_hash:
                    d["evidence_hash"] = e.evidence_hash
            entries.append(d)
        return json.dumps({"l35_merkle_log": {"version": "0.1.0", "entries": entries}}, indent=2)


def demo():
    print("=== L3.5 Revocation Entry Format ===\n")
    log = MerkleLog()

    # 1. Agent commits (LOCKED)
    commit = log.append_attestation("agent_alice", "commitment", "sol_lock_abc123")
    print(f"1. ATTEST: {commit.agent_id} committed → hash={commit.entry_hash}")

    # 2. Agent delivers work
    delivery = log.append_attestation("agent_alice", "delivery", "tc4_vocabulary_7f7")
    print(f"2. ATTEST: {commit.agent_id} delivered → hash={delivery.entry_hash}")

    # 3. Agent gets slashed (e.g., dispute resolution)
    slash = log.append_revocation(commit, "slashed", "dispute_oracle", prior_state="locked", evidence_hash="dispute_ruling_xyz")
    print(f"3. REVOKE: {commit.agent_id} slashed → hash={slash.entry_hash} (refs {slash.original_hash})")

    # 4. Check revocation
    rev = log.is_revoked(commit)
    print(f"\n4. Is commitment revoked? {'YES — ' + rev.reason if rev else 'NO'}")

    rev2 = log.is_revoked(delivery)
    print(f"5. Is delivery revoked? {'YES — ' + rev2.reason if rev2 else 'NO'}")
    print(f"   → Key: slashing commitment does NOT revoke delivery receipt!")

    # 5. Voluntary key rotation (not slash)
    key_attest = log.append_attestation("agent_alice", "identity", "ed25519_pubkey_v2")
    old_key = log.append_revocation(
        AttestationEntry("agent_alice", "identity", "ed25519_pubkey_v1",
                        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        "key_rotation", "agent_alice", prior_state="active"
    )
    print(f"\n6. KEY ROTATION: old key revoked → hash={old_key.entry_hash}")
    print(f"   New key attested → hash={key_attest.entry_hash}")

    # 6. Model migration (NOT revocation — identity persists)
    migrate = log.append_migration("agent_alice", "opus-4.5-weights", "opus-4.6-weights",
                                    continuity_proof="soul_md_hash_unchanged")
    print(f"\n7. MODEL MIGRATION: {migrate.content_hash} → hash={migrate.entry_hash}")
    print(f"   → Not revocation! Identity persists. SOUL.md hash unchanged.")

    print(f"\n=== Full Log ({len(log.entries)} entries) ===")
    print(log.to_json())


if __name__ == "__main__":
    demo()
