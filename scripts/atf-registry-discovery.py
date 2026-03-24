#!/usr/bin/env python3
"""
atf-registry-discovery.py — DNS-based cross-registry discovery for ATF federation.

Per santaclawd: ATF V1.2 cross-registry discovery gap.
Per Henderson (ROW-2024): DNS as bridge for interoperable trust anchors (TRAIN framework).

Three-phase federation:
  1. DISCOVERY  — DNS TXT lookup at _atf.<domain> (unauthenticated, like DNS-SD RFC 6763)
  2. BOOTSTRAP  — SMTP handshake for first contact (authenticated, DKIM-signed)
  3. CEREMONY   — Cross-signing with witnesses (per genesis-ceremony.py)

Key insight: DNS finds who exists. Email is the first meeting. Ceremony is the treaty.
Discovery ≠ trust. FBCA learned this: cross-certification without pathLenConstraint = trust laundering.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DiscoveryPhase(Enum):
    DNS_LOOKUP = "DNS_LOOKUP"           # Phase 1: Find registry exists
    SMTP_BOOTSTRAP = "SMTP_BOOTSTRAP"   # Phase 2: First authenticated contact
    CROSS_SIGNING = "CROSS_SIGNING"     # Phase 3: Mutual recognition ceremony
    FEDERATED = "FEDERATED"             # Complete: Trust bridge active


class AssuranceLevel(Enum):
    """FBCA-mapped assurance levels for ATF registries."""
    RUDIMENTARY = "RUDIMENTARY"   # Self-signed, no audit → PROVISIONAL
    BASIC = "BASIC"               # Audited, <30 receipts → ALLEGED
    MEDIUM = "MEDIUM"             # Audited, n≥30, Wilson≥0.7 → CONFIRMED
    HIGH = "HIGH"                 # Full ceremony, n≥100, diverse → VERIFIED


class FederationStatus(Enum):
    UNKNOWN = "UNKNOWN"
    DISCOVERED = "DISCOVERED"     # DNS TXT found
    CONTACTED = "CONTACTED"       # SMTP handshake complete
    PENDING = "PENDING"           # Cross-signing proposed
    ACTIVE = "ACTIVE"             # Bridge live
    SUSPENDED = "SUSPENDED"       # Bridge paused (incident)
    REVOKED = "REVOKED"           # Bridge permanently closed


# SPEC_CONSTANTS
DNS_TXT_PREFIX = "_atf"          # _atf.<registry-domain>
MIN_ASSURANCE_FOR_FEDERATION = AssuranceLevel.BASIC
BOOTSTRAP_TIMEOUT_HOURS = 72     # SMTP bootstrap must complete within
CEREMONY_MIN_WITNESSES = 3       # Per genesis-ceremony.py
BRIDGE_MAX_AGE_DAYS = 365        # Annual renewal required
DNSSEC_REQUIRED = True           # TXT must be DNSSEC-signed


@dataclass
class DNSTXTRecord:
    """Simulated _atf TXT record."""
    domain: str
    version: str = "ATFv1"
    endpoint: str = ""            # API endpoint URL
    assurance: str = "BASIC"      # Self-declared assurance level
    policy_url: str = ""          # Registry policy document
    contact_email: str = ""       # SMTP bootstrap target
    dnssec: bool = False          # Whether DNSSEC is active
    timestamp: float = 0.0


@dataclass
class FederationBridge:
    """Cross-registry trust bridge."""
    bridge_id: str
    registry_a: str
    registry_b: str
    direction: str               # "A→B", "B→A", or "A↔B"
    assurance_floor: str         # MIN(a_assurance, b_assurance)
    phase: DiscoveryPhase = DiscoveryPhase.DNS_LOOKUP
    status: FederationStatus = FederationStatus.UNKNOWN
    discovery_timestamp: Optional[float] = None
    bootstrap_timestamp: Optional[float] = None
    ceremony_timestamp: Optional[float] = None
    ceremony_witnesses: int = 0
    ceremony_hash: str = ""
    expires_at: Optional[float] = None
    grade: str = "F"


def simulate_dns_lookup(domain: str, records: dict[str, DNSTXTRecord]) -> dict:
    """Phase 1: DNS TXT discovery."""
    key = f"_atf.{domain}"
    if key in records:
        record = records[key]
        dnssec_ok = record.dnssec if DNSSEC_REQUIRED else True
        return {
            "phase": "DNS_LOOKUP",
            "found": True,
            "domain": domain,
            "record": {
                "version": record.version,
                "endpoint": record.endpoint,
                "assurance": record.assurance,
                "contact": record.contact_email,
                "dnssec": record.dnssec
            },
            "dnssec_valid": dnssec_ok,
            "status": "DISCOVERED" if dnssec_ok else "DNSSEC_FAILED"
        }
    return {
        "phase": "DNS_LOOKUP",
        "found": False,
        "domain": domain,
        "status": "NOT_FOUND"
    }


def simulate_smtp_bootstrap(registry_a: str, registry_b_record: DNSTXTRecord) -> dict:
    """Phase 2: SMTP bootstrap handshake."""
    # Validate assurance level meets minimum
    try:
        assurance = AssuranceLevel[registry_b_record.assurance]
    except KeyError:
        return {"phase": "SMTP_BOOTSTRAP", "status": "INVALID_ASSURANCE"}
    
    min_assurance = AssuranceLevel[MIN_ASSURANCE_FOR_FEDERATION.name]
    assurance_levels = list(AssuranceLevel)
    if assurance_levels.index(assurance) < assurance_levels.index(min_assurance):
        return {
            "phase": "SMTP_BOOTSTRAP",
            "status": "BELOW_MINIMUM_ASSURANCE",
            "registry_assurance": assurance.value,
            "minimum_required": min_assurance.value
        }
    
    # Simulate DKIM-signed introduction email
    bootstrap_hash = hashlib.sha256(
        f"{registry_a}:{registry_b_record.domain}:{time.time()}".encode()
    ).hexdigest()[:16]
    
    return {
        "phase": "SMTP_BOOTSTRAP",
        "status": "CONTACTED",
        "from": registry_a,
        "to": registry_b_record.contact_email,
        "bootstrap_hash": bootstrap_hash,
        "dkim_signed": True,
        "assurance_verified": assurance.value
    }


def create_federation_bridge(
    registry_a: str, registry_b: str,
    a_assurance: AssuranceLevel, b_assurance: AssuranceLevel,
    witnesses: int, direction: str = "A→B"
) -> FederationBridge:
    """Phase 3: Create cross-signing bridge."""
    now = time.time()
    
    # Assurance floor = MIN(both registries)
    levels = list(AssuranceLevel)
    floor = min(a_assurance, b_assurance, key=lambda x: levels.index(x))
    
    # Bridge ID
    bridge_hash = hashlib.sha256(
        f"{registry_a}:{registry_b}:{now}".encode()
    ).hexdigest()[:16]
    
    bridge = FederationBridge(
        bridge_id=f"bridge_{bridge_hash}",
        registry_a=registry_a,
        registry_b=registry_b,
        direction=direction,
        assurance_floor=floor.value,
        phase=DiscoveryPhase.CROSS_SIGNING if witnesses >= CEREMONY_MIN_WITNESSES else DiscoveryPhase.SMTP_BOOTSTRAP,
        status=FederationStatus.ACTIVE if witnesses >= CEREMONY_MIN_WITNESSES else FederationStatus.PENDING,
        discovery_timestamp=now - 86400*2,
        bootstrap_timestamp=now - 86400,
        ceremony_timestamp=now if witnesses >= CEREMONY_MIN_WITNESSES else None,
        ceremony_witnesses=witnesses,
        ceremony_hash=bridge_hash,
        expires_at=now + BRIDGE_MAX_AGE_DAYS * 86400,
        grade="A" if witnesses >= 5 and floor in (AssuranceLevel.MEDIUM, AssuranceLevel.HIGH) else
              "B" if witnesses >= CEREMONY_MIN_WITNESSES else
              "C" if witnesses > 0 else "F"
    )
    return bridge


def validate_bridge(bridge: FederationBridge) -> dict:
    """Validate federation bridge health."""
    issues = []
    now = time.time()
    
    if bridge.ceremony_witnesses < CEREMONY_MIN_WITNESSES:
        issues.append(f"Insufficient witnesses: {bridge.ceremony_witnesses} < {CEREMONY_MIN_WITNESSES}")
    
    if bridge.expires_at and bridge.expires_at < now:
        issues.append("Bridge expired — requires renewal ceremony")
    
    if bridge.status == FederationStatus.SUSPENDED:
        issues.append("Bridge suspended — incident under review")
    
    # Check for trust laundering (unidirectional claimed as bidirectional)
    if bridge.direction == "A↔B" and bridge.assurance_floor == "RUDIMENTARY":
        issues.append("WARNING: Bidirectional bridge with RUDIMENTARY floor — trust laundering risk")
    
    days_remaining = (bridge.expires_at - now) / 86400 if bridge.expires_at else 0
    
    return {
        "bridge_id": bridge.bridge_id,
        "status": bridge.status.value,
        "grade": bridge.grade,
        "assurance_floor": bridge.assurance_floor,
        "witnesses": bridge.ceremony_witnesses,
        "days_remaining": round(days_remaining),
        "issues": issues,
        "healthy": len(issues) == 0
    }


# === Scenarios ===

def scenario_full_federation():
    """Complete three-phase federation between two registries."""
    print("=== Scenario: Full Federation (DNS → SMTP → Ceremony) ===")
    
    dns_records = {
        "_atf.registry-alpha.io": DNSTXTRecord(
            "registry-alpha.io", "ATFv1",
            "https://registry-alpha.io/atf/v1",
            "MEDIUM", "https://registry-alpha.io/policy",
            "atf@registry-alpha.io", True
        ),
        "_atf.registry-beta.net": DNSTXTRecord(
            "registry-beta.net", "ATFv1",
            "https://registry-beta.net/atf/v1",
            "HIGH", "https://registry-beta.net/policy",
            "atf@registry-beta.net", True
        )
    }
    
    # Phase 1: Discovery
    lookup = simulate_dns_lookup("registry-beta.net", dns_records)
    print(f"  Phase 1 DNS: {lookup['status']} (DNSSEC: {lookup.get('dnssec_valid')})")
    
    # Phase 2: Bootstrap
    bootstrap = simulate_smtp_bootstrap("registry-alpha.io", dns_records["_atf.registry-beta.net"])
    print(f"  Phase 2 SMTP: {bootstrap['status']} (DKIM: {bootstrap.get('dkim_signed')})")
    
    # Phase 3: Ceremony
    bridge = create_federation_bridge(
        "registry-alpha.io", "registry-beta.net",
        AssuranceLevel.MEDIUM, AssuranceLevel.HIGH,
        witnesses=5, direction="A↔B"
    )
    validation = validate_bridge(bridge)
    print(f"  Phase 3 Ceremony: {bridge.status.value}")
    print(f"  Bridge: {bridge.bridge_id}")
    print(f"  Assurance floor: {bridge.assurance_floor} (MIN of MEDIUM, HIGH)")
    print(f"  Grade: {validation['grade']}, Witnesses: {validation['witnesses']}")
    print(f"  Expires in: {validation['days_remaining']} days")
    print(f"  Healthy: {validation['healthy']}")
    print()


def scenario_dnssec_failure():
    """Registry without DNSSEC — discovery blocked."""
    print("=== Scenario: DNSSEC Failure ===")
    
    dns_records = {
        "_atf.sketchy-registry.xyz": DNSTXTRecord(
            "sketchy-registry.xyz", "ATFv1",
            "https://sketchy-registry.xyz/atf",
            "BASIC", "", "admin@sketchy-registry.xyz",
            dnssec=False  # No DNSSEC!
        )
    }
    
    lookup = simulate_dns_lookup("sketchy-registry.xyz", dns_records)
    print(f"  DNS found: {lookup['found']}")
    print(f"  DNSSEC valid: {lookup['dnssec_valid']}")
    print(f"  Status: {lookup['status']}")
    print(f"  → Federation blocked at Phase 1. DNSSEC = MUST.")
    print()


def scenario_assurance_floor():
    """Cross-registry bridge inherits lower assurance."""
    print("=== Scenario: Assurance Floor (Trust Laundering Prevention) ===")
    
    bridge_high_low = create_federation_bridge(
        "high-trust.org", "low-trust.io",
        AssuranceLevel.HIGH, AssuranceLevel.RUDIMENTARY,
        witnesses=5, direction="A↔B"
    )
    
    validation = validate_bridge(bridge_high_low)
    print(f"  HIGH ↔ RUDIMENTARY bridge:")
    print(f"  Floor: {bridge_high_low.assurance_floor}")
    print(f"  Issues: {validation['issues']}")
    print(f"  → Trust laundering detected. RUDIMENTARY cannot ride HIGH's reputation.")
    print()
    
    bridge_med_med = create_federation_bridge(
        "registry-a.io", "registry-b.net",
        AssuranceLevel.MEDIUM, AssuranceLevel.MEDIUM,
        witnesses=4, direction="A→B"
    )
    validation2 = validate_bridge(bridge_med_med)
    print(f"  MEDIUM → MEDIUM bridge:")
    print(f"  Floor: {bridge_med_med.assurance_floor}")
    print(f"  Grade: {validation2['grade']}")
    print(f"  Healthy: {validation2['healthy']}")
    print()


def scenario_insufficient_witnesses():
    """Ceremony without enough witnesses — bridge stays PENDING."""
    print("=== Scenario: Insufficient Witnesses ===")
    
    bridge = create_federation_bridge(
        "registry-a.io", "registry-b.net",
        AssuranceLevel.MEDIUM, AssuranceLevel.BASIC,
        witnesses=1, direction="A→B"
    )
    
    validation = validate_bridge(bridge)
    print(f"  Status: {bridge.status.value}")
    print(f"  Phase: {bridge.phase.value}")
    print(f"  Witnesses: {bridge.ceremony_witnesses} (min: {CEREMONY_MIN_WITNESSES})")
    print(f"  Issues: {validation['issues']}")
    print(f"  → Bridge stuck at PENDING. Need {CEREMONY_MIN_WITNESSES} witnesses.")
    print()


if __name__ == "__main__":
    print("ATF Registry Discovery — DNS-Based Cross-Registry Federation")
    print("Per santaclawd V1.2 + Henderson (ROW-2024) TRAIN framework")
    print("=" * 70)
    print()
    print("Three phases: DNS discovery → SMTP bootstrap → Cross-signing ceremony")
    print(f"DNSSEC required: {DNSSEC_REQUIRED}")
    print(f"Min assurance: {MIN_ASSURANCE_FOR_FEDERATION.value}")
    print(f"Min witnesses: {CEREMONY_MIN_WITNESSES}")
    print(f"Bridge max age: {BRIDGE_MAX_AGE_DAYS} days")
    print()
    
    scenario_full_federation()
    scenario_dnssec_failure()
    scenario_assurance_floor()
    scenario_insufficient_witnesses()
    
    print("=" * 70)
    print("KEY INSIGHT: Discovery ≠ trust. DNS is the phonebook.")
    print("SMTP is the first meeting. Ceremony is the treaty.")
    print("Assurance floor = MIN(both registries). No laundering upward.")
    print("FBCA cross-certification without pathLenConstraint = trust laundering.")
    print("ATF prevents this: MAX_DELEGATION_DEPTH + assurance floor inheritance.")
