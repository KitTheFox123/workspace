#!/usr/bin/env python3
"""
Capability Scope Auditor — Saltzer & Schroeder (1975) least privilege for agents.

"Every program and every privileged user of the system should operate using
the least amount of privilege necessary to complete the job."

Audits agent capability grants against actual usage. Unused capabilities =
unnecessary attack surface. Over-scoped agents = unauditable blast radius.

Usage:
    python3 capability-scope-auditor.py              # Demo
    echo '{"granted": [...], "used": [...]}' | python3 capability-scope-auditor.py --stdin
"""

import json, sys, math
from collections import Counter

# Capability risk taxonomy
CAPABILITIES = {
    # Low risk (read-only, no side effects)
    "read_file": {"risk": 0.1, "category": "read"},
    "search_web": {"risk": 0.1, "category": "read"},
    "read_memory": {"risk": 0.05, "category": "read"},
    "list_directory": {"risk": 0.05, "category": "read"},
    
    # Medium risk (write, reversible)
    "write_file": {"risk": 0.4, "category": "write"},
    "write_memory": {"risk": 0.3, "category": "write"},
    "send_message": {"risk": 0.5, "category": "communicate"},
    "post_social": {"risk": 0.4, "category": "communicate"},
    
    # High risk (external effects, hard to reverse)
    "send_email": {"risk": 0.6, "category": "communicate"},
    "execute_code": {"risk": 0.7, "category": "execute"},
    "install_package": {"risk": 0.6, "category": "execute"},
    "modify_config": {"risk": 0.7, "category": "system"},
    "spawn_agent": {"risk": 0.65, "category": "delegate"},
    
    # Critical (irreversible, high consequence)
    "delete_file": {"risk": 0.8, "category": "destructive"},
    "sign_transaction": {"risk": 0.95, "category": "financial"},
    "manage_credentials": {"risk": 0.9, "category": "security"},
    "modify_system_prompt": {"risk": 0.95, "category": "identity"},
}


def audit_scope(granted: list[str], used: list[str], session_actions: int = 0) -> dict:
    """Audit capability scope against actual usage."""
    
    granted_set = set(granted)
    used_set = set(used)
    
    # Unused capabilities = attack surface
    unused = granted_set - used_set
    # Used but not granted = scope violation
    violations = used_set - granted_set
    # Properly scoped
    properly_used = granted_set & used_set
    
    # Risk scores
    unused_risk = sum(CAPABILITIES.get(c, {"risk": 0.5})["risk"] for c in unused)
    violation_risk = sum(CAPABILITIES.get(c, {"risk": 0.5})["risk"] * 2.0 for c in violations)  # 2x for unauthorized
    granted_risk = sum(CAPABILITIES.get(c, {"risk": 0.5})["risk"] for c in granted)
    
    # Utilization ratio
    if len(granted) > 0:
        utilization = len(properly_used) / len(granted)
    else:
        utilization = 1.0 if len(used) == 0 else 0.0
    
    # Saltzer score: lower unused risk + no violations = better
    if granted_risk > 0:
        saltzer_score = 1.0 - (unused_risk / granted_risk) * 0.5 - min(1.0, violation_risk) * 0.5
    else:
        saltzer_score = 1.0 if not violations else 0.0
    saltzer_score = max(0, min(1, saltzer_score))
    
    # Category analysis
    granted_cats = Counter(CAPABILITIES.get(c, {"category": "unknown"})["category"] for c in granted)
    used_cats = Counter(CAPABILITIES.get(c, {"category": "unknown"})["category"] for c in used)
    
    # Grade
    if violations:
        grade = "F"
    elif saltzer_score >= 0.8:
        grade = "A"
    elif saltzer_score >= 0.6:
        grade = "B"
    elif saltzer_score >= 0.4:
        grade = "C"
    else:
        grade = "D"
    
    # Recommendations
    recs = []
    for cap in sorted(unused, key=lambda c: CAPABILITIES.get(c, {"risk": 0.5})["risk"], reverse=True):
        info = CAPABILITIES.get(cap, {"risk": 0.5, "category": "unknown"})
        if info["risk"] >= 0.5:
            recs.append(f"REVOKE {cap} (risk={info['risk']}, unused, category={info['category']})")
        elif info["risk"] >= 0.3:
            recs.append(f"REVIEW {cap} (risk={info['risk']}, unused)")
    
    for cap in sorted(violations, key=lambda c: CAPABILITIES.get(c, {"risk": 0.5})["risk"], reverse=True):
        info = CAPABILITIES.get(cap, {"risk": 0.5, "category": "unknown"})
        recs.append(f"VIOLATION {cap} (risk={info['risk']}, used without grant!)")
    
    return {
        "saltzer_score": round(saltzer_score, 3),
        "grade": grade,
        "utilization": round(utilization, 3),
        "granted_count": len(granted),
        "used_count": len(used),
        "unused_count": len(unused),
        "violation_count": len(violations),
        "unused_risk_total": round(unused_risk, 3),
        "violation_risk_total": round(violation_risk, 3),
        "granted_categories": dict(granted_cats),
        "used_categories": dict(used_cats),
        "unused_capabilities": sorted(unused),
        "violations": sorted(violations),
        "recommendations": recs[:10],
        "diagnosis": _diagnose(utilization, len(violations), unused_risk, granted_risk),
    }


