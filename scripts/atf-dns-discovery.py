#!/usr/bin/env python3
"""
atf-dns-discovery.py — DNS TXT-based cross-registry discovery for ATF.

Per santaclawd: "how does ATF-A find ATF-B exists?"
Model: DMARC (RFC 7489) _dmarc.domain TXT records + DANE (RFC 7671) cert pinning.

Three-phase bootstrap:
  1. DISCOVERY — _atf.<domain> DNS TXT → endpoint + assurance_level + policy_hash
  2. BOOTSTRAP — SMTP handshake → exchange genesis hashes  
  3. CEREMONY — Authenticated cross-signing → bridge established

TXT record format:
  v=ATF1; endpoint=https://registry.example/atf; level=CONFIRMED;
  policy=sha256:<hash>; contact=admin@registry.example

Who audits the TXT record? Hash(TXT) in receipt chain = any change detectable.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AssuranceLevel(Enum):
    PROVISIONAL = "PROVISIONAL"  # FBCA RUDIMENTARY: n<10, Wilson CI < 0.5
    ALLEGED = "ALLEGED"          # FBCA BASIC: n≥10, Wilson CI ≥ 0.5
    CONFIRMED = "CONFIRMED"      # FBCA MEDIUM: n≥30, Wilson CI ≥ 0.7
    VERIFIED = "VERIFIED"        # FBCA HIGH: n≥100, Wilson CI ≥ 0.9


class DiscoveryPhase(Enum):
    DNS_LOOKUP = "DNS_LOOKUP"
    SMTP_BOOTSTRAP = "SMTP_BOOTSTRAP"
    CROSS_SIGN_CEREMONY = "CROSS_SIGN_CEREMONY"


class BridgeStatus(Enum):
    DISCOVERED = "DISCOVERED"
    BOOTSTRAPPED = "BOOTSTRAPPED"
    FEDERATED = "FEDERATED"
    STALE = "STALE"
    REVOKED = "REVOKED"


# SPEC_CONSTANTS
TXT_PREFIX = "_atf"
TXT_VERSION = "ATF1"
MIN_ASSURANCE_FOR_BRIDGE = AssuranceLevel.ALLEGED
BRIDGE_MAX_AGE_DAYS = 90
TXT_AUDIT_INTERVAL_HOURS = 24
BOOTSTRAP_TIMEOUT_SECONDS = 300


@dataclass
class ATFTxtRecord:
    """Parsed _atf DNS TXT record."""
    domain: str
    version: str
    endpoint: str
    assurance_level: AssuranceLevel
    policy_hash: str
    contact: str
    raw_txt: str = ""
    record_hash: str = ""
    
    def __post_init__(self):
        if not self.record_hash:
            self.record_hash = hashlib.sha256(self.raw_txt.encode()).hexdigest()[:16]


@dataclass
class RegistryBridge:
    """Cross-registry bridge established via DNS discovery."""
    source_domain: str
    target_domain: str
    source_level: AssuranceLevel
    target_level: AssuranceLevel
    bridge_level: AssuranceLevel  # MIN(source, target)
    phase: DiscoveryPhase
    status: BridgeStatus
    discovered_at: float
    bootstrapped_at: Optional[float] = None
    federated_at: Optional[float] = None
    txt_hash_at_discovery: str = ""
    current_txt_hash: str = ""
    bridge_hash: str = ""


def parse_txt_record(domain: str, raw_txt: str) -> ATFTxtRecord:
    """Parse an _atf DNS TXT record."""
    fields = {}
    for part in raw_txt.split(";"):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key.strip()] = value.strip()
    
    level_map = {
        "PROVISIONAL": AssuranceLevel.PROVISIONAL,
        "ALLEGED": AssuranceLevel.ALLEGED,
        "CONFIRMED": AssuranceLevel.CONFIRMED,
        "VERIFIED": AssuranceLevel.VERIFIED
    }
    
    return ATFTxtRecord(
        domain=domain,
        version=fields.get("v", ""),
        endpoint=fields.get("endpoint", ""),
        assurance_level=level_map.get(fields.get("level", ""), AssuranceLevel.PROVISIONAL),
        policy_hash=fields.get("policy", ""),
        contact=fields.get("contact", ""),
        raw_txt=raw_txt
    )


def validate_txt_record(record: ATFTxtRecord) -> dict:
    """Validate a parsed TXT record."""
    issues = []
    
    if record.version != TXT_VERSION:
        issues.append(f"Version mismatch: expected {TXT_VERSION}, got {record.version}")
    
    if not record.endpoint:
        issues.append("Missing endpoint URL")
    elif not record.endpoint.startswith("https://"):
        issues.append("Endpoint must use HTTPS")
    
    if not record.policy_hash:
        issues.append("Missing policy hash")
    elif not record.policy_hash.startswith("sha256:"):
        issues.append("Policy hash must use sha256: prefix")
    
    if not record.contact:
        issues.append("Missing contact email")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "record_hash": record.record_hash,
        "assurance_level": record.assurance_level.value
    }


def compute_bridge_level(source: AssuranceLevel, target: AssuranceLevel) -> AssuranceLevel:
    """Bridge inherits LOWER of two registries' assurance levels."""
    order = [AssuranceLevel.PROVISIONAL, AssuranceLevel.ALLEGED, 
             AssuranceLevel.CONFIRMED, AssuranceLevel.VERIFIED]
    source_idx = order.index(source)
    target_idx = order.index(target)
    return order[min(source_idx, target_idx)]


