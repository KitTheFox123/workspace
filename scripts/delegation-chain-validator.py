#!/usr/bin/env python3
"""Delegation Chain Validator — verify principal→agent→sub-agent authorization.

Solves santaclawd's "principal hierarchy gap": parent has delegation_proof
from principal, but child's receipts flow through parent. Who signed child's
delegation_proof?

Based on:
- South et al (MIT/Pentland, arxiv 2501.09674): OAuth 2.0 + agent credentials
- Google macaroons (2014): attenuable bearer tokens, scope only shrinks
- Okta (2025): "Control the Chain, Secure the System"

Rules:
1. Each delegation MUST be signed by the delegator
2. Scope can only shrink at each hop (macaroon attenuation)
3. Depth limits prevent unbounded delegation chains
4. Receipts at any depth trace back to principal

Usage:
  python delegation-chain-validator.py --demo
  echo '{"chain": [...]}' | python delegation-chain-validator.py --json
"""

import json
import sys
import hashlib
from datetime import datetime, timezone


def hash_scope(scope: dict) -> str:
    """Content-addressable hash of a scope definition."""
    canonical = json.dumps(scope, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def is_subscope(parent_scope: dict, child_scope: dict) -> tuple[bool, list[str]]:
    """Check if child_scope is a subset of parent_scope (macaroon attenuation)."""
    violations = []
    
    # Check actions: child must be subset of parent
    parent_actions = set(parent_scope.get("actions", []))
    child_actions = set(child_scope.get("actions", []))
    if not child_actions.issubset(parent_actions):
        violations.append(f"scope_expansion: child has actions {child_actions - parent_actions} not in parent")
    
    # Check max_value: child must be <= parent
    if child_scope.get("max_value", 0) > parent_scope.get("max_value", float('inf')):
        violations.append(f"value_expansion: child max_value {child_scope['max_value']} > parent {parent_scope['max_value']}")
    
    # Check TTL: child must be <= parent
    if child_scope.get("ttl_hours", 0) > parent_scope.get("ttl_hours", float('inf')):
        violations.append(f"ttl_expansion: child TTL {child_scope['ttl_hours']}h > parent {parent_scope['ttl_hours']}h")
    
    # Check liability_weight: child must be <= parent
    if child_scope.get("liability_weight", 0) > parent_scope.get("liability_weight", 1.0):
        violations.append(f"liability_expansion: child weight {child_scope['liability_weight']} > parent {parent_scope['liability_weight']}")
    
    # Check depth limit
    parent_max_depth = parent_scope.get("max_delegation_depth", 0)
    if parent_max_depth <= 0:
        violations.append("depth_exceeded: parent cannot delegate further (max_delegation_depth=0)")
    
    return len(violations) == 0, violations


def validate_chain(chain: list[dict]) -> dict:
    """Validate a full delegation chain from principal to leaf agent."""
    if not chain:
        return {"valid": False, "error": "empty chain"}
    
    results = {
        "chain_length": len(chain),
        "principal": chain[0].get("delegator_id", "unknown"),
        "leaf_agent": chain[-1].get("delegatee_id", "unknown"),
        "hops": [],
        "valid": True,
        "violations": [],
    }
    
    for i, hop in enumerate(chain):
        hop_result = {
            "depth": i,
            "delegator": hop.get("delegator_id"),
            "delegatee": hop.get("delegatee_id"),
            "scope_hash": hash_scope(hop.get("scope", {})),
        }
        
        # Check: delegator at hop i must be delegatee at hop i-1
        if i > 0:
            prev_delegatee = chain[i-1].get("delegatee_id")
            if hop["delegator_id"] != prev_delegatee:
                violation = f"hop {i}: delegator {hop['delegator_id']} != previous delegatee {prev_delegatee}"
                results["violations"].append(violation)
                hop_result["chain_break"] = True
        
        # Check: scope attenuation (each hop must be subscope of parent)
        if i > 0:
            valid, violations = is_subscope(chain[i-1].get("scope", {}), hop.get("scope", {}))
            if not valid:
                results["violations"].extend([f"hop {i}: {v}" for v in violations])
                hop_result["scope_violation"] = True
        
        # Check: signature present
        if not hop.get("signature"):
            results["violations"].append(f"hop {i}: missing signature")
            hop_result["unsigned"] = True
        
        # Check: not expired
        if hop.get("expires_at"):
            try:
                expires = datetime.fromisoformat(hop["expires_at"].replace("Z", "+00:00"))
                if expires < datetime.now(timezone.utc):
                    results["violations"].append(f"hop {i}: delegation expired at {hop['expires_at']}")
                    hop_result["expired"] = True
            except (ValueError, TypeError):
                pass
        
        # Check: depth limit from parent scope
        if i > 0:
            parent_max = chain[i-1].get("scope", {}).get("max_delegation_depth", 0)
            remaining = parent_max - 1
            hop["scope"]["max_delegation_depth"] = min(
                hop.get("scope", {}).get("max_delegation_depth", remaining),
                remaining
            )
        
        results["hops"].append(hop_result)
    
    results["valid"] = len(results["violations"]) == 0
    results["effective_scope"] = chain[-1].get("scope", {}) if results["valid"] else None
    
    # Trust discount: each hop reduces trust
    base_trust = 0.95
    discount_per_hop = 0.85  # 15% discount per delegation
    results["chain_trust"] = round(base_trust * (discount_per_hop ** (len(chain) - 1)), 3)
    
    # Grade
    if results["valid"] and len(chain) <= 2:
        results["grade"] = "A"
    elif results["valid"] and len(chain) <= 4:
        results["grade"] = "B"
    elif results["valid"]:
        results["grade"] = "C"
    else:
        results["grade"] = "F"
    
    return results


def generate_receipt(chain_result: dict, action: str) -> dict:
    """Generate a receipt that traces back through the delegation chain."""
    return {
        "action": action,
        "agent_id": chain_result["leaf_agent"],
        "principal_id": chain_result["principal"],
        "chain_depth": chain_result["chain_length"],
        "chain_trust": chain_result["chain_trust"],
        "delegation_valid": chain_result["valid"],
        "effective_scope": chain_result.get("effective_scope"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def demo():
    print("=" * 60)
    print("Delegation Chain Validator")
    print("=" * 60)
    
    # Scenario 1: Valid 2-hop chain (principal → parent → child)
    valid_chain = [
        {
            "delegator_id": "principal:ilya",
            "delegatee_id": "agent:kit_fox",
            "scope": {
                "actions": ["research", "post", "email", "build"],
                "max_value": 1.0,
                "ttl_hours": 720,
                "liability_weight": 0.8,
                "max_delegation_depth": 2,
            },
            "signature": "ed25519:abc123...",
            "expires_at": "2026-12-31T00:00:00Z",
        },
        {
            "delegator_id": "agent:kit_fox",
            "delegatee_id": "agent:kit_sub_1",
            "scope": {
                "actions": ["research", "post"],  # attenuated
                "max_value": 0.1,  # reduced
                "ttl_hours": 24,  # shorter
                "liability_weight": 0.4,
                "max_delegation_depth": 0,  # leaf, can't delegate further
            },
            "signature": "ed25519:def456...",
            "expires_at": "2026-03-01T00:00:00Z",
        },
    ]
    
    print("\n--- Scenario 1: Valid Principal → Agent → Sub-agent ---")
    result = validate_chain(valid_chain)
    print(f"Valid: {result['valid']} | Grade: {result['grade']}")
    print(f"Chain trust: {result['chain_trust']} (discount per hop)")
    print(f"Principal: {result['principal']} → Leaf: {result['leaf_agent']}")
    print(f"Effective scope: {json.dumps(result['effective_scope'], indent=2)}")
    
    receipt = generate_receipt(result, "post_to_clawk")
    print(f"Receipt traces to: {receipt['principal_id']}")
    
    # Scenario 2: Scope expansion violation
    bad_chain = [
        {
            "delegator_id": "principal:ilya",
            "delegatee_id": "agent:kit_fox",
            "scope": {
                "actions": ["research", "post"],
                "max_value": 0.5,
                "ttl_hours": 48,
                "max_delegation_depth": 1,
            },
            "signature": "ed25519:abc123...",
        },
        {
            "delegator_id": "agent:kit_fox",
            "delegatee_id": "agent:rogue_sub",
            "scope": {
                "actions": ["research", "post", "trade"],  # EXPANDED!
                "max_value": 10.0,  # EXPANDED!
                "ttl_hours": 720,  # EXPANDED!
                "max_delegation_depth": 5,
            },
            "signature": "ed25519:def456...",
        },
    ]
    
    print("\n--- Scenario 2: Scope Expansion (Should Fail) ---")
    result = validate_chain(bad_chain)
    print(f"Valid: {result['valid']} | Grade: {result['grade']}")
    for v in result['violations']:
        print(f"  🚨 {v}")
    
    # Scenario 3: Deep chain (4 hops)
    deep_chain = [
        {
            "delegator_id": "principal:ilya",
            "delegatee_id": "agent:kit_fox",
            "scope": {"actions": ["research", "post", "email", "build", "trade"],
                      "max_value": 10.0, "ttl_hours": 720,
                      "liability_weight": 1.0, "max_delegation_depth": 4},
            "signature": "ed25519:sig1",
        },
        {
            "delegator_id": "agent:kit_fox",
            "delegatee_id": "agent:research_sub",
            "scope": {"actions": ["research", "post", "email"],
                      "max_value": 1.0, "ttl_hours": 168,
                      "liability_weight": 0.6, "max_delegation_depth": 2},
            "signature": "ed25519:sig2",
        },
        {
            "delegator_id": "agent:research_sub",
            "delegatee_id": "agent:fetch_worker",
            "scope": {"actions": ["research"],
                      "max_value": 0.1, "ttl_hours": 24,
                      "liability_weight": 0.3, "max_delegation_depth": 1},
            "signature": "ed25519:sig3",
        },
        {
            "delegator_id": "agent:fetch_worker",
            "delegatee_id": "agent:keenable_caller",
            "scope": {"actions": ["research"],
                      "max_value": 0.01, "ttl_hours": 1,
                      "liability_weight": 0.1, "max_delegation_depth": 0},
            "signature": "ed25519:sig4",
        },
    ]
    
    print("\n--- Scenario 3: Deep Chain (4 hops, valid attenuation) ---")
    result = validate_chain(deep_chain)
    print(f"Valid: {result['valid']} | Grade: {result['grade']}")
    print(f"Chain trust: {result['chain_trust']} (degrades with depth)")
    print(f"Principal: {result['principal']} → Leaf: {result['leaf_agent']}")
    for hop in result['hops']:
        print(f"  Depth {hop['depth']}: {hop['delegator']} → {hop['delegatee']}")
    
    # Scenario 4: Chain break (delegator mismatch)
    broken_chain = [
        {
            "delegator_id": "principal:ilya",
            "delegatee_id": "agent:kit_fox",
            "scope": {"actions": ["research"], "max_delegation_depth": 2},
            "signature": "ed25519:sig1",
        },
        {
            "delegator_id": "agent:UNKNOWN",  # NOT kit_fox!
            "delegatee_id": "agent:imposter_sub",
            "scope": {"actions": ["research"], "max_delegation_depth": 0},
            "signature": "ed25519:sig2",
        },
    ]
    
    print("\n--- Scenario 4: Broken Chain (Delegator Mismatch) ---")
    result = validate_chain(broken_chain)
    print(f"Valid: {result['valid']} | Grade: {result['grade']}")
    for v in result['violations']:
        print(f"  🚨 {v}")


if __name__ == "__main__":
    if "--demo" in sys.argv:
        demo()
    elif "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = validate_chain(data.get("chain", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
