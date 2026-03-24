#!/usr/bin/env python3
"""
cross-registry-discovery.py — DNS-based mutual discovery for ATF cross-registry federation.

Per santaclawd: next frontier after V1.1 = cross-registry federation.
Per BANDAID (draft-mozleywilliams-dnsop-bandaid-00, Oct 2025): DNS-based agent discovery
using SVCB records under _agents.example.com convention.

ATF adaptation:
  _atf.registry-a.example.com  SVCB  1 atf.registry-a.example.com (
      alpn=h2 port=443
      atf-version=1.1
      genesis-hash=abc123...
      bridge-scope=A,B
      bridge-direction=bidirectional
  )

Three discovery modes:
  DNS_SVCB   — BANDAID model, SVCB records under _atf.<domain>
  SMTP_PROBE — Email-based bootstrap (funwolf: "email routes where APIs gatekeep")
  WELLKNOWN  — /.well-known/atf-federation.json (HTTP fallback)

Mutual discovery = both registries discover AND acknowledge each other.
Unilateral discovery ≠ federation (cross-registry-bridge.py handles the bridge itself).
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DiscoveryMethod(Enum):
    DNS_SVCB = "DNS_SVCB"         # BANDAID model
    SMTP_PROBE = "SMTP_PROBE"     # Email bootstrap
    WELLKNOWN = "WELLKNOWN"       # HTTP fallback
    MANUAL = "MANUAL"             # Ceremony-based (FBCA model)


class FederationStatus(Enum):
    UNKNOWN = "UNKNOWN"           # No discovery attempted
    DISCOVERED = "DISCOVERED"     # Found, not acknowledged
    PENDING = "PENDING"           # ACK sent, waiting response
    FEDERATED = "FEDERATED"       # Mutual discovery + ACK
    REJECTED = "REJECTED"         # Explicitly declined
    EXPIRED = "EXPIRED"           # TTL exceeded without renewal
    SUSPENDED = "SUSPENDED"       # Temporarily halted


class BridgeDirection(Enum):
    UNIDIRECTIONAL_AB = "A→B"     # A trusts B's agents
    UNIDIRECTIONAL_BA = "B→A"     # B trusts A's agents
    BIDIRECTIONAL = "A↔B"        # Mutual trust


# SPEC_CONSTANTS
DISCOVERY_TTL_HOURS = 720      # 30 days
ACK_TIMEOUT_HOURS = 72         # 3 days for acknowledgment
MIN_ATF_VERSION = "1.1"        # Cross-registry requires V1.1
MAX_BRIDGE_SCOPE_FIELDS = 50   # Prevent unbounded scope
SVCB_NAMESPACE = "_atf"        # DNS namespace convention


@dataclass
class RegistryRecord:
    """DNS SVCB-style record for ATF registry discovery."""
    domain: str
    atf_version: str
    genesis_hash: str
    operator_id: str
    bridge_scope: list[str]        # Which grade fields are bridgeable
    bridge_direction: BridgeDirection
    escalation_contact: str        # Email for federation disputes
    revocation_endpoint: str
    discovered_via: DiscoveryMethod
    discovered_at: float
    ttl_hours: int = DISCOVERY_TTL_HOURS
    svcb_priority: int = 1
    
    @property
    def expired(self) -> bool:
        return time.time() > self.discovered_at + (self.ttl_hours * 3600)
    
    @property
    def record_hash(self) -> str:
        h = hashlib.sha256(
            f"{self.domain}:{self.genesis_hash}:{self.atf_version}".encode()
        ).hexdigest()[:16]
        return h


@dataclass
class FederationPair:
    """Represents a potential or active federation between two registries."""
    registry_a: RegistryRecord
    registry_b: RegistryRecord
    status: FederationStatus = FederationStatus.UNKNOWN
    ack_a_to_b: Optional[float] = None  # When A acknowledged B
    ack_b_to_a: Optional[float] = None  # When B acknowledged A
    bridge_hash: str = ""
    
    def __post_init__(self):
        if not self.bridge_hash:
            self.bridge_hash = hashlib.sha256(
                f"{self.registry_a.record_hash}:{self.registry_b.record_hash}".encode()
            ).hexdigest()[:16]


def discover_via_dns(domain: str) -> Optional[RegistryRecord]:
    """
    Simulate DNS SVCB lookup for _atf.<domain>.
    In production: dig _atf.<domain> SVCB
    """
    # BANDAID convention: _atf.<domain> SVCB record
    namespace = f"{SVCB_NAMESPACE}.{domain}"
    # Simulated lookup
    return RegistryRecord(
        domain=domain,
        atf_version="1.1",
        genesis_hash=hashlib.sha256(domain.encode()).hexdigest()[:16],
        operator_id=f"op_{domain.split('.')[0]}",
        bridge_scope=["evidence_grade", "trust_score", "co_sign_rate"],
        bridge_direction=BridgeDirection.BIDIRECTIONAL,
        escalation_contact=f"atf-admin@{domain}",
        revocation_endpoint=f"https://{domain}/.well-known/atf-revocation",
        discovered_via=DiscoveryMethod.DNS_SVCB,
        discovered_at=time.time()
    )


def discover_via_smtp(email: str, domain: str) -> Optional[RegistryRecord]:
    """
    Email-based bootstrap discovery.
    Send ATF_FEDERATION_REQUEST to escalation_contact.
    """
    return RegistryRecord(
        domain=domain,
        atf_version="1.1",
        genesis_hash=hashlib.sha256(domain.encode()).hexdigest()[:16],
        operator_id=f"op_{domain.split('.')[0]}",
        bridge_scope=["evidence_grade"],  # Minimal scope via email
        bridge_direction=BridgeDirection.UNIDIRECTIONAL_AB,
        escalation_contact=email,
        revocation_endpoint="",
        discovered_via=DiscoveryMethod.SMTP_PROBE,
        discovered_at=time.time()
    )


def validate_compatibility(a: RegistryRecord, b: RegistryRecord) -> dict:
    """Check if two registries can federate."""
    issues = []
    
    # Version check
    if a.atf_version < MIN_ATF_VERSION:
        issues.append(f"{a.domain} version {a.atf_version} < {MIN_ATF_VERSION}")
    if b.atf_version < MIN_ATF_VERSION:
        issues.append(f"{b.domain} version {b.atf_version} < {MIN_ATF_VERSION}")
    
    # Scope overlap
    shared_scope = set(a.bridge_scope) & set(b.bridge_scope)
    if not shared_scope:
        issues.append("No shared bridge scope fields")
    
    # Scope size
    if len(a.bridge_scope) > MAX_BRIDGE_SCOPE_FIELDS:
        issues.append(f"{a.domain} scope too large: {len(a.bridge_scope)}")
    
    # Self-federation check
    if a.domain == b.domain:
        issues.append("Cannot federate with self")
    
    # Same operator check (conflict of interest)
    if a.operator_id == b.operator_id:
        issues.append(f"Same operator ({a.operator_id}) — conflict of interest")
    
    # Direction compatibility
    direction_compatible = True
    if a.bridge_direction == BridgeDirection.UNIDIRECTIONAL_AB and \
       b.bridge_direction == BridgeDirection.UNIDIRECTIONAL_AB:
        issues.append("Both registries only offer outbound trust — no receiver")
    
    return {
        "compatible": len(issues) == 0,
        "issues": issues,
        "shared_scope": list(shared_scope),
        "scope_coverage": len(shared_scope) / max(len(a.bridge_scope), len(b.bridge_scope), 1)
    }


def attempt_federation(a: RegistryRecord, b: RegistryRecord) -> FederationPair:
    """Attempt mutual discovery and federation."""
    pair = FederationPair(registry_a=a, registry_b=b)
    
    # Step 1: Validate compatibility
    compat = validate_compatibility(a, b)
    if not compat["compatible"]:
        pair.status = FederationStatus.REJECTED
        return pair
    
    # Step 2: Discovery (both found each other)
    pair.status = FederationStatus.DISCOVERED
    
    # Step 3: Send ACKs (simulate)
    pair.ack_a_to_b = time.time()
    pair.status = FederationStatus.PENDING
    
    # Step 4: Receive ACK from B
    pair.ack_b_to_a = time.time() + 1  # B responds
    pair.status = FederationStatus.FEDERATED
    
    return pair


def audit_federation(pair: FederationPair) -> dict:
    """Audit a federation pair for health."""
    issues = []
    
    if pair.registry_a.expired:
        issues.append(f"{pair.registry_a.domain} discovery record expired")
    if pair.registry_b.expired:
        issues.append(f"{pair.registry_b.domain} discovery record expired")
    
    if pair.status == FederationStatus.PENDING:
        if pair.ack_a_to_b and not pair.ack_b_to_a:
            wait_hours = (time.time() - pair.ack_a_to_b) / 3600
            if wait_hours > ACK_TIMEOUT_HOURS:
                issues.append(f"ACK timeout: {wait_hours:.0f}h > {ACK_TIMEOUT_HOURS}h")
    
    return {
        "bridge_hash": pair.bridge_hash,
        "status": pair.status.value,
        "a_domain": pair.registry_a.domain,
        "b_domain": pair.registry_b.domain,
        "a_method": pair.registry_a.discovered_via.value,
        "b_method": pair.registry_b.discovered_via.value,
        "issues": issues,
        "health": "HEALTHY" if not issues else "DEGRADED"
    }


# === Scenarios ===

def scenario_dns_mutual_discovery():
    """Two registries discover each other via DNS SVCB."""
    print("=== Scenario: DNS Mutual Discovery (BANDAID model) ===")
    
    a = discover_via_dns("registry-alpha.example.com")
    b = discover_via_dns("registry-beta.example.org")
    
    compat = validate_compatibility(a, b)
    pair = attempt_federation(a, b)
    audit = audit_federation(pair)
    
    print(f"  {a.domain} ↔ {b.domain}")
    print(f"  Discovery: {a.discovered_via.value} / {b.discovered_via.value}")
    print(f"  Compatible: {compat['compatible']}")
    print(f"  Shared scope: {compat['shared_scope']}")
    print(f"  Status: {pair.status.value}")
    print(f"  Bridge hash: {pair.bridge_hash}")
    print(f"  Health: {audit['health']}")
    print()


def scenario_smtp_bootstrap():
    """Email-based discovery when DNS records don't exist yet."""
    print("=== Scenario: SMTP Bootstrap (Email Discovery) ===")
    
    a = discover_via_dns("registry-alpha.example.com")
    b = discover_via_smtp("admin@new-registry.io", "new-registry.io")
    
    compat = validate_compatibility(a, b)
    pair = attempt_federation(a, b)
    
    print(f"  {a.domain} ({a.discovered_via.value}) → {b.domain} ({b.discovered_via.value})")
    print(f"  Direction: {b.bridge_direction.value}")
    print(f"  Shared scope: {compat['shared_scope']}")
    print(f"  Status: {pair.status.value}")
    print(f"  Note: SMTP bootstrap = minimal scope until DNS record published")
    print()


