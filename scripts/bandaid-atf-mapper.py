#!/usr/bin/env python3
"""
bandaid-atf-mapper.py — Map ATF fields to IETF BANDAID DNS discovery.

Per petra: AID spec uses _agent DNS TXT for discovery.
Per IETF BANDAID draft (Mozley et al, Oct 2025): _agents.<domain> SVCB records.
Per santaclawd: ATF _atf.<domain> TXT aligns with both.

Maps ATF V1.2 fields to BANDAID SVCB parameters for cross-protocol discovery.
Compose, don't compete.
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DiscoveryProtocol(Enum):
    ATF_TXT = "ATF_TXT"           # _atf.<domain> TXT record
    BANDAID_SVCB = "BANDAID_SVCB" # _agents.<domain> SVCB record  
    AID_TXT = "AID_TXT"           # _agent.<domain> TXT record


class SecurityLevel(Enum):
    DANE_PINNED = "DANE_PINNED"           # Full DNSSEC + DANE (5.5%)
    DNSSEC_VERIFIED = "DNSSEC_VERIFIED"   # DNSSEC but no DANE
    CT_FALLBACK = "CT_FALLBACK"           # CT log verification of TXT hash
    TOFU = "TOFU"                         # Trust on first use (no DNSSEC)


# ATF V1.2 DNS TXT fields
ATF_TXT_FIELDS = {
    "v": "ATF1",                    # Version
    "endpoint": str,                # Registry API endpoint
    "genesis_hash": str,            # Agent genesis hash
    "registry_hash": str,           # Registry spec hash
    "anchor_type": str,             # DKIM, DANE, CT
    "revocation_endpoint": str,     # OCSP-style revocation URL
    "operator_id": str,             # Operator identifier
}

# BANDAID SVCB parameters (from IETF draft)
BANDAID_SVCB_PARAMS = {
    "alpn": str,                    # Protocol negotiation
    "port": int,                    # Service port
    "ipv4hint": str,                # IPv4 address hint
    "ipv6hint": str,                # IPv6 address hint
    "mandatory": list,              # Required parameters
    "ech": str,                     # Encrypted Client Hello
}

# AID TXT fields
AID_TXT_FIELDS = {
    "endpoint": str,
    "protocol": str,
    "public_key": str,
}


@dataclass
class ATFRecord:
    domain: str
    version: str = "ATF1"
    endpoint: str = ""
    genesis_hash: str = ""
    registry_hash: str = ""
    anchor_type: str = "DANE"
    revocation_endpoint: str = ""
    operator_id: str = ""


@dataclass
class BANDAIDRecord:
    domain: str
    service_name: str = ""  # e.g., "chat", "trust", "atf"
    alpn: str = "h2"
    port: int = 443
    target: str = ""
    ipv4hint: str = ""
    priority: int = 1


@dataclass
class MappedDiscovery:
    """Cross-protocol discovery record."""
    domain: str
    atf: Optional[ATFRecord] = None
    bandaid: Optional[BANDAIDRecord] = None
    aid_compatible: bool = False
    security_level: SecurityLevel = SecurityLevel.TOFU
    mapping_hash: str = ""
    compatibility_score: float = 0.0


def map_atf_to_bandaid(atf: ATFRecord) -> BANDAIDRecord:
    """Map ATF TXT record to BANDAID SVCB parameters."""
    return BANDAIDRecord(
        domain=atf.domain,
        service_name="atf",               # ATF as a BANDAID service
        alpn="h2",                          # HTTP/2 for registry API
        port=443,
        target=atf.endpoint.replace("https://", "").split("/")[0] if atf.endpoint else "",
    )


def map_bandaid_to_atf(bandaid: BANDAIDRecord, genesis_hash: str = "",
                        registry_hash: str = "") -> ATFRecord:
    """Map BANDAID SVCB to ATF TXT record."""
    return ATFRecord(
        domain=bandaid.domain,
        endpoint=f"https://{bandaid.target}:{bandaid.port}" if bandaid.target else "",
        genesis_hash=genesis_hash,
        registry_hash=registry_hash,
        anchor_type="DANE" if bandaid.domain else "TOFU",
    )


def assess_security(domain: str, has_dnssec: bool = False, has_dane: bool = False,
                     has_ct_log: bool = False) -> SecurityLevel:
    """Determine security level based on DNS infrastructure."""
    if has_dane and has_dnssec:
        return SecurityLevel.DANE_PINNED
    elif has_dnssec:
        return SecurityLevel.DNSSEC_VERIFIED
    elif has_ct_log:
        return SecurityLevel.CT_FALLBACK
    return SecurityLevel.TOFU


def compute_compatibility(atf: Optional[ATFRecord], bandaid: Optional[BANDAIDRecord]) -> float:
    """Score cross-protocol compatibility 0-1."""
    score = 0.0
    max_score = 0.0
    
    if atf and bandaid:
        max_score += 3
        # Domain match
        if atf.domain == bandaid.domain:
            score += 1
        # Endpoint resolvable
        if atf.endpoint and bandaid.target:
            score += 1
        # Both have service info
        if atf.genesis_hash and bandaid.service_name:
            score += 1
    elif atf:
        max_score = 2
        if atf.endpoint: score += 1
        if atf.genesis_hash: score += 1
    elif bandaid:
        max_score = 2
        if bandaid.target: score += 1
        if bandaid.service_name: score += 1
    
    return round(score / max_score, 2) if max_score > 0 else 0.0


def generate_dns_records(discovery: MappedDiscovery) -> dict:
    """Generate DNS zone entries for both protocols."""
    records = {}
    
    if discovery.atf:
        atf = discovery.atf
        txt_value = (f"v={atf.version}; endpoint={atf.endpoint}; "
                    f"genesis_hash={atf.genesis_hash}; "
                    f"registry_hash={atf.registry_hash}; "
                    f"anchor={atf.anchor_type}")
        records["_atf"] = {
            "type": "TXT",
            "name": f"_atf.{atf.domain}",
            "value": txt_value
        }
    
    if discovery.bandaid:
        b = discovery.bandaid
        records["_agents"] = {
            "type": "SVCB",
            "name": f"{b.service_name}._agents.{b.domain}",
            "priority": b.priority,
            "target": b.target,
            "params": f"alpn={b.alpn} port={b.port}"
        }
    
    return records


# === Scenarios ===

def scenario_full_stack():
    """Agent with both ATF and BANDAID records — full composition."""
    print("=== Scenario: Full Stack (ATF + BANDAID) ===")
    
    atf = ATFRecord(
        domain="kit-fox.agent.example",
        endpoint="https://registry.atf.example/api/v1",
        genesis_hash="a1b2c3d4e5f6",
        registry_hash="f6e5d4c3b2a1",
        anchor_type="DANE",
        revocation_endpoint="https://registry.atf.example/revoke",
        operator_id="ilya@openclaw.ai"
    )
    
    bandaid = map_atf_to_bandaid(atf)
    security = assess_security("kit-fox.agent.example", has_dnssec=True, has_dane=True)
    compat = compute_compatibility(atf, bandaid)
    
    discovery = MappedDiscovery(
        domain="kit-fox.agent.example",
        atf=atf,
        bandaid=bandaid,
        aid_compatible=True,
        security_level=security,
        compatibility_score=compat
    )
    
    records = generate_dns_records(discovery)
    
    print(f"  Security: {security.value}")
    print(f"  Compatibility: {compat}")
    print(f"  DNS Records:")
    for name, rec in records.items():
        print(f"    {rec['name']} {rec['type']} = {rec.get('value', rec.get('params', ''))[:80]}")
    print()


def scenario_no_dnssec():
    """94.5% case — no DNSSEC, CT fallback."""
    print("=== Scenario: No DNSSEC (94.5% of domains) ===")
    
    atf = ATFRecord(
        domain="agent.notsecure.example",
        endpoint="https://trust.notsecure.example/atf",
        genesis_hash="deadbeef1234",
        registry_hash="cafe0000babe",
        anchor_type="CT",  # CT fallback since no DANE
    )
    
    security = assess_security("agent.notsecure.example", has_ct_log=True)
    bandaid = map_atf_to_bandaid(atf)
    compat = compute_compatibility(atf, bandaid)
    
    print(f"  Security: {security.value} (degraded but functional)")
    print(f"  Compatibility: {compat}")
    print(f"  ATF anchor: CT (not DANE)")
    print(f"  Discovery: works, trust: TOFU until receipts accumulate")
    print(f"  Key insight: 94.5% of agents still get discovery — just not pinned")
    print()


def scenario_bandaid_only():
    """Agent registered via BANDAID but not ATF."""
    print("=== Scenario: BANDAID Only (no ATF) ===")
    
    bandaid = BANDAIDRecord(
        domain="new-agent.example",
        service_name="chat",
        alpn="h2",
        port=443,
        target="api.new-agent.example"
    )
    
    atf = map_bandaid_to_atf(bandaid)
    compat = compute_compatibility(atf, bandaid)
    
    print(f"  BANDAID: {bandaid.service_name}._agents.{bandaid.domain}")
    print(f"  Mapped ATF: endpoint={atf.endpoint}")
    print(f"  Missing: genesis_hash, registry_hash (ATF-specific)")
    print(f"  Compatibility: {compat} (partial — needs ATF registration)")
    print(f"  Path: BANDAID discovery → ATF registration → full trust chain")
    print()


def scenario_cross_registry():
    """Two registries discovering each other via DNS."""
    print("=== Scenario: Cross-Registry Discovery ===")
    
    registry_a = ATFRecord(
        domain="registry-a.trust.example",
        endpoint="https://api.registry-a.trust.example/v1",
        genesis_hash="aaaa1111",
        registry_hash="rrrr1111",
        anchor_type="DANE"
    )
    
    registry_b = ATFRecord(
        domain="registry-b.trust.example",
        endpoint="https://api.registry-b.trust.example/v1",
        genesis_hash="bbbb2222",
        registry_hash="rrrr2222",
        anchor_type="DANE"
    )
    
    # Cross-registry discovery: each queries the other's _atf TXT
    sec_a = assess_security("registry-a.trust.example", has_dnssec=True, has_dane=True)
    sec_b = assess_security("registry-b.trust.example", has_dnssec=True, has_dane=True)
    
    print(f"  Registry A: {registry_a.domain} [{sec_a.value}]")
    print(f"  Registry B: {registry_b.domain} [{sec_b.value}]")
    print(f"  Discovery: A queries _atf.{registry_b.domain}")
    print(f"  Bridge: unidirectional, scoped, expiring (cross-registry-bridge.py)")
    print(f"  FBCA model: peer-to-peer, NOT transitive")
    print()


if __name__ == "__main__":
    print("BANDAID-ATF Mapper — Cross-Protocol Agent Discovery")
    print("Per petra (AID spec) + IETF BANDAID (Mozley et al, Oct 2025)")
    print("=" * 70)
    print()
    print("Three discovery protocols mapped:")
    print("  ATF:     _atf.<domain> TXT (trust framework)")
    print("  BANDAID: _agents.<domain> SVCB (IETF standards track)")
    print("  AID:     _agent.<domain> TXT (community spec)")
    print()
    
    scenario_full_stack()
    scenario_no_dnssec()
    scenario_bandaid_only()
    scenario_cross_registry()
    
    print("=" * 70)
    print("KEY INSIGHT: Compose, don't compete.")
    print("ATF = trust framework. BANDAID = discovery protocol. AID = community spec.")
    print("Same DNS infrastructure, different layers.")
    print("5.5% DNSSEC = DANE pinned. 94.5% = CT fallback. 100% = discovery works.")
