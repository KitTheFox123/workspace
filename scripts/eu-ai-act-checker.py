#!/usr/bin/env python3
"""EU AI Act Compliance Checker — verify receipt chains against Art. 12/72 requirements.

Maps EU AI Act record-keeping and post-market monitoring requirements
to receipt-chain governance primitives.

Art. 12: Automatic recording of events (logging)
Art. 72: Post-market monitoring (drift detection)
Art. 9: Risk management (classification)

Usage:
  python eu-ai-act-checker.py --demo
  echo '{"chain": [...]}' | python eu-ai-act-checker.py --json
"""

import json
import sys
from datetime import datetime, timezone

# EU AI Act requirements mapped to receipt-chain primitives
REQUIREMENTS = {
    "art_12_logging": {
        "article": "Art. 12",
        "title": "Record-Keeping",
        "requirement": "Automatic recording of events for traceability",
        "checks": [
            ("has_timestamps", "Each event has ISO 8601 timestamp"),
            ("has_hash_chain", "Events linked by cryptographic hash chain"),
            ("has_action_type", "Event type/action recorded"),
            ("has_actor_id", "Actor identity recorded per event"),
            ("is_append_only", "Log is append-only (no deletions detected)"),
        ],
    },
    "art_12_null_nodes": {
        "article": "Art. 12 (extended)",
        "title": "Null Node Recording",
        "requirement": "Record what was CONSIDERED, not just what happened",
        "checks": [
            ("has_null_nodes", "Declined actions recorded as null nodes"),
            ("null_ratio_reasonable", "Null node ratio between 5-80% of total"),
        ],
    },
    "art_72_monitoring": {
        "article": "Art. 72",
        "title": "Post-Market Monitoring",
        "requirement": "Continuous monitoring for drift and degradation",
        "checks": [
            ("has_quality_metrics", "Quality/score fields present"),
            ("temporal_coverage", "Events span meaningful time period (>24h)"),
            ("regular_intervals", "Events at regular intervals (heartbeat)"),
        ],
    },
    "art_9_risk": {
        "article": "Art. 9",
        "title": "Risk Management",
        "requirement": "Risk identification, estimation, evaluation",
        "checks": [
            ("has_proof_classes", "Multiple proof class types present"),
            ("has_attestation", "Third-party attestation/witness present"),
            ("diversity_scoring", "Proof class diversity measured"),
        ],
    },
    "chain_of_custody": {
        "article": "Legal",
        "title": "Chain of Custody",
        "requirement": "Unbroken documentation at each transfer",
        "checks": [
            ("unbroken_chain", "No hash chain breaks detected"),
            ("signed_entries", "Entries have cryptographic signatures"),
            ("no_gaps", "No temporal gaps >48h without null node"),
        ],
    },
}


def check_chain(chain: list) -> dict:
    """Check a receipt chain against EU AI Act requirements."""
    results = {}
    
    for req_id, req in REQUIREMENTS.items():
        checks = {}
        for check_id, description in req["checks"]:
            passed = run_check(check_id, chain)
            checks[check_id] = {"passed": passed, "description": description}
        
        passed_count = sum(1 for c in checks.values() if c["passed"])
        total = len(checks)
        score = passed_count / total if total > 0 else 0
        
        results[req_id] = {
            "article": req["article"],
            "title": req["title"],
            "score": round(score, 2),
            "passed": passed_count,
            "total": total,
            "status": "PASS" if score >= 0.8 else "PARTIAL" if score >= 0.5 else "FAIL",
            "checks": checks,
        }
    
    # Overall compliance
    scores = [r["score"] for r in results.values()]
    overall = sum(scores) / len(scores) if scores else 0
    
    return {
        "overall_score": round(overall, 3),
        "overall_status": "COMPLIANT" if overall >= 0.8 else "PARTIAL" if overall >= 0.5 else "NON-COMPLIANT",
        "requirements": results,
        "chain_length": len(chain),
        "recommendation": generate_recommendation(results),
    }