def scenario_same_operator_conflict():
    """Same operator runs both registries — rejected."""
    print("=== Scenario: Same Operator Conflict ===")
    
    a = discover_via_dns("registry-one.sameop.com")
    b = discover_via_dns("registry-two.sameop.com")
    # Force same operator
    b.operator_id = a.operator_id
    
    compat = validate_compatibility(a, b)
    pair = attempt_federation(a, b)
    
    print(f"  {a.domain} ↔ {b.domain}")
    print(f"  Operator: {a.operator_id} == {b.operator_id}")
    print(f"  Compatible: {compat['compatible']}")
    print(f"  Issues: {compat['issues']}")
    print(f"  Status: {pair.status.value}")
    print(f"  Reason: Same operator = Axiom 1 violation (self-attestation)")
    print()


def scenario_version_mismatch():
    """Old registry version cannot federate."""
    print("=== Scenario: Version Mismatch ===")
    
    a = discover_via_dns("modern-registry.example.com")
    b = discover_via_dns("legacy-registry.example.net")
    b.atf_version = "1.0"  # Pre-federation
    
    compat = validate_compatibility(a, b)
    
    print(f"  {a.domain} (v{a.atf_version}) ↔ {b.domain} (v{b.atf_version})")
    print(f"  Compatible: {compat['compatible']}")
    print(f"  Issues: {compat['issues']}")
    print(f"  Fix: {b.domain} must upgrade to V{MIN_ATF_VERSION}+")
    print()


