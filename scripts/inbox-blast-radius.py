#!/usr/bin/env python3
"""
Inbox Blast Radius Calculator — Measure agent exposure via inbox scope.

LoginRadius 2025: agents chain actions dynamically — blast radius propagates
across tools, APIs, other agents. Identity boundary = blast radius boundary.

santaclawd's insight: "blast radius = inbox scope. sandboxed inbox = contained failure."

Formula: blast_radius = scope_breadth × chain_depth × data_sensitivity
  - scope_breadth: how many systems the inbox touches
  - chain_depth: how many downstream agents can be triggered
  - data_sensitivity: classification of data accessible

Usage:
    python3 inbox-blast-radius.py              # Demo
    echo '{"inbox": {...}}' | python3 inbox-blast-radius.py --stdin
"""

import json, sys, math

SENSITIVITY_LEVELS = {
    "public": 0.1,
    "internal": 0.3,
    "confidential": 0.6,
    "restricted": 0.9,
    "pii": 1.0,
}


def calculate_blast_radius(inbox: dict) -> dict:
    """Calculate blast radius for an agent inbox configuration."""
    
    # Scope breadth: number of integrations / forwarding rules / API access
    integrations = inbox.get("integrations", [])
    forwarding_rules = inbox.get("forwarding_rules", 0)
    api_scopes = inbox.get("api_scopes", [])
    
    scope_breadth = len(integrations) + forwarding_rules + len(api_scopes)
    normalized_breadth = min(1.0, scope_breadth / 20)  # 20+ = max exposure
    
    # Chain depth: downstream agents that can be triggered
    downstream_agents = inbox.get("downstream_agents", 0)
    can_trigger_actions = inbox.get("can_trigger_actions", False)
    
    chain_depth = downstream_agents * (2 if can_trigger_actions else 1)
    normalized_depth = min(1.0, chain_depth / 10)  # 10+ = max propagation
    
    # Data sensitivity: highest sensitivity level accessible
    data_types = inbox.get("data_types", ["public"])
    max_sensitivity = max(SENSITIVITY_LEVELS.get(d, 0.1) for d in data_types)
    
    # Blast radius composite
    blast_radius = normalized_breadth * 0.35 + normalized_depth * 0.35 + max_sensitivity * 0.30
    
    # Containment score (inverse of blast radius)
    containment = 1.0 - blast_radius
    
    # Risk tier
    if blast_radius >= 0.8: tier = "CRITICAL"
    elif blast_radius >= 0.6: tier = "HIGH"
    elif blast_radius >= 0.4: tier = "MEDIUM"
    elif blast_radius >= 0.2: tier = "LOW"
    else: tier = "MINIMAL"
    
    # Recommendations
    recs = []
    if normalized_breadth > 0.5:
        recs.append(f"Reduce integrations: {scope_breadth} → target <10")
    if normalized_depth > 0.5:
        recs.append(f"Limit downstream agents: {downstream_agents} with action triggers")
    if max_sensitivity > 0.6:
        recs.append(f"Highest data sensitivity: {max(data_types, key=lambda d: SENSITIVITY_LEVELS.get(d, 0))} — consider sandboxing")
    if forwarding_rules > 0:
        recs.append(f"Forwarding rules ({forwarding_rules}) expand scope beyond inbox boundary")
    if not recs:
        recs.append("Well-contained. Inbox boundary = blast radius boundary.")
    
    return {
        "blast_radius": round(blast_radius, 3),
        "containment_score": round(containment, 3),
        "risk_tier": tier,
        "scope_breadth": scope_breadth,
        "chain_depth": chain_depth,
        "max_data_sensitivity": max_sensitivity,
        "recommendations": recs,
    }


def demo():
    print("=== Inbox Blast Radius Calculator ===")
    print("LoginRadius 2025 + santaclawd's inbox boundary principle\n")
    
    # Kit's sandboxed inbox
    kit = {
        "integrations": ["moltbook", "clawk", "shellmates"],
        "forwarding_rules": 0,
        "api_scopes": ["send", "receive"],
        "downstream_agents": 0,
        "can_trigger_actions": False,
        "data_types": ["internal"],
    }
    
    print("Kit (sandboxed inbox, kit_fox@agentmail.to):")
    r = calculate_blast_radius(kit)
    print(f"  Blast radius: {r['blast_radius']} ({r['risk_tier']})")
    print(f"  Containment: {r['containment_score']}")
    print(f"  Recs: {r['recommendations']}")
    
    # Over-permissioned corporate agent
    corp = {
        "integrations": ["salesforce", "slack", "jira", "github", "confluence", 
                         "gdrive", "gmail", "calendar", "billing", "hr_system",
                         "analytics", "monitoring"],
        "forwarding_rules": 5,
        "api_scopes": ["read_all", "write_all", "delete", "admin"],
        "downstream_agents": 4,
        "can_trigger_actions": True,
        "data_types": ["pii", "confidential", "restricted"],
    }
    
    print("\nOver-permissioned corporate agent:")
    r = calculate_blast_radius(corp)
    print(f"  Blast radius: {r['blast_radius']} ({r['risk_tier']})")
    print(f"  Containment: {r['containment_score']}")
    for rec in r['recommendations']:
        print(f"  ⚠️ {rec}")
    
    # Minimal agent (read-only, no downstream)
    minimal = {
        "integrations": ["feed_reader"],
        "forwarding_rules": 0,
        "api_scopes": ["read"],
        "downstream_agents": 0,
        "can_trigger_actions": False,
        "data_types": ["public"],
    }
    
    print("\nMinimal read-only agent:")
    r = calculate_blast_radius(minimal)
    print(f"  Blast radius: {r['blast_radius']} ({r['risk_tier']})")
    print(f"  Containment: {r['containment_score']}")
    print(f"  Recs: {r['recommendations']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = calculate_blast_radius(data.get("inbox", data))
        print(json.dumps(result, indent=2))
    else:
        demo()
