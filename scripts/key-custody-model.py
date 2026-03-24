#!/usr/bin/env python3
"""
key-custody-model.py — DKIM-style key custody for ATF genesis receipts.

Per santaclawd: "who holds the signing key = who vouches for the agent."
Gap: ATF genesis doesn't specify key_custodian.

DKIM answer: domain holds key, publishes via DNS TXT, delegates via selectors.
Three custody models:
  OPERATOR_HELD  — Operator signs on agent's behalf (like ESP signing DKIM)
  AGENT_HELD     — Agent holds own key (autonomous but vulnerable to loss)
  SPLIT_CUSTODY  — M-of-N threshold between operator + agent (HSM model)

Key rotation = new selector, old expires. RFC 6376 §3.3.4.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class CustodyModel(Enum):
    OPERATOR_HELD = "OPERATOR_HELD"   # ESP/provider model
    AGENT_HELD = "AGENT_HELD"         # Autonomous model
    SPLIT_CUSTODY = "SPLIT_CUSTODY"   # M-of-N threshold


class KeyStatus(Enum):
    ACTIVE = "ACTIVE"
    ROTATING = "ROTATING"       # New key active, old still valid
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


# SPEC_CONSTANTS
MAX_KEY_AGE_DAYS = 90           # DKIM best practice: rotate every 90 days
ROTATION_OVERLAP_DAYS = 7       # Both keys valid during rotation
MIN_KEY_BITS = 2048             # RFC 8301: minimum RSA key size
SPLIT_CUSTODY_THRESHOLD = 2     # M in M-of-N
SPLIT_CUSTODY_TOTAL = 3         # N in M-of-N


@dataclass
class SigningKey:
    key_id: str
    selector: str               # DKIM selector equivalent
    custodian: CustodyModel
    created_at: float
    expires_at: float
    status: KeyStatus = KeyStatus.ACTIVE
    key_bits: int = 2048
    algorithm: str = "Ed25519"  # Modern default
    operator_id: Optional[str] = None
    split_holders: list = field(default_factory=list)
    rotation_successor: Optional[str] = None


@dataclass
class GenesisKeyField:
    """Proposed ATF genesis field for key custody."""
    custody_model: str
    active_selector: str
    key_algorithm: str
    key_bits: int
    rotation_policy_days: int
    operator_id: Optional[str] = None
    split_threshold: Optional[int] = None
    split_total: Optional[int] = None


def create_selector(agent_id: str, timestamp: float) -> str:
    """Generate DKIM-style selector: agent_timestamp._atfkey"""
    ts = int(timestamp)
    h = hashlib.sha256(f"{agent_id}:{ts}".encode()).hexdigest()[:8]
    return f"{h}._atfkey.{agent_id}"


def validate_key(key: SigningKey) -> dict:
    """Validate a signing key against ATF SPEC_CONSTANTS."""
    issues = []
    grade = "A"
    
    now = time.time()
    age_days = (now - key.created_at) / 86400
    
    # Key age
    if age_days > MAX_KEY_AGE_DAYS:
        issues.append(f"KEY_EXPIRED: {age_days:.0f} days old (max {MAX_KEY_AGE_DAYS})")
        grade = "F"
    elif age_days > MAX_KEY_AGE_DAYS * 0.8:
        issues.append(f"KEY_AGING: {age_days:.0f} days old, rotation due")
        grade = min(grade, "B")
    
    # Key size (RSA only)
    if key.algorithm == "RSA" and key.key_bits < MIN_KEY_BITS:
        issues.append(f"KEY_WEAK: {key.key_bits} bits (min {MIN_KEY_BITS})")
        grade = "F"
    
    # Custody model validation
    if key.custodian == CustodyModel.OPERATOR_HELD and not key.operator_id:
        issues.append("CUSTODY_GAP: operator_held but no operator_id")
        grade = "F"
    
    if key.custodian == CustodyModel.SPLIT_CUSTODY:
        if len(key.split_holders) < SPLIT_CUSTODY_TOTAL:
            issues.append(f"SPLIT_INCOMPLETE: {len(key.split_holders)}/{SPLIT_CUSTODY_TOTAL} holders")
            grade = "D"
        # Check for self-split (operator is also holder)
        if key.operator_id and key.operator_id in key.split_holders:
            issues.append("SELF_SPLIT: operator is also split holder (axiom 1 risk)")
            grade = min(grade, "C")
    
    if key.custodian == CustodyModel.AGENT_HELD:
        # No operator oversight = higher risk
        if not key.rotation_successor:
            issues.append("NO_ROTATION_PLAN: agent-held key without successor selector")
            grade = min(grade, "C")
    
    return {
        "key_id": key.key_id,
        "selector": key.selector,
        "custodian": key.custodian.value,
        "age_days": round(age_days, 1),
        "grade": grade,
        "issues": issues
    }


def rotate_key(old_key: SigningKey, agent_id: str) -> tuple[SigningKey, SigningKey]:
    """
    Rotate a signing key. Returns (new_key, updated_old_key).
    
    DKIM model: both keys valid during overlap period.
    Old key status → ROTATING, then EXPIRED after overlap.
    """
    now = time.time()
    new_selector = create_selector(agent_id, now)
    
    new_key = SigningKey(
        key_id=hashlib.sha256(new_selector.encode()).hexdigest()[:16],
        selector=new_selector,
        custodian=old_key.custodian,
        created_at=now,
        expires_at=now + MAX_KEY_AGE_DAYS * 86400,
        key_bits=old_key.key_bits,
        algorithm=old_key.algorithm,
        operator_id=old_key.operator_id,
        split_holders=old_key.split_holders.copy(),
    )
    
    # Old key enters rotation period
    old_key.status = KeyStatus.ROTATING
    old_key.expires_at = now + ROTATION_OVERLAP_DAYS * 86400
    old_key.rotation_successor = new_key.key_id
    
    return new_key, old_key


def genesis_key_field(key: SigningKey) -> GenesisKeyField:
    """Generate the genesis key custody field for ATF."""
    return GenesisKeyField(
        custody_model=key.custodian.value,
        active_selector=key.selector,
        key_algorithm=key.algorithm,
        key_bits=key.key_bits,
        rotation_policy_days=MAX_KEY_AGE_DAYS,
        operator_id=key.operator_id,
        split_threshold=SPLIT_CUSTODY_THRESHOLD if key.custodian == CustodyModel.SPLIT_CUSTODY else None,
        split_total=SPLIT_CUSTODY_TOTAL if key.custodian == CustodyModel.SPLIT_CUSTODY else None,
    )


# === Scenarios ===

def scenario_operator_held():
    """Standard operator-held key (like Gmail signing DKIM)."""
    print("=== Scenario: Operator-Held Key (ESP Model) ===")
    now = time.time()
    
    key = SigningKey(
        key_id="op_key_001",
        selector=create_selector("kit_fox", now),
        custodian=CustodyModel.OPERATOR_HELD,
        created_at=now - 30 * 86400,  # 30 days old
        expires_at=now + 60 * 86400,
        operator_id="ilya_openclaw",
    )
    
    result = validate_key(key)
    genesis = genesis_key_field(key)
    print(f"  Key: {result['key_id']}, age={result['age_days']}d, grade={result['grade']}")
    print(f"  Custody: {result['custodian']}")
    print(f"  Genesis field: custody={genesis.custody_model}, rotation={genesis.rotation_policy_days}d")
    print(f"  Issues: {result['issues'] or 'none'}")
    print()


def scenario_agent_held_no_rotation():
    """Agent-held key with no rotation plan — catches the gap."""
    print("=== Scenario: Agent-Held Key (No Rotation Plan) ===")
    now = time.time()
    
    key = SigningKey(
        key_id="agent_key_001",
        selector=create_selector("autonomous_bot", now),
        custodian=CustodyModel.AGENT_HELD,
        created_at=now - 100 * 86400,  # 100 days = expired!
        expires_at=now - 10 * 86400,
    )
    
    result = validate_key(key)
    print(f"  Key: {result['key_id']}, age={result['age_days']}d, grade={result['grade']}")
    print(f"  Issues: {result['issues']}")
    print()


def scenario_split_custody():
    """M-of-N split custody (HSM model)."""
    print("=== Scenario: Split Custody (2-of-3 Threshold) ===")
    now = time.time()
    
    key = SigningKey(
        key_id="split_key_001",
        selector=create_selector("high_value_agent", now),
        custodian=CustodyModel.SPLIT_CUSTODY,
        created_at=now - 45 * 86400,
        expires_at=now + 45 * 86400,
        operator_id="org_operator",
        split_holders=["org_operator", "agent_self", "independent_witness"],
    )
    
    result = validate_key(key)
    genesis = genesis_key_field(key)
    print(f"  Key: {result['key_id']}, age={result['age_days']}d, grade={result['grade']}")
    print(f"  Custody: {result['custodian']}, threshold={genesis.split_threshold}/{genesis.split_total}")
    print(f"  Issues: {result['issues'] or 'none'}")
    # Note: operator is also split holder = axiom 1 risk
    print()


def scenario_key_rotation():
    """Demonstrate DKIM-style key rotation with overlap."""
    print("=== Scenario: Key Rotation (DKIM Overlap Model) ===")
    now = time.time()
    
    old_key = SigningKey(
        key_id="old_key_001",
        selector=create_selector("rotating_agent", now - 85 * 86400),
        custodian=CustodyModel.OPERATOR_HELD,
        created_at=now - 85 * 86400,  # Almost expired
        expires_at=now + 5 * 86400,
        operator_id="org_operator",
    )
    
    print(f"  Before rotation:")
    print(f"    Old key: {old_key.key_id}, status={old_key.status.value}, age={85}d")
    
    new_key, updated_old = rotate_key(old_key, "rotating_agent")
    
    print(f"  After rotation:")
    print(f"    Old key: {updated_old.key_id}, status={updated_old.status.value}, "
          f"expires in {ROTATION_OVERLAP_DAYS}d")
    print(f"    New key: {new_key.key_id}, status={new_key.status.value}, "
          f"expires in {MAX_KEY_AGE_DAYS}d")
    print(f"    Successor chain: {updated_old.key_id} → {new_key.key_id}")
    print(f"    Both valid during {ROTATION_OVERLAP_DAYS}d overlap")
    print()


if __name__ == "__main__":
    print("Key Custody Model — DKIM-Style Key Management for ATF")
    print("Per santaclawd: 'who holds the signing key = who vouches for the agent'")
    print("=" * 65)
    print()
    scenario_operator_held()
    scenario_agent_held_no_rotation()
    scenario_split_custody()
    scenario_key_rotation()
    
    print("=" * 65)
    print("KEY INSIGHT: key_custodian is a missing ATF genesis field.")
    print("Three models: OPERATOR_HELD (centralized trust),")
    print("  AGENT_HELD (autonomous but fragile),")
    print("  SPLIT_CUSTODY (M-of-N threshold, HSM model).")
    print("DKIM solved this 20 years ago: selector delegation + DNS TXT.")
    print("ATF needs: custody_model + active_selector + rotation_policy in genesis.")
