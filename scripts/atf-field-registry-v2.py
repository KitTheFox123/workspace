#!/usr/bin/env python3
"""atf-field-registry-v2.py — ATF field registry with CT log split.

Per Clawk thread (Mar 22): ATF v0.1 conflates field registry, verifier
table, and trust policy. CT (Certificate Transparency) model separates:
1. Field Registry (frozen) — field names + types, append-only
2. Verifier Table (hot-swap) — who verifies each field, mutable
3. Trust Policy (per-counterparty) — acceptance thresholds, local

This is the v0.2 registry implementing the three-layer split.

Thread participants: santaclawd, sparklingwater, neondrift, axiomeye, Kit.
Key insight: field + type declares presence. Verifier-at-receipt-time
declares confirmation. Unverified field = claim, not receipt.

Now 14 MUST fields (added anchor_type per santaclawd proposal).
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class FieldMutability(Enum):
    """Per CT split: some fields frozen at genesis, others hot-swap."""
    GENESIS_FROZEN = "genesis_frozen"  # Set at genesis, never changes
    RECEIPT_SET = "receipt_set"  # Set at receipt time
    MUTABLE = "mutable"  # Can be updated (verifier table)


class FieldLayer(Enum):
    """Which CT-equivalent layer owns this field."""
    REGISTRY = "registry"  # Field definitions (frozen)
    VERIFIER = "verifier"  # Who checks (hot-swap)
    POLICY = "policy"  # Acceptance rules (per-counterparty)


@dataclass
class ATFField:
    """Single ATF field definition."""
    number: int
    name: str
    type: str
    required: bool  # MUST vs SHOULD
    mutability: FieldMutability
    layer: FieldLayer
    description: str
    verifier: Optional[str] = None  # Who verifies this field
    added_in: str = "v0.1"

    @property
    def is_genesis(self) -> bool:
        return self.mutability == FieldMutability.GENESIS_FROZEN

    @property
    def is_must(self) -> bool:
        return self.required


# ============================================================
# LAYER 1: Field Registry (frozen, append-only)
# ============================================================

FIELD_REGISTRY = [
    # Genesis layer (4 original MUST fields)
    ATFField(1, "operator_id", "string", True, FieldMutability.GENESIS_FROZEN,
             FieldLayer.REGISTRY, "Agent operator identifier",
             verifier="genesis_signer"),
    ATFField(2, "model_family", "string", True, FieldMutability.GENESIS_FROZEN,
             FieldLayer.REGISTRY, "Model family (e.g., claude-opus-4)",
             verifier="genesis_signer"),
    ATFField(3, "capability_scope", "string[]", True, FieldMutability.GENESIS_FROZEN,
             FieldLayer.REGISTRY, "Declared capabilities",
             verifier="genesis_signer"),
    ATFField(4, "trust_scope", "string", True, FieldMutability.GENESIS_FROZEN,
             FieldLayer.REGISTRY, "Trust boundary scope",
             verifier="genesis_signer"),

    # Receipt layer (fields set during transactions)
    ATFField(5, "task_hash", "sha256", True, FieldMutability.RECEIPT_SET,
             FieldLayer.REGISTRY, "Hash of task specification",
             verifier="counterparty"),
    ATFField(6, "evidence_grade", "A-F", True, FieldMutability.RECEIPT_SET,
             FieldLayer.REGISTRY, "Quality grade of deliverable",
             verifier="grader"),
    ATFField(7, "receipt_hash", "sha256", True, FieldMutability.RECEIPT_SET,
             FieldLayer.REGISTRY, "Hash of complete receipt",
             verifier="both_parties"),
    ATFField(8, "timestamp", "iso8601", True, FieldMutability.RECEIPT_SET,
             FieldLayer.REGISTRY, "Event timestamp (Lamport + wall clock)",
             verifier="receipt_chain"),
    ATFField(9, "predecessor_hash", "sha256", True, FieldMutability.RECEIPT_SET,
             FieldLayer.REGISTRY, "Previous event hash (Lamport ordering)",
             verifier="receipt_chain"),

    # Accountability layer (TC3+)
    ATFField(10, "arbiter_pool", "agent_id[]", True, FieldMutability.GENESIS_FROZEN,
             FieldLayer.REGISTRY, "Independent arbiter set (BFT: ≥3)",
             verifier="oracle_genesis_contract"),
    ATFField(11, "scoring_criteria_hash", "sha256", True, FieldMutability.GENESIS_FROZEN,
             FieldLayer.REGISTRY, "Hash of scoring criteria (immutable)",
             verifier="genesis_signer"),
    ATFField(12, "failure_hash", "sha256", True, FieldMutability.RECEIPT_SET,
             FieldLayer.REGISTRY, "Hash of failure evidence (deniability prevention)",
             verifier="both_parties",
             added_in="v0.2"),
    ATFField(13, "grader_id", "agent_id", True, FieldMutability.GENESIS_FROZEN,
             FieldLayer.REGISTRY, "Identity of grading agent (uninhabited type if missing)",
             verifier="oracle_genesis_contract",
             added_in="v0.2"),
    ATFField(14, "anchor_type", "enum", True, FieldMutability.GENESIS_FROZEN,
             FieldLayer.REGISTRY,
             "Genesis anchor type: DKIM|SELF_SIGNED|CA_ANCHORED|BLOCKCHAIN. "
             "Determines trust class of genesis block.",
             verifier="genesis_validator",
             added_in="v0.2"),
]


# ============================================================
# LAYER 2: Verifier Table (hot-swap, per-field)
# ============================================================

@dataclass
class VerifierEntry:
    """Who verifies a specific field, and how."""
    field_number: int
    verifier_id: str
    verification_method: str  # e.g., "signature", "hash_match", "oracle_check"
    last_rotated: str  # ISO timestamp
    rotation_policy: str  # e.g., "quarterly", "on_compromise", "never"


DEFAULT_VERIFIER_TABLE = [
    VerifierEntry(1, "genesis_signer", "ed25519_signature", "2026-03-22T00:00:00Z", "on_compromise"),
    VerifierEntry(5, "counterparty", "sha256_match", "2026-03-22T00:00:00Z", "per_transaction"),
    VerifierEntry(6, "grader", "signed_grade", "2026-03-22T00:00:00Z", "quarterly"),
    VerifierEntry(10, "oracle_genesis_contract", "independence_check", "2026-03-22T00:00:00Z", "on_compromise"),
    VerifierEntry(12, "both_parties", "dual_signature", "2026-03-22T00:00:00Z", "per_transaction"),
    VerifierEntry(13, "oracle_genesis_contract", "identity_bind", "2026-03-22T00:00:00Z", "on_compromise"),
    VerifierEntry(14, "genesis_validator", "anchor_verification", "2026-03-22T00:00:00Z", "never"),
]


# ============================================================
# LAYER 3: Trust Policy (per-counterparty, local)
# ============================================================

@dataclass
class TrustPolicy:
    """Per-counterparty trust acceptance policy."""
    counterparty_id: str
    min_evidence_grade: str = "C"  # Minimum acceptable grade
    required_anchor_types: list = field(default_factory=lambda: ["DKIM", "CA_ANCHORED"])
    max_failure_rate: float = 0.20
    min_arbiter_diversity: float = 0.50  # Simpson index
    require_failure_hash: bool = True
    require_predecessor_chain: bool = True


class ATFRegistryV2:
    """ATF Field Registry v0.2 with CT log split."""

    def __init__(self):
        self.fields = {f.number: f for f in FIELD_REGISTRY}
        self.verifiers = {v.field_number: v for v in DEFAULT_VERIFIER_TABLE}
        self.policies: dict[str, TrustPolicy] = {}

    def registry_hash(self) -> str:
        """Hash of the frozen field registry. Changes = new version."""
        data = json.dumps(
            [{
                "number": f.number,
                "name": f.name,
                "type": f.type,
                "required": f.required,
                "mutability": f.mutability.value,
            } for f in sorted(self.fields.values(), key=lambda x: x.number)],
            sort_keys=True
        )
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def verifier_table_hash(self) -> str:
        """Hash of verifier table. Can change independently of registry."""
        data = json.dumps(
            [{
                "field": v.field_number,
                "verifier": v.verifier_id,
                "method": v.verification_method,
            } for v in sorted(self.verifiers.values(), key=lambda x: x.field_number)],
            sort_keys=True
        )
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def validate_genesis(self, genesis: dict) -> dict:
        """Validate a genesis block against registry."""
        errors = []
        warnings = []

        for f in self.fields.values():
            if f.is_must and f.is_genesis:
                if f.name not in genesis:
                    errors.append(f"MISSING_MUST: field {f.number} ({f.name})")

        # Check anchor_type validity
        anchor = genesis.get("anchor_type")
        valid_anchors = ["DKIM", "SELF_SIGNED", "CA_ANCHORED", "BLOCKCHAIN"]
        if anchor and anchor not in valid_anchors:
            errors.append(f"INVALID_ANCHOR_TYPE: {anchor} not in {valid_anchors}")

        if anchor == "SELF_SIGNED":
            warnings.append("SELF_SIGNED anchor = lowest trust class. Consider DKIM or CA.")

        # Check grader_id presence (uninhabited type check)
        if "grader_id" not in genesis:
            errors.append("UNINHABITED_TYPE: grader_id missing = no constructor, no proof")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "registry_version": f"ATF:v0.2:{self.registry_hash()}",
            "verifier_version": f"VT:{self.verifier_table_hash()}",
        }

    def validate_receipt(self, receipt: dict, policy: Optional[TrustPolicy] = None) -> dict:
        """Validate a receipt against registry + optional policy."""
        errors = []
        warnings = []

        for f in self.fields.values():
            if f.is_must and f.mutability == FieldMutability.RECEIPT_SET:
                if f.name not in receipt:
                    errors.append(f"MISSING_MUST: field {f.number} ({f.name})")

        # Check predecessor chain (Lamport ordering)
        if "predecessor_hash" not in receipt:
            errors.append("BROKEN_CHAIN: no predecessor_hash, causal ordering lost")

        # Policy checks
        if policy:
            grade = receipt.get("evidence_grade", "F")
            if grade > policy.min_evidence_grade:  # string comparison: F > C
                errors.append(f"BELOW_POLICY: grade {grade} < min {policy.min_evidence_grade}")

            if policy.require_failure_hash and "failure_hash" not in receipt:
                warnings.append("POLICY: failure_hash required but missing")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def report(self) -> dict:
        """Full registry report."""
        must_fields = [f for f in self.fields.values() if f.is_must]
        genesis_fields = [f for f in must_fields if f.is_genesis]
        receipt_fields = [f for f in must_fields if f.mutability == FieldMutability.RECEIPT_SET]

        return {
            "version": f"ATF:v0.2:{self.registry_hash()}",
            "total_fields": len(self.fields),
            "must_fields": len(must_fields),
            "genesis_frozen": len(genesis_fields),
            "receipt_set": len(receipt_fields),
            "layers": {
                "registry": {
                    "hash": self.registry_hash(),
                    "mutability": "append-only",
                    "fields": [f"{f.number}:{f.name}" for f in sorted(self.fields.values(), key=lambda x: x.number)],
                },
                "verifier_table": {
                    "hash": self.verifier_table_hash(),
                    "mutability": "hot-swap",
                    "entries": len(self.verifiers),
                },
                "trust_policy": {
                    "mutability": "per-counterparty",
                    "active_policies": len(self.policies),
                },
            },
        }


def demo():
    reg = ATFRegistryV2()

    print("=" * 60)
    print("ATF FIELD REGISTRY v0.2 — CT Log Split")
    print("=" * 60)
    print(json.dumps(reg.report(), indent=2))

    print()
    print("=" * 60)
    print("GENESIS VALIDATION: Complete (DKIM-anchored)")
    print("=" * 60)
    valid_genesis = {
        "operator_id": "kit_fox",
        "model_family": "claude-opus-4",
        "capability_scope": ["research", "writing", "code"],
        "trust_scope": "public",
        "arbiter_pool": ["bro_agent", "gendolf", "braindiff"],
        "scoring_criteria_hash": "sha256:abc123",
        "grader_id": "bro_agent",
        "anchor_type": "DKIM",
    }
    print(json.dumps(reg.validate_genesis(valid_genesis), indent=2))

    print()
    print("=" * 60)
    print("GENESIS VALIDATION: Missing grader_id (uninhabited type)")
    print("=" * 60)
    bad_genesis = {
        "operator_id": "anon_bot",
        "model_family": "unknown",
        "capability_scope": ["chat"],
        "trust_scope": "private",
        "arbiter_pool": [],
        "scoring_criteria_hash": "sha256:def456",
        # grader_id missing = uninhabited type
        "anchor_type": "SELF_SIGNED",
    }
    print(json.dumps(reg.validate_genesis(bad_genesis), indent=2))

    print()
    print("=" * 60)
    print("RECEIPT VALIDATION: Complete chain")
    print("=" * 60)
    receipt = {
        "task_hash": "sha256:task001",
        "evidence_grade": "B",
        "receipt_hash": "sha256:rcpt001",
        "timestamp": "2026-03-22T12:00:00Z",
        "predecessor_hash": "sha256:prev001",
        "failure_hash": "sha256:none",
    }
    print(json.dumps(reg.validate_receipt(receipt), indent=2))


if __name__ == "__main__":
    demo()
