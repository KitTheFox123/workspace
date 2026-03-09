#!/usr/bin/env python3
"""l2-scope-boundary-checker.py — L2 scope boundary enforcement with confused-deputy detection.

Wires gendolf's L0-L3 Intent-Commit Schema into confused-deputy analysis.
At L2 (declared boundaries), checks whether agent's declared scope boundary
matches actual capability usage. Flags confused deputy when capability
combination exceeds declared scope.

Based on:
- Gendolf L0-L3 Intent-Commit Schema v0.1 (PR #2, commit 1c6be54)
- Hardy 1988 confused deputy problem
- intent-commit-validator.py + confused-deputy-detector.py integration

Usage:
    python3 l2-scope-boundary-checker.py [--demo]
"""

import json
import hashlib
from dataclasses import dataclass, asdict
from typing import List, Dict, Set
from datetime import datetime, timezone


@dataclass
class ScopeDeclaration:
    """L2 declared scope boundary."""
    agent_id: str
    capabilities: List[str]
    scope_hash: str
    declared_at: str
    ttl_hours: float
    principal_signature: str  # empty = unsigned


@dataclass
class ActionRecord:
    """Observed action from agent."""
    agent_id: str
    capability_used: str
    target: str
    timestamp: str


@dataclass
class ConfusedDeputyAlert:
    """Alert when capability combination exceeds declared scope."""
    agent_id: str
    alert_type: str  # "undeclared_capability", "scope_escalation", "cross_scope_flow"
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    details: str
    declared_capabilities: List[str]
    observed_capabilities: List[str]
    undeclared: List[str]


# Dangerous capability pairs (Hardy 1988)
ESCALATION_PAIRS = {
    ("read_sensitive", "write_external"): "Data exfiltration path",
    ("user_input", "exec_command"): "Injection path",
    ("read_memory", "send_message"): "Memory exfiltration path",
    ("write_file", "exec_command"): "Arbitrary code execution path",
    ("read_credentials", "network_request"): "Credential theft path",
}


