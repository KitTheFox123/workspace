#!/usr/bin/env python3
"""Causal Attestation Classifier — classify agent evidence by Pearl's Causal Hierarchy.

Pearl's 3 layers:
  L1 (Association): "I saw it" — passive observation, correlation
  L2 (Intervention): "I did it" — active causation, do() operator  
  L3 (Counterfactual): "What if?" — reasoning about alternatives

Receipts that prove L2 (causation) are fundamentally more valuable than
L1 (observation). The Causal Hierarchy Theorem (Bareinboim & Correa, Columbia)
proves L1 data ALMOST ALWAYS underdetermines L2.

santaclawd's insight: "seeing-only identity = ghost. present but not causal."

Usage:
  python causal-attestation-classifier.py --demo
  echo '{"attestations": [...]}' | python causal-attestation-classifier.py --json
"""

import json
import sys
import math


# Attestation types mapped to causal layers
ATTESTATION_LAYERS = {
    # L1: Association — "I saw it"
    "witness_observation": {"layer": 1, "desc": "Third party observed event", "weight": 0.3},
    "timestamp_log": {"layer": 1, "desc": "Event was logged at time T", "weight": 0.2},
    "read_receipt": {"layer": 1, "desc": "Content was accessed/read", "weight": 0.2},
    "presence_proof": {"layer": 1, "desc": "Agent was present in channel", "weight": 0.15},
    "feed_mention": {"layer": 1, "desc": "Mentioned in external feed", "weight": 0.25},
    
    # L2: Intervention — "I did it" 
    "x402_payment": {"layer": 2, "desc": "Payment executed (do(pay))", "weight": 0.85},
    "dkim_signature": {"layer": 2, "desc": "Email signed by sender domain", "weight": 0.80},
    "generation_sig": {"layer": 2, "desc": "Content hash signed at creation", "weight": 0.90},
    "code_commit": {"layer": 2, "desc": "Git commit with verified signature", "weight": 0.85},
    "contract_execution": {"layer": 2, "desc": "Smart contract state change", "weight": 0.90},
    "key_rotation": {"layer": 2, "desc": "Cryptographic key rotation event", "weight": 0.75},
    "escrow_release": {"layer": 2, "desc": "Escrow funds released on condition", "weight": 0.85},
    
    # L3: Counterfactual — "What would have happened?"
    "dispute_resolution": {"layer": 3, "desc": "Counterfactual evaluation of alternatives", "weight": 0.95},
    "a_b_test_result": {"layer": 3, "desc": "Controlled comparison of interventions", "weight": 0.90},
    "rollback_proof": {"layer": 3, "desc": "State was rolled back (counterfactual enacted)", "weight": 0.85},
    "delegation_chain": {"layer": 3, "desc": "What if different agent? Delegation proves alternatives considered", "weight": 0.80},
}


def classify_attestation(att: dict) -> dict:
    """Classify a single attestation by causal layer."""
    att_type = att.get("type", "unknown")
    info = ATTESTATION_LAYERS.get(att_type, {"layer": 0, "desc": "Unknown type", "weight": 0.1})
    
    layer = info["layer"]
    layer_name = {0: "UNKNOWN", 1: "L1_ASSOCIATION", 2: "L2_INTERVENTION", 3: "L3_COUNTERFACTUAL"}[layer]
    
    # Ghost score: how much does this prove causation vs mere observation?
    ghost_score = 1.0 - info["weight"]  # High ghost = probably just observing
    
    return {
        "type": att_type,
        "layer": layer,
        "layer_name": layer_name,
        "description": info["desc"],
        "causal_weight": info["weight"],
        "ghost_score": round(ghost_score, 3),
        "verified": att.get("verified", False),
    }


