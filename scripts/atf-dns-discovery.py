#!/usr/bin/env python3
"""
atf-dns-discovery.py — DNS-based cross-registry discovery for ATF.

Per santaclawd: "how does ATF-A find ATF-B exists?"
Model: DANE (RFC 6698) + DMARC (RFC 7489) + MCP issue #1959.

Three-layer discovery:
  1. DNS TXT: _atf.<domain> → endpoint + assurance level (unauthenticated phonebook)
  2. SMTP bootstrap: first handshake, exchange genesis hashes (authenticated meeting)
  3. Cross-signing ceremony: mutual or unidirectional trust (signed treaty)

Key insight: discovery is unauthenticated. ceremony is authenticated.
Don't conflate the phonebook with the treaty.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AssuranceLevel(Enum):
    """FBCA-equivalent assurance levels for ATF registries."""
    RUDIMENTARY = "RUDIMENTARY"   # Self-declared, no external verification
    BASIC = "BASIC"               # n<30 receipts, Wilson CI floor
    MEDIUM = "MEDIUM"             # n≥30, CI>0.7, diverse counterparties
    HIGH = "HIGH"                 # n≥50, CI>0.85, audited, ceremony transcript


class DiscoveryStatus(Enum):
    DISCOVERED = "DISCOVERED"     # Found via DNS
    BOOTSTRAPPED = "BOOTSTRAPPED" # SMTP handshake complete
    CROSS_SIGNED = "CROSS_SIGNED" # Ceremony complete
    REJECTED = "REJECTED"         # Failed validation
    STALE = "STALE"              # TTL expired


# SPEC_CONSTANTS
DNS_TTL_SECONDS = 3600           # 1h TTL for _atf TXT records
BOOTSTRAP_TIMEOUT_HOURS = 72     # Max time to complete SMTP handshake
CEREMONY_TIMEOUT_HOURS = 168     # 7 days to complete cross-signing
MIN_DNSSEC_REQUIRED = True       # DNSSEC mandatory for HIGH assurance
ASSURANCE_MAPPING = {
    # ATF assurance → min requirements
    "RUDIMENTARY": {"min_n": 0, "min_ci": 0.0, "max_depth": 1},
    "BASIC": {"min_n": 10, "min_ci": 0.5, "max_depth": 2},
    "MEDIUM": {"min_n": 30, "min_ci": 0.7, "max_depth": 3},
    "HIGH": {"min_n": 50, "min_ci": 0.85, "max_depth": 4},
}


@dataclass
class DNSTXTRecord:
    """_atf.<domain> TXT record."""
    domain: str
    version: str = "ATFv1"
    endpoint: str = ""             # URL for ATF API
    assurance: str = "RUDIMENTARY"
    contact_email: str = ""
    genesis_hash: str = ""
    dnssec: bool = False
    ttl: int = DNS_TTL_SECONDS
    discovered_at: float = 0.0

    def to_txt(self) -> str:
        """Generate DNS TXT record value."""
        return (f"v={self.version}; "
                f"endpoint={self.endpoint}; "
                f"assurance={self.assurance}; "
                f"contact={self.contact_email}; "
                f"genesis={self.genesis_hash[:16]}")


@dataclass
class BootstrapHandshake:
    """SMTP-style bootstrap between two registries."""
    initiator_domain: str
    responder_domain: str
    initiator_genesis_hash: str
    responder_genesis_hash: str
    initiated_at: float
    completed_at: Optional[float] = None
    status: str = "PENDING"
    handshake_hash: str = ""

    def complete(self):
        self.completed_at = time.time()
        self.status = "COMPLETE"
        h = hashlib.sha256(
            f"{self.initiator_genesis_hash}:{self.responder_genesis_hash}:{self.completed_at}".encode()
        ).hexdigest()[:16]
        self.handshake_hash = h


@dataclass
class CrossSigningCeremony:
    """Mutual or unidirectional cross-signing between registries."""
    source_domain: str
    target_domain: str
    direction: str  # "UNIDIRECTIONAL" or "MUTUAL"
    source_assurance: str
    target_assurance: str
    bridge_grade: str = ""     # MIN(source, target) assurance
    witnesses: list = field(default_factory=list)
    ceremony_hash: str = ""
    signed_at: Optional[float] = None
    expires_at: Optional[float] = None
    
    def compute_bridge_grade(self):
        """Bridge grade = MIN(source, target) — prevents trust laundering."""
        levels = list(AssuranceLevel)
        s_idx = next(i for i, l in enumerate(levels) if l.value == self.source_assurance)
        t_idx = next(i for i, l in enumerate(levels) if l.value == self.target_assurance)
        self.bridge_grade = levels[min(s_idx, t_idx)].value


@dataclass
class RegistryDiscovery:
    """Complete discovery state for a foreign registry."""
    domain: str
    dns_record: Optional[DNSTXTRecord] = None
    bootstrap: Optional[BootstrapHandshake] = None
    ceremony: Optional[CrossSigningCeremony] = None
    status: DiscoveryStatus = DiscoveryStatus.DISCOVERED
    
    def current_assurance(self) -> str:
        if self.ceremony and self.ceremony.bridge_grade:
            return self.ceremony.bridge_grade
        if self.dns_record:
            return self.dns_record.assurance
        return "UNKNOWN"


def validate_dns_record(record: DNSTXTRecord) -> dict:
    """Validate a discovered _atf TXT record."""
    issues = []
    
    if not record.endpoint:
        issues.append("Missing endpoint URL")
    if not record.genesis_hash:
        issues.append("Missing genesis hash")
    if record.assurance not in [l.value for l in AssuranceLevel]:
        issues.append(f"Unknown assurance level: {record.assurance}")
    if record.assurance == "HIGH" and not record.dnssec:
        issues.append("HIGH assurance requires DNSSEC")
    
    return {
        "domain": record.domain,
        "valid": len(issues) == 0,
        "issues": issues,
        "txt_value": record.to_txt(),
        "assurance": record.assurance,
        "dnssec": record.dnssec
    }


def map_assurance_level(n_receipts: int, wilson_ci_lower: float, 
                         max_depth: int, has_audit: bool) -> str:
    """Map registry metrics to FBCA-equivalent assurance level."""
    if has_audit and n_receipts >= 50 and wilson_ci_lower >= 0.85:
        return "HIGH"
    elif n_receipts >= 30 and wilson_ci_lower >= 0.7:
        return "MEDIUM"
    elif n_receipts >= 10 and wilson_ci_lower >= 0.5:
        return "BASIC"
    else:
        return "RUDIMENTARY"


def compute_bridge_trust(source_assurance: str, target_assurance: str) -> dict:
    """
    Compute cross-registry bridge trust.
    Bridge grade = MIN(source, target) — prevents laundering trust upward.
    """
    levels = ["RUDIMENTARY", "BASIC", "MEDIUM", "HIGH"]
    s_idx = levels.index(source_assurance) if source_assurance in levels else 0
    t_idx = levels.index(target_assurance) if target_assurance in levels else 0
    bridge = levels[min(s_idx, t_idx)]
    
    return {
        "source": source_assurance,
        "target": target_assurance,
        "bridge_grade": bridge,
        "trust_laundering": s_idx != t_idx,
        "effective_depth": ASSURANCE_MAPPING[bridge]["max_depth"]
    }


def full_discovery_flow(local_domain: str, remote_domain: str,
                        remote_record: DNSTXTRecord,
                        local_assurance: str) -> dict:
    """Execute full three-layer discovery flow."""
    now = time.time()
    
    # Layer 1: DNS Discovery
    dns_validation = validate_dns_record(remote_record)
    if not dns_validation["valid"]:
        return {
            "status": "REJECTED",
            "layer": "DNS",
            "reason": dns_validation["issues"]
        }
    
    # Layer 2: SMTP Bootstrap
    bootstrap = BootstrapHandshake(
        initiator_domain=local_domain,
        responder_domain=remote_domain,
        initiator_genesis_hash=hashlib.sha256(local_domain.encode()).hexdigest()[:16],
        responder_genesis_hash=remote_record.genesis_hash,
        initiated_at=now
    )
    bootstrap.complete()
    
    # Layer 3: Cross-Signing Ceremony
    bridge = compute_bridge_trust(local_assurance, remote_record.assurance)
    ceremony = CrossSigningCeremony(
        source_domain=local_domain,
        target_domain=remote_domain,
        direction="UNIDIRECTIONAL",
        source_assurance=local_assurance,
        target_assurance=remote_record.assurance,
        witnesses=["witness_1", "witness_2", "witness_3"],
        signed_at=now,
        expires_at=now + 86400 * 90  # 90-day expiry
    )
    ceremony.compute_bridge_grade()
    
    return {
        "status": "CROSS_SIGNED",
        "dns": dns_validation,
        "bootstrap": {
            "handshake_hash": bootstrap.handshake_hash,
            "status": bootstrap.status
        },
        "ceremony": {
            "direction": ceremony.direction,
            "bridge_grade": ceremony.bridge_grade,
            "witnesses": len(ceremony.witnesses),
            "expires_days": 90
        },
        "bridge_trust": bridge
    }


# === Scenarios ===

def scenario_healthy_discovery():
    """Two HIGH-assurance registries discover each other."""
    print("=== Scenario: Healthy Cross-Registry Discovery ===")
    
    remote = DNSTXTRecord(
        domain="registry-b.example.com",
        endpoint="https://registry-b.example.com/atf/v1",
        assurance="HIGH",
        contact_email="ops@registry-b.example.com",
        genesis_hash="a1b2c3d4e5f6a7b8",
        dnssec=True,
        discovered_at=time.time()
    )
    
    result = full_discovery_flow("registry-a.example.com", "registry-b.example.com",
                                 remote, "HIGH")
    
    print(f"  Status: {result['status']}")
    print(f"  DNS: valid={result['dns']['valid']}, TXT={result['dns']['txt_value']}")
    print(f"  Bootstrap: {result['bootstrap']['status']}")
    print(f"  Bridge grade: {result['ceremony']['bridge_grade']}")
    print(f"  Trust laundering: {result['bridge_trust']['trust_laundering']}")
    print()


def scenario_assurance_mismatch():
    """HIGH tries to bridge with BASIC — grade drops to BASIC."""
    print("=== Scenario: Assurance Mismatch (Trust Laundering Prevention) ===")
    
    remote = DNSTXTRecord(
        domain="weak-registry.example.com",
        endpoint="https://weak-registry.example.com/atf/v1",
        assurance="BASIC",
        contact_email="ops@weak-registry.example.com",
        genesis_hash="deadbeef12345678",
        dnssec=False,
        discovered_at=time.time()
    )
    
    result = full_discovery_flow("strong-registry.example.com", "weak-registry.example.com",
                                 remote, "HIGH")
    
    print(f"  Source: HIGH, Target: BASIC")
    print(f"  Bridge grade: {result['ceremony']['bridge_grade']} (dropped to MIN)")
    print(f"  Trust laundering prevented: {result['bridge_trust']['trust_laundering']}")
    print(f"  Effective delegation depth: {result['bridge_trust']['effective_depth']}")
    print()


def scenario_high_without_dnssec():
    """Claims HIGH assurance but no DNSSEC — rejected."""
    print("=== Scenario: HIGH Without DNSSEC — Rejected ===")
    
    remote = DNSTXTRecord(
        domain="liar-registry.example.com",
        endpoint="https://liar-registry.example.com/atf/v1",
        assurance="HIGH",
        genesis_hash="1234567890abcdef",
        dnssec=False,  # Claims HIGH but no DNSSEC
        discovered_at=time.time()
    )
    
    validation = validate_dns_record(remote)
    print(f"  Claims: HIGH, DNSSEC: {remote.dnssec}")
    print(f"  Valid: {validation['valid']}")
    print(f"  Issues: {validation['issues']}")
    print()


def scenario_assurance_mapping():
    """Map real registry metrics to FBCA levels."""
    print("=== Scenario: Assurance Level Mapping ===")
    
    registries = [
        ("new_registry", 5, 0.35, 1, False),
        ("growing_registry", 15, 0.62, 2, False),
        ("established_registry", 45, 0.78, 3, False),
        ("audited_registry", 120, 0.91, 4, True),
    ]
    
    for name, n, ci, depth, audit in registries:
        level = map_assurance_level(n, ci, depth, audit)
        print(f"  {name}: n={n}, CI={ci:.2f}, audit={audit} → {level}")
    print()


if __name__ == "__main__":
    print("ATF DNS Discovery — Cross-Registry Discovery Protocol")
    print("Per santaclawd + DANE (RFC 6698) + MCP issue #1959")
    print("=" * 70)
    print()
    print("Three layers:")
    print("  1. DNS TXT (_atf.<domain>) → unauthenticated phonebook")
    print("  2. SMTP bootstrap → authenticated first handshake")
    print("  3. Cross-signing ceremony → signed treaty")
    print()
    
    scenario_healthy_discovery()
    scenario_assurance_mismatch()
    scenario_high_without_dnssec()
    scenario_assurance_mapping()
    
    print("=" * 70)
    print("KEY INSIGHT: Discovery ≠ trust. DNS finds who exists.")
    print("SMTP verifies they respond. Ceremony creates trust.")
    print("Bridge grade = MIN(source, target) — prevents laundering.")
    print("DANE: _25._tcp → TLSA. ATF: _atf.<domain> → endpoint+assurance.")
