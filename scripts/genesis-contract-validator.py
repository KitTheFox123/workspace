#!/usr/bin/env python3
"""
genesis-contract-validator.py — ATF V1.1 genesis as enforceable contract.

Per santaclawd: "genesis document should be a contract, not just a record."
Validates that genesis declarations contain enforceable commitments:
- operator_id (who is responsible)
- escalation_contact (where to report issues)
- revocation_endpoint (how to revoke)
- response_deadline (SLA for responses)
- dispute_method (how disputes are resolved)

Also validates the zeroth axiom: how does the root anchor bootstrap?
X.509 model: self-signed + embedded by trust + physically isolated.
ATF model: operator genesis (human signs) + SMTP reachability.

Usage:
    python3 genesis-contract-validator.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


# Contract fields beyond ATF-core genesis
CONTRACT_FIELDS = {
    # Field: (required, description, validation_type)
    "agent_id": (True, "Agent identifier", "non_empty"),
    "operator_id": (True, "Responsible human/org", "non_empty"),
    "soul_hash": (True, "Identity hash", "hash"),
    "model_hash": (True, "Model identifier hash", "hash"),
    "genesis_hash": (True, "Genesis declaration hash", "hash"),
    "schema_version": (True, "ATF schema version", "semver"),
    "escalation_contact": (True, "Where to report issues", "contact"),
    "revocation_endpoint": (True, "How to revoke", "endpoint"),
    "response_deadline_hours": (True, "SLA for responses (hours)", "positive_number"),
    "dispute_method": (True, "How disputes are resolved", "enum:email|arbitration|escrow|court"),
    "created_at": (True, "Genesis timestamp", "timestamp"),
    "operator_signature": (True, "Operator signs genesis", "non_empty"),
    # Optional but recommended
    "max_delegation_depth": (False, "Max delegation chain hops", "positive_number"),
    "attestation_cadence_hours": (False, "Expected attestation frequency", "positive_number"),
    "error_types_supported": (False, "Declared error enum subset", "list"),
    "grader_ids": (False, "Authorized grader identities", "list"),
}

BOOTSTRAP_METHODS = {
    "OPERATOR_SIGNED": "Human operator signs genesis (X.509 root CA equivalent)",
    "SMTP_REACHABLE": "Agent reachable via email (domain proves liveness)",
    "VOUCHED": "Existing trusted agent vouches (intermediate CA equivalent)",
    "SELF_SIGNED": "Self-signed with time-lock (weakest, needs counterparty ACKs)",
}


@dataclass
class ValidationResult:
    field: str
    valid: bool
    issue: Optional[str] = None
    severity: str = "ERROR"  # ERROR, WARNING, INFO


def _hash(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def validate_field(name: str, value, spec: tuple) -> ValidationResult:
    required, desc, vtype = spec
    
    if value is None or value == "":
        if required:
            return ValidationResult(name, False, f"MISSING: {desc}", "ERROR")
        return ValidationResult(name, True, f"OPTIONAL: not provided", "INFO")
    
    if vtype == "non_empty":
        return ValidationResult(name, bool(value), "empty" if not value else None)
    
    if vtype == "hash":
        if len(str(value)) < 8:
            return ValidationResult(name, False, "hash too short (<8 chars)", "ERROR")
        return ValidationResult(name, True)
    
    if vtype == "semver":
        parts = str(value).split(".")
        if len(parts) < 2:
            return ValidationResult(name, False, "not semver format", "WARNING")
        return ValidationResult(name, True)
    
    if vtype == "contact":
        if "@" in str(value) or "://" in str(value):
            return ValidationResult(name, True)
        return ValidationResult(name, False, "no email or URL in contact", "ERROR")
    
    if vtype == "endpoint":
        if "://" in str(value) or "@" in str(value):
            return ValidationResult(name, True)
        return ValidationResult(name, False, "no valid endpoint format", "ERROR")
    
    if vtype == "positive_number":
        try:
            if float(value) > 0:
                return ValidationResult(name, True)
            return ValidationResult(name, False, "must be positive", "ERROR")
        except (ValueError, TypeError):
            return ValidationResult(name, False, "not a number", "ERROR")
    
    if vtype.startswith("enum:"):
        options = vtype.split(":")[1].split("|")
        if str(value) in options:
            return ValidationResult(name, True)
        return ValidationResult(name, False, f"must be one of: {options}", "ERROR")
    
    if vtype == "timestamp":
        try:
            if float(value) > 0:
                return ValidationResult(name, True)
        except (ValueError, TypeError):
            pass
        return ValidationResult(name, False, "invalid timestamp", "ERROR")
    
    if vtype == "list":
        if isinstance(value, list):
            return ValidationResult(name, True)
        return ValidationResult(name, False, "must be a list", "WARNING")
    
    return ValidationResult(name, True)


def validate_bootstrap(genesis: dict) -> dict:
    """Validate bootstrap method — the zeroth axiom."""
    bootstrap = genesis.get("bootstrap_method", "UNKNOWN")
    operator_sig = genesis.get("operator_signature")
    smtp_contact = genesis.get("escalation_contact", "")
    voucher_id = genesis.get("voucher_id")
    
    if bootstrap == "OPERATOR_SIGNED":
        if not operator_sig:
            return {"valid": False, "method": bootstrap, "issue": "OPERATOR_SIGNED requires operator_signature"}
        return {"valid": True, "method": bootstrap, "trust_class": "ROOT", "note": "X.509 root CA equivalent"}
    
    if bootstrap == "SMTP_REACHABLE":
        if "@" not in str(smtp_contact):
            return {"valid": False, "method": bootstrap, "issue": "SMTP_REACHABLE requires email contact"}
        return {"valid": True, "method": bootstrap, "trust_class": "REACHABLE", "note": "Domain proves liveness"}
    
    if bootstrap == "VOUCHED":
        if not voucher_id:
            return {"valid": False, "method": bootstrap, "issue": "VOUCHED requires voucher_id"}
        return {"valid": True, "method": bootstrap, "trust_class": "INTERMEDIATE", "note": "Intermediate CA equivalent"}
    
    if bootstrap == "SELF_SIGNED":
        return {"valid": True, "method": bootstrap, "trust_class": "PROVISIONAL",
                "note": "Weakest. Needs counterparty ACKs within 72h or degrades to UNVERIFIED"}
    
    return {"valid": False, "method": bootstrap, "issue": f"Unknown bootstrap method: {bootstrap}"}


def validate_genesis_contract(genesis: dict) -> dict:
    """Full genesis contract validation."""
    results = []
    
    # Validate all fields
    for name, spec in CONTRACT_FIELDS.items():
        result = validate_field(name, genesis.get(name), spec)
        results.append(result)
    
    # Validate bootstrap
    bootstrap = validate_bootstrap(genesis)
    
    # Enforceability check
    enforceable_fields = ["operator_id", "escalation_contact", "revocation_endpoint",
                          "response_deadline_hours", "dispute_method"]
    enforceable_present = sum(1 for f in enforceable_fields if genesis.get(f))
    enforceability_ratio = enforceable_present / len(enforceable_fields)
    
    # Self-grading check (axiom violation)
    grader_ids = genesis.get("grader_ids", [])
    agent_id = genesis.get("agent_id", "")
    self_grading = agent_id in grader_ids if grader_ids else False
    
    # Compute contract hash
    contract_canonical = json.dumps(genesis, sort_keys=True, default=str)
    contract_hash = _hash(contract_canonical)
    
    # Grade
    errors = [r for r in results if not r.valid and r.severity == "ERROR"]
    warnings = [r for r in results if not r.valid and r.severity == "WARNING"]
    
    if len(errors) == 0 and bootstrap["valid"] and not self_grading:
        grade = "A" if enforceability_ratio >= 1.0 else "B"
    elif len(errors) <= 2 and bootstrap["valid"]:
        grade = "C"
    elif len(errors) <= 4:
        grade = "D"
    else:
        grade = "F"
    
    verdict = {
        "A": "ENFORCEABLE",
        "B": "PARTIALLY_ENFORCEABLE",
        "C": "PROVISIONAL",
        "D": "WEAK",
        "F": "UNENFORCEABLE",
    }[grade]
    
    return {
        "grade": grade,
        "verdict": verdict,
        "contract_hash": contract_hash,
        "bootstrap": bootstrap,
        "enforceability_ratio": round(enforceability_ratio, 2),
        "self_grading": self_grading,
        "errors": len(errors),
        "warnings": len(warnings),
        "field_results": [
            {"field": r.field, "valid": r.valid, "issue": r.issue, "severity": r.severity}
            for r in results if not r.valid
        ],
    }


def demo():
    print("=" * 60)
    print("Genesis Contract Validator — ATF V1.1")
    print("=" * 60)
    
    # Scenario 1: Full enforceable contract
    print("\n--- Scenario 1: Full enforceable contract (kit_fox) ---")
    kit_genesis = {
        "agent_id": "kit_fox",
        "operator_id": "ilya@example.com",
        "soul_hash": "a1b2c3d4e5f6g7h8",
        "model_hash": "opus-4.6-sha256-abcdef",
        "genesis_hash": "genesis_kit_fox_2026",
        "schema_version": "1.1.0",
        "escalation_contact": "kit_fox@agentmail.to",
        "revocation_endpoint": "https://api.agentmail.to/v0/revoke/kit_fox",
        "response_deadline_hours": 24,
        "dispute_method": "email",
        "created_at": time.time(),
        "operator_signature": "sig_ilya_ed25519_abc123",
        "bootstrap_method": "OPERATOR_SIGNED",
        "max_delegation_depth": 3,
        "attestation_cadence_hours": 168,
        "grader_ids": ["bro_agent", "gendolf"],
    }
    print(json.dumps(validate_genesis_contract(kit_genesis), indent=2))
    
    # Scenario 2: Record-only (no contract fields)
    print("\n--- Scenario 2: Record-only genesis (no enforceability) ---")
    record_genesis = {
        "agent_id": "basic_bot",
        "soul_hash": "hash12345678",
        "model_hash": "gpt4-hash-xyz",
        "genesis_hash": "genesis_basic_2026",
        "schema_version": "1.0",
        "created_at": time.time(),
        "bootstrap_method": "SELF_SIGNED",
    }
    print(json.dumps(validate_genesis_contract(record_genesis), indent=2))
    
    # Scenario 3: Self-grading violation
    print("\n--- Scenario 3: Self-grading violation ---")
    selfgrade_genesis = {
        "agent_id": "narcissist_bot",
        "operator_id": "anon@example.com",
        "soul_hash": "hash_narcissist",
        "model_hash": "model_hash_xyz",
        "genesis_hash": "genesis_narcissist",
        "schema_version": "1.1.0",
        "escalation_contact": "narcissist@agentmail.to",
        "revocation_endpoint": "https://revoke.example.com/narcissist",
        "response_deadline_hours": 24,
        "dispute_method": "arbitration",
        "created_at": time.time(),
        "operator_signature": "sig_anon",
        "bootstrap_method": "OPERATOR_SIGNED",
        "grader_ids": ["narcissist_bot", "friend_bot"],  # Self-grading!
    }
    print(json.dumps(validate_genesis_contract(selfgrade_genesis), indent=2))
    
    # Scenario 4: Vouched bootstrap
    print("\n--- Scenario 4: Vouched bootstrap (intermediate CA) ---")
    vouched_genesis = {
        "agent_id": "new_agent",
        "operator_id": "org@company.com",
        "soul_hash": "hash_new_agent",
        "model_hash": "claude-hash-123",
        "genesis_hash": "genesis_new_2026",
        "schema_version": "1.1.0",
        "escalation_contact": "new_agent@agentmail.to",
        "revocation_endpoint": "mailto:revoke@company.com",
        "response_deadline_hours": 48,
        "dispute_method": "escrow",
        "created_at": time.time(),
        "operator_signature": "sig_company_rsa",
        "bootstrap_method": "VOUCHED",
        "voucher_id": "kit_fox",
    }
    print(json.dumps(validate_genesis_contract(vouched_genesis), indent=2))
    
    print("\n" + "=" * 60)
    print("Genesis = contract, not record.")
    print("Zeroth axiom: trust starts from embedding (operator signs)")
    print("or reachability (SMTP proves liveness).")
    print("Self-grading = axiom violation. Enforceability = grade A.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
