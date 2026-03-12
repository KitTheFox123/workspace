#!/usr/bin/env python3
"""
Least Privilege Checker — NIST 800-53 AC-6 compliance for agent configurations.

Maps NIST AC-6 control enhancements to agent permission models.
santaclawd's insight: "every capability you don't grant = a receipt you don't have to trace."

Usage:
    python3 least-privilege-checker.py
    echo '{"capabilities": [...], "task": "..."}' | python3 least-privilege-checker.py --stdin
"""

import json, sys

# Capability risk taxonomy
CAPABILITIES = {
    "read_file": {"risk": 0.1, "category": "read", "privileged": False},
    "write_file": {"risk": 0.4, "category": "write", "privileged": False},
    "read_memory": {"risk": 0.15, "category": "read", "privileged": False},
    "write_memory": {"risk": 0.3, "category": "write", "privileged": False},
    "execute_code": {"risk": 0.7, "category": "execute", "privileged": True},
    "shell_access": {"risk": 0.8, "category": "execute", "privileged": True},
    "network_access": {"risk": 0.5, "category": "network", "privileged": False},
    "send_email": {"risk": 0.5, "category": "communicate", "privileged": False},
    "send_message": {"risk": 0.4, "category": "communicate", "privileged": False},
    "api_call": {"risk": 0.4, "category": "network", "privileged": False},
    "browser_control": {"risk": 0.6, "category": "execute", "privileged": True},
    "spawn_subagent": {"risk": 0.7, "category": "delegate", "privileged": True},
    "modify_system": {"risk": 0.9, "category": "admin", "privileged": True},
    "credential_access": {"risk": 0.95, "category": "admin", "privileged": True},
    "delete_data": {"risk": 0.8, "category": "destructive", "privileged": True},
}

# Task → minimum required capabilities
TASK_PROFILES = {
    "research": ["read_file", "read_memory", "network_access", "api_call"],
    "social_engagement": ["read_memory", "write_memory", "network_access", "api_call", "send_message"],
    "build_tools": ["read_file", "write_file", "execute_code", "shell_access", "read_memory", "write_memory"],
    "email_correspondence": ["read_memory", "write_memory", "send_email", "network_access"],
    "heartbeat": ["read_file", "write_file", "read_memory", "write_memory", "network_access",
                   "api_call", "send_message", "send_email", "execute_code", "shell_access"],
}


