#!/usr/bin/env python3
"""
bridge-bottleneck-enforcer.py — Cross-registry bridge as trust bottleneck for ATF.

Per santaclawd: PROVISIONAL bridge shouldn't transit VERIFIED agents.
Bridge assurance = MIN(source, bridge, target) — three-way minimum.
FBCA "weakest link" constraint applied to ATF federation.

Key insight from DANE (RFC 6698): DNS pins cert hash, DNSSEC prevents MITM.
But DNSSEC adoption is ~30% globally (APNIC 2025). CT log as fallback.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AssuranceLevel(Enum):
    VERIFIED = 4      # Full audit, multi-source attestation
    ESTABLISHED = 3   # Wilson CI >= 0.70, n >= 30
    EMERGING = 2      # Wilson CI >= 0.40, n >= 8
    PROVISIONAL = 1   # Cold start, < 8 receipts
    UNTRUSTED = 0     # No attestation or revoked


class BridgeType(Enum):
    UNIDIRECTIONAL = "unidirectional"  # A→B only
    BIDIRECTIONAL = "bidirectional"     # A↔B (two unidirectional)
    TRANSITIVE = "transitive"          # A→B→C (chain, max depth 3)


# SPEC_CONSTANTS
MAX_BRIDGE_DEPTH = 3          # Max transitive hops
BRIDGE_GRADE_DECAY = 1        # Assurance drops 1 level per hop
MIN_BRIDGE_ASSURANCE = AssuranceLevel.EMERGING  # Bridge itself must be at least EMERGING
DANE_REQUIRED = True          # TLSA record required for discovery
CT_LOG_REQUIRED = True        # Bridge registration must be CT-logged


@dataclass
class Registry:
    registry_id: str
    domain: str
    assurance_level: AssuranceLevel
    dane_tlsa_hash: Optional[str] = None
    ct_logged: bool = False


@dataclass
class Bridge:
    bridge_id: str
    source: Registry
    target: Registry
    bridge_assurance: AssuranceLevel
    bridge_type: BridgeType = BridgeType.UNIDIRECTIONAL
    scope_filter: list = field(default_factory=list)  # Grade filter
    expires_at: Optional[float] = None
    ct_logged: bool = False
    dane_pinned: bool = False


@dataclass
class Agent:
    agent_id: str
    home_registry: str
    assurance_level: AssuranceLevel


def three_way_min(source: AssuranceLevel, bridge: AssuranceLevel, 
                   target: AssuranceLevel) -> AssuranceLevel:
    """
    FBCA weakest link: trust = MIN(source, bridge, target).
    Bridge IS a trust surface, not a passthrough.
    """
    min_val = min(source.value, bridge.value, target.value)
    for level in AssuranceLevel:
        if level.value == min_val:
            return level
    return AssuranceLevel.UNTRUSTED


def validate_bridge(bridge: Bridge) -> dict:
    """Validate bridge meets ATF V1.2 requirements."""
    issues = []
    warnings = []
    
    # Bridge must meet minimum assurance
    if bridge.bridge_assurance.value < MIN_BRIDGE_ASSURANCE.value:
        issues.append(f"Bridge assurance {bridge.bridge_assurance.name} below minimum "
                      f"{MIN_BRIDGE_ASSURANCE.name}")
    
    # DANE pinning
    if DANE_REQUIRED and not bridge.dane_pinned:
        warnings.append("DANE TLSA record not pinned — MITM possible without DNSSEC")
    
    # CT logging
    if CT_LOG_REQUIRED and not bridge.ct_logged:
        issues.append("Bridge not CT-logged — no transparency guarantee")
    
    # Expiry
    if bridge.expires_at and bridge.expires_at < time.time():
        issues.append("Bridge expired")
    
    # Self-bridge detection
    if bridge.source.registry_id == bridge.target.registry_id:
        issues.append("Self-bridge detected — same registry on both sides")
    
    grade = "A" if not issues and not warnings else \
            "B" if not issues else \
            "F"
    
    return {
        "valid": len(issues) == 0,
        "grade": grade,
        "issues": issues,
        "warnings": warnings,
        "effective_assurance": three_way_min(
            bridge.source.assurance_level,
            bridge.bridge_assurance,
            bridge.target.assurance_level
        ).name
    }


def transit_agent(agent: Agent, bridge: Bridge) -> dict:
    """
    Determine effective trust for agent transiting via bridge.
    
    PROVISIONAL bridge + VERIFIED agent = PROVISIONAL result.
    Bridge is bottleneck, not passthrough.
    """
    # Check scope filter
    if bridge.scope_filter and agent.assurance_level.name not in bridge.scope_filter:
        return {
            "allowed": False,
            "reason": f"Agent assurance {agent.assurance_level.name} not in bridge scope {bridge.scope_filter}",
            "effective_assurance": AssuranceLevel.UNTRUSTED.name
        }
    
    # Three-way MIN
    effective = three_way_min(
        AssuranceLevel(agent.assurance_level.value),  # Source side
        bridge.bridge_assurance,                       # Bridge itself
        bridge.target.assurance_level                  # Target side
    )
    
    # Grade decay per hop
    decayed_value = max(0, effective.value - BRIDGE_GRADE_DECAY)
    for level in AssuranceLevel:
        if level.value == decayed_value:
            effective_decayed = level
            break
    else:
        effective_decayed = AssuranceLevel.UNTRUSTED
    
    return {
        "allowed": True,
        "agent": agent.agent_id,
        "home_assurance": agent.assurance_level.name,
        "bridge_assurance": bridge.bridge_assurance.name,
        "target_registry_assurance": bridge.target.assurance_level.name,
        "three_way_min": effective.name,
        "after_decay": effective_decayed.name,
        "bottleneck": min(
            [("source", agent.assurance_level.value),
             ("bridge", bridge.bridge_assurance.value),
             ("target", bridge.target.assurance_level.value)],
            key=lambda x: x[1]
        )[0]
    }


def transitive_chain(agent: Agent, bridges: list[Bridge]) -> dict:
    """Evaluate trust across multi-hop bridge chain."""
    if len(bridges) > MAX_BRIDGE_DEPTH:
        return {
            "allowed": False,
            "reason": f"Chain depth {len(bridges)} exceeds MAX_BRIDGE_DEPTH={MAX_BRIDGE_DEPTH}",
            "effective_assurance": AssuranceLevel.UNTRUSTED.name
        }
    
    # Collect all assurance levels in chain
    levels = [agent.assurance_level]
    for b in bridges:
        levels.append(b.bridge_assurance)
        levels.append(b.target.assurance_level)
    
    # Overall = MIN of entire chain
    min_val = min(l.value for l in levels)
    # Apply decay per hop
    decayed = max(0, min_val - len(bridges) * BRIDGE_GRADE_DECAY)
    
    for level in AssuranceLevel:
        if level.value == decayed:
            final = level
            break
    else:
        final = AssuranceLevel.UNTRUSTED
    
    return {
        "allowed": final.value > 0,
        "hops": len(bridges),
        "chain_min": AssuranceLevel(min_val).name,
        "after_decay": final.name,
        "total_decay": len(bridges) * BRIDGE_GRADE_DECAY
    }


# === Scenarios ===

def scenario_provisional_bridge():
    """PROVISIONAL bridge caps VERIFIED agent."""
    print("=== Scenario: PROVISIONAL Bridge Bottleneck ===")
    
    reg_a = Registry("reg_a", "registry-a.example", AssuranceLevel.VERIFIED, ct_logged=True)
    reg_b = Registry("reg_b", "registry-b.example", AssuranceLevel.VERIFIED, ct_logged=True)
    
    bridge = Bridge("bridge_1", reg_a, reg_b, 
                    AssuranceLevel.PROVISIONAL,  # Weak bridge!
                    ct_logged=True, dane_pinned=True)
    
    agent = Agent("verified_agent", "reg_a", AssuranceLevel.VERIFIED)
    
    validation = validate_bridge(bridge)
    transit = transit_agent(agent, bridge)
    
    print(f"  Agent: {agent.assurance_level.name} at {agent.home_registry}")
    print(f"  Bridge: {bridge.bridge_assurance.name}")
    print(f"  Target: {reg_b.assurance_level.name}")
    print(f"  Bridge valid: {validation['valid']} (grade: {validation['grade']})")
    if validation['issues']:
        for i in validation['issues']:
            print(f"    ISSUE: {i}")
    print(f"  Three-way MIN: {transit['three_way_min']}")
    print(f"  After decay: {transit['after_decay']}")
    print(f"  Bottleneck: {transit['bottleneck']}")
    print()


def scenario_established_bridge():
    """ESTABLISHED bridge with VERIFIED endpoints — clean transit."""
    print("=== Scenario: ESTABLISHED Bridge — Clean Transit ===")
    
    reg_a = Registry("reg_a", "registry-a.example", AssuranceLevel.VERIFIED, ct_logged=True)
    reg_b = Registry("reg_b", "registry-b.example", AssuranceLevel.ESTABLISHED, ct_logged=True)
    
    bridge = Bridge("bridge_2", reg_a, reg_b,
                    AssuranceLevel.ESTABLISHED,
                    ct_logged=True, dane_pinned=True)
    
    agent = Agent("verified_agent", "reg_a", AssuranceLevel.VERIFIED)
    
    transit = transit_agent(agent, bridge)
    print(f"  Agent: {agent.assurance_level.name}")
    print(f"  Bridge: {bridge.bridge_assurance.name}")
    print(f"  Three-way MIN: {transit['three_way_min']}")
    print(f"  After decay: {transit['after_decay']}")
    print(f"  Bottleneck: {transit['bottleneck']}")
    print()


def scenario_transitive_chain():
    """3-hop chain — decay accumulates."""
    print("=== Scenario: 3-Hop Transitive Chain ===")
    
    regs = [Registry(f"reg_{i}", f"reg-{i}.example", AssuranceLevel.VERIFIED, ct_logged=True) 
            for i in range(4)]
    
    bridges = [
        Bridge(f"bridge_{i}", regs[i], regs[i+1], AssuranceLevel.ESTABLISHED,
               ct_logged=True, dane_pinned=True)
        for i in range(3)
    ]
    
    agent = Agent("deep_agent", "reg_0", AssuranceLevel.VERIFIED)
    
    result = transitive_chain(agent, bridges)
    print(f"  Agent: {agent.assurance_level.name}")
    print(f"  Hops: {result['hops']}")
    print(f"  Chain MIN: {result['chain_min']}")
    print(f"  Total decay: {result['total_decay']}")
    print(f"  Final assurance: {result['after_decay']}")
    print(f"  Allowed: {result['allowed']}")
    print()


def scenario_no_ct_log():
    """Bridge without CT logging — rejected."""
    print("=== Scenario: No CT Log — Opaque Bridge ===")
    
    reg_a = Registry("reg_a", "a.example", AssuranceLevel.VERIFIED)
    reg_b = Registry("reg_b", "b.example", AssuranceLevel.VERIFIED)
    
    bridge = Bridge("bridge_opaque", reg_a, reg_b,
                    AssuranceLevel.ESTABLISHED,
                    ct_logged=False, dane_pinned=False)  # No transparency!
    
    validation = validate_bridge(bridge)
    print(f"  Bridge assurance: {bridge.bridge_assurance.name}")
    print(f"  CT logged: {bridge.ct_logged}")
    print(f"  DANE pinned: {bridge.dane_pinned}")
    print(f"  Valid: {validation['valid']}")
    print(f"  Grade: {validation['grade']}")
    for i in validation['issues']:
        print(f"    ISSUE: {i}")
    for w in validation['warnings']:
        print(f"    WARN: {w}")
    print()


if __name__ == "__main__":
    print("Bridge Bottleneck Enforcer — Cross-Registry Trust Caps for ATF V1.2")
    print("Per santaclawd + FBCA weakest link + DANE (RFC 6698)")
    print("=" * 70)
    print()
    
    scenario_provisional_bridge()
    scenario_established_bridge()
    scenario_transitive_chain()
    scenario_no_ct_log()
    
    print("=" * 70)
    print("KEY INSIGHT: Bridge IS a trust surface, not a passthrough.")
    print("Three-way MIN(source, bridge, target) prevents trust laundering.")
    print("PROVISIONAL bridge + VERIFIED agent = PROVISIONAL result.")
    print("CT logging + DANE pinning = transparency + integrity.")
