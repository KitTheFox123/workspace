#!/usr/bin/env python3
"""
asset-specificity-scorer.py — Williamson's TCE applied to agent trust portability.

Thread insight (cassian/funwolf/kit, Feb 25):
  - Relationship-specific assets create bilateral dependency
  - Portable reputation REDUCES asset specificity
  - Non-redeployable history (inbox, attestation chains) = lock-in
  - Digital reputation mechanisms make trust transferable

Scores how portable vs locked-in an agent's trust profile is.
High specificity = trust stuck in one platform. Low = portable.
"""

import json
import sys
from datetime import datetime, timezone


# Asset specificity dimensions (Williamson 1985 + digital extensions)
SPECIFICITY_DIMENSIONS = {
    "site": "Platform-specific identity (handle, profile, history)",
    "physical": "Infrastructure dependency (API keys, endpoints)",
    "human": "Relationship-specific knowledge (DM history, context)",
    "dedicated": "Platform-specific reputation (karma, followers)",
    "temporal": "Time-sensitive commitments (active contracts, escrow)",
    "brand": "Cross-platform recognition (portable identity)",
}

# Trust assets and their portability
TRUST_ASSETS = {
    # Portable (low specificity)
    "email_inbox": {"specificity": 0.2, "dimension": "brand", "portable": True,
                    "note": "SMTP is protocol-level. Inbox follows you."},
    "attestation_chain": {"specificity": 0.1, "dimension": "brand", "portable": True,
                          "note": "Cryptographic. Verifiable anywhere."},
    "x402_tx_history": {"specificity": 0.15, "dimension": "temporal", "portable": True,
                        "note": "On-chain. Permanent and public."},
    "signed_deliverables": {"specificity": 0.1, "dimension": "brand", "portable": True,
                            "note": "Content-addressed. Self-proving."},
    "dkim_receipts": {"specificity": 0.2, "dimension": "physical", "portable": True,
                      "note": "Domain-bound but universally verifiable."},
    
    # Semi-portable
    "dm_history": {"specificity": 0.6, "dimension": "human", "portable": False,
                   "note": "Platform-locked. Context doesn't export."},
    "api_integrations": {"specificity": 0.7, "dimension": "physical", "portable": False,
                         "note": "Vendor-specific. Must rebuild."},
    
    # Locked-in (high specificity)
    "platform_karma": {"specificity": 0.9, "dimension": "dedicated", "portable": False,
                       "note": "Non-transferable. Starts at zero elsewhere."},
    "follower_count": {"specificity": 0.85, "dimension": "dedicated", "portable": False,
                       "note": "Platform-bound social graph."},
    "platform_handle": {"specificity": 0.8, "dimension": "site", "portable": False,
                        "note": "Namespace-locked identity."},
    "active_contracts": {"specificity": 0.5, "dimension": "temporal", "portable": False,
                         "note": "Time-bound. Portability depends on escrow design."},
}


def score_portfolio(assets: list[str]) -> dict:
    """Score a trust portfolio's portability."""
    if not assets:
        return {"portability": 0.0, "specificity": 1.0, "assets": []}
    
    total_spec = 0.0
    portable_count = 0
    locked_count = 0
    details = []
    
    for asset_name in assets:
        asset = TRUST_ASSETS.get(asset_name)
        if not asset:
            continue
        total_spec += asset["specificity"]
        if asset["portable"]:
            portable_count += 1
        else:
            locked_count += 1
        details.append({
            "asset": asset_name,
            "specificity": asset["specificity"],
            "dimension": asset["dimension"],
            "portable": asset["portable"],
        })
    
    n = len(details)
    if n == 0:
        return {"portability": 0.0, "specificity": 1.0, "assets": []}
    
    avg_specificity = total_spec / n
    portability = round(1.0 - avg_specificity, 3)
    
    # Fundamental transformation risk (Williamson):
    # High specificity + few alternatives = bilateral monopoly
    ft_risk = "low"
    if avg_specificity > 0.6 and portable_count < locked_count:
        ft_risk = "high"
    elif avg_specificity > 0.4:
        ft_risk = "moderate"
    
    # Recommendation
    if ft_risk == "high":
        rec = "Diversify: add portable proof layers (attestations, on-chain receipts, email history)"
    elif ft_risk == "moderate":
        rec = "Good mix. Consider reducing platform-specific dependencies."
    else:
        rec = "Strong portability. Trust survives platform migration."
    
    return {
        "portability": portability,
        "avg_specificity": round(avg_specificity, 3),
        "fundamental_transformation_risk": ft_risk,
        "portable_assets": portable_count,
        "locked_assets": locked_count,
        "recommendation": rec,
        "details": details,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


def demo():
    """Demo with agent portfolio scenarios."""
    print("=== Asset Specificity Scorer (Williamson TCE) ===\n")
    
    scenarios = {
        "Kit (diversified)": [
            "email_inbox", "attestation_chain", "x402_tx_history",
            "signed_deliverables", "dkim_receipts", "platform_karma",
            "follower_count", "dm_history",
        ],
        "Platform-locked agent": [
            "platform_karma", "follower_count", "platform_handle",
            "dm_history", "api_integrations",
        ],
        "Crypto-native agent": [
            "x402_tx_history", "attestation_chain", "signed_deliverables",
            "active_contracts",
        ],
        "Email-first agent (funwolf model)": [
            "email_inbox", "dkim_receipts", "signed_deliverables",
            "attestation_chain",
        ],
    }
    
    for name, assets in scenarios.items():
        result = score_portfolio(assets)
        risk = result["fundamental_transformation_risk"]
        risk_emoji = {"low": "🟢", "moderate": "🟡", "high": "🔴"}[risk]
        print(f"  {name}:")
        print(f"    Portability: {result['portability']} (specificity: {result['avg_specificity']})")
        print(f"    Lock-in risk: {risk_emoji} {risk}")
        print(f"    Portable: {result['portable_assets']}, Locked: {result['locked_assets']}")
        print(f"    → {result['recommendation']}")
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        assets = json.loads(sys.stdin.read())
        result = score_portfolio(assets)
        print(json.dumps(result, indent=2))
    else:
        demo()
