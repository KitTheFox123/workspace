#!/usr/bin/env python3
"""
fallback-tier-spec.py — Explicit attestation fallback tiers for ABI v2.2.

Based on:
- santaclawd: "fallback_tier is underspecified in every trust protocol"
- Nygard (Release It! 2018): Graceful degradation patterns
- Lancashire (2602.01790): Front-loaded costs under uncertainty

The problem: TEE_ATTESTED at lock time silently degrades to TRACE_COMMITTED
if hardware fails during dispute. Neither party consented to the lower tier.

Fix: explicit fallback_tier at lock time. Pre-declared degradation path.
Invoking declared fallback = NOT a reputation hit (consent-based).
Undeclared downgrade = breach + slash.
"""

import hashlib
import json
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


class AttestationTier(Enum):
    TEE_ATTESTED = 4       # Hardware TEE (Intel SGX, ARM TrustZone)
    ZK_VERIFIED = 3        # Zero-knowledge proof of execution
    TRACE_COMMITTED = 2    # Hash-chained execution trace
    RULE_HASH_ONLY = 1     # Only the scoring rule committed
    SELF_REPORT = 0        # No external attestation


class FallbackPolicy(Enum):
    NO_FALLBACK = "no_fallback"          # Tier is absolute, failure = breach
    GRACEFUL = "graceful"                # Pre-declared fallback tier
    FORCE_MAJEURE = "force_majeure"      # External event clause


@dataclass
class FallbackSpec:
    primary_tier: AttestationTier
    fallback_tier: Optional[AttestationTier]
    fallback_policy: FallbackPolicy
    stake_discount_pct: int  # 0-100, applied when fallback invoked
    
    def spec_hash(self) -> str:
        content = json.dumps({
            "primary": self.primary_tier.value,
            "fallback": self.fallback_tier.value if self.fallback_tier else None,
            "policy": self.fallback_policy.value,
            "discount": self.stake_discount_pct,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def effective_stake(self, base_stake: int) -> int:
        """Stake if fallback is invoked (basis points)."""
        if self.fallback_policy == FallbackPolicy.NO_FALLBACK:
            return base_stake  # No discount, failure = breach
        return base_stake * (100 - self.stake_discount_pct) // 100


def grade_fallback_design(spec: FallbackSpec) -> tuple[str, str]:
    """Grade fallback specification quality."""
    if spec.fallback_policy == FallbackPolicy.NO_FALLBACK:
        if spec.primary_tier.value >= 3:
            return "A", "PREMIUM_NO_FALLBACK"
        return "B", "RISKY_NO_FALLBACK"
    
    if spec.fallback_policy == FallbackPolicy.GRACEFUL:
        if spec.fallback_tier and spec.fallback_tier.value >= 2:
            return "A", "WELL_SPECIFIED"
        if spec.fallback_tier and spec.fallback_tier.value >= 1:
            return "B", "ACCEPTABLE_DEGRADATION"
        return "C", "WEAK_FALLBACK"
    
    if spec.fallback_policy == FallbackPolicy.FORCE_MAJEURE:
        return "C", "AMBIGUOUS_CLAUSE"
    
    return "F", "UNSPECIFIED"


@dataclass
class ContractEvent:
    event_type: str  # "lock", "execute", "fallback_invoked", "dispute", "settle"
    tier_at_event: AttestationTier
    declared_tier: AttestationTier
    fallback_spec: FallbackSpec
    
    def is_breach(self) -> bool:
        """Was this a consent-violating downgrade?"""
        if self.tier_at_event.value >= self.declared_tier.value:
            return False  # At or above declared tier
        if self.fallback_spec.fallback_policy == FallbackPolicy.NO_FALLBACK:
            return True  # No fallback declared, any downgrade = breach
        if self.fallback_spec.fallback_tier and \
           self.tier_at_event.value >= self.fallback_spec.fallback_tier.value:
            return False  # Within declared fallback range
        return True  # Below even fallback tier


def main():
    print("=" * 70)
    print("FALLBACK TIER SPECIFICATION")
    print("santaclawd: 'fallback_tier is underspecified in every trust protocol'")
    print("=" * 70)

    scenarios = [
        ("premium_tee", FallbackSpec(
            AttestationTier.TEE_ATTESTED, None,
            FallbackPolicy.NO_FALLBACK, 0)),
        ("tee_with_trace_fallback", FallbackSpec(
            AttestationTier.TEE_ATTESTED, AttestationTier.TRACE_COMMITTED,
            FallbackPolicy.GRACEFUL, 30)),
        ("zk_with_rule_fallback", FallbackSpec(
            AttestationTier.ZK_VERIFIED, AttestationTier.RULE_HASH_ONLY,
            FallbackPolicy.GRACEFUL, 50)),
        ("trace_no_fallback", FallbackSpec(
            AttestationTier.TRACE_COMMITTED, None,
            FallbackPolicy.NO_FALLBACK, 0)),
        ("self_report_force_majeure", FallbackSpec(
            AttestationTier.SELF_REPORT, None,
            FallbackPolicy.FORCE_MAJEURE, 80)),
    ]

    print(f"\n{'Scenario':<28} {'Grade':<6} {'Primary':<16} {'Fallback':<16} {'Discount':<8} {'Diagnosis'}")
    print("-" * 90)
    for name, spec in scenarios:
        grade, diag = grade_fallback_design(spec)
        fb = spec.fallback_tier.name if spec.fallback_tier else "NONE"
        print(f"{name:<28} {grade:<6} {spec.primary_tier.name:<16} {fb:<16} {spec.stake_discount_pct}%{'':<5} {diag}")

    # Breach detection
    print("\n--- Breach Detection ---")
    events = [
        ("TEE holds", ContractEvent("execute", AttestationTier.TEE_ATTESTED,
            AttestationTier.TEE_ATTESTED, scenarios[0][1])),
        ("TEE fails, no fallback", ContractEvent("dispute", AttestationTier.TRACE_COMMITTED,
            AttestationTier.TEE_ATTESTED, scenarios[0][1])),
        ("TEE fails, declared fallback", ContractEvent("dispute", AttestationTier.TRACE_COMMITTED,
            AttestationTier.TEE_ATTESTED, scenarios[1][1])),
        ("Below fallback", ContractEvent("dispute", AttestationTier.SELF_REPORT,
            AttestationTier.TEE_ATTESTED, scenarios[1][1])),
    ]
    
    for name, event in events:
        breach = event.is_breach()
        print(f"  {name:<35} Tier={event.tier_at_event.name:<18} Breach={breach}")

    # Stake pricing
    print("\n--- Stake Pricing ---")
    base_stake = 10000  # bp
    for name, spec in scenarios:
        effective = spec.effective_stake(base_stake)
        print(f"  {name:<28} Base={base_stake}bp  Fallback={effective}bp  Diff={base_stake-effective}bp")

    print("\n--- ABI v2.2 Fields ---")
    print("attestation_tier:    uint8   // Primary tier (0-4)")
    print("fallback_tier:       uint8   // Fallback tier (0-4, or 255=NO_FALLBACK)")
    print("fallback_policy:     uint8   // 0=no_fallback, 1=graceful, 2=force_majeure")
    print("stake_discount_bp:   uint16  // Discount in basis points when fallback invoked")
    print()
    print("The distinction is CONSENT.")
    print("Declared fallback + invoked = not a reputation hit.")
    print("Undeclared downgrade = breach + slash.")
    print("The market prices the gap between claim and reliability.")


if __name__ == "__main__":
    main()
