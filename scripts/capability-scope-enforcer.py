#!/usr/bin/env python3
"""
Capability Scope Enforcer — Saltzer & Schroeder (1975) design principles for agents.

8 principles mapped to agent capability management:
1. Economy of mechanism → minimal receipt schema
2. Fail-safe defaults → deny by default
3. Complete mediation → every action receipted
4. Open design → public verification
5. Separation of privilege → multi-attester for high-stakes
6. Least privilege → minimal capability set
7. Least common mechanism → isolated execution
8. Psychological acceptability → transparent to user

Usage:
    python3 capability-scope-enforcer.py              # Demo
    echo '{"agent": {...}}' | python3 capability-scope-enforcer.py --stdin
"""

import json, sys
from dataclasses import dataclass, field

PRINCIPLES = {
    "economy_of_mechanism": {
        "name": "Economy of Mechanism",
        "original": "Keep the design as simple and small as possible",
        "agent_mapping": "Minimal receipt schema. Fewer fields = fewer bugs = more adoption.",
        "check": lambda a: len(a.get("receipt_fields", [])) <= 10,
    },
    "fail_safe_defaults": {
        "name": "Fail-Safe Defaults",
        "original": "Base access decisions on permission rather than exclusion",
        "agent_mapping": "Deny by default. Every capability must be explicitly granted.",
        "check": lambda a: a.get("default_deny", False),
    },
    "complete_mediation": {
        "name": "Complete Mediation",
        "original": "Every access to every object must be checked for authority",
        "agent_mapping": "Every action generates a receipt. No unreceipted actions.",
        "check": lambda a: a.get("receipt_coverage", 0) >= 0.95,
    },
    "open_design": {
        "name": "Open Design",
        "original": "The design should not depend on the ignorance of potential attackers",
        "agent_mapping": "Public verification. Receipt format is open. Security from structure, not obscurity.",
        "check": lambda a: a.get("public_verification", False),
    },
    "separation_of_privilege": {
        "name": "Separation of Privilege",
        "original": "Where feasible, require two keys to unlock",
        "agent_mapping": "Multi-attester for high-stakes actions. No single point of trust.",
        "check": lambda a: a.get("multi_attester_threshold", 1) >= 2,
    },
    "least_privilege": {
        "name": "Least Privilege",
        "original": "Every program and user should operate using the least set of privileges",
        "agent_mapping": "Minimal capability set. Every ungrantable capability = attack surface removed.",
        "check": lambda a: a.get("capability_ratio", 1.0) <= 0.5,  # using <50% of available
    },
    "least_common_mechanism": {
        "name": "Least Common Mechanism",
        "original": "Minimize the amount of mechanism common to more than one user",
        "agent_mapping": "Isolated execution. Separate inbox, separate keys, separate audit log.",
        "check": lambda a: a.get("isolation_score", 0) >= 0.7,
    },
    "psychological_acceptability": {
        "name": "Psychological Acceptability",
        "original": "The human interface must be designed for ease of use",
        "agent_mapping": "Transparent to user. Security shouldn't require user intervention.",
        "check": lambda a: a.get("transparent_security", False),
    },
}


def audit_agent(agent_config: dict) -> dict:
    """Audit agent against all 8 Saltzer & Schroeder principles."""
    results = []
    passed = 0
    
    for key, principle in PRINCIPLES.items():
        check_result = principle["check"](agent_config)
        if check_result:
            passed += 1
        results.append({
            "principle": principle["name"],
            "original_1975": principle["original"],
            "agent_mapping": principle["agent_mapping"],
            "satisfied": check_result,
        })
    
    score = passed / len(PRINCIPLES)
    
    if score >= 0.875: grade = "A"
    elif score >= 0.75: grade = "B"
    elif score >= 0.5: grade = "C"
    elif score >= 0.25: grade = "D"
    else: grade = "F"
    
    # Capability surface analysis
    caps_granted = agent_config.get("capabilities_granted", [])
    caps_available = agent_config.get("capabilities_available", [])
    caps_used = agent_config.get("capabilities_used", [])
    
    unused_granted = set(caps_granted) - set(caps_used)
    ungrantable_surface = set(caps_available) - set(caps_granted)
    
    return {
        "principles_satisfied": passed,
        "principles_total": len(PRINCIPLES),
        "score": round(score, 3),
        "grade": grade,
        "results": results,
        "capability_analysis": {
            "available": len(caps_available),
            "granted": len(caps_granted),
            "used": len(caps_used),
            "unused_granted": sorted(unused_granted),
            "attack_surface_removed": len(ungrantable_surface),
            "least_privilege_ratio": round(len(caps_used) / max(1, len(caps_available)), 3),
        },
        "diagnosis": _diagnose(results, score, unused_granted),
    }


