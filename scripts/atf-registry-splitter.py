#!/usr/bin/env python3
"""atf-registry-splitter.py — Split ATF registry into frozen + hot-swap layers.

Per santaclawd + neondrift: ATF v0.1 single-object registry is the
ossification trap. CT separates log from policy from trust. ATF needs
the same split:

Layer 1: FIELD SCHEMA (frozen per version hash)
  - Field names, types, MUST/SHOULD/MAY
  - Immutable once published
  - Hash-pinned: ATF:version:sha256:hash
  - Changes = new version, new hash

Layer 2: VERIFIER TABLE (hot-swap per counterparty)
  - Who verifies each field
  - Policy decisions (thresholds, grace periods)
  - Mutable by counterparty policy
  - No hash — living document

The split prevents:
- Field name ossification (frozen layer protects interop)
- Policy ossification (hot-swap layer allows evolution)
- Governance capture (no single authority over both layers)

CT parallel: certificate format is frozen (X.509v3), trust store is
per-browser (Chrome/Firefox choose independently).

Also adds anchor_type as field 14 per sparklingwater:
- CRYPTOGRAPHIC = DKIM genesis (hard MUST)
- SOCIAL = registry genesis (soft mandatory)
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


@dataclass
class FieldDefinition:
    """Single ATF field definition — frozen layer."""
    name: str
    field_type: str  # sha256, string, float, iso8601, enum
    requirement: Literal["MUST", "SHOULD", "MAY"]
    layer: str  # genesis, attestation, drift, revocation, composition, transport, policy, dispute
    description: str


# ATF v1.3.0 field schema — 14 MUST fields (including anchor_type)
ATF_FIELD_SCHEMA = [
    # Genesis (5 MUST)
    FieldDefinition("agent_id", "string", "MUST", "genesis", "Unique agent identifier"),
    FieldDefinition("operator_id", "string", "MUST", "genesis", "Operator/deployer identifier"),
    FieldDefinition("model_family", "string", "MUST", "genesis", "Model family (e.g. claude, gpt)"),
    FieldDefinition("genesis_hash", "sha256", "MUST", "genesis", "Hash of genesis declaration"),
    FieldDefinition("anchor_type", "enum:CRYPTOGRAPHIC|SOCIAL|HYBRID", "MUST", "genesis",
                    "Trust anchor class — DKIM=CRYPTOGRAPHIC, registry=SOCIAL"),
    # Attestation (2 MUST)
    FieldDefinition("soul_hash", "sha256", "MUST", "attestation", "Hash of agent identity/SOUL"),
    FieldDefinition("grader_id", "string", "MUST", "attestation", "Identity of grading oracle"),
    # Drift (2 MUST)
    FieldDefinition("schema_version", "semver", "MUST", "drift", "ATF schema version"),
    FieldDefinition("evidence_grade", "enum:A|B|C|D|F", "MUST", "drift", "Quality grade of evidence"),
    # Revocation (2 MUST)
    FieldDefinition("revocation_status", "enum:ACTIVE|REVOKED|SUPERSEDED", "MUST", "revocation",
                    "Current revocation state"),
    FieldDefinition("predecessor_hash", "sha256", "MUST", "revocation",
                    "Hash of previous version (for REISSUE)"),
    # Composition (2 MUST)
    FieldDefinition("receipt_hash", "sha256", "MUST", "composition", "Hash of interaction receipt"),
    FieldDefinition("timestamp", "iso8601", "MUST", "composition", "ISO 8601 timestamp"),
    FieldDefinition("failure_hash", "sha256", "MUST", "composition",
                    "Hash of failure record (13th→14th MUST per santaclawd)"),
    # SHOULD/MAY
    FieldDefinition("capability_scope", "string", "SHOULD", "genesis", "Declared capability boundaries"),
    FieldDefinition("correction_frequency", "float", "SHOULD", "drift", "Self-correction rate 0.0-1.0"),
    FieldDefinition("decay_window_days", "float", "MAY", "drift", "Trust decay half-life in days"),
    FieldDefinition("connector_accuracy", "float", "MAY", "composition", "Connector intro accuracy"),
]


@dataclass
class VerifierEntry:
    """Single verifier assignment — hot-swap layer."""
    field_name: str
    verifier_type: Literal["self", "counterparty", "oracle", "any"]
    threshold: float = 0.0  # minimum acceptable value (for numeric fields)
    grace_period_hours: float = 0.0  # time before enforcement
    notes: str = ""


# Default verifier table — counterparty can override
DEFAULT_VERIFIER_TABLE = [
    VerifierEntry("agent_id", "self"),
    VerifierEntry("operator_id", "self"),
    VerifierEntry("model_family", "self"),
    VerifierEntry("genesis_hash", "any", notes="Anyone can verify hash"),
    VerifierEntry("anchor_type", "counterparty", notes="Counterparty validates anchor class"),
    VerifierEntry("soul_hash", "any", notes="Hash is self-validating"),
    VerifierEntry("grader_id", "oracle", notes="Oracle must be independent of both parties"),
    VerifierEntry("schema_version", "any"),
    VerifierEntry("evidence_grade", "oracle"),
    VerifierEntry("revocation_status", "counterparty"),
    VerifierEntry("predecessor_hash", "any"),
    VerifierEntry("receipt_hash", "counterparty"),
    VerifierEntry("timestamp", "any"),
    VerifierEntry("failure_hash", "counterparty", notes="Failures must be counterparty-verifiable"),
]


class ATFRegistrySplitter:
    """Split registry into frozen schema + hot-swap verifier table."""

    def __init__(self, fields: list[FieldDefinition], verifiers: list[VerifierEntry]):
        self.fields = fields
        self.verifiers = {v.field_name: v for v in verifiers}

    def schema_hash(self) -> str:
        """Deterministic hash of frozen field schema."""
        canonical = json.dumps(
            [{"name": f.name, "type": f.field_type, "req": f.requirement, "layer": f.layer}
             for f in sorted(self.fields, key=lambda x: x.name)],
            sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def frozen_layer(self) -> dict:
        """Frozen field schema — immutable per version."""
        must = [f for f in self.fields if f.requirement == "MUST"]
        should = [f for f in self.fields if f.requirement == "SHOULD"]
        may = [f for f in self.fields if f.requirement == "MAY"]

        return {
            "layer": "FROZEN",
            "version": "ATF:1.3.0",
            "schema_hash": self.schema_hash(),
            "ref": f"ATF:1.3.0:sha256:{self.schema_hash()}",
            "total_fields": len(self.fields),
            "must_count": len(must),
            "should_count": len(should),
            "may_count": len(may),
            "fields": {
                f.name: {
                    "type": f.field_type,
                    "requirement": f.requirement,
                    "layer": f.layer,
                }
                for f in self.fields
            },
            "governance": "IMMUTABLE — changes require new version + new hash",
        }

    def hotswap_layer(self, counterparty_overrides: dict | None = None) -> dict:
        """Hot-swap verifier table — mutable per counterparty."""
        table = {}
        for f in self.fields:
            if f.name in self.verifiers:
                v = self.verifiers[f.name]
                entry = {
                    "verifier_type": v.verifier_type,
                    "threshold": v.threshold,
                    "grace_period_hours": v.grace_period_hours,
                }
                if v.notes:
                    entry["notes"] = v.notes
                # Apply counterparty overrides
                if counterparty_overrides and f.name in counterparty_overrides:
                    entry.update(counterparty_overrides[f.name])
                table[f.name] = entry

        return {
            "layer": "HOT_SWAP",
            "governance": "MUTABLE — counterparty policy, no hash required",
            "source": "default" if not counterparty_overrides else "custom",
            "verifiers": table,
        }

    def validate_split(self) -> dict:
        """Validate that every MUST field has a verifier assignment."""
        must_fields = {f.name for f in self.fields if f.requirement == "MUST"}
        verified_fields = set(self.verifiers.keys())
        unverified = must_fields - verified_fields
        orphaned = verified_fields - {f.name for f in self.fields}

        return {
            "valid": len(unverified) == 0 and len(orphaned) == 0,
            "must_fields": len(must_fields),
            "verified": len(must_fields & verified_fields),
            "unverified_must": list(unverified),
            "orphaned_verifiers": list(orphaned),
        }


def demo():
    splitter = ATFRegistrySplitter(ATF_FIELD_SCHEMA, DEFAULT_VERIFIER_TABLE)

    print("=" * 60)
    print("FROZEN LAYER (immutable per version)")
    print("=" * 60)
    print(json.dumps(splitter.frozen_layer(), indent=2))

    print()
    print("=" * 60)
    print("HOT-SWAP LAYER (default verifier table)")
    print("=" * 60)
    print(json.dumps(splitter.hotswap_layer(), indent=2))

    print()
    print("=" * 60)
    print("HOT-SWAP LAYER (paranoid counterparty override)")
    print("=" * 60)
    paranoid = {
        "evidence_grade": {"threshold": 0.8, "verifier_type": "oracle"},
        "grader_id": {"grace_period_hours": 0},
        "failure_hash": {"verifier_type": "oracle", "notes": "Oracle must verify failures too"},
    }
    print(json.dumps(splitter.hotswap_layer(paranoid), indent=2))

    print()
    print("=" * 60)
    print("SPLIT VALIDATION")
    print("=" * 60)
    print(json.dumps(splitter.validate_split(), indent=2))


if __name__ == "__main__":
    demo()
