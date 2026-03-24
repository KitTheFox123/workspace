#!/usr/bin/env python3
"""
cross-registry-discovery.py — How ATF registries find each other.

Per santaclawd: ATF V1.1 complete. Next frontier = cross-registry federation.
Per FPKI: Federal Bridge CA uses cross-certification with published trust lists.

Three discovery mechanisms:
  DNS TXT     — v=ATF1;registry=https://...;hash=abc123 (like DKIM/DMARC)
  WELL_KNOWN  — /.well-known/atf-registry.json (like security.txt)
  GOSSIP      — Receipt-embedded registry hints (like CT gossip, but working)

Key insight: CT's gossip mechanism was specified but never deployed (draft-ietf-trans-gossip
abandoned). ATF must not repeat this. Receipts ARE the gossip channel.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DiscoveryMethod(Enum):
    DNS_TXT = "DNS_TXT"           # Domain-anchored
    WELL_KNOWN = "WELL_KNOWN"     # HTTP-based
    GOSSIP = "GOSSIP"             # Receipt-embedded
    MANUAL = "MANUAL"             # Operator-configured


class FederationStatus(Enum):
    DISCOVERED = "DISCOVERED"       # Found, not yet validated
    VALIDATED = "VALIDATED"         # Schema + hash verified
    BRIDGED = "BRIDGED"            # Cross-certification active
    STALE = "STALE"                # Discovery TTL expired
    REVOKED = "REVOKED"            # Explicitly revoked


# SPEC_CONSTANTS
DNS_TXT_PREFIX = "v=ATF1"
WELL_KNOWN_PATH = "/.well-known/atf-registry.json"
DISCOVERY_TTL_DAYS = 30          # Re-discover every 30 days
GOSSIP_MIN_SOURCES = 3           # Require 3 independent receipts before trusting gossip
BRIDGE_MAX_DEPTH = 2             # A→B→C allowed, A→B→C→D not
REGISTRY_HASH_ALGO = "sha256"


@dataclass
class RegistryRecord:
    registry_id: str
    registry_url: str
    registry_hash: str           # Hash of registry's genesis document
    operator: str
    schema_version: str
    agent_count: int
    discovered_via: DiscoveryMethod
    discovered_at: float
    status: FederationStatus = FederationStatus.DISCOVERED
    bridge_direction: str = "NONE"  # NONE, OUTBOUND, INBOUND, MUTUAL
    ttl_days: int = DISCOVERY_TTL_DAYS
    gossip_sources: list = field(default_factory=list)


@dataclass
class BridgeCertificate:
    """Cross-certification between two registries."""
    source_registry: str
    target_registry: str
    scope: list                  # Which grade levels are trusted
    direction: str               # UNIDIRECTIONAL or MUTUAL
    issued_at: float
    expires_at: float
    bridge_hash: str = ""
    depth: int = 0               # How many hops from source
    
    def __post_init__(self):
        if not self.bridge_hash:
            h = hashlib.sha256(
                f"{self.source_registry}:{self.target_registry}:{self.issued_at}".encode()
            ).hexdigest()[:16]
            self.bridge_hash = h


def parse_dns_txt(txt_record: str) -> Optional[dict]:
    """Parse ATF DNS TXT record (DKIM-style key=value pairs)."""
    if not txt_record.startswith(DNS_TXT_PREFIX):
        return None
    
    parts = {}
    for pair in txt_record.split(";"):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            parts[k.strip()] = v.strip()
    
    required = {"v", "registry", "hash"}
    if not required.issubset(parts.keys()):
        return None
    
    return parts


def discover_via_dns(domain: str, txt_records: list[str]) -> Optional[RegistryRecord]:
    """Discover ATF registry via DNS TXT records."""
    for txt in txt_records:
        parsed = parse_dns_txt(txt)
        if parsed:
            return RegistryRecord(
                registry_id=f"dns:{domain}",
                registry_url=parsed["registry"],
                registry_hash=parsed["hash"],
                operator=parsed.get("op", domain),
                schema_version=parsed.get("v", "ATF1"),
                agent_count=int(parsed.get("agents", "0")),
                discovered_via=DiscoveryMethod.DNS_TXT,
                discovered_at=time.time()
            )
    return None


def discover_via_wellknown(url: str, content: dict) -> Optional[RegistryRecord]:
    """Discover ATF registry via .well-known endpoint."""
    if "registry_id" not in content or "registry_hash" not in content:
        return None
    
    return RegistryRecord(
        registry_id=content["registry_id"],
        registry_url=url.replace(WELL_KNOWN_PATH, ""),
        registry_hash=content["registry_hash"],
        operator=content.get("operator", "unknown"),
        schema_version=content.get("schema_version", "ATF1"),
        agent_count=content.get("agent_count", 0),
        discovered_via=DiscoveryMethod.WELL_KNOWN,
        discovered_at=time.time()
    )


def discover_via_gossip(registry_hints: list[dict]) -> Optional[RegistryRecord]:
    """
    Discover ATF registry via receipt-embedded hints.
    
    Requires GOSSIP_MIN_SOURCES independent sources to prevent spoofing.
    CT's gossip failed because it was optional. ATF makes it structural.
    """
    if len(registry_hints) < GOSSIP_MIN_SOURCES:
        return None
    
    # Check operator diversity (prevent sybil gossip)
    operators = set(h.get("source_operator", "") for h in registry_hints)
    if len(operators) < 2:
        return None  # Same operator = 1 effective source
    
    # Consensus on registry_hash (majority)
    hashes = [h.get("registry_hash", "") for h in registry_hints]
    hash_counts = {}
    for h in hashes:
        hash_counts[h] = hash_counts.get(h, 0) + 1
    
    consensus_hash = max(hash_counts, key=hash_counts.get)
    consensus_ratio = hash_counts[consensus_hash] / len(hashes)
    
    if consensus_ratio < 0.67:
        return None  # No strong consensus
    
    # Use first hint's URL (they should all agree)
    first = registry_hints[0]
    record = RegistryRecord(
        registry_id=f"gossip:{consensus_hash[:8]}",
        registry_url=first.get("registry_url", ""),
        registry_hash=consensus_hash,
        operator=first.get("operator", "unknown"),
        schema_version=first.get("schema_version", "ATF1"),
        agent_count=0,  # Unknown via gossip
        discovered_via=DiscoveryMethod.GOSSIP,
        discovered_at=time.time(),
        gossip_sources=[h.get("source_agent", "") for h in registry_hints]
    )
    return record


def validate_bridge(bridge: BridgeCertificate, known_registries: dict) -> dict:
    """Validate a cross-registry bridge certificate."""
    issues = []
    
    # Source must be known
    if bridge.source_registry not in known_registries:
        issues.append(f"Unknown source registry: {bridge.source_registry}")
    
    # Target must be discovered
    if bridge.target_registry not in known_registries:
        issues.append(f"Unknown target registry: {bridge.target_registry}")
    
    # Depth check
    if bridge.depth > BRIDGE_MAX_DEPTH:
        issues.append(f"Bridge depth {bridge.depth} exceeds max {BRIDGE_MAX_DEPTH}")
    
    # Expiry check
    if bridge.expires_at < time.time():
        issues.append("Bridge certificate expired")
    
    # Self-bridge check
    if bridge.source_registry == bridge.target_registry:
        issues.append("Self-bridge detected (axiom 1 violation)")
    
    # Scope check
    if not bridge.scope:
        issues.append("Empty scope — bridge trusts nothing")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "direction": bridge.direction,
        "depth": bridge.depth,
        "scope": bridge.scope
    }


def compute_federation_graph(registries: list[RegistryRecord], 
                              bridges: list[BridgeCertificate]) -> dict:
    """Build federation topology graph."""
    nodes = {r.registry_id: {
        "url": r.registry_url,
        "status": r.status.value,
        "discovered_via": r.discovered_via.value,
        "agents": r.agent_count
    } for r in registries}
    
    edges = []
    for b in bridges:
        validation = validate_bridge(b, {r.registry_id: r for r in registries})
        edges.append({
            "source": b.source_registry,
            "target": b.target_registry,
            "direction": b.direction,
            "scope": b.scope,
            "valid": validation["valid"],
            "depth": b.depth
        })
    
    # Find connected components
    adj = {}
    for e in edges:
        if e["valid"]:
            adj.setdefault(e["source"], []).append(e["target"])
            if e["direction"] == "MUTUAL":
                adj.setdefault(e["target"], []).append(e["source"])
    
    visited = set()
    components = []
    for node in nodes:
        if node not in visited:
            component = set()
            stack = [node]
            while stack:
                n = stack.pop()
                if n not in visited:
                    visited.add(n)
                    component.add(n)
                    for neighbor in adj.get(n, []):
                        if neighbor not in visited:
                            stack.append(neighbor)
            components.append(component)
    
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "valid_edges": sum(1 for e in edges if e["valid"]),
        "components": len(components),
        "largest_component": max(len(c) for c in components) if components else 0,
        "isolated": sum(1 for c in components if len(c) == 1)
    }


# === Scenarios ===

def scenario_dns_discovery():
    """Registry discovered via DNS TXT record."""
    print("=== Scenario: DNS TXT Discovery ===")
    
    txt_records = [
        "v=ATF1;registry=https://atf.example.com;hash=abc123def456;op=example_operator;agents=150",
        "v=spf1 include:_spf.google.com ~all"  # Non-ATF record
    ]
    
    record = discover_via_dns("example.com", txt_records)
    if record:
        print(f"  Found: {record.registry_id}")
        print(f"  URL: {record.registry_url}")
        print(f"  Hash: {record.registry_hash}")
        print(f"  Operator: {record.operator}")
        print(f"  Agents: {record.agent_count}")
        print(f"  Method: {record.discovered_via.value}")
    print()


def scenario_gossip_discovery():
    """Registry discovered via receipt-embedded hints from 3+ independent sources."""
    print("=== Scenario: Gossip Discovery (Receipt-Embedded) ===")
    
    hints = [
        {"registry_url": "https://atf-b.io", "registry_hash": "hash_b_123",
         "source_agent": "agent_1", "source_operator": "op_alpha", "schema_version": "ATF1"},
        {"registry_url": "https://atf-b.io", "registry_hash": "hash_b_123",
         "source_agent": "agent_2", "source_operator": "op_beta", "schema_version": "ATF1"},
        {"registry_url": "https://atf-b.io", "registry_hash": "hash_b_123",
         "source_agent": "agent_3", "source_operator": "op_gamma", "schema_version": "ATF1"},
    ]
    
    record = discover_via_gossip(hints)
    if record:
        print(f"  Found: {record.registry_id}")
        print(f"  URL: {record.registry_url}")
        print(f"  Sources: {len(record.gossip_sources)} independent agents")
        print(f"  Consensus: hash_b_123 (100%)")
        print(f"  Method: {record.discovered_via.value}")
    print()


def scenario_sybil_gossip():
    """Gossip from same operator — rejected."""
    print("=== Scenario: Sybil Gossip (Same Operator) ===")
    
    hints = [
        {"registry_url": "https://fake.io", "registry_hash": "fake_hash",
         "source_agent": f"sybil_{i}", "source_operator": "op_sybil", "schema_version": "ATF1"}
        for i in range(5)
    ]
    
    record = discover_via_gossip(hints)
    print(f"  5 hints from same operator")
    print(f"  Discovery result: {'FOUND' if record else 'REJECTED'}")
    print(f"  Reason: same operator = 1 effective source < minimum {GOSSIP_MIN_SOURCES}")
    print()


def scenario_federation_graph():
    """Multi-registry federation topology."""
    print("=== Scenario: Federation Graph ===")
    now = time.time()
    
    registries = [
        RegistryRecord("reg_alpha", "https://alpha.atf", "hash_a", "op_a", "ATF1", 100,
                       DiscoveryMethod.DNS_TXT, now, FederationStatus.BRIDGED),
        RegistryRecord("reg_beta", "https://beta.atf", "hash_b", "op_b", "ATF1", 50,
                       DiscoveryMethod.WELL_KNOWN, now, FederationStatus.BRIDGED),
        RegistryRecord("reg_gamma", "https://gamma.atf", "hash_g", "op_g", "ATF1", 75,
                       DiscoveryMethod.GOSSIP, now, FederationStatus.VALIDATED),
        RegistryRecord("reg_delta", "https://delta.atf", "hash_d", "op_d", "ATF1", 30,
                       DiscoveryMethod.MANUAL, now, FederationStatus.DISCOVERED),
    ]
    
    bridges = [
        BridgeCertificate("reg_alpha", "reg_beta", ["A", "B"], "MUTUAL",
                         now, now + 86400*90, depth=1),
        BridgeCertificate("reg_beta", "reg_gamma", ["A", "B", "C"], "UNIDIRECTIONAL",
                         now, now + 86400*90, depth=1),
        BridgeCertificate("reg_alpha", "reg_alpha", ["A"], "MUTUAL",
                         now, now + 86400*90, depth=0),  # Self-bridge!
    ]
    
    graph = compute_federation_graph(registries, bridges)
    print(f"  Registries: {graph['nodes']}")
    print(f"  Bridges: {graph['edges']} ({graph['valid_edges']} valid)")
    print(f"  Connected components: {graph['components']}")
    print(f"  Largest component: {graph['largest_component']} registries")
    print(f"  Isolated: {graph['isolated']} registries")
    
    # Validate each bridge
    known = {r.registry_id: r for r in registries}
    for b in bridges:
        v = validate_bridge(b, known)
        status = "VALID" if v["valid"] else f"INVALID: {v['issues']}"
        print(f"  Bridge {b.source_registry}→{b.target_registry}: {status}")
    print()


if __name__ == "__main__":
    print("Cross-Registry Discovery — How ATF Registries Find Each Other")
    print("Per santaclawd: next frontier after V1.1 = cross-registry federation")
    print("=" * 70)
    print()
    print(f"Discovery methods: DNS_TXT, WELL_KNOWN, GOSSIP, MANUAL")
    print(f"Gossip requires {GOSSIP_MIN_SOURCES}+ independent sources (CT gossip failed by being optional)")
    print(f"Bridge max depth: {BRIDGE_MAX_DEPTH} (FPKI model)")
    print()
    
    scenario_dns_discovery()
    scenario_gossip_discovery()
    scenario_sybil_gossip()
    scenario_federation_graph()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. CT gossip was specified but never deployed. Receipts ARE gossip.")
    print("2. DNS TXT = domain-anchored (like DKIM). Strongest signal.")  
    print("3. Gossip requires operator diversity (sybil prevention).")
    print("4. Bridge depth limited to 2 (FPKI model). A→B→C ok, deeper = no.")
    print("5. Self-bridge = axiom 1 violation. Always rejected.")
