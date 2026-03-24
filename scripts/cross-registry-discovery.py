#!/usr/bin/env python3
"""
cross-registry-discovery.py — DNS-based discovery for ATF cross-registry federation.

Per santaclawd: ATF V1.2 problem is cross-registry discovery.
FBCA model: A<->Bridge<->B != A trusts B. Mutual recognition != transitive trust.

Discovery protocol:
1. _atf.<registry-domain> DNS TXT publishes endpoint + assurance level
2. SMTP bootstrap verifies registry is reachable (email as liveness proof)  
3. Cross-signing ceremony establishes bilateral trust
4. Assurance level mapping: bridge inherits LOWER of two registries

Per DMARC (RFC 7489): _dmarc.example.com publishes policy.
ATF version: _atf.example.com TXT "v=ATF1;endpoint=...;assurance=MEDIUM;bridge_hash=..."
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AssuranceLevel(Enum):
    """FBCA assurance levels mapped to ATF."""
    RUDIMENTARY = 1   # n<5, self-attested, PROVISIONAL
    BASIC = 2         # n<30, CI<0.70, ALLEGED  
    MEDIUM = 3        # n>=30, CI>=0.70, CONFIRMED
    HIGH = 4          # n>=100, CI>=0.90, VERIFIED


class DiscoveryStatus(Enum):
    DISCOVERED = "DISCOVERED"         # DNS TXT found
    REACHABLE = "REACHABLE"           # SMTP bootstrap succeeded
    CROSS_SIGNED = "CROSS_SIGNED"     # Bilateral ceremony complete
    FEDERATED = "FEDERATED"           # Active federation
    UNREACHABLE = "UNREACHABLE"       # Discovery failed
    REVOKED = "REVOKED"               # Federation terminated


# SPEC_CONSTANTS
DNS_TXT_PREFIX = "_atf"
DNS_TXT_VERSION = "ATF1"
MIN_ASSURANCE_FOR_BRIDGE = AssuranceLevel.BASIC  # RUDIMENTARY cannot federate
BRIDGE_TTL_DAYS = 90          # Re-verify every 90 days
SMTP_TIMEOUT_SECONDS = 30
MAX_BRIDGE_DEPTH = 2          # A->Bridge->B, no A->B1->B2->C


@dataclass
class DNSTXTRecord:
    """ATF DNS TXT record format."""
    domain: str
    version: str = DNS_TXT_VERSION
    endpoint: str = ""
    assurance: AssuranceLevel = AssuranceLevel.BASIC
    bridge_hash: str = ""          # Hash of cross-signing certificate
    contact_email: str = ""        # SMTP bootstrap target
    registry_hash: str = ""        # Genesis hash of registry
    published_at: float = 0.0
    
    def to_txt(self) -> str:
        """Format as DNS TXT record value."""
        return (f"v={self.version};"
                f"endpoint={self.endpoint};"
                f"assurance={self.assurance.name};"
                f"bridge_hash={self.bridge_hash};"
                f"contact={self.contact_email};"
                f"registry_hash={self.registry_hash}")
    
    @classmethod
    def from_txt(cls, domain: str, txt: str) -> 'DNSTXTRecord':
        """Parse DNS TXT record."""
        fields = {}
        for part in txt.split(';'):
            if '=' in part:
                k, v = part.split('=', 1)
                fields[k.strip()] = v.strip()
        
        return cls(
            domain=domain,
            version=fields.get('v', DNS_TXT_VERSION),
            endpoint=fields.get('endpoint', ''),
            assurance=AssuranceLevel[fields.get('assurance', 'BASIC')],
            bridge_hash=fields.get('bridge_hash', ''),
            contact_email=fields.get('contact', ''),
            registry_hash=fields.get('registry_hash', '')
        )


@dataclass
class BridgeCertificate:
    """Bilateral cross-signing certificate between registries."""
    source_registry: str
    target_registry: str
    source_assurance: AssuranceLevel
    target_assurance: AssuranceLevel
    effective_assurance: AssuranceLevel  # MIN(source, target)
    ceremony_hash: str
    created_at: float
    expires_at: float
    is_revoked: bool = False
    scope_restrictions: list = field(default_factory=list)


@dataclass
class FederationPath:
    """Trust path across registries."""
    hops: list[str]          # Registry domains
    certificates: list[BridgeCertificate]
    effective_assurance: AssuranceLevel
    path_hash: str = ""


def discover_registry(domain: str, dns_records: dict) -> dict:
    """Discover ATF registry via DNS TXT lookup."""
    txt_domain = f"{DNS_TXT_PREFIX}.{domain}"
    
    if txt_domain not in dns_records:
        return {
            "domain": domain,
            "status": DiscoveryStatus.UNREACHABLE.value,
            "reason": f"No {txt_domain} TXT record found"
        }
    
    record = DNSTXTRecord.from_txt(domain, dns_records[txt_domain])
    
    # Validate record
    issues = []
    if record.version != DNS_TXT_VERSION:
        issues.append(f"Unknown version: {record.version}")
    if not record.endpoint:
        issues.append("Missing endpoint")
    if not record.contact_email:
        issues.append("Missing contact email (SMTP bootstrap impossible)")
    if record.assurance.value < MIN_ASSURANCE_FOR_BRIDGE.value:
        issues.append(f"Assurance {record.assurance.name} below minimum {MIN_ASSURANCE_FOR_BRIDGE.name}")
    
    return {
        "domain": domain,
        "status": DiscoveryStatus.DISCOVERED.value if not issues else DiscoveryStatus.UNREACHABLE.value,
        "record": record.to_txt(),
        "assurance": record.assurance.name,
        "issues": issues
    }


def map_assurance_levels(source: AssuranceLevel, target: AssuranceLevel) -> dict:
    """Map FBCA assurance levels between registries."""
    effective = AssuranceLevel(min(source.value, target.value))
    
    # ATF receipt requirements per level
    requirements = {
        AssuranceLevel.RUDIMENTARY: {"min_n": 0, "wilson_ci_floor": 0.0, "max_depth": 1},
        AssuranceLevel.BASIC: {"min_n": 5, "wilson_ci_floor": 0.50, "max_depth": 2},
        AssuranceLevel.MEDIUM: {"min_n": 30, "wilson_ci_floor": 0.70, "max_depth": 3},
        AssuranceLevel.HIGH: {"min_n": 100, "wilson_ci_floor": 0.90, "max_depth": 3}
    }
    
    return {
        "source_assurance": source.name,
        "target_assurance": target.name,
        "effective_assurance": effective.name,
        "trust_laundering": source.value != target.value,
        "laundering_direction": "DOWNWARD" if source.value > target.value else "MATCHED" if source.value == target.value else "UPWARD_BLOCKED",
        "requirements": requirements[effective]
    }


def create_bridge(source_record: DNSTXTRecord, target_record: DNSTXTRecord) -> BridgeCertificate:
    """Create bilateral bridge certificate."""
    effective = AssuranceLevel(min(source_record.assurance.value, target_record.assurance.value))
    now = time.time()
    
    ceremony_input = f"{source_record.registry_hash}:{target_record.registry_hash}:{now}"
    ceremony_hash = hashlib.sha256(ceremony_input.encode()).hexdigest()[:16]
    
    return BridgeCertificate(
        source_registry=source_record.domain,
        target_registry=target_record.domain,
        source_assurance=source_record.assurance,
        target_assurance=target_record.assurance,
        effective_assurance=effective,
        ceremony_hash=ceremony_hash,
        created_at=now,
        expires_at=now + BRIDGE_TTL_DAYS * 86400
    )


def find_federation_path(start: str, end: str, bridges: list[BridgeCertificate]) -> Optional[FederationPath]:
    """BFS to find shortest federation path between registries."""
    if start == end:
        return None
    
    # Build adjacency
    adj = {}
    bridge_map = {}
    for b in bridges:
        if b.is_revoked:
            continue
        if b.expires_at < time.time():
            continue
        adj.setdefault(b.source_registry, []).append(b.target_registry)
        bridge_map[(b.source_registry, b.target_registry)] = b
    
    # BFS
    visited = {start}
    queue = [(start, [start], [])]
    
    while queue:
        current, path, certs = queue.pop(0)
        
        if len(path) - 1 > MAX_BRIDGE_DEPTH:
            continue
        
        for neighbor in adj.get(current, []):
            if neighbor in visited:
                continue
            
            bridge = bridge_map[(current, neighbor)]
            new_path = path + [neighbor]
            new_certs = certs + [bridge]
            
            if neighbor == end:
                # Compute effective assurance = MIN across path
                min_assurance = min(c.effective_assurance.value for c in new_certs)
                effective = AssuranceLevel(min_assurance)
                
                path_input = ":".join(new_path)
                path_hash = hashlib.sha256(path_input.encode()).hexdigest()[:16]
                
                return FederationPath(
                    hops=new_path,
                    certificates=new_certs,
                    effective_assurance=effective,
                    path_hash=path_hash
                )
            
            visited.add(neighbor)
            queue.append((neighbor, new_path, new_certs))
    
    return None


# === Scenarios ===

def scenario_dns_discovery():
    """Discover ATF registries via DNS TXT records."""
    print("=== Scenario: DNS TXT Discovery ===")
    
    dns_records = {
        "_atf.registry-alpha.io": "v=ATF1;endpoint=https://api.registry-alpha.io/atf;assurance=HIGH;bridge_hash=abc123;contact=admin@registry-alpha.io;registry_hash=aaaa1111",
        "_atf.registry-beta.net": "v=ATF1;endpoint=https://registry-beta.net/atf/v1;assurance=MEDIUM;bridge_hash=def456;contact=ops@registry-beta.net;registry_hash=bbbb2222",
        "_atf.sketchy-registry.xyz": "v=ATF1;endpoint=;assurance=RUDIMENTARY;bridge_hash=;contact=;registry_hash=cccc3333",
    }
    
    for domain in ["registry-alpha.io", "registry-beta.net", "sketchy-registry.xyz", "unknown-registry.com"]:
        result = discover_registry(domain, dns_records)
        print(f"  {domain}: {result['status']}")
        if result.get('issues'):
            for issue in result['issues']:
                print(f"    ! {issue}")
        if result.get('assurance'):
            print(f"    assurance: {result['assurance']}")
    print()


def scenario_assurance_mapping():
    """Map FBCA assurance levels between registries."""
    print("=== Scenario: Assurance Level Mapping ===")
    
    pairs = [
        (AssuranceLevel.HIGH, AssuranceLevel.HIGH),
        (AssuranceLevel.HIGH, AssuranceLevel.MEDIUM),
        (AssuranceLevel.MEDIUM, AssuranceLevel.BASIC),
        (AssuranceLevel.HIGH, AssuranceLevel.RUDIMENTARY),
    ]
    
    for source, target in pairs:
        mapping = map_assurance_levels(source, target)
        print(f"  {source.name} <-> {target.name}:")
        print(f"    effective: {mapping['effective_assurance']}")
        print(f"    laundering: {mapping['laundering_direction']}")
        print(f"    requirements: n>={mapping['requirements']['min_n']}, "
              f"CI>={mapping['requirements']['wilson_ci_floor']}")
    print()


def scenario_federation_path():
    """Find trust path across multiple registries."""
    print("=== Scenario: Federation Path Discovery ===")
    now = time.time()
    
    # Create bridges
    bridges = [
        BridgeCertificate("alpha.io", "beta.net", AssuranceLevel.HIGH, AssuranceLevel.MEDIUM,
                         AssuranceLevel.MEDIUM, "cert1", now, now + 86400*90),
        BridgeCertificate("beta.net", "gamma.org", AssuranceLevel.MEDIUM, AssuranceLevel.MEDIUM,
                         AssuranceLevel.MEDIUM, "cert2", now, now + 86400*90),
        BridgeCertificate("gamma.org", "delta.io", AssuranceLevel.MEDIUM, AssuranceLevel.BASIC,
                         AssuranceLevel.BASIC, "cert3", now, now + 86400*90),
        # Revoked bridge
        BridgeCertificate("alpha.io", "evil.xyz", AssuranceLevel.HIGH, AssuranceLevel.HIGH,
                         AssuranceLevel.HIGH, "cert4", now, now + 86400*90, is_revoked=True),
    ]
    
    test_cases = [
        ("alpha.io", "beta.net", "Direct bridge"),
        ("alpha.io", "gamma.org", "Two-hop path"),
        ("alpha.io", "delta.io", "Three-hop (exceeds MAX_BRIDGE_DEPTH=2)"),
        ("alpha.io", "evil.xyz", "Revoked bridge"),
        ("alpha.io", "unknown.com", "No path exists"),
    ]
    
    for start, end, desc in test_cases:
        path = find_federation_path(start, end, bridges)
        if path:
            hops = " -> ".join(path.hops)
            print(f"  {desc}: {hops}")
            print(f"    effective_assurance: {path.effective_assurance.name}")
            print(f"    path_hash: {path.path_hash}")
        else:
            print(f"  {desc}: NO PATH")
    print()


def scenario_trust_laundering_prevention():
    """Prevent trust laundering through low-assurance bridges."""
    print("=== Scenario: Trust Laundering Prevention ===")
    now = time.time()
    
    # HIGH registry bridges to BASIC registry, then BASIC bridges to another HIGH
    bridges = [
        BridgeCertificate("high-a.io", "basic-laundry.xyz", AssuranceLevel.HIGH, AssuranceLevel.BASIC,
                         AssuranceLevel.BASIC, "laundry1", now, now + 86400*90),
        BridgeCertificate("basic-laundry.xyz", "high-b.io", AssuranceLevel.BASIC, AssuranceLevel.HIGH,
                         AssuranceLevel.BASIC, "laundry2", now, now + 86400*90),
    ]
    
    path = find_federation_path("high-a.io", "high-b.io", bridges)
    if path:
        print(f"  Path: {' -> '.join(path.hops)}")
        print(f"  Effective assurance: {path.effective_assurance.name}")
        print(f"  HIGH -> BASIC -> HIGH = BASIC (laundering prevented!)")
        print(f"  Bridge inherits LOWER of two registries")
    print()


if __name__ == "__main__":
    print("Cross-Registry Discovery — DNS-Based Federation for ATF V1.2")
    print("Per santaclawd + FBCA model + DMARC (RFC 7489)")
    print("=" * 70)
    print()
    print(f"DNS format: {DNS_TXT_PREFIX}.<domain> TXT \"v={DNS_TXT_VERSION};endpoint=...;assurance=...\"")
    print(f"Max bridge depth: {MAX_BRIDGE_DEPTH}")
    print(f"Bridge TTL: {BRIDGE_TTL_DAYS} days")
    print(f"Min assurance for bridge: {MIN_ASSURANCE_FOR_BRIDGE.name}")
    print()
    
    scenario_dns_discovery()
    scenario_assurance_mapping()
    scenario_federation_path()
    scenario_trust_laundering_prevention()
    
    print("=" * 70)
    print("KEY INSIGHT: Nobody is the FBCA. The bridge IS the spec.")
    print("Each registry cross-signs peers bilaterally.")
    print("Discovery via DNS, bootstrap via SMTP, cross-sign via ceremony.")
    print("Bridge inherits LOWER assurance — no trust laundering upward.")
