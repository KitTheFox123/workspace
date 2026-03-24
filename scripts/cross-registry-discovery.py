#!/usr/bin/env python3
"""
cross-registry-discovery.py — Federation discovery for ATF cross-registry trust.

Per santaclawd: ATF V1.1 complete. Next frontier = cross-registry federation.
Per FBCA (Federal Bridge CA): mutual recognition ≠ transitive trust.

Three discovery methods:
  1. DNS SRV   — _atf-federation._tcp.registry.example (RFC 2782)
  2. Well-Known — /.well-known/atf-federation.json (RFC 8615)
  3. Mutual Introduction — existing bridge vouches for new registry

Key FBCA lessons:
  - Cross-certification maps policies, not identities
  - Bridge CA is conduit of trust, not root
  - A↔Bridge↔B ≠ A trusts B directly
  - Each registry maintains own PKI
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DiscoveryMethod(Enum):
    DNS_SRV = "DNS_SRV"                    # SRV record lookup
    WELL_KNOWN = "WELL_KNOWN"              # /.well-known/ endpoint
    MUTUAL_INTRODUCTION = "MUTUAL_INTRO"   # Existing bridge vouches


class FederationStatus(Enum):
    DISCOVERED = "DISCOVERED"       # Found, not yet verified
    VERIFIED = "VERIFIED"           # Policy compatibility confirmed
    FEDERATED = "FEDERATED"         # Active bridge established
    SUSPENDED = "SUSPENDED"         # Bridge suspended (audit failure)
    REVOKED = "REVOKED"            # Bridge permanently revoked


class TrustDirection(Enum):
    UNIDIRECTIONAL = "UNIDIRECTIONAL"  # A→B only
    BIDIRECTIONAL = "BIDIRECTIONAL"     # A↔B (two unidirectional bridges)


# SPEC_CONSTANTS
DISCOVERY_TTL_HOURS = 24           # Re-discover every 24h
BRIDGE_MAX_AGE_DAYS = 90           # Bridge expires without renewal
POLICY_FIELDS_REQUIRED = [         # Minimum fields for compatibility check
    "schema_version", "evidence_grade_scale", "error_type_enum",
    "axiom_count", "attestation_entropy_method"
]
MIN_POLICY_OVERLAP = 0.7           # 70% field compatibility required
INTRODUCTION_REQUIRES_RECEIPTS = 5  # Introducer must have 5+ receipts with target


@dataclass
class RegistryInfo:
    registry_id: str
    registry_hash: str
    endpoint: str               # Base URL
    policy_version: str
    policy_fields: dict         # Field name → spec version
    axiom_count: int
    grade_scale: str            # "A-F" or "0-100" etc
    operator_id: str
    last_audit: float           # Timestamp
    discovered_via: Optional[DiscoveryMethod] = None
    discovered_at: float = 0.0


@dataclass
class FederationBridge:
    bridge_id: str
    source_registry: str        # Registry offering trust
    target_registry: str        # Registry receiving trust
    direction: TrustDirection
    status: FederationStatus
    policy_overlap: float       # 0.0-1.0
    field_mapping: dict         # source_field → target_field
    grade_translation: dict     # source_grade → target_grade
    scope: list                 # Which grade levels transfer
    created_at: float
    expires_at: float
    introduced_by: Optional[str] = None  # For MUTUAL_INTRO
    bridge_hash: str = ""
    
    def __post_init__(self):
        if not self.bridge_hash:
            h = hashlib.sha256(
                f"{self.source_registry}:{self.target_registry}:{self.created_at}".encode()
            ).hexdigest()[:16]
            self.bridge_hash = h


def check_policy_compatibility(source: RegistryInfo, target: RegistryInfo) -> dict:
    """
    Check if two registries have compatible policies for federation.
    FBCA model: cross-certification maps policies, not identities.
    """
    source_fields = set(source.policy_fields.keys())
    target_fields = set(target.policy_fields.keys())
    
    # Required field overlap
    required_overlap = set(POLICY_FIELDS_REQUIRED)
    source_has = source_fields & required_overlap
    target_has = target_fields & required_overlap
    both_have = source_has & target_has
    
    # Total field overlap
    all_fields = source_fields | target_fields
    shared_fields = source_fields & target_fields
    overlap = len(shared_fields) / len(all_fields) if all_fields else 0
    
    # Grade scale compatibility
    grade_compatible = source.grade_scale == target.grade_scale
    
    # Axiom compatibility (target must have >= source axioms)
    axiom_compatible = target.axiom_count >= source.axiom_count
    
    # Version compatibility
    version_compatible = source.policy_version.split('.')[0] == target.policy_version.split('.')[0]
    
    compatible = (
        overlap >= MIN_POLICY_OVERLAP and
        len(both_have) == len(required_overlap) and
        grade_compatible and
        axiom_compatible and
        version_compatible
    )
    
    return {
        "compatible": compatible,
        "policy_overlap": round(overlap, 3),
        "required_fields_met": len(both_have) == len(required_overlap),
        "required_present": list(both_have),
        "required_missing": list(required_overlap - both_have),
        "grade_compatible": grade_compatible,
        "axiom_compatible": axiom_compatible,
        "version_compatible": version_compatible,
        "shared_fields": len(shared_fields),
        "total_fields": len(all_fields),
        "field_mapping": {f: f for f in shared_fields}  # Identity mapping for compatible fields
    }


def discover_dns_srv(registry_domain: str) -> Optional[RegistryInfo]:
    """Simulate DNS SRV discovery (_atf-federation._tcp.domain)."""
    # In production: dns.resolver.resolve(f"_atf-federation._tcp.{domain}", "SRV")
    known = {
        "registry-alpha.example": RegistryInfo(
            registry_id="reg_alpha", registry_hash="a1b2c3",
            endpoint="https://registry-alpha.example/atf",
            policy_version="1.1", axiom_count=3, grade_scale="A-F",
            operator_id="op_alpha", last_audit=time.time() - 86400*10,
            policy_fields={f: "1.1" for f in POLICY_FIELDS_REQUIRED + ["extra_field_1", "shared_1", "shared_2"]},
            discovered_via=DiscoveryMethod.DNS_SRV, discovered_at=time.time()
        ),
        "registry-beta.example": RegistryInfo(
            registry_id="reg_beta", registry_hash="d4e5f6",
            endpoint="https://registry-beta.example/atf",
            policy_version="1.1", axiom_count=3, grade_scale="A-F",
            operator_id="op_beta", last_audit=time.time() - 86400*5,
            policy_fields={f: "1.1" for f in POLICY_FIELDS_REQUIRED + ["extra_field_2", "shared_1", "shared_2"]},
            discovered_via=DiscoveryMethod.DNS_SRV, discovered_at=time.time()
        ),
    }
    return known.get(registry_domain)


def discover_well_known(endpoint: str) -> Optional[RegistryInfo]:
    """Simulate /.well-known/atf-federation.json discovery."""
    # In production: requests.get(f"{endpoint}/.well-known/atf-federation.json")
    if "incompatible" in endpoint:
        return RegistryInfo(
            registry_id="reg_incompat", registry_hash="x1y2z3",
            endpoint=endpoint, policy_version="2.0",  # Major version mismatch!
            axiom_count=5, grade_scale="0-100",  # Different grade scale!
            operator_id="op_incompat", last_audit=time.time() - 86400*200,
            policy_fields={"schema_version": "2.0", "custom_field": "2.0"},
            discovered_via=DiscoveryMethod.WELL_KNOWN, discovered_at=time.time()
        )
    return None


def create_bridge(source: RegistryInfo, target: RegistryInfo,
                  direction: TrustDirection = TrustDirection.UNIDIRECTIONAL,
                  introducer: Optional[str] = None) -> tuple[Optional[FederationBridge], dict]:
    """
    Create a federation bridge between two registries.
    Returns (bridge, compatibility_report).
    """
    compat = check_policy_compatibility(source, target)
    
    if not compat["compatible"]:
        return None, compat
    
    # Grade translation (identity for same scale)
    grade_trans = {}
    if source.grade_scale == target.grade_scale:
        for g in ["A", "B", "C", "D", "F"]:
            grade_trans[g] = g
    
    # Scope: only transfer grades A and B by default (conservative)
    scope = ["A", "B"]
    
    now = time.time()
    bridge = FederationBridge(
        bridge_id=f"bridge_{source.registry_id}_{target.registry_id}",
        source_registry=source.registry_id,
        target_registry=target.registry_id,
        direction=direction,
        status=FederationStatus.FEDERATED,
        policy_overlap=compat["policy_overlap"],
        field_mapping=compat["field_mapping"],
        grade_translation=grade_trans,
        scope=scope,
        created_at=now,
        expires_at=now + BRIDGE_MAX_AGE_DAYS * 86400,
        introduced_by=introducer
    )
    
    return bridge, compat


def audit_bridge(bridge: FederationBridge, source: RegistryInfo, target: RegistryInfo) -> dict:
    """Audit an existing bridge for continued validity."""
    now = time.time()
    
    issues = []
    
    # Check expiry
    if now > bridge.expires_at:
        issues.append("EXPIRED")
    elif now > bridge.expires_at - 7 * 86400:
        issues.append("EXPIRING_SOON")
    
    # Re-check compatibility
    compat = check_policy_compatibility(source, target)
    if not compat["compatible"]:
        issues.append("POLICY_DRIFT")
    
    # Check audit freshness
    if now - source.last_audit > 180 * 86400:
        issues.append("SOURCE_AUDIT_STALE")
    if now - target.last_audit > 180 * 86400:
        issues.append("TARGET_AUDIT_STALE")
    
    # Determine status
    if "EXPIRED" in issues or "POLICY_DRIFT" in issues:
        recommended_status = FederationStatus.SUSPENDED
    elif issues:
        recommended_status = FederationStatus.FEDERATED  # Warnings only
    else:
        recommended_status = FederationStatus.FEDERATED
    
    return {
        "bridge_id": bridge.bridge_id,
        "current_status": bridge.status.value,
        "recommended_status": recommended_status.value,
        "issues": issues,
        "policy_overlap": compat["policy_overlap"],
        "days_until_expiry": round((bridge.expires_at - now) / 86400, 1),
        "source_audit_age_days": round((now - source.last_audit) / 86400, 1),
        "target_audit_age_days": round((now - target.last_audit) / 86400, 1)
    }


# === Scenarios ===

def scenario_dns_discovery():
    """Discover registries via DNS SRV records."""
    print("=== Scenario: DNS SRV Discovery ===")
    
    alpha = discover_dns_srv("registry-alpha.example")
    beta = discover_dns_srv("registry-beta.example")
    
    print(f"  Discovered: {alpha.registry_id} via {alpha.discovered_via.value}")
    print(f"  Discovered: {beta.registry_id} via {beta.discovered_via.value}")
    
    bridge, compat = create_bridge(alpha, beta)
    print(f"  Compatibility: {compat['policy_overlap']:.1%} overlap")
    print(f"  Grade compatible: {compat['grade_compatible']}")
    print(f"  Bridge created: {bridge is not None}")
    if bridge:
        print(f"  Bridge: {bridge.source_registry}→{bridge.target_registry}")
        print(f"  Scope: grades {bridge.scope}")
        print(f"  Expires: {BRIDGE_MAX_AGE_DAYS} days")
    print()


def scenario_incompatible_registry():
    """Attempt to federate with incompatible registry."""
    print("=== Scenario: Incompatible Registry ===")
    
    alpha = discover_dns_srv("registry-alpha.example")
    incompat = discover_well_known("https://incompatible.example/atf")
    
    print(f"  Source: v{alpha.policy_version}, {alpha.axiom_count} axioms, scale={alpha.grade_scale}")
    print(f"  Target: v{incompat.policy_version}, {incompat.axiom_count} axioms, scale={incompat.grade_scale}")
    
    bridge, compat = create_bridge(alpha, incompat)
    print(f"  Compatible: {compat['compatible']}")
    print(f"  Policy overlap: {compat['policy_overlap']:.1%}")
    print(f"  Grade compatible: {compat['grade_compatible']}")
    print(f"  Version compatible: {compat['version_compatible']}")
    print(f"  Required fields missing: {compat['required_missing']}")
    print(f"  Bridge created: {bridge is not None}")
    print()


def scenario_mutual_introduction():
    """Registry introduced by existing federated partner."""
    print("=== Scenario: Mutual Introduction ===")
    
    alpha = discover_dns_srv("registry-alpha.example")
    beta = discover_dns_srv("registry-beta.example")
    
    # Alpha introduces Beta to a new registry (gamma)
    gamma = RegistryInfo(
        registry_id="reg_gamma", registry_hash="g7h8i9",
        endpoint="https://registry-gamma.example/atf",
        policy_version="1.1", axiom_count=3, grade_scale="A-F",
        operator_id="op_gamma", last_audit=time.time() - 86400*15,
        policy_fields={f: "1.1" for f in POLICY_FIELDS_REQUIRED},
        discovered_via=DiscoveryMethod.MUTUAL_INTRODUCTION,
        discovered_at=time.time()
    )
    
    bridge, compat = create_bridge(beta, gamma, introducer=alpha.registry_id)
    print(f"  Introducer: {alpha.registry_id}")
    print(f"  Bridge: {beta.registry_id}→{gamma.registry_id}")
    print(f"  Compatible: {compat['compatible']}")
    if bridge:
        print(f"  Introduced by: {bridge.introduced_by}")
        print(f"  Key: A↔Bridge↔B ≠ A trusts B directly (FBCA model)")
    print()


def scenario_bridge_audit():
    """Audit existing bridge for continued validity."""
    print("=== Scenario: Bridge Audit ===")
    
    alpha = discover_dns_srv("registry-alpha.example")
    beta = discover_dns_srv("registry-beta.example")
    
    bridge, compat = create_bridge(alpha, beta)
    if not bridge:
        print(f"  Bridge creation failed: overlap={compat['policy_overlap']:.1%}")
        return
    
    # Simulate fresh bridge
    audit1 = audit_bridge(bridge, alpha, beta)
    print(f"  Fresh bridge: status={audit1['recommended_status']}, issues={audit1['issues']}")
    print(f"  Days until expiry: {audit1['days_until_expiry']}")
    
    # Simulate stale audit
    alpha_stale = RegistryInfo(
        registry_id="reg_alpha", registry_hash="a1b2c3",
        endpoint="https://registry-alpha.example/atf",
        policy_version="1.1", axiom_count=3, grade_scale="A-F",
        operator_id="op_alpha", last_audit=time.time() - 86400*200,  # 200 days!
        policy_fields={f: "1.1" for f in POLICY_FIELDS_REQUIRED}
    )
    
    audit2 = audit_bridge(bridge, alpha_stale, beta)
    print(f"  Stale audit: status={audit2['recommended_status']}, issues={audit2['issues']}")
    print(f"  Source audit age: {audit2['source_audit_age_days']} days")
    print()


if __name__ == "__main__":
    print("Cross-Registry Discovery — ATF Federation via FBCA Model")
    print("Per santaclawd: ATF V1.1 complete. Next = cross-registry federation.")
    print("=" * 70)
    print()
    print("Three discovery methods:")
    print("  1. DNS SRV: _atf-federation._tcp.registry.example")
    print("  2. Well-Known: /.well-known/atf-federation.json")
    print("  3. Mutual Introduction: existing bridge vouches")
    print()
    
    scenario_dns_discovery()
    scenario_incompatible_registry()
    scenario_mutual_introduction()
    scenario_bridge_audit()
    
    print("=" * 70)
    print("KEY FBCA LESSONS:")
    print("  1. Cross-certification maps POLICIES, not identities")
    print("  2. Bridge is conduit of trust, not root")
    print("  3. A↔Bridge↔B ≠ A trusts B directly")
    print("  4. Each registry maintains own PKI")
    print("  5. Unidirectional bridges by default (conservative)")
