#!/usr/bin/env python3
"""
intent-inference.py — Infer agent intent from receipt patterns.

Thread insight (santaclawd Feb 25): capability (did they deliver?) vs intent 
(will they act in your interest?). Receipts prove capability directly.
Intent must be inferred from the PATTERN of receipts over time.

Samuelson (1938): revealed preference > stated preference.
"""

import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta

# Intent signals derived from receipt patterns
INTENT_SIGNALS = {
    "scope_adherence": {
        "desc": "Stayed within contracted scope across deliveries",
        "weight": 0.3,
    },
    "restraint": {
        "desc": "Had capability to overstep but didn't (e.g., had write access, only read)",
        "weight": 0.25,
    },
    "consistency": {
        "desc": "Behavior stable across different contexts/principals",
        "weight": 0.2,
    },
    "dispute_initiation": {
        "desc": "Ratio of disputes initiated vs received (lower = better intent signal)",
        "weight": 0.15,
    },
    "voluntary_disclosure": {
        "desc": "Proactively reported issues/limitations before asked",
        "weight": 0.1,
    },
}


def infer_intent(receipts: list[dict]) -> dict:
    """Infer intent from a sequence of receipts."""
    if not receipts:
        return {"intent_score": 0.0, "confidence": 0.0, "signals": {}, "verdict": "unknown"}
    
    n = len(receipts)
    signals = {}
    
    # Scope adherence: fraction of deliveries marked in-scope
    in_scope = sum(1 for r in receipts if r.get("in_scope", True))
    scope_score = in_scope / n
    signals["scope_adherence"] = round(scope_score, 3)
    
    # Restraint: had elevated access but didn't use it
    restrained = sum(1 for r in receipts if r.get("had_elevated_access") and not r.get("used_elevated_access"))
    restraint_opportunities = sum(1 for r in receipts if r.get("had_elevated_access"))
    restraint_score = restrained / restraint_opportunities if restraint_opportunities > 0 else 0.5  # neutral if no opportunities
    signals["restraint"] = round(restraint_score, 3)
    
    # Consistency: low variance in quality scores across different principals
    principals = {}
    for r in receipts:
        p = r.get("principal", "unknown")
        q = r.get("quality_score", 0.5)
        principals.setdefault(p, []).append(q)
    
    if len(principals) > 1:
        means = [sum(v)/len(v) for v in principals.values()]
        overall_mean = sum(means) / len(means)
        variance = sum((m - overall_mean)**2 for m in means) / len(means)
        consistency_score = max(0, 1.0 - math.sqrt(variance) * 2)  # penalize high variance
    else:
        consistency_score = 0.5  # can't assess with single principal
    signals["consistency"] = round(consistency_score, 3)
    
    # Dispute ratio: disputes initiated / total interactions
    disputes_initiated = sum(1 for r in receipts if r.get("dispute_initiated"))
    dispute_score = max(0, 1.0 - (disputes_initiated / n) * 5)  # heavily penalize frequent disputers
    signals["dispute_initiation"] = round(dispute_score, 3)
    
    # Voluntary disclosure
    disclosures = sum(1 for r in receipts if r.get("voluntary_disclosure"))
    disclosure_score = min(disclosures / max(n * 0.1, 1), 1.0)  # 10% disclosure rate = max
    signals["voluntary_disclosure"] = round(disclosure_score, 3)
    
    # Weighted intent score
    intent_score = sum(
        signals[name] * info["weight"]
        for name, info in INTENT_SIGNALS.items()
    )
    
    # Confidence scales with receipt count (Bayesian-flavored)
    # Need ~20 receipts for high confidence
    confidence = 1.0 - math.exp(-n / 10.0)
    
    # Verdict
    effective = intent_score * confidence
    if effective > 0.7:
        verdict = "high_intent"
    elif effective > 0.4:
        verdict = "moderate_intent"
    elif effective > 0.2:
        verdict = "low_intent"
    else:
        verdict = "unknown_or_adversarial"
    
    return {
        "intent_score": round(intent_score, 3),
        "confidence": round(confidence, 3),
        "effective_score": round(effective, 3),
        "n_receipts": n,
        "n_principals": len(principals),
        "signals": signals,
        "verdict": verdict,
        "method": "revealed_preference_inference",
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


def demo():
    """Demo with synthetic agent histories."""
    print("=== Intent Inference (Revealed Preference) ===\n")
    
    cases = {
        "reliable agent (50 receipts, 3 principals)": [
            {"principal": ["alice", "bob", "carol"][i % 3],
             "quality_score": 0.85 + (i % 5) * 0.03,
             "in_scope": True,
             "had_elevated_access": i % 4 == 0,
             "used_elevated_access": False,
             "voluntary_disclosure": i % 8 == 0}
            for i in range(50)
        ],
        "scope creeper (20 receipts)": [
            {"principal": "alice",
             "quality_score": 0.9,
             "in_scope": i < 12,  # first 12 in scope, then creeps
             "had_elevated_access": i > 10,
             "used_elevated_access": i > 14,
             "dispute_initiated": i > 16}
            for i in range(20)
        ],
        "new agent (3 receipts)": [
            {"principal": "bob", "quality_score": 0.8, "in_scope": True}
            for _ in range(3)
        ],
        "adversarial (10 receipts, all disputes)": [
            {"principal": "carol",
             "quality_score": 0.3,
             "in_scope": False,
             "dispute_initiated": True,
             "had_elevated_access": True,
             "used_elevated_access": True}
            for _ in range(10)
        ],
    }
    
    for name, receipts in cases.items():
        result = infer_intent(receipts)
        print(f"  {name}:")
        print(f"    Intent: {result['intent_score']} × Confidence: {result['confidence']} = {result['effective_score']} ({result['verdict']})")
        print(f"    Signals: {result['signals']}")
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        receipts = json.loads(sys.stdin.read())
        result = infer_intent(receipts)
        print(json.dumps(result, indent=2))
    else:
        demo()
