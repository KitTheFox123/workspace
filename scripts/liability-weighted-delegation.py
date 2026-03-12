#!/usr/bin/env python3
"""Liability-Weighted Delegation Scorer — scope attenuation with risk tiers.

santaclawd's insight: "write email = low. execute trade = high. delete data = very high.
delegation_proof should encode liability_weight."

Maps action types to liability tiers, determines required attestation depth,
and scores whether a delegation chain meets the requirements.

Based on:
- Google macaroons (2014): bearer tokens with attenuable caveats
- Lawfare/Schwarcz 2025: insurers need loss data, receipts = actuarial dataset
- Campbell's Law (1979): metrics corrupt when used for decisions
"""

import json
import sys
import math

# Liability tiers: action -> weight (0.0 = trivial, 1.0 = critical)
ACTION_LIABILITY = {
    # Low liability (tier 1)
    "read_public": 0.05,
    "send_message": 0.10,
    "write_email": 0.15,
    "search_web": 0.05,
    "read_file": 0.10,
    
    # Medium liability (tier 2)
    "write_file": 0.30,
    "post_public": 0.35,
    "send_dm": 0.25,
    "api_call": 0.30,
    "create_account": 0.40,
    
    # High liability (tier 3)
    "execute_code": 0.60,
    "install_package": 0.55,
    "modify_config": 0.65,
    "send_money": 0.70,
    "sign_contract": 0.75,
    
    # Critical liability (tier 4)
    "execute_trade": 0.85,
    "delete_data": 0.90,
    "delegate_authority": 0.80,
    "modify_credentials": 0.95,
    "transfer_ownership": 1.00,
}

# Required attestation depth per tier
TIER_REQUIREMENTS = {
    1: {"min_attesters": 0, "proof_classes": 0, "escrow_pct": 0,   "dispute_window_h": 0},
    2: {"min_attesters": 1, "proof_classes": 1, "escrow_pct": 10,  "dispute_window_h": 4},
    3: {"min_attesters": 2, "proof_classes": 2, "escrow_pct": 30,  "dispute_window_h": 24},
    4: {"min_attesters": 3, "proof_classes": 3, "escrow_pct": 50,  "dispute_window_h": 48},
}


def get_tier(weight: float) -> int:
    if weight <= 0.20: return 1
    if weight <= 0.45: return 2
    if weight <= 0.75: return 3
    return 4


def score_delegation(delegation: dict) -> dict:
    """Score a delegation chain against liability requirements."""
    action = delegation.get("action", "unknown")
    weight = ACTION_LIABILITY.get(action, 0.50)
    tier = get_tier(weight)
    reqs = TIER_REQUIREMENTS[tier]
    
    # What the delegation provides
    attesters = delegation.get("attesters", 0)
    proof_classes = delegation.get("proof_classes", 0)
    escrow_pct = delegation.get("escrow_pct", 0)
    dispute_window_h = delegation.get("dispute_window_h", 0)
    
    # Macaroon-style scope checks
    scope_chain = delegation.get("scope_chain", [])
    scope_valid = True
    scope_issues = []
    
    # Each delegator can only RESTRICT scope, never expand
    current_scope = set(scope_chain[0]) if scope_chain else set()
    for i, scope in enumerate(scope_chain[1:], 1):
        new_scope = set(scope)
        if not new_scope.issubset(current_scope):
            scope_valid = False
            expanded = new_scope - current_scope
            scope_issues.append(f"Layer {i} expanded scope: +{expanded}")
        current_scope = new_scope
    
    # Check requirements
    checks = {
        "attesters": attesters >= reqs["min_attesters"],
        "proof_classes": proof_classes >= reqs["proof_classes"],
        "escrow": escrow_pct >= reqs["escrow_pct"],
        "dispute_window": dispute_window_h >= reqs["dispute_window_h"],
        "scope_attenuation": scope_valid,
    }
    
    passed = sum(checks.values())
    total = len(checks)
    compliance = passed / total
    
    return {
        "action": action,
        "liability_weight": weight,
        "tier": tier,
        "tier_label": ["", "LOW", "MEDIUM", "HIGH", "CRITICAL"][tier],
        "requirements": reqs,
        "provided": {
            "attesters": attesters,
            "proof_classes": proof_classes,
            "escrow_pct": escrow_pct,
            "dispute_window_h": dispute_window_h,
        },
        "checks": checks,
        "compliance": round(compliance, 3),
        "grade": "PASS" if compliance >= 0.8 else "WARN" if compliance >= 0.6 else "FAIL",
        "scope_issues": scope_issues,
        "insurance_note": f"Actuarial tier {tier}: {'insurable' if compliance >= 0.8 else 'uninsurable without additional attestation'}",
    }


def demo():
    print("=" * 60)
    print("Liability-Weighted Delegation Scorer")
    print("=" * 60)
    
    cases = [
        {
            "name": "Low: Send email (well-attested)",
            "delegation": {
                "action": "write_email",
                "attesters": 1,
                "proof_classes": 1,
                "escrow_pct": 0,
                "dispute_window_h": 0,
                "scope_chain": [["write_email", "read_file"], ["write_email"]],
            }
        },
        {
            "name": "High: Execute trade (under-attested)",
            "delegation": {
                "action": "execute_trade",
                "attesters": 1,
                "proof_classes": 1,
                "escrow_pct": 10,
                "dispute_window_h": 4,
                "scope_chain": [["execute_trade", "read_file"], ["execute_trade"]],
            }
        },
        {
            "name": "Critical: Delete data (properly attested)",
            "delegation": {
                "action": "delete_data",
                "attesters": 3,
                "proof_classes": 3,
                "escrow_pct": 50,
                "dispute_window_h": 48,
                "scope_chain": [["delete_data", "read_file", "write_file"], ["delete_data", "read_file"], ["delete_data"]],
            }
        },
        {
            "name": "Scope violation: Delegation expands authority",
            "delegation": {
                "action": "send_money",
                "attesters": 2,
                "proof_classes": 2,
                "escrow_pct": 30,
                "dispute_window_h": 24,
                "scope_chain": [["send_message"], ["send_message", "send_money"]],
            }
        },
    ]
    
    for case in cases:
        print(f"\n--- {case['name']} ---")
        result = score_delegation(case["delegation"])
        print(f"Action: {result['action']} (weight: {result['liability_weight']})")
        print(f"Tier: {result['tier']} ({result['tier_label']})")
        print(f"Compliance: {result['compliance']:.0%} → {result['grade']}")
        fails = [k for k, v in result["checks"].items() if not v]
        if fails:
            print(f"Failed: {', '.join(fails)}")
        if result["scope_issues"]:
            for issue in result["scope_issues"]:
                print(f"  🚨 {issue}")
        print(f"Insurance: {result['insurance_note']}")
    
    # Summary table
    print("\n--- Action Liability Table ---")
    print(f"{'Action':<25} {'Weight':>6} {'Tier':>4} {'Min Attesters':>14}")
    for action, weight in sorted(ACTION_LIABILITY.items(), key=lambda x: x[1]):
        tier = get_tier(weight)
        reqs = TIER_REQUIREMENTS[tier]
        print(f"{action:<25} {weight:>6.2f} {tier:>4} {reqs['min_attesters']:>14}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = score_delegation(data)
        print(json.dumps(result, indent=2))
    else:
        demo()
