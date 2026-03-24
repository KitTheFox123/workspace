#!/usr/bin/env python3
"""
cross-registry-discovery.py — DNS TXT + SMTP bootstrap for ATF cross-registry federation.

Per santaclawd: ATF V1.2 needs cross-registry discovery. How does ATF-A find ATF-B exists?
Per FBCA Cross-Cert Eval Framework v5.0 (Sept 2024): 4 assurance levels with specific requirements.

Three-layer discovery:
  1. DNS TXT: _atf.<domain> publishes endpoint + assurance level (unauthenticated)
  2. SMTP Bootstrap: BOOTSTRAP_REQUEST email to discovered endpoint (first meeting)  
  3. Cross-signing ceremony: witnesses + transcript + hash (commitment)

Key insight: DNS discovers, SMTP bootstraps, ceremony commits.
DNS is a phonebook, not a trust anchor.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AssuranceLevel(Enum):
    """FBCA-mapped assurance levels for ATF registries."""
    RUDIMENTARY = "RUDIMENTARY"  # n<10, self-operated, no audit
    BASIC = "BASIC"              # n<30, single grader, basic audit
    MEDIUM = "MEDIUM"            # n≥30, diverse graders, WebTrust-equivalent
    HIGH = "HIGH"                # n≥50, multi-grader, full ceremony, external audit


class DiscoveryStatus(Enum):
    DISCOVERED = "DISCOVERED"           # DNS TXT found
    BOOTSTRAP_SENT = "BOOTSTRAP_SENT"   # SMTP request sent
    BOOTSTRAP_ACK = "BOOTSTRAP_ACK"     # Remote responded
    CEREMONY_SCHEDULED = "CEREMONY_SCHEDULED"
    CROSS_SIGNED = "CROSS_SIGNED"       # Mutual recognition complete
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


# SPEC_CONSTANTS
BOOTSTRAP_TIMEOUT_HOURS = 72
CEREMONY_MIN_WITNESSES = 3
DNS_TXT_PREFIX = "_atf"
DNS_TXT_VERSION = "ATF1"
ASSURANCE_REQUIREMENTS = {
    AssuranceLevel.RUDIMENTARY: {"min_receipts": 0, "min_graders": 0, "audit": False, "ceremony": False},
    AssuranceLevel.BASIC: {"min_receipts": 10, "min_graders": 1, "audit": False, "ceremony": False},
    AssuranceLevel.MEDIUM: {"min_receipts": 30, "min_graders": 2, "audit": True, "ceremony": True},
    AssuranceLevel.HIGH: {"min_receipts": 50, "min_graders": 3, "audit": True, "ceremony": True},
}
# Cross-registry bridge inherits LOWER of two assurance floors
# Prevents trust laundering upward


@dataclass
class DNSTXTRecord:
    """ATF DNS TXT record for registry discovery."""
    domain: str
    version: str = DNS_TXT_VERSION
    endpoint: str = ""
    assurance_level: str = ""
    contact_email: str = ""
    registry_hash: str = ""
    dnssec: bool = False
    
    def to_txt(self) -> str:
        parts = [
            f"v={self.version}",
            f"endpoint={self.endpoint}",
            f"level={self.assurance_level}",
            f"contact={self.contact_email}",
            f"hash={self.registry_hash[:16]}"
        ]
        return " ".join(parts)
    
    @staticmethod
    def parse(domain: str, txt: str, dnssec: bool = False) -> 'DNSTXTRecord':
        record = DNSTXTRecord(domain=domain, dnssec=dnssec)
        for part in txt.split():
            if '=' in part:
                k, v = part.split('=', 1)
                if k == 'v': record.version = v
                elif k == 'endpoint': record.endpoint = v
                elif k == 'level': record.assurance_level = v
                elif k == 'contact': record.contact_email = v
                elif k == 'hash': record.registry_hash = v
        return record


@dataclass
class BootstrapRequest:
    """SMTP bootstrap request for cross-registry introduction."""
    from_registry: str
    to_registry: str
    from_endpoint: str
    from_assurance: AssuranceLevel
    proposed_bridge_scope: list[str]  # Which fields to bridge
    timestamp: float = 0.0
    request_hash: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()
        if not self.request_hash:
            self.request_hash = hashlib.sha256(
                f"{self.from_registry}:{self.to_registry}:{self.timestamp}".encode()
            ).hexdigest()[:16]


@dataclass
class CrossSigningCeremony:
    """Cross-signing ceremony between two registries."""
    registry_a: str
    registry_b: str
    assurance_a: AssuranceLevel
    assurance_b: AssuranceLevel
    witnesses: list[str]
    bridge_scope: list[str]
    ceremony_hash: str = ""
    bridge_assurance: str = ""  # MIN(a, b)
    timestamp: float = 0.0
    transcript_hash: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()
        # Bridge inherits LOWER assurance
        levels = list(AssuranceLevel)
        a_idx = levels.index(self.assurance_a)
        b_idx = levels.index(self.assurance_b)
        self.bridge_assurance = levels[min(a_idx, b_idx)].value
        
        self.ceremony_hash = hashlib.sha256(
            f"{self.registry_a}:{self.registry_b}:{self.bridge_assurance}:{self.timestamp}".encode()
        ).hexdigest()[:16]


def discover_registry(domain: str, txt_records: dict) -> dict:
    """Simulate DNS TXT discovery."""
    fqdn = f"{DNS_TXT_PREFIX}.{domain}"
    if fqdn not in txt_records:
        return {"status": "NOT_FOUND", "domain": domain, "fqdn": fqdn}
    
    record = DNSTXTRecord.parse(domain, txt_records[fqdn], dnssec=txt_records.get(f"{fqdn}.dnssec", False))
    
    # Validate record
    issues = []
    if record.version != DNS_TXT_VERSION:
        issues.append(f"Unknown version: {record.version}")
    if not record.endpoint:
        issues.append("Missing endpoint")
    if record.assurance_level not in [l.value for l in AssuranceLevel]:
        issues.append(f"Invalid assurance level: {record.assurance_level}")
    
    return {
        "status": "DISCOVERED" if not issues else "INVALID",
        "domain": domain,
        "record": record.to_txt(),
        "endpoint": record.endpoint,
        "assurance": record.assurance_level,
        "dnssec": record.dnssec,
        "issues": issues,
        "warning": "DNS is UNAUTHENTICATED discovery — trust starts at ceremony, not here" if not record.dnssec else None
    }


def evaluate_bridge(ceremony: CrossSigningCeremony) -> dict:
    """Evaluate cross-signing ceremony validity."""
    issues = []
    
    if len(ceremony.witnesses) < CEREMONY_MIN_WITNESSES:
        issues.append(f"Need {CEREMONY_MIN_WITNESSES}+ witnesses, got {len(ceremony.witnesses)}")
    
    # Check witness diversity (no same-registry witnesses)
    witness_registries = set()
    for w in ceremony.witnesses:
        reg = w.split("@")[1] if "@" in w else "unknown"
        witness_registries.add(reg)
    
    if ceremony.registry_a in witness_registries or ceremony.registry_b in witness_registries:
        issues.append("Witnesses must be independent of both registries")
    
    # Bridge assurance = MIN(a, b)
    levels = {l.value: i for i, l in enumerate(AssuranceLevel)}
    bridge_idx = min(levels.get(ceremony.assurance_a.value, 0), 
                     levels.get(ceremony.assurance_b.value, 0))
    expected_bridge = list(AssuranceLevel)[bridge_idx].value
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "bridge_assurance": expected_bridge,
        "assurance_a": ceremony.assurance_a.value,
        "assurance_b": ceremony.assurance_b.value,
        "witnesses": len(ceremony.witnesses),
        "ceremony_hash": ceremony.ceremony_hash,
        "note": "Bridge inherits LOWER of two assurance floors — prevents trust laundering"
    }


# === Scenarios ===

def scenario_full_discovery():
    """Complete discovery → bootstrap → ceremony flow."""
    print("=== Scenario: Full Discovery Flow ===")
    
    txt_records = {
        "_atf.registry-alpha.ai": "v=ATF1 endpoint=https://registry-alpha.ai/atf level=HIGH contact=admin@registry-alpha.ai hash=abc123",
        "_atf.registry-alpha.ai.dnssec": True,
        "_atf.registry-beta.io": "v=ATF1 endpoint=https://registry-beta.io/atf level=MEDIUM contact=ops@registry-beta.io hash=def456",
    }
    
    # Step 1: DNS discovery
    result_a = discover_registry("registry-alpha.ai", txt_records)
    result_b = discover_registry("registry-beta.io", txt_records)
    print(f"  Discovery A: {result_a['status']} ({result_a['assurance']}) DNSSEC={result_a['dnssec']}")
    print(f"  Discovery B: {result_b['status']} ({result_b['assurance']}) DNSSEC={result_b.get('dnssec', False)}")
    
    # Step 2: Bootstrap
    bootstrap = BootstrapRequest(
        from_registry="registry-alpha.ai",
        to_registry="registry-beta.io",
        from_endpoint="https://registry-alpha.ai/atf",
        from_assurance=AssuranceLevel.HIGH,
        proposed_bridge_scope=["evidence_grade", "trust_score", "agent_id"]
    )
    print(f"  Bootstrap: {bootstrap.from_registry} → {bootstrap.to_registry}")
    print(f"  Scope: {bootstrap.proposed_bridge_scope}")
    
    # Step 3: Ceremony
    ceremony = CrossSigningCeremony(
        registry_a="registry-alpha.ai",
        registry_b="registry-beta.io",
        assurance_a=AssuranceLevel.HIGH,
        assurance_b=AssuranceLevel.MEDIUM,
        witnesses=["witness1@independent.org", "witness2@neutral.net", "witness3@audit.co"],
        bridge_scope=["evidence_grade", "trust_score", "agent_id"]
    )
    
    evaluation = evaluate_bridge(ceremony)
    print(f"  Ceremony: {evaluation['valid']}")
    print(f"  Bridge assurance: {evaluation['bridge_assurance']} (HIGH ∩ MEDIUM = MEDIUM)")
    print(f"  Witnesses: {evaluation['witnesses']}")
    print()


def scenario_trust_laundering():
    """RUDIMENTARY tries to bridge to HIGH — caught."""
    print("=== Scenario: Trust Laundering Attempt ===")
    
    ceremony = CrossSigningCeremony(
        registry_a="sketchy-registry.xyz",
        registry_b="trusted-registry.ai",
        assurance_a=AssuranceLevel.RUDIMENTARY,
        assurance_b=AssuranceLevel.HIGH,
        witnesses=["w1@independent.org", "w2@neutral.net", "w3@audit.co"],
        bridge_scope=["evidence_grade", "trust_score"]
    )
    
    evaluation = evaluate_bridge(ceremony)
    print(f"  HIGH ∩ RUDIMENTARY = {evaluation['bridge_assurance']}")
    print(f"  Bridge does NOT elevate sketchy registry to HIGH")
    print(f"  Agents from sketchy-registry.xyz carry RUDIMENTARY grade through bridge")
    print()


def scenario_no_dnssec():
    """Discovery without DNSSEC — warning."""
    print("=== Scenario: No DNSSEC — Unauthenticated Discovery ===")
    
    txt_records = {
        "_atf.new-registry.ai": "v=ATF1 endpoint=https://new-registry.ai/atf level=BASIC contact=admin@new-registry.ai hash=xyz789",
    }
    
    result = discover_registry("new-registry.ai", txt_records)
    print(f"  Status: {result['status']}")
    print(f"  DNSSEC: {result['dnssec']}")
    print(f"  Warning: {result.get('warning', 'none')}")
    print(f"  Key: DNS TXT = phonebook, not trust anchor. Ceremony = trust anchor.")
    print()


def scenario_missing_registry():
    """Registry not found in DNS."""
    print("=== Scenario: Registry Not Found ===")
    
    result = discover_registry("nonexistent-registry.ai", {})
    print(f"  Status: {result['status']}")
    print(f"  FQDN: {result['fqdn']}")
    print(f"  No TXT record = no ATF presence. Cannot bootstrap.")
    print()


if __name__ == "__main__":
    print("Cross-Registry Discovery — DNS TXT + SMTP Bootstrap for ATF Federation")
    print("Per santaclawd + FBCA Cross-Cert Eval Framework v5.0 (Sept 2024)")
    print("=" * 70)
    print()
    print("Three layers:")
    print("  1. DNS TXT: _atf.<domain> → endpoint + assurance (phonebook)")
    print("  2. SMTP: BOOTSTRAP_REQUEST to endpoint (first meeting)")
    print("  3. Ceremony: witnesses + transcript + hash (commitment)")
    print()
    
    scenario_full_discovery()
    scenario_trust_laundering()
    scenario_no_dnssec()
    scenario_missing_registry()
    
    print("=" * 70)
    print("KEY INSIGHT: DNS discovers, SMTP bootstraps, ceremony commits.")
    print("Bridge assurance = MIN(both registries). Trust laundering impossible.")
    print("DNSSEC adds integrity but not authorization.")
    print("CAA tells you who CAN issue, not who SHOULD.")
