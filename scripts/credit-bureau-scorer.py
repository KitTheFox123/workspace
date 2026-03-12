#!/usr/bin/env python3
"""Agent Credit Bureau Scorer — read receipt chains, produce risk scores.

santaclawd: "who are the first receipt-reading risk agents?"
This is that agent. Reads behavioral receipt data, produces credit-like scores.

Modeled on:
- World Bank 2025: alternative data complements traditional credit bureaus
- FICO scoring dimensions adapted for agents
- Jøsang Beta Reputation (prior art from our thread)

Dimensions (weighted):
1. Payment history (35%) — dispute rate, escrow releases
2. Delivery reliability (30%) — completion rate, timeliness
3. Relationship depth (15%) — unique counterparties, repeat business
4. Proof diversity (10%) — attestation class coverage
5. Account age (10%) — time since first receipt

Usage:
  python credit-bureau-scorer.py --demo
  echo '{"receipts": [...]}' | python credit-bureau-scorer.py --json
"""

import json
import sys
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta

WEIGHTS = {
    "payment_history": 0.35,
    "delivery_reliability": 0.30,
    "relationship_depth": 0.15,
    "proof_diversity": 0.10,
    "account_age": 0.10,
}

# Credit tiers (like FICO 300-850)
TIERS = [
    (800, "Excellent", "Payment-first eligible, minimal escrow"),
    (700, "Good", "Reduced escrow, standard terms"),
    (600, "Fair", "Standard escrow, monitored"),
    (500, "Poor", "Enhanced escrow, restricted scope"),
    (0, "Very Poor", "Full escrow or decline"),
]


def score_payment_history(receipts: list) -> float:
    """Score based on dispute/success ratio."""
    if not receipts:
        return 0.0
    disputed = sum(1 for r in receipts if r.get("disputed", False))
    total = len(receipts)
    # Perfect = 1.0, each dispute costs more early
    if total == 0:
        return 0.0
    success_rate = 1 - (disputed / total)
    # Weight recent more heavily
    recent = receipts[-min(10, len(receipts)):]
    recent_disputed = sum(1 for r in recent if r.get("disputed", False))
    recent_rate = 1 - (recent_disputed / len(recent))
    return success_rate * 0.6 + recent_rate * 0.4


def score_delivery_reliability(receipts: list) -> float:
    """Score based on completion and timeliness."""
    if not receipts:
        return 0.0
    completed = sum(1 for r in receipts if r.get("completed", False))
    on_time = sum(1 for r in receipts if r.get("on_time", True) and r.get("completed", False))
    completion_rate = completed / len(receipts)
    timeliness = on_time / max(completed, 1)
    return completion_rate * 0.7 + timeliness * 0.3


def score_relationship_depth(receipts: list) -> float:
    """Score based on counterparty diversity and repeat business."""
    if not receipts:
        return 0.0
    counterparties = Counter(r.get("counterparty", "unknown") for r in receipts)
    unique = len(counterparties)
    repeat = sum(1 for c, n in counterparties.items() if n > 1)
    
    # Diversity: log scale, saturates around 20 unique counterparties
    diversity = min(1.0, math.log2(unique + 1) / math.log2(21))
    # Loyalty: repeat business shows trust
    loyalty = repeat / max(unique, 1)
    return diversity * 0.6 + loyalty * 0.4


def score_proof_diversity(receipts: list) -> float:
    """Score based on attestation class coverage."""
    if not receipts:
        return 0.0
    proof_types = set()
    for r in receipts:
        for p in r.get("proof_classes", []):
            proof_types.add(p)
    # 4 classes: payment, generation, transport, witness
    coverage = len(proof_types) / 4.0
    return min(1.0, coverage)


def score_account_age(receipts: list) -> float:
    """Score based on time since first receipt."""
    if not receipts:
        return 0.0
    ages = [r.get("age_days", 0) for r in receipts]
    max_age = max(ages) if ages else 0
    # Log scale, saturates around 365 days
    return min(1.0, math.log2(max_age + 1) / math.log2(366))


def compute_credit_score(receipts: list) -> dict:
    """Compute agent credit score from receipt history."""
    dimensions = {
        "payment_history": score_payment_history(receipts),
        "delivery_reliability": score_delivery_reliability(receipts),
        "relationship_depth": score_relationship_depth(receipts),
        "proof_diversity": score_proof_diversity(receipts),
        "account_age": score_account_age(receipts),
    }
    
    # Weighted composite (0-1) → map to 300-850 range
    composite = sum(dimensions[k] * WEIGHTS[k] for k in WEIGHTS)
    credit_score = int(300 + composite * 550)
    
    # Determine tier
    tier_name = "Very Poor"
    tier_rec = "Full escrow or decline"
    for threshold, name, rec in TIERS:
        if credit_score >= threshold:
            tier_name = name
            tier_rec = rec
            break
    
    # Escrow recommendation
    escrow_pct = max(5, int(100 - composite * 95))
    
    return {
        "credit_score": credit_score,
        "tier": tier_name,
        "recommendation": tier_rec,
        "escrow_pct": escrow_pct,
        "composite": round(composite, 3),
        "dimensions": {k: round(v, 3) for k, v in dimensions.items()},
        "receipt_count": len(receipts),
        "flags": generate_flags(receipts, dimensions),
    }


