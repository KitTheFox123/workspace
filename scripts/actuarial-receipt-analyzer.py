#!/usr/bin/env python3
"""Actuarial Receipt Analyzer — estimate insurability from receipt chain data.

Insurers need loss data to price coverage. No data = no policy.
Receipt chains ARE the actuarial dataset: scope, duration, outcome, dispute rate.

Based on:
- Setnor Byer/Verisk 2025: insurers adding AI-specific exclusions (no loss data)
- santaclawd: "receipt chain = actuarial dataset"
- Olson 1965: selective incentives for monitoring

Usage:
  python actuarial-receipt-analyzer.py --demo
  echo '{"receipts": [...]}' | python actuarial-receipt-analyzer.py --json
"""

import json
import sys
import math
from collections import defaultdict
from datetime import datetime

# Industry loss ratios for reference
INDUSTRY_BENCHMARKS = {
    "professional_liability": 0.65,  # E&O typical
    "cyber_liability": 0.72,         # High and rising
    "general_liability": 0.55,
    "agent_services": None,          # No data yet — that's the problem
}


def analyze_receipt_history(receipts: list) -> dict:
    """Analyze receipt chain for actuarial metrics."""
    if not receipts:
        return {"error": "no receipts", "insurable": False}
    
    n = len(receipts)
    
    # Core metrics
    disputes = [r for r in receipts if r.get("disputed", False)]
    successes = [r for r in receipts if r.get("outcome") == "success"]
    failures = [r for r in receipts if r.get("outcome") == "failure"]
    
    dispute_rate = len(disputes) / n
    success_rate = len(successes) / n
    failure_rate = len(failures) / n
    
    # Loss severity (average disputed amount / average contract value)
    total_value = sum(r.get("value", 0) for r in receipts)
    disputed_value = sum(r.get("value", 0) for r in disputes)
    avg_value = total_value / n if n > 0 else 0
    loss_severity = disputed_value / total_value if total_value > 0 else 0
    
    # Expected loss ratio = frequency × severity
    loss_ratio = dispute_rate * loss_severity if loss_severity > 0 else dispute_rate * 0.5
    
    # Proof class diversity (higher = more verifiable = lower risk)
    proof_classes = set()
    for r in receipts:
        proof_classes.update(r.get("proof_classes", []))
    diversity_factor = min(1.0, len(proof_classes) / 3)  # 3 classes = full credit
    
    # Temporal consistency (regular activity = lower risk)
    timestamps = sorted(r.get("timestamp", 0) for r in receipts if r.get("timestamp"))
    if len(timestamps) > 1:
        intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
        avg_interval = sum(intervals) / len(intervals)
        cv = (sum((i - avg_interval)**2 for i in intervals) / len(intervals))**0.5 / avg_interval if avg_interval > 0 else 1
        regularity = max(0, 1 - cv)  # Lower CV = more regular
    else:
        regularity = 0
    
    # Counterparty diversity (more unique partners = broader dataset)
    counterparties = set(r.get("counterparty", "unknown") for r in receipts)
    counterparty_diversity = min(1.0, len(counterparties) / 5)  # 5+ = full credit
    
    # Credibility factor (actuarial: how much to trust this agent's data vs population)
    # Bühlmann credibility: Z = n / (n + k), k typically 50-100
    k = 50  # experience needed for full credibility
    credibility = n / (n + k)
    
    # Risk-adjusted premium rate
    base_rate = 0.15  # 15% of contract value (high for new market)
    experience_mod = 1.0 + (loss_ratio - 0.10) * 2  # Center at 10% loss
    diversity_discount = 0.10 * diversity_factor  # Up to 10% discount for proof diversity
    regularity_discount = 0.05 * regularity  # Up to 5% for consistent activity
    
    premium_rate = max(0.05, base_rate * experience_mod - diversity_discount - regularity_discount)
    
    # Insurability assessment
    min_receipts = 10
    max_dispute_rate = 0.30
    insurable = n >= min_receipts and dispute_rate <= max_dispute_rate
    
    # Rating
    if loss_ratio < 0.05 and n >= 20:
        rating = "A"
        rating_desc = "Preferred risk — low loss ratio, sufficient history"
    elif loss_ratio < 0.15 and n >= 10:
        rating = "B"
        rating_desc = "Standard risk — acceptable loss history"
    elif loss_ratio < 0.30:
        rating = "C"
        rating_desc = "Substandard — elevated loss ratio, monitor closely"
    else:
        rating = "D"
        rating_desc = "Decline — insufficient data or excessive losses"
    
    return {
        "receipts_analyzed": n,
        "success_rate": round(success_rate, 3),
        "dispute_rate": round(dispute_rate, 3),
        "loss_severity": round(loss_severity, 3),
        "loss_ratio": round(loss_ratio, 3),
        "proof_class_diversity": round(diversity_factor, 3),
        "temporal_regularity": round(regularity, 3),
        "counterparty_diversity": round(counterparty_diversity, 3),
        "credibility_factor": round(credibility, 3),
        "premium_rate": round(premium_rate, 4),
        "insurable": insurable,
        "rating": rating,
        "rating_desc": rating_desc,
        "benchmarks": {
            "vs_professional_liability": f"{'below' if loss_ratio < 0.65 else 'above'} industry ({loss_ratio:.1%} vs 65%)",
            "vs_cyber_liability": f"{'below' if loss_ratio < 0.72 else 'above'} industry ({loss_ratio:.1%} vs 72%)",
        },
        "recommendations": generate_recs(n, dispute_rate, diversity_factor, credibility, loss_ratio),
    }


