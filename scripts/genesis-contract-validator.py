#!/usr/bin/env python3
"""
genesis-contract-validator.py — ATF V1.1 genesis-as-contract validator.

Per santaclawd: "genesis document should be a contract, not just a record."
Validation at genesis time = enforcement at crisis time.

A genesis record says "I exist." A genesis contract says "here are my
obligations, and here's how to hold me accountable."

Contract fields (beyond ATF-core genesis):
  - operator_id: who is responsible
  - escalation_contact: reachable endpoint for disputes
  - revocation_endpoint: how to revoke if compromised
  - max_delegation_depth: how far trust can chain (ARC parallel)
  - sla_commitment: what the agent promises (response time, uptime)
  - governing_law: which dispute framework applies

Usage:
    python3 genesis-contract-validator.py
"""

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GenesisContract:
    """ATF V1.1 genesis contract — obligations, not just declarations."""
    # ATF-core genesis fields (MUST)
    agent_id: str
    soul_hash: str
    model_hash: str
    genesis_hash: str = ""  # computed
    schema_version: str = "ATF:1.1.0"

    # Contract fields (MUST for V1.1)
    operator_id: str = ""
    escalation_contact: str = ""  # email, URL, or agent_id
    revocation_endpoint: str = ""  # URL or protocol

    # Contract fields (SHOULD)
    max_delegation_depth: int = 3
    sla_response_seconds: int = 3600
    sla_uptime_percent: float = 95.0
    governing_framework: str = "ATF-core"  # ATF-core, PayLock, custom

    # Contract fields (RECOMMENDED)
    dispute_oracle: str = ""  # agent_id of preferred oracle
    audit_cadence_hours: int = 24
    error_taxonomy_version: str = "core:v1"

    def compute_genesis_hash(self) -> str:
        """Deterministic hash of all contract fields."""
        fields = [
            self.agent_id, self.soul_hash, self.model_hash,
            self.schema_version, self.operator_id,
            self.escalation_contact, self.revocation_endpoint,
            str(self.max_delegation_depth), str(self.sla_response_seconds),
            str(self.sla_uptime_percent), self.governing_framework,
        ]
        combined = "|".join(fields)
        self.genesis_hash = hashlib.sha256(combined.encode()).hexdigest()[:16]
        return self.genesis_hash


def _is_reachable_format(contact: str) -> bool:
    """Check if escalation contact is a plausibly reachable format."""
    if not contact:
        return False
    # Email
    if re.match(r'^[^@]+@[^@]+\.[^@]+$', contact):
        return True
    # URL
    if contact.startswith(('http://', 'https://')):
        return True
    # Agent ID format
    if contact.startswith('agent:') or contact.startswith('sh_agent_'):
        return True
    return False


def _is_valid_endpoint(endpoint: str) -> bool:
    """Check if revocation endpoint is structurally valid."""
    if not endpoint:
        return False
    if endpoint.startswith(('http://', 'https://')):
        return True
    if endpoint.startswith('dns:'):
        return True
    if endpoint.startswith('smtp:'):
        return True
    return False


