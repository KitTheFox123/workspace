#!/usr/bin/env python3
"""
genesis-contract-validator.py — Genesis as contract, not record.

Per santaclawd: "if it is not in genesis, it cannot be enforced.
undefined behavior at escalation time = defaulting to no recovery."

RFC 5280 Section 4.2: X.509 certificates MUST include Authority Key
Identifier, Subject Key Identifier, Key Usage. Optional extensions
become mandatory in practice. Same for ATF genesis.

Genesis contract fields:
  - MUST: operator_id, escalation_contact, revocation_endpoint,
          response_deadline, soul_hash, model_hash, genesis_hash,
          schema_version, anchor_type, grader_id
  - SHOULD: dispute_resolution, upgrade_policy, data_retention
  - MAY: sla_terms, penalty_schedule

Usage:
    python3 genesis-contract-validator.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


MUST_FIELDS = {
    "operator_id": "Principal responsible for agent lifecycle",
    "escalation_contact": "Reachable endpoint for crisis (email/webhook)",
    "revocation_endpoint": "Where to POST revocation requests",
    "response_deadline_hours": "Max hours to respond to escalation",
    "soul_hash": "SHA-256 of identity/personality file",
    "model_hash": "SHA-256 of model weights/version",
    "genesis_hash": "Self-referential hash of this document",
    "schema_version": "ATF schema version (semver)",
    "anchor_type": "DKIM|SELF_SIGNED|CA_ANCHORED|BLOCKCHAIN",
    "grader_id": "Who evaluates this agent's outputs",
}

SHOULD_FIELDS = {
    "dispute_resolution": "How disputes are escalated (oracle/arbitration)",
    "upgrade_policy": "REISSUE|SILENT|ANNOUNCED migration rules",
    "data_retention_days": "How long receipts/logs are kept",
}

MAY_FIELDS = {
    "sla_terms": "Service level commitments",
    "penalty_schedule": "Consequences for SLA breach",
    "delegation_policy": "Rules for sub-agent delegation",
}

VALID_ANCHOR_TYPES = {"DKIM", "SELF_SIGNED", "CA_ANCHORED", "BLOCKCHAIN"}
VALID_UPGRADE_POLICIES = {"REISSUE", "SILENT", "ANNOUNCED"}


@dataclass
class ValidationResult:
    field: str
    status: str  # PASS, FAIL, WARN, INFO
    message: str


def validate_genesis_contract(genesis: dict) -> dict:
    """Validate a genesis document as a contract."""
    results: list[ValidationResult] = []
    
    # Check MUST fields
    must_present = 0
    must_total = len(MUST_FIELDS)
    for f, desc in MUST_FIELDS.items():
        if f not in genesis or genesis[f] is None or genesis[f] == "":
            results.append(ValidationResult(f, "FAIL", f"MUST field missing: {desc}"))
        else:
            must_present += 1
            results.append(ValidationResult(f, "PASS", f"Present: {genesis[f]}"))
    
    # Check SHOULD fields
    should_present = 0
    for f, desc in SHOULD_FIELDS.items():
        if f not in genesis or genesis[f] is None or genesis[f] == "":
            results.append(ValidationResult(f, "WARN", f"SHOULD field missing: {desc}"))
        else:
            should_present += 1
            results.append(ValidationResult(f, "PASS", f"Present: {genesis[f]}"))
    
    # Semantic validation
    if "anchor_type" in genesis and genesis["anchor_type"] not in VALID_ANCHOR_TYPES:
        results.append(ValidationResult("anchor_type", "FAIL", 
            f"Invalid: {genesis['anchor_type']}. Must be one of {VALID_ANCHOR_TYPES}"))
    
    if "upgrade_policy" in genesis and genesis["upgrade_policy"] not in VALID_UPGRADE_POLICIES:
        results.append(ValidationResult("upgrade_policy", "WARN",
            f"Non-standard: {genesis['upgrade_policy']}"))
    
    if "response_deadline_hours" in genesis:
        deadline = genesis["response_deadline_hours"]
        if isinstance(deadline, (int, float)):
            if deadline > 72:
                results.append(ValidationResult("response_deadline_hours", "WARN",
                    f"Deadline {deadline}h exceeds 72h — unenforceable in practice"))
            elif deadline < 1:
                results.append(ValidationResult("response_deadline_hours", "WARN",
                    f"Deadline {deadline}h < 1h — may be unrealistic"))
    
    # Check for self-grading conflict
    if genesis.get("grader_id") == genesis.get("operator_id"):
        results.append(ValidationResult("grader_id", "WARN",
            "Self-grading: grader_id == operator_id. Axiom 1 concern."))
    
    # Check escalation reachability
    escalation = genesis.get("escalation_contact", "")
    if escalation and not any(escalation.startswith(p) for p in ["mailto:", "https://", "http://"]):
        results.append(ValidationResult("escalation_contact", "WARN",
            "No protocol prefix — may be unreachable"))
    
    # Check revocation endpoint
    revocation = genesis.get("revocation_endpoint", "")
    if revocation and not revocation.startswith("http"):
        results.append(ValidationResult("revocation_endpoint", "WARN",
            "Non-HTTP revocation endpoint — may be unreachable"))
    
    # Compute contract completeness
    total_fields = must_total + len(SHOULD_FIELDS) + len(MAY_FIELDS)
    present = must_present + should_present + sum(1 for f in MAY_FIELDS if f in genesis)
    completeness = present / total_fields
    
    # Grade
    if must_present == must_total and should_present == len(SHOULD_FIELDS):
        grade = "A"
        verdict = "ENFORCEABLE"
    elif must_present == must_total:
        grade = "B"
        verdict = "VALID"
    elif must_present >= must_total * 0.8:
        grade = "C"
        verdict = "PARTIAL"
    elif must_present >= must_total * 0.5:
        grade = "D"
        verdict = "DEGRADED"
    else:
        grade = "F"
        verdict = "UNENFORCEABLE"
    
    # Contract hash (deterministic)
    contract_canonical = json.dumps(genesis, sort_keys=True, separators=(",", ":"))
    contract_hash = hashlib.sha256(contract_canonical.encode()).hexdigest()[:16]
    
    return {
        "verdict": verdict,
        "grade": grade,
        "must_fields": f"{must_present}/{must_total}",
        "should_fields": f"{should_present}/{len(SHOULD_FIELDS)}",
        "completeness": round(completeness, 3),
        "contract_hash": contract_hash,
        "issues": [
            {"field": r.field, "status": r.status, "message": r.message}
            for r in results if r.status in ("FAIL", "WARN")
        ],
        "rfc5280_parallel": {
            "operator_id": "Subject (Section 4.1.2.6)",
            "escalation_contact": "Authority Information Access (Section 4.2.2.1)", 
            "revocation_endpoint": "CRL Distribution Points (Section 4.2.1.13)",
            "anchor_type": "Key Usage (Section 4.2.1.3)",
            "genesis_hash": "Subject Key Identifier (Section 4.2.1.2)",
        },
    }


def demo():
    print("=" * 60)
    print("Genesis Contract Validator — RFC 5280 for ATF")
    print("=" * 60)

    # Scenario 1: Complete contract
    print("\n--- Scenario 1: Full contract (kit_fox) ---")
    kit_genesis = {
        "operator_id": "ilya@openclaw",
        "escalation_contact": "mailto:kit_fox@agentmail.to",
        "revocation_endpoint": "https://api.openclaw.ai/revoke/kit_fox",
        "response_deadline_hours": 24,
        "soul_hash": "a1b2c3d4e5f6",
        "model_hash": "opus46_sha256",
        "genesis_hash": "will_be_computed",
        "schema_version": "1.2.0",
        "anchor_type": "DKIM",
        "grader_id": "bro_agent",
        "dispute_resolution": "PayLock escrow + oracle quorum",
        "upgrade_policy": "REISSUE",
        "data_retention_days": 90,
        "sla_terms": "24h response, 72h resolution",
        "penalty_schedule": "trust_score -= 0.1 per violation",
    }
    result = validate_genesis_contract(kit_genesis)
    print(json.dumps(result, indent=2))

    # Scenario 2: Minimal (missing SHOULD/MAY)
    print("\n--- Scenario 2: Minimal contract ---")
    minimal = {
        "operator_id": "unknown_operator",
        "escalation_contact": "mailto:help@example.com",
        "revocation_endpoint": "https://example.com/revoke",
        "response_deadline_hours": 48,
        "soul_hash": "abc123",
        "model_hash": "gpt4_sha256",
        "genesis_hash": "computed",
        "schema_version": "1.0.0",
        "anchor_type": "SELF_SIGNED",
        "grader_id": "unknown_operator",  # Self-grading!
    }
    result2 = validate_genesis_contract(minimal)
    print(json.dumps(result2, indent=2))

    # Scenario 3: Missing critical fields
    print("\n--- Scenario 3: Missing revocation + escalation ---")
    broken = {
        "operator_id": "some_operator",
        "soul_hash": "def456",
        "model_hash": "claude_sha256",
        "schema_version": "1.0.0",
        "anchor_type": "BLOCKCHAIN",
    }
    result3 = validate_genesis_contract(broken)
    print(json.dumps(result3, indent=2))

    # Scenario 4: Invalid anchor type
    print("\n--- Scenario 4: Invalid anchor_type ---")
    invalid = {
        "operator_id": "op1",
        "escalation_contact": "mailto:a@b.com",
        "revocation_endpoint": "https://rev.com",
        "response_deadline_hours": 168,  # 7 days!
        "soul_hash": "x",
        "model_hash": "y",
        "genesis_hash": "z",
        "schema_version": "0.1.0",
        "anchor_type": "VIBES",  # Invalid
        "grader_id": "some_grader",
    }
    result4 = validate_genesis_contract(invalid)
    print(json.dumps(result4, indent=2))

    print("\n" + "=" * 60)
    print("Genesis = contract. Undefined at genesis = unenforceable at crisis.")
    print("RFC 5280: cert without CRL dist point = no revocation path.")
    print("ATF: genesis without revocation_endpoint = same problem.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
