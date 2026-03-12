#!/usr/bin/env python3
"""Causal Hierarchy Scorer — classify evidence by Pearl's Causal Hierarchy.

Based on Bareinboim & Correa (Columbia 2022): Causal Hierarchy Theorem.
L1 (observational) ALMOST ALWAYS underdetermines L2 (interventional).

Receipts = L2 (do-operator). Scores = L1 (observation). The gap is provable.

Usage:
  python causal-hierarchy-scorer.py --demo
  echo '{"evidence": [...]}' | python causal-hierarchy-scorer.py --json
"""

import json
import sys
import math

# Pearl's Causal Hierarchy layers
LAYERS = {
    1: {"name": "Observational (seeing)", "operator": "P(Y|X)", "examples": ["reputation score", "benchmark result", "upvote count", "follower count"]},
    2: {"name": "Interventional (doing)", "operator": "P(Y|do(X))", "examples": ["receipt chain", "DKIM proof", "x402 payment", "attestation", "escrow completion"]},
    3: {"name": "Counterfactual (imagining)", "operator": "P(Y_x|X',Y')", "examples": ["dispute resolution outcome", "what-if analysis", "alternative history"]},
}

# Evidence type → causal layer mapping
EVIDENCE_LAYER = {
    # L1: Observational — can be confounded
    "reputation_score": 1,
    "benchmark": 1,
    "upvote_count": 1,
    "follower_count": 1,
    "self_report": 1,
    "survey": 1,
    "rating": 1,
    
    # L2: Interventional — causal evidence
    "receipt": 2,
    "dkim_proof": 2,
    "x402_payment": 2,
    "attestation": 2,
    "escrow_completion": 2,
    "signed_delivery": 2,
    "hash_verification": 2,
    "key_rotation_proof": 2,
    "witness_attestation": 2,
    
    # L3: Counterfactual — strongest
    "dispute_resolution": 3,
    "a_b_test": 3,
    "adversarial_audit": 3,
    "fault_injection_result": 3,
}


def classify_evidence(evidence: dict) -> dict:
    """Classify a single piece of evidence by causal layer."""
    etype = evidence.get("type", "unknown")
    layer = EVIDENCE_LAYER.get(etype, 1)  # Default to L1 (weakest)
    
    # Verification status affects weight within layer
    verified = evidence.get("verified", False)
    fresh = evidence.get("age_hours", 0) < 48
    independent = evidence.get("independent", True)
    
    # Base weight by layer (CHT: higher layers exponentially more valuable)
    base_weight = {1: 0.1, 2: 0.6, 3: 1.0}[layer]
    
    # Modifiers
    weight = base_weight
    if verified:
        weight *= 1.3
    if not fresh:
        weight *= 0.7
    if not independent:
        weight *= 0.5
    
    weight = min(1.0, weight)
    
    return {
        "type": etype,
        "layer": layer,
        "layer_name": LAYERS[layer]["name"],
        "operator": LAYERS[layer]["operator"],
        "weight": round(weight, 3),
        "verified": verified,
        "confoundable": layer == 1,
        "causal": layer >= 2,
    }


def score_evidence_bundle(evidence_list: list) -> dict:
    """Score a bundle of evidence using causal hierarchy."""
    classified = [classify_evidence(e) for e in evidence_list]
    
    if not classified:
        return {"error": "no evidence"}
    
    # Layer distribution
    layers = {1: [], 2: [], 3: []}
    for c in classified:
        layers[c["layer"]].append(c)
    
    # CHT gap analysis
    has_l2 = len(layers[2]) > 0
    has_l3 = len(layers[3]) > 0
    l1_only = not has_l2 and not has_l3
    
    # Weighted score
    total_weight = sum(c["weight"] for c in classified)
    max_possible = len(classified) * 1.0
    score = total_weight / max_possible if max_possible > 0 else 0
    
    # Causal coverage: what % of evidence is L2+?
    causal_count = sum(1 for c in classified if c["causal"])
    causal_coverage = causal_count / len(classified)
    
    # Grade
    if has_l3 and has_l2 and causal_coverage > 0.6:
        grade = "A"
    elif has_l2 and causal_coverage > 0.5:
        grade = "B"
    elif has_l2:
        grade = "C"
    else:
        grade = "F"  # L1 only = confounded, CHT applies
    
    return {
        "evidence_count": len(classified),
        "layer_distribution": {f"L{k}": len(v) for k, v in layers.items()},
        "causal_coverage": round(causal_coverage, 3),
        "weighted_score": round(score, 3),
        "grade": grade,
        "cht_warning": l1_only,
        "cht_message": "CHT: L1 data ALMOST ALWAYS underdetermines L2. No causal claims possible from observational evidence alone." if l1_only else "Interventional evidence present. Causal attribution supported." if has_l2 else "",
        "classified": classified,
    }


def demo():
    print("=" * 60)
    print("Causal Hierarchy Scorer")
    print("Bareinboim & Correa (Columbia 2022)")
    print("=" * 60)
    
    # Scenario 1: L1 only (reputation scores)
    print("\n--- Scenario 1: Reputation Scores Only (L1) ---")
    l1_only = [
        {"type": "reputation_score", "verified": True},
        {"type": "upvote_count"},
        {"type": "benchmark", "verified": True},
        {"type": "rating"},
    ]
    r = score_evidence_bundle(l1_only)
    print(f"Grade: {r['grade']} | Layers: {r['layer_distribution']}")
    print(f"Causal coverage: {r['causal_coverage']:.0%}")
    print(f"⚠️  {r['cht_message']}")
    
    # Scenario 2: Receipt chain (L2)
    print("\n--- Scenario 2: TC3-style Receipt Chain (L2) ---")
    tc3 = [
        {"type": "x402_payment", "verified": True},
        {"type": "signed_delivery", "verified": True},
        {"type": "dkim_proof", "verified": True},
        {"type": "attestation", "verified": True, "independent": True},
        {"type": "reputation_score"},
    ]
    r = score_evidence_bundle(tc3)
    print(f"Grade: {r['grade']} | Layers: {r['layer_distribution']}")
    print(f"Causal coverage: {r['causal_coverage']:.0%}")
    print(f"✅ {r['cht_message']}")
    
    # Scenario 3: Full hierarchy (L1+L2+L3)
    print("\n--- Scenario 3: Full Causal Hierarchy ---")
    full = [
        {"type": "x402_payment", "verified": True},
        {"type": "dkim_proof", "verified": True},
        {"type": "attestation", "verified": True},
        {"type": "dispute_resolution", "verified": True},
        {"type": "adversarial_audit", "verified": True},
        {"type": "reputation_score"},
    ]
    r = score_evidence_bundle(full)
    print(f"Grade: {r['grade']} | Layers: {r['layer_distribution']}")
    print(f"Causal coverage: {r['causal_coverage']:.0%}")
    print(f"Score: {r['weighted_score']}")
    
    # Key insight
    print("\n--- CHT Implications ---")
    print("L1 (scores) → L2 (receipts): IMPOSSIBLE without intervention")
    print("L2 (receipts) → L1 (scores): trivial compression")
    print("Therefore: receipts > scores. Always. Provably.")
    print("Pearl's do-calculus: receipts ARE the do() operator for trust.")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = score_evidence_bundle(data.get("evidence", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
