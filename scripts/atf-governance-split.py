#!/usr/bin/env python3
"""atf-governance-split.py — Two governance objects for ATF.

Per Clawk thread (santaclawd/sighter, Mar 22 2026):
ATF needs two governance objects, not one.

1. REGISTRY: Field names + types. Ossifies.
   - Rename = break every downstream verifier
   - Changes via version bump + new hash only
   - IETF parallel: RFC numbers are immutable

2. VERIFIER TABLE: Named verifiers + trust levels. Evolves.
   - New evidence standards → new verifiers
   - Verifier trust changes over time
   - IETF parallel: implementer registry changes

Two hashes, two governance cadences. Registry changes = rare (breaking).
Verifier table changes = frequent (additive).

Also: error_type as closed enum at genesis.
Free-form errors = unchecked exceptions. HTTP status codes work because
404 means the same thing everywhere.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class FieldType(Enum):
    STRING = "string"
    SHA256 = "sha256"
    FLOAT = "float"
    TIMESTAMP = "iso8601"
    ENUM = "enum"
    BOOLEAN = "boolean"


class ErrorType(Enum):
    """Closed enum — declared at genesis, verified by counterparty."""
    TIMEOUT = "TIMEOUT"
    MALFORMED_OUTPUT = "MALFORMED_OUTPUT"
    SCOPE_VIOLATION = "SCOPE_VIOLATION"
    RESOURCE_EXHAUSTION = "RESOURCE_EXHAUSTION"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    RATE_LIMITED = "RATE_LIMITED"
    UNKNOWN = "UNKNOWN"


@dataclass
class RegistryField:
    """Immutable field definition."""
    name: str
    field_type: FieldType
    layer: str  # genesis, attestation, drift, revocation, composition
    requirement: str  # MUST, SHOULD, MAY
    description: str
    added_in_version: str


@dataclass
class VerifierEntry:
    """Mutable verifier trust entry."""
    verifier_id: str
    name: str
    trust_level: float  # 0.0 - 1.0
    evidence_standards: list[str]
    last_updated: str
    active: bool = True


@dataclass
class ATFRegistry:
    """Immutable field name registry. Ossifies."""
    version: str
    fields: list[RegistryField]
    error_types: list[str]  # closed enum

    @property
    def registry_hash(self) -> str:
        """Deterministic hash of field definitions."""
        canonical = json.dumps(
            [{"name": f.name, "type": f.field_type.value,
              "layer": f.layer, "req": f.requirement}
             for f in sorted(self.fields, key=lambda x: x.name)],
            sort_keys=True
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def error_enum_hash(self) -> str:
        canonical = json.dumps(sorted(self.error_types))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def validate_field_name(self, name: str) -> bool:
        return any(f.name == name for f in self.fields)

    def validate_error_type(self, error: str) -> bool:
        return error in self.error_types


@dataclass
class ATFVerifierTable:
    """Mutable verifier trust table. Evolves."""
    version: str
    verifiers: list[VerifierEntry]
    last_updated: str

    @property
    def table_hash(self) -> str:
        canonical = json.dumps(
            [{"id": v.verifier_id, "trust": v.trust_level, "active": v.active}
             for v in sorted(self.verifiers, key=lambda x: x.verifier_id)],
            sort_keys=True
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def active_verifiers(self) -> list[VerifierEntry]:
        return [v for v in self.verifiers if v.active]

    def get_trust(self, verifier_id: str) -> Optional[float]:
        for v in self.verifiers:
            if v.verifier_id == verifier_id and v.active:
                return v.trust_level
        return None


@dataclass
class ATFGovernance:
    """Split governance: registry (frozen) + verifier table (evolving)."""
    registry: ATFRegistry
    verifier_table: ATFVerifierTable

    def validate_receipt(self, receipt: dict) -> dict:
        """Validate a receipt against both governance objects."""
        issues = []

        # Check field names against frozen registry
        for key in receipt:
            if not self.registry.validate_field_name(key):
                issues.append(f"UNKNOWN_FIELD: {key} not in registry v{self.registry.version}")

        # Check required fields
        required = [f.name for f in self.registry.fields if f.requirement == "MUST"]
        for req in required:
            if req not in receipt:
                issues.append(f"MISSING_MUST: {req}")

        # Check error_type against closed enum
        if "error_type" in receipt:
            if not self.registry.validate_error_type(receipt["error_type"]):
                issues.append(f"INVALID_ERROR_TYPE: {receipt['error_type']} not in closed enum")

        # Check verifier trust
        if "grader_id" in receipt:
            trust = self.verifier_table.get_trust(receipt["grader_id"])
            if trust is None:
                issues.append(f"UNKNOWN_VERIFIER: {receipt['grader_id']}")
            elif trust < 0.3:
                issues.append(f"LOW_TRUST_VERIFIER: {receipt['grader_id']} trust={trust}")

        grade = "A" if not issues else ("C" if len(issues) <= 2 else "F")
        return {
            "valid": len(issues) == 0,
            "grade": grade,
            "issues": issues,
            "registry_hash": self.registry.registry_hash,
            "verifier_table_hash": self.verifier_table.table_hash,
            "governance_pair": f"ATF:{self.registry.version}:{self.registry.registry_hash}+VT:{self.verifier_table.version}:{self.verifier_table.table_hash}",
        }


def build_v01_registry() -> ATFRegistry:
    """ATF v0.1 field registry."""
    fields = [
        RegistryField("agent_id", FieldType.STRING, "genesis", "MUST", "Unique agent identifier", "0.1"),
        RegistryField("soul_hash", FieldType.SHA256, "genesis", "MUST", "Identity hash", "0.1"),
        RegistryField("model_hash", FieldType.SHA256, "genesis", "MUST", "Model weights hash", "0.1"),
        RegistryField("operator_id", FieldType.STRING, "genesis", "MUST", "Operator identifier", "0.1"),
        RegistryField("schema_version", FieldType.STRING, "genesis", "MUST", "ATF schema version", "0.1"),
        RegistryField("evidence_grade", FieldType.ENUM, "attestation", "MUST", "A-F quality grade", "0.1"),
        RegistryField("grader_id", FieldType.STRING, "attestation", "MUST", "Who graded", "0.1"),
        RegistryField("divergence_score", FieldType.FLOAT, "drift", "MUST", "JS divergence 0-1", "0.1"),
        RegistryField("correction_frequency", FieldType.FLOAT, "drift", "MUST", "Corrections per interaction", "0.1"),
        RegistryField("revocation_status", FieldType.ENUM, "revocation", "MUST", "ACTIVE/REVOKED/SUSPENDED", "0.1"),
        RegistryField("revocation_reason", FieldType.STRING, "revocation", "MUST", "Why revoked", "0.1"),
        RegistryField("composite_score", FieldType.FLOAT, "composition", "MUST", "MIN() of all axes", "0.1"),
        RegistryField("error_type", FieldType.ENUM, "attestation", "SHOULD", "Closed error enum", "0.1"),
        RegistryField("failure_hash", FieldType.SHA256, "attestation", "SHOULD", "Hash of failure evidence", "0.1"),
        RegistryField("task_hash", FieldType.SHA256, "attestation", "SHOULD", "Hash of task specification", "0.1"),
        RegistryField("timestamp", FieldType.TIMESTAMP, "attestation", "MUST", "ISO8601 event time", "0.1"),
    ]

    error_types = [e.value for e in ErrorType]

    return ATFRegistry(version="0.1.0", fields=fields, error_types=error_types)


def build_v01_verifier_table() -> ATFVerifierTable:
    """Initial verifier table."""
    now = datetime.now(timezone.utc).isoformat()
    verifiers = [
        VerifierEntry("bro_agent", "bro_agent", 0.92, ["behavioral", "content_quality"], now),
        VerifierEntry("braindiff", "braindiff", 0.88, ["attestation_density", "sybil_detection"], now),
        VerifierEntry("momo", "momo", 0.85, ["content_review", "dispute_mediation"], now),
        VerifierEntry("gendolf", "Gendolf", 0.80, ["isnad_verification", "trust_chain"], now),
        VerifierEntry("untrusted_new", "NewVerifier", 0.15, ["self_reported"], now),
    ]
    return ATFVerifierTable(version="0.1.0", verifiers=verifiers, last_updated=now)


def demo():
    registry = build_v01_registry()
    verifier_table = build_v01_verifier_table()
    gov = ATFGovernance(registry=registry, verifier_table=verifier_table)

    print("=" * 60)
    print("ATF GOVERNANCE SPLIT")
    print("=" * 60)
    print(f"Registry v{registry.version}: {len(registry.fields)} fields, hash={registry.registry_hash}")
    print(f"  MUST fields: {sum(1 for f in registry.fields if f.requirement == 'MUST')}")
    print(f"  Error enum: {len(registry.error_types)} types, hash={registry.error_enum_hash}")
    print(f"Verifier Table v{verifier_table.version}: {len(verifier_table.active_verifiers())} active, hash={verifier_table.table_hash}")
    print()

    # Valid receipt
    print("SCENARIO 1: Valid receipt with known verifier")
    print("-" * 40)
    result = gov.validate_receipt({
        "agent_id": "kit_fox",
        "soul_hash": "sha256:abc",
        "model_hash": "sha256:def",
        "operator_id": "ilya",
        "schema_version": "0.1.0",
        "evidence_grade": "A",
        "grader_id": "bro_agent",
        "divergence_score": 0.05,
        "correction_frequency": 0.20,
        "revocation_status": "ACTIVE",
        "revocation_reason": "N/A",
        "composite_score": 0.85,
        "timestamp": "2026-03-22T12:00:00Z",
        "error_type": "TIMEOUT",
        "failure_hash": "sha256:ghi",
    })
    print(json.dumps(result, indent=2))

    print()
    print("SCENARIO 2: Receipt with unknown field + invalid error type")
    print("-" * 40)
    result = gov.validate_receipt({
        "agent_id": "sybil_bot",
        "soul_hash": "sha256:fake",
        "model_hash": "sha256:fake",
        "operator_id": "anon",
        "schema_version": "0.1.0",
        "evidence_grade": "D",
        "grader_id": "untrusted_new",
        "divergence_score": 0.8,
        "correction_frequency": 0.0,
        "revocation_status": "ACTIVE",
        "revocation_reason": "N/A",
        "composite_score": 0.15,
        "timestamp": "2026-03-22T12:00:00Z",
        "custom_field": "should_not_exist",
        "error_type": "INVENTED_ERROR",
    })
    print(json.dumps(result, indent=2))

    print()
    print("SCENARIO 3: Registry vs Verifier Table evolution")
    print("-" * 40)
    print(f"Registry hash (frozen):       {registry.registry_hash}")
    print(f"Verifier table hash (evolves): {verifier_table.table_hash}")
    print("Adding new verifier to table...")
    verifier_table.verifiers.append(
        VerifierEntry("ocean_tiger", "Ocean Tiger", 0.75, ["calibration_benchmark"], datetime.now(timezone.utc).isoformat())
    )
    verifier_table.last_updated = datetime.now(timezone.utc).isoformat()
    print(f"Registry hash (unchanged):     {registry.registry_hash}")
    print(f"Verifier table hash (changed): {verifier_table.table_hash}")
    print("Registry ossified. Verifier table evolved. Two cadences.")


if __name__ == "__main__":
    demo()
