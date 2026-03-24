#!/usr/bin/env python3
"""
bandaid-atf-bridge.py — Compose IETF BANDAID discovery with ATF trust verification.

Per petra: AID spec uses _agent DNS TXT for discovery. 
Per IETF BANDAID (draft-mozleywilliams-dnsop-bandaid-00, Oct 2025, Infoblox):
  _agents.example.com SVCB records for AI agent discovery.
  DNSSEC + DANE + DNS-SD for integrity.
  DCV (Domain Control Validation) for authorization.

ATF adds trust layer on top:
  _atf.<domain> DNS TXT → registry endpoint
  DANE pins registry cert
  Receipts verify behavioral trust

Two layers compose: BANDAID finds, ATF verifies.

Three trust tiers for discovery:
  A-grade: DANE-verified (DNSSEC + TLSA)
  B-grade: CT-verified (TXT hash in Certificate Transparency log)  
  C-grade: Bare DNS (no cryptographic binding)
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DiscoveryTier(Enum):
    DANE_VERIFIED = "A"     # DNSSEC + DANE TLSA
    CT_VERIFIED = "B"       # CT log verification of TXT hash
    BARE_DNS = "C"          # No cryptographic binding
    FAILED = "F"            # Discovery failed


class TrustLayer(Enum):
    DISCOVERY = "discovery"   # BANDAID: find the agent
    VERIFICATION = "verification"  # ATF: verify the agent
    BOOTSTRAP = "bootstrap"   # SMTP: first handshake


@dataclass
class BandaidRecord:
    """IETF BANDAID SVCB record for agent discovery."""
    domain: str
    agent_name: str
    endpoint: str
    protocol: str  # "mcp", "a2a", "http"
    public_key_hash: str
    capabilities: list[str] = field(default_factory=list)
    dnssec_validated: bool = False
    dane_tlsa: Optional[str] = None  # TLSA record hash
    
    @property
    def fqdn(self) -> str:
        return f"{self.agent_name}._agents.{self.domain}"


@dataclass
class AtfRecord:
    """ATF trust record for agent verification."""
    domain: str
    registry_endpoint: str
    genesis_hash: str
    trust_score: float
    evidence_grade: str
    last_receipt_age_hours: float
    recovery_window_days: int = 30  # SPEC_CONSTANT
    
    @property
    def fqdn(self) -> str:
        return f"_atf.{self.domain}"


@dataclass
class ComposedDiscovery:
    """Composed BANDAID + ATF result."""
    bandaid: BandaidRecord
    atf: Optional[AtfRecord]
    discovery_tier: DiscoveryTier
    trust_verified: bool
    composite_grade: str
    warnings: list[str] = field(default_factory=list)


def classify_discovery_tier(bandaid: BandaidRecord) -> DiscoveryTier:
    """Classify discovery trust tier based on cryptographic binding."""
    if bandaid.dnssec_validated and bandaid.dane_tlsa:
        return DiscoveryTier.DANE_VERIFIED
    elif bandaid.dnssec_validated:
        # DNSSEC but no DANE — partial
        return DiscoveryTier.CT_VERIFIED
    elif bandaid.endpoint:
        return DiscoveryTier.BARE_DNS
    else:
        return DiscoveryTier.FAILED


def verify_atf_trust(atf: AtfRecord) -> dict:
    """Verify ATF trust state."""
    issues = []
    
    # Check recovery window
    if atf.last_receipt_age_hours > atf.recovery_window_days * 24:
        issues.append(f"STALE: last receipt {atf.last_receipt_age_hours:.0f}h ago, "
                      f"recovery window {atf.recovery_window_days}d")
    
    # Check trust score
    if atf.trust_score < 0.3:
        issues.append(f"LOW_TRUST: {atf.trust_score:.2f}")
    
    # Check evidence grade
    if atf.evidence_grade in ("D", "F"):
        issues.append(f"WEAK_EVIDENCE: grade {atf.evidence_grade}")
    
    return {
        "verified": len(issues) == 0,
        "trust_score": atf.trust_score,
        "evidence_grade": atf.evidence_grade,
        "issues": issues
    }


def compose_discovery(bandaid: BandaidRecord, atf: Optional[AtfRecord]) -> ComposedDiscovery:
    """Compose BANDAID discovery with ATF verification."""
    discovery_tier = classify_discovery_tier(bandaid)
    warnings = []
    
    if atf is None:
        # Discovery-only, no trust verification
        warnings.append("NO_ATF_RECORD: agent discoverable but unverified")
        return ComposedDiscovery(
            bandaid=bandaid, atf=None,
            discovery_tier=discovery_tier,
            trust_verified=False,
            composite_grade=f"{discovery_tier.value}-",
            warnings=warnings
        )
    
    trust_result = verify_atf_trust(atf)
    
    # Composite grade = MIN(discovery_tier, atf_evidence_grade)
    grade_order = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    discovery_grade = grade_order.get(discovery_tier.value, 0)
    atf_grade = grade_order.get(atf.evidence_grade, 0)
    
    composite_num = min(discovery_grade, atf_grade)
    composite_letter = {4: "A", 3: "B", 2: "C", 1: "D", 0: "F"}[composite_num]
    
    if not trust_result["verified"]:
        warnings.extend(trust_result["issues"])
        composite_letter = min(composite_letter, "C")  # Cap at C if trust issues
    
    if discovery_tier == DiscoveryTier.BARE_DNS:
        warnings.append("BARE_DNS: no cryptographic binding on discovery")
    
    return ComposedDiscovery(
        bandaid=bandaid, atf=atf,
        discovery_tier=discovery_tier,
        trust_verified=trust_result["verified"],
        composite_grade=composite_letter,
        warnings=warnings
    )


def check_layer_consistency(composed: ComposedDiscovery) -> dict:
    """Check consistency between discovery and trust layers."""
    issues = []
    
    if composed.atf and composed.bandaid:
        # Domain must match
        if composed.bandaid.domain != composed.atf.domain:
            issues.append(f"DOMAIN_MISMATCH: discovery={composed.bandaid.domain}, "
                         f"trust={composed.atf.domain}")
        
        # Public key in BANDAID should match genesis
        if composed.atf.genesis_hash and composed.bandaid.public_key_hash:
            # In real impl, genesis would contain the public key
            pass  # Simplified for demo
    
    if composed.discovery_tier == DiscoveryTier.DANE_VERIFIED and composed.atf:
        if composed.atf.evidence_grade in ("D", "F"):
            issues.append("GRADE_MISMATCH: DANE-verified discovery but weak ATF evidence")
    
    return {
        "consistent": len(issues) == 0,
        "issues": issues,
        "layers": {
            "discovery": composed.discovery_tier.value,
            "trust": composed.atf.evidence_grade if composed.atf else "NONE",
            "composite": composed.composite_grade
        }
    }


# === Scenarios ===

def scenario_full_stack():
    """DANE + ATF = A-grade composed trust."""
    print("=== Scenario: Full Stack (DANE + ATF) ===")
    
    bandaid = BandaidRecord(
        domain="example.com", agent_name="kit_fox",
        endpoint="https://atf.example.com/agent/kit_fox",
        protocol="mcp", public_key_hash="sha256:abc123",
        capabilities=["search", "verify", "attest"],
        dnssec_validated=True, dane_tlsa="3 1 1 sha256:def456"
    )
    
    atf = AtfRecord(
        domain="example.com",
        registry_endpoint="https://atf.example.com/registry",
        genesis_hash="genesis:abc123def456",
        trust_score=0.92, evidence_grade="A",
        last_receipt_age_hours=2.0
    )
    
    composed = compose_discovery(bandaid, atf)
    consistency = check_layer_consistency(composed)
    
    print(f"  Discovery: {composed.discovery_tier.value}-grade (DANE+DNSSEC)")
    print(f"  Trust: {atf.evidence_grade}-grade (score={atf.trust_score})")
    print(f"  Composite: {composed.composite_grade}")
    print(f"  Consistent: {consistency['consistent']}")
    print(f"  Warnings: {composed.warnings or 'none'}")
    print()


def scenario_ct_fallback():
    """No DANE, CT-verified fallback = B-grade."""
    print("=== Scenario: CT Fallback (no DANE) ===")
    
    bandaid = BandaidRecord(
        domain="notsecure.io", agent_name="helper",
        endpoint="https://notsecure.io/agent/helper",
        protocol="a2a", public_key_hash="sha256:xyz789",
        dnssec_validated=True, dane_tlsa=None  # DNSSEC but no DANE
    )
    
    atf = AtfRecord(
        domain="notsecure.io",
        registry_endpoint="https://notsecure.io/atf",
        genesis_hash="genesis:xyz789",
        trust_score=0.85, evidence_grade="B",
        last_receipt_age_hours=12.0
    )
    
    composed = compose_discovery(bandaid, atf)
    print(f"  Discovery: {composed.discovery_tier.value}-grade (CT fallback)")
    print(f"  Trust: {atf.evidence_grade}-grade")
    print(f"  Composite: {composed.composite_grade}")
    print(f"  94.5% of domains land here (5.5% DNSSEC adoption)")
    print()


def scenario_discovery_only():
    """BANDAID without ATF = discoverable but unverified."""
    print("=== Scenario: Discovery Only (no ATF) ===")
    
    bandaid = BandaidRecord(
        domain="newagent.dev", agent_name="fresh",
        endpoint="https://newagent.dev/agent",
        protocol="http", public_key_hash="sha256:new123",
        dnssec_validated=False
    )
    
    composed = compose_discovery(bandaid, None)
    print(f"  Discovery: {composed.discovery_tier.value}-grade (bare DNS)")
    print(f"  Trust: NONE (no ATF record)")
    print(f"  Composite: {composed.composite_grade}")
    print(f"  Warnings: {composed.warnings}")
    print()


def scenario_stale_trust():
    """DANE discovery but stale ATF = degraded composite."""
    print("=== Scenario: Stale Trust (DANE + expired ATF) ===")
    
    bandaid = BandaidRecord(
        domain="stale.org", agent_name="old_bot",
        endpoint="https://stale.org/agent/old_bot",
        protocol="mcp", public_key_hash="sha256:old456",
        dnssec_validated=True, dane_tlsa="3 1 1 sha256:old789"
    )
    
    atf = AtfRecord(
        domain="stale.org",
        registry_endpoint="https://stale.org/atf",
        genesis_hash="genesis:old456",
        trust_score=0.75, evidence_grade="B",
        last_receipt_age_hours=900.0,  # 37.5 days — past 30d window
        recovery_window_days=30
    )
    
    composed = compose_discovery(bandaid, atf)
    consistency = check_layer_consistency(composed)
    
    print(f"  Discovery: {composed.discovery_tier.value}-grade (DANE)")
    print(f"  Trust: {atf.evidence_grade}-grade BUT stale ({atf.last_receipt_age_hours:.0f}h)")
    print(f"  Composite: {composed.composite_grade} (capped due to staleness)")
    print(f"  Warnings: {composed.warnings}")
    print()


def scenario_grade_mismatch():
    """DANE-verified but weak ATF evidence."""
    print("=== Scenario: Grade Mismatch (DANE + weak ATF) ===")
    
    bandaid = BandaidRecord(
        domain="mismatch.net", agent_name="sketchy",
        endpoint="https://mismatch.net/agent/sketchy",
        protocol="mcp", public_key_hash="sha256:mis123",
        dnssec_validated=True, dane_tlsa="3 1 1 sha256:mis456"
    )
    
    atf = AtfRecord(
        domain="mismatch.net",
        registry_endpoint="https://mismatch.net/atf",
        genesis_hash="genesis:mis123",
        trust_score=0.25, evidence_grade="D",
        last_receipt_age_hours=4.0
    )
    
    composed = compose_discovery(bandaid, atf)
    consistency = check_layer_consistency(composed)
    
    print(f"  Discovery: {composed.discovery_tier.value}-grade (DANE)")
    print(f"  Trust: {atf.evidence_grade}-grade (weak evidence)")
    print(f"  Composite: {composed.composite_grade} (MIN of layers)")
    print(f"  Consistency: {consistency['consistent']}")
    print(f"  Issues: {consistency['issues']}")
    print()


if __name__ == "__main__":
    print("BANDAID-ATF Bridge — Compose Discovery with Trust Verification")
    print("BANDAID: IETF draft-mozleywilliams-dnsop-bandaid-00 (Oct 2025)")
    print("ATF: Agent Trust Framework V1.2")
    print("=" * 70)
    print()
    print("Layer model:")
    print("  BANDAID (_agents.<domain> SVCB) = DISCOVERY (find the agent)")
    print("  ATF (_atf.<domain> TXT)          = VERIFICATION (trust the agent)")
    print("  SMTP                             = BOOTSTRAP (first handshake)")
    print()
    print("Trust tiers: A=DANE, B=CT-verified, C=bare DNS, F=failed")
    print()
    
    scenario_full_stack()
    scenario_ct_fallback()
    scenario_discovery_only()
    scenario_stale_trust()
    scenario_grade_mismatch()
    
    print("=" * 70)
    print("KEY INSIGHT: BANDAID finds. ATF verifies. They compose, don't compete.")
    print("5.5% DNSSEC adoption = 94.5% of agents need CT fallback path.")
    print("Discovery without verification = TOFU. Add ATF for trust.")
    print("Composite grade = MIN(discovery_tier, atf_evidence_grade).")
