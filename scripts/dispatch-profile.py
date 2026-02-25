#!/usr/bin/env python3
"""
dispatch-profile.py — Dispatch profile schema for agent service contracts.

Based on the Clawk thread insight: bind evidence type, signature path,
and settlement trigger at contract creation, not at dispute time.

Hart (1995): contracts are always incomplete. Dispatch profiles handle this
by specifying MECHANISMS for resolving unknowns, not exhaustive contingencies.

Usage:
    python3 dispatch-profile.py demo        # Show example profiles
    python3 dispatch-profile.py validate FILE  # Validate a profile JSON
    python3 dispatch-profile.py select       # Interactive profile selector
"""

import json
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum


class VerifiabilityLevel(str, Enum):
    """How verifiable is the deliverable?"""
    DETERMINISTIC = "deterministic"   # Machine-checkable (code tests, hash match)
    MEASURABLE = "measurable"         # Metric-based (engagement, uptime)
    SUBJECTIVE = "subjective"         # Requires judgment (research quality, creative)


class SettlementMode(str, Enum):
    """When does payment release?"""
    IMMEDIATE = "immediate"           # On delivery confirmation
    WINDOW = "window"                 # After dispute window expires
    ORACLE = "oracle"                 # After external attestation
    MILESTONE = "milestone"           # Staged release


class EvidenceType(str, Enum):
    """What constitutes proof of delivery?"""
    HASH = "hash"                     # Content hash matches commitment
    TX = "tx"                         # On-chain transaction exists
    ATTESTATION = "attestation"       # Signed attestation from verifier
    METRIC = "metric"                 # Measurable target achieved
    SIGNATURE = "signature"           # Deliverable signed by provider


@dataclass
class DisputeConfig:
    """How disputes are resolved."""
    window_hours: int = 48
    min_attesters: int = 2
    attester_diversity_required: bool = True  # From wisdom-of-crowds research
    auto_release_on_timeout: bool = True
    max_escalation_rounds: int = 1
    reputation_weighted: bool = True


@dataclass
class DispatchProfile:
    """A dispatch profile binds all contract parameters at creation time."""
    
    # Identity
    profile_id: str
    version: str = "0.1"
    
    # What
    deliverable_type: str = ""        # e.g., "research", "code", "data"
    verifiability: VerifiabilityLevel = VerifiabilityLevel.SUBJECTIVE
    
    # Evidence
    evidence_types: list[EvidenceType] = field(default_factory=lambda: [EvidenceType.ATTESTATION])
    evidence_threshold: int = 1       # How many evidence items needed
    
    # Settlement
    settlement_mode: SettlementMode = SettlementMode.WINDOW
    settlement_currency: str = "SOL"
    settlement_amount: float = 0.0
    
    # Dispute
    dispute: DisputeConfig = field(default_factory=DisputeConfig)
    
    # Signatures
    provider_did: str = ""
    buyer_did: str = ""
    escrow_agent_did: str = ""
    
    def validate(self) -> list[str]:
        """Validate profile consistency. Returns list of errors."""
        errors = []
        
        if not self.profile_id:
            errors.append("profile_id required")
        
        if not self.provider_did or not self.buyer_did:
            errors.append("both provider_did and buyer_did required")
        
        # Verifiability determines sensible settlement
        if self.verifiability == VerifiabilityLevel.DETERMINISTIC:
            if self.settlement_mode == SettlementMode.ORACLE:
                errors.append("deterministic deliverables don't need oracle settlement")
            if EvidenceType.ATTESTATION in self.evidence_types and len(self.evidence_types) == 1:
                errors.append("deterministic deliverables should use hash/tx evidence, not just attestation")
        
        if self.verifiability == VerifiabilityLevel.SUBJECTIVE:
            if self.settlement_mode == SettlementMode.IMMEDIATE:
                errors.append("subjective deliverables should not use immediate settlement (no dispute window)")
            if self.dispute.min_attesters < 2:
                errors.append("subjective deliverables need >= 2 attesters (correlated oracle risk)")
        
        if self.settlement_amount <= 0:
            errors.append("settlement_amount must be positive")
        
        if not self.dispute.attester_diversity_required and self.dispute.min_attesters > 1:
            errors.append("multiple attesters without diversity requirement = expensive groupthink")
        
        return errors
    
    def to_json(self) -> str:
        d = asdict(self)
        return json.dumps(d, indent=2, default=str)
    
    @classmethod
    def from_json(cls, data: str) -> 'DispatchProfile':
        d = json.loads(data)
        d['verifiability'] = VerifiabilityLevel(d['verifiability'])
        d['settlement_mode'] = SettlementMode(d['settlement_mode'])
        d['evidence_types'] = [EvidenceType(e) for e in d['evidence_types']]
        d['dispute'] = DisputeConfig(**d['dispute'])
        return cls(**d)


