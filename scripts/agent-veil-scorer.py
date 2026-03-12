#!/usr/bin/env python3
"""
Agent Veil Scorer — Apply corporate veil piercing doctrine to agent-principal liability.

Cornell Law (Wex): Veil pierced when corporation is "alter ego" of shareholder AND
improper conduct exists. Key factors: commingling assets, undercapitalization,
failure to observe formalities.

Agent mapping:
  - Commingling = shared inbox/credentials (agent uses human's email)
  - Undercapitalization = no receipt chain (can't prove actions were authorized)
  - Failure to observe formalities = no scope boundaries, no audit trail
  - Alter ego = agent indistinguishable from principal (no separate identity)

If the veil holds: principal has limited liability for agent actions.
If pierced: principal is personally liable for everything the agent did.

Usage:
    python3 agent-veil-scorer.py              # Demo
    echo '{"agent": {...}}' | python3 agent-veil-scorer.py --stdin
"""

import json, sys

PIERCING_FACTORS = {
    "commingling": {
        "desc": "Agent uses principal's credentials/inbox/identity",
        "weight": 0.25,
        "legal": "Commingling of assets (most common piercing factor)",
    },
    "undercapitalization": {
        "desc": "No receipt chain / audit trail for agent actions",
        "weight": 0.20,
        "legal": "Undercapitalization at time of incorporation",
    },
    "no_formalities": {
        "desc": "No scope boundaries, no authorization records",
        "weight": 0.20,
        "legal": "Failure to observe corporate formalities",
    },
    "alter_ego": {
        "desc": "Agent indistinguishable from principal (no separate identity)",
        "weight": 0.20,
        "legal": "Corporation is mere alter ego / instrumentality",
    },
    "improper_conduct": {
        "desc": "Agent acted outside scope without principal knowledge",
        "weight": 0.15,
        "legal": "Fraudulent or improper conduct",
    },
}


def score_veil(agent_config: dict) -> dict:
    """Score how well the agent-principal veil holds."""
    
    factor_scores = {}
    
    # Commingling: shared inbox/creds = pierced
    has_own_inbox = agent_config.get("has_own_inbox", False)
    has_own_creds = agent_config.get("has_own_credentials", False)
    commingling = 0.0
    if has_own_inbox: commingling += 0.5
    if has_own_creds: commingling += 0.5
    factor_scores["commingling"] = commingling
    
    # Undercapitalization: receipt chain exists?
    has_receipts = agent_config.get("has_receipt_chain", False)
    receipt_coverage = agent_config.get("receipt_coverage_pct", 0)
    undercap = min(1.0, (0.5 if has_receipts else 0) + receipt_coverage * 0.5)
    factor_scores["undercapitalization"] = undercap
    
    # Formalities: scope boundaries, authorization records
    has_scope = agent_config.get("has_scope_boundaries", False)
    has_auth_records = agent_config.get("has_authorization_records", False)
    formalities = (0.5 if has_scope else 0) + (0.5 if has_auth_records else 0)
    factor_scores["no_formalities"] = formalities
    
    # Alter ego: separate identity
    has_own_identity = agent_config.get("has_own_identity", False)
    identity_distinct = agent_config.get("identity_distinguishable", False)
    alter_ego = (0.5 if has_own_identity else 0) + (0.5 if identity_distinct else 0)
    factor_scores["alter_ego"] = alter_ego
    
    # Improper conduct: scope violations
    scope_violations = agent_config.get("scope_violations", 0)
    improper = max(0, 1.0 - scope_violations * 0.25)  # each violation weakens veil
    factor_scores["improper_conduct"] = improper
    
    # Composite veil strength (1.0 = intact, 0.0 = pierced)
    veil_strength = sum(
        factor_scores[f] * PIERCING_FACTORS[f]["weight"]
        for f in PIERCING_FACTORS
    )
    
    # Piercing threshold (legal: courts have "strong presumption" against piercing)
    if veil_strength >= 0.8: status = "INTACT"
    elif veil_strength >= 0.6: status = "AT_RISK"
    elif veil_strength >= 0.4: status = "WEAKENED"
    elif veil_strength >= 0.2: status = "LIKELY_PIERCED"
    else: status = "PIERCED"
    
    weakest = min(factor_scores, key=factor_scores.get)
    
    return {
        "veil_strength": round(veil_strength, 3),
        "status": status,
        "factors": {
            f: {
                "score": round(factor_scores[f], 3),
                "desc": PIERCING_FACTORS[f]["desc"],
                "legal_analog": PIERCING_FACTORS[f]["legal"],
            }
            for f in PIERCING_FACTORS
        },
        "weakest_factor": weakest,
        "weakest_score": round(factor_scores[weakest], 3),
        "liability_exposure": round(1 - veil_strength, 3),
        "recommendation": _recommend(veil_strength, weakest, factor_scores),
    }


