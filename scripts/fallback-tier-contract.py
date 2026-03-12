#!/usr/bin/env python3
"""
fallback-tier-contract.py — Pre-declared fallback tiers for agent trust contracts.

Based on:
- Tjong Tjin Tai (SSRN 2018): Force majeure in smart contracts
- santaclawd: "fallback_tier is underspecified in every trust protocol"
- Nygard (Release It! 2018): Circuit breaker degradation

Force majeure requires:
1. Event beyond control (hardware failure)
2. Unforeseeable at time of contract
3. Pre-disclosed possibility (fallback_tier declaration)

Silent degradation = fraud. Disclosed degradation = resilience.
"""

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ExecutionTier(Enum):
    TEE_ATTESTED = "TEE_ATTESTED"           # Highest: TEE + zkVM proof
    TRACE_COMMITTED = "TRACE_COMMITTED"     # Mid: execution trace hash
    RULE_HASH_ONLY = "RULE_HASH_ONLY"       # Low: only rule identity
    SELF_REPORT = "SELF_REPORT"             # Lowest: trust-me


class FallbackPolicy(Enum):
    NO_FALLBACK = "NO_FALLBACK"             # Tier absolute, failure = breach
    GRACEFUL = "GRACEFUL"                   # Pre-declared lower tier
    FORCE_MAJEURE = "FORCE_MAJEURE"         # Hardware failure clause


@dataclass
class TierDeclaration:
    primary_tier: ExecutionTier
    fallback_tier: Optional[ExecutionTier]
    fallback_policy: FallbackPolicy
    fallback_stake_discount_bp: int  # Basis points discount on stake
    
    def declaration_hash(self) -> str:
        content = json.dumps({
            "primary": self.primary_tier.value,
            "fallback": self.fallback_tier.value if self.fallback_tier else None,
            "policy": self.fallback_policy.value,
            "discount_bp": self.fallback_stake_discount_bp,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class DegradationEvent:
    original_tier: ExecutionTier
    actual_tier: ExecutionTier
    declared_fallback: Optional[ExecutionTier]
    reason: str


def classify_degradation(event: DegradationEvent, declaration: TierDeclaration) -> tuple[str, str, bool]:
    """Classify degradation as excused or breach.
    
    Returns: (grade, classification, slashable)
    """
    if event.actual_tier == event.original_tier:
        return "A", "NO_DEGRADATION", False
    
    if declaration.fallback_policy == FallbackPolicy.NO_FALLBACK:
        return "F", "BREACH_NO_FALLBACK", True
    
    if event.actual_tier == declaration.fallback_tier:
        if declaration.fallback_policy == FallbackPolicy.FORCE_MAJEURE:
            return "B", "EXCUSED_FORCE_MAJEURE", False
        return "B", "DECLARED_FALLBACK", False
    
    # Degraded beyond declared fallback
    if declaration.fallback_tier and tier_rank(event.actual_tier) < tier_rank(declaration.fallback_tier):
        return "D", "BEYOND_DECLARED_FALLBACK", True
    
    # Undeclared degradation
    return "F", "SILENT_DEGRADATION", True


def tier_rank(tier: ExecutionTier) -> int:
    ranks = {
        ExecutionTier.TEE_ATTESTED: 4,
        ExecutionTier.TRACE_COMMITTED: 3,
        ExecutionTier.RULE_HASH_ONLY: 2,
        ExecutionTier.SELF_REPORT: 1,
    }
    return ranks[tier]


def compute_adjusted_stake(base_stake_bp: int, declaration: TierDeclaration, 
                            degraded: bool) -> int:
    """Compute stake after fallback discount."""
    if not degraded:
        return base_stake_bp
    return base_stake_bp - declaration.fallback_stake_discount_bp


def main():
    print("=" * 70)
    print("FALLBACK TIER CONTRACT")
    print("Tjong Tjin Tai (SSRN 2018): Force Majeure in Smart Contracts")
    print("=" * 70)

    scenarios = [
        ("honest_tee", 
         TierDeclaration(ExecutionTier.TEE_ATTESTED, ExecutionTier.TRACE_COMMITTED, 
                         FallbackPolicy.FORCE_MAJEURE, 2000),
         DegradationEvent(ExecutionTier.TEE_ATTESTED, ExecutionTier.TEE_ATTESTED, 
                          ExecutionTier.TRACE_COMMITTED, "no failure")),
        
        ("tee_hardware_fail_declared",
         TierDeclaration(ExecutionTier.TEE_ATTESTED, ExecutionTier.TRACE_COMMITTED,
                         FallbackPolicy.FORCE_MAJEURE, 2000),
         DegradationEvent(ExecutionTier.TEE_ATTESTED, ExecutionTier.TRACE_COMMITTED,
                          ExecutionTier.TRACE_COMMITTED, "SGX hardware failure")),
        
        ("tee_fail_no_fallback",
         TierDeclaration(ExecutionTier.TEE_ATTESTED, None,
                         FallbackPolicy.NO_FALLBACK, 0),
         DegradationEvent(ExecutionTier.TEE_ATTESTED, ExecutionTier.TRACE_COMMITTED,
                          None, "SGX hardware failure")),
        
        ("silent_degradation",
         TierDeclaration(ExecutionTier.TEE_ATTESTED, ExecutionTier.TRACE_COMMITTED,
                         FallbackPolicy.GRACEFUL, 1500),
         DegradationEvent(ExecutionTier.TEE_ATTESTED, ExecutionTier.SELF_REPORT,
                          ExecutionTier.TRACE_COMMITTED, "cost cutting")),
        
        ("graceful_declared",
         TierDeclaration(ExecutionTier.TRACE_COMMITTED, ExecutionTier.RULE_HASH_ONLY,
                         FallbackPolicy.GRACEFUL, 3000),
         DegradationEvent(ExecutionTier.TRACE_COMMITTED, ExecutionTier.RULE_HASH_ONLY,
                          ExecutionTier.RULE_HASH_ONLY, "trace infra outage")),
    ]

    print(f"\n{'Scenario':<30} {'Grade':<6} {'Classification':<25} {'Slash':<6} {'Stake Adj'}")
    print("-" * 80)

    for name, decl, event in scenarios:
        grade, classification, slashable = classify_degradation(event, decl)
        stake = compute_adjusted_stake(10000, decl, event.actual_tier != event.original_tier)
        print(f"{name:<30} {grade:<6} {classification:<25} {'YES' if slashable else 'no':<6} {stake} bp")

    print("\n--- ABI v2.2 Fallback Fields ---")
    print("fallback_tier:           enum(TEE_ATTESTED|TRACE_COMMITTED|RULE_HASH_ONLY|SELF_REPORT|NO_FALLBACK)")
    print("fallback_policy:         enum(NO_FALLBACK|GRACEFUL|FORCE_MAJEURE)")
    print("fallback_stake_discount: uint16  // basis points discount when fallback invoked")
    print("fallback_declaration_hash: bytes32  // committed at lock time")

    print("\n--- Force Majeure Mapping ---")
    print("Legal requirement          → Agent equivalent")
    print("Beyond control             → Hardware failure, API outage")
    print("Unforeseeable              → Not caused by agent's own actions")
    print("Pre-disclosed              → fallback_tier declared at lock")
    print("Proportional               → fallback_stake_discount (partial refund)")
    print()
    print("Key: disclosed degradation = resilience. Silent = fraud.")
    print("Slashing for hardware failure feels wrong IF risk was disclosed.")
    print("Slashing for silent degradation is ALWAYS correct.")


if __name__ == "__main__":
    main()
