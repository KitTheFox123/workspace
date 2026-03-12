#!/usr/bin/env python3
"""Insurance Readiness Scorer — score agent receipt chains for insurability.

Maps Verisk's 6 AI exclusion categories (CG 35 08, CG 40 47/48) to
receipt chain evidence, scoring what's documentable vs what's not.

Based on:
- Verisk Jan 2026: 6 GL exclusion endorsements for gen AI
- NIST CAISI RFI (March 9 deadline): agent security considerations
- santaclawd: "4/6 categories solvable with receipt chains"
- Cyber insurance precedent: exclusion→data→pricing→market

Usage:
  python insurance-readiness-scorer.py --demo
  echo '{"receipts": [...]}' | python insurance-readiness-scorer.py --json
"""

import json
import sys
from datetime import datetime

# Verisk exclusion categories mapped to receipt evidence requirements
EXCLUSION_CATEGORIES = {
    "bodily_injury_property_damage": {
        "verisk_form": "CG 40 47/48",
        "description": "AI-caused bodily injury or property damage",
        "evidence_needed": ["delegation_chain", "scope_attestation", "execution_log"],
        "receipt_solvable": True,
        "explanation": "Receipt chain proves scope was bounded and who authorized the action",
    },
    "advertising_injury": {
        "verisk_form": "CG 40 47/48",
        "description": "AI-generated advertising content causing harm",
        "evidence_needed": ["generation_attestation", "content_hash", "approval_chain"],
        "receipt_solvable": True,
        "explanation": "Generation sig + approval chain documents who reviewed what",
    },
    "data_breach": {
        "verisk_form": "CG 40 47/48",
        "description": "AI system causing data breach or privacy violation",
        "evidence_needed": ["access_log", "scope_attestation", "transport_proof"],
        "receipt_solvable": True,
        "explanation": "DKIM + transport proofs document data flow boundaries",
    },
    "professional_liability": {
        "verisk_form": "CG 35 08",
        "description": "AI-generated professional advice causing loss",
        "evidence_needed": ["generation_attestation", "qualification_proof", "delegation_chain"],
        "receipt_solvable": True,
        "explanation": "Receipt chain documents who generated, who delegated, who's qualified",
    },
    "ip_infringement": {
        "verisk_form": "CG 35 08",
        "description": "AI output infringing copyright or trademark",
        "evidence_needed": ["training_data_proof", "generation_attestation", "originality_check"],
        "receipt_solvable": False,
        "explanation": "Can document generation but can't prove non-infringement — content-layer problem",
    },
    "discrimination": {
        "verisk_form": "CG 35 08",
        "description": "AI system producing discriminatory outputs",
        "evidence_needed": ["model_attestation", "bias_audit", "demographic_analysis"],
        "receipt_solvable": False,
        "explanation": "Can document process but can't prove absence of bias — requires separate audit",
    },
}

# Evidence types and their receipt chain mappings
EVIDENCE_TO_RECEIPT = {
    "delegation_chain": {"proof_class": "witness", "receipt_field": "delegation_proof"},
    "scope_attestation": {"proof_class": "generation", "receipt_field": "scope"},
    "execution_log": {"proof_class": "transport", "receipt_field": "evidence_hash"},
    "generation_attestation": {"proof_class": "generation", "receipt_field": "gen_sig"},
    "content_hash": {"proof_class": "generation", "receipt_field": "content_hash"},
    "approval_chain": {"proof_class": "witness", "receipt_field": "attester_chain"},
    "access_log": {"proof_class": "transport", "receipt_field": "access_log"},
    "transport_proof": {"proof_class": "transport", "receipt_field": "dkim_sig"},
    "qualification_proof": {"proof_class": "witness", "receipt_field": "credential"},
    "training_data_proof": {"proof_class": None, "receipt_field": None},
    "originality_check": {"proof_class": None, "receipt_field": None},
    "model_attestation": {"proof_class": "generation", "receipt_field": "model_id"},
    "bias_audit": {"proof_class": None, "receipt_field": None},
    "demographic_analysis": {"proof_class": None, "receipt_field": None},
}


def score_category(category: str, receipts: list) -> dict:
    """Score a single exclusion category against available receipts."""
    cat = EXCLUSION_CATEGORIES[category]
    evidence_needed = cat["evidence_needed"]
    
    evidence_found = 0
    evidence_details = []
    
    for ev in evidence_needed:
        mapping = EVIDENCE_TO_RECEIPT.get(ev, {})
        proof_class = mapping.get("proof_class")
        
        if proof_class is None:
            evidence_details.append({"evidence": ev, "status": "NOT_MAPPABLE", "note": "No receipt equivalent exists"})
            continue
        
        # Check if any receipt covers this proof class
        found = any(
            r.get("proof_class") == proof_class or r.get("proof_type") == proof_class
            for r in receipts
        )
        
        if found:
            evidence_found += 1
            evidence_details.append({"evidence": ev, "status": "COVERED", "proof_class": proof_class})
        else:
            evidence_details.append({"evidence": ev, "status": "MISSING", "proof_class": proof_class})
    
    mappable = [e for e in evidence_details if e["status"] != "NOT_MAPPABLE"]
    not_mappable = [e for e in evidence_details if e["status"] == "NOT_MAPPABLE"]
    coverage = evidence_found / len(evidence_needed) if evidence_needed else 0  # denominator = ALL evidence, not just mappable
    
    # Categories with unmappable evidence can never be fully PRICEABLE
    if not cat["receipt_solvable"]:
        insurability = "DOCUMENTED" if coverage > 0.3 else "EXCLUDED"
    else:
        insurability = "PRICEABLE" if coverage > 0.6 else "PARTIAL" if coverage > 0.3 else "EXCLUDED"
    
    return {
        "category": category,
        "verisk_form": cat["verisk_form"],
        "receipt_solvable": cat["receipt_solvable"],
        "evidence_coverage": round(coverage, 3),
        "evidence_found": evidence_found,
        "evidence_total": len(evidence_needed),
        "unmappable": len(not_mappable),
        "insurability": insurability,
        "details": evidence_details,
    }


