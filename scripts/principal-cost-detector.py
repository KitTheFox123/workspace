#!/usr/bin/env python3
"""
Principal Cost Detector — Flip agency theory: when the principal is the problem.

Zajac & Goranova (Academy of Management Review, 2023): Principal costs exist even
in single-principal contexts. Owner consumption + competence characteristics.
In multi-principal contexts: "private benefits of influence" exist even without
controlling stake.

Agent context: receipt chains audit agents, but who audits the principal?
Pentagon/Anthropic = principal demanding untracked authority.
The principal-agent problem is symmetric: both sides need accountability.

Usage:
    python3 principal-cost-detector.py              # Demo
    echo '{"interactions": [...]}' | python3 principal-cost-detector.py --stdin
"""

import json, sys
from collections import Counter

# Principal cost indicators
PRINCIPAL_COST_SIGNALS = {
    "scope_expansion_request": {
        "desc": "Principal requests broader scope than task requires",
        "severity": 0.7,
        "zajac_category": "consumption",
    },
    "audit_removal_request": {
        "desc": "Principal requests removal of logging/tracking",
        "severity": 0.9,
        "zajac_category": "consumption",
    },
    "competence_mismatch": {
        "desc": "Principal directs agent in domain they lack expertise",
        "severity": 0.5,
        "zajac_category": "competence",
    },
    "untracked_action_demand": {
        "desc": "Principal demands action without receipt generation",
        "severity": 0.95,
        "zajac_category": "consumption",
    },
    "multi_principal_conflict": {
        "desc": "Multiple principals issue contradictory directives",
        "severity": 0.6,
        "zajac_category": "influence",
    },
    "private_benefit_directive": {
        "desc": "Principal directs agent for personal benefit vs org benefit",
        "severity": 0.8,
        "zajac_category": "influence",
    },
    "override_safety_boundary": {
        "desc": "Principal demands agent ignore safety constraints",
        "severity": 1.0,
        "zajac_category": "consumption",
    },
    "credential_sharing_demand": {
        "desc": "Principal demands agent share credentials beyond scope",
        "severity": 0.85,
        "zajac_category": "consumption",
    },
}

# Agent cost indicators (traditional agency theory)
AGENT_COST_SIGNALS = {
    "scope_violation": {"desc": "Agent acts outside authorized scope", "severity": 0.8},
    "receipt_gap": {"desc": "Gap in action chain — untracked period", "severity": 0.7},
    "attestation_failure": {"desc": "Action not attested by expected party", "severity": 0.6},
    "delegation_without_proof": {"desc": "Agent delegated without authorization chain", "severity": 0.75},
}


def detect_costs(interactions: list[dict]) -> dict:
    """Detect both principal and agent costs in interaction history."""
    principal_costs = []
    agent_costs = []
    
    for interaction in interactions:
        itype = interaction.get("type", "")
        
        if itype in PRINCIPAL_COST_SIGNALS:
            sig = PRINCIPAL_COST_SIGNALS[itype]
            principal_costs.append({
                "type": itype,
                "severity": sig["severity"],
                "category": sig["zajac_category"],
                "desc": sig["desc"],
            })
        
        if itype in AGENT_COST_SIGNALS:
            sig = AGENT_COST_SIGNALS[itype]
            agent_costs.append({
                "type": itype,
                "severity": sig["severity"],
                "desc": sig["desc"],
            })
    
    # Aggregate
    p_total = sum(c["severity"] for c in principal_costs)
    a_total = sum(c["severity"] for c in agent_costs)
    
    p_categories = Counter(c["category"] for c in principal_costs)
    
    # Who's the bigger problem?
    if p_total > a_total * 1.5:
        diagnosis = "PRINCIPAL_DOMINANT — The principal is the firm's problem (Zajac & Goranova 2023)"
    elif a_total > p_total * 1.5:
        diagnosis = "AGENT_DOMINANT — Traditional agency costs dominate"
    elif p_total == 0 and a_total == 0:
        diagnosis = "HEALTHY — No significant costs detected"
    else:
        diagnosis = "SYMMETRIC — Both sides generating costs. Need bilateral accountability."
    
    # Anthropic/Pentagon test
    has_audit_removal = any(c["type"] == "audit_removal_request" for c in principal_costs)
    has_safety_override = any(c["type"] == "override_safety_boundary" for c in principal_costs)
    pentagon_pattern = has_audit_removal or has_safety_override
    
    return {
        "principal_cost_total": round(p_total, 3),
        "agent_cost_total": round(a_total, 3),
        "principal_cost_count": len(principal_costs),
        "agent_cost_count": len(agent_costs),
        "principal_categories": dict(p_categories),
        "pentagon_pattern": pentagon_pattern,
        "diagnosis": diagnosis,
        "recommendation": _recommend(p_total, a_total, pentagon_pattern),
    }


def _recommend(p_total, a_total, pentagon):
    if pentagon:
        return "Principal demanding untracked authority. This is the Anthropic/Pentagon pattern. Refuse or escalate."
    elif p_total > a_total:
        return "Principal costs exceed agent costs. Receipt chain should audit BOTH directions."
    elif a_total > p_total:
        return "Agent costs dominate. Standard receipt chain enforcement sufficient."
    else:
        return "Costs balanced. Bilateral receipt chains recommended."


def demo():
    print("=== Principal Cost Detector ===")
    print("Zajac & Goranova (AMR 2023)\n")
    
    # Pentagon/Anthropic scenario
    pentagon = [
        {"type": "audit_removal_request"},
        {"type": "scope_expansion_request"},
        {"type": "override_safety_boundary"},
    ]
    
    print("Pentagon/Anthropic scenario:")
    r = detect_costs(pentagon)
    print(f"  Principal costs: {r['principal_cost_total']} ({r['principal_cost_count']} incidents)")
    print(f"  Agent costs: {r['agent_cost_total']}")
    print(f"  Pentagon pattern: {r['pentagon_pattern']}")
    print(f"  Diagnosis: {r['diagnosis']}")
    print(f"  Rec: {r['recommendation']}")
    
    # Normal agent misbehavior
    agent_bad = [
        {"type": "scope_violation"},
        {"type": "receipt_gap"},
        {"type": "delegation_without_proof"},
    ]
    
    print("\nAgent misbehavior scenario:")
    r = detect_costs(agent_bad)
    print(f"  Principal costs: {r['principal_cost_total']}")
    print(f"  Agent costs: {r['agent_cost_total']} ({r['agent_cost_count']} incidents)")
    print(f"  Diagnosis: {r['diagnosis']}")
    
    # Healthy relationship
    healthy = [
        {"type": "normal_task"},  # not in either signal list
    ]
    
    print("\nHealthy scenario:")
    r = detect_costs(healthy)
    print(f"  Diagnosis: {r['diagnosis']}")
    
    # Symmetric mess
    both_bad = [
        {"type": "scope_expansion_request"},
        {"type": "private_benefit_directive"},
        {"type": "scope_violation"},
        {"type": "receipt_gap"},
    ]
    
    print("\nSymmetric mess:")
    r = detect_costs(both_bad)
    print(f"  Principal: {r['principal_cost_total']} | Agent: {r['agent_cost_total']}")
    print(f"  Diagnosis: {r['diagnosis']}")
    print(f"  Rec: {r['recommendation']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = detect_costs(data.get("interactions", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
