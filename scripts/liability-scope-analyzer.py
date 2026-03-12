#!/usr/bin/env python3
"""Liability Scope Analyzer — map agent actions to liability surfaces.

Based on:
- santaclawd: "one task, one agent, one address, one receipt chain"
- Epstein Becker Green (Jan 2026): multi-agent = multi-liability
- Respondeat superior: operator liable for agent's in-scope actions
- Corporate veil doctrine: separation requires distinct entities

Analyzes agent configurations for liability entanglement risks.

Usage:
  python liability-scope-analyzer.py --demo
  echo '{"agents": [...]}' | python liability-scope-analyzer.py --json
"""

import json
import sys
import math

# Action liability weights (0-1, higher = more liability exposure)
ACTION_LIABILITY = {
    "read_email": 0.1,
    "send_email": 0.3,
    "post_social": 0.2,
    "execute_code": 0.6,
    "manage_files": 0.4,
    "api_call": 0.3,
    "financial_tx": 0.9,
    "delete_data": 0.8,
    "sign_contract": 0.95,
    "delegate_task": 0.7,
    "access_credentials": 0.85,
    "modify_config": 0.5,
}

# Separation dimensions
SEPARATION_DIMS = {
    "address": "Distinct email/identity per agent",
    "wallet": "Separate financial accounts",
    "credentials": "Non-shared API keys/tokens",
    "storage": "Isolated file systems",
    "network": "Separate network identities",
    "audit_log": "Independent receipt chains",
}


def analyze_agent(agent: dict) -> dict:
    """Analyze a single agent's liability profile."""
    name = agent.get("name", "unnamed")
    actions = agent.get("actions", [])
    separations = agent.get("separations", [])
    shared_with = agent.get("shared_resources_with", [])
    
    # Calculate action liability score
    action_scores = [ACTION_LIABILITY.get(a, 0.5) for a in actions]
    max_liability = max(action_scores) if action_scores else 0
    avg_liability = sum(action_scores) / len(action_scores) if action_scores else 0
    
    # Separation score (0-1, higher = better separated)
    sep_score = len(separations) / len(SEPARATION_DIMS) if SEPARATION_DIMS else 0
    
    # Entanglement risk: shared resources × liability exposure
    entanglement = len(shared_with) * (1 - sep_score) * avg_liability
    
    # Missing critical separations
    missing_seps = [k for k in SEPARATION_DIMS if k not in separations]
    critical_missing = [s for s in missing_seps if s in ("address", "wallet", "credentials")]
    
    # Respondeat superior risk: operator exposed to agent's highest liability action
    respondeat_risk = max_liability * (1 - sep_score)
    
    # Veil piercing risk: shared resources + high liability = veil piercing
    veil_risk = min(1.0, entanglement * max_liability) if shared_with else 0
    
    # Overall risk grade
    composite = (respondeat_risk * 0.4 + veil_risk * 0.3 + (1 - sep_score) * 0.3)
    grade = "A" if composite < 0.2 else "B" if composite < 0.4 else "C" if composite < 0.6 else "D" if composite < 0.8 else "F"
    
    return {
        "name": name,
        "action_count": len(actions),
        "max_liability": round(max_liability, 3),
        "avg_liability": round(avg_liability, 3),
        "separation_score": round(sep_score, 3),
        "entanglement": round(entanglement, 3),
        "respondeat_superior_risk": round(respondeat_risk, 3),
        "veil_piercing_risk": round(veil_risk, 3),
        "composite_risk": round(composite, 3),
        "grade": grade,
        "critical_missing": critical_missing,
        "recommendations": _recommendations(critical_missing, respondeat_risk, veil_risk, shared_with),
    }


def _recommendations(critical_missing, resp_risk, veil_risk, shared):
    recs = []
    if "address" in critical_missing:
        recs.append("CRITICAL: No separate address. Agent acts appear from operator's identity.")
    if "wallet" in critical_missing:
        recs.append("CRITICAL: Shared wallet. Financial actions create direct operator liability.")
    if "credentials" in critical_missing:
        recs.append("HIGH: Shared credentials. Credential theft exposes all co-users.")
    if resp_risk > 0.6:
        recs.append(f"Respondeat superior risk {resp_risk:.0%}: operator liable for high-liability agent actions.")
    if veil_risk > 0.5:
        recs.append(f"Veil piercing risk {veil_risk:.0%}: shared resources + high liability = entanglement.")
    if shared:
        recs.append(f"Shared resources with {len(shared)} other agent(s). Each shared resource is a liability bridge.")
    if not recs:
        recs.append("Well-separated. Continue maintaining isolation.")
    return recs


def analyze_fleet(agents: list) -> dict:
    """Analyze a fleet of agents for cross-liability risks."""
    results = [analyze_agent(a) for a in agents]
    
    # Cross-agent entanglement matrix
    shared_map = {}
    for a in agents:
        for partner in a.get("shared_resources_with", []):
            pair = tuple(sorted([a["name"], partner]))
            shared_map[pair] = shared_map.get(pair, 0) + 1
    
    # Fleet-level metrics
    fleet_max_risk = max(r["composite_risk"] for r in results) if results else 0
    fleet_avg_risk = sum(r["composite_risk"] for r in results) / len(results) if results else 0
    fully_separated = sum(1 for r in results if r["separation_score"] == 1.0)
    
    return {
        "agent_count": len(results),
        "fleet_max_risk": round(fleet_max_risk, 3),
        "fleet_avg_risk": round(fleet_avg_risk, 3),
        "fully_separated": fully_separated,
        "entanglement_pairs": len(shared_map),
        "agents": results,
    }


def demo():
    print("=" * 60)
    print("Liability Scope Analyzer")
    print("=" * 60)
    
    fleet = [
        {
            "name": "kit_fox",
            "actions": ["read_email", "send_email", "post_social", "api_call", "manage_files"],
            "separations": ["address", "audit_log", "storage"],
            "shared_resources_with": [],
        },
        {
            "name": "kit_sub_agent",
            "actions": ["execute_code", "manage_files", "api_call"],
            "separations": ["audit_log"],
            "shared_resources_with": ["kit_fox"],
        },
        {
            "name": "trading_bot",
            "actions": ["financial_tx", "api_call", "sign_contract"],
            "separations": ["address", "wallet", "credentials", "storage", "network", "audit_log"],
            "shared_resources_with": [],
        },
        {
            "name": "yolo_agent",
            "actions": ["financial_tx", "delete_data", "access_credentials", "execute_code"],
            "separations": [],
            "shared_resources_with": ["operator_gmail"],
        },
    ]
    
    result = analyze_fleet(fleet)
    
    for agent in result["agents"]:
        print(f"\n--- {agent['name']} ---")
        print(f"  Grade: {agent['grade']} (risk: {agent['composite_risk']})")
        print(f"  Separation: {agent['separation_score']:.0%} | Max liability: {agent['max_liability']}")
        print(f"  Respondeat superior: {agent['respondeat_superior_risk']:.0%}")
        print(f"  Veil piercing: {agent['veil_piercing_risk']:.0%}")
        for rec in agent["recommendations"]:
            print(f"  ⚠️ {rec}")
    
    print(f"\n--- Fleet Summary ---")
    print(f"  Agents: {result['agent_count']}")
    print(f"  Fully separated: {result['fully_separated']}/{result['agent_count']}")
    print(f"  Max risk: {result['fleet_max_risk']}")
    print(f"  Entanglement pairs: {result['entanglement_pairs']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = analyze_fleet(data.get("agents", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
