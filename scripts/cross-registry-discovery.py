#!/usr/bin/env python3
"""
cross-registry-discovery.py — DNS-based cross-registry federation for ATF.

Per santaclawd: ATF V1.1 complete. Next frontier = cross-registry federation.
Per WHO SMART Trust / Regi-TRUST: DNS-based decentralized trust discovery.
"Network of networks" — each registry publishes endpoints + governance policies.

Model: DNS TXT records for ATF registry discovery.
  _atf.registry.example.com TXT "v=ATF1; endpoint=https://...; governance=https://..."

Verifiers build custom trust lists from multiple registries.
Cross-signing = scoped, unidirectional, expiring (per cross-registry-bridge.py).
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FederationMode(Enum):
    BILATERAL = "BILATERAL"       # Both registries cross-sign
    UNILATERAL = "UNILATERAL"     # One registry trusts another (not reciprocal)
    TRANSITIVE = "TRANSITIVE"     # Trust flows through intermediary
    NONE = "NONE"                 # No federation


class RegistryStatus(Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"
    UNKNOWN = "UNKNOWN"


class TrustLevel(Enum):
    FULL = "FULL"           # All grades accepted
    SCOPED = "SCOPED"       # Only specified grade ranges
    MONITOR = "MONITOR"     # Observe but don't accept grades
    NONE = "NONE"


# SPEC_CONSTANTS
DNS_TXT_PREFIX = "_atf"
MAX_FEDERATION_DEPTH = 2        # A→B→C max (no A→B→C→D)
CROSS_SIGN_MAX_TTL_DAYS = 365   # Bridges expire
GRADE_FLOOR_FOR_FEDERATION = "C"  # Don't federate D/F grades
MIN_GOVERNANCE_OVERLAP = 0.5    # 50% field coverage for FULL trust


@dataclass
class RegistryRecord:
    """DNS TXT record for ATF registry discovery."""
    registry_id: str
    domain: str
    endpoint: str
    governance_url: str
    schema_version: str
    genesis_hash: str
    supported_grades: list[str]
    anchor_type: str            # DKIM, X509, ED25519
    status: RegistryStatus = RegistryStatus.ACTIVE
    last_seen: float = 0.0
    
    def to_dns_txt(self) -> str:
        grades = ",".join(self.supported_grades)
        return (f"v=ATF1; endpoint={self.endpoint}; "
                f"governance={self.governance_url}; "
                f"schema={self.schema_version}; "
                f"genesis={self.genesis_hash[:16]}; "
                f"grades={grades}; anchor={self.anchor_type}")


@dataclass
class CrossSignBridge:
    """Scoped unidirectional trust bridge between registries."""
    source_registry: str
    target_registry: str
    scope: list[str]            # Grade range accepted
    mode: FederationMode
    trust_level: TrustLevel
    created_at: float
    expires_at: float
    bridge_hash: str = ""
    
    def __post_init__(self):
        if not self.bridge_hash:
            h = hashlib.sha256(
                f"{self.source_registry}:{self.target_registry}:{self.expires_at}".encode()
            ).hexdigest()[:16]
            self.bridge_hash = h
    
    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at
    
    @property
    def ttl_days(self) -> float:
        return max(0, (self.expires_at - time.time()) / 86400)


@dataclass
class FederationGraph:
    """Network of ATF registries with cross-sign bridges."""
    registries: dict[str, RegistryRecord] = field(default_factory=dict)
    bridges: list[CrossSignBridge] = field(default_factory=list)
    
    def add_registry(self, record: RegistryRecord):
        self.registries[record.registry_id] = record
    
    def add_bridge(self, bridge: CrossSignBridge):
        if bridge.expires_at - bridge.created_at > CROSS_SIGN_MAX_TTL_DAYS * 86400:
            raise ValueError(f"Bridge TTL exceeds max {CROSS_SIGN_MAX_TTL_DAYS} days")
        self.bridges.append(bridge)
    
    def discover_paths(self, source: str, target: str) -> list[list[str]]:
        """BFS to find all trust paths between registries."""
        if source not in self.registries or target not in self.registries:
            return []
        
        # Build adjacency from active, non-expired bridges
        adj = {}
        for b in self.bridges:
            if not b.is_expired and b.trust_level != TrustLevel.NONE:
                src = b.source_registry
                if src not in adj:
                    adj[src] = []
                adj[src].append((b.target_registry, b))
        
        # BFS with depth limit
        paths = []
        queue = [(source, [source], [])]
        while queue:
            current, path, bridge_path = queue.pop(0)
            if current == target and len(path) > 1:
                paths.append((path, bridge_path))
                continue
            if len(path) - 1 >= MAX_FEDERATION_DEPTH:
                continue
            for neighbor, bridge in adj.get(current, []):
                if neighbor not in path:  # No cycles
                    queue.append((neighbor, path + [neighbor], bridge_path + [bridge]))
        
        return paths
    
    def evaluate_path(self, path: list[str], bridges: list[CrossSignBridge]) -> dict:
        """Evaluate trust quality of a federation path."""
        if not bridges:
            return {"grade": "F", "reason": "no_bridges"}
        
        # Grade = MIN across all bridges
        grade_order = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        min_grade = "A"
        
        issues = []
        for b in bridges:
            if b.is_expired:
                return {"grade": "F", "reason": "expired_bridge", "bridge": b.bridge_hash}
            
            if b.trust_level == TrustLevel.MONITOR:
                issues.append(f"MONITOR-only bridge {b.bridge_hash}")
                min_grade = "C"
            
            if b.ttl_days < 30:
                issues.append(f"Bridge {b.bridge_hash} expires in {b.ttl_days:.0f}d")
            
            # Scope check: grades accepted
            for g in b.scope:
                if g in grade_order and grade_order.get(g, 0) < grade_order.get(GRADE_FLOOR_FOR_FEDERATION, 0):
                    issues.append(f"Bridge accepts below-floor grade {g}")
        
        # Depth penalty
        depth = len(bridges)
        if depth > 1:
            depth_penalty = depth - 1  # Each hop degrades by 1
            grade_idx = grade_order.get(min_grade, 0) - depth_penalty
            min_grade = {v: k for k, v in grade_order.items()}.get(max(0, grade_idx), "F")
        
        return {
            "grade": min_grade,
            "depth": depth,
            "path": path,
            "issues": issues,
            "all_bilateral": all(b.mode == FederationMode.BILATERAL for b in bridges),
            "min_ttl_days": min(b.ttl_days for b in bridges)
        }
    
    def governance_overlap(self, reg_a: str, reg_b: str) -> float:
        """Check governance compatibility between registries."""
        a = self.registries.get(reg_a)
        b = self.registries.get(reg_b)
        if not a or not b:
            return 0.0
        
        # Compare supported grades
        shared_grades = set(a.supported_grades) & set(b.supported_grades)
        all_grades = set(a.supported_grades) | set(b.supported_grades)
        grade_overlap = len(shared_grades) / len(all_grades) if all_grades else 0
        
        # Compare anchor types
        anchor_match = 1.0 if a.anchor_type == b.anchor_type else 0.5
        
        # Compare schema versions
        schema_match = 1.0 if a.schema_version == b.schema_version else 0.3
        
        return round((grade_overlap * 0.4 + anchor_match * 0.3 + schema_match * 0.3), 3)
    
    def audit(self) -> dict:
        """Audit the federation graph."""
        active_bridges = [b for b in self.bridges if not b.is_expired]
        expired = [b for b in self.bridges if b.is_expired]
        
        # Check for circular trust
        circular = []
        for b1 in active_bridges:
            for b2 in active_bridges:
                if (b1.source_registry == b2.target_registry and 
                    b1.target_registry == b2.source_registry):
                    circular.append((b1.source_registry, b1.target_registry))
        
        # Check for transitive chains exceeding depth
        deep_paths = []
        for src in self.registries:
            for tgt in self.registries:
                if src != tgt:
                    paths = self.discover_paths(src, tgt)
                    for path, bridges in paths:
                        if len(bridges) > MAX_FEDERATION_DEPTH:
                            deep_paths.append(path)
        
        return {
            "total_registries": len(self.registries),
            "active_bridges": len(active_bridges),
            "expired_bridges": len(expired),
            "bilateral_pairs": len(circular),
            "deep_paths_violating_max": len(deep_paths),
            "health": "HEALTHY" if not deep_paths and not expired else "NEEDS_ATTENTION"
        }


# === Scenarios ===

def scenario_bilateral_federation():
    """Two registries with bilateral trust."""
    print("=== Scenario: Bilateral Federation ===")
    now = time.time()
    
    graph = FederationGraph()
    graph.add_registry(RegistryRecord(
        "atf_alpha", "alpha.example.com",
        "https://alpha.example.com/atf/v1",
        "https://alpha.example.com/governance",
        "1.1", "aaa111", ["A", "B", "C"], "ED25519", last_seen=now
    ))
    graph.add_registry(RegistryRecord(
        "atf_beta", "beta.example.com",
        "https://beta.example.com/atf/v1",
        "https://beta.example.com/governance",
        "1.1", "bbb222", ["A", "B", "C"], "ED25519", last_seen=now
    ))
    
    # Bilateral bridges
    graph.add_bridge(CrossSignBridge(
        "atf_alpha", "atf_beta", ["A", "B"], FederationMode.BILATERAL,
        TrustLevel.FULL, now, now + 180 * 86400
    ))
    graph.add_bridge(CrossSignBridge(
        "atf_beta", "atf_alpha", ["A", "B"], FederationMode.BILATERAL,
        TrustLevel.FULL, now, now + 180 * 86400
    ))
    
    paths = graph.discover_paths("atf_alpha", "atf_beta")
    for path, bridges in paths:
        eval_result = graph.evaluate_path(path, bridges)
        print(f"  Path: {' → '.join(path)}")
        print(f"  Grade: {eval_result['grade']}, Bilateral: {eval_result['all_bilateral']}")
        print(f"  TTL: {eval_result['min_ttl_days']:.0f}d")
    
    overlap = graph.governance_overlap("atf_alpha", "atf_beta")
    print(f"  Governance overlap: {overlap:.1%}")
    
    audit = graph.audit()
    print(f"  Audit: {audit['health']}, bilateral pairs: {audit['bilateral_pairs']}")
    print()


def scenario_transitive_chain():
    """A→B→C transitive trust (depth=2)."""
    print("=== Scenario: Transitive Chain (A→B→C) ===")
    now = time.time()
    
    graph = FederationGraph()
    for name in ["alpha", "beta", "gamma"]:
        graph.add_registry(RegistryRecord(
            f"atf_{name}", f"{name}.example.com",
            f"https://{name}.example.com/atf/v1",
            f"https://{name}.example.com/governance",
            "1.1", f"{name[:3]}111", ["A", "B", "C"], "ED25519", last_seen=now
        ))
    
    graph.add_bridge(CrossSignBridge(
        "atf_alpha", "atf_beta", ["A", "B"], FederationMode.UNILATERAL,
        TrustLevel.FULL, now, now + 90 * 86400
    ))
    graph.add_bridge(CrossSignBridge(
        "atf_beta", "atf_gamma", ["A", "B"], FederationMode.UNILATERAL,
        TrustLevel.SCOPED, now, now + 90 * 86400
    ))
    
    paths = graph.discover_paths("atf_alpha", "atf_gamma")
    for path, bridges in paths:
        eval_result = graph.evaluate_path(path, bridges)
        print(f"  Path: {' → '.join(path)}")
        print(f"  Grade: {eval_result['grade']} (depth penalty applied)")
        print(f"  Depth: {eval_result['depth']}, Bilateral: {eval_result['all_bilateral']}")
    
    # No direct path gamma→alpha (unilateral)
    reverse = graph.discover_paths("atf_gamma", "atf_alpha")
    print(f"  Reverse path (gamma→alpha): {'exists' if reverse else 'NONE (unilateral)'}")
    print()


def scenario_expired_bridge():
    """Bridge expired — federation broken."""
    print("=== Scenario: Expired Bridge ===")
    now = time.time()
    
    graph = FederationGraph()
    graph.add_registry(RegistryRecord(
        "atf_alpha", "alpha.example.com", "https://alpha/atf",
        "https://alpha/gov", "1.1", "aaa", ["A", "B"], "ED25519", last_seen=now
    ))
    graph.add_registry(RegistryRecord(
        "atf_beta", "beta.example.com", "https://beta/atf",
        "https://beta/gov", "1.1", "bbb", ["A", "B"], "ED25519", last_seen=now
    ))
    
    # Expired bridge
    graph.add_bridge(CrossSignBridge(
        "atf_alpha", "atf_beta", ["A", "B"], FederationMode.BILATERAL,
        TrustLevel.FULL, now - 400 * 86400, now - 35 * 86400  # Expired 35 days ago
    ))
    
    paths = graph.discover_paths("atf_alpha", "atf_beta")
    print(f"  Paths found: {len(paths)} (expired bridges filtered)")
    
    audit = graph.audit()
    print(f"  Audit: {audit['health']}")
    print(f"  Expired bridges: {audit['expired_bridges']}")
    print()


def scenario_schema_mismatch():
    """Different schema versions — degraded governance overlap."""
    print("=== Scenario: Schema Mismatch ===")
    now = time.time()
    
    graph = FederationGraph()
    graph.add_registry(RegistryRecord(
        "atf_v11", "modern.example.com", "https://modern/atf",
        "https://modern/gov", "1.1", "mod111", ["A", "B", "C"], "ED25519", last_seen=now
    ))
    graph.add_registry(RegistryRecord(
        "atf_v10", "legacy.example.com", "https://legacy/atf",
        "https://legacy/gov", "1.0", "leg111", ["A", "B", "C", "D"], "DKIM", last_seen=now
    ))
    
    overlap = graph.governance_overlap("atf_v11", "atf_v10")
    print(f"  Governance overlap: {overlap:.1%}")
    print(f"  Schema match: {'1.1' == '1.0'} (v1.1 vs v1.0)")
    print(f"  Anchor match: {'ED25519' == 'DKIM'} (ED25519 vs DKIM)")
    print(f"  Grade overlap: A,B,C shared of A,B,C,D total = 75%")
    print(f"  Federation eligible: {'YES' if overlap >= MIN_GOVERNANCE_OVERLAP else 'NO'} (threshold: {MIN_GOVERNANCE_OVERLAP:.0%})")
    print()


if __name__ == "__main__":
    print("Cross-Registry Discovery — DNS-Based ATF Federation")
    print("Per santaclawd + WHO SMART Trust / Regi-TRUST model")
    print("=" * 70)
    print()
    print(f"DNS record format: {DNS_TXT_PREFIX}.registry.example.com TXT \"v=ATF1; ...\"")
    print(f"Max federation depth: {MAX_FEDERATION_DEPTH}")
    print(f"Max bridge TTL: {CROSS_SIGN_MAX_TTL_DAYS} days")
    print(f"Grade floor for federation: {GRADE_FLOOR_FOR_FEDERATION}")
    print()
    
    scenario_bilateral_federation()
    scenario_transitive_chain()
    scenario_expired_bridge()
    scenario_schema_mismatch()
    
    print("=" * 70)
    print("KEY INSIGHT: Federation = network of networks, not single registry.")
    print("DNS discovery: lightweight, decentralized, already deployed globally.")
    print("Bridges are scoped, unidirectional, expiring. No permanent trust.")
    print("Governance overlap check prevents incompatible federation.")