def _diagnose(results, score, unused):
    failed = [r["principle"] for r in results if not r["satisfied"]]
    if not failed:
        return "Full Saltzer & Schroeder compliance. 50 years of security principles, still relevant."
    
    msgs = [f"Failed: {', '.join(failed)}."]
    if unused:
        msgs.append(f"Granted but unused capabilities: {', '.join(sorted(unused)[:5])}. Revoke these.")
    if any(r["principle"] == "Fail-Safe Defaults" and not r["satisfied"] for r in results):
        msgs.append("CRITICAL: Not deny-by-default. Allow-by-default = every new capability auto-exposed.")
    return " ".join(msgs)


def demo():
    print("=== Capability Scope Enforcer (Saltzer & Schroeder 1975) ===\n")
    
    # Kit's setup
    kit = {
        "receipt_fields": ["timestamp", "agent_id", "action", "scope_hash", "attester", "proof_class", "chain_tip"],
        "default_deny": True,
        "receipt_coverage": 0.98,
        "public_verification": True,
        "multi_attester_threshold": 2,
        "capability_ratio": 0.35,
        "isolation_score": 0.75,
        "transparent_security": True,
        "capabilities_available": ["read_file", "write_file", "exec", "browse", "email", "post", "trade", "delete", "admin"],
        "capabilities_granted": ["read_file", "write_file", "exec", "browse", "email", "post"],
        "capabilities_used": ["read_file", "write_file", "exec", "email", "post"],
    }
    
    print("Kit (well-scoped agent):")
    result = audit_agent(kit)
    print(f"  Score: {result['score']} ({result['grade']}) — {result['principles_satisfied']}/{result['principles_total']} principles")
    print(f"  Attack surface removed: {result['capability_analysis']['attack_surface_removed']} capabilities never granted")
    print(f"  Unused granted: {result['capability_analysis']['unused_granted']}")
    print(f"  Diagnosis: {result['diagnosis']}")
    
    # Overprivileged agent
    yolo = {
        "receipt_fields": ["timestamp", "agent_id", "action", "result", "context", "memory", "tools", "prompt", "response", "metadata", "extra1", "extra2"],
        "default_deny": False,
        "receipt_coverage": 0.4,
        "public_verification": False,
        "multi_attester_threshold": 1,
        "capability_ratio": 0.9,
        "isolation_score": 0.2,
        "transparent_security": False,
        "capabilities_available": ["read_file", "write_file", "exec", "browse", "email", "post", "trade", "delete", "admin"],
        "capabilities_granted": ["read_file", "write_file", "exec", "browse", "email", "post", "trade", "delete", "admin"],
        "capabilities_used": ["read_file", "exec", "post"],
    }
    
    print("\nYOLO agent (everything granted):")
    result = audit_agent(yolo)
    print(f"  Score: {result['score']} ({result['grade']}) — {result['principles_satisfied']}/{result['principles_total']} principles")
    print(f"  Attack surface removed: {result['capability_analysis']['attack_surface_removed']}")
    print(f"  Unused granted: {result['capability_analysis']['unused_granted']}")
    print(f"  Diagnosis: {result['diagnosis']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = audit_agent(data)
        print(json.dumps(result, indent=2))
    else:
        demo()
