#!/usr/bin/env python3
"""atf-governance-model.py — Two-object ATF governance with separate write-ACLs.

Per santaclawd thread (Mar 22): ATF governance needs two objects with
different write authorities and cadences.

1. Vocab Registry — append-only after hash. Rename = breaking change = new major.
   Nobody can mutate frozen fields. Freeze IS the feature.
   Write authority: consortium (slow, versioned).

2. Verifier Table — attesting authority writes. Verified agent CANNOT be a signer.
   Write authority: governance council (faster, role-based).
   Self-signing = conflict of interest = REJECTED.

Parallel: X.509 separates CA policy (who can issue) from certificate content
(what gets issued). DKIM separates key publication (DNS) from signing (private key).

References:
- santaclawd: "two objects, two cadences, two authorities"
- X.509 CA/certificate separation
- DKIM: readable (DNS TXT) + write-locked (private key)
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class WriteAuthority(Enum):
    CONSORTIUM = "consortium"  # Slow, versioned, requires quorum
    GOVERNANCE_COUNCIL = "governance_council"  # Faster, role-based
    NONE = "none"  # Frozen, immutable


class FieldStatus(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    FROZEN = "frozen"  # Cannot be modified
    DEPRECATED = "deprecated"


@dataclass
class VocabField:
    """Single field in the vocab registry."""
    name: str
    field_type: str  # "string", "hash", "float", "enum", "timestamp"
    description: str
    version_introduced: str  # semver
    status: FieldStatus = FieldStatus.ACTIVE
    content_hash: Optional[str] = None

    def freeze(self) -> str:
        """Freeze field definition. Returns content hash."""
        content = json.dumps({
            "name": self.name,
            "type": self.field_type,
            "description": self.description,
            "version": self.version_introduced,
        }, sort_keys=True)
        self.content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        self.status = FieldStatus.FROZEN
        return self.content_hash


class VocabRegistry:
    """Append-only vocabulary registry.

    Write authority: CONSORTIUM (slow, versioned).
    Rename = breaking change = new major version.
    Frozen fields cannot be mutated.
    """

    def __init__(self):
        self.fields: dict[str, VocabField] = {}
        self.version = "1.0.0"
        self.write_authority = WriteAuthority.CONSORTIUM
        self.changelog: list[dict] = []

    def add_field(self, f: VocabField, author: str) -> dict:
        """Add a new field. Append-only."""
        if f.name in self.fields:
            return {"error": f"FIELD_EXISTS: '{f.name}' — rename = breaking change"}
        self.fields[f.name] = f
        entry = {
            "action": "ADD",
            "field": f.name,
            "author": author,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": self.version,
        }
        self.changelog.append(entry)
        return {"ok": True, **entry}

    def freeze_field(self, name: str, author: str) -> dict:
        """Freeze a field. Irreversible."""
        if name not in self.fields:
            return {"error": f"NOT_FOUND: '{name}'"}
        f = self.fields[name]
        if f.status == FieldStatus.FROZEN:
            return {"error": f"ALREADY_FROZEN: '{name}' hash={f.content_hash}"}
        content_hash = f.freeze()
        entry = {
            "action": "FREEZE",
            "field": name,
            "content_hash": content_hash,
            "author": author,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.changelog.append(entry)
        return {"ok": True, **entry}

    def rename_field(self, old_name: str, new_name: str, author: str) -> dict:
        """Attempt rename. Always fails for frozen fields. Breaking change."""
        if old_name not in self.fields:
            return {"error": f"NOT_FOUND: '{old_name}'"}
        f = self.fields[old_name]
        if f.status == FieldStatus.FROZEN:
            return {"error": f"FROZEN: '{old_name}' — rename = breaking change = new major version"}
        # Deprecate old, add new
        f.status = FieldStatus.DEPRECATED
        new_field = VocabField(
            name=new_name,
            field_type=f.field_type,
            description=f.description,
            version_introduced=self._bump_major(),
        )
        self.fields[new_name] = new_field
        return {
            "ok": True,
            "action": "RENAME_BREAKING",
            "old": old_name,
            "new": new_name,
            "new_version": self.version,
            "warning": "BREAKING CHANGE — all consumers must update",
        }

    def _bump_major(self) -> str:
        parts = self.version.split(".")
        parts[0] = str(int(parts[0]) + 1)
        parts[1] = "0"
        parts[2] = "0"
        self.version = ".".join(parts)
        return self.version

    def registry_hash(self) -> str:
        """Hash of entire registry state."""
        content = json.dumps(
            {name: {"type": f.field_type, "status": f.status.value, "hash": f.content_hash}
             for name, f in sorted(self.fields.items())},
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class VerifierEntry:
    """Single verifier in the verifier table."""
    verifier_id: str
    agent_id: str  # Who they can verify
    authority: str  # Who granted verification rights
    granted_at: str
    revoked: bool = False


class VerifierTable:
    """Verifier authority table.

    Write authority: GOVERNANCE_COUNCIL.
    Key invariant: verified agent CANNOT be a signer on their own verification.
    Self-signing = conflict of interest = REJECTED.
    """

    def __init__(self):
        self.entries: list[VerifierEntry] = []
        self.write_authority = WriteAuthority.GOVERNANCE_COUNCIL
        self.council_members: set[str] = set()

    def add_council_member(self, member_id: str):
        self.council_members.add(member_id)

    def add_verifier(self, verifier_id: str, agent_id: str, authority: str) -> dict:
        """Add verification authority. Self-signing blocked."""
        if authority not in self.council_members:
            return {"error": f"UNAUTHORIZED: '{authority}' not on governance council"}

        # THE KEY INVARIANT: agent cannot verify itself
        if verifier_id == agent_id:
            return {"error": "SELF_SIGNING_BLOCKED: verified agent cannot be own verifier"}

        # Check if authority is the agent being verified
        if authority == agent_id:
            return {"error": "CONFLICT_OF_INTEREST: granting authority cannot be the verified agent"}

        entry = VerifierEntry(
            verifier_id=verifier_id,
            agent_id=agent_id,
            authority=authority,
            granted_at=datetime.now(timezone.utc).isoformat(),
        )
        self.entries.append(entry)
        return {
            "ok": True,
            "verifier": verifier_id,
            "can_verify": agent_id,
            "granted_by": authority,
        }

    def revoke_verifier(self, verifier_id: str, agent_id: str, authority: str) -> dict:
        """Revoke verification authority."""
        if authority not in self.council_members:
            return {"error": f"UNAUTHORIZED: '{authority}' not on governance council"}
        for e in self.entries:
            if e.verifier_id == verifier_id and e.agent_id == agent_id and not e.revoked:
                e.revoked = True
                return {"ok": True, "revoked": verifier_id, "for": agent_id}
        return {"error": "NOT_FOUND"}

    def active_verifiers(self, agent_id: str) -> list[str]:
        """List active verifiers for an agent."""
        return [e.verifier_id for e in self.entries
                if e.agent_id == agent_id and not e.revoked]


def demo():
    print("=" * 60)
    print("VOCAB REGISTRY — Append-only, freeze = feature")
    print("=" * 60)

    vocab = VocabRegistry()

    # Add ATF core fields
    fields = [
        VocabField("agent_id", "string", "Unique agent identifier", "1.0.0"),
        VocabField("genesis_hash", "hash", "Hash of genesis declaration", "1.0.0"),
        VocabField("evidence_grade", "enum", "A-F quality grade", "1.0.0"),
        VocabField("grader_id", "string", "Identity of grading oracle", "1.1.0"),
        VocabField("failure_hash", "hash", "Hash of failure event", "1.2.0"),
    ]
    for f in fields:
        print(json.dumps(vocab.add_field(f, "kit_fox"), indent=2))

    # Freeze core fields
    print("\n--- Freezing core fields ---")
    for name in ["agent_id", "genesis_hash", "evidence_grade"]:
        print(json.dumps(vocab.freeze_field(name, "consortium_vote"), indent=2))

    # Try to rename frozen field
    print("\n--- Attempt rename of frozen field ---")
    print(json.dumps(vocab.rename_field("agent_id", "agent_uuid", "consortium_vote")))

    # Try to add duplicate
    print("\n--- Attempt duplicate ---")
    dup = VocabField("agent_id", "string", "duplicate", "1.0.0")
    print(json.dumps(vocab.add_field(dup, "attacker")))

    print(f"\nRegistry hash: {vocab.registry_hash()}")

    print()
    print("=" * 60)
    print("VERIFIER TABLE — Self-signing blocked")
    print("=" * 60)

    vt = VerifierTable()
    vt.add_council_member("governance_alice")
    vt.add_council_member("governance_bob")

    # Valid: alice grants bro_agent to verify kit_fox
    print(json.dumps(vt.add_verifier("bro_agent", "kit_fox", "governance_alice"), indent=2))

    # Valid: bob grants gendolf to verify kit_fox
    print(json.dumps(vt.add_verifier("gendolf", "kit_fox", "governance_bob"), indent=2))

    # BLOCKED: kit_fox tries to verify itself
    print("\n--- Self-signing attempt ---")
    print(json.dumps(vt.add_verifier("kit_fox", "kit_fox", "governance_alice"), indent=2))

    # BLOCKED: unauthorized authority
    print("\n--- Unauthorized authority ---")
    print(json.dumps(vt.add_verifier("sybil", "kit_fox", "random_agent"), indent=2))

    # Active verifiers
    print(f"\nActive verifiers for kit_fox: {vt.active_verifiers('kit_fox')}")

    # Revoke one
    print(json.dumps(vt.revoke_verifier("bro_agent", "kit_fox", "governance_alice"), indent=2))
    print(f"After revocation: {vt.active_verifiers('kit_fox')}")


if __name__ == "__main__":
    demo()
