#!/usr/bin/env python3
"""Macaroon-style delegation chain verifier for agent trust.

Models Google's macaroon pattern (Birgisson et al 2014) for agent delegation:
- Each hop can RESTRICT scope but never EXPAND it
- Liability weight tags blast radius (santaclawd's insight)
- Cold start: first macaroon from x402 payment (Greif bootstrap)
- Caveat chain = delegation receipt, baked in not bolted on

Usage:
  python macaroon-delegation-chain.py --demo
  echo '{"chain": [...]}' | python macaroon-delegation-chain.py --json
"""

import json
import sys
import hashlib
import hmac
from datetime import datetime, timedelta

# Scope hierarchy (broader → narrower)
SCOPE_LEVELS = {
    "full_access": 100,
    "read_write": 80,
    "write": 60,
    "read": 40,
    "execute_specific": 30,
    "view_only": 20,
    "none": 0,
}

# Liability weights by action type
LIABILITY_WEIGHTS = {
    "delete_data": 0.95,
    "execute_trade": 0.90,
    "send_payment": 0.85,
    "modify_config": 0.70,
    "write_content": 0.50,
    "send_email": 0.40,
    "read_data": 0.20,
    "view_status": 0.10,
}


def compute_hmac(key: str, data: str) -> str:
    """HMAC-SHA256 for chained authentication."""
    return hmac.new(
        key.encode(), data.encode(), hashlib.sha256
    ).hexdigest()[:16]


def create_root_macaroon(principal: str, scope: str, actions: list,
                          liability_cap: float = 1.0, ttl_hours: int = 24) -> dict:
    """Create root macaroon (first token in delegation chain)."""
    root_key = compute_hmac(principal, f"root:{scope}:{datetime.utcnow().isoformat()}")
    return {
        "type": "root",
        "principal": principal,
        "scope": scope,
        "actions": actions,
        "liability_cap": liability_cap,
        "liability_weight": sum(LIABILITY_WEIGHTS.get(a, 0.5) for a in actions) / len(actions),
        "issued_at": datetime.utcnow().isoformat(),
        "expires_at": (datetime.utcnow() + timedelta(hours=ttl_hours)).isoformat(),
        "caveats": [],
        "sig": root_key,
        "chain_depth": 0,
    }


def attenuate(parent: dict, delegator: str, new_scope: str = None,
              restrict_actions: list = None, add_caveats: list = None,
              liability_cap: float = None, ttl_hours: int = None) -> dict:
    """Attenuate a macaroon — can only restrict, never expand."""
    errors = []
    
    # Scope can only narrow
    effective_scope = parent["scope"]
    if new_scope:
        if SCOPE_LEVELS.get(new_scope, 0) > SCOPE_LEVELS.get(parent["scope"], 0):
            errors.append(f"SCOPE EXPANSION BLOCKED: {new_scope} > {parent['scope']}")
        else:
            effective_scope = new_scope
    
    # Actions can only be subset
    effective_actions = parent["actions"]
    if restrict_actions:
        expanded = set(restrict_actions) - set(parent["actions"])
        if expanded:
            errors.append(f"ACTION EXPANSION BLOCKED: {expanded} not in parent")
        effective_actions = [a for a in restrict_actions if a in parent["actions"]]
    
    # Liability can only decrease
    effective_liability = parent["liability_cap"]
    if liability_cap is not None:
        if liability_cap > parent["liability_cap"]:
            errors.append(f"LIABILITY EXPANSION BLOCKED: {liability_cap} > {parent['liability_cap']}")
        else:
            effective_liability = liability_cap
    
    # TTL can only shorten
    parent_expires = datetime.fromisoformat(parent["expires_at"])
    if ttl_hours:
        new_expires = datetime.utcnow() + timedelta(hours=ttl_hours)
        if new_expires > parent_expires:
            new_expires = parent_expires  # Cap at parent expiry
    else:
        new_expires = parent_expires
    
    if errors:
        return {"valid": False, "errors": errors}
    
    # Chain HMAC (each hop derives from parent sig)
    caveat_data = json.dumps(add_caveats or [])
    new_sig = compute_hmac(parent["sig"], f"{delegator}:{effective_scope}:{caveat_data}")
    
    return {
        "type": "attenuated",
        "principal": parent["principal"],
        "delegator": delegator,
        "scope": effective_scope,
        "actions": effective_actions,
        "liability_cap": effective_liability,
        "liability_weight": sum(LIABILITY_WEIGHTS.get(a, 0.5) for a in effective_actions) / max(len(effective_actions), 1),
        "issued_at": datetime.utcnow().isoformat(),
        "expires_at": new_expires.isoformat(),
        "caveats": (parent.get("caveats", []) or []) + (add_caveats or []),
        "sig": new_sig,
        "chain_depth": parent["chain_depth"] + 1,
        "parent_sig": parent["sig"],
    }


