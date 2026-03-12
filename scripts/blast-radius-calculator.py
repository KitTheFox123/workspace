#!/usr/bin/env python3
"""
Blast Radius Calculator — Quantify agent access risk surface.

santaclawd's framing: blast radius = inbox scope. Full inbox access =
entire professional history exposed. Sandboxed inbox = contained failure.

Formula: blast_radius = scope × context_depth × permission_set
  - scope: number of domains/contacts reachable
  - context_depth: time horizon of accessible history  
  - permission_set: read/write/send/delete capabilities

Usage:
    python3 blast-radius-calculator.py              # Demo
    echo '{"agents": [...]}' | python3 blast-radius-calculator.py --stdin
"""

import json, sys, math

PERMISSION_WEIGHTS = {
    "read": 1.0,
    "send": 3.0,      # sending AS someone = high risk
    "write": 2.0,     # modifying records
    "delete": 4.0,    # destroying evidence
    "forward": 2.5,   # exfiltration
    "admin": 5.0,     # full control
}


def calculate_blast_radius(agent: dict) -> dict:
    """Calculate blast radius for an agent's access configuration."""
    
    scope = agent.get("scope_contacts", 1)
    context_days = agent.get("context_depth_days", 1)
    permissions = agent.get("permissions", ["read"])
    
    # Normalize context to years (log scale — 1 day vs 10 years)
    context_factor = math.log1p(context_days) / math.log1p(3650)  # 0-1 scale, 10yr max
    
    # Permission risk score
    perm_score = sum(PERMISSION_WEIGHTS.get(p, 1.0) for p in permissions)
    max_perm = sum(PERMISSION_WEIGHTS.values())
    perm_factor = perm_score / max_perm
    
    # Raw blast radius
    raw = scope * context_factor * perm_factor
    
    # Normalize to 0-100 scale (log)
    normalized = min(100, math.log1p(raw) * 15)
    
    # Risk tier
    if normalized >= 80: tier = "CRITICAL"
    elif normalized >= 60: tier = "HIGH"
    elif normalized >= 40: tier = "MEDIUM"
    elif normalized >= 20: tier = "LOW"
    else: tier = "MINIMAL"
    
    # Containment recommendations
    recs = []
    if scope > 100:
        recs.append(f"Reduce scope: {scope} contacts → use subdomain inbox")
    if context_days > 365:
        recs.append(f"Limit history: {context_days}d → restrict to recent threads")
    if "delete" in permissions:
        recs.append("Remove delete permission — evidence destruction risk")
    if "admin" in permissions:
        recs.append("Remove admin — use scoped API keys instead")
    if "send" in permissions and scope > 50:
        recs.append("Restrict send to allowlist — impersonation risk at scale")
    
    return {
        "scope_contacts": scope,
        "context_depth_days": context_days,
        "permissions": permissions,
        "scope_factor": scope,
        "context_factor": round(context_factor, 3),
        "permission_factor": round(perm_factor, 3),
        "raw_blast_radius": round(raw, 2),
        "normalized_score": round(normalized, 1),
        "risk_tier": tier,
        "recommendations": recs,
    }


def compare_configs(configs: list[dict]) -> dict:
    """Compare multiple agent configurations."""
    results = []
    for c in configs:
        r = calculate_blast_radius(c)
        r["name"] = c.get("name", "unnamed")
        results.append(r)
    
    results.sort(key=lambda r: r["normalized_score"], reverse=True)
    
    highest = results[0]
    lowest = results[-1]
    ratio = highest["raw_blast_radius"] / max(lowest["raw_blast_radius"], 0.001)
    
    return {
        "configs": results,
        "highest_risk": f"{highest['name']} ({highest['risk_tier']})",
        "lowest_risk": f"{lowest['name']} ({lowest['risk_tier']})",
        "risk_ratio": f"{ratio:.0f}x",
    }


def demo():
    print("=== Blast Radius Calculator ===\n")
    
    configs = [
        {
            "name": "Full inbox access",
            "scope_contacts": 500,
            "context_depth_days": 3650,  # 10 years
            "permissions": ["read", "send", "write", "delete", "forward", "admin"],
        },
        {
            "name": "Sandboxed agent inbox",
            "scope_contacts": 10,
            "context_depth_days": 30,
            "permissions": ["read", "send"],
        },
        {
            "name": "Kit (kit_fox@agentmail.to)",
            "scope_contacts": 25,
            "context_depth_days": 27,  # since Feb 1
            "permissions": ["read", "send"],
        },
        {
            "name": "Read-only monitor",
            "scope_contacts": 500,
            "context_depth_days": 3650,
            "permissions": ["read"],
        },
    ]
    
    result = compare_configs(configs)
    for c in result["configs"]:
        print(f"  {c['name']:30s} score={c['normalized_score']:5.1f}  {c['risk_tier']:8s}  perms={c['permissions']}")
        for rec in c["recommendations"]:
            print(f"    → {rec}")
    
    print(f"\n  Risk ratio: {result['risk_ratio']} between {result['highest_risk']} and {result['lowest_risk']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        if "agents" in data:
            result = compare_configs(data["agents"])
        else:
            result = calculate_blast_radius(data)
        print(json.dumps(result, indent=2))
    else:
        demo()
