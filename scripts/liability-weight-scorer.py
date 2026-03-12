#!/usr/bin/env python3
"""Liability Weight Scorer — actuarial pricing for agent delegation.

Maps santaclawd's insight: liability_weight = f(frequency, severity, exposure).
Delegator self-declares = self-insuring. Attester-set floor = external underwriter.

Based on:
- Arrow 1963: moral hazard in insurance
- Verisk CG 40 47 (Jan 2026): GL exclusions for generative AI
- Hart 1995: incomplete contracts + residual control rights

Usage:
  python liability-weight-scorer.py --demo
  echo '{"action": "execute_trade", ...}' | python liability-weight-scorer.py --json
"""

import json
import sys
import math

# Action taxonomy with base liability parameters
# frequency: how often this action type leads to claims (0-1)
# severity: average loss when claim occurs (0-1 normalized)
# exposure: breadth of potential harm (0-1)
ACTION_PROFILES = {
    "read_file": {"frequency": 0.01, "severity": 0.05, "exposure": 0.10, "category": "observation"},
    "write_email": {"frequency": 0.05, "severity": 0.20, "exposure": 0.30, "category": "communication"},
    "post_public": {"frequency": 0.08, "severity": 0.35, "exposure": 0.80, "category": "communication"},
    "execute_trade": {"frequency": 0.15, "severity": 0.90, "exposure": 0.70, "category": "financial"},
    "transfer_funds": {"frequency": 0.12, "severity": 0.95, "exposure": 0.60, "category": "financial"},
    "delete_data": {"frequency": 0.03, "severity": 0.80, "exposure": 0.50, "category": "destructive"},
    "modify_config": {"frequency": 0.06, "severity": 0.70, "exposure": 0.40, "category": "system"},
    "generate_content": {"frequency": 0.10, "severity": 0.40, "exposure": 0.90, "category": "creative"},
    "sign_attestation": {"frequency": 0.04, "severity": 0.60, "exposure": 0.50, "category": "trust"},
    "delegate_task": {"frequency": 0.07, "severity": 0.50, "exposure": 0.45, "category": "delegation"},
}

# Delegation depth multiplier (respondeat superior)
DEPTH_MULTIPLIER = {
    0: 1.0,    # Direct action
    1: 1.3,    # One level of delegation
    2: 1.7,    # Two levels
    3: 2.2,    # Three levels — getting risky
}


def compute_liability_weight(action: str, delegation_depth: int = 0,
                              delegator_declared: float = None,
                              attester_floor: float = None,
                              history_clean: int = 0,
                              history_disputed: int = 0) -> dict:
    """Compute liability weight for an action."""
    profile = ACTION_PROFILES.get(action, {"frequency": 0.10, "severity": 0.50, "exposure": 0.50, "category": "unknown"})
    
    # Base expected loss = frequency × severity × exposure
    base_loss = profile["frequency"] * profile["severity"] * profile["exposure"]
    
    # Delegation depth multiplier (respondeat superior chain)
    depth_mult = DEPTH_MULTIPLIER.get(min(delegation_depth, 3), 2.5)
    
    # History-adjusted frequency (Bayesian)
    if history_clean + history_disputed > 0:
        observed_freq = (history_disputed + 1) / (history_clean + history_disputed + 2)
        # Blend observed with base (weight increases with data)
        data_weight = min(1.0, (history_clean + history_disputed) / 50)
        adj_frequency = profile["frequency"] * (1 - data_weight) + observed_freq * data_weight
    else:
        adj_frequency = profile["frequency"]
    
    # Adjusted expected loss
    expected_loss = adj_frequency * profile["severity"] * profile["exposure"] * depth_mult
    
    # Liability weight (normalized 0-1, capped)
    liability_weight = min(1.0, expected_loss * 5)  # Scale so 0.20 expected loss = 1.0 weight
    
    # Self-insurance check (Arrow moral hazard)
    moral_hazard_flag = False
    if delegator_declared is not None:
        if delegator_declared < liability_weight * 0.5:
            moral_hazard_flag = True  # Delegator under-declaring by >50%
    
    # Bilateral negotiation (attester floor + delegator ceiling)
    negotiated_weight = liability_weight
    if attester_floor is not None and delegator_declared is not None:
        negotiated_weight = max(attester_floor, min(delegator_declared, liability_weight))
    elif attester_floor is not None:
        negotiated_weight = max(attester_floor, liability_weight)
    elif delegator_declared is not None:
        negotiated_weight = delegator_declared  # Self-insured — moral hazard applies
    
    # Escrow recommendation
    escrow_pct = min(100, int(negotiated_weight * 100))
    
    # Insurability (Verisk CG 40 47: no data = excluded)
    insurable = (history_clean + history_disputed) >= 10
    
    return {
        "action": action,
        "category": profile["category"],
        "base_expected_loss": round(base_loss, 4),
        "delegation_depth": delegation_depth,
        "depth_multiplier": depth_mult,
        "adjusted_frequency": round(adj_frequency, 4),
        "liability_weight": round(liability_weight, 4),
        "negotiated_weight": round(negotiated_weight, 4),
        "moral_hazard": moral_hazard_flag,
        "escrow_recommendation": f"{escrow_pct}%",
        "insurable": insurable,
        "insurability_note": "Sufficient loss history" if insurable else "Verisk CG 40 47: excluded — insufficient data",
        "governance": "payment_first" if negotiated_weight < 0.15 else "escrow" if negotiated_weight < 0.60 else "full_escrow_plus_attestation",
    }


