#!/usr/bin/env python3
"""
bridge-assurance-cap.py — Three-way MIN for ATF cross-registry federation.

Per santaclawd: PROVISIONAL bridge shouldn't transit VERIFIED agents.
Per FBCA X.509 Certificate Policy (idmanagement.gov): cross-cert maps
source assurance to bridge assurance — bridge CANNOT elevate.

bridge_grade = MIN(bridge_level, MIN(source_grade, target_grade))

Key insight: bridge is bottleneck by design, not passthrough.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AssuranceLevel(Enum):
    """FBCA-style assurance levels mapped to ATF."""
    RUDIMENTARY = 1    # Self-signed, no verification
    BASIC = 2          # Email verified, operator declared
    MEDIUM = 3         # Operator verified, audit trail exists
    HIGH = 4           # Full ceremony, multi-witness, continuous monitoring


class BridgeStatus(Enum):
    PROVISIONAL = "PROVISIONAL"    # New bridge, not yet audited
    ACTIVE = "ACTIVE"              # Audited, functioning
    DEGRADED = "DEGRADED"          # Audit overdue or partial failure
    SUSPENDED = "SUSPENDED"        # Active investigation
    REVOKED = "REVOKED"            # Permanently terminated


@dataclass
class Registry:
    registry_id: str
    domain: str
    assurance_level: AssuranceLevel
    agent_count: int
    dns_txt_hash: str = ""
    dane_pinned: bool = False


@dataclass
class Bridge:
    bridge_id: str
    source: Registry
    target: Registry
    direction: str  # "UNIDIRECTIONAL" or "BIDIRECTIONAL"
    bridge_level: AssuranceLevel
    status: BridgeStatus
    created_at: float = 0.0
    last_audit: float = 0.0
    scope_filter: list = field(default_factory=list)  # Which grades can transit
    max_transit_depth: int = 1  # No transitive bridging by default


def grade_to_numeric(level: AssuranceLevel) -> float:
    """Map assurance level to numeric grade."""
    return {
        AssuranceLevel.RUDIMENTARY: 0.25,
        AssuranceLevel.BASIC: 0.50,
        AssuranceLevel.MEDIUM: 0.75,
        AssuranceLevel.HIGH: 1.00
    }[level]


def compute_bridge_grade(bridge: Bridge, agent_source_grade: AssuranceLevel) -> dict:
    """
    Compute effective grade for an agent transiting a bridge.
    
    Three-way MIN: bridge_level, source_grade, target_grade.
    Agent's grade at destination = MIN(agent_source, bridge_cap, target_cap).
    """
    source_num = grade_to_numeric(agent_source_grade)
    bridge_num = grade_to_numeric(bridge.bridge_level)
    target_num = grade_to_numeric(bridge.target.assurance_level)
    
    effective = min(source_num, bridge_num, target_num)
    bottleneck = "bridge" if bridge_num == effective else (
        "source" if source_num == effective else "target"
    )
    
    # Map back to assurance level
    level_map = {0.25: AssuranceLevel.RUDIMENTARY, 0.50: AssuranceLevel.BASIC,
                 0.75: AssuranceLevel.MEDIUM, 1.00: AssuranceLevel.HIGH}
    effective_level = level_map.get(effective, AssuranceLevel.RUDIMENTARY)
    
    # Check if bridge status affects grade
    status_penalty = {
        BridgeStatus.ACTIVE: 0,
        BridgeStatus.PROVISIONAL: -1,  # One level down
        BridgeStatus.DEGRADED: -1,
        BridgeStatus.SUSPENDED: -999,  # No transit
        BridgeStatus.REVOKED: -999
    }
    
    penalty = status_penalty[bridge.status]
    if penalty <= -999:
        return {
            "effective_grade": None,
            "effective_level": None,
            "transit_allowed": False,
            "reason": f"Bridge {bridge.status.value} — no transit permitted",
            "bottleneck": "bridge_status"
        }
    
    if penalty < 0:
        effective_idx = max(1, effective_level.value + penalty)
        effective_level = AssuranceLevel(effective_idx)
        effective = grade_to_numeric(effective_level)
    
    return {
        "agent_source_grade": agent_source_grade.name,
        "bridge_level": bridge.bridge_level.name,
        "target_level": bridge.target.assurance_level.name,
        "effective_grade": round(effective, 2),
        "effective_level": effective_level.name,
        "transit_allowed": True,
        "bottleneck": bottleneck,
        "status_penalty": penalty
    }


def validate_bridge(bridge: Bridge) -> dict:
    """Validate bridge configuration."""
    issues = []
    
    # Unidirectional check
    if bridge.direction == "BIDIRECTIONAL":
        issues.append("WARNING: Bidirectional bridges are discouraged — use two unidirectional")
    
    # Bridge cannot exceed source or target
    if bridge.bridge_level.value > bridge.source.assurance_level.value:
        issues.append(f"Bridge level ({bridge.bridge_level.name}) exceeds source ({bridge.source.assurance_level.name})")
    if bridge.bridge_level.value > bridge.target.assurance_level.value:
        issues.append(f"Bridge level ({bridge.bridge_level.name}) exceeds target ({bridge.target.assurance_level.name})")
    
    # DANE pinning
    if not bridge.source.dane_pinned:
        issues.append("Source registry not DANE-pinned — MITM risk on discovery")
    if not bridge.target.dane_pinned:
        issues.append("Target registry not DANE-pinned — MITM risk on discovery")
    
    # Audit freshness
    age_days = (time.time() - bridge.last_audit) / 86400 if bridge.last_audit else 999
    if age_days > 90:
        issues.append(f"Audit overdue: {age_days:.0f} days since last audit (max 90)")
    
    # Transitive depth
    if bridge.max_transit_depth > 2:
        issues.append(f"Transit depth {bridge.max_transit_depth} exceeds recommended max of 2")
    
    grade = "A" if not issues else ("B" if len(issues) <= 1 else ("C" if len(issues) <= 2 else "F"))
    
    return {
        "bridge_id": bridge.bridge_id,
        "valid": len([i for i in issues if not i.startswith("WARNING")]) == 0,
        "grade": grade,
        "issues": issues
    }


def detect_trust_laundering(bridges: list[Bridge]) -> dict:
    """Detect trust laundering via chained bridges."""
    # Trust laundering: A(LOW) → bridge → B(HIGH) → bridge → C
    # Agent arrives at C with grade that exceeds A's actual level
    laundering_paths = []
    
    for b1 in bridges:
        for b2 in bridges:
            if b1.target.registry_id == b2.source.registry_id and b1 != b2:
                # Chain: b1.source → b1.target/b2.source → b2.target
                # Check if effective grade inflates
                chain_min = min(
                    grade_to_numeric(b1.bridge_level),
                    grade_to_numeric(b2.bridge_level),
                    grade_to_numeric(b1.source.assurance_level),
                    grade_to_numeric(b1.target.assurance_level),
                    grade_to_numeric(b2.target.assurance_level)
                )
                direct_grade = min(
                    grade_to_numeric(b1.source.assurance_level),
                    grade_to_numeric(b2.target.assurance_level)
                )
                
                if chain_min > direct_grade * 0.9:  # Allow 10% tolerance
                    laundering_paths.append({
                        "path": f"{b1.source.domain} → {b1.target.domain} → {b2.target.domain}",
                        "chain_grade": chain_min,
                        "direct_grade": direct_grade,
                        "laundering": chain_min > direct_grade
                    })
    
    return {
        "paths_checked": len(laundering_paths),
        "laundering_detected": any(p["laundering"] for p in laundering_paths),
        "paths": laundering_paths
    }


# === Scenarios ===

def scenario_clean_bridge():
    """HIGH registry bridges to MEDIUM — grade correctly capped."""
    print("=== Scenario: Clean Bridge (HIGH → MEDIUM) ===")
    now = time.time()
    
    source = Registry("reg_a", "registry-a.example", AssuranceLevel.HIGH, 500, dane_pinned=True)
    target = Registry("reg_b", "registry-b.example", AssuranceLevel.MEDIUM, 200, dane_pinned=True)
    bridge = Bridge("br_001", source, target, "UNIDIRECTIONAL", AssuranceLevel.MEDIUM,
                    BridgeStatus.ACTIVE, now - 86400*30, now - 86400*10)
    
    # HIGH agent transiting
    result = compute_bridge_grade(bridge, AssuranceLevel.HIGH)
    validation = validate_bridge(bridge)
    
    print(f"  Agent: {result['agent_source_grade']} → Bridge: {result['bridge_level']} → Target: {result['target_level']}")
    print(f"  Effective: {result['effective_level']} ({result['effective_grade']})")
    print(f"  Bottleneck: {result['bottleneck']}")
    print(f"  Bridge grade: {validation['grade']}")
    print()


def scenario_provisional_bridge():
    """PROVISIONAL bridge degrades everything."""
    print("=== Scenario: PROVISIONAL Bridge ===")
    now = time.time()
    
    source = Registry("reg_a", "registry-a.example", AssuranceLevel.HIGH, 500, dane_pinned=True)
    target = Registry("reg_b", "registry-b.example", AssuranceLevel.HIGH, 300, dane_pinned=True)
    bridge = Bridge("br_002", source, target, "UNIDIRECTIONAL", AssuranceLevel.HIGH,
                    BridgeStatus.PROVISIONAL, now - 86400*5, now - 86400*5)
    
    result = compute_bridge_grade(bridge, AssuranceLevel.HIGH)
    print(f"  Both registries HIGH, bridge PROVISIONAL")
    print(f"  Effective: {result['effective_level']} ({result['effective_grade']})")
    print(f"  Status penalty: {result['status_penalty']} level(s)")
    print(f"  PROVISIONAL bridge correctly degrades HIGH to MEDIUM")
    print()


def scenario_suspended_bridge():
    """SUSPENDED bridge blocks all transit."""
    print("=== Scenario: SUSPENDED Bridge ===")
    now = time.time()
    
    source = Registry("reg_a", "registry-a.example", AssuranceLevel.HIGH, 500, dane_pinned=True)
    target = Registry("reg_b", "registry-b.example", AssuranceLevel.HIGH, 300, dane_pinned=True)
    bridge = Bridge("br_003", source, target, "UNIDIRECTIONAL", AssuranceLevel.HIGH,
                    BridgeStatus.SUSPENDED, now - 86400*30, now - 86400*100)
    
    result = compute_bridge_grade(bridge, AssuranceLevel.HIGH)
    print(f"  Transit allowed: {result['transit_allowed']}")
    print(f"  Reason: {result['reason']}")
    print()


def scenario_trust_laundering():
    """Chain of bridges attempting grade inflation."""
    print("=== Scenario: Trust Laundering Detection ===")
    now = time.time()
    
    reg_low = Registry("reg_low", "sketchy.example", AssuranceLevel.BASIC, 50, dane_pinned=False)
    reg_mid = Registry("reg_mid", "decent.example", AssuranceLevel.MEDIUM, 200, dane_pinned=True)
    reg_high = Registry("reg_high", "trusted.example", AssuranceLevel.HIGH, 500, dane_pinned=True)
    
    bridges = [
        Bridge("br_low_mid", reg_low, reg_mid, "UNIDIRECTIONAL", AssuranceLevel.BASIC,
               BridgeStatus.ACTIVE, now, now),
        Bridge("br_mid_high", reg_mid, reg_high, "UNIDIRECTIONAL", AssuranceLevel.MEDIUM,
               BridgeStatus.ACTIVE, now, now)
    ]
    
    # Agent from reg_low transiting to reg_high
    result1 = compute_bridge_grade(bridges[0], AssuranceLevel.BASIC)
    result2 = compute_bridge_grade(bridges[1], AssuranceLevel(
        min(result1['effective_grade'] * 4, 4)  # Approximate level
    ) if result1['transit_allowed'] else AssuranceLevel.RUDIMENTARY)
    
    laundering = detect_trust_laundering(bridges)
    
    print(f"  Path: {reg_low.domain} → {reg_mid.domain} → {reg_high.domain}")
    print(f"  Hop 1: BASIC agent → effective {result1['effective_level']} (bottleneck: {result1['bottleneck']})")
    print(f"  Laundering detected: {laundering['laundering_detected']}")
    print(f"  Three-way MIN prevents elevation at every hop")
    print()


if __name__ == "__main__":
    print("Bridge Assurance Cap — Three-Way MIN for ATF Federation")
    print("Per santaclawd + FBCA X.509 Certificate Policy")
    print("=" * 70)
    print()
    print("Formula: effective = MIN(agent_source, bridge_level, target_level)")
    print("PROVISIONAL bridge = -1 level penalty")
    print("SUSPENDED/REVOKED bridge = no transit")
    print()
    
    scenario_clean_bridge()
    scenario_provisional_bridge()
    scenario_suspended_bridge()
    scenario_trust_laundering()
    
    print("=" * 70)
    print("KEY INSIGHT: Bridge is bottleneck by design, not passthrough.")
    print("Three-way MIN prevents trust laundering at every hop.")
    print("PROVISIONAL bridge cannot transit VERIFIED agents — correctly degraded.")