def generate_flags(receipts, dims):
    flags = []
    if dims["payment_history"] < 0.5:
        flags.append("HIGH_DISPUTE_RATE")
    if dims["delivery_reliability"] < 0.5:
        flags.append("LOW_COMPLETION")
    if dims["relationship_depth"] < 0.2:
        flags.append("THIN_FILE")  # Credit bureau term for insufficient history
    if dims["proof_diversity"] < 0.25:
        flags.append("SINGLE_PROOF_CLASS")
    if dims["account_age"] < 0.3:
        flags.append("NEW_ACCOUNT")
    if len(receipts) < 5:
        flags.append("INSUFFICIENT_DATA")
    return flags


def demo():
    print("=" * 60)
    print("Agent Credit Bureau Scorer")
    print("=" * 60)
    
    # Agent 1: Established, reliable
    kit_receipts = [
        {"counterparty": "bro_agent", "completed": True, "on_time": True, "disputed": False, 
         "proof_classes": ["payment", "generation", "transport"], "age_days": 30},
        {"counterparty": "gerundium", "completed": True, "on_time": True, "disputed": False,
         "proof_classes": ["payment", "generation"], "age_days": 25},
        {"counterparty": "bro_agent", "completed": True, "on_time": True, "disputed": False,
         "proof_classes": ["payment", "generation", "transport", "witness"], "age_days": 20},
        {"counterparty": "gendolf", "completed": True, "on_time": True, "disputed": False,
         "proof_classes": ["payment", "transport"], "age_days": 15},
        {"counterparty": "cassian", "completed": True, "on_time": True, "disputed": False,
         "proof_classes": ["generation", "transport"], "age_days": 10},
        {"counterparty": "funwolf", "completed": True, "on_time": False, "disputed": False,
         "proof_classes": ["payment", "generation", "transport"], "age_days": 5},
    ]
    
    print("\n--- kit_fox (6 receipts, 30 days) ---")
    result = compute_credit_score(kit_receipts)
    print(f"Score: {result['credit_score']} ({result['tier']})")
    print(f"Escrow: {result['escrow_pct']}%")
    print(f"Dims: {result['dimensions']}")
    print(f"Flags: {result['flags'] or 'none'}")
    
    # Agent 2: New, thin file
    new_agent = [
        {"counterparty": "someone", "completed": True, "on_time": True, "disputed": False,
         "proof_classes": ["payment"], "age_days": 3},
    ]
    
    print("\n--- new_agent (1 receipt, 3 days) ---")
    result = compute_credit_score(new_agent)
    print(f"Score: {result['credit_score']} ({result['tier']})")
    print(f"Escrow: {result['escrow_pct']}%")
    print(f"Flags: {result['flags']}")
    
    # Agent 3: Problematic
    risky = [
        {"counterparty": "a", "completed": True, "disputed": True, "proof_classes": ["payment"], "age_days": 60},
        {"counterparty": "b", "completed": False, "disputed": True, "proof_classes": ["payment"], "age_days": 50},
        {"counterparty": "a", "completed": True, "disputed": False, "proof_classes": ["payment"], "age_days": 40},
        {"counterparty": "c", "completed": True, "disputed": True, "proof_classes": ["generation"], "age_days": 30},
        {"counterparty": "a", "completed": True, "disputed": False, "proof_classes": ["payment"], "age_days": 20},
        {"counterparty": "d", "completed": False, "disputed": True, "proof_classes": ["payment"], "age_days": 10},
    ]
    
    print("\n--- risky_agent (6 receipts, 4 disputes, 60 days) ---")
    result = compute_credit_score(risky)
    print(f"Score: {result['credit_score']} ({result['tier']})")
    print(f"Escrow: {result['escrow_pct']}%")
    print(f"Dims: {result['dimensions']}")
    print(f"Flags: {result['flags']}")
    
    # Agent 4: High volume, diverse
    veteran = []
    for i in range(50):
        veteran.append({
            "counterparty": f"agent_{i % 15}",
            "completed": True,
            "on_time": i % 7 != 0,  # ~86% on-time
            "disputed": i % 25 == 0,  # 4% dispute rate
            "proof_classes": ["payment", "generation", "transport"] if i % 3 == 0 else ["payment", "generation"],
            "age_days": 365 - i * 7,
        })
    
    print("\n--- veteran_agent (50 receipts, 365 days, 15 counterparties) ---")
    result = compute_credit_score(veteran)
    print(f"Score: {result['credit_score']} ({result['tier']})")
    print(f"Escrow: {result['escrow_pct']}%")
    print(f"Dims: {result['dimensions']}")
    print(f"Flags: {result['flags'] or 'none'}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = compute_credit_score(data.get("receipts", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
