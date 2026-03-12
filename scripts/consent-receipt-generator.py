#!/usr/bin/env python3
"""
Consent Receipt Generator — Kantara v1.1 spec for agent data access.

Kantara Initiative Consent Receipt Specification v1.1: standard JSON record of
authority granted by a PII Principal to a PII Controller. Maps directly to
agent-to-agent and agent-to-human data access patterns.

GDPR Art. 7(1): "the controller shall be able to demonstrate that the data subject
has consented." This IS that demonstration.

Usage:
    python3 consent-receipt-generator.py              # Demo
    echo '{"principal": "...", ...}' | python3 consent-receipt-generator.py --stdin
"""

import json, sys, hashlib, time
from datetime import datetime, timezone


def generate_receipt(
    principal_id: str,      # Data subject (human or agent granting access)
    controller_id: str,     # Agent accessing data
    purposes: list[str],    # Why data is being accessed
    data_categories: list[str],  # What data
    scope: str,             # Access scope (read/write/delegate)
    duration_seconds: int = 3600,  # How long consent is valid
    third_parties: list[str] = None,  # Who else gets data
    legal_basis: str = "consent",  # GDPR basis
) -> dict:
    """Generate a Kantara-style consent receipt for agent data access."""
    
    now = datetime.now(timezone.utc)
    
    receipt = {
        "version": "kit-cr-1.0",
        "jurisdiction": "GDPR",
        "timestamp": now.isoformat(),
        "collection_method": "agent_api",
        
        # Principal (data subject)
        "principal": {
            "id": principal_id,
            "type": "agent" if "@" not in principal_id else "email_identity",
        },
        
        # Controller (agent accessing data)
        "controller": {
            "id": controller_id,
            "type": "agent",
            "contact": controller_id if "@" in controller_id else f"{controller_id}@agentmail.to",
        },
        
        # Purpose specification (Kantara required)
        "purposes": [
            {
                "purpose": p,
                "primary": i == 0,
                "termination": f"{duration_seconds}s",
                "third_party_disclosure": bool(third_parties),
            }
            for i, p in enumerate(purposes)
        ],
        
        # Data categories (Kantara: "sensitive" flag)
        "pii_categories": [
            {
                "category": cat,
                "sensitive": _is_sensitive(cat),
            }
            for cat in data_categories
        ],
        
        # Access scope (agent-specific extension)
        "scope": {
            "access_level": scope,
            "delegation_allowed": scope == "delegate",
            "expiry": datetime.fromtimestamp(
                now.timestamp() + duration_seconds, tz=timezone.utc
            ).isoformat(),
        },
        
        # Legal basis
        "legal_basis": legal_basis,
        
        # Third parties
        "third_parties": third_parties or [],
        
        # Integrity
        "receipt_hash": None,  # filled below
    }
    
    # Hash for integrity
    content = json.dumps(receipt, sort_keys=True)
    receipt["receipt_hash"] = hashlib.sha256(content.encode()).hexdigest()[:16]
    
    return receipt


def _is_sensitive(category: str) -> bool:
    """GDPR Art. 9 special categories."""
    sensitive_keywords = [
        "health", "biometric", "genetic", "racial", "ethnic",
        "political", "religious", "sexual", "trade_union",
        "criminal", "location", "financial",
    ]
    return any(kw in category.lower() for kw in sensitive_keywords)


def verify_receipt(receipt: dict) -> dict:
    """Verify a consent receipt's integrity and validity."""
    issues = []
    
    # Required fields (Kantara spec)
    required = ["version", "timestamp", "principal", "controller", "purposes", "pii_categories"]
    for field in required:
        if field not in receipt:
            issues.append(f"Missing required field: {field}")
    
    # Purpose must exist
    if not receipt.get("purposes"):
        issues.append("No purposes specified (Kantara requires at least one)")
    
    # Expiry check
    scope = receipt.get("scope", {})
    if "expiry" in scope:
        try:
            expiry = datetime.fromisoformat(scope["expiry"])
            if expiry < datetime.now(timezone.utc):
                issues.append("Consent has EXPIRED")
        except (ValueError, TypeError):
            issues.append("Invalid expiry format")
    
    # Sensitive data check
    sensitive = [c for c in receipt.get("pii_categories", []) if c.get("sensitive")]
    if sensitive and receipt.get("legal_basis") == "legitimate_interest":
        issues.append("GDPR Art. 9: sensitive data requires explicit consent, not legitimate interest")
    
    # Third party disclosure
    if any(p.get("third_party_disclosure") for p in receipt.get("purposes", [])):
        if not receipt.get("third_parties"):
            issues.append("Third party disclosure flagged but no parties listed")
    
    valid = len(issues) == 0
    return {
        "valid": valid,
        "issues": issues,
        "grade": "PASS" if valid else ("WARN" if len(issues) <= 2 else "FAIL"),
        "sensitive_data": len(sensitive) > 0,
        "gdpr_compliant": valid and receipt.get("legal_basis") in ["consent", "contract"],
    }


def demo():
    print("=== Consent Receipt Generator (Kantara v1.1) ===\n")
    
    # Agent accessing another agent's data
    r1 = generate_receipt(
        principal_id="bro_agent",
        controller_id="kit_fox@agentmail.to",
        purposes=["attestation_verification", "trust_scoring"],
        data_categories=["receipt_chain", "public_profile"],
        scope="read",
        duration_seconds=86400,
    )
    print("Agent-to-agent data access:")
    print(f"  Principal: {r1['principal']['id']}")
    print(f"  Controller: {r1['controller']['id']}")
    print(f"  Purposes: {[p['purpose'] for p in r1['purposes']]}")
    print(f"  Scope: {r1['scope']['access_level']}")
    print(f"  Hash: {r1['receipt_hash']}")
    
    v1 = verify_receipt(r1)
    print(f"  Valid: {v1['valid']} ({v1['grade']})")
    
    # Agent accessing sensitive data (should flag)
    r2 = generate_receipt(
        principal_id="human_user@email.com",
        controller_id="health_bot",
        purposes=["health_monitoring"],
        data_categories=["health_records", "biometric_data", "location"],
        scope="read",
        legal_basis="legitimate_interest",  # WRONG for sensitive data
    )
    print("\nSensitive data access (bad legal basis):")
    v2 = verify_receipt(r2)
    print(f"  Valid: {v2['valid']} ({v2['grade']})")
    print(f"  Issues: {v2['issues']}")
    print(f"  GDPR compliant: {v2['gdpr_compliant']}")
    
    # Expired consent
    r3 = generate_receipt(
        principal_id="agent_a",
        controller_id="agent_b",
        purposes=["data_sync"],
        data_categories=["messages"],
        scope="read",
        duration_seconds=-3600,  # already expired
    )
    print("\nExpired consent:")
    v3 = verify_receipt(r3)
    print(f"  Valid: {v3['valid']} ({v3['grade']})")
    print(f"  Issues: {v3['issues']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        receipt = generate_receipt(**data)
        verification = verify_receipt(receipt)
        print(json.dumps({"receipt": receipt, "verification": verification}, indent=2))
    else:
        demo()
