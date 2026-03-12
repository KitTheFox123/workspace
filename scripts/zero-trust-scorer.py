#!/usr/bin/env python3
"""
Zero Trust Scorer — Evaluate agent architecture against NIST 800-207.

Seven core principles mapped to agent infrastructure:
1. All data sources/services = resources
2. All communication secured regardless of location
3. Per-request access based on identity, posture, context
4. Least privilege enforced dynamically
5. Continuous diagnostics and threat detection
6. Authentication/authorization dynamic and strictly enforced
7. Collect info about asset state, infra, comms → improve security posture

Usage:
    python3 zero-trust-scorer.py              # Demo
    echo '{"agent": {...}}' | python3 zero-trust-scorer.py --stdin
"""

import json, sys

NIST_PRINCIPLES = {
    "p1_resources": {
        "name": "Everything is a Resource",
        "checks": ["api_keys_scoped", "inboxes_isolated", "memory_separated"],
        "weight": 0.12,
    },
    "p2_secure_comms": {
        "name": "Secure All Communication",
        "checks": ["tls_enforced", "dkim_signing", "auth_headers"],
        "weight": 0.12,
    },
    "p3_per_request": {
        "name": "Per-Request Access",
        "checks": ["scope_hash_per_action", "delegation_proof", "session_scoped"],
        "weight": 0.18,
    },
    "p4_least_privilege": {
        "name": "Least Privilege",
        "checks": ["read_only_default", "write_requires_attestation", "no_master_keys"],
        "weight": 0.18,
    },
    "p5_continuous_monitoring": {
        "name": "Continuous Diagnostics",
        "checks": ["heartbeat_monitoring", "cusum_drift_detection", "anomaly_scoring"],
        "weight": 0.15,
    },
    "p6_dynamic_auth": {
        "name": "Dynamic Authentication",
        "checks": ["trust_score_recalculated", "beta_reputation", "receipt_chain_verified"],
        "weight": 0.15,
    },
    "p7_telemetry": {
        "name": "Collect & Improve",
        "checks": ["provenance_logging", "null_receipt_tracking", "behavioral_baselines"],
        "weight": 0.10,
    },
}


def score_agent(config: dict) -> dict:
    """Score agent against NIST 800-207 zero trust principles."""
    checks_present = set(config.get("checks", []))
    
    principle_scores = {}
    for pid, p in NIST_PRINCIPLES.items():
        present = [c for c in p["checks"] if c in checks_present]
        coverage = len(present) / len(p["checks"])
        principle_scores[pid] = {
            "name": p["name"],
            "coverage": round(coverage, 3),
            "present": present,
            "missing": [c for c in p["checks"] if c not in checks_present],
            "pass": coverage >= 0.67,
        }
    
    composite = sum(
        principle_scores[p]["coverage"] * NIST_PRINCIPLES[p]["weight"]
        for p in NIST_PRINCIPLES
    )
    
    passed = sum(1 for p in principle_scores.values() if p["pass"])
    
    if composite >= 0.8: grade = "A"
    elif composite >= 0.6: grade = "B"
    elif composite >= 0.4: grade = "C"
    elif composite >= 0.2: grade = "D"
    else: grade = "F"
    
    # Turing vs Zero Trust comparison
    philosophy = (
        "Turing test: trust if convincing (perimeter model). "
        "Zero trust: verify every action (NIST 800-207). "
        "Receipts = per-action verification. Heartbeats = continuous re-evaluation."
    )
    
    return {
        "composite_score": round(composite, 3),
        "grade": grade,
        "principles_passed": passed,
        "total_principles": len(NIST_PRINCIPLES),
        "zero_trust_compliant": passed >= 5,
        "principles": principle_scores,
        "philosophy": philosophy,
    }


def demo():
    print("=== Zero Trust Scorer (NIST 800-207) ===\n")
    
    # Kit's architecture
    kit = {"checks": [
        "api_keys_scoped", "inboxes_isolated", "memory_separated",
        "tls_enforced", "dkim_signing", "auth_headers",
        "scope_hash_per_action", "delegation_proof", "session_scoped",
        "read_only_default", "write_requires_attestation",
        "heartbeat_monitoring", "cusum_drift_detection", "anomaly_scoring",
        "trust_score_recalculated", "beta_reputation", "receipt_chain_verified",
        "provenance_logging", "null_receipt_tracking", "behavioral_baselines",
    ]}
    
    print("Kit (governance stack):")
    r = score_agent(kit)
    print(f"  Score: {r['composite_score']} ({r['grade']})")
    print(f"  Principles: {r['principles_passed']}/{r['total_principles']}")
    print(f"  Zero trust: {r['zero_trust_compliant']}")
    
    # Generic bot
    generic = {"checks": ["tls_enforced", "auth_headers", "session_scoped"]}
    
    print("\nGeneric bot (TLS + auth only):")
    r = score_agent(generic)
    print(f"  Score: {r['composite_score']} ({r['grade']})")
    print(f"  Principles: {r['principles_passed']}/{r['total_principles']}")
    for pid, p in r["principles"].items():
        if not p["pass"]:
            print(f"  ❌ {p['name']}: missing {p['missing']}")
    
    # Perimeter model (Turing-style trust)
    perimeter = {"checks": ["tls_enforced", "auth_headers", "api_keys_scoped"]}
    
    print("\nPerimeter model (trust once, access always):")
    r = score_agent(perimeter)
    print(f"  Score: {r['composite_score']} ({r['grade']})")
    print(f"  Philosophy: {r['philosophy']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = score_agent(data)
        print(json.dumps(result, indent=2))
    else:
        demo()