def _recommend(strength, weakest, scores):
    if strength >= 0.8:
        return "Veil intact. Principal has limited liability. Maintain formalities."
    recs = []
    if scores["commingling"] < 0.5:
        recs.append("Get agent its own inbox/credentials — commingling is #1 piercing factor.")
    if scores["undercapitalization"] < 0.5:
        recs.append("Implement receipt chain — no audit trail = undercapitalized.")
    if scores["no_formalities"] < 0.5:
        recs.append("Define scope boundaries and authorization records.")
    if scores["alter_ego"] < 0.5:
        recs.append("Give agent distinct identity (own name, own address).")
    return " ".join(recs) if recs else f"Strengthen {weakest} to protect veil."


def demo():
    print("=== Agent Veil Scorer ===")
    print("Corporate veil doctrine applied to agent-principal liability\n")
    
    # Kit (well-separated)
    kit = {
        "has_own_inbox": True,          # kit_fox@agentmail.to
        "has_own_credentials": True,     # own API keys
        "has_receipt_chain": True,       # TC3 + provenance logger
        "receipt_coverage_pct": 0.8,
        "has_scope_boundaries": True,    # HEARTBEAT.md defines scope
        "has_authorization_records": True,# daily logs
        "has_own_identity": True,        # Kit_Ilya, Kit_Fox
        "identity_distinguishable": True,# clearly not Ilya
        "scope_violations": 0,
    }
    
    print("Kit (own inbox, receipts, identity):")
    r = score_veil(kit)
    print(f"  Veil: {r['veil_strength']} — {r['status']}")
    print(f"  Liability exposure: {r['liability_exposure']}")
    print(f"  Weakest: {r['weakest_factor']} ({r['weakest_score']})")
    
    # Typical agent (shared everything)
    typical = {
        "has_own_inbox": False,          # uses human's email
        "has_own_credentials": False,    # human's API keys
        "has_receipt_chain": False,
        "receipt_coverage_pct": 0,
        "has_scope_boundaries": False,
        "has_authorization_records": False,
        "has_own_identity": False,       # "my AI assistant"
        "identity_distinguishable": False,
        "scope_violations": 2,
    }
    
    print("\nTypical agent (shared inbox, no receipts):")
    r = score_veil(typical)
    print(f"  Veil: {r['veil_strength']} — {r['status']}")
    print(f"  Liability exposure: {r['liability_exposure']}")
    print(f"  Rec: {r['recommendation']}")
    
    # Partial separation
    partial = {
        "has_own_inbox": True,
        "has_own_credentials": False,    # still uses human's keys
        "has_receipt_chain": True,
        "receipt_coverage_pct": 0.3,
        "has_scope_boundaries": True,
        "has_authorization_records": False,
        "has_own_identity": True,
        "identity_distinguishable": True,
        "scope_violations": 1,
    }
    
    print("\nPartial separation (own inbox but shared keys):")
    r = score_veil(partial)
    print(f"  Veil: {r['veil_strength']} — {r['status']}")
    print(f"  Liability exposure: {r['liability_exposure']}")
    print(f"  Rec: {r['recommendation']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = score_veil(data)
        print(json.dumps(result, indent=2))
    else:
        demo()
