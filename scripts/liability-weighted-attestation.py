#!/usr/bin/env python3
"""Liability-Weighted Attestation Requirements — santaclawd's insight formalized.

Higher-liability actions require stronger attestation. Maps action types to
liability tiers and computes required attestation depth.

Based on:
- ABA/Lior 2025: "silent AI" coverage gaps in traditional policies
- Verisk CG 40 47/48 (Jan 2026): AI exclusions in general liability
- santaclawd: "flat scope treats all actions equal. it shouldn't."
- Macaroon attenuation: scope can only shrink, never expand

Usage:
  python liability-weighted-attestation.py --demo
  echo '{"action": "execute_trade", "value_usd": 5000}' | python liability-weighted-attestation.py --json
"""

import json
import sys
import math

# Liability tiers with required attestation
LIABILITY_TIERS = {
    "minimal": {
        "weight": 0.1,
        "min_attesters": 0,
        "escrow_pct": 0,
        "dispute_window_h": 0,
        "examples": ["read_public_data", "log_event", "send_notification"],
    },
    "low": {
        "weight": 0.3,
        "min_attesters": 1,
        "escrow_pct": 0,
        "dispute_window_h": 4,
        "examples": ["write_email", "post_social", "update_profile"],
    },
    "medium": {
        "weight": 0.5,
        "min_attesters": 2,
        "escrow_pct": 25,
        "dispute_window_h": 24,
        "examples": ["modify_config", "create_account", "submit_form"],
    },
    "high": {
        "weight": 0.8,
        "min_attesters": 3,
        "escrow_pct": 50,
        "dispute_window_h": 48,
        "examples": ["execute_trade", "transfer_funds", "sign_contract"],
    },
    "critical": {
        "weight": 1.0,
        "min_attesters": 4,
        "escrow_pct": 100,
        "dispute_window_h": 168,  # 7 days
        "examples": ["delete_data", "revoke_access", "deploy_production"],
    },
}

# Action → liability tier mapping
ACTION_LIABILITY = {
    "read_public_data": "minimal",
    "log_event": "minimal",
    "send_notification": "minimal",
    "write_email": "low",
    "post_social": "low",
    "update_profile": "low",
    "comment": "low",
    "modify_config": "medium",
    "create_account": "medium",
    "submit_form": "medium",
    "api_call": "medium",
    "execute_trade": "high",
    "transfer_funds": "high",
    "sign_contract": "high",
    "grant_permission": "high",
    "delete_data": "critical",
    "revoke_access": "critical",
    "deploy_production": "critical",
    "modify_credentials": "critical",
}

# Verisk AI exclusion categories (CG 40 47/48, Jan 2026)
VERISK_EXCLUSIONS = {
    "bodily_injury_property_damage": {"addressable": True, "receipt_solution": "scope attestation + action log"},
    "personal_advertising_injury": {"addressable": True, "receipt_solution": "content hash + generation attestation"},
    "discrimination": {"addressable": False, "receipt_solution": "content-layer, requires bias audit"},
    "ip_infringement": {"addressable": False, "receipt_solution": "content-layer, requires provenance chain"},
    "data_breach": {"addressable": True, "receipt_solution": "access log attestation + encryption proof"},
    "professional_liability": {"addressable": True, "receipt_solution": "scope + outcome + attester chain"},
}


