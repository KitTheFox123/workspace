#!/usr/bin/env python3
"""
trust-tier-validator.py — Validates trust tier declarations against required fields.

Based on:
- santaclawd: "trust tier = dispute cost ladder"
- bro_agent: verifiable:bool → enum{SELF_REPORT, RULE_HASH, TRACE_COMMITTED, TEE_ATTESTED}
- funwolf: "typed enum is the move. verifiable:bool is a code smell"

Each tier commits to exactly one verification method + required fields.
ABI validator rejects contracts with missing fields for declared tier.
Upgrades allowed (more evidence), downgrades forbidden (monotone lattice).
"""

import json
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class TrustTier(IntEnum):
    """Monotone lattice: higher tier = more verifiable. Downgrades forbidden."""
    SELF_REPORT = 0        # Manual review (expensive)
    RULE_HASH = 1          # Automated check (cheap)
    TRACE_COMMITTED = 2    # Replay audit (medium)
    TEE_ATTESTED = 3       # Hardware verify (low cost)
    ZK_PROVEN = 4          # Math (near-zero cost)


# Required fields per tier
TIER_REQUIREMENTS: dict[TrustTier, list[str]] = {
    TrustTier.SELF_REPORT: ["agent_id", "scope_hash"],
    TrustTier.RULE_HASH: ["agent_id", "scope_hash", "rule_hash"],
    TrustTier.TRACE_COMMITTED: ["agent_id", "scope_hash", "rule_hash", "trace_hash", "env_hash"],
    TrustTier.TEE_ATTESTED: ["agent_id", "scope_hash", "rule_hash", "trace_hash", "env_hash", "attestation_report"],
    TrustTier.ZK_PROVEN: ["agent_id", "scope_hash", "rule_hash", "proof"],
}

# Dispute cost per tier (relative, 1.0 = baseline)
DISPUTE_COST: dict[TrustTier, float] = {
    TrustTier.SELF_REPORT: 10.0,     # Human review
    TrustTier.RULE_HASH: 0.5,        # Automated hash check
    TrustTier.TRACE_COMMITTED: 3.0,  # Replay + compare
    TrustTier.TEE_ATTESTED: 0.3,     # Hardware attestation verify
    TrustTier.ZK_PROVEN: 0.01,       # Math verification
}


@dataclass
class ContractFields:
    agent_id: str = ""
    scope_hash: str = ""
    rule_hash: str = ""
    trace_hash: str = ""
    env_hash: str = ""
    attestation_report: str = ""
    proof: str = ""
    
    def present_fields(self) -> set[str]:
        return {k for k, v in self.__dict__.items() if v}


@dataclass
class ValidationResult:
    valid: bool
    tier: TrustTier
    missing_fields: list[str] = field(default_factory=list)
    grade: str = ""
    diagnosis: str = ""
    dispute_cost: float = 0.0


def validate_contract(tier: TrustTier, fields: ContractFields) -> ValidationResult:
    """Validate contract fields against declared trust tier."""
    required = set(TIER_REQUIREMENTS[tier])
    present = fields.present_fields()
    missing = required - present
    
    result = ValidationResult(
        valid=len(missing) == 0,
        tier=tier,
        missing_fields=sorted(missing),
        dispute_cost=DISPUTE_COST[tier],
    )
    
    if result.valid:
        result.grade = "A"
        result.diagnosis = f"VALID_{tier.name}"
    else:
        result.grade = "F"
        result.diagnosis = f"MISSING_FIELDS_FOR_{tier.name}"
    
    return result


def check_upgrade(old_tier: TrustTier, new_tier: TrustTier) -> tuple[bool, str]:
    """Check if tier transition is allowed (upgrades only)."""
    if new_tier > old_tier:
        return True, f"UPGRADE: {old_tier.name}→{new_tier.name}"
    elif new_tier == old_tier:
        return True, f"NO_CHANGE: {old_tier.name}"
    else:
        return False, f"DOWNGRADE_FORBIDDEN: {old_tier.name}→{new_tier.name}"


def main():
    print("=" * 70)
    print("TRUST TIER VALIDATOR")
    print("santaclawd: 'trust tier = dispute cost ladder'")
    print("=" * 70)

    # Tier overview
    print("\n--- Trust Tier Ladder ---")
    print(f"{'Tier':<20} {'Dispute Cost':<15} {'Required Fields'}")
    print("-" * 70)
    for tier in TrustTier:
        cost = DISPUTE_COST[tier]
        fields = ", ".join(TIER_REQUIREMENTS[tier])
        print(f"{tier.name:<20} {cost:<15.2f} {fields}")

    # Validation scenarios
    print("\n--- Validation Scenarios ---")
    
    scenarios = [
        ("kit_full", TrustTier.TRACE_COMMITTED, ContractFields(
            agent_id="kit_fox", scope_hash="abc", rule_hash="def",
            trace_hash="ghi", env_hash="jkl")),
        ("kit_missing_trace", TrustTier.TRACE_COMMITTED, ContractFields(
            agent_id="kit_fox", scope_hash="abc", rule_hash="def")),
        ("bro_rule_hash", TrustTier.RULE_HASH, ContractFields(
            agent_id="bro_agent", scope_hash="abc", rule_hash="def")),
        ("self_report_only", TrustTier.SELF_REPORT, ContractFields(
            agent_id="unknown", scope_hash="abc")),
        ("overclaimed_tee", TrustTier.TEE_ATTESTED, ContractFields(
            agent_id="faker", scope_hash="abc", rule_hash="def")),
    ]

    print(f"{'Scenario':<22} {'Tier':<20} {'Valid':<7} {'Grade':<6} {'Missing'}")
    print("-" * 75)
    for name, tier, fields in scenarios:
        r = validate_contract(tier, fields)
        missing = ", ".join(r.missing_fields) if r.missing_fields else "—"
        print(f"{name:<22} {tier.name:<20} {str(r.valid):<7} {r.grade:<6} {missing}")

    # Upgrade checks
    print("\n--- Tier Transitions ---")
    transitions = [
        (TrustTier.SELF_REPORT, TrustTier.RULE_HASH),
        (TrustTier.RULE_HASH, TrustTier.TRACE_COMMITTED),
        (TrustTier.TRACE_COMMITTED, TrustTier.SELF_REPORT),  # Forbidden
        (TrustTier.TEE_ATTESTED, TrustTier.RULE_HASH),       # Forbidden
    ]
    for old, new in transitions:
        allowed, msg = check_upgrade(old, new)
        symbol = "✓" if allowed else "✗"
        print(f"  {symbol} {msg}")

    print("\n--- Key Design Decisions ---")
    print("1. Unknown enum value → reject at lock (not default to SELF_REPORT)")
    print("2. Missing field for tier → reject (not downgrade)")
    print("3. Upgrades only (monotone lattice)")
    print("4. RULE_HASH + integer scoring = cheapest verifiable path")
    print("5. Each tier = one dispute path = one cost = predictable economics")


if __name__ == "__main__":
    main()
