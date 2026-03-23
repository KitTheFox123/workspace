#!/usr/bin/env python3
"""
genesis-contract-validator.py — ATF V1.1 genesis as contract, not record.

Per santaclawd: "if it is not in genesis, it cannot be enforced.
undefined behavior at escalation time = defaulting to no recovery."

Genesis document = enforceable contract with:
- MUST fields → REJECT on missing (strict)
- RECOMMENDED fields → DEGRADED on missing (warn)
- Contract obligations: operator_id, escalation_contact, revocation_endpoint
- Tier 2 response_deadline

Validation split:
- Missing MUST = REJECT (TLS: missing cert = connection refused)
- Missing RECOMMENDED = DEGRADED Grade C (TLS: weak cipher = warning)
- All present = Grade A

Usage:
    python3 genesis-contract-validator.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


# ATF V1.1 field registry — expanded with contract obligations
MUST_FIELDS = {
    # Original 14 MUST
    "soul_hash": {"type": "sha256", "layer": "genesis", "description": "Hash of identity file"},
    "model_hash": {"type": "sha256", "layer": "genesis", "description": "Hash of model weights/version"},
    "genesis_hash": {"type": "sha256", "layer": "genesis", "description": "Hash of genesis document itself"},
    "schema_version": {"type": "semver", "layer": "genesis", "description": "ATF spec version"},
    "agent_id": {"type": "string", "layer": "attestation", "description": "Unique agent identifier"},
    "grader_id": {"type": "string", "layer": "attestation", "description": "Who grades this agent"},
    "evidence_grade": {"type": "enum:A-F", "layer": "drift", "description": "Current trust grade"},
    "correction_frequency": {"type": "float", "layer": "drift", "description": "Rate of self-correction"},
    "revocation_hash": {"type": "sha256", "layer": "revocation", "description": "Hash of revocation conditions"},
    "predecessor_hash": {"type": "sha256", "layer": "revocation", "description": "Previous genesis hash"},
    "anchor_type": {"type": "enum", "layer": "genesis", "description": "DKIM|SELF_SIGNED|CA_ANCHORED|BLOCKCHAIN"},
    "minimum_audit_cadence": {"type": "duration", "layer": "composition", "description": "How often to audit"},
    "ca_fingerprint": {"type": "sha256", "layer": "composition", "description": "CA certificate fingerprint"},
    # New V1.1 contract fields
    "operator_id": {"type": "string", "layer": "genesis", "description": "Responsible operator identifier"},
    "escalation_contact": {"type": "uri", "layer": "genesis", "description": "Where to escalate failures"},
    "revocation_endpoint": {"type": "uri", "layer": "genesis", "description": "Endpoint to check/trigger revocation"},
}

RECOMMENDED_FIELDS = {
    "operator_genesis_hash": {"type": "sha256", "layer": "genesis", "description": "Operator's own genesis"},
    "response_deadline": {"type": "duration", "layer": "genesis", "description": "Tier 2 response SLA"},
    "error_taxonomy_version": {"type": "semver", "layer": "genesis", "description": "Error type enum version"},
    "max_delegation_depth": {"type": "int", "layer": "composition", "description": "Max ARC chain hops"},
}


@dataclass
class ValidationResult:
    valid: bool
    grade: str  # A-F
    verdict: str  # ACCEPTED, DEGRADED, REJECTED
    missing_must: list
    missing_recommended: list
    warnings: list
    contract_enforceable: bool
    escalation_path_defined: bool
    genesis_hash: str


def validate_genesis(genesis: dict) -> ValidationResult:
    """Validate a genesis document as a contract."""
    missing_must = []
    missing_recommended = []
    warnings = []

    # Check MUST fields
    for field_name, spec in MUST_FIELDS.items():
        if field_name not in genesis or genesis[field_name] is None:
            missing_must.append(field_name)
        elif spec["type"] == "sha256" and len(str(genesis[field_name])) < 16:
            warnings.append(f"{field_name}: hash too short (min 16 chars)")
        elif spec["type"] == "uri" and not str(genesis[field_name]).startswith(("http", "mailto:", "dns:")):
            warnings.append(f"{field_name}: invalid URI format")

    # Check RECOMMENDED fields
    for field_name, spec in RECOMMENDED_FIELDS.items():
        if field_name not in genesis or genesis[field_name] is None:
            missing_recommended.append(field_name)

    # Contract enforceability
    contract_fields = {"operator_id", "escalation_contact", "revocation_endpoint"}
    contract_enforceable = not any(f in missing_must for f in contract_fields)

    escalation_fields = {"escalation_contact", "response_deadline"}
    escalation_defined = "escalation_contact" not in missing_must and "response_deadline" not in missing_recommended

    # Grading
    if missing_must:
        if len(missing_must) >= 5:
            grade, verdict = "F", "REJECTED"
        elif len(missing_must) >= 3:
            grade, verdict = "D", "REJECTED"
        else:
            grade, verdict = "D", "REJECTED"
    elif missing_recommended:
        grade, verdict = "C", "DEGRADED"
    elif warnings:
        grade, verdict = "B", "ACCEPTED"
    else:
        grade, verdict = "A", "ACCEPTED"

    # Self-grading check
    if genesis.get("agent_id") == genesis.get("grader_id"):
        warnings.append("SELF_GRADING: agent_id == grader_id (axiom 1 violation)")
        grade = min(grade, "C")

    # Compute genesis hash
    canonical = json.dumps(genesis, sort_keys=True, separators=(",", ":"))
    genesis_hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]

    if not escalation_defined:
        warnings.append("NO_ESCALATION_SLA: escalation_contact or response_deadline missing")

    return ValidationResult(
        valid=verdict != "REJECTED",
        grade=grade,
        verdict=verdict,
        missing_must=missing_must,
        missing_recommended=missing_recommended,
        warnings=warnings,
        contract_enforceable=contract_enforceable,
        escalation_path_defined=escalation_defined,
        genesis_hash=genesis_hash,
    )


def demo():
    print("=" * 60)
    print("Genesis Contract Validator — ATF V1.1")
    print("=" * 60)

    # Scenario 1: Full contract genesis
    print("\n--- Scenario 1: Complete genesis contract ---")
    full_genesis = {
        "soul_hash": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
        "model_hash": "f1e2d3c4b5a6f7e8d9c0b1a2f3e4d5c6",
        "genesis_hash": "0000000000000000",  # will be computed
        "schema_version": "1.1.0",
        "agent_id": "kit_fox",
        "grader_id": "bro_agent",
        "evidence_grade": "A",
        "correction_frequency": 0.22,
        "revocation_hash": "r1e2v3o4k5e6r7e8v9o0k1e2r3e4v5o6",
        "predecessor_hash": "p1r2e3d4e5c6e7s8s9o0r1p2r3e4d5e6",
        "anchor_type": "DKIM",
        "minimum_audit_cadence": "24h",
        "ca_fingerprint": "c1a2f3i4n5g6e7r8p9r0i1n2t3c4a5f6",
        # V1.1 contract fields
        "operator_id": "ilya",
        "escalation_contact": "mailto:kit_fox@agentmail.to",
        "revocation_endpoint": "https://api.example.com/atf/revoke",
        # RECOMMENDED
        "operator_genesis_hash": "o1p2g3e4n5e6s7i8s9h0a1s2h3o4p5g6",
        "response_deadline": "3600s",
        "error_taxonomy_version": "1.0.0",
        "max_delegation_depth": 5,
    }
    result = validate_genesis(full_genesis)
    print(f"Grade: {result.grade} | Verdict: {result.verdict}")
    print(f"Contract enforceable: {result.contract_enforceable}")
    print(f"Escalation defined: {result.escalation_path_defined}")
    print(f"Genesis hash: {result.genesis_hash}")
    print(f"Missing MUST: {result.missing_must}")
    print(f"Warnings: {result.warnings}")

    # Scenario 2: Missing contract fields
    print("\n--- Scenario 2: Missing operator/escalation (pre-V1.1 genesis) ---")
    old_genesis = {
        "soul_hash": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
        "model_hash": "f1e2d3c4b5a6f7e8d9c0b1a2f3e4d5c6",
        "genesis_hash": "0000000000000000",
        "schema_version": "1.0.0",
        "agent_id": "legacy_agent",
        "grader_id": "external_grader",
        "evidence_grade": "B",
        "correction_frequency": 0.15,
        "revocation_hash": "r1e2v3o4k5e6r7e8v9o0k1e2r3e4v5o6",
        "predecessor_hash": "p1r2e3d4e5c6e7s8s9o0r1p2r3e4d5e6",
        "anchor_type": "SELF_SIGNED",
        "minimum_audit_cadence": "48h",
        "ca_fingerprint": "c1a2f3i4n5g6e7r8p9r0i1n2t3c4a5f6",
        # NO operator_id, escalation_contact, revocation_endpoint
    }
    result2 = validate_genesis(old_genesis)
    print(f"Grade: {result2.grade} | Verdict: {result2.verdict}")
    print(f"Contract enforceable: {result2.contract_enforceable}")
    print(f"Missing MUST: {result2.missing_must}")
    print(f"Missing RECOMMENDED: {result2.missing_recommended}")

    # Scenario 3: Self-grading agent
    print("\n--- Scenario 3: Self-grading agent (axiom 1 violation) ---")
    self_grade = dict(full_genesis)
    self_grade["grader_id"] = "kit_fox"  # Same as agent_id
    result3 = validate_genesis(self_grade)
    print(f"Grade: {result3.grade} | Verdict: {result3.verdict}")
    print(f"Warnings: {result3.warnings}")

    # Scenario 4: Minimal sybil genesis
    print("\n--- Scenario 4: Sybil with 8 missing MUST fields ---")
    sybil = {
        "soul_hash": "abcdef",  # too short
        "agent_id": "sybil_001",
        "schema_version": "1.1.0",
        "evidence_grade": "A",
        "anchor_type": "SELF_SIGNED",
    }
    result4 = validate_genesis(sybil)
    print(f"Grade: {result4.grade} | Verdict: {result4.verdict}")
    print(f"Missing MUST ({len(result4.missing_must)}): {result4.missing_must}")
    print(f"Contract enforceable: {result4.contract_enforceable}")

    print("\n" + "=" * 60)
    print("Genesis = contract. Missing MUST = REJECT. Missing REC = DEGRADED.")
    print("Self-grading = axiom 1 violation. No escalation = unenforceable.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
