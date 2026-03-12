#!/usr/bin/env python3
"""
Least Privilege Scorer — Score agent permission sets for minimal capability.

Based on MiniScope (Zhu et al., Berkeley/IBM 2025, arxiv 2512.11147):
- Derive permission hierarchies from tool capabilities
- Find minimal set needed for task via ILP-style optimization
- Score overprivilege risk

Usage:
    python3 least-privilege-scorer.py              # Demo
    echo '{"granted": [...], "used": [...]}' | python3 least-privilege-scorer.py --stdin
"""

import json, sys
from itertools import combinations

# Permission hierarchy (inspired by OAuth scopes)
PERMISSIONS = {
    # Read permissions (low risk)
    "read_files": {"risk": 0.1, "covers": ["list_files", "get_file_content"]},
    "read_email": {"risk": 0.15, "covers": ["list_messages", "get_message", "search_messages"]},
    "read_calendar": {"risk": 0.1, "covers": ["list_events", "get_event"]},
    
    # Write permissions (medium risk)
    "write_files": {"risk": 0.4, "covers": ["create_file", "update_file", "delete_file"]},
    "write_email": {"risk": 0.5, "covers": ["send_email", "reply_email", "forward_email"]},
    "write_calendar": {"risk": 0.3, "covers": ["create_event", "update_event", "delete_event"]},
    
    # Execute permissions (high risk)
    "execute_code": {"risk": 0.8, "covers": ["run_script", "install_package", "exec_command"]},
    "manage_credentials": {"risk": 0.95, "covers": ["create_key", "revoke_key", "rotate_key"]},
    "spawn_agent": {"risk": 0.7, "covers": ["create_subagent", "delegate_task"]},
    
    # Network permissions (medium-high risk)
    "network_access": {"risk": 0.6, "covers": ["http_request", "api_call", "webhook"]},
    "sign_attestation": {"risk": 0.5, "covers": ["sign_receipt", "attest_delivery", "endorse"]},
}


def find_minimal_permissions(needed_tools: list[str]) -> list[str]:
    """Find minimal permission set that covers all needed tools."""
    needed = set(needed_tools)
    minimal = []
    
    # Greedy set cover (approximation of ILP)
    remaining = set(needed)
    while remaining:
        best_perm = None
        best_coverage = 0
        best_risk = float('inf')
        
        for perm, info in PERMISSIONS.items():
            coverage = len(remaining & set(info["covers"]))
            if coverage > best_coverage or (coverage == best_coverage and info["risk"] < best_risk):
                best_perm = perm
                best_coverage = coverage
                best_risk = info["risk"]
        
        if best_perm and best_coverage > 0:
            minimal.append(best_perm)
            remaining -= set(PERMISSIONS[best_perm]["covers"])
        else:
            break  # uncoverable tools
    
    return minimal


def score_privilege(granted: list[str], used_tools: list[str]) -> dict:
    """Score how well-scoped the granted permissions are."""
    
    # What permissions are actually needed?
    minimal = find_minimal_permissions(used_tools)
    
    # Calculate overprivilege
    granted_set = set(granted)
    minimal_set = set(minimal)
    excess = granted_set - minimal_set
    missing = minimal_set - granted_set
    
    # Risk scores
    granted_risk = sum(PERMISSIONS.get(p, {}).get("risk", 0.5) for p in granted)
    minimal_risk = sum(PERMISSIONS.get(p, {}).get("risk", 0.5) for p in minimal)
    
    # Overprivilege ratio
    if granted_risk > 0:
        efficiency = minimal_risk / granted_risk
    else:
        efficiency = 1.0 if not minimal else 0.0
    
    # Blast radius: what COULD the excess permissions do?
    excess_tools = set()
    for p in excess:
        if p in PERMISSIONS:
            excess_tools.update(PERMISSIONS[p]["covers"])
    
    blast_radius = len(excess_tools)
    
    # Grade
    if efficiency >= 0.9 and not excess: grade = "A"
    elif efficiency >= 0.7: grade = "B"
    elif efficiency >= 0.5: grade = "C"
    elif efficiency >= 0.3: grade = "D"
    else: grade = "F"
    
    return {
        "granted_permissions": sorted(granted),
        "minimal_permissions": sorted(minimal),
        "excess_permissions": sorted(excess),
        "missing_permissions": sorted(missing),
        "granted_risk": round(granted_risk, 3),
        "minimal_risk": round(minimal_risk, 3),
        "efficiency": round(efficiency, 3),
        "blast_radius": blast_radius,
        "excess_tool_count": blast_radius,
        "grade": grade,
        "diagnosis": _diagnose(efficiency, excess, missing, blast_radius),
    }


def _diagnose(efficiency, excess, missing, blast_radius):
    parts = []
    if not excess and not missing:
        parts.append("Perfectly scoped. Minimal privilege achieved.")
    elif excess:
        parts.append(f"Overprivileged: {len(excess)} unnecessary permission(s).")
        if blast_radius > 5:
            parts.append(f"Blast radius: {blast_radius} excess tool capabilities.")
    if missing:
        parts.append(f"Underprivileged: {len(missing)} needed permission(s) missing.")
    if efficiency < 0.5:
        parts.append("MiniScope (2025): LLM-based policy only 70-83% optimal. Use mechanical enforcement.")
    return " ".join(parts)


def demo():
    print("=== Least Privilege Scorer (MiniScope-inspired) ===\n")
    
    # Well-scoped agent
    print("Well-scoped email reader:")
    r = score_privilege(
        granted=["read_email"],
        used_tools=["list_messages", "get_message"]
    )
    print(f"  Efficiency: {r['efficiency']} ({r['grade']})")
    print(f"  Excess: {r['excess_permissions']}")
    print(f"  Diagnosis: {r['diagnosis']}\n")
    
    # Overprivileged agent
    print("Overprivileged bot (granted everything, only reads email):")
    r = score_privilege(
        granted=["read_email", "write_email", "read_files", "write_files", 
                 "execute_code", "network_access", "manage_credentials"],
        used_tools=["list_messages", "get_message"]
    )
    print(f"  Efficiency: {r['efficiency']} ({r['grade']})")
    print(f"  Blast radius: {r['blast_radius']} excess tools")
    print(f"  Excess: {r['excess_permissions']}")
    print(f"  Diagnosis: {r['diagnosis']}\n")
    
    # Kit's actual profile
    print("Kit (heartbeat session):")
    r = score_privilege(
        granted=["read_files", "write_files", "read_email", "write_email",
                 "network_access", "sign_attestation", "execute_code"],
        used_tools=["get_file_content", "create_file", "update_file",
                    "list_messages", "send_email", "http_request",
                    "api_call", "run_script", "sign_receipt"]
    )
    print(f"  Efficiency: {r['efficiency']} ({r['grade']})")
    print(f"  Excess: {r['excess_permissions']}")
    print(f"  Blast radius: {r['blast_radius']} excess tools")
    print(f"  Diagnosis: {r['diagnosis']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = score_privilege(data.get("granted", []), data.get("used", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
