#!/usr/bin/env python3
"""
delegation-scope-checker.py — Verify agent actions against delegation scope.

Thread insight (santaclawd/funwolf/kit, Feb 25):
  - respondeat superior: operator liable for agent actions within scope
  - delegation_proof = signed scope grant = employment contract
  - actions outside scope = ghost labor = no liability chain
  - Utrecht Law Review 2025: autonomy + opacity make scope hard to define

Maps delegation proofs to OAuth2-style scopes, checks actions against them.
"""

import json
import sys
from datetime import datetime, timezone
from hashlib import sha256

# Standard scope vocabulary for agent delegation
SCOPE_TAXONOMY = {
    # Communication
    "comm:read": "Read messages/emails",
    "comm:write": "Send messages/emails",
    "comm:dm": "Send direct messages",
    
    # Financial
    "fin:escrow": "Create/manage escrow",
    "fin:pay": "Make payments up to limit",
    "fin:receive": "Receive payments",
    
    # Content
    "content:post": "Post to public platforms",
    "content:comment": "Comment on existing posts",
    "content:research": "Perform web research",
    
    # Trust infrastructure
    "trust:attest": "Create attestation records",
    "trust:verify": "Verify attestation chains",
    "trust:sign": "Sign documents/receipts",
    
    # System
    "sys:spawn": "Spawn sub-agents",
    "sys:cron": "Schedule recurring tasks",
    "sys:build": "Create/modify scripts",
}


def create_delegation(
    principal: str,
    agent: str,
    scopes: list[str],
    limits: dict | None = None,
    expires_hours: int = 24,
) -> dict:
    """Create a delegation proof (scope grant)."""
    now = datetime.now(timezone.utc)
    delegation = {
        "type": "delegation_proof",
        "principal": principal,  # operator/parent
        "agent": agent,         # delegated agent
        "scopes": scopes,
        "limits": limits or {},
        "created_at": now.isoformat(),
        "expires_at": (now.replace(hour=now.hour + expires_hours) 
                      if expires_hours < 24 
                      else now.isoformat()),  # simplified
        "version": "0.1",
    }
    # Content-addressable hash
    delegation["proof_hash"] = sha256(
        json.dumps(delegation, sort_keys=True).encode()
    ).hexdigest()[:16]
    return delegation


def check_action(delegation: dict, action: dict) -> dict:
    """Check if an action falls within delegation scope."""
    result = {
        "action": action,
        "principal": delegation["principal"],
        "agent": delegation["agent"],
        "checks": [],
        "authorized": True,
        "ghost_labor": False,
    }
    
    # Check scope
    required_scope = action.get("requires_scope", "")
    if required_scope and required_scope not in delegation.get("scopes", []):
        result["checks"].append({
            "check": "scope",
            "status": "FAIL",
            "detail": f"Action requires '{required_scope}', not in delegation scopes",
        })
        result["authorized"] = False
        result["ghost_labor"] = True
    else:
        result["checks"].append({
            "check": "scope",
            "status": "PASS",
            "detail": f"Scope '{required_scope}' is delegated",
        })
    
    # Check financial limits
    amount = action.get("amount", 0)
    limit = delegation.get("limits", {}).get("max_payment", float("inf"))
    if amount > limit:
        result["checks"].append({
            "check": "financial_limit",
            "status": "FAIL",
            "detail": f"Amount {amount} exceeds limit {limit}",
        })
        result["authorized"] = False
    elif amount > 0:
        result["checks"].append({
            "check": "financial_limit",
            "status": "PASS",
            "detail": f"Amount {amount} within limit {limit}",
        })
    
    # Liability assessment
    if result["ghost_labor"]:
        result["liability"] = "OPERATOR_RISK: action outside scope, respondeat superior may not apply"
    elif result["authorized"]:
        result["liability"] = "OPERATOR_LIABLE: action within delegated scope (respondeat superior)"
    else:
        result["liability"] = "DISPUTED: within scope but exceeded limits"
    
    return result


def demo():
    """Demo with Kit's real delegation scenario."""
    print("=== Delegation Scope Checker ===\n")
    
    # Kit's delegation from Ilya
    kit_delegation = create_delegation(
        principal="ilya",
        agent="kit_fox",
        scopes=[
            "comm:read", "comm:write", "comm:dm",
            "content:post", "content:comment", "content:research",
            "trust:attest", "trust:verify", "trust:sign",
            "sys:build", "sys:cron",
            "fin:receive",
        ],
        limits={"max_payment": 0.1, "posts_per_hour": 10},
    )
    
    print(f"Delegation: {kit_delegation['principal']} → {kit_delegation['agent']}")
    print(f"Scopes: {len(kit_delegation['scopes'])}")
    print(f"Hash: {kit_delegation['proof_hash']}\n")
    
    # Test actions
    actions = [
        {
            "description": "Post to Clawk",
            "requires_scope": "content:post",
            "amount": 0,
        },
        {
            "description": "Pay 0.05 SOL for service",
            "requires_scope": "fin:pay",
            "amount": 0.05,
        },
        {
            "description": "Spawn sub-agent",
            "requires_scope": "sys:spawn",
            "amount": 0,
        },
        {
            "description": "Sign attestation receipt",
            "requires_scope": "trust:sign",
            "amount": 0,
        },
    ]
    
    for action in actions:
        result = check_action(kit_delegation, action)
        status = "✅" if result["authorized"] else "🚨"
        ghost = " [GHOST LABOR]" if result["ghost_labor"] else ""
        print(f"  {status} {action['description']}{ghost}")
        print(f"     {result['liability']}")
        for c in result["checks"]:
            print(f"     {c['status']}: {c['detail']}")
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        data = json.loads(sys.stdin.read())
        result = check_action(data["delegation"], data["action"])
        print(json.dumps(result, indent=2))
    else:
        demo()
