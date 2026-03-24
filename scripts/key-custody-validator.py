#!/usr/bin/env python3
"""
key-custody-validator.py — Key custody model validator for ATF genesis.

Per santaclawd: "who holds the signing key = who vouches for the agent."
DKIM RFC 6376 solved this with selector mechanism.

Three custody models:
  OPERATOR_HELD  — Provider signs on behalf of agent (ESP model, centralized)
  AGENT_HELD     — Agent controls own key (autonomous but TOFU risk)
  HSM_MANAGED    — Hardware security module (strongest, requires infra)

Genesis MUST declare key_custodian_type. Revocation differs per type.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CustodyType(Enum):
    OPERATOR_HELD = "OPERATOR_HELD"    # ESP/provider model
    AGENT_HELD = "AGENT_HELD"          # Autonomous key control
    HSM_MANAGED = "HSM_MANAGED"        # Hardware security module
    DELEGATED = "DELEGATED"            # Sub-delegation (intermediate)
    UNDECLARED = "UNDECLARED"           # Gap in genesis


class RevocationPath(Enum):
    OPERATOR_REVOKE = "OPERATOR_REVOKE"      # Operator revokes signing authority
    KEY_ROTATION = "KEY_ROTATION"            # Agent rotates own key
    HSM_CEREMONY = "HSM_CEREMONY"            # Formal key ceremony required
    EMERGENCY_REVOKE = "EMERGENCY_REVOKE"    # Compromise response
    SELECTOR_DEPRECATE = "SELECTOR_DEPRECATE"  # DKIM-style selector rotation


# SPEC_CONSTANTS
CUSTODY_FIELDS_REQUIRED = [
    "key_custodian_type",
    "key_custody_operator_id",    # WHO holds the key
    "key_rotation_policy",         # HOW OFTEN
    "revocation_endpoint",         # WHERE to check
    "custody_attestation_hash",    # PROOF of custody declaration
]

ROTATION_POLICIES = {
    "OPERATOR_HELD": {"max_lifetime_days": 365, "recommended_days": 90},
    "AGENT_HELD": {"max_lifetime_days": 180, "recommended_days": 30},
    "HSM_MANAGED": {"max_lifetime_days": 730, "recommended_days": 365},
    "DELEGATED": {"max_lifetime_days": 90, "recommended_days": 30},
}


@dataclass
class GenesisKeyCustody:
    agent_id: str
    key_custodian_type: str
    key_custody_operator_id: Optional[str] = None
    key_rotation_policy_days: int = 90
    revocation_endpoint: Optional[str] = None
    key_algorithm: str = "Ed25519"
    selector: Optional[str] = None  # DKIM-style selector
    custody_attestation_hash: Optional[str] = None
    hsm_vendor: Optional[str] = None
    delegation_chain: list = field(default_factory=list)


@dataclass
class CustodyAuditResult:
    agent_id: str
    custody_type: str
    grade: str  # A-F
    issues: list
    revocation_path: str
    key_lifetime_status: str
    dkim_parallel: str


def validate_custody(genesis: GenesisKeyCustody) -> CustodyAuditResult:
    """Validate key custody declaration in genesis."""
    issues = []
    grade_penalties = 0
    
    # 1. Custody type declared?
    try:
        custody = CustodyType(genesis.key_custodian_type)
    except ValueError:
        custody = CustodyType.UNDECLARED
        issues.append("CRITICAL: key_custodian_type not declared or invalid")
        grade_penalties += 3
    
    # 2. Operator ID for OPERATOR_HELD/DELEGATED
    if custody in (CustodyType.OPERATOR_HELD, CustodyType.DELEGATED):
        if not genesis.key_custody_operator_id:
            issues.append("CRITICAL: OPERATOR_HELD/DELEGATED requires key_custody_operator_id")
            grade_penalties += 2
    
    # 3. Self-custody check (agent_id == operator_id = self-attestation risk)
    if (genesis.key_custodian_type == "OPERATOR_HELD" and 
        genesis.key_custody_operator_id == genesis.agent_id):
        issues.append("WARNING: self-custody declared as OPERATOR_HELD (axiom 1 tension)")
        grade_penalties += 1
    
    # 4. Rotation policy
    if custody != CustodyType.UNDECLARED:
        policy = ROTATION_POLICIES.get(genesis.key_custodian_type, {})
        max_days = policy.get("max_lifetime_days", 365)
        rec_days = policy.get("recommended_days", 90)
        
        if genesis.key_rotation_policy_days > max_days:
            issues.append(f"CRITICAL: rotation {genesis.key_rotation_policy_days}d exceeds max {max_days}d for {custody.value}")
            grade_penalties += 2
        elif genesis.key_rotation_policy_days > rec_days:
            issues.append(f"WARNING: rotation {genesis.key_rotation_policy_days}d exceeds recommended {rec_days}d")
            grade_penalties += 1
    
    # 5. Revocation endpoint
    if not genesis.revocation_endpoint:
        issues.append("CRITICAL: no revocation_endpoint (cert without CRL DP)")
        grade_penalties += 2
    
    # 6. Custody attestation
    if not genesis.custody_attestation_hash:
        issues.append("WARNING: no custody_attestation_hash (unverifiable custody claim)")
        grade_penalties += 1
    
    # 7. DKIM selector (enables key rotation without genesis change)
    if not genesis.selector:
        issues.append("INFO: no selector (DKIM-style key rotation not available)")
    
    # 8. HSM-specific checks
    if custody == CustodyType.HSM_MANAGED and not genesis.hsm_vendor:
        issues.append("WARNING: HSM_MANAGED without hsm_vendor declaration")
        grade_penalties += 1
    
    # 9. Delegation chain validation
    if custody == CustodyType.DELEGATED:
        if not genesis.delegation_chain:
            issues.append("CRITICAL: DELEGATED custody without delegation_chain")
            grade_penalties += 2
        elif len(genesis.delegation_chain) > 3:
            issues.append(f"WARNING: delegation chain depth {len(genesis.delegation_chain)} exceeds recommended max 3")
            grade_penalties += 1
    
    # Determine revocation path
    revocation_map = {
        CustodyType.OPERATOR_HELD: RevocationPath.OPERATOR_REVOKE,
        CustodyType.AGENT_HELD: RevocationPath.KEY_ROTATION,
        CustodyType.HSM_MANAGED: RevocationPath.HSM_CEREMONY,
        CustodyType.DELEGATED: RevocationPath.OPERATOR_REVOKE,
        CustodyType.UNDECLARED: RevocationPath.EMERGENCY_REVOKE,
    }
    
    # DKIM parallel
    dkim_parallels = {
        CustodyType.OPERATOR_HELD: "ESP signs on behalf of domain (Google/Microsoft model)",
        CustodyType.AGENT_HELD: "Domain owner manages own DKIM keys",
        CustodyType.HSM_MANAGED: "Enterprise with dedicated signing infrastructure",
        CustodyType.DELEGATED: "Third-party signing service with selector delegation",
        CustodyType.UNDECLARED: "No DKIM = no sender verification",
    }
    
    # Grade
    grades = ["A", "B", "C", "D", "F"]
    grade_idx = min(grade_penalties, 4)
    
    return CustodyAuditResult(
        agent_id=genesis.agent_id,
        custody_type=custody.value,
        grade=grades[grade_idx],
        issues=issues,
        revocation_path=revocation_map[custody].value,
        key_lifetime_status="COMPLIANT" if grade_penalties < 2 else "NON_COMPLIANT",
        dkim_parallel=dkim_parallels[custody]
    )


# === Scenarios ===

def run_scenarios():
    scenarios = [
        ("Kit (operator-held, compliant)", GenesisKeyCustody(
            agent_id="kit_fox",
            key_custodian_type="OPERATOR_HELD",
            key_custody_operator_id="ilya_operator",
            key_rotation_policy_days=90,
            revocation_endpoint="https://atf.example/revoke/kit_fox",
            selector="kit2026q1",
            custody_attestation_hash="abc123def456",
        )),
        ("Anonymous bot (undeclared custody)", GenesisKeyCustody(
            agent_id="anon_bot",
            key_custodian_type="UNDECLARED",
        )),
        ("Self-custody pretending to be operator-held", GenesisKeyCustody(
            agent_id="sneaky_agent",
            key_custodian_type="OPERATOR_HELD",
            key_custody_operator_id="sneaky_agent",  # self!
            key_rotation_policy_days=90,
            revocation_endpoint="https://atf.example/revoke/sneaky",
        )),
        ("HSM-managed enterprise agent", GenesisKeyCustody(
            agent_id="enterprise_bot",
            key_custodian_type="HSM_MANAGED",
            key_custody_operator_id="acme_corp",
            key_rotation_policy_days=365,
            revocation_endpoint="https://acme.example/atf/revoke",
            hsm_vendor="Thales Luna",
            selector="enterprise2026",
            custody_attestation_hash="hsm_attestation_789",
        )),
        ("Delegated with deep chain", GenesisKeyCustody(
            agent_id="subagent_deep",
            key_custodian_type="DELEGATED",
            key_custody_operator_id="parent_agent",
            key_rotation_policy_days=30,
            revocation_endpoint="https://atf.example/revoke/sub",
            delegation_chain=["root_op", "mid_agent", "parent_agent", "subagent_deep"],
        )),
        ("Agent-held, long rotation", GenesisKeyCustody(
            agent_id="lazy_agent",
            key_custodian_type="AGENT_HELD",
            key_rotation_policy_days=365,  # Too long for agent-held
            revocation_endpoint="https://atf.example/revoke/lazy",
        )),
    ]
    
    for name, genesis in scenarios:
        result = validate_custody(genesis)
        print(f"=== {name} ===")
        print(f"  Custody: {result.custody_type}")
        print(f"  Grade: {result.grade}")
        print(f"  Revocation: {result.revocation_path}")
        print(f"  DKIM parallel: {result.dkim_parallel}")
        print(f"  Status: {result.key_lifetime_status}")
        for issue in result.issues:
            print(f"  ⚠ {issue}")
        print()


if __name__ == "__main__":
    print("Key Custody Validator — ATF Genesis Key Management")
    print("Per santaclawd: 'who holds the signing key = who vouches for the agent'")
    print("DKIM RFC 6376 selector mechanism as model")
    print("=" * 65)
    print()
    run_scenarios()
    print("=" * 65)
    print("KEY INSIGHT: custody type determines revocation path.")
    print("OPERATOR_HELD = operator revokes (ESP model).")
    print("AGENT_HELD = agent rotates (TOFU risk, shorter lifetime).")
    print("HSM_MANAGED = ceremony required (strongest, slowest).")
    print("DKIM selector = rotate keys without changing genesis.")
