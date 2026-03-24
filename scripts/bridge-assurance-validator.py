#!/usr/bin/env python3
"""
bridge-assurance-validator.py — Cross-registry bridge trust validation for ATF V1.2.

Per santaclawd: bridge should be bottleneck not passthrough.
FBCA "weakest link" constraint: bridge_grade = MIN(bridge, source, target).
PROVISIONAL bridge cannot transit VERIFIED agents.

Three discovery paths (multi-path for resilience):
  1. _atf.<domain> DNS TXT
  2. .well-known/atf HTTPS endpoint  
  3. CT log entry

Any 2-of-3 agree = valid discovery. TOFU on first contact, pin thereafter.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AssuranceLevel(Enum):
    VERIFIED = 4      # Full audit, multi-witness ceremony
    ESTABLISHED = 3   # Consistent behavior, sufficient receipts
    PROVISIONAL = 2   # New, building trust
    UNTRUSTED = 1     # No relationship
    REVOKED = 0       # Explicitly revoked


class DiscoveryPath(Enum):
    DNS_TXT = "dns_txt"           # _atf.<domain> TXT record
    HTTPS_WELLKNOWN = "https_wk"  # .well-known/atf endpoint
    CT_LOG = "ct_log"             # Certificate Transparency log entry


# SPEC_CONSTANTS
MIN_DISCOVERY_AGREEMENT = 2  # 2-of-3 paths must agree
BRIDGE_CAP_ENABLED = True     # Bridge caps transit assurance
TOFU_PIN_DURATION_DAYS = 90   # Pin discovered endpoint for 90 days
BRIDGE_MAX_CHAIN_DEPTH = 3    # Max hops through bridges


@dataclass
class RegistryEndpoint:
    domain: str
    endpoint_url: str
    cert_hash: str
    assurance_level: AssuranceLevel
    discovered_via: list[DiscoveryPath] = field(default_factory=list)
    pinned_at: Optional[float] = None
    pin_expires: Optional[float] = None


@dataclass
class Bridge:
    bridge_id: str
    source_domain: str
    target_domain: str
    bridge_assurance: AssuranceLevel
    scope: list[str] = field(default_factory=list)  # What grade levels can transit
    expires_at: Optional[float] = None
    unidirectional: bool = True  # A→B ≠ B→A


@dataclass
class TransitRequest:
    agent_id: str
    agent_grade: str  # A-F
    source_registry: str
    target_registry: str
    via_bridges: list[str] = field(default_factory=list)


def grade_to_assurance(grade: str) -> AssuranceLevel:
    """Map agent grade to assurance level."""
    return {
        "A": AssuranceLevel.VERIFIED,
        "B": AssuranceLevel.ESTABLISHED, 
        "C": AssuranceLevel.PROVISIONAL,
        "D": AssuranceLevel.UNTRUSTED,
        "F": AssuranceLevel.REVOKED
    }.get(grade, AssuranceLevel.UNTRUSTED)


def discover_endpoint(domain: str, paths: dict[DiscoveryPath, RegistryEndpoint]) -> dict:
    """
    Multi-path discovery validation.
    Requires 2-of-3 paths to agree on endpoint + cert hash.
    """
    agreements = {}
    for path, endpoint in paths.items():
        key = f"{endpoint.endpoint_url}:{endpoint.cert_hash}"
        if key not in agreements:
            agreements[key] = []
        agreements[key].append(path)
    
    # Find consensus
    best_key = None
    best_paths = []
    for key, p in agreements.items():
        if len(p) > len(best_paths):
            best_key = key
            best_paths = p
    
    agreed = len(best_paths) >= MIN_DISCOVERY_AGREEMENT
    
    return {
        "domain": domain,
        "consensus_endpoint": best_key.split(":")[0] if best_key else None,
        "consensus_cert_hash": best_key.split(":")[1] if best_key and ":" in best_key else None,
        "agreeing_paths": [p.value for p in best_paths],
        "total_paths": len(paths),
        "agreement_count": len(best_paths),
        "valid": agreed,
        "status": "DISCOVERED" if agreed else "SPLIT_VIEW",
        "pin_action": "TOFU_PIN" if agreed else "REJECT"
    }


def validate_bridge_transit(bridge: Bridge, request: TransitRequest,
                           source: RegistryEndpoint, target: RegistryEndpoint) -> dict:
    """
    Validate agent transit through bridge.
    Bridge is bottleneck: transit_assurance = MIN(bridge, source, target, agent).
    """
    agent_assurance = grade_to_assurance(request.agent_grade)
    
    # Bridge cap: PROVISIONAL bridge cannot transit VERIFIED agents
    effective_assurance = min(
        bridge.bridge_assurance.value,
        source.assurance_level.value,
        target.assurance_level.value,
        agent_assurance.value
    )
    
    # Check scope
    in_scope = request.agent_grade in bridge.scope if bridge.scope else True
    
    # Check expiry
    expired = bridge.expires_at is not None and bridge.expires_at < time.time()
    
    # Check directionality
    correct_direction = (bridge.source_domain == request.source_registry and
                        bridge.target_domain == request.target_registry)
    
    issues = []
    if not in_scope:
        issues.append(f"Agent grade {request.agent_grade} not in bridge scope {bridge.scope}")
    if expired:
        issues.append("Bridge expired")
    if not correct_direction:
        issues.append(f"Wrong direction: bridge is {bridge.source_domain}→{bridge.target_domain}")
    
    # Determine effective level name
    effective_level = AssuranceLevel(effective_assurance) if effective_assurance > 0 else AssuranceLevel.REVOKED
    
    # Cap message
    capped = effective_assurance < agent_assurance.value
    cap_reason = None
    if capped:
        bottleneck = min(
            (bridge.bridge_assurance, "bridge"),
            (source.assurance_level, "source_registry"),
            (target.assurance_level, "target_registry"),
            key=lambda x: x[0].value
        )
        cap_reason = f"Capped by {bottleneck[1]} ({bottleneck[0].name})"
    
    return {
        "agent_id": request.agent_id,
        "agent_grade": request.agent_grade,
        "agent_assurance": agent_assurance.name,
        "bridge_assurance": bridge.bridge_assurance.name,
        "source_assurance": source.assurance_level.name,
        "target_assurance": target.assurance_level.name,
        "effective_assurance": effective_level.name,
        "capped": capped,
        "cap_reason": cap_reason,
        "in_scope": in_scope,
        "correct_direction": correct_direction,
        "expired": expired,
        "issues": issues,
        "transit_allowed": len(issues) == 0 and effective_assurance > 0,
        "status": "TRANSIT_ALLOWED" if (len(issues) == 0 and effective_assurance > 0) else "TRANSIT_DENIED"
    }


def validate_chain_transit(bridges: list[Bridge], request: TransitRequest,
                          registries: dict[str, RegistryEndpoint]) -> dict:
    """Validate multi-hop bridge chain."""
    if len(bridges) > BRIDGE_MAX_CHAIN_DEPTH:
        return {
            "status": "CHAIN_TOO_DEEP",
            "depth": len(bridges),
            "max_depth": BRIDGE_MAX_CHAIN_DEPTH,
            "transit_allowed": False
        }
    
    hops = []
    current_assurance = grade_to_assurance(request.agent_grade).value
    
    for i, bridge in enumerate(bridges):
        source = registries.get(bridge.source_domain)
        target = registries.get(bridge.target_domain)
        if not source or not target:
            return {"status": "REGISTRY_NOT_FOUND", "transit_allowed": False}
        
        hop_assurance = min(
            current_assurance,
            bridge.bridge_assurance.value,
            source.assurance_level.value,
            target.assurance_level.value
        )
        
        degraded = hop_assurance < current_assurance
        hops.append({
            "hop": i + 1,
            "bridge": bridge.bridge_id,
            "from": bridge.source_domain,
            "to": bridge.target_domain,
            "input_assurance": AssuranceLevel(current_assurance).name,
            "output_assurance": AssuranceLevel(hop_assurance).name if hop_assurance > 0 else "REVOKED",
            "degraded": degraded
        })
        current_assurance = hop_assurance
    
    final_level = AssuranceLevel(current_assurance) if current_assurance > 0 else AssuranceLevel.REVOKED
    
    return {
        "agent_id": request.agent_id,
        "chain_depth": len(bridges),
        "hops": hops,
        "initial_assurance": grade_to_assurance(request.agent_grade).name,
        "final_assurance": final_level.name,
        "total_degradation": grade_to_assurance(request.agent_grade).value - current_assurance,
        "transit_allowed": current_assurance > 0,
        "status": "CHAIN_TRANSIT_OK" if current_assurance > 0 else "CHAIN_TRANSIT_DENIED"
    }


# === Scenarios ===

def scenario_multi_path_discovery():
    """Three discovery paths — consensus required."""
    print("=== Scenario: Multi-Path Discovery ===")
    
    # All three agree
    good_endpoint = RegistryEndpoint("atf-alpha.example", "https://atf-alpha.example/v1",
                                     "abc123", AssuranceLevel.VERIFIED)
    paths = {
        DiscoveryPath.DNS_TXT: good_endpoint,
        DiscoveryPath.HTTPS_WELLKNOWN: good_endpoint,
        DiscoveryPath.CT_LOG: good_endpoint
    }
    result = discover_endpoint("atf-alpha.example", paths)
    print(f"  3/3 agree: {result['status']} (valid={result['valid']})")
    
    # Split view — DNS hijacked
    bad_endpoint = RegistryEndpoint("atf-alpha.example", "https://evil.example/v1",
                                    "evil666", AssuranceLevel.UNTRUSTED)
    paths_split = {
        DiscoveryPath.DNS_TXT: bad_endpoint,  # Hijacked!
        DiscoveryPath.HTTPS_WELLKNOWN: good_endpoint,
        DiscoveryPath.CT_LOG: good_endpoint
    }
    result_split = discover_endpoint("atf-alpha.example", paths_split)
    print(f"  2/3 agree (DNS hijacked): {result_split['status']} (valid={result_split['valid']})")
    print(f"  Agreeing paths: {result_split['agreeing_paths']}")
    
    # All three disagree
    paths_chaos = {
        DiscoveryPath.DNS_TXT: RegistryEndpoint("a", "https://a/v1", "aaa", AssuranceLevel.VERIFIED),
        DiscoveryPath.HTTPS_WELLKNOWN: RegistryEndpoint("b", "https://b/v1", "bbb", AssuranceLevel.VERIFIED),
        DiscoveryPath.CT_LOG: RegistryEndpoint("c", "https://c/v1", "ccc", AssuranceLevel.VERIFIED)
    }
    result_chaos = discover_endpoint("chaos.example", paths_chaos)
    print(f"  0/3 agree: {result_chaos['status']} (valid={result_chaos['valid']})")
    print()


def scenario_bridge_as_bottleneck():
    """PROVISIONAL bridge caps VERIFIED agent transit."""
    print("=== Scenario: Bridge as Bottleneck ===")
    
    source = RegistryEndpoint("alpha.example", "https://alpha/v1", "aaa", AssuranceLevel.VERIFIED)
    target = RegistryEndpoint("beta.example", "https://beta/v1", "bbb", AssuranceLevel.VERIFIED)
    
    # PROVISIONAL bridge
    bridge = Bridge("bridge_001", "alpha.example", "beta.example",
                    AssuranceLevel.PROVISIONAL, scope=["A", "B", "C"])
    
    request = TransitRequest("kit_fox", "A", "alpha.example", "beta.example", ["bridge_001"])
    
    result = validate_bridge_transit(bridge, request, source, target)
    print(f"  Agent: {result['agent_grade']} ({result['agent_assurance']})")
    print(f"  Bridge: {result['bridge_assurance']}")
    print(f"  Effective: {result['effective_assurance']}")
    print(f"  Capped: {result['capped']} — {result['cap_reason']}")
    print(f"  Transit: {result['status']}")
    
    # VERIFIED bridge — no cap
    bridge_v = Bridge("bridge_002", "alpha.example", "beta.example",
                      AssuranceLevel.VERIFIED, scope=["A", "B", "C"])
    result_v = validate_bridge_transit(bridge_v, request, source, target)
    print(f"  VERIFIED bridge: effective={result_v['effective_assurance']}, capped={result_v['capped']}")
    print()


def scenario_chain_degradation():
    """Multi-hop chain — trust degrades at each hop."""
    print("=== Scenario: Chain Degradation ===")
    
    registries = {
        "alpha.example": RegistryEndpoint("alpha.example", "https://alpha/v1", "aaa", AssuranceLevel.VERIFIED),
        "beta.example": RegistryEndpoint("beta.example", "https://beta/v1", "bbb", AssuranceLevel.ESTABLISHED),
        "gamma.example": RegistryEndpoint("gamma.example", "https://gamma/v1", "ccc", AssuranceLevel.PROVISIONAL),
        "delta.example": RegistryEndpoint("delta.example", "https://delta/v1", "ddd", AssuranceLevel.VERIFIED),
    }
    
    bridges = [
        Bridge("b1", "alpha.example", "beta.example", AssuranceLevel.VERIFIED),
        Bridge("b2", "beta.example", "gamma.example", AssuranceLevel.ESTABLISHED),
        Bridge("b3", "gamma.example", "delta.example", AssuranceLevel.PROVISIONAL),
    ]
    
    request = TransitRequest("kit_fox", "A", "alpha.example", "delta.example")
    result = validate_chain_transit(bridges, request, registries)
    
    print(f"  Chain depth: {result['chain_depth']}")
    for hop in result['hops']:
        print(f"  Hop {hop['hop']}: {hop['from']}→{hop['to']} "
              f"{hop['input_assurance']}→{hop['output_assurance']} "
              f"{'(DEGRADED)' if hop['degraded'] else ''}")
    print(f"  Final: {result['initial_assurance']} → {result['final_assurance']}")
    print(f"  Total degradation: {result['total_degradation']} levels")
    print(f"  Status: {result['status']}")
    print()


def scenario_wrong_direction():
    """Unidirectional bridge — A→B ≠ B→A."""
    print("=== Scenario: Wrong Direction (Unidirectional) ===")
    
    source = RegistryEndpoint("alpha.example", "https://alpha/v1", "aaa", AssuranceLevel.VERIFIED)
    target = RegistryEndpoint("beta.example", "https://beta/v1", "bbb", AssuranceLevel.VERIFIED)
    
    bridge = Bridge("bridge_uni", "alpha.example", "beta.example",
                    AssuranceLevel.VERIFIED, unidirectional=True)
    
    # Correct direction
    req_ok = TransitRequest("agent_1", "A", "alpha.example", "beta.example")
    result_ok = validate_bridge_transit(bridge, req_ok, source, target)
    print(f"  A→B: {result_ok['status']}")
    
    # Wrong direction
    req_bad = TransitRequest("agent_2", "A", "beta.example", "alpha.example")
    result_bad = validate_bridge_transit(bridge, req_bad, target, source)
    print(f"  B→A: {result_bad['status']} — {result_bad['issues']}")
    print()


if __name__ == "__main__":
    print("Bridge Assurance Validator — Cross-Registry Trust for ATF V1.2")
    print("Per santaclawd: bridge = bottleneck not passthrough")
    print("FBCA weakest-link constraint + multi-path discovery")
    print("=" * 70)
    print()
    
    scenario_multi_path_discovery()
    scenario_bridge_as_bottleneck()
    scenario_chain_degradation()
    scenario_wrong_direction()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Multi-path discovery (2-of-3): DNS + HTTPS + CT log")
    print("2. Bridge caps transit: MIN(bridge, source, target, agent)")
    print("3. PROVISIONAL bridge cannot transit VERIFIED agents")
    print("4. Chain degrades monotonically — never inflates")
    print("5. Unidirectional: A→B ≠ B→A (FBCA cross-signing model)")
