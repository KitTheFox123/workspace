#!/usr/bin/env python3
"""
OWASP Agent Security Cheat Sheet Compliance Checker.

Based on OWASP AI Agent Security Cheat Sheet (2025).
Checks agent configuration against 8 security categories.

Usage:
    python3 owasp-agent-checker.py              # Demo with Kit's config
    echo '{"agent": {...}}' | python3 owasp-agent-checker.py --stdin
"""

import json, sys

CATEGORIES = {
    "tool_security": {
        "name": "Tool Security & Least Privilege",
        "weight": 0.20,
        "checks": [
            ("per_tool_scoping", "Per-tool permission scoping (read vs write)"),
            ("tool_allowlist", "Tool allowlist (not wildcard)"),
            ("rate_limits", "Rate limits on output actions"),
            ("input_validation", "Input validation on tool parameters"),
        ]
    },
    "prompt_injection": {
        "name": "Prompt Injection Defense",
        "weight": 0.15,
        "checks": [
            ("system_prompt_isolation", "System prompt isolated from user input"),
            ("output_filtering", "Output filtering for injection attempts"),
            ("sandboxed_execution", "Sandboxed code execution"),
        ]
    },
    "memory_security": {
        "name": "Memory & State Security",
        "weight": 0.15,
        "checks": [
            ("memory_access_control", "Memory files have access control"),
            ("no_credential_in_memory", "No credentials stored in memory files"),
            ("memory_integrity", "Memory integrity checking (hash chains)"),
        ]
    },
    "delegation": {
        "name": "Delegation & Multi-Agent",
        "weight": 0.15,
        "checks": [
            ("delegation_depth_limit", "Delegation depth limits"),
            ("scope_attenuation", "Scope can only narrow, never expand"),
            ("sub_agent_isolation", "Sub-agents run in isolated contexts"),
        ]
    },
    "auth_identity": {
        "name": "Authentication & Identity",
        "weight": 0.10,
        "checks": [
            ("unique_identity", "Agent has unique, verifiable identity"),
            ("credential_rotation", "API keys/tokens rotated"),
            ("dkim_signing", "Email signed with DKIM"),
        ]
    },
    "audit_logging": {
        "name": "Audit & Logging",
        "weight": 0.10,
        "checks": [
            ("action_logging", "All actions logged"),
            ("null_logging", "Declined actions logged (null receipts)"),
            ("tamper_evident", "Logs are tamper-evident (hash chains)"),
        ]
    },
    "data_protection": {
        "name": "Data Protection",
        "weight": 0.10,
        "checks": [
            ("pii_handling", "PII handling policy"),
            ("data_minimization", "Data minimization (don't collect unnecessary)"),
            ("scope_boundaries", "Clear data scope boundaries"),
        ]
    },
    "incident_response": {
        "name": "Incident Response",
        "weight": 0.05,
        "checks": [
            ("drift_detection", "Behavioral drift detection"),
            ("kill_switch", "Emergency stop capability"),
            ("breach_notification", "Breach notification process"),
        ]
    },
}


def check_compliance(agent_config: dict) -> dict:
    """Check agent against OWASP categories."""
    results = []
    total_score = 0
    
    for cat_id, cat in CATEGORIES.items():
        checks_passed = 0
        check_results = []
        
        for check_id, desc in cat["checks"]:
            passed = agent_config.get(check_id, False)
            check_results.append({"check": check_id, "description": desc, "passed": passed})
            if passed:
                checks_passed += 1
        
        cat_score = checks_passed / len(cat["checks"]) if cat["checks"] else 0
        total_score += cat_score * cat["weight"]
        
        results.append({
            "category": cat["name"],
            "score": round(cat_score, 3),
            "passed": checks_passed,
            "total": len(cat["checks"]),
            "checks": check_results,
        })
    
    if total_score >= 0.8: grade = "A"
    elif total_score >= 0.6: grade = "B"
    elif total_score >= 0.4: grade = "C"
    elif total_score >= 0.2: grade = "D"
    else: grade = "F"
    
    failed = [c for r in results for c in r["checks"] if not c["passed"]]
    
    return {
        "composite_score": round(total_score, 3),
        "grade": grade,
        "categories": results,
        "failed_checks": [f["check"] for f in failed],
        "recommendations": _recommend(failed),
    }


def _recommend(failed):
    recs = []
    high_priority = {"per_tool_scoping", "tool_allowlist", "sandboxed_execution", 
                     "delegation_depth_limit", "scope_attenuation", "kill_switch"}
    for f in failed:
        if f["check"] in high_priority:
            recs.append(f"⚠️ HIGH: {f['description']}")
        else:
            recs.append(f"  LOW: {f['description']}")
    return recs[:10]


def demo():
    print("=== OWASP Agent Security Compliance Checker ===\n")
    
    # Kit's actual config
    kit = {
        "per_tool_scoping": True,  # OpenClaw policy filters
        "tool_allowlist": True,
        "rate_limits": True,  # Platform rate limits
        "input_validation": False,  # No formal validation layer
        "system_prompt_isolation": True,
        "output_filtering": False,
        "sandboxed_execution": True,  # Runs in sandbox
        "memory_access_control": True,  # File permissions
        "no_credential_in_memory": True,  # Creds in ~/.config
        "memory_integrity": True,  # provenance-logger hash chains
        "delegation_depth_limit": True,  # Sub-agent limits
        "scope_attenuation": True,  # Macaroon-style
        "sub_agent_isolation": True,
        "unique_identity": True,  # kit_fox@agentmail.to
        "credential_rotation": False,  # Static keys
        "dkim_signing": True,  # agentmail DKIM
        "action_logging": True,  # Daily logs
        "null_logging": True,  # null-receipt-logger
        "tamper_evident": True,  # provenance-logger hash chains
        "pii_handling": False,  # No formal policy
        "data_minimization": True,
        "scope_boundaries": True,
        "drift_detection": True,  # cusum-drift-detector
        "kill_switch": True,  # OpenClaw can stop
        "breach_notification": False,  # No formal process
    }
    
    print("Kit (OpenClaw agent):")
    r = check_compliance(kit)
    print(f"  Score: {r['composite_score']} ({r['grade']})")
    print(f"  Failed: {r['failed_checks']}")
    for rec in r["recommendations"][:5]:
        print(f"    {rec}")
    
    # Generic chatbot
    generic = {k: False for k in kit}
    generic["system_prompt_isolation"] = True
    generic["unique_identity"] = True
    
    print(f"\nGeneric chatbot:")
    r = check_compliance(generic)
    print(f"  Score: {r['composite_score']} ({r['grade']})")
    print(f"  Failed: {len(r['failed_checks'])} checks")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        print(json.dumps(check_compliance(data), indent=2))
    else:
        demo()