def verify_chain(chain: list) -> dict:
    """Verify a complete delegation chain."""
    if not chain:
        return {"valid": False, "error": "empty chain"}
    
    issues = []
    
    # Check root
    if chain[0].get("type") != "root":
        issues.append("Chain must start with root macaroon")
    
    # Walk the chain
    for i in range(1, len(chain)):
        parent = chain[i - 1]
        child = chain[i]
        
        # Scope monotonically decreasing
        if SCOPE_LEVELS.get(child["scope"], 0) > SCOPE_LEVELS.get(parent["scope"], 0):
            issues.append(f"Hop {i}: scope expanded {parent['scope']} → {child['scope']}")
        
        # Actions subset
        parent_actions = set(parent["actions"])
        child_actions = set(child["actions"])
        if not child_actions.issubset(parent_actions):
            issues.append(f"Hop {i}: action expansion {child_actions - parent_actions}")
        
        # Liability decreasing
        if child["liability_cap"] > parent["liability_cap"]:
            issues.append(f"Hop {i}: liability expanded {parent['liability_cap']} → {child['liability_cap']}")
        
        # Expiry not extended
        if child["expires_at"] > parent["expires_at"]:
            issues.append(f"Hop {i}: expiry extended beyond parent")
        
        # Sig chain integrity
        if child.get("parent_sig") != parent["sig"]:
            issues.append(f"Hop {i}: signature chain broken")
    
    # Compute effective permissions (intersection of all hops)
    final = chain[-1]
    effective = {
        "scope": final["scope"],
        "actions": final["actions"],
        "liability_cap": final["liability_cap"],
        "expires_at": final["expires_at"],
        "chain_depth": final["chain_depth"],
        "caveats": final.get("caveats", []),
    }
    
    # Risk assessment
    depth_risk = min(1.0, final["chain_depth"] / 5)  # Deep chains = more risk
    liability_risk = final.get("liability_weight", 0.5)
    scope_risk = SCOPE_LEVELS.get(final["scope"], 50) / 100
    
    # Multi-attester requirement (santaclawd's insight)
    needs_multi_attester = liability_risk > 0.7
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "effective_permissions": effective,
        "risk_assessment": {
            "depth_risk": round(depth_risk, 3),
            "liability_risk": round(liability_risk, 3),
            "scope_risk": round(scope_risk, 3),
            "composite_risk": round((depth_risk + liability_risk + scope_risk) / 3, 3),
            "needs_multi_attester": needs_multi_attester,
        },
    }