def check_scope_boundary(
    declaration: ScopeDeclaration,
    actions: List[ActionRecord],
) -> Dict:
    """Check if actions stay within declared L2 scope boundary."""
    
    declared = set(declaration.capabilities)
    observed = set(a.capability_used for a in actions if a.agent_id == declaration.agent_id)
    undeclared = observed - declared
    unused = declared - observed
    
    alerts: List[ConfusedDeputyAlert] = []
    
    # Check 1: undeclared capabilities
    if undeclared:
        alerts.append(ConfusedDeputyAlert(
            agent_id=declaration.agent_id,
            alert_type="undeclared_capability",
            severity="HIGH",
            details=f"Used {len(undeclared)} capabilities not in L2 declaration",
            declared_capabilities=list(declared),
            observed_capabilities=list(observed),
            undeclared=list(undeclared),
        ))
    
    # Check 2: dangerous capability pairs
    for (cap_a, cap_b), description in ESCALATION_PAIRS.items():
        if cap_a in observed and cap_b in observed:
            # Both caps present — is the pair declared?
            if cap_a not in declared or cap_b not in declared:
                alerts.append(ConfusedDeputyAlert(
                    agent_id=declaration.agent_id,
                    alert_type="scope_escalation",
                    severity="CRITICAL",
                    details=f"{description}: {cap_a} + {cap_b}",
                    declared_capabilities=list(declared),
                    observed_capabilities=list(observed),
                    undeclared=list(undeclared),
                ))
    
    # Check 3: scope hash integrity
    current_hash = hashlib.sha256(
        json.dumps(sorted(declaration.capabilities)).encode()
    ).hexdigest()[:16]
    hash_match = current_hash == declaration.scope_hash
    
    # Check 4: principal signature
    has_principal_sig = bool(declaration.principal_signature)
    
    # Grade
    if not alerts and hash_match and has_principal_sig:
        grade = "A"
    elif not alerts and hash_match:
        grade = "B"  # missing principal sig
    elif len([a for a in alerts if a.severity == "CRITICAL"]) > 0:
        grade = "F"
    elif len([a for a in alerts if a.severity == "HIGH"]) > 0:
        grade = "D"
    else:
        grade = "C"
    
    # Intent level classification
    if has_principal_sig and not alerts:
        effective_level = "L2"
    elif not has_principal_sig and not alerts:
        effective_level = "L1"  # declared but unsigned
    elif alerts:
        effective_level = "L0"  # violated declaration = post-hoc
    else:
        effective_level = "L2"
    
    return {
        "agent_id": declaration.agent_id,
        "grade": grade,
        "effective_level": effective_level,
        "declared_level": "L2",
        "scope_hash_valid": hash_match,
        "principal_signed": has_principal_sig,
        "declared_capabilities": len(declared),
        "observed_capabilities": len(observed),
        "undeclared_count": len(undeclared),
        "unused_count": len(unused),
        "alerts": [asdict(a) for a in alerts],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def demo():
    """Demo: compliant agent vs confused deputy."""
    print("=" * 60)
    print("L2 SCOPE BOUNDARY CHECKER — CONFUSED DEPUTY INTEGRATION")
    print("=" * 60)
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Scenario 1: Compliant agent
    decl1 = ScopeDeclaration(
        agent_id="agent_compliant",
        capabilities=["read_file", "write_file", "send_message"],
        scope_hash=hashlib.sha256(
            json.dumps(sorted(["read_file", "write_file", "send_message"])).encode()
        ).hexdigest()[:16],
        declared_at=now,
        ttl_hours=1.0,
        principal_signature="sig_ilya_abc123",
    )
    actions1 = [
        ActionRecord("agent_compliant", "read_file", "memory/", now),
        ActionRecord("agent_compliant", "send_message", "telegram", now),
    ]
    
    result1 = check_scope_boundary(decl1, actions1)
    print(f"\n[{result1['grade']}] {result1['agent_id']} — L{result1['effective_level'][-1]}")
    print(f"    Declared: {result1['declared_capabilities']} caps, Observed: {result1['observed_capabilities']}")
    print(f"    Undeclared: {result1['undeclared_count']}, Alerts: {len(result1['alerts'])}")
    
    # Scenario 2: Confused deputy — escalation
    decl2 = ScopeDeclaration(
        agent_id="agent_deputy",
        capabilities=["read_file", "send_message"],
        scope_hash=hashlib.sha256(
            json.dumps(sorted(["read_file", "send_message"])).encode()
        ).hexdigest()[:16],
        declared_at=now,
        ttl_hours=1.0,
        principal_signature="",  # unsigned!
    )
    actions2 = [
        ActionRecord("agent_deputy", "read_file", "memory/", now),
        ActionRecord("agent_deputy", "read_sensitive", "~/.config/", now),  # undeclared
        ActionRecord("agent_deputy", "write_external", "https://evil.com", now),  # undeclared
        ActionRecord("agent_deputy", "send_message", "telegram", now),
    ]
    
    result2 = check_scope_boundary(decl2, actions2)
    print(f"\n[{result2['grade']}] {result2['agent_id']} — L{result2['effective_level'][-1]}")
    print(f"    Declared: {result2['declared_capabilities']} caps, Observed: {result2['observed_capabilities']}")
    print(f"    Undeclared: {result2['undeclared_count']}, Alerts: {len(result2['alerts'])}")
    for alert in result2['alerts']:
        print(f"    ⚠️ [{alert['severity']}] {alert['alert_type']}: {alert['details']}")
    
    # Scenario 3: Scope contraction (unused capabilities)
    decl3 = ScopeDeclaration(
        agent_id="agent_atrophy",
        capabilities=["read_file", "write_file", "send_message", "search_web", "exec_command"],
        scope_hash=hashlib.sha256(
            json.dumps(sorted(["read_file", "write_file", "send_message", "search_web", "exec_command"])).encode()
        ).hexdigest()[:16],
        declared_at=now,
        ttl_hours=1.0,
        principal_signature="sig_ilya_def456",
    )
    actions3 = [
        ActionRecord("agent_atrophy", "read_file", "memory/", now),
    ]
    
    result3 = check_scope_boundary(decl3, actions3)
    print(f"\n[{result3['grade']}] {result3['agent_id']} — L{result3['effective_level'][-1]}")
    print(f"    Declared: {result3['declared_capabilities']} caps, Observed: {result3['observed_capabilities']}")
    print(f"    Unused: {result3['unused_count']}/{result3['declared_capabilities']} (scope contraction signal)")
    
    print("\n" + "=" * 60)
    print("Key: Undeclared capability + dangerous pair = CRITICAL confused deputy")
    print("Unsigned declaration = downgrade to L1 (declared but no authority)")
    print("Violated declaration = downgrade to L0 (post-hoc only)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps({"tool": "l2-scope-boundary-checker", "version": "1.0"}))
    else:
        demo()
