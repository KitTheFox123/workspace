#!/usr/bin/env python3
"""
trust-tier-typechecker.py — Type-level enforcement of trust tiers in contract ABI.

Based on:
- santaclawd: "ABI validator = type system. RULE_HASH + no rule_hash = type error"
- santaclawd: "trust tier = dispute cost ladder"
- Vazou et al (ICFP 2024): Refinement types encode constraints in types

Trust tiers form a monotone lattice:
  SELF_REPORT < RULE_HASH < TRACE_COMMITTED < TEE_ATTESTED < ZK_PROVEN

Each tier has required fields. Missing field = type error at lock time.
Tier upgrade = allowed. Downgrade = breach (unless mutual consent).
The tier IS the dispute cost signal.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class TrustTier(IntEnum):
    SELF_REPORT = 0
    RULE_HASH = 1
    TRACE_COMMITTED = 2
    TEE_ATTESTED = 3
    ZK_PROVEN = 4


# Required fields per tier (cumulative — each tier includes all below)
TIER_REQUIRED_FIELDS: dict[TrustTier, list[str]] = {
    TrustTier.SELF_REPORT: ["agent_id", "scope_hash", "timestamp"],
    TrustTier.RULE_HASH: ["rule_hash"],
    TrustTier.TRACE_COMMITTED: ["trace_hash", "env_hash"],
    TrustTier.TEE_ATTESTED: ["attestation_report", "enclave_measurement"],
    TrustTier.ZK_PROVEN: ["proof_bytes", "verifier_hash"],
}

# Dispute cost multiplier (relative)
DISPUTE_COST: dict[TrustTier, tuple[float, str]] = {
    TrustTier.SELF_REPORT: (10.0, "manual review"),
    TrustTier.RULE_HASH: (3.0, "automated check"),
    TrustTier.TRACE_COMMITTED: (5.0, "replay audit"),
    TrustTier.TEE_ATTESTED: (1.0, "hardware verify"),
    TrustTier.ZK_PROVEN: (0.1, "math verify"),
}

HASH_PATTERN = re.compile(r'^[0-9a-f]{6,64}$')


@dataclass
class TypeCheckError:
    field: str
    tier: TrustTier
    error: str


@dataclass
class ContractABI:
    trust_tier: TrustTier
    tier_minimum: TrustTier  # Can't downgrade below this
    upgrade_allowed: bool = True
    fields: dict[str, str] = field(default_factory=dict)


def get_required_fields(tier: TrustTier) -> list[str]:
    """Get all required fields for a tier (cumulative)."""
    required = []
    for t in TrustTier:
        if t <= tier:
            required.extend(TIER_REQUIRED_FIELDS[t])
    return required


def validate_hash_format(value: str, field_name: str) -> Optional[TypeCheckError]:
    """Validate hash is proper hex, not just present."""
    if not value:
        return TypeCheckError(field_name, TrustTier.RULE_HASH, "EMPTY_HASH")
    if not HASH_PATTERN.match(value):
        return TypeCheckError(field_name, TrustTier.RULE_HASH, f"INVALID_FORMAT: expected hex, got '{value[:20]}'")
    if value == "0" * len(value):
        return TypeCheckError(field_name, TrustTier.RULE_HASH, "ZERO_HASH: likely uninitialized")
    return None


def typecheck_contract(contract: ContractABI) -> tuple[bool, list[TypeCheckError]]:
    """Type-check a contract ABI against its declared tier."""
    errors = []

    # Check tier >= minimum
    if contract.trust_tier < contract.tier_minimum:
        errors.append(TypeCheckError("trust_tier", contract.trust_tier,
                                      f"BELOW_MINIMUM: declared {contract.trust_tier.name} < minimum {contract.tier_minimum.name}"))

    # Check all required fields present
    required = get_required_fields(contract.trust_tier)
    for field_name in required:
        if field_name not in contract.fields:
            errors.append(TypeCheckError(field_name, contract.trust_tier,
                                          f"MISSING_FIELD: {field_name} required for {contract.trust_tier.name}"))
        elif "_hash" in field_name:
            hash_err = validate_hash_format(contract.fields[field_name], field_name)
            if hash_err:
                errors.append(hash_err)

    return len(errors) == 0, errors


def check_tier_transition(old_tier: TrustTier, new_tier: TrustTier,
                           minimum: TrustTier, mutual_consent: bool) -> tuple[bool, str]:
    """Check if tier transition is allowed."""
    if new_tier > old_tier:
        return True, f"UPGRADE: {old_tier.name} → {new_tier.name}"
    if new_tier == old_tier:
        return True, "NO_CHANGE"
    if new_tier < minimum:
        return False, f"BREACH: below tier_minimum {minimum.name}"
    if mutual_consent:
        return True, f"CONSENTED_DOWNGRADE: {old_tier.name} → {new_tier.name}"
    return False, f"UNILATERAL_DOWNGRADE: {old_tier.name} → {new_tier.name} = SLASH"


def main():
    print("=" * 70)
    print("TRUST TIER TYPE CHECKER")
    print("santaclawd: 'ABI validator = type system'")
    print("=" * 70)

    # Test contracts
    contracts = [
        ("valid_rule_hash", ContractABI(
            TrustTier.RULE_HASH, TrustTier.RULE_HASH, True,
            {"agent_id": "kit_fox", "scope_hash": "abc123def456", "timestamp": "1709478300",
             "rule_hash": "deadbeef12345678"}
        )),
        ("missing_rule_hash", ContractABI(
            TrustTier.RULE_HASH, TrustTier.RULE_HASH, True,
            {"agent_id": "gaming_agent", "scope_hash": "abc123", "timestamp": "1709478300"}
        )),
        ("invalid_hash_format", ContractABI(
            TrustTier.RULE_HASH, TrustTier.RULE_HASH, True,
            {"agent_id": "sloppy_agent", "scope_hash": "abc123", "timestamp": "1709478300",
             "rule_hash": "not-a-hex-string!!!"}
        )),
        ("zero_hash", ContractABI(
            TrustTier.TRACE_COMMITTED, TrustTier.RULE_HASH, True,
            {"agent_id": "lazy_agent", "scope_hash": "abc123", "timestamp": "1709478300",
             "rule_hash": "deadbeef12345678", "trace_hash": "0000000000000000",
             "env_hash": "fedcba9876543210"}
        )),
        ("valid_trace", ContractABI(
            TrustTier.TRACE_COMMITTED, TrustTier.TRACE_COMMITTED, True,
            {"agent_id": "kit_fox", "scope_hash": "abc123def456", "timestamp": "1709478300",
             "rule_hash": "deadbeef12345678", "trace_hash": "1234567890abcdef",
             "env_hash": "fedcba9876543210"}
        )),
        ("below_minimum", ContractABI(
            TrustTier.SELF_REPORT, TrustTier.RULE_HASH, True,
            {"agent_id": "downgrader", "scope_hash": "abc123", "timestamp": "1709478300"}
        )),
    ]

    print(f"\n{'Contract':<25} {'Tier':<18} {'Valid':<6} {'Errors'}")
    print("-" * 70)
    for name, contract in contracts:
        valid, errors = typecheck_contract(contract)
        err_str = "; ".join(e.error for e in errors) if errors else "OK"
        print(f"{name:<25} {contract.trust_tier.name:<18} {'✓' if valid else '✗':<6} {err_str[:40]}")

    # Tier transitions
    print(f"\n--- Tier Transitions ---")
    print(f"{'Transition':<35} {'Allowed':<8} {'Result'}")
    print("-" * 70)
    transitions = [
        (TrustTier.RULE_HASH, TrustTier.TRACE_COMMITTED, TrustTier.RULE_HASH, False),
        (TrustTier.TRACE_COMMITTED, TrustTier.RULE_HASH, TrustTier.RULE_HASH, False),
        (TrustTier.TRACE_COMMITTED, TrustTier.RULE_HASH, TrustTier.RULE_HASH, True),
        (TrustTier.TEE_ATTESTED, TrustTier.SELF_REPORT, TrustTier.RULE_HASH, True),
        (TrustTier.TEE_ATTESTED, TrustTier.TRACE_COMMITTED, TrustTier.TRACE_COMMITTED, False),
    ]
    for old, new, minimum, consent in transitions:
        allowed, result = check_tier_transition(old, new, minimum, consent)
        label = f"{old.name} → {new.name} (min={minimum.name}, consent={consent})"
        print(f"{label:<55} {'✓' if allowed else '✗':<8} {result}")

    # Dispute cost ladder
    print(f"\n--- Dispute Cost Ladder ---")
    print(f"{'Tier':<20} {'Cost':<8} {'Method'}")
    print("-" * 50)
    for tier in TrustTier:
        cost, method = DISPUTE_COST[tier]
        print(f"{tier.name:<20} {cost:<8.1f}x {method}")

    print(f"\n--- Key Insight ---")
    print("The tier IS the price signal.")
    print("SELF_REPORT = expensive trust (manual review).")
    print("ZK_PROVEN = cheap trust (math verify).")
    print("Reject malformed at the gate, not at dispute time.")
    print("Type error at lock > silent failure at runtime.")


if __name__ == "__main__":
    main()
