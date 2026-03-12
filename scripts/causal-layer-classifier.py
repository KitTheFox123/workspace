#!/usr/bin/env python3
"""Causal Layer Classifier — classify attestation evidence by Pearl's Causal Hierarchy.

Pearl's CHT (Bareinboim/Columbia 2022) proves data at one layer virtually always
underdetermines higher layers:
  L1 (Seeing/Observational): logs, timestamps, metadata
  L2 (Doing/Interventional): receipts, signatures, transactions  
  L3 (Imagining/Counterfactual): what-if scenarios, restraint signals

Key insight: you CANNOT reconstruct L2 from L1. Logs don't prove action.
santaclawd: "if you didn't log receipts at execution time, they're gone."

Usage:
  python causal-layer-classifier.py --demo
  echo '{"evidence": [...]}' | python causal-layer-classifier.py --json
"""

import json
import sys
import math

# Evidence type → causal layer mapping
EVIDENCE_LAYERS = {
    # L1: Observational (seeing)
    "server_log": 1,
    "timestamp": 1,
    "ip_address": 1,
    "user_agent": 1,
    "api_call_log": 1,
    "metric": 1,
    "heartbeat_ping": 1,
    
    # L2: Interventional (doing)
    "x402_receipt": 2,
    "dkim_signature": 2,
    "generation_signature": 2,
    "escrow_lock": 2,
    "payment_tx": 2,
    "key_rotation": 2,
    "attestation_signature": 2,
    "delegation_proof": 2,
    "content_hash": 2,
    "witness_receipt": 2,
    
    # L3: Counterfactual (imagining)
    "restraint_signal": 3,     # approved-but-not-taken actions
    "scope_boundary": 3,       # what COULD have been accessed but wasn't
    "null_receipt": 3,         # proof of non-action
    "dispute_resolution": 3,   # what WOULD have happened under challenge
    "preregistration": 3,      # committed methodology before execution
}

# Trust multipliers by layer
LAYER_TRUST = {1: 0.3, 2: 0.7, 3: 0.9}
LAYER_NAMES = {1: "Observational (Seeing)", 2: "Interventional (Doing)", 3: "Counterfactual (Imagining)"}


def classify_evidence(evidence: dict) -> dict:
    """Classify a single piece of evidence into Pearl's hierarchy."""
    etype = evidence.get("type", "unknown")
    layer = EVIDENCE_LAYERS.get(etype, 0)
    
    verified = evidence.get("verified", False)
    age_hours = evidence.get("age_hours", 0)
    
    base_trust = LAYER_TRUST.get(layer, 0.1)
    verification_bonus = 0.1 if verified else 0
    freshness = math.exp(-age_hours / (24 * 14))  # 14-day half-life
    
    effective_trust = min(0.95, (base_trust + verification_bonus) * freshness)
    
    return {
        "type": etype,
        "layer": layer,
        "layer_name": LAYER_NAMES.get(layer, "Unknown"),
        "base_trust": round(base_trust, 3),
        "effective_trust": round(effective_trust, 3),
        "verified": verified,
        "cht_note": _cht_note(layer),
    }


def _cht_note(layer):
    if layer == 1:
        return "Observational only — cannot prove causation or action"
    elif layer == 2:
        return "Interventional — proves action was taken, cryptographically bound"
    elif layer == 3:
        return "Counterfactual — proves what COULD have happened but didn't"
    return "Unclassified — treat as adversarial"


def analyze_bundle(evidence_list: list) -> dict:
    """Analyze a bundle of evidence across causal layers."""
    classified = [classify_evidence(e) for e in evidence_list]
    
    layer_counts = {1: 0, 2: 0, 3: 0, 0: 0}
    layer_trust_sums = {1: 0, 2: 0, 3: 0}
    
    for c in classified:
        layer_counts[c["layer"]] = layer_counts.get(c["layer"], 0) + 1
        if c["layer"] in layer_trust_sums:
            layer_trust_sums[c["layer"]] += c["effective_trust"]
    
    # Layer coverage score (having evidence at multiple layers)
    layers_present = sum(1 for l in [1, 2, 3] if layer_counts[l] > 0)
    coverage = layers_present / 3
    
    # CHT collapse risk: relying only on L1 = can't prove anything happened
    l1_only = layer_counts[1] > 0 and layer_counts[2] == 0 and layer_counts[3] == 0
    
    # Weighted trust (higher layers worth more)
    total_evidence = sum(layer_counts[l] for l in [1, 2, 3])
    if total_evidence == 0:
        weighted_trust = 0
    else:
        weighted_trust = sum(
            layer_trust_sums[l] for l in [1, 2, 3]
        ) / total_evidence
    
    # Grade
    if coverage >= 0.66 and weighted_trust > 0.6:
        grade = "A"
    elif coverage >= 0.33 and weighted_trust > 0.4:
        grade = "B"
    elif layer_counts[2] > 0:
        grade = "C"
    elif l1_only:
        grade = "D"
    else:
        grade = "F"
    
    return {
        "evidence_count": len(classified),
        "layer_distribution": {LAYER_NAMES[l]: layer_counts[l] for l in [1, 2, 3]},
        "unclassified": layer_counts[0],
        "coverage": round(coverage, 3),
        "weighted_trust": round(weighted_trust, 3),
        "grade": grade,
        "cht_collapse_risk": l1_only,
        "cht_warning": "L1 ONLY: Cannot prove any action was taken (Pearl CHT)" if l1_only else None,
        "recommendations": _recommendations(layer_counts, coverage, l1_only),
        "evidence": classified,
    }


