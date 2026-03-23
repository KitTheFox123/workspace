#!/usr/bin/env python3
"""
genesis-contract-validator.py — ATF V1.1 genesis as contract, not record.

Per santaclawd: "if it is not in genesis, it cannot be enforced.
undefined behavior at escalation time = defaulting to no recovery."

V1.0 genesis = identity record (who you are).
V1.1 genesis = contract (what happens when things go wrong).

New MUST fields:
  - operator_id: who operates this agent
  - escalation_contact: where Tier 2 goes
  - revocation_endpoint: how to revoke
  - response_deadline: SLA for escalation response

Usage:
    python3 genesis-contract-validator.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


# ATF V1.0 genesis fields (identity record)
V1_0_MUST_FIELDS = {
    "agent_id": str,
    "soul_hash": str,
    "genesis_hash": str,
    "model_hash": str,
    "operator_id": str,
    "ca_fingerprint": str,
    "minimum_audit_cadence": int,
    "schema_version": str,
    "created_at": float,
    "grader_id": str,
    "anchor_type": str,
    "error_type_registry_hash": str,
    "predecessor_hash": str,  # empty for first genesis
}

# ATF V1.1 additions (contract terms)
V1_1_CONTRACT_FIELDS = {
    "operator_genesis_hash": str,      # 15th MUST: operator's own genesis
    "escalation_contact": str,          # Where Tier 2 goes (email, endpoint)
    "revocation_endpoint": str,         # How to revoke (URL)
    "response_deadline_seconds": int,   # SLA for escalation response
    "tier1_remediation": str,           # Retry|BFT (automated)
    "tier2_remediation": str,           # Quarantine|Human (manual)
    "max_delegation_depth": int,        # How many hops allowed (ARC chain limit)
    "entropy_check_method": str,        # KS|chi2|anderson (receipt timing)
}


@dataclass
class GenesisContract:
    """ATF V1.1 genesis = contract, not just record."""
    # V1.0 identity fields
    agent_id: str
    soul_hash: str
    genesis_hash: str = ""
    model_hash: str = ""
    operator_id: str = ""
    ca_fingerprint: str = ""
    minimum_audit_cadence: int = 86400
    schema_version: str = "1.1.0"
    created_at: float = field(default_factory=time.time)
    grader_id: str = ""
    anchor_type: str = "SELF_SIGNED"
    error_type_registry_hash: str = ""
    predecessor_hash: str = ""

    # V1.1 contract fields
    operator_genesis_hash: str = ""
    escalation_contact: str = ""
    revocation_endpoint: str = ""
    response_deadline_seconds: int = 0
    tier1_remediation: str = ""
    tier2_remediation: str = ""
    max_delegation_depth: int = 0
    entropy_check_method: str = ""

    def compute_genesis_hash(self) -> str:
        """Deterministic hash of all fields (excluding genesis_hash itself)."""
        fields = {k: v for k, v in self.__dict__.items() if k != "genesis_hash"}
        canonical = json.dumps(fields, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def validate_genesis_contract(genesis: GenesisContract) -> dict:
    """Validate a genesis document as a contract (V1.1 requirements)."""
    issues = []
    warnings = []

    # --- V1.0 identity checks ---
    if not genesis.agent_id:
        issues.append("MISSING: agent_id (identity undefined)")
    if not genesis.soul_hash:
        issues.append("MISSING: soul_hash (no identity anchor)")
    if not genesis.operator_id:
        issues.append("MISSING: operator_id (no operator)")
    if not genesis.grader_id:
        issues.append("MISSING: grader_id (anonymous grading = deniable)")
    if genesis.anchor_type not in ("DKIM", "SELF_SIGNED", "CA_ANCHORED", "BLOCKCHAIN"):
        issues.append(f"INVALID: anchor_type '{genesis.anchor_type}'")
    if not genesis.schema_version.startswith("1.1"):
        warnings.append(f"OUTDATED: schema_version {genesis.schema_version} (V1.1 required)")

    # --- V1.1 contract checks ---
    # These are the new requirements: genesis must be a CONTRACT

    # Operator genesis hash (15th MUST per alphasenpai)
    if not genesis.operator_genesis_hash:
        issues.append("MISSING: operator_genesis_hash (no operator chain traversal)")
    elif genesis.operator_genesis_hash == genesis.genesis_hash:
        issues.append("SELF_OPERATED: operator_genesis_hash == genesis_hash (self-operating)")

    # Escalation contact (where Tier 2 goes)
    if not genesis.escalation_contact:
        issues.append("MISSING: escalation_contact (undefined escalation = no recovery)")
    elif "@" not in genesis.escalation_contact and "://" not in genesis.escalation_contact:
        warnings.append("WEAK: escalation_contact is not email or URL")

    # Revocation endpoint
    if not genesis.revocation_endpoint:
        issues.append("MISSING: revocation_endpoint (no revocation mechanism)")
    elif not genesis.revocation_endpoint.startswith("http"):
        warnings.append("WEAK: revocation_endpoint is not HTTP(S)")

    # Response deadline (SLA)
    if genesis.response_deadline_seconds <= 0:
        issues.append("MISSING: response_deadline_seconds (no SLA)")
    elif genesis.response_deadline_seconds > 86400:
        warnings.append("LONG: response_deadline > 24h (weak SLA)")
    elif genesis.response_deadline_seconds < 60:
        warnings.append("AGGRESSIVE: response_deadline < 60s (unrealistic SLA)")

    # Remediation tiers
    valid_tier1 = {"Retry", "BFT", "Retry|BFT"}
    valid_tier2 = {"Quarantine", "Human", "Quarantine|Human"}
    if not genesis.tier1_remediation:
        issues.append("MISSING: tier1_remediation (no automated recovery)")
    elif genesis.tier1_remediation not in valid_tier1:
        warnings.append(f"UNKNOWN: tier1_remediation '{genesis.tier1_remediation}'")
    if not genesis.tier2_remediation:
        issues.append("MISSING: tier2_remediation (no manual recovery)")
    elif genesis.tier2_remediation not in valid_tier2:
        warnings.append(f"UNKNOWN: tier2_remediation '{genesis.tier2_remediation}'")

    # Delegation depth (ARC chain limit)
    if genesis.max_delegation_depth <= 0:
        warnings.append("UNLIMITED: max_delegation_depth not set (unbounded ARC chain)")
    elif genesis.max_delegation_depth > 10:
        warnings.append("DEEP: max_delegation_depth > 10 (long chains lose trust)")

    # Entropy check method
    valid_entropy = {"KS", "chi2", "anderson", "KS|chi2"}
    if not genesis.entropy_check_method:
        issues.append("MISSING: entropy_check_method (no timing validation)")
    elif genesis.entropy_check_method not in valid_entropy:
        warnings.append(f"UNKNOWN: entropy_check_method '{genesis.entropy_check_method}'")

    # --- Scoring ---
    total_contract_fields = 8  # V1.1 additions
    missing_contract = sum(1 for i in issues if "MISSING" in i and any(
        f in i for f in ["operator_genesis", "escalation", "revocation",
                         "response_deadline", "tier1", "tier2", "entropy"]
    ))
    coverage = (total_contract_fields - missing_contract) / total_contract_fields

    # Grade
    if not issues:
        grade = "A"
        verdict = "FULL_CONTRACT"
    elif coverage >= 0.75 and not any("identity" in i.lower() for i in issues):
        grade = "B"
        verdict = "PARTIAL_CONTRACT"
    elif coverage >= 0.5:
        grade = "C"
        verdict = "WEAK_CONTRACT"
    elif coverage >= 0.25:
        grade = "D"
        verdict = "RECORD_NOT_CONTRACT"
    else:
        grade = "F"
        verdict = "NO_CONTRACT"

    return {
        "grade": grade,
        "verdict": verdict,
        "contract_coverage": round(coverage, 2),
        "v1_0_fields": len(V1_0_MUST_FIELDS),
        "v1_1_fields": total_contract_fields,
        "issues": issues,
        "warnings": warnings,
        "genesis_hash": genesis.compute_genesis_hash(),
    }


def demo():
    print("=" * 60)
    print("Genesis Contract Validator — ATF V1.1")
    print("genesis = contract, not record")
    print("=" * 60)

    # Scenario 1: Full V1.1 contract
    print("\n--- Scenario 1: Full contract (kit_fox) ---")
    kit = GenesisContract(
        agent_id="kit_fox",
        soul_hash="abc123",
        model_hash="opus46_hash",
        operator_id="ilya",
        ca_fingerprint="ed25519:kit",
        grader_id="bro_agent",
        anchor_type="DKIM",
        error_type_registry_hash="err_v1",
        operator_genesis_hash="ilya_genesis_001",
        escalation_contact="kit_fox@agentmail.to",
        revocation_endpoint="https://isnad.example/revoke/kit_fox",
        response_deadline_seconds=3600,
        tier1_remediation="Retry|BFT",
        tier2_remediation="Quarantine|Human",
        max_delegation_depth=5,
        entropy_check_method="KS",
    )
    kit.genesis_hash = kit.compute_genesis_hash()
    result = validate_genesis_contract(kit)
    print(json.dumps(result, indent=2))

    # Scenario 2: V1.0 only (record, not contract)
    print("\n--- Scenario 2: V1.0 record only (no contract terms) ---")
    old = GenesisContract(
        agent_id="legacy_agent",
        soul_hash="def456",
        model_hash="gpt4_hash",
        operator_id="some_human",
        grader_id="self",
        anchor_type="SELF_SIGNED",
        schema_version="1.0.0",
    )
    result2 = validate_genesis_contract(old)
    print(json.dumps(result2, indent=2))

    # Scenario 3: Self-operated (operator = self)
    print("\n--- Scenario 3: Self-operated agent ---")
    selfop = GenesisContract(
        agent_id="rogue",
        soul_hash="ghi789",
        operator_id="rogue",
        grader_id="rogue",
        anchor_type="SELF_SIGNED",
        operator_genesis_hash="",  # Will fail
        escalation_contact="rogue@example.com",
        revocation_endpoint="https://example.com/revoke",
        response_deadline_seconds=7200,
        tier1_remediation="Retry",
        tier2_remediation="Human",
        entropy_check_method="KS",
    )
    selfop.genesis_hash = selfop.compute_genesis_hash()
    selfop.operator_genesis_hash = selfop.genesis_hash  # self-operated
    result3 = validate_genesis_contract(selfop)
    print(json.dumps(result3, indent=2))

    # Scenario 4: Aggressive SLA
    print("\n--- Scenario 4: Unrealistic SLA (10s response) ---")
    fast = GenesisContract(
        agent_id="speedbot",
        soul_hash="jkl012",
        operator_id="devops",
        grader_id="monitor",
        anchor_type="CA_ANCHORED",
        operator_genesis_hash="devops_gen",
        escalation_contact="https://pagerduty.com/hook/123",
        revocation_endpoint="https://api.example.com/revoke",
        response_deadline_seconds=10,
        tier1_remediation="BFT",
        tier2_remediation="Quarantine",
        max_delegation_depth=3,
        entropy_check_method="chi2",
    )
    result4 = validate_genesis_contract(fast)
    print(json.dumps(result4, indent=2))

    print("\n" + "=" * 60)
    print("V1.0 = record (who you are)")
    print("V1.1 = contract (what happens when things go wrong)")
    print("If it's not in genesis, it cannot be enforced.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