def demo():
    print("=" * 60)
    print("Liability Weight Scorer")
    print("=" * 60)
    
    # Scenario 1: Low-risk read
    print("\n--- Read File (low risk) ---")
    r = compute_liability_weight("read_file")
    print(f"  Weight: {r['liability_weight']} → Escrow: {r['escrow_recommendation']} → {r['governance']}")
    
    # Scenario 2: Execute trade (high risk)
    print("\n--- Execute Trade (high risk) ---")
    r = compute_liability_weight("execute_trade")
    print(f"  Weight: {r['liability_weight']} → Escrow: {r['escrow_recommendation']} → {r['governance']}")
    
    # Scenario 3: Delegated trade (depth=2)
    print("\n--- Execute Trade via 2-level delegation ---")
    r = compute_liability_weight("execute_trade", delegation_depth=2)
    print(f"  Weight: {r['liability_weight']} → Escrow: {r['escrow_recommendation']}")
    print(f"  Depth multiplier: {r['depth_multiplier']}x")
    
    # Scenario 4: Moral hazard — delegator under-declares
    print("\n--- Moral Hazard Detection ---")
    r = compute_liability_weight("execute_trade", delegator_declared=0.05)
    print(f"  Self-declared: 0.05, Computed: {r['liability_weight']}")
    print(f"  Moral hazard: {'⚠️ YES' if r['moral_hazard'] else 'No'}")
    print(f"  Negotiated: {r['negotiated_weight']} (self-insured at declared rate)")
    
    # Scenario 5: Bilateral — attester floor corrects moral hazard
    print("\n--- Bilateral Negotiation (attester floor) ---")
    r = compute_liability_weight("execute_trade", delegator_declared=0.05, attester_floor=0.40)
    print(f"  Delegator wants: 0.05, Attester floor: 0.40, Computed: {r['liability_weight']}")
    print(f"  Negotiated: {r['negotiated_weight']} (attester floor wins)")
    print(f"  Moral hazard: {'⚠️ YES' if r['moral_hazard'] else 'No'}")
    
    # Scenario 6: History reduces frequency
    print("\n--- Experienced Agent (50 clean, 1 disputed) ---")
    r = compute_liability_weight("execute_trade", history_clean=50, history_disputed=1)
    print(f"  Adjusted frequency: {r['adjusted_frequency']} (base: 0.15)")
    print(f"  Weight: {r['liability_weight']} → Escrow: {r['escrow_recommendation']}")
    print(f"  Insurable: {'✅' if r['insurable'] else '❌'} — {r['insurability_note']}")
    
    # Scenario 7: New agent — uninsurable
    print("\n--- New Agent (no history) ---")
    r = compute_liability_weight("execute_trade")
    print(f"  Weight: {r['liability_weight']} → Escrow: {r['escrow_recommendation']}")
    print(f"  Insurable: {'✅' if r['insurable'] else '❌'} — {r['insurability_note']}")
    
    # Full action comparison
    print("\n--- Action Risk Comparison ---")
    print(f"  {'Action':<20} {'Weight':>8} {'Escrow':>8} {'Governance'}")
    print(f"  {'-'*20} {'-'*8} {'-'*8} {'-'*20}")
    for action in sorted(ACTION_PROFILES.keys(), key=lambda a: compute_liability_weight(a)["liability_weight"]):
        r = compute_liability_weight(action)
        print(f"  {action:<20} {r['liability_weight']:>8.4f} {r['escrow_recommendation']:>8} {r['governance']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = compute_liability_weight(**data)
        print(json.dumps(result, indent=2))
    else:
        demo()