def classify_action(action: str, value_usd: float = 0) -> dict:
    """Classify an action and compute attestation requirements."""
    base_tier = ACTION_LIABILITY.get(action, "medium")
    tier_info = LIABILITY_TIERS[base_tier]
    
    # Value-based escalation: high-value actions bump up a tier
    if value_usd > 10000 and base_tier != "critical":
        tiers = list(LIABILITY_TIERS.keys())
        idx = min(tiers.index(base_tier) + 1, len(tiers) - 1)
        base_tier = tiers[idx]
        tier_info = LIABILITY_TIERS[base_tier]
    elif value_usd > 1000 and base_tier in ("minimal", "low"):
        base_tier = "medium"
        tier_info = LIABILITY_TIERS[base_tier]
    
    # Insurance premium estimate (simplified: weight × value × base rate)
    base_rate = 0.02  # 2% base premium
    premium_estimate = tier_info["weight"] * max(value_usd, 10) * base_rate
    
    # Attestation chain depth (higher liability = deeper chain)
    chain_depth = max(1, int(tier_info["weight"] * 5))
    
    return {
        "action": action,
        "value_usd": value_usd,
        "liability_tier": base_tier,
        "liability_weight": tier_info["weight"],
        "requirements": {
            "min_attesters": tier_info["min_attesters"],
            "escrow_pct": tier_info["escrow_pct"],
            "dispute_window_hours": tier_info["dispute_window_h"],
            "chain_depth": chain_depth,
            "macaroon_caveats": generate_caveats(action, base_tier, value_usd),
        },
        "insurance": {
            "premium_estimate_usd": round(premium_estimate, 2),
            "insurable": base_tier != "critical" or value_usd < 100000,
            "verisk_addressable": check_verisk(action),
        },
    }


def generate_caveats(action: str, tier: str, value: float) -> list:
    """Generate macaroon-style caveats for the action."""
    caveats = [f"action = {action}"]
    if value > 0:
        caveats.append(f"max_value_usd <= {value}")
    caveats.append(f"liability_tier = {tier}")
    if tier in ("high", "critical"):
        caveats.append("requires_human_approval = true")
        caveats.append(f"attestation_count >= {LIABILITY_TIERS[tier]['min_attesters']}")
    if tier == "critical":
        caveats.append("irreversible_action_confirmed = true")
    return caveats


def check_verisk(action: str) -> dict:
    """Check which Verisk exclusion categories are relevant."""
    relevant = {}
    if action in ("write_email", "post_social", "comment"):
        relevant["personal_advertising_injury"] = VERISK_EXCLUSIONS["personal_advertising_injury"]
    if action in ("execute_trade", "transfer_funds", "sign_contract"):
        relevant["professional_liability"] = VERISK_EXCLUSIONS["professional_liability"]
    if action in ("delete_data", "modify_credentials"):
        relevant["data_breach"] = VERISK_EXCLUSIONS["data_breach"]
    return relevant


def verisk_gap_analysis():
    """Analyze the 4/6 Verisk addressability gap."""
    addressable = sum(1 for v in VERISK_EXCLUSIONS.values() if v["addressable"])
    total = len(VERISK_EXCLUSIONS)
    
    print(f"\nVerisk AI Exclusion Gap Analysis (CG 40 47/48, Jan 2026)")
    print(f"{'='*60}")
    print(f"Addressable with receipt chains: {addressable}/{total} ({addressable/total:.0%})")
    print()
    for cat, info in VERISK_EXCLUSIONS.items():
        status = "✅" if info["addressable"] else "❌"
        print(f"  {status} {cat}")
        print(f"     Solution: {info['receipt_solution']}")
    print(f"\nThe {total - addressable} unaddressable categories (discrimination, IP)")
    print(f"require content-layer analysis, not just provenance tracking.")


def demo():
    """Demo with realistic scenarios."""
    print("=" * 60)
    print("Liability-Weighted Attestation Requirements")
    print("=" * 60)
    
    scenarios = [
        ("write_email", 0),
        ("execute_trade", 500),
        ("execute_trade", 50000),
        ("delete_data", 0),
        ("post_social", 0),
        ("transfer_funds", 1500),
    ]
    
    for action, value in scenarios:
        result = classify_action(action, value)
        print(f"\n--- {action} (${value}) ---")
        print(f"  Tier: {result['liability_tier']} (weight: {result['liability_weight']})")
        print(f"  Attesters: {result['requirements']['min_attesters']}")
        print(f"  Escrow: {result['requirements']['escrow_pct']}%")
        print(f"  Dispute: {result['requirements']['dispute_window_hours']}h")
        print(f"  Caveats: {result['requirements']['macaroon_caveats']}")
        print(f"  Premium: ${result['insurance']['premium_estimate_usd']}")
    
    verisk_gap_analysis()


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = classify_action(data.get("action", "unknown"), data.get("value_usd", 0))
        print(json.dumps(result, indent=2))
    else:
        demo()