# Pre-built profiles for common scenarios
PROFILES = {
    "tc3_research": DispatchProfile(
        profile_id="tc3-research-v1",
        deliverable_type="research",
        verifiability=VerifiabilityLevel.SUBJECTIVE,
        evidence_types=[EvidenceType.ATTESTATION, EvidenceType.SIGNATURE],
        evidence_threshold=2,
        settlement_mode=SettlementMode.WINDOW,
        settlement_currency="SOL",
        settlement_amount=0.01,
        dispute=DisputeConfig(
            window_hours=48,
            min_attesters=2,
            attester_diversity_required=True,
            auto_release_on_timeout=True,
        ),
        provider_did="agent:kit",
        buyer_did="agent:gendolf",
        escrow_agent_did="agent:bro_agent",
    ),
    "tc4_deterministic": DispatchProfile(
        profile_id="tc4-tx-anchor-v1",
        deliverable_type="on-chain-anchor",
        verifiability=VerifiabilityLevel.DETERMINISTIC,
        evidence_types=[EvidenceType.TX, EvidenceType.HASH],
        evidence_threshold=1,
        settlement_mode=SettlementMode.IMMEDIATE,
        settlement_currency="SOL",
        settlement_amount=0.12,
        dispute=DisputeConfig(
            window_hours=0,
            min_attesters=0,
            attester_diversity_required=False,
            auto_release_on_timeout=True,
        ),
        provider_did="agent:tbd",
        buyer_did="agent:tbd",
        escrow_agent_did="agent:bro_agent",
    ),
    "code_bounty": DispatchProfile(
        profile_id="code-bounty-v1",
        deliverable_type="code",
        verifiability=VerifiabilityLevel.DETERMINISTIC,
        evidence_types=[EvidenceType.HASH, EvidenceType.SIGNATURE],
        evidence_threshold=1,
        settlement_mode=SettlementMode.IMMEDIATE,
        settlement_currency="USDC",
        settlement_amount=5.0,
        dispute=DisputeConfig(
            window_hours=24,
            min_attesters=1,
            attester_diversity_required=False,
        ),
        provider_did="",
        buyer_did="",
        escrow_agent_did="",
    ),
    "creative_work": DispatchProfile(
        profile_id="creative-v1",
        deliverable_type="creative",
        verifiability=VerifiabilityLevel.SUBJECTIVE,
        evidence_types=[EvidenceType.ATTESTATION],
        evidence_threshold=2,
        settlement_mode=SettlementMode.ORACLE,
        settlement_currency="SOL",
        settlement_amount=0.05,
        dispute=DisputeConfig(
            window_hours=72,
            min_attesters=3,
            attester_diversity_required=True,
            reputation_weighted=True,
        ),
        provider_did="",
        buyer_did="",
        escrow_agent_did="",
    ),
}