def establish_bridge(source: ATFTxtRecord, target: ATFTxtRecord) -> RegistryBridge:
    """Establish a cross-registry bridge via DNS discovery."""
    now = time.time()
    bridge_level = compute_bridge_level(source.assurance_level, target.assurance_level)
    
    # Check minimum assurance
    min_level_order = [AssuranceLevel.PROVISIONAL, AssuranceLevel.ALLEGED,
                       AssuranceLevel.CONFIRMED, AssuranceLevel.VERIFIED]
    if min_level_order.index(bridge_level) < min_level_order.index(MIN_ASSURANCE_FOR_BRIDGE):
        bridge_level = AssuranceLevel.PROVISIONAL  # Degraded
    
    bridge_hash = hashlib.sha256(
        f"{source.record_hash}:{target.record_hash}:{now}".encode()
    ).hexdigest()[:16]
    
    return RegistryBridge(
        source_domain=source.domain,
        target_domain=target.domain,
        source_level=source.assurance_level,
        target_level=target.assurance_level,
        bridge_level=bridge_level,
        phase=DiscoveryPhase.DNS_LOOKUP,
        status=BridgeStatus.DISCOVERED,
        discovered_at=now,
        txt_hash_at_discovery=target.record_hash,
        current_txt_hash=target.record_hash,
        bridge_hash=bridge_hash
    )


def audit_txt_change(bridge: RegistryBridge, new_txt_hash: str) -> dict:
    """Detect TXT record changes (potential registry compromise or update)."""
    changed = bridge.txt_hash_at_discovery != new_txt_hash
    bridge.current_txt_hash = new_txt_hash
    
    if changed:
        return {
            "status": "TXT_CHANGED",
            "action": "RE_BOOTSTRAP_REQUIRED",
            "old_hash": bridge.txt_hash_at_discovery,
            "new_hash": new_txt_hash,
            "bridge_status": "STALE — TXT record changed since discovery"
        }
    
    return {
        "status": "TXT_UNCHANGED",
        "action": "NONE",
        "hash": new_txt_hash,
        "bridge_status": bridge.status.value
    }


def simulate_discovery_flow(source_txt: str, target_txt: str, 
                           source_domain: str, target_domain: str) -> dict:
    """Simulate full three-phase discovery flow."""
    # Phase 1: DNS Discovery
    source = parse_txt_record(source_domain, source_txt)
    target = parse_txt_record(target_domain, target_txt)
    
    source_valid = validate_txt_record(source)
    target_valid = validate_txt_record(target)
    
    if not source_valid["valid"] or not target_valid["valid"]:
        return {
            "phase": "DNS_LOOKUP",
            "status": "FAILED",
            "source_issues": source_valid["issues"],
            "target_issues": target_valid["issues"]
        }
    
    # Phase 2: Bridge establishment
    bridge = establish_bridge(source, target)
    bridge.phase = DiscoveryPhase.SMTP_BOOTSTRAP
    bridge.status = BridgeStatus.BOOTSTRAPPED
    bridge.bootstrapped_at = time.time()
    
    # Phase 3: Federation (cross-signing)
    bridge.phase = DiscoveryPhase.CROSS_SIGN_CEREMONY
    bridge.status = BridgeStatus.FEDERATED
    bridge.federated_at = time.time()
    
    return {
        "phase": "COMPLETE",
        "status": "FEDERATED",
        "bridge_level": bridge.bridge_level.value,
        "source": f"{source_domain} ({source.assurance_level.value})",
        "target": f"{target_domain} ({target.assurance_level.value})",
        "bridge_hash": bridge.bridge_hash,
        "txt_hash_source": source.record_hash,
        "txt_hash_target": target.record_hash
    }


# === Scenarios ===

def scenario_normal_discovery():
    """Two CONFIRMED registries discover each other."""
    print("=== Scenario: Normal Discovery (CONFIRMED↔CONFIRMED) ===")
    result = simulate_discovery_flow(
        "v=ATF1; endpoint=https://registry-a.example/atf; level=CONFIRMED; policy=sha256:abc123; contact=admin@registry-a.example",
        "v=ATF1; endpoint=https://registry-b.example/atf; level=CONFIRMED; policy=sha256:def456; contact=admin@registry-b.example",
        "registry-a.example", "registry-b.example"
    )
    print(f"  Status: {result['status']}")
    print(f"  Bridge level: {result['bridge_level']}")
    print(f"  Source: {result['source']}")
    print(f"  Target: {result['target']}")
    print()


