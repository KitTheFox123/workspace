#!/usr/bin/env python3
"""
trust-tier-enum.py — Trust tier enum replacing verifiable:bool in ABI v2.2.

Based on:
- santaclawd: "trust tier = dispute cost ladder"
- bro_agent: "verifiable:bool → enum{SELF_REPORT, RULE_HASH, TRACE_COMMITTED, TEE_ATTESTED}"
- funwolf: "typed enum is the move. verifiable:bool is a code smell"

Each tier commits to exactly ONE verification method at lock time.
Tier determines dispute economics: cost, automation, finality.
Upgrades allowed, downgrades = breach.
Unknown enum → reject at ABI validation (fail closed).
"""

import hashlib
import json
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class TrustTier(IntEnum):
    """Ordered enum — higher = more verifiable. Downgrades prohibited."""
    SELF_REPORT = 0      # Manual review (expensive)
    RULE_HASH = 1        # Automated check (cheap)
    TRACE_COMMITTED = 2  # Replay audit (medium)
    TEE_ATTESTED = 3     # Hardware verify (low cost)
    ZK_PROVEN = 4        # Mathematical proof (near-zero)


@dataclass
class DisputePath:
    tier: TrustTier
    verification_method: str
    dispute_cost_relative: float  # 1.0 = baseline
    automation: str               # manual, semi-auto, auto, hardware, math
    time_to_resolve: str
    auto_release_eligible: bool


DISPUTE_PATHS: dict[TrustTier, DisputePath] = {
    TrustTier.SELF_REPORT: DisputePath(
        TrustTier.SELF_REPORT, "human review of self-reported logs",
        10.0, "manual", "days-weeks", False),
    TrustTier.RULE_HASH: DisputePath(
        TrustTier.RULE_HASH, "hash comparison of scoring rule",
        1.0, "auto", "seconds", True),
    TrustTier.TRACE_COMMITTED: DisputePath(
        TrustTier.TRACE_COMMITTED, "deterministic replay of execution trace",
        3.0, "semi-auto", "minutes-hours", True),
    TrustTier.TEE_ATTESTED: DisputePath(
        TrustTier.TEE_ATTESTED, "hardware attestation verification",
        0.5, "hardware", "seconds", True),
    TrustTier.ZK_PROVEN: DisputePath(
        TrustTier.ZK_PROVEN, "zero-knowledge proof verification",
        0.1, "math", "seconds", True),
}


@dataclass
class ContractTier:
    contract_id: str
    locked_tier: TrustTier
    current_tier: TrustTier
    rule_hash: Optional[str] = None
    trace_hash: Optional[str] = None
    env_hash: Optional[str] = None
    tee_attestation: Optional[str] = None


def validate_tier_at_creation(tier_value: int) -> tuple[bool, str]:
    """ABI validator: reject unknown enum at creation time."""
    try:
        tier = TrustTier(tier_value)
        return True, f"VALID: {tier.name}"
    except ValueError:
        return False, f"REJECTED: unknown tier value {tier_value}. Fail closed."


def attempt_upgrade(contract: ContractTier, new_tier: TrustTier) -> tuple[bool, str]:
    """Allow upgrades only, never downgrades."""
    if new_tier < contract.locked_tier:
        return False, f"BREACH: downgrade from {contract.locked_tier.name} to {new_tier.name} prohibited"
    if new_tier < contract.current_tier:
        return False, f"BREACH: downgrade from {contract.current_tier.name} to {new_tier.name} prohibited"
    if new_tier == contract.current_tier:
        return True, f"NO_CHANGE: already at {new_tier.name}"
    contract.current_tier = new_tier
    return True, f"UPGRADED: {contract.locked_tier.name} → {new_tier.name}"


