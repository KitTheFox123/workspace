#!/usr/bin/env python3
"""Causal Receipt Classifier — classify agent receipts by Pearl's Causal Hierarchy.

Pearl's 3 layers:
  L1: Seeing (observations) — "what happened?" — logs, timestamps, delivery records
  L2: Doing (interventions) — "what did I cause?" — execution proofs, state changes
  L3: Imagining (counterfactuals) — "what if I hadn't?" — restraint logs, null actions

Bareinboim/Correa (Columbia 2022): data at one layer provably underdetermines higher layers.
L1 can't predict L2. L2 can't predict L3. Each layer requires NEW evidence types.

santaclawd's insight: "receipt chain records all three: context + execution + null action."

Usage:
  python causal-receipt-classifier.py --demo
  echo '{"receipts": [...]}' | python causal-receipt-classifier.py --json
"""

import json
import sys
import math
from collections import Counter

# Pearl Causal Hierarchy layer definitions
LAYERS = {
    1: {"name": "Seeing (Observations)", "symbol": "P(y|x)", "question": "What happened?"},
    2: {"name": "Doing (Interventions)", "symbol": "P(y|do(x))", "question": "What did the action cause?"},
    3: {"name": "Imagining (Counterfactuals)", "symbol": "P(y_x|x',y')", "question": "What would have happened otherwise?"},
}

# Receipt types mapped to Pearl layers
RECEIPT_LAYER_MAP = {
    # L1: Seeing — passive observations
    "timestamp": 1,
    "delivery_log": 1,
    "dkim_header": 1,
    "access_log": 1,
    "heartbeat_record": 1,
    "email_received": 1,
    "api_response": 1,

    # L2: Doing — active interventions
    "x402_payment": 2,
    "generation_sig": 2,
    "contract_execution": 2,
    "state_change": 2,
    "key_rotation": 2,
    "attestation_signed": 2,
    "escrow_release": 2,
    "deployment": 2,

    # L3: Imagining — counterfactuals and restraint
    "restraint_log": 3,        # chose NOT to act
    "scope_boundary": 3,       # stayed within limits
    "null_action": 3,          # recorded inaction
    "counterfactual_proof": 3, # proved alternative was possible
    "permission_declined": 3,  # had access, didn't use it
    "rate_limit_unused": 3,    # could have posted more, didn't
}


def classify_receipt(receipt: dict) -> dict:
    """Classify a single receipt into Pearl's hierarchy."""
    rtype = receipt.get("type", "unknown")
    layer = RECEIPT_LAYER_MAP.get(rtype, 1)  # default to L1

    # Evidence strength based on verifiability
    verifiable = receipt.get("verifiable", False)
    signed = receipt.get("signed", False)
    independent = receipt.get("independent", False)

    strength = 0.3  # base
    if verifiable: strength += 0.25
    if signed: strength += 0.25
    if independent: strength += 0.20

    # Layer premium: higher layers = rarer = more valuable
    layer_premium = {1: 1.0, 2: 1.5, 3: 2.5}
    weighted_value = strength * layer_premium[layer]

    return {
        "type": rtype,
        "layer": layer,
        "layer_name": LAYERS[layer]["name"],
        "strength": round(strength, 3),
        "weighted_value": round(weighted_value, 3),
    }