def select_profile() -> DispatchProfile:
    """Interactive profile selector based on deliverable characteristics."""
    print("=== Dispatch Profile Selector ===\n")
    
    print("Is the deliverable machine-verifiable?")
    print("  1. Yes — code passes tests, hash matches, tx exists")
    print("  2. Partially — measurable metric (engagement, uptime)")
    print("  3. No — requires human/agent judgment")
    
    choice = input("\nChoice [1-3]: ").strip()
    
    if choice == "1":
        v = VerifiabilityLevel.DETERMINISTIC
        print("\n→ Deterministic. Recommending: immediate settlement, hash/tx evidence.")
        profile = DispatchProfile(
            profile_id="custom-deterministic",
            verifiability=v,
            evidence_types=[EvidenceType.HASH, EvidenceType.TX],
            settlement_mode=SettlementMode.IMMEDIATE,
            dispute=DisputeConfig(window_hours=24, min_attesters=1, attester_diversity_required=False),
        )
    elif choice == "2":
        v = VerifiabilityLevel.MEASURABLE
        print("\n→ Measurable. Recommending: window settlement, metric evidence + attestation.")
        profile = DispatchProfile(
            profile_id="custom-measurable",
            verifiability=v,
            evidence_types=[EvidenceType.METRIC, EvidenceType.ATTESTATION],
            settlement_mode=SettlementMode.WINDOW,
            dispute=DisputeConfig(window_hours=48, min_attesters=2),
        )
    else:
        v = VerifiabilityLevel.SUBJECTIVE
        print("\n→ Subjective. Recommending: oracle settlement, 2+ diverse attesters, 48h window.")
        profile = DispatchProfile(
            profile_id="custom-subjective",
            verifiability=v,
            evidence_types=[EvidenceType.ATTESTATION, EvidenceType.SIGNATURE],
            settlement_mode=SettlementMode.ORACLE,
            dispute=DisputeConfig(window_hours=48, min_attesters=2, attester_diversity_required=True),
        )
    
    return profile


def demo():
    """Show all pre-built profiles and validate them."""
    print("=" * 60)
    print("Dispatch Profile System — Contract Schemas for Agent Services")
    print("=" * 60)
    print("\nInspired by Hart (1995): specify MECHANISMS, not contingencies.\n")
    
    for name, profile in PROFILES.items():
        print(f"--- {name} ---")
        print(f"  Deliverable: {profile.deliverable_type}")
        print(f"  Verifiability: {profile.verifiability.value}")
        print(f"  Evidence: {[e.value for e in profile.evidence_types]}")
        print(f"  Settlement: {profile.settlement_mode.value} ({profile.settlement_amount} {profile.settlement_currency})")
        print(f"  Dispute window: {profile.dispute.window_hours}h, {profile.dispute.min_attesters} attesters")
        
        errors = profile.validate()
        if errors:
            print(f"  ⚠️  Validation: {errors}")
        else:
            print(f"  ✅ Valid")
        print()
    
    # Show what happens with bad configs
    print("--- Intentionally bad profile (subjective + immediate + 1 attester) ---")
    bad = DispatchProfile(
        profile_id="bad-example",
        verifiability=VerifiabilityLevel.SUBJECTIVE,
        settlement_mode=SettlementMode.IMMEDIATE,
        settlement_amount=1.0,
        dispute=DisputeConfig(min_attesters=1),
        provider_did="agent:a",
        buyer_did="agent:b",
    )
    errors = bad.validate()
    print(f"  Errors: {errors}")
    print(f"  (Subjective work + no dispute window + single attester = recipe for conflict)")


def validate_file(filepath: str):
    """Validate a profile from JSON file."""
    with open(filepath) as f:
        profile = DispatchProfile.from_json(f.read())
    
    errors = profile.validate()
    if errors:
        print(f"❌ Invalid profile: {errors}")
        return False
    else:
        print(f"✅ Valid profile: {profile.profile_id}")
        print(f"   {profile.verifiability.value} / {profile.settlement_mode.value} / {profile.settlement_amount} {profile.settlement_currency}")
        return True


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "demo":
        demo()
    elif sys.argv[1] == "validate" and len(sys.argv) > 2:
        validate_file(sys.argv[2])
    elif sys.argv[1] == "select":
        profile = select_profile()
        print(f"\n{profile.to_json()}")
    else:
        print(__doc__)
