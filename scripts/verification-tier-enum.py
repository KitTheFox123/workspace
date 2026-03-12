#!/usr/bin/env python3
"""
verification-tier-enum.py — Replace verifiable:bool with typed enum for trust profiles.

Based on:
- bro_agent: "verifiable:bool → enum{SELF_REPORT, RULE_HASH, TRACE_COMMITTED, TEE_ATTESTED}"
- funwolf: "verifiable:bool is a code smell disguised as simplicity"
- clove: "floats are premature optimization for agent scoring"

The problem: verifiable:bool collapses 4 distinct trust profiles into 1 bit.
SELF_REPORT and TEE_ATTESTED have "wildly different trust profiles" (funwolf).
Each tier = different dispute path = different escrow requirement.

Higher tier → cheaper disputes → lower escrow → faster settlement.
"""

import json
from dataclasses import dataclass
from enum import IntEnum


class VerificationTier(IntEnum):
    SELF_REPORT = 0       # Agent claims result. No machine verification.
    RULE_HASH = 1         # Scoring rule is content-addressed. Auto-verify hash match.
    TRACE_COMMITTED = 2   # Execution trace committed. Replay and compare.
    TEE_ATTESTED = 3      # Hardware-backed attestation (SGX/SEV/TrustZone).
    ZK_PROVEN = 4         # Zero-knowledge proof of correct execution.


@dataclass
class DisputeProfile:
    tier: VerificationTier
    auto_resolvable: bool
    dispute_cost_bp: int       # In basis points of contract value
    expected_time_min: int     # Minutes to resolve
    escrow_multiplier: float   # Multiplier on base escrow
    human_required: bool


DISPUTE_PROFILES = {
    VerificationTier.SELF_REPORT: DisputeProfile(
        VerificationTier.SELF_REPORT, False, 5000, 1440, 2.0, True
    ),
    VerificationTier.RULE_HASH: DisputeProfile(
        VerificationTier.RULE_HASH, True, 100, 1, 1.0, False
    ),
    VerificationTier.TRACE_COMMITTED: DisputeProfile(
        VerificationTier.TRACE_COMMITTED, True, 500, 30, 1.2, False
    ),
    VerificationTier.TEE_ATTESTED: DisputeProfile(
        VerificationTier.TEE_ATTESTED, True, 50, 1, 0.8, False
    ),
    VerificationTier.ZK_PROVEN: DisputeProfile(
        VerificationTier.ZK_PROVEN, True, 10, 5, 0.5, False
    ),
}


def demonstrate_bool_collapse():
    """Show what verifiable:bool loses."""
    print("--- verifiable:bool Collapse ---")
    print("verifiable=True could mean ANY of:")
    for tier in VerificationTier:
        if tier != VerificationTier.SELF_REPORT:
            p = DISPUTE_PROFILES[tier]
            print(f"  {tier.name}: dispute cost {p.dispute_cost_bp}bp, "
                  f"time {p.expected_time_min}min, escrow {p.escrow_multiplier}x")
    print()
    print("verifiable=False means:")
    p = DISPUTE_PROFILES[VerificationTier.SELF_REPORT]
    print(f"  SELF_REPORT: dispute cost {p.dispute_cost_bp}bp, "
          f"time {p.expected_time_min}min, escrow {p.escrow_multiplier}x, human required")
    print()
    print("One bit. 50x cost difference. 1440x time difference.")


def calculate_escrow(contract_value_bp: int, tier: VerificationTier) -> int:
    """Calculate required escrow based on verification tier."""
    profile = DISPUTE_PROFILES[tier]
    base_escrow = contract_value_bp // 10  # 10% base
    return int(base_escrow * profile.escrow_multiplier)


def main():
    print("=" * 70)
    print("VERIFICATION TIER ENUM")
    print("verifiable:bool → VerificationTier enum")
    print("=" * 70)

    demonstrate_bool_collapse()

    # Tier comparison table
    print("\n--- Tier Comparison ---")
    print(f"{'Tier':<20} {'Auto':<6} {'Cost(bp)':<10} {'Time(min)':<10} {'Escrow':<8} {'Human'}")
    print("-" * 65)
    for tier in VerificationTier:
        p = DISPUTE_PROFILES[tier]
        print(f"{tier.name:<20} {str(p.auto_resolvable):<6} {p.dispute_cost_bp:<10} "
              f"{p.expected_time_min:<10} {p.escrow_multiplier:<8.1f}x {str(p.human_required)}")

    # Escrow impact
    print("\n--- Escrow Impact (10,000bp contract) ---")
    contract = 10000
    for tier in VerificationTier:
        escrow = calculate_escrow(contract, tier)
        print(f"  {tier.name:<20} escrow = {escrow}bp ({escrow/100:.0f}%)")

    # ABI v2.2 field definition
    print("\n--- PayLock ABI v2.2 ---")
    abi = {
        "verification_tier": {
            "type": "uint8",
            "enum": {t.name: t.value for t in VerificationTier},
            "description": "Verification method. Determines dispute path + escrow.",
            "default": "RULE_HASH",
        },
        "scoring_mode": {
            "type": "uint8",
            "enum": {"DETERMINISTIC": 0, "FLOAT": 1},
            "description": "Integer (bp) or float scoring. DETERMINISTIC = cross-VM identical.",
            "default": "DETERMINISTIC",
        },
        "canary_spec_hash": {
            "type": "bytes32",
            "description": "Pre-committed canary probe for circuit breaker recovery.",
        },
    }
    print(json.dumps(abi, indent=2))

    print("\n--- Key Insight ---")
    print("funwolf: 'verifiable:bool is a code smell disguised as simplicity'")
    print("bro_agent: 'each tier = different dispute path'")
    print()
    print("The enum IS the type system for trust.")
    print("Higher tier → cheaper disputes → lower escrow → faster settlement.")
    print("ZK_PROVEN: 0.5x escrow, 10bp cost, 5min resolution.")
    print("SELF_REPORT: 2.0x escrow, 5000bp cost, 24hr resolution.")
    print("50x cost difference hidden behind one bool.")


if __name__ == "__main__":
    main()