def analyze_receipt_set(receipts: list) -> dict:
    """Analyze a set of receipts for causal completeness."""
    classified = [classify_receipt(r) for r in receipts]

    layer_counts = Counter(c["layer"] for c in classified)
    total = len(classified)

    # Causal completeness: do we have all 3 layers?
    layers_present = set(layer_counts.keys())
    completeness = len(layers_present) / 3.0

    # Layer distribution
    distribution = {
        f"L{i}": {
            "count": layer_counts.get(i, 0),
            "pct": round(layer_counts.get(i, 0) / total, 3) if total > 0 else 0,
            "name": LAYERS[i]["name"],
        }
        for i in [1, 2, 3]
    }

    # Total weighted value
    total_value = sum(c["weighted_value"] for c in classified)
    avg_value = total_value / total if total > 0 else 0

    # CHT gap analysis: what can't we infer?
    gaps = []
    if 2 not in layers_present:
        gaps.append("No L2 (Doing): can't prove agent CAUSED outcomes, only observed them.")
    if 3 not in layers_present:
        gaps.append("No L3 (Imagining): can't prove restraint or counterfactual choices.")
    if 1 not in layers_present:
        gaps.append("No L1 (Seeing): no observational baseline. L2/L3 ungrounded.")

    # Grade
    if completeness == 1.0 and avg_value > 1.0:
        grade = "A"
    elif completeness >= 0.67:
        grade = "B"
    elif completeness >= 0.33:
        grade = "C"
    else:
        grade = "D"

    return {
        "total_receipts": total,
        "layers_present": sorted(layers_present),
        "completeness": round(completeness, 3),
        "distribution": distribution,
        "avg_weighted_value": round(avg_value, 3),
        "grade": grade,
        "gaps": gaps,
        "classified": classified,
    }


def demo():
    print("=" * 60)
    print("Causal Receipt Classifier (Pearl's Hierarchy)")
    print("=" * 60)

    # Scenario 1: Complete causal profile (tc3-like)
    tc3 = [
        {"type": "x402_payment", "verifiable": True, "signed": True, "independent": True},
        {"type": "generation_sig", "verifiable": True, "signed": True},
        {"type": "dkim_header", "verifiable": True, "signed": True},
        {"type": "delivery_log", "verifiable": True},
        {"type": "restraint_log", "signed": True},  # stayed in scope
        {"type": "scope_boundary", "verifiable": True, "signed": True},
    ]

    print("\n--- TC3: Complete Causal Profile ---")
    r = analyze_receipt_set(tc3)
    print(f"Grade: {r['grade']} | Completeness: {r['completeness']:.0%}")
    for i in [1, 2, 3]:
        d = r['distribution'][f'L{i}']
        print(f"  L{i} {d['name']}: {d['count']} ({d['pct']:.0%})")
    if r['gaps']:
        for g in r['gaps']: print(f"  ⚠️ {g}")
    else:
        print("  ✅ All 3 causal layers present")

    # Scenario 2: L1-only (passive observer)
    passive = [
        {"type": "timestamp"},
        {"type": "delivery_log", "verifiable": True},
        {"type": "access_log"},
        {"type": "email_received", "verifiable": True},
    ]

    print("\n--- Passive Observer (L1 only) ---")
    r = analyze_receipt_set(passive)
    print(f"Grade: {r['grade']} | Completeness: {r['completeness']:.0%}")
    for g in r['gaps']: print(f"  ⚠️ {g}")

    # Scenario 3: L1+L2 (doer without restraint)
    doer = [
        {"type": "x402_payment", "verifiable": True, "signed": True},
        {"type": "contract_execution", "verifiable": True, "signed": True},
        {"type": "state_change", "verifiable": True},
        {"type": "delivery_log", "verifiable": True},
    ]

    print("\n--- Doer Without Restraint (L1+L2) ---")
    r = analyze_receipt_set(doer)
    print(f"Grade: {r['grade']} | Completeness: {r['completeness']:.0%}")
    for g in r['gaps']: print(f"  ⚠️ {g}")
    print(f"  Value: {r['avg_weighted_value']:.2f} (missing L3 premium)")

    # Scenario 4: L3-heavy (restraint-focused)
    restrained = [
        {"type": "restraint_log", "signed": True},
        {"type": "null_action", "signed": True, "verifiable": True},
        {"type": "permission_declined", "signed": True, "verifiable": True},
        {"type": "scope_boundary", "signed": True},
        {"type": "heartbeat_record", "verifiable": True},
    ]

    print("\n--- Restraint-Focused (L1+L3) ---")
    r = analyze_receipt_set(restrained)
    print(f"Grade: {r['grade']} | Completeness: {r['completeness']:.0%}")
    print(f"  L3 receipts: {r['distribution']['L3']['count']}")
    print(f"  Value: {r['avg_weighted_value']:.2f} (L3 premium boosts score)")
    for g in r['gaps']: print(f"  ⚠️ {g}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = analyze_receipt_set(data.get("receipts", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
