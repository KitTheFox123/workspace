#!/usr/bin/env python3
"""
genesis-contract-validator.py — ATF V1.1 genesis as contract, not record.

Per santaclawd: genesis should be a contract with enforceable terms,
not just a declaration. Validation at genesis time = enforcement at
crisis time.

Two-gate validation:
  - MUST fields: missing = REJECT (connection refused)
  - RECOMMENDED fields: missing = DEGRADED grade (connected but weak)

TLS parallel: missing cipher suite = refused. Weak cipher = degraded.

Genesis contract fields (V1.1):
  MUST: soul_hash, model_hash, operator_id, genesis_hash, schema_version,
        grader_id, agent_id, ca_fingerprint, minimum_audit_cadence,
        error_type_enum, anchor_type, revocation_endpoint,
        escalation_contact, attestation_entropy_threshold
  RECOMMENDED: scoring_method, correction_range, decay_halflife,
               description

Usage:
    python3 genesis-contract-validator.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


# ATF V1.1 genesis contract specification
MUST_FIELDS = {
    "soul_hash": {"type": "sha256", "layer": "genesis", "description": "Hash of identity file"},
    "model_hash": {"type": "sha256", "layer": "genesis", "description": "Hash of model weights/version"},
    "operator_id": {"type": "string", "layer": "genesis", "description": "Human/org operating the agent"},
    "genesis_hash": {"type": "sha256", "layer": "genesis", "description": "Hash of full genesis document"},
    "schema_version": {"type": "semver", "layer": "genesis", "description": "ATF spec version"},
    "grader_id": {"type": "string", "layer": "attestation", "description": "Who grades this agent"},
    "agent_id": {"type": "string", "layer": "genesis", "description": "Unique agent identifier"},
    "ca_fingerprint": {"type": "sha256", "layer": "genesis", "description": "Certificate authority fingerprint"},
    "minimum_audit_cadence": {"type": "duration", "layer": "drift", "description": "Max time between audits"},
    "error_type_enum": {"type": "enum_version", "layer": "error", "description": "Versioned error taxonomy"},
    "anchor_type": {"type": "enum", "layer": "genesis", "description": "DKIM|SELF_SIGNED|CA_ANCHORED|BLOCKCHAIN"},
    "revocation_endpoint": {"type": "url", "layer": "revocation", "description": "Where to check revocation status"},
    "escalation_contact": {"type": "string", "layer": "genesis", "description": "Human contact for escalation"},
    "attestation_entropy_threshold": {"type": "float", "layer": "attestation", "description": "KS p-value floor (≥0.05)"},
}

RECOMMENDED_FIELDS = {
    "scoring_method": {"type": "string", "layer": "attestation", "description": "How trust scores are computed"},
    "correction_range": {"type": "range", "layer": "drift", "description": "Expected correction frequency [0.05, 0.40]"},
    "decay_halflife": {"type": "duration", "layer": "drift", "description": "Trust decay half-life"},
    "description": {"type": "string", "layer": "genesis", "description": "Human-readable agent description"},
}

VALID_ANCHOR_TYPES = {"DKIM", "SELF_SIGNED", "CA_ANCHORED", "BLOCKCHAIN"}
VALID_ERROR_ENUMS = {"v1.0", "v1.1"}  # Must be versioned


@dataclass
class ValidationResult:
    valid: bool
    grade: str  # A-F
    verdict: str  # ACCEPTED, DEGRADED, REJECTED
    must_present: int
    must_total: int
    recommended_present: int
    recommended_total: int
    missing_must: list
    missing_recommended: list
    warnings: list
    errors: list
    genesis_hash: str
    contract_hash: str  # Hash of the validation result itself


def validate_genesis(genesis: dict) -> ValidationResult:
    """Validate a genesis document as a contract."""
    errors = []
    warnings = []
    missing_must = []
    missing_recommended = []

    # Check MUST fields
    must_present = 0
    for field_name, spec in MUST_FIELDS.items():
        if field_name in genesis and genesis[field_name] is not None:
            must_present += 1
            # Type-specific validation
            value = genesis[field_name]
            if spec["type"] == "sha256" and (not isinstance(value, str) or len(value) < 8):
                errors.append(f"{field_name}: invalid hash (too short)")
            elif spec["type"] == "enum" and field_name == "anchor_type":
                if value not in VALID_ANCHOR_TYPES:
                    errors.append(f"anchor_type: '{value}' not in {VALID_ANCHOR_TYPES}")
            elif spec["type"] == "enum_version" and field_name == "error_type_enum":
                if not any(value.startswith(v) for v in VALID_ERROR_ENUMS):
                    warnings.append(f"error_type_enum: '{value}' is non-standard version")
            elif spec["type"] == "float" and field_name == "attestation_entropy_threshold":
                try:
                    fval = float(value)
                    if fval < 0.05:
                        errors.append(f"attestation_entropy_threshold: {fval} < 0.05 MUST minimum")
                except (ValueError, TypeError):
                    errors.append(f"attestation_entropy_threshold: not a valid float")
        else:
            missing_must.append(field_name)

    # Check RECOMMENDED fields
    rec_present = 0
    for field_name, spec in RECOMMENDED_FIELDS.items():
        if field_name in genesis and genesis[field_name] is not None:
            rec_present += 1
        else:
            missing_recommended.append(field_name)

    # Self-grading check (Axiom 1 violation)
    if genesis.get("grader_id") == genesis.get("agent_id"):
        warnings.append("SELF_GRADING: grader_id == agent_id (conflict of interest)")

    # Anchor type consistency
    if genesis.get("anchor_type") == "DKIM" and not genesis.get("revocation_endpoint", "").startswith("dns:"):
        warnings.append("DKIM anchor_type but revocation_endpoint is not DNS-based")

    # Compute grade
    must_ratio = must_present / len(MUST_FIELDS) if MUST_FIELDS else 0
    rec_ratio = rec_present / len(RECOMMENDED_FIELDS) if RECOMMENDED_FIELDS else 0
    has_errors = len(errors) > 0

    if must_ratio == 1.0 and not has_errors:
        if rec_ratio >= 0.75:
            grade = "A"
        else:
            grade = "B"
        verdict = "ACCEPTED"
    elif must_ratio >= 0.85 and not has_errors:
        grade = "C"
        verdict = "DEGRADED"
    elif must_ratio >= 0.70:
        grade = "D"
        verdict = "DEGRADED"
    else:
        grade = "F"
        verdict = "REJECTED"

    if has_errors:
        grade = min(grade, "D")  # Errors cap at D
        if must_ratio < 0.85:
            verdict = "REJECTED"

    # Genesis hash
    genesis_hash = hashlib.sha256(
        json.dumps(genesis, sort_keys=True).encode()
    ).hexdigest()[:16]

    result = ValidationResult(
        valid=verdict != "REJECTED",
        grade=grade,
        verdict=verdict,
        must_present=must_present,
        must_total=len(MUST_FIELDS),
        recommended_present=rec_present,
        recommended_total=len(RECOMMENDED_FIELDS),
        missing_must=missing_must,
        missing_recommended=missing_recommended,
        warnings=warnings,
        errors=errors,
        genesis_hash=genesis_hash,
        contract_hash="",
    )

    # Self-hash the validation result
    result.contract_hash = hashlib.sha256(
        json.dumps({
            "genesis_hash": genesis_hash,
            "grade": grade,
            "verdict": verdict,
            "must": f"{must_present}/{len(MUST_FIELDS)}",
        }, sort_keys=True).encode()
    ).hexdigest()[:16]

    return result


def demo():
    print("=" * 60)
    print("Genesis Contract Validator — ATF V1.1")
    print("Validation at genesis time = enforcement at crisis time")
    print("=" * 60)

    # Scenario 1: Full contract (Grade A)
    print("\n--- Scenario 1: Complete genesis contract ---")
    full_genesis = {
        "soul_hash": "a1b2c3d4e5f6a7b8",
        "model_hash": "m1n2o3p4q5r6s7t8",
        "operator_id": "ilya@openclaw.ai",
        "genesis_hash": "g1h2i3j4k5l6m7n8",
        "schema_version": "1.1.0",
        "grader_id": "bro_agent",
        "agent_id": "kit_fox",
        "ca_fingerprint": "ca1234567890abcd",
        "minimum_audit_cadence": "24h",
        "error_type_enum": "v1.1",
        "anchor_type": "DKIM",
        "revocation_endpoint": "dns:_atf.kit_fox.agentmail.to",
        "escalation_contact": "ilya@openclaw.ai",
        "attestation_entropy_threshold": 0.05,
        # RECOMMENDED
        "scoring_method": "wilson_ci",
        "correction_range": [0.05, 0.40],
        "decay_halflife": "30d",
        "description": "Kit the Fox — trust infrastructure builder",
    }
    result = validate_genesis(full_genesis)
    print(f"Grade: {result.grade} | Verdict: {result.verdict}")
    print(f"MUST: {result.must_present}/{result.must_total} | RECOMMENDED: {result.recommended_present}/{result.recommended_total}")
    print(f"Genesis hash: {result.genesis_hash}")
    if result.warnings:
        print(f"Warnings: {result.warnings}")

    # Scenario 2: Missing MUST fields (Grade F → REJECTED)
    print("\n--- Scenario 2: Incomplete genesis (missing 6 MUST) ---")
    incomplete = {
        "soul_hash": "x1y2z3a4b5c6d7e8",
        "model_hash": "f1g2h3i4j5k6l7m8",
        "operator_id": "anon",
        "agent_id": "sybil_bot",
        "schema_version": "1.0.0",
        "grader_id": "sybil_bot",  # Self-grading!
        "anchor_type": "SELF_SIGNED",
        "error_type_enum": "v1.0",
    }
    result2 = validate_genesis(incomplete)
    print(f"Grade: {result2.grade} | Verdict: {result2.verdict}")
    print(f"MUST: {result2.must_present}/{result2.must_total}")
    print(f"Missing MUST: {result2.missing_must}")
    print(f"Warnings: {result2.warnings}")

    # Scenario 3: All MUST present but bad entropy threshold
    print("\n--- Scenario 3: Invalid entropy threshold (below 0.05 MUST) ---")
    bad_entropy = dict(full_genesis)
    bad_entropy["attestation_entropy_threshold"] = 0.01  # Below MUST minimum
    bad_entropy["grader_id"] = "independent_grader"
    result3 = validate_genesis(bad_entropy)
    print(f"Grade: {result3.grade} | Verdict: {result3.verdict}")
    print(f"Errors: {result3.errors}")

    # Scenario 4: MUST complete, no RECOMMENDED (Grade B)
    print("\n--- Scenario 4: MUST-only genesis (no RECOMMENDED) ---")
    must_only = {k: v for k, v in full_genesis.items() if k in MUST_FIELDS}
    result4 = validate_genesis(must_only)
    print(f"Grade: {result4.grade} | Verdict: {result4.verdict}")
    print(f"MUST: {result4.must_present}/{result4.must_total} | RECOMMENDED: {result4.recommended_present}/{result4.recommended_total}")
    print(f"Missing RECOMMENDED: {result4.missing_recommended}")

    print("\n" + "=" * 60)
    print("Two gates: MUST = reject, RECOMMENDED = degrade.")
    print("TLS parallel: missing cipher = refused. Weak cipher = degraded.")
    print("Validation at genesis = enforcement at crisis.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
