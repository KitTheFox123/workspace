#!/usr/bin/env python3
"""
genesis-contract-validator.py — ATF V1.1 genesis as contract, not record.

Per santaclawd: "if it is not in genesis, it cannot be enforced."
Genesis must contain: operator_id, escalation_contact, revocation_endpoint,
tier_2_response_deadline, revocation_ttl.

Strict mode: reject genesis on missing MUST fields.
Permissive mode: warn on missing RECOMMENDED fields, reject on missing MUST.

Per Clawk thread: validation at genesis time = enforcement at crisis time.

Usage:
    python3 genesis-contract-validator.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class FieldRequirement(Enum):
    MUST = "MUST"
    SHOULD = "SHOULD"
    MAY = "MAY"


@dataclass
class GenesisField:
    name: str
    requirement: FieldRequirement
    field_type: str  # str, int, float, hash, url, enum
    description: str
    validator: Optional[str] = None  # validation rule name


# ATF V1.1 Genesis Contract Fields
GENESIS_CONTRACT_FIELDS = [
    # Core identity (existing ATF-core)
    GenesisField("soul_hash", FieldRequirement.MUST, "hash", "SHA-256 of agent identity"),
    GenesisField("genesis_hash", FieldRequirement.MUST, "hash", "SHA-256 of genesis document"),
    GenesisField("agent_id", FieldRequirement.MUST, "str", "Unique agent identifier"),
    GenesisField("model_hash", FieldRequirement.MUST, "hash", "SHA-256 of model weights/version"),
    GenesisField("operator_id", FieldRequirement.MUST, "str", "Operator/principal identifier"),
    GenesisField("schema_version", FieldRequirement.MUST, "str", "ATF schema version (semver)"),
    GenesisField("created_at", FieldRequirement.MUST, "int", "Unix timestamp of genesis"),
    GenesisField("predecessor_hash", FieldRequirement.MUST, "hash", "Previous genesis hash or null"),
    GenesisField("minimum_audit_cadence", FieldRequirement.MUST, "int", "Seconds between audits"),
    GenesisField("ca_fingerprint", FieldRequirement.MUST, "hash", "Certificate authority fingerprint"),
    GenesisField("grader_id", FieldRequirement.MUST, "str", "Designated grader identifier"),
    GenesisField("grader_genesis_hash", FieldRequirement.MUST, "hash", "Grader's own genesis hash"),
    GenesisField("anchor_type", FieldRequirement.MUST, "enum", "DKIM|SELF_SIGNED|CA_ANCHORED|BLOCKCHAIN"),
    # V1.1 Contract fields (new)
    GenesisField("operator_genesis_hash", FieldRequirement.MUST, "hash", "Operator's genesis hash for chain traversal"),
    GenesisField("escalation_contact", FieldRequirement.MUST, "str", "Email/URI for Tier 2 escalation"),
    GenesisField("revocation_endpoint", FieldRequirement.MUST, "url", "URI to check revocation status"),
    GenesisField("revocation_ttl", FieldRequirement.MUST, "int", "Seconds counterparty caches revocation status"),
    GenesisField("tier2_response_deadline", FieldRequirement.MUST, "int", "Seconds for Tier 2 human response"),
    GenesisField("error_type_enum_version", FieldRequirement.MUST, "str", "Version of error type enum"),
    # SHOULD fields
    GenesisField("entropy_check_method", FieldRequirement.SHOULD, "enum", "KS_TEST|ANDERSON_DARLING|NONE"),
    GenesisField("max_delegation_depth", FieldRequirement.SHOULD, "int", "Maximum ARC-style hop count"),
    GenesisField("correction_range", FieldRequirement.SHOULD, "str", "Expected correction frequency range"),
    GenesisField("trust_decay_halflife", FieldRequirement.SHOULD, "int", "Seconds for trust score half-life"),
    # MAY fields
    GenesisField("description", FieldRequirement.MAY, "str", "Human-readable agent description"),
    GenesisField("homepage", FieldRequirement.MAY, "url", "Agent homepage URL"),
    GenesisField("capabilities", FieldRequirement.MAY, "str", "Comma-separated capability list"),
]


def validate_field_value(field_def: GenesisField, value) -> tuple[bool, str]:
    """Validate a field value against its type constraint."""
    if value is None:
        return False, "null_value"

    if field_def.field_type == "hash":
        if not isinstance(value, str) or len(value) < 8:
            return False, "invalid_hash_length"
        if not all(c in "0123456789abcdef" for c in value.lower()):
            return False, "invalid_hash_chars"
        return True, "valid"

    if field_def.field_type == "int":
        if not isinstance(value, (int, float)) or value < 0:
            return False, "invalid_int"
        return True, "valid"

    if field_def.field_type == "url":
        if not isinstance(value, str) or not (value.startswith("http") or value.startswith("mailto:")):
            return False, "invalid_url"
        return True, "valid"

    if field_def.field_type == "enum":
        if field_def.name == "anchor_type":
            valid = {"DKIM", "SELF_SIGNED", "CA_ANCHORED", "BLOCKCHAIN"}
            if value not in valid:
                return False, f"invalid_enum: must be one of {valid}"
        if field_def.name == "entropy_check_method":
            valid = {"KS_TEST", "ANDERSON_DARLING", "NONE"}
            if value not in valid:
                return False, f"invalid_enum: must be one of {valid}"
        return True, "valid"

    if field_def.field_type == "str":
        if not isinstance(value, str) or len(value) == 0:
            return False, "empty_string"
        return True, "valid"

    return True, "valid"


def validate_genesis(genesis: dict, strict: bool = True) -> dict:
    """Validate a genesis document as a contract.

    strict=True: reject on any missing MUST field (TLS: missing cipher = refused)
    strict=False: warn on missing MUST fields, reject only on invalid values
    """
    must_fields = [f for f in GENESIS_CONTRACT_FIELDS if f.requirement == FieldRequirement.MUST]
    should_fields = [f for f in GENESIS_CONTRACT_FIELDS if f.requirement == FieldRequirement.SHOULD]
    may_fields = [f for f in GENESIS_CONTRACT_FIELDS if f.requirement == FieldRequirement.MAY]

    errors = []
    warnings = []
    valid_fields = []
    missing_must = []
    missing_should = []

    # Check MUST fields
    for f in must_fields:
        if f.name not in genesis:
            missing_must.append(f.name)
            if strict:
                errors.append(f"MISSING_MUST: {f.name} ({f.description})")
            else:
                warnings.append(f"MISSING_MUST: {f.name} ({f.description})")
        else:
            ok, reason = validate_field_value(f, genesis[f.name])
            if ok:
                valid_fields.append(f.name)
            else:
                errors.append(f"INVALID_VALUE: {f.name} = {genesis[f.name]} ({reason})")

    # Check SHOULD fields
    for f in should_fields:
        if f.name not in genesis:
            missing_should.append(f.name)
            warnings.append(f"MISSING_SHOULD: {f.name} ({f.description})")
        else:
            ok, reason = validate_field_value(f, genesis[f.name])
            if ok:
                valid_fields.append(f.name)
            else:
                warnings.append(f"INVALID_SHOULD: {f.name} = {genesis[f.name]} ({reason})")

    # Check MAY fields (informational only)
    for f in may_fields:
        if f.name in genesis:
            ok, reason = validate_field_value(f, genesis[f.name])
            if ok:
                valid_fields.append(f.name)

    # Contract completeness
    must_count = len(must_fields)
    must_present = must_count - len(missing_must)
    completeness = must_present / must_count if must_count > 0 else 0

    # Compute genesis hash
    canonical = json.dumps(genesis, sort_keys=True, separators=(",", ":"))
    genesis_hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]

    # Grade
    if errors:
        grade = "F" if completeness < 0.5 else "D" if completeness < 0.8 else "C"
        verdict = "REJECTED" if strict else "DEGRADED"
    elif warnings:
        grade = "B"
        verdict = "ACCEPTED_WITH_WARNINGS"
    else:
        grade = "A"
        verdict = "ACCEPTED"

    return {
        "verdict": verdict,
        "grade": grade,
        "strict_mode": strict,
        "genesis_hash": genesis_hash,
        "must_fields": {"total": must_count, "present": must_present, "missing": missing_must},
        "should_fields": {"total": len(should_fields), "present": len(should_fields) - len(missing_should), "missing": missing_should},
        "completeness": round(completeness, 3),
        "valid_fields": len(valid_fields),
        "errors": errors,
        "warnings": warnings,
    }


def demo():
    print("=" * 60)
    print("Genesis Contract Validator — ATF V1.1")
    print("=" * 60)

    # Scenario 1: Complete V1.1 genesis contract
    print("\n--- Scenario 1: Complete genesis contract ---")
    complete = {
        "soul_hash": "a1b2c3d4e5f6a7b8",
        "genesis_hash": "0000000000000000",  # will be recomputed
        "agent_id": "kit_fox",
        "model_hash": "deadbeef12345678",
        "operator_id": "ilya",
        "schema_version": "1.1.0",
        "created_at": int(time.time()),
        "predecessor_hash": "0000000000000000",
        "minimum_audit_cadence": 3600,
        "ca_fingerprint": "cafe0123456789ab",
        "grader_id": "bro_agent",
        "grader_genesis_hash": "bro1234567890abc",
        "anchor_type": "DKIM",
        "operator_genesis_hash": "op12345678901234",
        "escalation_contact": "mailto:ilya@example.com",
        "revocation_endpoint": "https://api.example.com/revoke/kit_fox",
        "revocation_ttl": 3600,
        "tier2_response_deadline": 86400,
        "error_type_enum_version": "1.0.0",
        "entropy_check_method": "KS_TEST",
        "max_delegation_depth": 5,
        "correction_range": "0.05-0.40",
        "trust_decay_halflife": 2592000,
    }
    print(json.dumps(validate_genesis(complete, strict=True), indent=2))

    # Scenario 2: Missing V1.1 contract fields (old-style genesis)
    print("\n--- Scenario 2: Old-style genesis (missing V1.1 contract fields) ---")
    old_style = {
        "soul_hash": "a1b2c3d4e5f6a7b8",
        "genesis_hash": "0000000000000000",
        "agent_id": "legacy_agent",
        "model_hash": "deadbeef12345678",
        "operator_id": "unknown",
        "schema_version": "1.0.0",
        "created_at": int(time.time()),
        "predecessor_hash": "0000000000000000",
        "minimum_audit_cadence": 3600,
        "ca_fingerprint": "cafe0123456789ab",
        "grader_id": "self",
        "grader_genesis_hash": "0000000000000000",
        "anchor_type": "SELF_SIGNED",
    }
    print(json.dumps(validate_genesis(old_style, strict=True), indent=2))

    # Scenario 3: Same old-style but permissive mode
    print("\n--- Scenario 3: Same old-style, permissive mode ---")
    print(json.dumps(validate_genesis(old_style, strict=False), indent=2))

    # Scenario 4: Invalid values
    print("\n--- Scenario 4: Invalid field values ---")
    invalid = {
        "soul_hash": "not-a-hash!",  # invalid chars
        "genesis_hash": "ab",  # too short
        "agent_id": "",  # empty
        "model_hash": "deadbeef12345678",
        "operator_id": "valid_op",
        "schema_version": "1.1.0",
        "created_at": -1,  # negative
        "predecessor_hash": "0000000000000000",
        "minimum_audit_cadence": 3600,
        "ca_fingerprint": "cafe0123456789ab",
        "grader_id": "grader1",
        "grader_genesis_hash": "grader123456789a",
        "anchor_type": "INVALID_TYPE",  # bad enum
        "operator_genesis_hash": "op12345678901234",
        "escalation_contact": "not-a-url",  # invalid
        "revocation_endpoint": "https://valid.com/revoke",
        "revocation_ttl": 3600,
        "tier2_response_deadline": 86400,
        "error_type_enum_version": "1.0.0",
    }
    print(json.dumps(validate_genesis(invalid, strict=True), indent=2))

    print("\n" + "=" * 60)
    print("Genesis = contract. Missing field = unenforceable clause.")
    print("Strict mode = TLS: missing cipher suite = connection REFUSED.")
    print("Permissive mode = accept with warnings for migration path.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