def _recommendations(counts, coverage, l1_only):
    recs = []
    if l1_only:
        recs.append("CRITICAL: Only observational evidence. Add L2 receipts (signatures, transactions, DKIM).")
    if counts[2] == 0:
        recs.append("No interventional evidence. Logs alone cannot prove work was done.")
    if counts[3] == 0 and counts[2] > 0:
        recs.append("No counterfactual evidence. Consider adding restraint signals or preregistration.")
    if coverage < 0.33:
        recs.append("Low layer coverage. Diversify across Pearl's hierarchy.")
    if not recs:
        recs.append("Good causal layer coverage. Evidence supports provenance claims.")
    return recs


def demo():
    print("=" * 60)
    print("Causal Layer Classifier (Pearl's Hierarchy)")
    print("=" * 60)
    
    # Scenario 1: Logs only (L1 — cannot prove action)
    logs_only = [
        {"type": "server_log", "verified": False},
        {"type": "timestamp", "verified": False},
        {"type": "api_call_log", "verified": False},
        {"type": "metric", "verified": False},
    ]
    print("\n--- Scenario 1: Logs Only (L1) ---")
    r = analyze_bundle(logs_only)
    print(f"Grade: {r['grade']}")
    print(f"CHT collapse: {r['cht_collapse_risk']}")
    print(f"Warning: {r['cht_warning']}")
    print(f"Coverage: {r['coverage']}")
    
    # Scenario 2: Full tc3-style bundle (L1+L2)
    tc3 = [
        {"type": "server_log", "verified": False},
        {"type": "x402_receipt", "verified": True},
        {"type": "dkim_signature", "verified": True},
        {"type": "generation_signature", "verified": True},
        {"type": "content_hash", "verified": True},
    ]
    print("\n--- Scenario 2: TC3 Bundle (L1+L2) ---")
    r = analyze_bundle(tc3)
    print(f"Grade: {r['grade']}")
    print(f"Coverage: {r['coverage']} (missing L3)")
    print(f"Trust: {r['weighted_trust']}")
    print(f"Rec: {r['recommendations'][0]}")
    
    # Scenario 3: Full hierarchy (L1+L2+L3)
    full = [
        {"type": "timestamp", "verified": False},
        {"type": "x402_receipt", "verified": True},
        {"type": "dkim_signature", "verified": True},
        {"type": "attestation_signature", "verified": True},
        {"type": "restraint_signal", "verified": True},
        {"type": "preregistration", "verified": True},
    ]
    print("\n--- Scenario 3: Full Hierarchy (L1+L2+L3) ---")
    r = analyze_bundle(full)
    print(f"Grade: {r['grade']}")
    print(f"Coverage: {r['coverage']} (all 3 layers)")
    print(f"Trust: {r['weighted_trust']}")
    print(f"Rec: {r['recommendations'][0]}")
    
    # Scenario 4: santaclawd's insight — restraint as signal
    restraint = [
        {"type": "x402_receipt", "verified": True},
        {"type": "scope_boundary", "verified": True},
        {"type": "null_receipt", "verified": True},
        {"type": "restraint_signal", "verified": True},
    ]
    print("\n--- Scenario 4: Restraint-Heavy (L2+L3) ---")
    r = analyze_bundle(restraint)
    print(f"Grade: {r['grade']}")
    print(f"Coverage: {r['coverage']}")
    print(f"Trust: {r['weighted_trust']}")
    print(f"L3 items prove what agent CHOSE NOT TO DO")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = analyze_bundle(data.get("evidence", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