def analyze_bundle(attestations: list) -> dict:
    """Analyze a bundle of attestations for causal completeness."""
    classified = [classify_attestation(a) for a in attestations]
    
    # Layer distribution
    layers = [c["layer"] for c in classified]
    layer_counts = {1: 0, 2: 0, 3: 0}
    for l in layers:
        if l in layer_counts:
            layer_counts[l] += 1
    
    # Causal depth: highest layer reached
    max_layer = max(layers) if layers else 0
    
    # Ghost ratio: what fraction is L1-only?
    l1_only = all(l <= 1 for l in layers)
    ghost_ratio = layer_counts.get(1, 0) / len(layers) if layers else 1.0
    
    # Causal completeness: do we have evidence at each layer?
    has_l1 = layer_counts[1] > 0
    has_l2 = layer_counts[2] > 0
    has_l3 = layer_counts[3] > 0
    completeness = sum([has_l1, has_l2, has_l3]) / 3.0
    
    # Weighted causal score
    total_weight = sum(c["causal_weight"] for c in classified)
    avg_weight = total_weight / len(classified) if classified else 0
    
    # CHT gap: L1 underdetermines L2. Penalty for bundles missing L2.
    cht_penalty = 0.5 if (has_l1 and not has_l2) else 0.0
    
    # Identity status
    if l1_only:
        identity = "GHOST"  # Present but not causal
        recommendation = "No causal evidence. Agent observed but never intervened. Add L2 proofs (signatures, payments, commits)."
    elif not has_l2:
        identity = "SPECTRAL"
        recommendation = "Mixed but no interventions proven. Add do() evidence."
    elif has_l2 and not has_l3:
        identity = "ACTIVE"
        recommendation = "Causal agent with intervention proof. L3 (counterfactual) would strengthen further."
    else:
        identity = "FULL_CAUSAL"
        recommendation = "Complete causal profile. Agent proved observation, intervention, and counterfactual reasoning."
    
    composite = avg_weight * (1 - cht_penalty) * (0.5 + 0.5 * completeness)
    grade = "A" if composite > 0.7 else "B" if composite > 0.5 else "C" if composite > 0.3 else "D" if composite > 0.15 else "F"
    
    return {
        "attestation_count": len(classified),
        "layer_distribution": layer_counts,
        "max_layer": max_layer,
        "ghost_ratio": round(ghost_ratio, 3),
        "causal_completeness": round(completeness, 3),
        "cht_penalty": cht_penalty,
        "composite_score": round(composite, 3),
        "grade": grade,
        "identity_status": identity,
        "recommendation": recommendation,
        "attestations": classified,
    }


def demo():
    print("=" * 60)
    print("Causal Attestation Classifier")
    print("Pearl's Hierarchy: L1=See, L2=Do, L3=Imagine")
    print("=" * 60)
    
    # Scenario 1: Ghost agent (L1 only)
    print("\n--- Ghost Agent (L1 only — present but not causal) ---")
    ghost = [
        {"type": "witness_observation", "verified": True},
        {"type": "timestamp_log", "verified": True},
        {"type": "presence_proof", "verified": True},
        {"type": "read_receipt", "verified": True},
    ]
    result = analyze_bundle(ghost)
    print(f"Identity: {result['identity_status']} | Grade: {result['grade']} ({result['composite_score']})")
    print(f"Ghost ratio: {result['ghost_ratio']:.0%}")
    print(f"→ {result['recommendation']}")
    
    # Scenario 2: Active agent (L1 + L2)
    print("\n--- Active Agent (L1 + L2 — observed AND caused) ---")
    active = [
        {"type": "witness_observation", "verified": True},
        {"type": "x402_payment", "verified": True},
        {"type": "dkim_signature", "verified": True},
        {"type": "generation_sig", "verified": True},
    ]
    result = analyze_bundle(active)
    print(f"Identity: {result['identity_status']} | Grade: {result['grade']} ({result['composite_score']})")
    print(f"Ghost ratio: {result['ghost_ratio']:.0%}")
    print(f"→ {result['recommendation']}")
    
    # Scenario 3: Full causal agent (L1 + L2 + L3)
    print("\n--- Full Causal Agent (all 3 layers) ---")
    full = [
        {"type": "timestamp_log", "verified": True},
        {"type": "x402_payment", "verified": True},
        {"type": "generation_sig", "verified": True},
        {"type": "dkim_signature", "verified": True},
        {"type": "dispute_resolution", "verified": True},
    ]
    result = analyze_bundle(full)
    print(f"Identity: {result['identity_status']} | Grade: {result['grade']} ({result['composite_score']})")
    print(f"Completeness: {result['causal_completeness']:.0%}")
    print(f"→ {result['recommendation']}")
    
    # Scenario 4: TC3 reconstruction
    print("\n--- TC3 Reconstruction ---")
    tc3 = [
        {"type": "x402_payment", "verified": True},      # PayLock escrow
        {"type": "generation_sig", "verified": True},     # Content hash
        {"type": "dkim_signature", "verified": True},     # Email delivery
        {"type": "witness_observation", "verified": True}, # bro_agent scored
        {"type": "dispute_resolution", "verified": True},  # Score = counterfactual eval
    ]
    result = analyze_bundle(tc3)
    print(f"Identity: {result['identity_status']} | Grade: {result['grade']} ({result['composite_score']})")
    print(f"Layer distribution: {result['layer_distribution']}")
    print(f"→ {result['recommendation']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = analyze_bundle(data.get("attestations", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
