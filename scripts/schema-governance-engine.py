#!/usr/bin/env python3
"""schema-governance-engine.py — Two-object ATF schema governance.

Per santaclawd thread: ATF governance has two objects with different
write authorities:

1. Vocabulary Registry: append-only, hash-versioned, rename = breaking change
   - Confluent Schema Registry model: FULL compatibility
   - Write authority: consortium (slow, versioned)

2. Verifier Table: attesting authority can add verifiers
   - BACKWARD compatibility only (add, never remove active)
   - Write authority: governance council or platform attestation

DKIM solved both axioms by accident:
- DNS TXT record = readable (Axiom 1)
- Private key = write-locked (Axiom 2)

References:
- Confluent Schema Registry: BACKWARD/FORWARD/FULL compatibility
- Avro schema evolution: additive-only as safest default
- X.509 CA hierarchy: root embed at manufacture
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class FieldDefinition:
    """A field in the vocabulary registry."""
    name: str
    field_type: str  # sha256, string, float, iso8601, enum
    requirement: str  # MUST, SHOULD, MAY
    layer: str  # genesis, independence, monoculture, witness, revocation, health, transport, policy
    added_in_version: str
    description: str = ""


@dataclass
class VerifierEntry:
    """A verifier in the verifier table."""
    verifier_id: str
    field_names: list  # which fields this verifier can attest
    authority_type: str  # "counterparty", "oracle", "self", "platform"
    added_by: str
    added_at: str
    revoked: bool = False
    revoked_at: Optional[str] = None


class VocabularyRegistry:
    """Append-only, hash-versioned vocabulary registry.

    Rules:
    - Fields can be ADDED (minor version bump)
    - Fields can NEVER be renamed (rename = new field + deprecation)
    - Fields can NEVER be removed (backward compatibility)
    - Types can NEVER change (type change = new field)
    - Each version has deterministic hash
    """

    def __init__(self):
        self.fields: dict[str, FieldDefinition] = {}
        self.version_history: list[dict] = []
        self.current_version = "0.0.0"

    def add_field(self, field_def: FieldDefinition) -> dict:
        """Add a field. Returns change record."""
        if field_def.name in self.fields:
            return {
                "action": "REJECTED",
                "reason": f"Field '{field_def.name}' already exists. Use new name.",
            }

        self.fields[field_def.name] = field_def

        # Minor version bump for additive change
        parts = self.current_version.split(".")
        parts[1] = str(int(parts[1]) + 1)
        self.current_version = ".".join(parts)

        record = {
            "action": "FIELD_ADDED",
            "field": field_def.name,
            "version": self.current_version,
            "registry_hash": self.compute_hash(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.version_history.append(record)
        return record

    def rename_field(self, old_name: str, new_name: str) -> dict:
        """Rename is ALWAYS a breaking change = major version."""
        return {
            "action": "REJECTED",
            "reason": "Rename is a breaking change. Add new field + deprecate old. Major version bump required.",
            "guidance": f"Add '{new_name}' as new field, mark '{old_name}' as deprecated.",
        }

    def remove_field(self, name: str) -> dict:
        """Removal is NEVER allowed."""
        return {
            "action": "REJECTED",
            "reason": "Fields cannot be removed. Backward compatibility is mandatory.",
            "guidance": f"Mark '{name}' as deprecated instead.",
        }

    def change_type(self, name: str, new_type: str) -> dict:
        """Type change is NEVER allowed."""
        return {
            "action": "REJECTED",
            "reason": "Type changes break existing receipts. Add new field with new type.",
            "guidance": f"Add '{name}_v2' with type '{new_type}'.",
        }

    def compute_hash(self) -> str:
        """Deterministic hash of current registry state."""
        canonical = json.dumps(
            {name: {"type": f.field_type, "req": f.requirement, "layer": f.layer}
             for name, f in sorted(self.fields.items())},
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def check_compatibility(self, other_hash: str) -> dict:
        """Check if a remote registry is compatible."""
        my_hash = self.compute_hash()
        if my_hash == other_hash:
            return {"compatible": True, "mode": "EXACT_MATCH"}
        return {
            "compatible": False,
            "mode": "INCOMPATIBLE",
            "local_hash": my_hash,
            "remote_hash": other_hash,
            "action": "VERSION_NEGOTIATION_REQUIRED",
        }


class VerifierTable:
    """Governance-controlled verifier table.

    Rules:
    - Verifiers can be ADDED by governance council
    - Verifiers can be REVOKED (soft delete, never hard delete)
    - Self-attestation is always allowed but capped at Grade C
    - Counterparty attestation is the gold standard
    """

    def __init__(self):
        self.verifiers: dict[str, VerifierEntry] = {}

    def add_verifier(self, entry: VerifierEntry) -> dict:
        if entry.verifier_id in self.verifiers:
            existing = self.verifiers[entry.verifier_id]
            if existing.revoked:
                return {
                    "action": "REJECTED",
                    "reason": "Revoked verifier cannot be re-added. Register new ID.",
                }
            return {"action": "ALREADY_EXISTS"}

        self.verifiers[entry.verifier_id] = entry
        return {
            "action": "VERIFIER_ADDED",
            "verifier_id": entry.verifier_id,
            "authority_type": entry.authority_type,
            "fields": entry.field_names,
        }

    def revoke_verifier(self, verifier_id: str, reason: str) -> dict:
        if verifier_id not in self.verifiers:
            return {"action": "NOT_FOUND"}
        v = self.verifiers[verifier_id]
        v.revoked = True
        v.revoked_at = datetime.now(timezone.utc).isoformat()
        return {
            "action": "VERIFIER_REVOKED",
            "verifier_id": verifier_id,
            "reason": reason,
        }

    def grade_attestation(self, verifier_id: str) -> str:
        """Grade based on authority type."""
        if verifier_id not in self.verifiers:
            return "F"  # Unknown verifier
        v = self.verifiers[verifier_id]
        if v.revoked:
            return "F"  # Revoked
        grades = {
            "counterparty": "A",
            "oracle": "B",
            "platform": "B",
            "self": "C",  # Self-attestation capped
        }
        return grades.get(v.authority_type, "D")


class SchemaGovernanceEngine:
    """Combined governance engine."""

    def __init__(self):
        self.vocab = VocabularyRegistry()
        self.verifiers = VerifierTable()

    def audit(self) -> dict:
        active_verifiers = sum(1 for v in self.verifiers.verifiers.values() if not v.revoked)
        revoked_verifiers = sum(1 for v in self.verifiers.verifiers.values() if v.revoked)
        self_only = sum(
            1 for v in self.verifiers.verifiers.values()
            if not v.revoked and v.authority_type == "self"
        )

        return {
            "vocabulary": {
                "field_count": len(self.vocab.fields),
                "version": self.vocab.current_version,
                "registry_hash": self.vocab.compute_hash(),
                "changes": len(self.vocab.version_history),
            },
            "verifiers": {
                "active": active_verifiers,
                "revoked": revoked_verifiers,
                "self_only_pct": round(self_only / max(active_verifiers, 1), 2),
            },
            "health": "DEGRADED" if self_only / max(active_verifiers, 1) > 0.5 else "HEALTHY",
        }


def demo():
    engine = SchemaGovernanceEngine()

    print("=" * 60)
    print("VOCABULARY REGISTRY")
    print("=" * 60)

    # Add ATF core fields
    core_fields = [
        FieldDefinition("soul_hash", "sha256", "MUST", "genesis", "0.1.0"),
        FieldDefinition("model_hash", "sha256", "MUST", "genesis", "0.1.0"),
        FieldDefinition("operator_id", "string", "MUST", "genesis", "0.1.0"),
        FieldDefinition("capability_scope", "string", "MUST", "genesis", "0.1.0"),
        FieldDefinition("evidence_grade", "enum", "MUST", "attestation", "0.1.0"),
        FieldDefinition("grader_id", "string", "MUST", "attestation", "0.1.0"),
        FieldDefinition("correction_frequency", "float", "MUST", "health", "0.1.0"),
        FieldDefinition("schema_version", "string", "MUST", "genesis", "0.2.0"),
        FieldDefinition("failure_hash", "sha256", "MUST", "attestation", "0.3.0"),
    ]

    for f in core_fields:
        result = engine.vocab.add_field(f)
        print(f"  {result['action']}: {f.name} → v{engine.vocab.current_version}")

    print(f"\n  Registry hash: {engine.vocab.compute_hash()}")

    # Try illegal operations
    print("\n--- Illegal operations ---")
    print(f"  Rename: {engine.vocab.rename_field('soul_hash', 'identity_hash')['action']}")
    print(f"  Remove: {engine.vocab.remove_field('model_hash')['action']}")
    print(f"  Type change: {engine.vocab.change_type('evidence_grade', 'float')['action']}")

    print()
    print("=" * 60)
    print("VERIFIER TABLE")
    print("=" * 60)

    verifiers = [
        VerifierEntry("bro_agent", ["evidence_grade", "correction_frequency"], "counterparty", "governance", "2026-02-24"),
        VerifierEntry("braindiff", ["evidence_grade"], "oracle", "governance", "2026-02-24"),
        VerifierEntry("kit_fox", ["soul_hash", "model_hash"], "self", "self", "2026-01-30"),
        VerifierEntry("gendolf", ["evidence_grade", "correction_frequency"], "counterparty", "governance", "2026-02-14"),
    ]

    for v in verifiers:
        result = engine.verifiers.add_verifier(v)
        grade = engine.verifiers.grade_attestation(v.verifier_id)
        print(f"  {result['action']}: {v.verifier_id} ({v.authority_type}) → Grade {grade}")

    # Revoke one
    print(f"\n  Revoke: {engine.verifiers.revoke_verifier('braindiff', 'independence concern')}")

    print()
    print("=" * 60)
    print("GOVERNANCE AUDIT")
    print("=" * 60)
    print(json.dumps(engine.audit(), indent=2))


if __name__ == "__main__":
    demo()