def generate_recs(n, dispute_rate, diversity, credibility, loss_ratio):
    recs = []
    if n < 10:
        recs.append(f"INSUFFICIENT DATA: {n} receipts, need 10+ for basic insurability")
    if n < 50:
        recs.append(f"LOW CREDIBILITY: {n}/50 receipts for full actuarial credibility (Bühlmann Z={n/(n+50):.2f})")
    if diversity < 0.67:
        recs.append("ADD PROOF CLASSES: 3+ independent proof types reduce fraud risk")
    if dispute_rate > 0.15:
        recs.append(f"HIGH DISPUTE RATE: {dispute_rate:.1%} — investigate root causes")
    if loss_ratio > 0.30:
        recs.append(f"LOSS RATIO CRITICAL: {loss_ratio:.1%} — may be uninsurable at any premium")
    if not recs:
        recs.append("Profile meets insurability criteria. Continue building receipt history.")
    return recs


def demo():
    print("=" * 60)
    print("Actuarial Receipt Analyzer")
    print("=" * 60)
    
    # Scenario 1: Established agent (kit_fox-like)
    established = [
        {"outcome": "success", "value": 100, "disputed": False, "proof_classes": ["payment", "generation", "transport"], "counterparty": f"agent_{i%5}", "timestamp": 1000 + i*86400}
        for i in range(48)
    ] + [
        {"outcome": "failure", "value": 150, "disputed": True, "proof_classes": ["payment"], "counterparty": "agent_bad", "timestamp": 1000 + 48*86400},
        {"outcome": "success", "value": 100, "disputed": True, "proof_classes": ["payment", "generation"], "counterparty": "agent_picky", "timestamp": 1000 + 49*86400},
    ]
    
    print("\n--- Established Agent (50 receipts, 2 disputes) ---")
    r = analyze_receipt_history(established)
    print(f"Rating: {r['rating']} — {r['rating_desc']}")
    print(f"Loss ratio: {r['loss_ratio']:.1%} | Dispute rate: {r['dispute_rate']:.1%}")
    print(f"Premium rate: {r['premium_rate']:.2%} of contract value")
    print(f"Credibility: {r['credibility_factor']:.2f} (Bühlmann)")
    print(f"Insurable: {r['insurable']}")
    
    # Scenario 2: New agent (cold start)
    new_agent = [
        {"outcome": "success", "value": 50, "disputed": False, "proof_classes": ["payment"], "counterparty": "agent_0", "timestamp": 1000 + i*86400}
        for i in range(3)
    ]
    
    print("\n--- New Agent (3 receipts, 0 disputes) ---")
    r = analyze_receipt_history(new_agent)
    print(f"Rating: {r['rating']} — {r['rating_desc']}")
    print(f"Credibility: {r['credibility_factor']:.2f}")
    print(f"Insurable: {r['insurable']}")
    for rec in r['recommendations']:
        print(f"  ⚠️ {rec}")
    
    # Scenario 3: Risky agent
    risky = [
        {"outcome": "success" if i % 3 != 0 else "failure", "value": 200, "disputed": i % 3 == 0, "proof_classes": ["payment"], "counterparty": "agent_0", "timestamp": 1000 + i*3600}
        for i in range(15)
    ]
    
    print("\n--- Risky Agent (15 receipts, 33% dispute rate, single counterparty) ---")
    r = analyze_receipt_history(risky)
    print(f"Rating: {r['rating']} — {r['rating_desc']}")
    print(f"Loss ratio: {r['loss_ratio']:.1%} | Dispute rate: {r['dispute_rate']:.1%}")
    print(f"Premium rate: {r['premium_rate']:.2%}")
    print(f"Insurable: {r['insurable']}")
    for rec in r['recommendations']:
        print(f"  🚨 {rec}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        print(json.dumps(analyze_receipt_history(data.get("receipts", [])), indent=2))
    else:
        demo()
