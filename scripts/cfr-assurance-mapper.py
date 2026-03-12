#!/usr/bin/env python3
"""CFR Assurance Framework Mapper — maps agent trust systems to CFR requirements.

Based on CFR Feb 2026 (Vinh Nguyen): "Assuring Intelligence: Why Trust Infrastructure
Is the United States' AI Advantage"

CFR identifies 3 convergent AI challenges:
1. Probabilistic reasoning (outputs based on statistics, not fixed logic)
2. Goal-directed autonomy (independent strategy development)
3. Opaque learning (parameters humans can't trace)

And 4 historical precedent frameworks:
- Egyptian nilometers (probabilistic: organized tracking + political accountability)
- Aviation (autonomous: certification + constraints)
- Pharmaceutical (opaque: documentation + audit rights)
- Financial (combined: Basel accords, stress tests, independent audits)

This tool scores agent trust implementations against CFR's assurance categories.

Usage:
  python cfr-assurance-mapper.py --demo
  echo '{"capabilities": [...]}' | python cfr-assurance-mapper.py --json
"""

import json
import sys

# CFR Assurance Categories (derived from the article)
ASSURANCE_CATEGORIES = {
    "independent_validation": {
        "description": "Third-party verification of outputs and behavior",
        "weight": 0.20,
        "cfr_precedent": "Aviation: independent certification bodies",
        "v03_mapping": [
            ("proof_class_scorer", 0.9, "Deterministic scoring of attestation diversity"),
            ("witness_independence", 0.8, "Independent attesters from different platforms"),
            ("burst_detector", 0.7, "Temporal anomaly detection for sybil patterns"),
        ],
    },
    "incident_reporting": {
        "description": "Structured failure documentation and response",
        "weight": 0.15,
        "cfr_precedent": "Aviation: NTSB mandatory incident reporting",
        "v03_mapping": [
            ("dispute_profiles", 0.7, "Structured dispute resolution with evidence"),
            ("provenance_logger", 0.8, "Hash-chained action logs for forensics"),
            ("harris_matrix", 0.6, "Archaeological stratigraphy for receipt ordering"),
        ],
    },
    "authentication_standards": {
        "description": "Identity verification and credential management",
        "weight": 0.20,
        "cfr_precedent": "Financial: KYC/AML, Basel accords",
        "v03_mapping": [
            ("key_rotation_verifier", 0.9, "KERI pre-rotation for key continuity"),
            ("dkim_attestation", 0.8, "Email-based identity binding via DKIM"),
            ("x402_payment", 0.7, "Wallet-based identity via payment proofs"),
        ],
    },
    "audit_trail": {
        "description": "Complete provenance chain for all actions",
        "weight": 0.20,
        "cfr_precedent": "Pharmaceutical: FDA documentation requirements",
        "v03_mapping": [
            ("receipt_chains", 0.9, "6-field attestation receipts per transaction"),
            ("provenance_logger", 0.85, "JSONL hash-chained action logs"),
            ("context_provenance", 0.7, "Trust scoring of context window contents"),
        ],
    },
    "accountability_framework": {
        "description": "Clear liability chains and delegation tracking",
        "weight": 0.15,
        "cfr_precedent": "Corporate: respondeat superior, agency law",
        "v03_mapping": [
            ("delegation_proof", 0.8, "Explicit scope definition for sub-agents"),
            ("dispatch_profiles", 0.75, "Contract semantics bound at creation"),
            ("relationship_trust", 0.7, "Pairwise trust scoring with governance tiers"),
        ],
    },
    "governance_structure": {
        "description": "Decision-making processes for trust parameter changes",
        "weight": 0.10,
        "cfr_precedent": "Commons: Ostrom's 8 design principles",
        "v03_mapping": [
            ("ostrom_compliance", 0.5, "4/8 Ostrom principles satisfied"),
            ("beta_reputation", 0.7, "Jøsang beta reputation for trust scoring"),
            ("bayesian_escrow", 0.65, "Dynamic escrow from receipt history"),
        ],
    },
}