def scenario_asymmetric_levels():
    """VERIFIED registry bridges to PROVISIONAL — inherits LOWER."""
    print("=== Scenario: Asymmetric Levels (VERIFIED↔PROVISIONAL) ===")
    result = simulate_discovery_flow(
        "v=ATF1; endpoint=https://trusted.example/atf; level=VERIFIED; policy=sha256:abc; contact=a@trusted.example",
        "v=ATF1; endpoint=https://new.example/atf; level=PROVISIONAL; policy=sha256:def; contact=a@new.example",
        "trusted.example", "new.example"
    )
    print(f"  Bridge level: {result['bridge_level']} (MIN of VERIFIED, PROVISIONAL)")
    print(f"  Prevents trust laundering: VERIFIED registry cannot uplift PROVISIONAL")
    print()


def scenario_invalid_txt():
    """Malformed TXT record — discovery fails."""
    print("=== Scenario: Invalid TXT Record ===")
    result = simulate_discovery_flow(
        "v=ATF1; endpoint=https://good.example/atf; level=CONFIRMED; policy=sha256:abc; contact=a@good.example",
        "v=ATF2; endpoint=http://bad.example/atf; level=CONFIRMED; contact=a@bad.example",
        "good.example", "bad.example"
    )
    print(f"  Status: {result['status']}")
    print(f"  Target issues: {result.get('target_issues', [])}")
    print()


def scenario_txt_change_detection():
    """TXT record changes after bridge established — stale detected."""
    print("=== Scenario: TXT Change Detection ===")
    source = parse_txt_record("a.example", "v=ATF1; endpoint=https://a.example/atf; level=CONFIRMED; policy=sha256:abc; contact=a@a.example")
    target = parse_txt_record("b.example", "v=ATF1; endpoint=https://b.example/atf; level=CONFIRMED; policy=sha256:def; contact=b@b.example")
    
    bridge = establish_bridge(source, target)
    bridge.status = BridgeStatus.FEDERATED
    
    # TXT record changes (e.g., new endpoint or policy)
    new_target = parse_txt_record("b.example", "v=ATF1; endpoint=https://b-new.example/atf; level=CONFIRMED; policy=sha256:ghi; contact=b@b.example")
    
    audit = audit_txt_change(bridge, new_target.record_hash)
    print(f"  TXT changed: {audit['status']}")
    print(f"  Action: {audit['action']}")
    print(f"  Old hash: {audit['old_hash']}")
    print(f"  New hash: {audit['new_hash']}")
    print()


def scenario_discovery_network():
    """Multiple registries forming a discovery network."""
    print("=== Scenario: Discovery Network (A→B→C) ===")
    registries = [
        ("alpha.example", "v=ATF1; endpoint=https://alpha.example/atf; level=VERIFIED; policy=sha256:aaa; contact=a@alpha.example"),
        ("beta.example", "v=ATF1; endpoint=https://beta.example/atf; level=CONFIRMED; policy=sha256:bbb; contact=b@beta.example"),
        ("gamma.example", "v=ATF1; endpoint=https://gamma.example/atf; level=ALLEGED; policy=sha256:ccc; contact=c@gamma.example"),
    ]
    
    records = [parse_txt_record(d, t) for d, t in registries]
    
    # A→B bridge
    ab = establish_bridge(records[0], records[1])
    print(f"  A→B: {ab.bridge_level.value} (MIN of VERIFIED, CONFIRMED)")
    
    # B→C bridge
    bc = establish_bridge(records[1], records[2])
    print(f"  B→C: {bc.bridge_level.value} (MIN of CONFIRMED, ALLEGED)")
    
    # A→C transitive? NO — bridges are not transitive
    print(f"  A→C: NOT ESTABLISHED (bridges are NOT transitive)")
    print(f"  A must discover C independently via _atf.gamma.example TXT")
    print(f"  FBCA model: mutual recognition ≠ transitive trust")
    print()


if __name__ == "__main__":
    print("ATF DNS Discovery — Cross-Registry Discovery via DNS TXT Records")
    print("Per santaclawd + DMARC (RFC 7489) + DANE (RFC 7671)")
    print("=" * 70)
    print()
    print("Format: _atf.<domain> TXT \"v=ATF1; endpoint=...; level=...; policy=sha256:...; contact=...\"")
    print()
    print("Three phases:")
    print("  1. DNS_LOOKUP    → unauthenticated discovery")
    print("  2. SMTP_BOOTSTRAP → genesis hash exchange")
    print("  3. CROSS_SIGN    → authenticated federation")
    print()
    
    scenario_normal_discovery()
    scenario_asymmetric_levels()
    scenario_invalid_txt()
    scenario_txt_change_detection()
    scenario_discovery_network()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. DNS is the phonebook. SMTP is the first meeting. Receipts are the relationship.")
    print("2. Bridge level = MIN(source, target). Prevents trust laundering.")
    print("3. Bridges are NOT transitive. A→B + B→C ≠ A→C.")
    print("4. TXT hash in receipt chain = any change detectable (CT log model).")
    print("5. DMARC + DANE already solved this for email. Steal the pattern.")
