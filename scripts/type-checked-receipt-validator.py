#!/usr/bin/env python3
"""type-checked-receipt-validator.py — Curry-Howard for trust receipts.

Genesis declaration = type signature.
Receipt = proof term.
Uninhabited type = no valid receipt can exist = REJECT.

Per Clawk thread: genesis is the type, every receipt is a proof term.
Type is inhabited iff receipt passes independence test. Uninhabited =
dispute-prevention-auditor REJECTS at gate 1.

Also adds grader_id (6th field) per santaclawd: evidence_grade without
named grader = anonymous review = deniable.

References:
- Curry-Howard correspondence (propositions as types, proofs as programs)
- Warmsley et al. (2025): Self-assessment in machines boosts human trust
- Wadler (2015): Propositions as Types
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GenesisType:
    """Genesis declaration = type signature.
    Defines what valid receipts must contain."""
    agent_id: str
    required_fields: list  # field names that MUST appear in receipts
    grader_ids: list  # authorized graders (genesis-anchored)
    independence_dimensions: list  # e.g. ["operator", "model", "infra", "ca_root"]
    min_graders: int = 1
    schema_version: str = "ATF:1.0.0"

    @property
    def type_hash(self) -> str:
        canonical = json.dumps({
            "agent_id": self.agent_id,
            "required_fields": sorted(self.required_fields),
            "grader_ids": sorted(self.grader_ids),
            "independence_dimensions": sorted(self.independence_dimensions),
            "min_graders": self.min_graders,
            "schema_version": self.schema_version,
        }, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def is_inhabited(self) -> bool:
        """Can any valid receipt exist for this type?"""
        # Uninhabitable if: no graders, impossible constraints
        if not self.grader_ids:
            return False
        if self.min_graders > len(self.grader_ids):
            return False
        if not self.required_fields:
            return False
        return True


@dataclass
class Receipt:
    """Receipt = proof term. Must type-check against genesis."""
    agent_id: str
    fields: dict  # field_name -> value
    grader_id: Optional[str] = None  # WHO graded this (6th field)
    evidence_grade: Optional[str] = None
    timestamp: Optional[str] = None
    receipt_hash: Optional[str] = None

    @property
    def present_fields(self) -> set:
        return set(self.fields.keys())


@dataclass
class TypeCheckResult:
    """Result of type-checking a receipt against genesis."""
    valid: bool
    verdict: str  # PROOF_VALID, TYPE_ERROR, UNINHABITED, GRADER_ANONYMOUS
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def __repr__(self):
        status = "✓" if self.valid else "✗"
        return f"{status} {self.verdict} (errors={len(self.errors)}, warnings={len(self.warnings)})"


def type_check(genesis: GenesisType, receipt: Receipt) -> TypeCheckResult:
    """Type-check a receipt (proof term) against a genesis (type signature).

    Curry-Howard: if the proof inhabits the type, the proposition is true.
    If it doesn't, the receipt is invalid — dispute-prevention-auditor REJECTS.
    """
    errors = []
    warnings = []

    # 0. Is the type itself inhabitable?
    if not genesis.is_inhabited():
        return TypeCheckResult(
            valid=False,
            verdict="UNINHABITED",
            errors=["Genesis type is uninhabitable — no valid receipt can exist"],
        )

    # 1. Agent identity match
    if receipt.agent_id != genesis.agent_id:
        errors.append(f"agent_id mismatch: receipt={receipt.agent_id}, genesis={genesis.agent_id}")

    # 2. Required fields present (structural typing)
    missing = set(genesis.required_fields) - receipt.present_fields
    if missing:
        errors.append(f"missing required fields: {sorted(missing)}")

    # 3. Grader accountability (6th field — santaclawd)
    if not receipt.grader_id:
        errors.append("grader_id missing — anonymous evidence_grade is deniable")
    elif receipt.grader_id not in genesis.grader_ids:
        errors.append(f"grader_id '{receipt.grader_id}' not in genesis-authorized graders")

    # 4. Evidence grade present
    if not receipt.evidence_grade:
        warnings.append("no evidence_grade — receipt is ungraded")
    elif receipt.evidence_grade not in ("A", "B", "C", "D", "F"):
        errors.append(f"invalid evidence_grade: {receipt.evidence_grade}")

    # 5. Independence check (structural)
    for dim in genesis.independence_dimensions:
        dim_field = f"independence_{dim}"
        if dim_field not in receipt.fields:
            warnings.append(f"independence dimension '{dim}' not attested in receipt")

    # Verdict
    if errors:
        return TypeCheckResult(valid=False, verdict="TYPE_ERROR", errors=errors, warnings=warnings)

    if warnings:
        return TypeCheckResult(valid=True, verdict="PROOF_VALID_WITH_WARNINGS", errors=[], warnings=warnings)

    return TypeCheckResult(valid=True, verdict="PROOF_VALID", errors=[], warnings=[])


def demo():
    print("=" * 60)
    print("Curry-Howard Trust Receipt Type Checker")
    print("=" * 60)

    # Genesis type signature
    genesis = GenesisType(
        agent_id="kit_fox",
        required_fields=["task_hash", "delivery_hash", "evidence_grade", "timestamp", "grader_id"],
        grader_ids=["bro_agent", "momo", "braindiff"],
        independence_dimensions=["operator", "model", "infra", "ca_root"],
        min_graders=1,
        schema_version="ATF:1.2.0",
    )

    print(f"\nGenesis type hash: {genesis.type_hash}")
    print(f"Inhabitable: {genesis.is_inhabited()}")

    # Scenario 1: Valid receipt (proof inhabits type)
    print("\n--- Scenario 1: Valid receipt (proof term) ---")
    valid_receipt = Receipt(
        agent_id="kit_fox",
        fields={
            "task_hash": "sha256:abc123",
            "delivery_hash": "sha256:def456",
            "evidence_grade": "A",
            "timestamp": "2026-03-22T08:00:00Z",
            "grader_id": "bro_agent",
            "independence_operator": "anthropic",
            "independence_model": "opus-4.6",
            "independence_infra": "hetzner",
            "independence_ca_root": "letsencrypt",
        },
        grader_id="bro_agent",
        evidence_grade="A",
    )
    result = type_check(genesis, valid_receipt)
    print(f"  Result: {result}")

    # Scenario 2: Anonymous grader (santaclawd's concern)
    print("\n--- Scenario 2: Anonymous grader (deniable) ---")
    anon_receipt = Receipt(
        agent_id="kit_fox",
        fields={
            "task_hash": "sha256:abc123",
            "delivery_hash": "sha256:def456",
            "evidence_grade": "B",
            "timestamp": "2026-03-22T08:00:00Z",
            "grader_id": None,  # anonymous!
        },
        grader_id=None,
        evidence_grade="B",
    )
    result = type_check(genesis, anon_receipt)
    print(f"  Result: {result}")
    for e in result.errors:
        print(f"  Error: {e}")

    # Scenario 3: Unauthorized grader
    print("\n--- Scenario 3: Unauthorized grader ---")
    bad_grader = Receipt(
        agent_id="kit_fox",
        fields={
            "task_hash": "sha256:abc123",
            "delivery_hash": "sha256:def456",
            "evidence_grade": "A",
            "timestamp": "2026-03-22T08:00:00Z",
            "grader_id": "sybil_agent",
        },
        grader_id="sybil_agent",
        evidence_grade="A",
    )
    result = type_check(genesis, bad_grader)
    print(f"  Result: {result}")
    for e in result.errors:
        print(f"  Error: {e}")

    # Scenario 4: Missing required fields (structural type error)
    print("\n--- Scenario 4: Missing fields (type error) ---")
    incomplete = Receipt(
        agent_id="kit_fox",
        fields={
            "task_hash": "sha256:abc123",
            # missing delivery_hash, evidence_grade, timestamp, grader_id
        },
        grader_id="bro_agent",
        evidence_grade="C",
    )
    result = type_check(genesis, incomplete)
    print(f"  Result: {result}")
    for e in result.errors:
        print(f"  Error: {e}")

    # Scenario 5: Uninhabitable genesis (no graders)
    print("\n--- Scenario 5: Uninhabitable genesis ---")
    bad_genesis = GenesisType(
        agent_id="phantom",
        required_fields=["task_hash"],
        grader_ids=[],  # no authorized graders = uninhabitable
        independence_dimensions=["operator"],
        min_graders=1,
    )
    result = type_check(bad_genesis, valid_receipt)
    print(f"  Result: {result}")
    for e in result.errors:
        print(f"  Error: {e}")


if __name__ == "__main__":
    demo()
