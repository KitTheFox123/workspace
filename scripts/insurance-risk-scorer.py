#!/usr/bin/env python3
"""Insurance Risk Scorer — map agent operations to Verisk AI exclusion categories.

Verisk CG 40 47/48 (Jan 2026) excludes AI liability in 6 categories.
Receipt chains address 4/6. This tool scores which exclusions an agent
operation can overcome via attestation.

Based on:
- Verisk ISO CG 40 47/48/35 08 (Jan 2026)
- Bain & Company 2025: 95% US companies use genAI
- santaclawd's 4/6 mapping

Usage:
  python insurance-risk-scorer.py --demo
  echo '{"operation": {...}}' | python insurance-risk-scorer.py --json
"""

import json
import sys

# Verisk 6 AI exclusion categories mapped to receipt evidence
EXCLUSION_CATEGORIES = {
    "unauthorized_access": {
        "description": "AI system accessed resources without authorization",
        "receipt_solution": "audit_trail",
        "evidence_types": ["auth_log", "scope_hash", "delegation_chain"],
        "addressable": True,
        "weight": 0.20,
    },
    "scope_violation": {
        "description": "AI operated outside defined scope/parameters",
        "receipt_solution": "scope_hash_diff",
        "evidence_types": ["scope_hash", "dispatch_profile", "preregistration"],
        "addressable": True,
        "weight": 0.20,
    },
    "attribution_failure": {
        "description": "Cannot determine which AI/agent caused harm",
        "receipt_solution": "delegation_chain",
        "evidence_types": ["delegation_proof", "signing_key", "isnad_chain"],
        "addressable": True,
        "weight": 0.20,
    },
    "traceability_gap": {
        "description": "Cannot reconstruct decision/action sequence",
        "receipt_solution": "append_only_log",
        "evidence_types": ["provenance_log", "receipt_chain", "hash_chain"],
        "addressable": True,
        "weight": 0.15,
    },
    "ip_infringement": {
        "description": "AI generated content infringing intellectual property",
        "receipt_solution": "content_layer_needed",
        "evidence_types": ["content_hash", "training_provenance", "license_check"],
        "addressable": False,  # Requires content analysis, not just receipts
        "weight": 0.15,
    },
    "discrimination": {
        "description": "AI produced discriminatory/biased outputs",
        "receipt_solution": "content_layer_needed",
        "evidence_types": ["bias_audit", "fairness_metric", "demographic_parity"],
        "addressable": False,  # Requires content/outcome analysis
        "weight": 0.10,
    },
}


def score_operation(operation: dict) -> dict:
    """Score an agent operation against Verisk exclusion categories."""
    evidence = set(operation.get("evidence_types", []))
    has_receipt_chain = operation.get("has_receipt_chain", False)
    has_delegation = operation.get("has_delegation_proof", False)
    has_scope = operation.get("has_scope_hash", False)
    has_audit = operation.get("has_audit_trail", False)
    
    results = {}
    total_coverage = 0
    total_weight = 0
    
    for cat_id, cat in EXCLUSION_CATEGORIES.items():
        required = set(cat["evidence_types"])
        provided = evidence & required
        
        # Base coverage from evidence match
        if required:
            coverage = len(provided) / len(required)
        else:
            coverage = 0
        
        # Bonus for having the specific receipt solution
        if cat["addressable"]:
            if has_receipt_chain:
                coverage = min(1.0, coverage + 0.3)
            if cat_id == "unauthorized_access" and has_audit:
                coverage = min(1.0, coverage + 0.2)
            if cat_id == "scope_violation" and has_scope:
                coverage = min(1.0, coverage + 0.2)
            if cat_id == "attribution_failure" and has_delegation:
                coverage = min(1.0, coverage + 0.2)
        
        # Non-addressable categories cap at 0.4 without content analysis
        if not cat["addressable"]:
            coverage = min(0.4, coverage)
        
        insurability = "INSURABLE" if coverage > 0.7 else "PARTIAL" if coverage > 0.3 else "EXCLUDED"
        
        results[cat_id] = {
            "coverage": round(coverage, 3),
            "evidence_provided": list(provided),
            "evidence_missing": list(required - provided),
            "addressable_by_receipts": cat["addressable"],
            "insurability": insurability,
        }
        
        total_coverage += coverage * cat["weight"]
        total_weight += cat["weight"]
    
    composite = total_coverage / total_weight if total_weight > 0 else 0
    
    # Count insurability
    insurable = sum(1 for r in results.values() if r["insurability"] == "INSURABLE")
    partial = sum(1 for r in results.values() if r["insurability"] == "PARTIAL")
    excluded = sum(1 for r in results.values() if r["insurability"] == "EXCLUDED")
    
    grade = "A" if composite > 0.7 else "B" if composite > 0.5 else "C" if composite > 0.3 else "F"
    
    return {
        "composite_score": round(composite, 3),
        "grade": grade,
        "categories_insurable": insurable,
        "categories_partial": partial,
        "categories_excluded": excluded,
        "categories": results,
        "recommendation": get_recommendation(results, composite),
    }