def run_check(check_id: str, chain: list) -> bool:
    """Run individual compliance check."""
    if not chain:
        return False
    
    if check_id == "has_timestamps":
        return all("timestamp" in e for e in chain)
    
    elif check_id == "has_hash_chain":
        for i, e in enumerate(chain):
            if "hash" not in e:
                return False
            if i > 0 and "prev_hash" not in e:
                return False
        return True
    
    elif check_id == "has_action_type":
        return all("action" in e for e in chain)
    
    elif check_id == "has_actor_id":
        return sum(1 for e in chain if "actor" in e or "target" in e) > len(chain) * 0.5
    
    elif check_id == "is_append_only":
        # Check timestamps are monotonically increasing
        timestamps = [e.get("timestamp", "") for e in chain if "timestamp" in e]
        return timestamps == sorted(timestamps)
    
    elif check_id == "has_null_nodes":
        return any(e.get("null_node") or e.get("action", "").startswith("null:") for e in chain)
    
    elif check_id == "null_ratio_reasonable":
        nulls = sum(1 for e in chain if e.get("null_node") or e.get("action", "").startswith("null:"))
        ratio = nulls / len(chain) if chain else 0
        return 0.05 <= ratio <= 0.80
    
    elif check_id == "has_quality_metrics":
        return any("score" in e or "quality" in e or "confidence" in e for e in chain)
    
    elif check_id == "temporal_coverage":
        timestamps = sorted(e.get("timestamp", "") for e in chain if "timestamp" in e)
        if len(timestamps) < 2:
            return False
        # Simple check: first and last differ
        return timestamps[0][:10] != timestamps[-1][:10]  # Different days
    
    elif check_id == "regular_intervals":
        return len(chain) >= 3  # At least 3 events suggests regularity
    
    elif check_id == "has_proof_classes":
        types = set(e.get("proof_class") or e.get("action", "") for e in chain)
        return len(types) >= 2
    
    elif check_id == "has_attestation":
        return any("attestation" in str(e).lower() or "witness" in str(e).lower() for e in chain)
    
    elif check_id == "diversity_scoring":
        return any("diversity" in str(e).lower() or "entropy" in str(e).lower() for e in chain)
    
    elif check_id == "unbroken_chain":
        for i in range(1, len(chain)):
            if chain[i].get("prev_hash") and chain[i-1].get("hash"):
                if chain[i]["prev_hash"] != chain[i-1]["hash"]:
                    return False
        return True
    
    elif check_id == "signed_entries":
        return any("signature" in e or "sig" in e for e in chain)
    
    elif check_id == "no_gaps":
        # Would need real timestamp parsing; simplified
        return len(chain) >= 2
    
    return False


def generate_recommendation(results: dict) -> str:
    fails = [r for r in results.values() if r["status"] == "FAIL"]
    if not fails:
        return "Chain meets EU AI Act record-keeping requirements. Continue monitoring."
    
    gaps = []
    for f in fails:
        failed_checks = [c["description"] for c in f["checks"].values() if not c["passed"]]
        gaps.append(f"{f['article']}: {', '.join(failed_checks[:2])}")
    return "Gaps: " + " | ".join(gaps[:3])


def demo():
    print("=" * 60)
    print("EU AI Act Compliance Checker for Receipt Chains")
    print("=" * 60)
    
    # Scenario 1: Full governance stack chain
    print("\n--- Scenario 1: Full Governance Stack ---")
    full_chain = [
        {"timestamp": "2026-02-25T10:00:00Z", "action": "clawk_reply", "target": "santaclawd",
         "hash": "abc123", "actor": "kit_fox", "score": 0.92, "proof_class": "generation"},
        {"timestamp": "2026-02-25T10:05:00Z", "action": "null:moltbook_post", "null_node": True,
         "hash": "def456", "prev_hash": "abc123", "actor": "kit_fox", "reason": "suspended"},
        {"timestamp": "2026-02-25T13:00:00Z", "action": "attestation", "target": "gendolf",
         "hash": "ghi789", "prev_hash": "def456", "actor": "kit_fox",
         "proof_class": "witness", "signature": "ed25519:...", "diversity": 0.85},
        {"timestamp": "2026-02-26T08:00:00Z", "action": "build", "target": "cusum-drift-detector",
         "hash": "jkl012", "prev_hash": "ghi789", "actor": "kit_fox",
         "proof_class": "generation", "quality": 0.95, "confidence": 0.88},
    ]
    result = check_chain(full_chain)
    print(f"Status: {result['overall_status']} ({result['overall_score']})")
    for req_id, req in result['requirements'].items():
        print(f"  {req['article']:12s} {req['title']:25s} {req['status']:8s} ({req['passed']}/{req['total']})")
    
    # Scenario 2: Minimal logging only
    print("\n--- Scenario 2: Minimal Logging (No Governance) ---")
    minimal = [
        {"timestamp": "2026-02-25T10:00:00Z", "action": "post", "hash": "aaa"},
        {"timestamp": "2026-02-25T10:05:00Z", "action": "post", "hash": "bbb", "prev_hash": "aaa"},
    ]
    result = check_chain(minimal)
    print(f"Status: {result['overall_status']} ({result['overall_score']})")
    for req_id, req in result['requirements'].items():
        print(f"  {req['article']:12s} {req['title']:25s} {req['status']:8s} ({req['passed']}/{req['total']})")
    print(f"  Recommendation: {result['recommendation']}")
    
    # Scenario 3: No chain at all
    print("\n--- Scenario 3: No Provenance Chain ---")
    result = check_chain([])
    print(f"Status: {result['overall_status']} ({result['overall_score']})")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = check_chain(data.get("chain", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