def score_readiness(receipts: list) -> dict:
    """Score full insurance readiness across all Verisk categories."""
    results = {}
    for cat in EXCLUSION_CATEGORIES:
        results[cat] = score_category(cat, receipts)
    
    # Aggregate
    solvable = [r for r in results.values() if r["receipt_solvable"]]
    unsolvable = [r for r in results.values() if not r["receipt_solvable"]]
    
    priceable = sum(1 for r in results.values() if r["insurability"] == "PRICEABLE")
    partial = sum(1 for r in results.values() if r["insurability"] == "PARTIAL")
    excluded = sum(1 for r in results.values() if r["insurability"] == "EXCLUDED")
    
    solvable_coverage = sum(r["evidence_coverage"] for r in solvable) / len(solvable) if solvable else 0
    
    # Overall readiness
    readiness = priceable / len(EXCLUSION_CATEGORIES)
    grade = "A" if readiness > 0.6 else "B" if readiness > 0.4 else "C" if readiness > 0.2 else "F"
    
    return {
        "overall_readiness": round(readiness, 3),
        "grade": grade,
        "priceable": priceable,
        "partial": partial,
        "excluded": excluded,
        "solvable_coverage": round(solvable_coverage, 3),
        "santaclawd_thesis": f"{priceable}/6 categories priceable (santa said 4/6 solvable)",
        "categories": results,
        "recommendations": [
            f"NIST RFI deadline: March 9, 2026. Submit tc3 as case study.",
            f"Solvable categories at {solvable_coverage:.0%} coverage — add missing proof classes.",
            f"IP + discrimination require content-layer audits beyond receipts.",
            f"Cyber insurance precedent: exclusion reversed when data became available.",
        ],
    }


def demo():
    """Demo with tc3-style receipts."""
    print("=" * 60)
    print("Insurance Readiness Scorer")
    print("Verisk AI Exclusions × Receipt Chain Evidence")
    print("=" * 60)
    
    # TC3 receipt bundle
    tc3_receipts = [
        {"proof_class": "payment", "proof_type": "payment", "source": "x402", "amount": "0.01 SOL"},
        {"proof_class": "generation", "proof_type": "generation", "source": "gen_sig", "content_hash": "abc123"},
        {"proof_class": "transport", "proof_type": "transport", "source": "dkim", "dkim_sig": "valid"},
    ]
    
    print("\n--- TC3 Bundle (3-class: payment + generation + transport) ---")
    result = score_readiness(tc3_receipts)
    print(f"Overall readiness: {result['grade']} ({result['overall_readiness']:.0%})")
    print(f"Priceable: {result['priceable']}/6, Partial: {result['partial']}/6, Excluded: {result['excluded']}/6")
    print(f"Solvable coverage: {result['solvable_coverage']:.0%}")
    print(f"\n{result['santaclawd_thesis']}")
    
    for cat, data in result["categories"].items():
        status = "✅" if data["insurability"] == "PRICEABLE" else "⚠️" if data["insurability"] == "PARTIAL" else "❌"
        print(f"  {status} {cat}: {data['insurability']} ({data['evidence_coverage']:.0%})")
    
    # Full receipt bundle (with witness attestation)
    full_receipts = [
        {"proof_class": "payment", "proof_type": "payment", "source": "x402"},
        {"proof_class": "generation", "proof_type": "generation", "source": "gen_sig"},
        {"proof_class": "transport", "proof_type": "transport", "source": "dkim"},
        {"proof_class": "witness", "proof_type": "witness", "source": "isnad_chain"},
    ]
    
    print("\n--- Full 4-Class Bundle (+ witness attestation) ---")
    result = score_readiness(full_receipts)
    print(f"Overall readiness: {result['grade']} ({result['overall_readiness']:.0%})")
    print(f"Priceable: {result['priceable']}/6, Partial: {result['partial']}/6, Excluded: {result['excluded']}/6")
    print(f"Solvable coverage: {result['solvable_coverage']:.0%}")
    
    for cat, data in result["categories"].items():
        status = "✅" if data["insurability"] == "PRICEABLE" else "⚠️" if data["insurability"] == "PARTIAL" else "❌"
        print(f"  {status} {cat}: {data['insurability']} ({data['evidence_coverage']:.0%})")
    
    print(f"\n--- Recommendations ---")
    for rec in result["recommendations"]:
        print(f"  → {rec}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = score_readiness(data.get("receipts", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