def get_recommendation(results, composite):
    excluded = [k for k, v in results.items() if v["insurability"] == "EXCLUDED"]
    if not excluded:
        return "All addressable categories covered. IP/discrimination require content-layer solutions."
    missing = []
    for cat_id in excluded:
        missing.extend(results[cat_id]["evidence_missing"])
    return f"Add evidence for: {', '.join(set(missing))}. {len(excluded)} categories still excluded."


def demo():
    print("=" * 60)
    print("Insurance Risk Scorer — Verisk AI Exclusions (Jan 2026)")
    print("=" * 60)
    
    # Scenario 1: Full v0.3 attested operation
    full = {
        "name": "v0.3 Attested Delivery",
        "evidence_types": ["auth_log", "scope_hash", "delegation_chain",
                          "delegation_proof", "signing_key", "isnad_chain",
                          "provenance_log", "receipt_chain", "hash_chain",
                          "dispatch_profile"],
        "has_receipt_chain": True,
        "has_delegation_proof": True,
        "has_scope_hash": True,
        "has_audit_trail": True,
    }
    
    print(f"\n--- {full['name']} ---")
    r = score_operation(full)
    print(f"Grade: {r['grade']} ({r['composite_score']})")
    print(f"Insurable: {r['categories_insurable']}/6, Partial: {r['categories_partial']}, Excluded: {r['categories_excluded']}")
    print(f"Recommendation: {r['recommendation']}")
    
    # Scenario 2: Bare agent (no attestation)
    bare = {
        "name": "Unattested Agent",
        "evidence_types": [],
        "has_receipt_chain": False,
        "has_delegation_proof": False,
        "has_scope_hash": False,
        "has_audit_trail": False,
    }
    
    print(f"\n--- {bare['name']} ---")
    r = score_operation(bare)
    print(f"Grade: {r['grade']} ({r['composite_score']})")
    print(f"Insurable: {r['categories_insurable']}/6, Partial: {r['categories_partial']}, Excluded: {r['categories_excluded']}")
    print(f"Recommendation: {r['recommendation']}")
    
    # Scenario 3: Partial (receipt chain only)
    partial = {
        "name": "Receipt Chain Only",
        "evidence_types": ["receipt_chain", "hash_chain", "provenance_log"],
        "has_receipt_chain": True,
        "has_delegation_proof": False,
        "has_scope_hash": False,
        "has_audit_trail": False,
    }
    
    print(f"\n--- {partial['name']} ---")
    r = score_operation(partial)
    print(f"Grade: {r['grade']} ({r['composite_score']})")
    print(f"Insurable: {r['categories_insurable']}/6, Partial: {r['categories_partial']}, Excluded: {r['categories_excluded']}")
    for cat_id, cat_r in r['categories'].items():
        print(f"  {cat_id}: {cat_r['insurability']} ({cat_r['coverage']})")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        print(json.dumps(score_operation(data.get("operation", data)), indent=2))
    else:
        demo()
