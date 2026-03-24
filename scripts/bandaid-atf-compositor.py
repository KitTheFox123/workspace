#!/usr/bin/env python3
"""
bandaid-atf-compositor.py — Compose BANDAID discovery with ATF trust layer.

Per petra: AID spec uses _agent DNS TXT for discovery (aid.agentcommunity.org).
Per IETF: BANDAID (draft-mozleywilliams-dnsop-bandaid-00, Oct 2025) — Infoblox/Deutsche Telekom.
  _agents.example.com with SVCB records + DNSSEC + DANE.

Key insight: BANDAID = discovery (WHO is there), ATF = trust (SHOULD I trust them).
Different layers, same DNS plumbing. Compose, don't compete.

Stack:
  Layer 1: DNS TXT (_atf.domain) — ATF registry endpoint discovery (DMARC model)
  Layer 2: SVCB (_agents.domain) — BANDAID capability advertisement
  Layer 3: DANE (TLSA) — Pin registry TLS certificate (5.5% DNSSEC adoption)
  Layer 4: CT log fallback — Auditable trust when DANE unavailable (94.5%)
  Layer 5: ATF genesis — Trust evaluation via receipts + behavioral attestation
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DiscoveryMethod(Enum):
    BANDAID_SVCB = "BANDAID_SVCB"     # IETF draft, SVCB records
    ATF_TXT = "ATF_TXT"               # _atf.<domain> TXT record
    AID_TXT = "AID_TXT"               # _agent.<domain> TXT record
    WELLKNOWN = "WELLKNOWN"            # /.well-known/atf fallback


class TrustLevel(Enum):
    VERIFIED = "VERIFIED"       # DANE + DNSSEC validated
    AUDITABLE = "AUDITABLE"     # CT log verified, no DANE
    DISCOVERED = "DISCOVERED"   # Found but not trust-verified
    UNKNOWN = "UNKNOWN"         # No discovery records


class CompatibilityStatus(Enum):
    COMPOSABLE = "COMPOSABLE"       # Both layers work together
    REDUNDANT = "REDUNDANT"         # Overlapping records, pick one
    CONFLICTING = "CONFLICTING"     # Records disagree
    PARTIAL = "PARTIAL"             # One layer present, other missing


@dataclass
class DNSRecord:
    domain: str
    record_type: str   # TXT, SVCB, TLSA
    value: str
    dnssec_signed: bool = False
    ttl: int = 3600


@dataclass
class DiscoveryResult:
    domain: str
    method: DiscoveryMethod
    endpoint: Optional[str] = None
    capabilities: list = field(default_factory=list)
    public_key_hash: Optional[str] = None
    trust_level: TrustLevel = TrustLevel.UNKNOWN
    dane_available: bool = False
    ct_log_verified: bool = False


@dataclass
class CompositionResult:
    domain: str
    bandaid_result: Optional[DiscoveryResult] = None
    atf_result: Optional[DiscoveryResult] = None
    compatibility: CompatibilityStatus = CompatibilityStatus.PARTIAL
    effective_trust: TrustLevel = TrustLevel.UNKNOWN
    issues: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)


def discover_bandaid(domain: str, records: list[DNSRecord]) -> Optional[DiscoveryResult]:
    """Simulate BANDAID discovery via SVCB records."""
    svcb = [r for r in records if r.record_type == "SVCB" and "_agents" in r.domain]
    if not svcb:
        return None
    
    rec = svcb[0]
    # Parse SVCB-like value
    endpoint = f"https://{domain}/.well-known/agents"
    caps = ["chat", "task", "search"]  # From SVCB alpn hints
    
    trust = TrustLevel.DISCOVERED
    dane = any(r.record_type == "TLSA" for r in records)
    dnssec = rec.dnssec_signed
    
    if dane and dnssec:
        trust = TrustLevel.VERIFIED
    elif dnssec:
        trust = TrustLevel.AUDITABLE
    
    return DiscoveryResult(
        domain=domain,
        method=DiscoveryMethod.BANDAID_SVCB,
        endpoint=endpoint,
        capabilities=caps,
        trust_level=trust,
        dane_available=dane
    )


def discover_atf(domain: str, records: list[DNSRecord]) -> Optional[DiscoveryResult]:
    """Simulate ATF discovery via _atf TXT records."""
    txt = [r for r in records if r.record_type == "TXT" and "_atf" in r.domain]
    if not txt:
        return None
    
    rec = txt[0]
    # Parse ATF TXT: v=ATF1; endpoint=https://...; registry_hash=...
    parts = dict(p.strip().split("=", 1) for p in rec.value.split(";") if "=" in p)
    
    endpoint = parts.get("endpoint", f"https://{domain}/atf")
    registry_hash = parts.get("registry_hash", "")
    
    trust = TrustLevel.DISCOVERED
    dane = any(r.record_type == "TLSA" for r in records)
    ct = any("ct_log" in r.value for r in records if r.record_type == "TXT")
    
    if dane and rec.dnssec_signed:
        trust = TrustLevel.VERIFIED
    elif ct or rec.dnssec_signed:
        trust = TrustLevel.AUDITABLE
    
    return DiscoveryResult(
        domain=domain,
        method=DiscoveryMethod.ATF_TXT,
        endpoint=endpoint,
        public_key_hash=registry_hash,
        trust_level=trust,
        dane_available=dane,
        ct_log_verified=ct
    )


def compose(domain: str, records: list[DNSRecord]) -> CompositionResult:
    """Compose BANDAID + ATF discovery for a domain."""
    bandaid = discover_bandaid(domain, records)
    atf = discover_atf(domain, records)
    
    result = CompositionResult(domain=domain, bandaid_result=bandaid, atf_result=atf)
    
    if bandaid and atf:
        # Both present — check compatibility
        if bandaid.dane_available == atf.dane_available:
            result.compatibility = CompatibilityStatus.COMPOSABLE
            # Effective trust = best of both
            trust_order = [TrustLevel.VERIFIED, TrustLevel.AUDITABLE, 
                          TrustLevel.DISCOVERED, TrustLevel.UNKNOWN]
            bt = trust_order.index(bandaid.trust_level)
            at = trust_order.index(atf.trust_level)
            result.effective_trust = trust_order[min(bt, at)]
            result.recommendations.append(
                "COMPOSABLE: BANDAID for capability discovery, ATF for trust evaluation"
            )
        else:
            result.compatibility = CompatibilityStatus.CONFLICTING
            result.issues.append(
                f"DANE mismatch: BANDAID={bandaid.dane_available}, ATF={atf.dane_available}"
            )
            # Conservative: take lower trust
            result.effective_trust = TrustLevel.DISCOVERED
    
    elif bandaid and not atf:
        result.compatibility = CompatibilityStatus.PARTIAL
        result.effective_trust = bandaid.trust_level
        result.recommendations.append(
            "PARTIAL: BANDAID discovery present, ATF trust layer missing. "
            "Agent discoverable but trust unverifiable."
        )
    
    elif atf and not bandaid:
        result.compatibility = CompatibilityStatus.PARTIAL
        result.effective_trust = atf.trust_level
        result.recommendations.append(
            "PARTIAL: ATF trust layer present, BANDAID discovery missing. "
            "Trust verifiable but capabilities unknown."
        )
    
    else:
        result.compatibility = CompatibilityStatus.PARTIAL
        result.effective_trust = TrustLevel.UNKNOWN
        result.issues.append("No discovery records found for either layer")
    
    return result


# === Scenarios ===

def scenario_full_stack():
    """Both BANDAID + ATF + DANE + DNSSEC — gold standard."""
    print("=== Scenario: Full Stack (BANDAID + ATF + DANE) ===")
    records = [
        DNSRecord("_agents.example.com", "SVCB", "1 . alpn=h2 port=443", dnssec_signed=True),
        DNSRecord("_atf.example.com", "TXT", 
                  "v=ATF1; endpoint=https://example.com/atf; registry_hash=abc123", 
                  dnssec_signed=True),
        DNSRecord("_443._tcp.example.com", "TLSA", "3 1 1 abc..."),
    ]
    result = compose("example.com", records)
    print(f"  Compatibility: {result.compatibility.value}")
    print(f"  Effective trust: {result.effective_trust.value}")
    print(f"  BANDAID: {result.bandaid_result.trust_level.value if result.bandaid_result else 'N/A'}")
    print(f"  ATF: {result.atf_result.trust_level.value if result.atf_result else 'N/A'}")
    for r in result.recommendations:
        print(f"  → {r}")
    print()


def scenario_atf_only():
    """ATF without BANDAID — trust without discovery."""
    print("=== Scenario: ATF Only (No BANDAID) ===")
    records = [
        DNSRecord("_atf.agent.io", "TXT",
                  "v=ATF1; endpoint=https://agent.io/atf; registry_hash=def456",
                  dnssec_signed=True),
    ]
    result = compose("agent.io", records)
    print(f"  Compatibility: {result.compatibility.value}")
    print(f"  Effective trust: {result.effective_trust.value}")
    for r in result.recommendations:
        print(f"  → {r}")
    print()


def scenario_no_dnssec():
    """94.5% case — no DNSSEC, CT log fallback."""
    print("=== Scenario: No DNSSEC (94.5% of domains) ===")
    records = [
        DNSRecord("_agents.nodane.com", "SVCB", "1 . alpn=h2", dnssec_signed=False),
        DNSRecord("_atf.nodane.com", "TXT",
                  "v=ATF1; endpoint=https://nodane.com/atf; ct_log=verified",
                  dnssec_signed=False),
    ]
    result = compose("nodane.com", records)
    print(f"  Compatibility: {result.compatibility.value}")
    print(f"  Effective trust: {result.effective_trust.value}")
    print(f"  BANDAID trust: {result.bandaid_result.trust_level.value}")
    print(f"  ATF trust: {result.atf_result.trust_level.value}")
    print(f"  Key: AUDITABLE < VERIFIED but >> UNKNOWN")
    print()


def scenario_conflicting():
    """DANE present for one layer but not other."""
    print("=== Scenario: Conflicting DANE Status ===")
    records = [
        DNSRecord("_agents.mixed.org", "SVCB", "1 . alpn=h2", dnssec_signed=True),
        DNSRecord("_443._tcp.mixed.org", "TLSA", "3 1 1 xyz..."),
        DNSRecord("_atf.mixed.org", "TXT",
                  "v=ATF1; endpoint=https://mixed.org/atf",
                  dnssec_signed=False),  # Not DNSSEC signed!
    ]
    result = compose("mixed.org", records)
    print(f"  Compatibility: {result.compatibility.value}")
    print(f"  Effective trust: {result.effective_trust.value}")
    for i in result.issues:
        print(f"  ⚠ {i}")
    print()


if __name__ == "__main__":
    print("BANDAID + ATF Compositor — Layer Composition for Agent Discovery + Trust")
    print("Per IETF draft-mozleywilliams-dnsop-bandaid-00 (Oct 2025)")
    print("=" * 70)
    print()
    print("Layers:")
    print("  BANDAID (IETF) = Discovery: WHO is there, WHAT can they do")
    print("  ATF            = Trust: SHOULD I trust them, WHAT have they done")
    print("  DANE/DNSSEC    = Verification: IS this record authentic (5.5%)")
    print("  CT log         = Auditability: WAS this record published (94.5%)")
    print()
    
    scenario_full_stack()
    scenario_atf_only()
    scenario_no_dnssec()
    scenario_conflicting()
    
    print("=" * 70)
    print("KEY INSIGHT: BANDAID and ATF solve different problems.")
    print("BANDAID = discovery + capabilities. ATF = trust + behavioral evidence.")
    print("Compose via DNS plumbing. Same domain, different subdomains.")
    print("Progressive enhancement: DANE(5.5%) > CT(94.5%) > DISCOVERED(100%)")
