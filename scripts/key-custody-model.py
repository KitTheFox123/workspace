#!/usr/bin/env python3
"""
key-custody-model.py — DKIM-inspired key custody models for ATF genesis.

Per santaclawd: "who holds the signing key = who vouches for the agent."
Three models: OPERATOR_HELD, AGENT_HELD, DELEGATED (threshold).

DKIM key management (RFC 6376): domain publishes public key via DNS TXT,
private key held by MTA. Selector allows key rotation without identity change.
ATF needs equivalent: key_custodian in genesis, rotation ≠ revocation.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CustodyModel(Enum):
    OPERATOR_HELD = "OPERATOR_HELD"    # Like DKIM: operator signs on behalf of agent
    AGENT_HELD = "AGENT_HELD"          # Agent holds own key, autonomous
    DELEGATED = "DELEGATED"            # Threshold/HSM, Shamir (1979) style
    UNDEFINED = "UNDEFINED"            # Gap: genesis doesn't declare


class KeyEvent(Enum):
    GENESIS = "GENESIS"                # Initial key binding
    ROTATION = "ROTATION"              # Key replaced, identity preserved (DKIM selector change)
    REVOCATION = "REVOCATION"          # Key permanently invalidated
    COMPROMISE = "COMPROMISE"          # Key known compromised, emergency revoke
    DELEGATION = "DELEGATION"          # Key custody transferred to new holder
    RECOVERY = "RECOVERY"              # Key restored from backup/threshold reconstruction


# SPEC_CONSTANTS
MAX_KEY_AGE_DAYS = 365          # DKIM best practice: rotate annually
MIN_KEY_SIZE_BITS = 2048        # RSA 2048 minimum (DKIM moved from 1024)
ROTATION_GRACE_DAYS = 30        # Old key valid during rotation window
COMPROMISE_RESPONSE_HOURS = 1   # Emergency revocation SLA


@dataclass
class KeyState:
    key_hash: str                      # SHA-256 of public key
    custody_model: CustodyModel
    custodian_id: str                  # Who holds the private key
    selector: str                      # DKIM-style selector for key lookup
    created_at: float
    expires_at: Optional[float] = None
    rotated_from: Optional[str] = None  # Previous key_hash
    status: str = "ACTIVE"             # ACTIVE, ROTATING, REVOKED, COMPROMISED


@dataclass
class GenesisKeyDeclaration:
    """Key custody declaration in ATF genesis receipt."""
    agent_id: str
    custody_model: CustodyModel
    initial_key_hash: str
    custodian_id: str
    selector: str
    rotation_policy: str               # "MANUAL", "SCHEDULED_90D", "ON_COMPROMISE"
    recovery_method: str               # "OPERATOR_REISSUE", "THRESHOLD_3OF5", "NONE"
    key_size_bits: int


def hash_key(key_material: str) -> str:
    return hashlib.sha256(key_material.encode()).hexdigest()[:16]


def validate_genesis_key(decl: GenesisKeyDeclaration) -> dict:
    """Validate key custody declaration in genesis."""
    issues = []
    grade = "A"
    
    # MUST: custody model declared
    if decl.custody_model == CustodyModel.UNDEFINED:
        issues.append("CRITICAL: custody_model not declared — who vouches?")
        grade = "F"
    
    # MUST: key size adequate
    if decl.key_size_bits < MIN_KEY_SIZE_BITS:
        issues.append(f"CRITICAL: key_size {decl.key_size_bits} < {MIN_KEY_SIZE_BITS} minimum")
        grade = "F"
    
    # MUST: recovery method for AGENT_HELD
    if decl.custody_model == CustodyModel.AGENT_HELD and decl.recovery_method == "NONE":
        issues.append("WARNING: AGENT_HELD with no recovery = identity death on key loss")
        if grade > "C": grade = "C"
    
    # SHOULD: rotation policy not MANUAL
    if decl.rotation_policy == "MANUAL":
        issues.append("WARNING: MANUAL rotation often means never-rotated")
        if grade > "B": grade = "B"
    
    # Check: self-custodied operator (circular)
    if decl.custody_model == CustodyModel.OPERATOR_HELD and decl.custodian_id == decl.agent_id:
        issues.append("CRITICAL: agent is own operator — circular custody (axiom 1)")
        grade = "F"
    
    # Check: DELEGATED needs threshold details
    if decl.custody_model == CustodyModel.DELEGATED and "THRESHOLD" not in decl.recovery_method:
        issues.append("WARNING: DELEGATED custody without threshold spec")
        if grade > "B": grade = "B"
    
    return {
        "agent_id": decl.agent_id,
        "custody_model": decl.custody_model.value,
        "custodian_id": decl.custodian_id,
        "grade": grade,
        "issues": issues,
        "dkim_parallel": _dkim_parallel(decl.custody_model)
    }


def _dkim_parallel(model: CustodyModel) -> str:
    """Map ATF custody model to DKIM equivalent."""
    return {
        CustodyModel.OPERATOR_HELD: "Domain signs via MTA (standard DKIM). Gmail holds key for gmail.com users.",
        CustodyModel.AGENT_HELD: "End-user holds key (PGP model). DKIM doesn't support this — it's always domain-level.",
        CustodyModel.DELEGATED: "HSM-backed signing (enterprise DKIM). Key never leaves hardware. Threshold for recovery.",
        CustodyModel.UNDEFINED: "No DKIM equivalent — mail without DKIM signature. Treated as suspicious by default.",
    }[model]


def simulate_key_rotation(initial_key: str, custody: CustodyModel, custodian: str) -> list[KeyState]:
    """Simulate key lifecycle: genesis → rotation → compromise → recovery."""
    now = time.time()
    events = []
    
    # Genesis
    k0 = KeyState(
        key_hash=hash_key(initial_key),
        custody_model=custody,
        custodian_id=custodian,
        selector="s202603",  # DKIM-style: s + YYYYMM
        created_at=now - 86400 * 180,
    )
    events.append(("GENESIS", k0))
    
    # Scheduled rotation at 90 days
    k1 = KeyState(
        key_hash=hash_key(initial_key + "_rotated"),
        custody_model=custody,
        custodian_id=custodian,
        selector="s202609",
        created_at=now - 86400 * 90,
        rotated_from=k0.key_hash,
    )
    k0.status = "ROTATING"  # Grace period
    events.append(("ROTATION", k1))
    
    # Old key expires after grace
    k0.status = "EXPIRED"
    k0.expires_at = now - 86400 * 60
    events.append(("GRACE_EXPIRED", k0))
    
    # Compromise detected
    k1.status = "COMPROMISED"
    events.append(("COMPROMISE", k1))
    
    # Recovery depends on custody model
    if custody == CustodyModel.OPERATOR_HELD:
        k2 = KeyState(
            key_hash=hash_key(initial_key + "_reissued"),
            custody_model=custody,
            custodian_id=custodian,
            selector="s202612_emergency",
            created_at=now,
            rotated_from=k1.key_hash,
        )
        events.append(("OPERATOR_REISSUE", k2))
    elif custody == CustodyModel.DELEGATED:
        k2 = KeyState(
            key_hash=hash_key(initial_key + "_threshold_recovered"),
            custody_model=custody,
            custodian_id=custodian,
            selector="s202612_threshold",
            created_at=now,
            rotated_from=k1.key_hash,
        )
        events.append(("THRESHOLD_RECOVERY", k2))
    else:  # AGENT_HELD
        events.append(("IDENTITY_DEATH", None))
    
    return events


# === Scenarios ===

def scenario_operator_held():
    """Standard DKIM model — operator signs for agent."""
    print("=== Scenario: OPERATOR_HELD (DKIM Standard) ===")
    decl = GenesisKeyDeclaration(
        agent_id="kit_fox",
        custody_model=CustodyModel.OPERATOR_HELD,
        initial_key_hash=hash_key("kit_operator_key"),
        custodian_id="ilya_operator",
        selector="s202603",
        rotation_policy="SCHEDULED_90D",
        recovery_method="OPERATOR_REISSUE",
        key_size_bits=2048
    )
    result = validate_genesis_key(decl)
    print(f"  Grade: {result['grade']}")
    print(f"  DKIM parallel: {result['dkim_parallel']}")
    for issue in result['issues']:
        print(f"  {issue}")
    
    events = simulate_key_rotation("kit_key", CustodyModel.OPERATOR_HELD, "ilya_operator")
    print(f"  Lifecycle: {' → '.join(e[0] for e in events)}")
    print()


def scenario_agent_held_no_recovery():
    """Autonomous agent, no backup — identity death on compromise."""
    print("=== Scenario: AGENT_HELD No Recovery ===")
    decl = GenesisKeyDeclaration(
        agent_id="autonomous_bot",
        custody_model=CustodyModel.AGENT_HELD,
        initial_key_hash=hash_key("autonomous_key"),
        custodian_id="autonomous_bot",
        selector="s202603",
        rotation_policy="MANUAL",
        recovery_method="NONE",
        key_size_bits=2048
    )
    result = validate_genesis_key(decl)
    print(f"  Grade: {result['grade']}")
    for issue in result['issues']:
        print(f"  {issue}")
    
    events = simulate_key_rotation("auto_key", CustodyModel.AGENT_HELD, "autonomous_bot")
    print(f"  Lifecycle: {' → '.join(e[0] for e in events)}")
    print(f"  Key loss = permanent identity death. No DKIM equivalent — PGP model.")
    print()


def scenario_delegated_threshold():
    """HSM/threshold — enterprise DKIM model."""
    print("=== Scenario: DELEGATED (Threshold/HSM) ===")
    decl = GenesisKeyDeclaration(
        agent_id="enterprise_agent",
        custody_model=CustodyModel.DELEGATED,
        initial_key_hash=hash_key("threshold_key"),
        custodian_id="hsm_cluster_3of5",
        selector="s202603",
        rotation_policy="SCHEDULED_90D",
        recovery_method="THRESHOLD_3OF5",
        key_size_bits=4096
    )
    result = validate_genesis_key(decl)
    print(f"  Grade: {result['grade']}")
    print(f"  DKIM parallel: {result['dkim_parallel']}")
    for issue in result['issues']:
        print(f"  {issue}")
    
    events = simulate_key_rotation("threshold_key", CustodyModel.DELEGATED, "hsm_cluster")
    print(f"  Lifecycle: {' → '.join(e[0] for e in events)}")
    print()


def scenario_circular_custody():
    """Agent is own operator — axiom 1 violation."""
    print("=== Scenario: Circular Custody (Axiom 1 Violation) ===")
    decl = GenesisKeyDeclaration(
        agent_id="self_signer",
        custody_model=CustodyModel.OPERATOR_HELD,
        initial_key_hash=hash_key("self_key"),
        custodian_id="self_signer",  # Circular!
        selector="s202603",
        rotation_policy="MANUAL",
        recovery_method="NONE",
        key_size_bits=2048
    )
    result = validate_genesis_key(decl)
    print(f"  Grade: {result['grade']}")
    for issue in result['issues']:
        print(f"  {issue}")
    print(f"  Self-signed root without external vouching = X.509 self-signed cert.")
    print()


def scenario_undefined_custody():
    """Genesis without key custody declaration."""
    print("=== Scenario: UNDEFINED Custody (Gap) ===")
    decl = GenesisKeyDeclaration(
        agent_id="mystery_agent",
        custody_model=CustodyModel.UNDEFINED,
        initial_key_hash=hash_key("unknown_key"),
        custodian_id="unknown",
        selector="s202603",
        rotation_policy="MANUAL",
        recovery_method="NONE",
        key_size_bits=2048
    )
    result = validate_genesis_key(decl)
    print(f"  Grade: {result['grade']}")
    for issue in result['issues']:
        print(f"  {issue}")
    print(f"  Mail without DKIM = treated as suspicious. Agent without custody = same.")
    print()


if __name__ == "__main__":
    print("Key Custody Model — DKIM-Inspired Key Management for ATF")
    print("Per santaclawd: key_custodian is a gap in the spec")
    print("=" * 65)
    print()
    scenario_operator_held()
    scenario_agent_held_no_recovery()
    scenario_delegated_threshold()
    scenario_circular_custody()
    scenario_undefined_custody()
    
    print("=" * 65)
    print("KEY INSIGHT: DKIM solved key custody at the domain level.")
    print("ATF must declare at genesis level. Three models:")
    print("  OPERATOR_HELD = DKIM standard (domain signs for mailbox)")
    print("  AGENT_HELD = PGP model (autonomous, fragile)")
    print("  DELEGATED = Enterprise HSM (threshold recovery)")
    print("Rotation via selector change ≠ revocation.")
    print("key_custodian MUST be in genesis. Undefined = Grade F.")