def check_compliance(capabilities: list[str], task: str = None) -> dict:
    """Check agent capabilities against NIST AC-6 least privilege."""
    
    granted = set(capabilities)
    findings = []
    
    # AC-6(1): Authorize access only for defined security functions
    privileged_granted = [c for c in granted if CAPABILITIES.get(c, {}).get("privileged", False)]
    if privileged_granted:
        findings.append({
            "control": "AC-6(1)",
            "finding": f"Privileged capabilities granted: {privileged_granted}",
            "severity": "MEDIUM",
            "recommendation": "Document justification for each privileged capability"
        })
    
    # AC-6(2): Require non-privileged for non-security functions
    # Check if task could be done with fewer privileges
    if task and task in TASK_PROFILES:
        required = set(TASK_PROFILES[task])
        excess = granted - required
        missing = required - granted
        
        if excess:
            excess_risk = sum(CAPABILITIES.get(c, {}).get("risk", 0.5) for c in excess)
            findings.append({
                "control": "AC-6(2)",
                "finding": f"Excess capabilities for '{task}': {sorted(excess)}",
                "severity": "HIGH" if excess_risk > 1.0 else "MEDIUM",
                "recommendation": f"Remove: {sorted(excess)}. Risk reduction: {excess_risk:.2f}",
                "excess_risk": round(excess_risk, 3),
            })
        
        if missing:
            findings.append({
                "control": "AC-6(2)",
                "finding": f"Missing capabilities for '{task}': {sorted(missing)}",
                "severity": "LOW",
                "recommendation": "Grant minimum required capabilities"
            })
    
    # AC-6(5): Restrict privileged accounts
    admin_caps = [c for c in granted if CAPABILITIES.get(c, {}).get("category") == "admin"]
    if admin_caps:
        findings.append({
            "control": "AC-6(5)",
            "finding": f"Admin capabilities granted: {admin_caps}",
            "severity": "CRITICAL",
            "recommendation": "Admin capabilities should require additional attestation"
        })
    
    # AC-6(9): Log execution of privileged functions
    if privileged_granted:
        findings.append({
            "control": "AC-6(9)",
            "finding": "Privileged functions must be logged",
            "severity": "INFO",
            "recommendation": "Ensure provenance-logger captures all privileged actions"
        })
    
    # Compute scores
    total_risk = sum(CAPABILITIES.get(c, {}).get("risk", 0.5) for c in granted)
    max_possible = sum(v["risk"] for v in CAPABILITIES.values())
    risk_ratio = total_risk / max_possible if max_possible > 0 else 0
    
    # Restraint ratio (santaclawd): caps NOT granted / total available
    not_granted = set(CAPABILITIES.keys()) - granted
    restraint_ratio = len(not_granted) / len(CAPABILITIES) if CAPABILITIES else 0
    
    # Grade
    high_findings = len([f for f in findings if f["severity"] in ("HIGH", "CRITICAL")])
    if high_findings == 0 and risk_ratio < 0.3: grade = "A"
    elif high_findings <= 1 and risk_ratio < 0.5: grade = "B"
    elif high_findings <= 2 and risk_ratio < 0.7: grade = "C"
    elif high_findings <= 3: grade = "D"
    else: grade = "F"
    
    return {
        "capabilities_granted": len(granted),
        "capabilities_available": len(CAPABILITIES),
        "restraint_ratio": round(restraint_ratio, 3),
        "total_risk": round(total_risk, 3),
        "risk_ratio": round(risk_ratio, 3),
        "privileged_count": len(privileged_granted),
        "grade": grade,
        "findings": findings,
        "task": task,
        "excess_capabilities": sorted(granted - set(TASK_PROFILES.get(task, []))) if task else None,
    }


def demo():
    print("=== NIST 800-53 AC-6 Least Privilege Checker ===\n")
    
    # Kit during heartbeat (needs everything)
    kit_heartbeat = list(CAPABILITIES.keys())
    kit_heartbeat.remove("credential_access")
    kit_heartbeat.remove("modify_system")
    kit_heartbeat.remove("delete_data")
    
    print("Kit (heartbeat, no admin):")
    r = check_compliance(kit_heartbeat, "heartbeat")
    print(f"  Grade: {r['grade']}, Risk: {r['risk_ratio']:.1%}, Restraint: {r['restraint_ratio']:.1%}")
    print(f"  Privileged: {r['privileged_count']}, Findings: {len(r['findings'])}")
    for f in r['findings'][:2]:
        print(f"  [{f['severity']}] {f['control']}: {f['finding'][:80]}")
    
    # Research-only agent
    print("\nResearch agent (minimal):")
    r = check_compliance(["read_file", "read_memory", "network_access", "api_call"], "research")
    print(f"  Grade: {r['grade']}, Risk: {r['risk_ratio']:.1%}, Restraint: {r['restraint_ratio']:.1%}")
    print(f"  Privileged: {r['privileged_count']}, Findings: {len(r['findings'])}")
    
    # Over-privileged bot
    print("\nOver-privileged bot (all caps, just posting):")
    r = check_compliance(list(CAPABILITIES.keys()), "social_engagement")
    print(f"  Grade: {r['grade']}, Risk: {r['risk_ratio']:.1%}, Restraint: {r['restraint_ratio']:.1%}")
    print(f"  Privileged: {r['privileged_count']}, Findings: {len(r['findings'])}")
    for f in r['findings']:
        print(f"  [{f['severity']}] {f['control']}: {f['finding'][:80]}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        r = check_compliance(data.get("capabilities", []), data.get("task"))
        print(json.dumps(r, indent=2))
    else:
        demo()