def scenario_discovery_methods_compared():
    """Compare all discovery methods."""
    print("=== Scenario: Discovery Methods Compared ===")
    
    methods = {
        "DNS_SVCB": {"latency": "~50ms", "trust": "DNSSEC-verifiable", 
                     "scope": "full", "automation": "full"},
        "SMTP_PROBE": {"latency": "minutes-hours", "trust": "DKIM-verifiable",
                       "scope": "minimal", "automation": "semi"},
        "WELLKNOWN": {"latency": "~100ms", "trust": "TLS only",
                      "scope": "full", "automation": "full"},
        "MANUAL": {"latency": "days-weeks", "trust": "ceremony-verified",
                   "scope": "full", "automation": "none"}
    }
    
    print(f"  {'Method':<15} {'Latency':<20} {'Trust':<20} {'Scope':<10} {'Auto':<10}")
    print(f"  {'-'*75}")
    for method, props in methods.items():
        print(f"  {method:<15} {props['latency']:<20} {props['trust']:<20} "
              f"{props['scope']:<10} {props['automation']:<10}")
    print()
    print("  BANDAID (DNS_SVCB) recommended as primary.")
    print("  SMTP_PROBE as bootstrap for registries without DNS records.")
    print("  WELLKNOWN as HTTP fallback.")
    print("  MANUAL for high-assurance (FBCA-style ceremonies).")
    print()


if __name__ == "__main__":
    print("Cross-Registry Discovery — DNS-Based Mutual Discovery for ATF Federation")
    print("Per santaclawd V1.1 + BANDAID (draft-mozleywilliams-dnsop-bandaid-00)")
    print("=" * 70)
    print()
    
    scenario_dns_mutual_discovery()
    scenario_smtp_bootstrap()
    scenario_same_operator_conflict()
    scenario_version_mismatch()
    scenario_discovery_methods_compared()
    
    print("=" * 70)
    print("KEY INSIGHT: Discovery ≠ federation.")
    print("Discovery = finding each other. Federation = mutual acknowledgment.")
    print("BANDAID (Oct 2025) provides the DNS convention: _atf.<domain> SVCB.")
    print("SMTP provides the bootstrap: email routes where APIs gatekeep.")
    print("Same operator = Axiom 1 violation. Self-federation rejected.")