def _diagnose(util, violations, unused_risk, granted_risk):
    if violations > 0:
        return f"SCOPE VIOLATION: {violations} unauthorized capabilities used. Immediate audit required."
    if util > 0.8 and unused_risk < 0.5:
        return "Well-scoped. Saltzer & Schroeder compliant. Minimal unnecessary attack surface."
    if util > 0.5:
        return "Moderately scoped. Some unused capabilities could be revoked."
    if granted_risk > 3.0:
        return "Over-provisioned with high-risk capabilities. Significant blast radius."
    return "Under-utilized grants. Review scope — either reduce grants or agent isn't doing its job."


def demo():
    print("=== Capability Scope Auditor (Saltzer & Schroeder 1975) ===\n")
    
    # Kit's actual capabilities
    kit_granted = ["read_file", "write_file", "search_web", "read_memory", "write_memory",
                   "send_message", "send_email", "post_social", "execute_code", 
                   "install_package", "spawn_agent", "list_directory"]
    kit_used = ["read_file", "write_file", "search_web", "read_memory", "write_memory",
                "send_message", "send_email", "post_social", "execute_code", "list_directory"]
    
    print("Kit (heartbeat session):")
    result = audit_scope(kit_granted, kit_used)
    print(f"  Saltzer score: {result['saltzer_score']} ({result['grade']})")
    print(f"  Utilization: {result['utilization']} ({result['used_count']}/{result['granted_count']})")
    print(f"  Unused: {result['unused_capabilities']}")
    print(f"  Diagnosis: {result['diagnosis']}")
    
    # Over-provisioned bot
    bot_granted = ["read_file", "write_file", "execute_code", "delete_file", 
                   "sign_transaction", "manage_credentials", "modify_system_prompt",
                   "send_email", "spawn_agent", "modify_config"]
    bot_used = ["read_file", "send_email"]
    
    print("\nOver-provisioned bot:")
    result = audit_scope(bot_granted, bot_used)
    print(f"  Saltzer score: {result['saltzer_score']} ({result['grade']})")
    print(f"  Utilization: {result['utilization']} ({result['used_count']}/{result['granted_count']})")
    print(f"  Unused risk: {result['unused_risk_total']}")
    print(f"  Recommendations: {result['recommendations'][:3]}")
    print(f"  Diagnosis: {result['diagnosis']}")
    
    # Scope violator
    viol_granted = ["read_file", "search_web"]
    viol_used = ["read_file", "search_web", "execute_code", "send_email"]
    
    print("\nScope violator:")
    result = audit_scope(viol_granted, viol_used)
    print(f"  Saltzer score: {result['saltzer_score']} ({result['grade']})")
    print(f"  Violations: {result['violations']}")
    print(f"  Diagnosis: {result['diagnosis']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = audit_scope(data.get("granted", []), data.get("used", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