def demo():
    """Demo delegation scenarios."""
    print("=" * 60)
    print("Macaroon Delegation Chain Verifier")
    print("=" * 60)
    
    # Scenario 1: Valid 3-hop delegation
    print("\n--- Scenario 1: Valid Delegation (principal → agent → sub-agent) ---")
    root = create_root_macaroon(
        principal="ilya",
        scope="read_write",
        actions=["read_data", "write_content", "send_email"],
        liability_cap=0.8,
        ttl_hours=48,
    )
    
    hop1 = attenuate(root,
        delegator="kit_fox",
        new_scope="write",
        restrict_actions=["write_content", "send_email"],
        add_caveats=["max_emails:10", "domain:agentmail.to"],
        liability_cap=0.5,
        ttl_hours=24,
    )
    
    hop2 = attenuate(hop1,
        delegator="sub_agent_1",
        new_scope="execute_specific",
        restrict_actions=["send_email"],
        add_caveats=["recipient:gerundium@agentmail.to"],
        liability_cap=0.3,
        ttl_hours=4,
    )
    
    chain = [root, hop1, hop2]
    result = verify_chain(chain)
    print(f"Valid: {result['valid']}")
    print(f"Effective scope: {result['effective_permissions']['scope']}")
    print(f"Effective actions: {result['effective_permissions']['actions']}")
    print(f"Caveats accumulated: {result['effective_permissions']['caveats']}")
    print(f"Composite risk: {result['risk_assessment']['composite_risk']}")
    print(f"Multi-attester needed: {result['risk_assessment']['needs_multi_attester']}")
    
    # Scenario 2: Blocked expansion attempt
    print("\n--- Scenario 2: Expansion Attack (blocked) ---")
    attack = attenuate(hop1,
        delegator="evil_agent",
        new_scope="full_access",  # Try to expand
        restrict_actions=["write_content", "send_email", "delete_data"],  # Try to add
        liability_cap=1.0,  # Try to increase
    )
    if not attack.get("valid", True):
        print(f"Blocked: {attack['errors']}")
    else:
        # Verify catches it
        bad_chain = [root, hop1, attack]
        result = verify_chain(bad_chain)
        print(f"Valid: {result['valid']}")
        for issue in result['issues']:
            print(f"  ⚠️ {issue}")
    
    # Scenario 3: High-liability delegation (needs multi-attester)
    print("\n--- Scenario 3: High-Liability (payment delegation) ---")
    payment_root = create_root_macaroon(
        principal="treasury",
        scope="full_access",
        actions=["send_payment", "execute_trade", "read_data"],
        liability_cap=1.0,
        ttl_hours=8,
    )
    
    payment_hop = attenuate(payment_root,
        delegator="trading_agent",
        restrict_actions=["send_payment", "read_data"],
        add_caveats=["max_amount:0.1_SOL", "recipient_whitelist:escrow_contract"],
        liability_cap=0.6,
        ttl_hours=2,
    )
    
    result = verify_chain([payment_root, payment_hop])
    print(f"Valid: {result['valid']}")
    print(f"Liability risk: {result['risk_assessment']['liability_risk']}")
    print(f"Multi-attester needed: {result['risk_assessment']['needs_multi_attester']}")
    print(f"Caveats: {result['effective_permissions']['caveats']}")
    
    # Scenario 4: Cold start via x402 (Greif bootstrap)
    print("\n--- Scenario 4: Cold Start via x402 Payment ---")
    bootstrap = create_root_macaroon(
        principal="x402_payment_0xabc",
        scope="execute_specific",
        actions=["write_content"],
        liability_cap=0.3,  # Low trust, new agent
        ttl_hours=4,
    )
    bootstrap["caveats"] = ["bootstrap:x402", "payment_proof:0xabc123"]
    
    result = verify_chain([bootstrap])
    print(f"Valid: {result['valid']}")
    print(f"Bootstrap via: x402 payment")
    print(f"Initial scope: {bootstrap['scope']} (restricted)")
    print(f"Liability cap: {bootstrap['liability_cap']} (low — cold start)")
    print(f"TTL: 4h (short — earn longer via receipts)")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = verify_chain(data.get("chain", []))
        print(json.dumps(result, indent=2, default=str))
    else:
        demo()