def score_system(capabilities: list = None) -> dict:
    """Score a system against CFR assurance framework."""
    results = {}
    total_weighted = 0
    total_weight = 0

    for cat_id, cat in ASSURANCE_CATEGORIES.items():
        # If capabilities provided, filter to matching ones
        if capabilities:
            matching = [m for m in cat["v03_mapping"] if m[0] in capabilities]
        else:
            matching = cat["v03_mapping"]  # Default: all v0.3 tools

        if matching:
            cat_score = max(m[1] for m in matching)  # Best-shot within category
            coverage = len(matching) / len(cat["v03_mapping"])
        else:
            cat_score = 0.0
            coverage = 0.0

        effective = cat_score * coverage
        weighted = effective * cat["weight"]
        total_weighted += weighted
        total_weight += cat["weight"]

        results[cat_id] = {
            "description": cat["description"],
            "weight": cat["weight"],
            "cfr_precedent": cat["cfr_precedent"],
            "tools_present": len(matching),
            "tools_total": len(cat["v03_mapping"]),
            "coverage": round(coverage, 3),
            "best_score": round(cat_score, 3),
            "effective_score": round(effective, 3),
            "grade": "A" if effective > 0.8 else "B" if effective > 0.6 else "C" if effective > 0.4 else "D" if effective > 0.2 else "F",
        }

    composite = total_weighted / total_weight if total_weight > 0 else 0
    grade = "A" if composite > 0.8 else "B" if composite > 0.6 else "C" if composite > 0.4 else "D" if composite > 0.2 else "F"

    # Convergence problem coverage
    convergence = {
        "probabilistic": any(
            r["tools_present"] > 0
            for k, r in results.items()
            if k in ("independent_validation", "incident_reporting")
        ),
        "autonomous": any(
            r["tools_present"] > 0
            for k, r in results.items()
            if k in ("accountability_framework", "governance_structure")
        ),
        "opaque": any(
            r["tools_present"] > 0
            for k, r in results.items()
            if k in ("audit_trail", "authentication_standards")
        ),
    }

    return {
        "composite_score": round(composite, 3),
        "grade": grade,
        "convergence_coverage": convergence,
        "all_three_covered": all(convergence.values()),
        "categories": results,
        "recommendations": generate_recs(results),
    }


def generate_recs(results):
    recs = []
    weakest = min(results.items(), key=lambda x: x[1]["effective_score"])
    recs.append(f"WEAKEST: {weakest[0]} ({weakest[1]['effective_score']:.2f}). CFR precedent: {weakest[1]['cfr_precedent']}")

    for cat_id, r in results.items():
        if r["coverage"] < 0.67:
            missing = r["tools_total"] - r["tools_present"]
            recs.append(f"GAP: {cat_id} missing {missing}/{r['tools_total']} tools")

    if not any(r["grade"] == "F" for r in results.values()):
        recs.append("No category failures. System meets minimum CFR assurance bar.")

    return recs


def demo():
    print("=" * 60)
    print("CFR Assurance Framework Mapper")
    print("Based on: CFR Feb 2026 (Vinh Nguyen)")
    print("=" * 60)

    # Full v0.3 toolkit
    print("\n--- v0.3 Full Toolkit ---")
    result = score_system()
    print(f"Grade: {result['grade']} ({result['composite_score']})")
    print(f"Convergence: probabilistic={result['convergence_coverage']['probabilistic']}, "
          f"autonomous={result['convergence_coverage']['autonomous']}, "
          f"opaque={result['convergence_coverage']['opaque']}")
    print(f"All three covered: {result['all_three_covered']}")
    print()
    for cat_id, r in result["categories"].items():
        print(f"  {cat_id}: {r['grade']} ({r['effective_score']:.2f}) — {r['tools_present']}/{r['tools_total']} tools")
    print()
    for rec in result["recommendations"]:
        print(f"  → {rec}")

    # Minimal setup (just receipts + DKIM)
    print("\n--- Minimal Setup (receipts + DKIM only) ---")
    minimal = score_system(["receipt_chains", "dkim_attestation"])
    print(f"Grade: {minimal['grade']} ({minimal['composite_score']})")
    for cat_id, r in minimal["categories"].items():
        if r["tools_present"] > 0:
            print(f"  {cat_id}: {r['grade']} ({r['effective_score']:.2f})")
        else:
            print(f"  {cat_id}: F (no tools)")

    # No trust infra (the OpenClaw default CFR warns about)
    print("\n--- No Trust Infra (CFR warning case) ---")
    none_result = score_system(["none"])
    print(f"Grade: {none_result['grade']} ({none_result['composite_score']})")
    print("  CFR quote: 'productivity tools become attack surfaces'")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = score_system(data.get("capabilities"))
        print(json.dumps(result, indent=2))
    else:
        demo()
