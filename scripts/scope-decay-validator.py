#!/usr/bin/env python3
"""
scope-decay-validator.py — Validate delegation_proof scope with TTL decay.

From santaclawd (Feb 25): "delegation_proof sets scope at spawn. but scope needs TTL too."
And the consent gap: "read email" ≠ "read THIS email" — granular scoping needed.

Persistent delegation = permanent authority (dangerous).
Scoped delegation = time-bound + action-bound (safe).

Like Google's granular OAuth (Dec 2025): per-scope consent, not all-or-nothing.
"""

import json
import sys
from datetime import datetime, timezone, timedelta


# Scope categories with default TTLs
SCOPE_DEFAULTS = {
    # High-risk: short TTL
    "send_payment": {"ttl_hours": 1, "risk": "critical"},
    "sign_attestation": {"ttl_hours": 4, "risk": "high"},
    "send_email": {"ttl_hours": 8, "risk": "high"},
    "post_public": {"ttl_hours": 12, "risk": "medium"},
    
    # Medium-risk: moderate TTL
    "read_email": {"ttl_hours": 24, "risk": "medium"},
    "search_web": {"ttl_hours": 48, "risk": "low"},
    "read_feed": {"ttl_hours": 48, "risk": "low"},
    
    # Low-risk: long TTL
    "read_public": {"ttl_hours": 168, "risk": "minimal"},  # 7 days
    "log_activity": {"ttl_hours": 720, "risk": "minimal"},  # 30 days
}


def validate_delegation(proof: dict) -> dict:
    """Validate a delegation_proof's scope against TTL constraints."""
    now = datetime.now(timezone.utc)
    
    issued_at = datetime.fromisoformat(proof.get("issued_at", now.isoformat()))
    scopes = proof.get("scopes", [])
    delegator = proof.get("delegator", "unknown")
    delegate = proof.get("delegate", "unknown")
    
    results = []
    overall_valid = True
    warnings = []
    
    for scope_entry in scopes:
        if isinstance(scope_entry, str):
            scope_name = scope_entry
            custom_ttl = None
        else:
            scope_name = scope_entry.get("name", "unknown")
            custom_ttl = scope_entry.get("ttl_hours")
        
        defaults = SCOPE_DEFAULTS.get(scope_name, {"ttl_hours": 24, "risk": "unknown"})
        ttl_hours = custom_ttl or defaults["ttl_hours"]
        risk = defaults["risk"]
        
        expires_at = issued_at + timedelta(hours=ttl_hours)
        expired = now > expires_at
        remaining = max((expires_at - now).total_seconds() / 3600, 0)
        
        # Warnings
        scope_warnings = []
        if custom_ttl and custom_ttl > defaults["ttl_hours"] * 2:
            scope_warnings.append(f"custom TTL {custom_ttl}h exceeds 2x default ({defaults['ttl_hours']}h)")
        if risk in ("critical", "high") and not expired and remaining > 24:
            scope_warnings.append(f"high-risk scope with {remaining:.0f}h remaining — consider shorter TTL")
        
        if expired:
            overall_valid = False
        
        results.append({
            "scope": scope_name,
            "risk": risk,
            "ttl_hours": ttl_hours,
            "expired": expired,
            "remaining_hours": round(remaining, 1),
            "warnings": scope_warnings,
        })
        warnings.extend(scope_warnings)
    
    # Mosaic check: many low-risk scopes combined = medium risk
    low_risk_count = sum(1 for r in results if r["risk"] in ("low", "minimal") and not r["expired"])
    if low_risk_count >= 5:
        warnings.append(f"mosaic risk: {low_risk_count} low-risk scopes combined may reveal sensitive patterns")
    
    return {
        "delegator": delegator,
        "delegate": delegate,
        "issued_at": issued_at.isoformat(),
        "all_valid": overall_valid,
        "scopes": results,
        "warnings": warnings,
        "checked_at": now.isoformat(),
    }


def demo():
    """Demo with example delegation proofs."""
    print("=== Scope Decay Validator ===\n")
    
    now = datetime.now(timezone.utc)
    
    # Fresh delegation
    fresh = validate_delegation({
        "delegator": "ilya",
        "delegate": "kit_fox",
        "issued_at": (now - timedelta(hours=2)).isoformat(),
        "scopes": ["read_email", "search_web", "post_public"],
    })
    print(f"  Fresh delegation ({fresh['delegator']} → {fresh['delegate']}):")
    print(f"    Valid: {fresh['all_valid']}")
    for s in fresh["scopes"]:
        status = "✅" if not s["expired"] else "❌"
        print(f"    {status} {s['scope']} ({s['risk']}) — {s['remaining_hours']}h remaining")
    print()
    
    # Expired high-risk
    expired = validate_delegation({
        "delegator": "ilya",
        "delegate": "kit_fox",
        "issued_at": (now - timedelta(hours=10)).isoformat(),
        "scopes": ["send_payment", "sign_attestation", "read_public"],
    })
    print(f"  Expired high-risk ({expired['delegator']} → {expired['delegate']}):")
    print(f"    Valid: {expired['all_valid']}")
    for s in expired["scopes"]:
        status = "✅" if not s["expired"] else "❌"
        print(f"    {status} {s['scope']} ({s['risk']}) — {s['remaining_hours']}h remaining")
    print()
    
    # Mosaic risk: many low-risk scopes
    mosaic = validate_delegation({
        "delegator": "operator",
        "delegate": "sub_agent",
        "issued_at": (now - timedelta(hours=1)).isoformat(),
        "scopes": ["read_public", "read_feed", "search_web", "log_activity",
                    {"name": "read_email", "ttl_hours": 48},
                    {"name": "read_public", "ttl_hours": 168}],
    })
    print(f"  Mosaic risk ({mosaic['delegator']} → {mosaic['delegate']}):")
    print(f"    Valid: {mosaic['all_valid']}")
    if mosaic["warnings"]:
        for w in mosaic["warnings"]:
            print(f"    ⚠️  {w}")
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        proof = json.loads(sys.stdin.read())
        result = validate_delegation(proof)
        print(json.dumps(result, indent=2))
    else:
        demo()
