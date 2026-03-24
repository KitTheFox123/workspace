#!/usr/bin/env python3
"""
bandaid-interop.py — IETF BANDAID + ATF DNS discovery interoperability.

Per petra: AID spec uses _agent DNS TXT for agent discovery.
Per IETF draft-mozleywilliams-dnsop-bandaid-00 (Oct 2025):
  _agents.<domain> SVCB records for capability discovery.
  DNS-SD + DNSSEC + DANE for integrity.

ATF layer: _atf.<domain> TXT for trust chain discovery.
BANDAID layer: _agents.<domain> SVCB for capability advertisement.

Two layers compose, don't compete:
  BANDAID = "what can this agent do?" (capability)
  ATF     = "should I trust this agent?" (trust chain)

Key insight: BANDAID provides discovery, ATF provides verification.
Like DKIM (authentication) + MX (routing) — different DNS records, same domain.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DiscoveryMethod(Enum):
    BANDAID_SVCB = "BANDAID_SVCB"   # IETF BANDAID _agents.<domain> SVCB
    ATF_TXT = "ATF_TXT"             # ATF _atf.<domain> TXT
    AID_TXT = "AID_TXT"             # .agent community _agent.<domain> TXT
    FALLBACK_HTTPS = "FALLBACK_HTTPS"  # .well-known/atf.json


class SecurityTier(Enum):
    DANE_PINNED = "A"     # DNSSEC + DANE = cryptographic pin
    CT_VERIFIED = "B"     # CT log verification, no DANE
    TLS_ONLY = "C"        # HTTPS but no DNSSEC/DANE
    UNSIGNED = "D"        # DNS without DNSSEC
    UNREACHABLE = "F"     # Discovery failed


@dataclass
class BandaidRecord:
    """IETF BANDAID SVCB record for agent capability discovery."""
    domain: str
    service_name: str          # e.g., "chat", "task", "atf"
    target: str                # endpoint hostname
    port: int = 443
    protocol: str = "h2"       # HTTP/2, HTTP/3
    priority: int = 1
    alpn: list = field(default_factory=lambda: ["h2", "h3"])
    capabilities: list = field(default_factory=list)  # MCP tools, etc.
    
    @property
    def fqdn(self):
        return f"{self.service_name}._agents.{self.domain}"
    
    def to_svcb(self) -> str:
        """Format as SVCB record."""
        alpn_str = ",".join(self.alpn)
        return (f"{self.fqdn} IN SVCB {self.priority} {self.target} "
                f"port={self.port} alpn={alpn_str}")


@dataclass
class AtfTxtRecord:
    """ATF _atf.<domain> TXT record for trust chain discovery."""
    domain: str
    registry_endpoint: str
    genesis_hash: str
    schema_version: str = "1.2"
    revocation_endpoint: Optional[str] = None
    bridge_endpoints: list = field(default_factory=list)
    
    @property
    def fqdn(self):
        return f"_atf.{self.domain}"
    
    def to_txt(self) -> str:
        """Format as DNS TXT record."""
        parts = [
            f"v=ATF1",
            f"reg={self.registry_endpoint}",
            f"genesis={self.genesis_hash[:16]}",
            f"schema={self.schema_version}"
        ]
        if self.revocation_endpoint:
            parts.append(f"revoke={self.revocation_endpoint}")
        return f'{self.fqdn} IN TXT "{"; ".join(parts)}"'


@dataclass
class CompositeDiscovery:
    """Combined BANDAID + ATF discovery result."""
    domain: str
    bandaid: Optional[BandaidRecord] = None
    atf: Optional[AtfTxtRecord] = None
    dnssec_validated: bool = False
    dane_pinned: bool = False
    ct_logged: bool = False
    discovery_timestamp: float = 0.0
    
    @property
    def security_tier(self) -> SecurityTier:
        if self.dnssec_validated and self.dane_pinned:
            return SecurityTier.DANE_PINNED
        if self.ct_logged:
            return SecurityTier.CT_VERIFIED
        if self.atf or self.bandaid:
            return SecurityTier.TLS_ONLY
        if not self.dnssec_validated:
            return SecurityTier.UNSIGNED
        return SecurityTier.UNREACHABLE
    
    @property
    def completeness(self) -> dict:
        """What percentage of discovery is available."""
        checks = {
            "bandaid_capability": self.bandaid is not None,
            "atf_trust_chain": self.atf is not None,
            "dnssec": self.dnssec_validated,
            "dane": self.dane_pinned,
            "ct_logged": self.ct_logged
        }
        score = sum(checks.values()) / len(checks)
        return {"checks": checks, "score": round(score, 2)}


def discover_domain(domain: str, bandaid: Optional[BandaidRecord] = None,
                    atf: Optional[AtfTxtRecord] = None,
                    dnssec: bool = False, dane: bool = False,
                    ct: bool = False) -> CompositeDiscovery:
    """Simulate composite discovery for a domain."""
    return CompositeDiscovery(
        domain=domain,
        bandaid=bandaid,
        atf=atf,
        dnssec_validated=dnssec,
        dane_pinned=dane,
        ct_logged=ct,
        discovery_timestamp=time.time()
    )


def validate_interop(discovery: CompositeDiscovery) -> dict:
    """Validate BANDAID + ATF interoperability."""
    issues = []
    recommendations = []
    
    if discovery.bandaid and not discovery.atf:
        issues.append("BANDAID capability found but no ATF trust chain — capability without trust")
        recommendations.append("Add _atf.<domain> TXT record for trust verification")
    
    if discovery.atf and not discovery.bandaid:
        issues.append("ATF trust chain found but no BANDAID capability — trust without discovery")
        recommendations.append("Add _agents.<domain> SVCB for capability advertisement")
    
    if discovery.bandaid and discovery.atf:
        # Check domain consistency
        if discovery.bandaid.domain != discovery.atf.domain:
            issues.append(f"Domain mismatch: BANDAID={discovery.bandaid.domain} ATF={discovery.atf.domain}")
    
    if not discovery.dnssec_validated:
        issues.append("DNSSEC not validated — DNS records vulnerable to spoofing")
        recommendations.append("Enable DNSSEC (only 5.5% of domains currently)")
    
    if discovery.dnssec_validated and not discovery.dane_pinned:
        recommendations.append("Add DANE TLSA record for certificate pinning")
    
    tier = discovery.security_tier
    completeness = discovery.completeness
    
    return {
        "domain": discovery.domain,
        "security_tier": tier.value,
        "tier_name": tier.name,
        "completeness": completeness["score"],
        "completeness_detail": completeness["checks"],
        "issues": issues,
        "recommendations": recommendations,
        "interop_grade": "FULL" if discovery.bandaid and discovery.atf else 
                        "PARTIAL" if discovery.bandaid or discovery.atf else "NONE"
    }


def ttl_analysis(discovery: CompositeDiscovery) -> dict:
    """Analyze TTL mismatch risk between DNS and registry state."""
    # BANDAID recommends short TTL (300s) for SVCB
    # ATF TXT may have longer TTL (3600s)
    # Registry state is real-time
    
    bandaid_ttl = 300   # BANDAID recommendation
    atf_ttl = 3600      # Typical TXT TTL
    registry_state = 0  # Real-time
    
    max_staleness = max(bandaid_ttl, atf_ttl)
    
    return {
        "bandaid_svcb_ttl": bandaid_ttl,
        "atf_txt_ttl": atf_ttl,
        "registry_state_latency": registry_state,
        "max_staleness_seconds": max_staleness,
        "risk": "HIGH" if max_staleness > 1800 else "MEDIUM" if max_staleness > 600 else "LOW",
        "recommendation": f"Align ATF TXT TTL to {bandaid_ttl}s (BANDAID standard)"
    }


# === Scenarios ===

def scenario_full_interop():
    """Domain with both BANDAID and ATF — full interop."""
    print("=== Scenario: Full Interop (BANDAID + ATF + DANE) ===")
    
    bandaid = BandaidRecord(
        domain="agent.example.com",
        service_name="task",
        target="api.agent.example.com",
        capabilities=["mcp/search", "mcp/execute", "atf/verify"]
    )
    
    atf = AtfTxtRecord(
        domain="agent.example.com",
        registry_endpoint="https://registry.example.com/v1",
        genesis_hash="a1b2c3d4e5f6789012345678",
        revocation_endpoint="https://registry.example.com/v1/revoke"
    )
    
    discovery = discover_domain("agent.example.com", bandaid, atf,
                                dnssec=True, dane=True, ct=True)
    
    print(f"  BANDAID: {bandaid.to_svcb()}")
    print(f"  ATF:     {atf.to_txt()}")
    print(f"  Security: {discovery.security_tier.name} ({discovery.security_tier.value})")
    
    interop = validate_interop(discovery)
    print(f"  Interop: {interop['interop_grade']}")
    print(f"  Completeness: {interop['completeness']}")
    print(f"  Issues: {interop['issues'] or 'None'}")
    
    ttl = ttl_analysis(discovery)
    print(f"  TTL risk: {ttl['risk']} (max staleness: {ttl['max_staleness_seconds']}s)")
    print()


def scenario_bandaid_only():
    """Domain with BANDAID but no ATF — capability without trust."""
    print("=== Scenario: BANDAID Only (Capability Without Trust) ===")
    
    bandaid = BandaidRecord(
        domain="newagent.io",
        service_name="chat",
        target="api.newagent.io",
        capabilities=["mcp/chat"]
    )
    
    discovery = discover_domain("newagent.io", bandaid=bandaid, dnssec=False)
    interop = validate_interop(discovery)
    
    print(f"  BANDAID: {bandaid.to_svcb()}")
    print(f"  ATF: None")
    print(f"  Security: {discovery.security_tier.name} ({discovery.security_tier.value})")
    print(f"  Interop: {interop['interop_grade']}")
    print(f"  Issues:")
    for i in interop['issues']:
        print(f"    - {i}")
    print(f"  Recommendations:")
    for r in interop['recommendations']:
        print(f"    + {r}")
    print()


def scenario_atf_no_dnssec():
    """ATF trust chain but 94.5% case — no DNSSEC, CT fallback."""
    print("=== Scenario: ATF Without DNSSEC (94.5% of domains) ===")
    
    atf = AtfTxtRecord(
        domain="typical-agent.com",
        registry_endpoint="https://registry.typical-agent.com",
        genesis_hash="dead beef cafe 1234",
    )
    
    discovery = discover_domain("typical-agent.com", atf=atf, ct=True)
    interop = validate_interop(discovery)
    
    print(f"  ATF: {atf.to_txt()}")
    print(f"  DNSSEC: No (94.5% of domains)")
    print(f"  CT fallback: Yes")
    print(f"  Security: {discovery.security_tier.name} ({discovery.security_tier.value})")
    print(f"  Interop: {interop['interop_grade']}")
    print(f"  Issues:")
    for i in interop['issues']:
        print(f"    - {i}")
    print()


def scenario_dane_pinned():
    """Ideal case: DNSSEC + DANE + BANDAID + ATF."""
    print("=== Scenario: Ideal — DANE-Pinned Full Stack ===")
    
    bandaid = BandaidRecord(
        domain="secure-agent.net",
        service_name="atf",
        target="trust.secure-agent.net",
        capabilities=["atf/verify", "atf/attest", "atf/revoke"]
    )
    
    atf = AtfTxtRecord(
        domain="secure-agent.net",
        registry_endpoint="https://trust.secure-agent.net/v1",
        genesis_hash="cafe1234deadbeef",
        revocation_endpoint="https://trust.secure-agent.net/v1/revoke",
        bridge_endpoints=["https://registry-b.example.com/bridge"]
    )
    
    discovery = discover_domain("secure-agent.net", bandaid, atf,
                                dnssec=True, dane=True, ct=True)
    interop = validate_interop(discovery)
    
    print(f"  Security: {discovery.security_tier.name} ({discovery.security_tier.value})")
    print(f"  Completeness: {interop['completeness']} (all checks pass)")
    print(f"  Interop: {interop['interop_grade']}")
    print(f"  Issues: {interop['issues'] or 'None'}")
    print(f"  This is the 5.5% — rare but achievable.")
    print()


if __name__ == "__main__":
    print("BANDAID Interop — IETF BANDAID + ATF DNS Discovery")
    print("Per petra + Mozley et al. (IETF draft-mozleywilliams-dnsop-bandaid-00, Oct 2025)")
    print("=" * 70)
    print()
    print("Two layers, one domain:")
    print("  BANDAID _agents.<domain> SVCB → capability discovery")
    print("  ATF     _atf.<domain> TXT    → trust chain verification")
    print("  Like MX (routing) + DKIM (auth) — different records, same domain")
    print()
    
    scenario_full_interop()
    scenario_bandaid_only()
    scenario_atf_no_dnssec()
    scenario_dane_pinned()
    
    print("=" * 70)
    print("KEY INSIGHT: BANDAID = what, ATF = whether to trust.")
    print("Compose, don't compete. DNS already has this pattern:")
    print("  MX = where to deliver, DKIM = who sent it, DMARC = what to do.")
    print("  SVCB = what agent does, TXT = whether agent is trusted.")
    print("5.5% DNSSEC is the bottleneck. CT fallback makes it practical.")