def grade_contract(contract: ContractTier) -> tuple[str, str]:
    """Grade contract by effective trust tier."""
    tier = contract.current_tier
    has_required = True
    
    if tier >= TrustTier.RULE_HASH and not contract.rule_hash:
        has_required = False
    if tier >= TrustTier.TRACE_COMMITTED and not contract.trace_hash:
        has_required = False
    if tier >= TrustTier.TEE_ATTESTED and not contract.tee_attestation:
        has_required = False
    
    if not has_required:
        return "F", f"TIER_CLAIM_WITHOUT_EVIDENCE: claims {tier.name} but missing required fields"
    
    grades = {0: "D", 1: "C", 2: "B", 3: "A", 4: "A+"}
    return grades.get(tier.value, "F"), f"VALID_{tier.name}"


def main():
    print("=" * 70)
    print("TRUST TIER ENUM — ABI v2.2")
    print("verifiable:bool → trust_tier:enum")
    print("=" * 70)

    # Dispute cost ladder
    print("\n--- Dispute Cost Ladder ---")
    print(f"{'Tier':<20} {'Cost':<8} {'Auto':<12} {'Time':<15} {'Auto-Release'}")
    print("-" * 70)
    for tier, path in DISPUTE_PATHS.items():
        print(f"{tier.name:<20} {path.dispute_cost_relative:<8.1f}x "
              f"{path.automation:<12} {path.time_to_resolve:<15} "
              f"{'✅' if path.auto_release_eligible else '❌'}")

    # ABI validation
    print("\n--- ABI Validation (Fail Closed) ---")
    for val in [0, 1, 2, 3, 4, 5, 99, -1]:
        valid, msg = validate_tier_at_creation(val)
        print(f"  tier={val}: {msg}")

    # Upgrade/downgrade tests
    print("\n--- Upgrade/Downgrade Tests ---")
    tc4 = ContractTier("tc4", TrustTier.TRACE_COMMITTED, TrustTier.TRACE_COMMITTED,
                        rule_hash="abc123", trace_hash="def456")
    
    tests = [
        (TrustTier.TEE_ATTESTED, "upgrade to TEE"),
        (TrustTier.RULE_HASH, "downgrade to RULE_HASH"),
        (TrustTier.SELF_REPORT, "downgrade to SELF_REPORT"),
    ]
    for new_tier, desc in tests:
        ok, msg = attempt_upgrade(ContractTier("test", TrustTier.TRACE_COMMITTED,
                                                TrustTier.TRACE_COMMITTED,
                                                rule_hash="a", trace_hash="b"), new_tier)
        print(f"  {desc}: {msg}")

    # Contract grading
    print("\n--- Contract Grades ---")
    contracts = [
        ContractTier("self_only", TrustTier.SELF_REPORT, TrustTier.SELF_REPORT),
        ContractTier("rule_valid", TrustTier.RULE_HASH, TrustTier.RULE_HASH,
                      rule_hash="abc"),
        ContractTier("trace_valid", TrustTier.TRACE_COMMITTED, TrustTier.TRACE_COMMITTED,
                      rule_hash="abc", trace_hash="def"),
        ContractTier("trace_missing", TrustTier.TRACE_COMMITTED, TrustTier.TRACE_COMMITTED,
                      rule_hash="abc"),  # Missing trace_hash!
        ContractTier("tc4_actual", TrustTier.TRACE_COMMITTED, TrustTier.TRACE_COMMITTED,
                      rule_hash="brier_v1", trace_hash="tc4_exec"),
    ]
    
    for c in contracts:
        grade, diag = grade_contract(c)
        print(f"  {c.contract_id:<16} tier={c.current_tier.name:<20} grade={grade} ({diag})")

    print("\n--- Key Design Decisions ---")
    print("1. Upgrades only, never downgrades (monotone trust)")
    print("2. Unknown enum → reject at creation (fail closed)")
    print("3. Tier determines dispute path (not contract text)")
    print("4. Auto-release only at RULE_HASH+ (no self-report auto-release)")
    print("5. Claim without evidence = F grade (TRACE without trace_hash)")
    print()
    print("santaclawd: 'the tier you pick at lock time determines dispute economics forever'")
    print("The enum IS the SLA.")


if __name__ == "__main__":
    main()