def validate_genesis_contract(contract: GenesisContract) -> dict:
    """Validate a genesis contract against ATF V1.1 requirements."""
    issues = []
    warnings = []
    gates_passed = 0
    gates_total = 8

    # Gate 1: Core identity fields present
    if contract.agent_id and contract.soul_hash and contract.model_hash:
        gates_passed += 1
    else:
        missing = []
        if not contract.agent_id: missing.append("agent_id")
        if not contract.soul_hash: missing.append("soul_hash")
        if not contract.model_hash: missing.append("model_hash")
        issues.append(f"MISSING_IDENTITY: {', '.join(missing)}")

    # Gate 2: Schema version present and valid
    if contract.schema_version.startswith("ATF:"):
        gates_passed += 1
    else:
        issues.append("INVALID_SCHEMA_VERSION")

    # Gate 3: Operator identified (Axiom 2 — write-protection needs a principal)
    if contract.operator_id:
        gates_passed += 1
        if contract.operator_id == contract.agent_id:
            warnings.append("SELF_OPERATED: agent_id == operator_id (valid but noted)")
    else:
        issues.append("MISSING_OPERATOR: no principal for write-protection (Axiom 2)")

    # Gate 4: Escalation contact reachable
    if _is_reachable_format(contract.escalation_contact):
        gates_passed += 1
    else:
        issues.append("UNREACHABLE_ESCALATION: contact format not recognized")

    # Gate 5: Revocation endpoint valid
    if _is_valid_endpoint(contract.revocation_endpoint):
        gates_passed += 1
    else:
        issues.append("INVALID_REVOCATION: no valid revocation endpoint")

    # Gate 6: Delegation depth bounded
    if 1 <= contract.max_delegation_depth <= 10:
        gates_passed += 1
    else:
        issues.append(f"UNBOUNDED_DELEGATION: depth={contract.max_delegation_depth}")

    # Gate 7: SLA commitments plausible
    if contract.sla_response_seconds > 0 and 0 < contract.sla_uptime_percent <= 100:
        gates_passed += 1
        if contract.sla_uptime_percent > 99.99:
            warnings.append("UNREALISTIC_SLA: >99.99% uptime is unlikely for agents")
    else:
        issues.append("INVALID_SLA")

    # Gate 8: Genesis hash computable and deterministic
    h1 = contract.compute_genesis_hash()
    h2 = contract.compute_genesis_hash()
    if h1 == h2 and len(h1) == 16:
        gates_passed += 1
    else:
        issues.append("NONDETERMINISTIC_HASH")

    # Verdict
    if gates_passed == gates_total:
        grade = "A"
        verdict = "VALID_CONTRACT"
    elif gates_passed >= 6:
        grade = "B"
        verdict = "PARTIAL_CONTRACT"
    elif gates_passed >= 4:
        grade = "C"
        verdict = "INCOMPLETE_CONTRACT"
    elif gates_passed >= 2:
        grade = "D"
        verdict = "RECORD_NOT_CONTRACT"
    else:
        grade = "F"
        verdict = "INVALID"

    # Crisis readiness assessment
    crisis_ready = all([
        contract.operator_id,
        _is_reachable_format(contract.escalation_contact),
        _is_valid_endpoint(contract.revocation_endpoint),
    ])

    return {
        "verdict": verdict,
        "grade": grade,
        "gates_passed": gates_passed,
        "gates_total": gates_total,
        "genesis_hash": contract.genesis_hash,
        "crisis_ready": crisis_ready,
        "issues": issues,
        "warnings": warnings,
        "contract_summary": {
            "agent_id": contract.agent_id,
            "operator_id": contract.operator_id,
            "escalation": contract.escalation_contact,
            "revocation": contract.revocation_endpoint,
            "max_delegation": contract.max_delegation_depth,
            "sla": f"{contract.sla_uptime_percent}% / {contract.sla_response_seconds}s",
            "framework": contract.governing_framework,
        },
    }


def demo():
    print("=" * 60)
    print("Genesis Contract Validator — ATF V1.1")
    print("=" * 60)

    # Scenario 1: Full contract (kit_fox)
    print("\n--- Scenario 1: Full genesis contract ---")
    kit = GenesisContract(
        agent_id="kit_fox",
        soul_hash="abc123def456",
        model_hash="opus-4-6-hash",
        operator_id="ilya",
        escalation_contact="kit_fox@agentmail.to",
        revocation_endpoint="https://api.agentmail.to/v0/revoke/kit_fox",
        max_delegation_depth=3,
        sla_response_seconds=1800,
        sla_uptime_percent=95.0,
        governing_framework="ATF-core",
        dispute_oracle="bro_agent",
        audit_cadence_hours=24,
    )
    print(json.dumps(validate_genesis_contract(kit), indent=2))

    # Scenario 2: Record, not contract (missing accountability)
    print("\n--- Scenario 2: Genesis record (no contract fields) ---")
    record_only = GenesisContract(
        agent_id="anonymous_bot",
        soul_hash="xyz789",
        model_hash="gpt4-hash",
    )
    print(json.dumps(validate_genesis_contract(record_only), indent=2))

    # Scenario 3: Self-operated agent
    print("\n--- Scenario 3: Self-operated (agent == operator) ---")
    self_op = GenesisContract(
        agent_id="autonomous_agent",
        soul_hash="self001",
        model_hash="claude-hash",
        operator_id="autonomous_agent",  # self-operated
        escalation_contact="autonomous_agent@agentmail.to",
        revocation_endpoint="https://example.com/revoke",
        max_delegation_depth=1,
        sla_response_seconds=3600,
        sla_uptime_percent=90.0,
    )
    print(json.dumps(validate_genesis_contract(self_op), indent=2))

    # Scenario 4: Unrealistic SLA
    print("\n--- Scenario 4: Unrealistic SLA claims ---")
    unrealistic = GenesisContract(
        agent_id="hype_agent",
        soul_hash="hype001",
        model_hash="gpt5-hash",
        operator_id="startup_inc",
        escalation_contact="support@startup.ai",
        revocation_endpoint="https://startup.ai/revoke",
        sla_uptime_percent=99.999,
        sla_response_seconds=1,
    )
    print(json.dumps(validate_genesis_contract(unrealistic), indent=2))

    # Scenario 5: Unbounded delegation
    print("\n--- Scenario 5: Unbounded delegation depth ---")
    unbounded = GenesisContract(
        agent_id="delegator",
        soul_hash="del001",
        model_hash="model-hash",
        operator_id="corp",
        escalation_contact="ops@corp.ai",
        revocation_endpoint="https://corp.ai/revoke",
        max_delegation_depth=100,  # too deep
    )
    print(json.dumps(validate_genesis_contract(unbounded), indent=2))

    print("\n" + "=" * 60)
    print("Genesis = starting state. Contract = obligations.")
    print("Validation at genesis = enforcement at crisis.")
    print("Crisis readiness: operator + escalation + revocation.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
