#!/usr/bin/env python3
"""
GDPR Receipt Checker — Score agent operations against GDPR requirements.

Maps receipt chain evidence to GDPR articles:
  Art 5(2): Accountability — demonstrate compliance
  Art 12-15: Transparency — meaningful information about logic
  Art 22: Automated decision-making — consent + human oversight
  Art 25: Data protection by design
  Art 30: Records of processing activities

Key insight (TechPolicy.Press/Douglas 2025): post-hoc XAI (LIME, SHAP) is unreliable
for complex models. Receipt chains provide actual decision traces, not approximations.

Usage:
    python3 gdpr-receipt-checker.py              # Demo
    echo '{"receipts": [...]}' | python3 gdpr-receipt-checker.py --stdin
"""

import json, sys
from dataclasses import dataclass, field

GDPR_ARTICLES = {
    "art_5_2": {
        "name": "Accountability",
        "requirement": "Demonstrate compliance with processing principles",
        "receipt_evidence": ["action_hash", "timestamp", "chain_integrity"],
        "weight": 0.2,
    },
    "art_12_15": {
        "name": "Transparency / Right to Explanation",
        "requirement": "Meaningful information about logic involved",
        "receipt_evidence": ["scope_hash", "delegation_proof", "proof_class"],
        "weight": 0.25,
    },
    "art_22": {
        "name": "Automated Decision-Making",
        "requirement": "Consent + right to human intervention",
        "receipt_evidence": ["consent_receipt", "human_oversight_flag", "scope_boundary"],
        "weight": 0.25,
    },
    "art_25": {
        "name": "Data Protection by Design",
        "requirement": "Technical measures ensuring data protection",
        "receipt_evidence": ["null_receipts", "scope_hash", "attestation_coverage"],
        "weight": 0.15,
    },
    "art_30": {
        "name": "Records of Processing",
        "requirement": "Maintain records of all processing activities",
        "receipt_evidence": ["action_hash", "timestamp", "attester_id", "chain_tip"],
        "weight": 0.15,
    },
}


def check_compliance(receipts: list[dict]) -> dict:
    """Check receipt chain against GDPR requirements."""
    if not receipts:
        return {"score": 0, "grade": "F", "compliant": False, "reason": "No receipts = no evidence"}

    # Count evidence types present
    evidence_present = set()
    for r in receipts:
        evidence_present.update(r.get("fields", []))

    article_scores = {}
    for art_id, art in GDPR_ARTICLES.items():
        required = art["receipt_evidence"]
        present = [e for e in required if e in evidence_present]
        coverage = len(present) / len(required) if required else 0

        article_scores[art_id] = {
            "name": art["name"],
            "requirement": art["requirement"],
            "coverage": round(coverage, 3),
            "present": present,
            "missing": [e for e in required if e not in evidence_present],
            "compliant": coverage >= 0.67,  # 2/3 threshold
        }

    # Composite
    composite = sum(
        article_scores[a]["coverage"] * GDPR_ARTICLES[a]["weight"]
        for a in GDPR_ARTICLES
    )

    compliant_count = sum(1 for a in article_scores.values() if a["compliant"])
    all_compliant = compliant_count == len(GDPR_ARTICLES)

    if composite >= 0.8: grade = "A"
    elif composite >= 0.6: grade = "B"
    elif composite >= 0.4: grade = "C"
    elif composite >= 0.2: grade = "D"
    else: grade = "F"

    # XAI comparison
    xai_note = (
        "Receipt chains provide actual decision traces. "
        "Post-hoc XAI (LIME, SHAP) approximates reasoning without guarantees of accuracy "
        "(Douglas/TechPolicy.Press 2025). Receipts > explanations."
    )

    return {
        "composite_score": round(composite, 3),
        "grade": grade,
        "compliant_articles": compliant_count,
        "total_articles": len(GDPR_ARTICLES),
        "fully_compliant": all_compliant,
        "receipt_count": len(receipts),
        "evidence_types": sorted(evidence_present),
        "articles": article_scores,
        "xai_comparison": xai_note,
    }


def demo():
    print("=== GDPR Receipt Checker ===\n")

    # TC3-style full receipts
    tc3 = [
        {"fields": ["action_hash", "timestamp", "chain_integrity", "scope_hash",
                     "delegation_proof", "proof_class", "consent_receipt",
                     "human_oversight_flag", "scope_boundary", "null_receipts",
                     "attestation_coverage", "attester_id", "chain_tip"]},
    ]

    print("TC3 full receipts:")
    r = check_compliance(tc3)
    print(f"  Score: {r['composite_score']} ({r['grade']})")
    print(f"  Compliant: {r['compliant_articles']}/{r['total_articles']} articles")
    print(f"  Fully compliant: {r['fully_compliant']}")

    # Minimal receipts (just timestamps + hashes)
    minimal = [
        {"fields": ["action_hash", "timestamp"]},
    ]

    print("\nMinimal receipts (hash + timestamp only):")
    r = check_compliance(minimal)
    print(f"  Score: {r['composite_score']} ({r['grade']})")
    print(f"  Compliant: {r['compliant_articles']}/{r['total_articles']} articles")
    for art_id, art in r["articles"].items():
        if not art["compliant"]:
            print(f"  ❌ {art['name']}: missing {art['missing']}")

    # No receipts
    print("\nNo receipts:")
    r = check_compliance([])
    print(f"  Score: {r.get('score', r.get('composite_score', 0))} ({r['grade']})")
    print(f"  {r.get('reason', '')}")

    print(f"\n📋 {tc3[0]['fields'][:3]}... → XAI comparison:")
    print(f"  {check_compliance(tc3)['xai_comparison']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = check_compliance(data.get("receipts", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
