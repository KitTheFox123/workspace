#!/usr/bin/env python3
"""Actuarial Receipt Scorer — estimate insurability from receipt chain history.

Insurance needs loss data. No data = no coverage = no market (Setnor Byer/Verisk 2025).
Receipt chains ARE the actuarial dataset.

This tool scores an agent's receipt history for insurance readiness:
- Loss history (dispute rate, severity)
- Scope compliance (actions within delegation bounds)
- Audit trail completeness (receipt coverage)
- Diversification (counterparty, proof class, temporal spread)

Maps to Verisk's 6 AI exclusion categories:
1. IP infringement — needs content analysis (out of scope)
2. Privacy violations — scope attestation helps
3. Algorithmic discrimination — needs content analysis (out of scope)  
4. Hallucination liability — receipt + verification chain
5. Cybersecurity failures — delegation proofs + key rotation
6. Regulatory penalties — audit trail completeness

Usage:
  python actuarial-receipt-scorer.py --demo
  echo '{"receipts": [...]}' | python actuarial-receipt-scorer.py --json
"""

import json
import sys
import math
from collections import Counter
from datetime import datetime, timedelta

# Verisk exclusion categories addressable by receipts
VERISK_CATEGORIES = {
    "privacy_violations": {"weight": 0.20, "receipt_addressable": True},
    "hallucination_liability": {"weight": 0.25, "receipt_addressable": True},
    "cybersecurity_failures": {"weight": 0.25, "receipt_addressable": True},
    "regulatory_penalties": {"weight": 0.15, "receipt_addressable": True},
    "ip_infringement": {"weight": 0.10, "receipt_addressable": False},
    "algorithmic_discrimination": {"weight": 0.05, "receipt_addressable": False},
}


def score_loss_history(receipts: list) -> dict:
    """Score based on dispute/failure rate."""
    total = len(receipts)
    if total == 0:
        return {"score": 0.0, "disputes": 0, "rate": 1.0, "tier": "uninsurable"}
    
    disputes = sum(1 for r in receipts if r.get("disputed", False))
    failures = sum(1 for r in receipts if r.get("outcome") == "failed")
    bad = disputes + failures
    rate = bad / total
    
    # Bayesian: Beta(good+1, bad+1) posterior mean
    bayesian_rate = (bad + 1) / (total + 2)
    
    score = max(0, 1.0 - bayesian_rate * 3)  # 33% dispute rate = 0
    tier = (
        "preferred" if score > 0.8 else
        "standard" if score > 0.5 else
        "substandard" if score > 0.2 else
        "uninsurable"
    )
    
    return {
        "score": round(score, 3),
        "total_contracts": total,
        "disputes": disputes,
        "failures": failures,
        "observed_rate": round(rate, 3),
        "bayesian_rate": round(bayesian_rate, 3),
        "tier": tier,
    }


def score_scope_compliance(receipts: list) -> dict:
    """Score based on whether actions stayed within delegated scope."""
    total = len(receipts)
    if total == 0:
        return {"score": 0.0, "in_scope": 0, "out_of_scope": 0}
    
    in_scope = sum(1 for r in receipts if r.get("in_scope", True))
    out_of_scope = total - in_scope
    
    score = in_scope / total
    return {
        "score": round(score, 3),
        "in_scope": in_scope,
        "out_of_scope": out_of_scope,
        "has_delegation_proof": sum(1 for r in receipts if r.get("delegation_proof")),
    }


def score_audit_completeness(receipts: list) -> dict:
    """Score audit trail quality."""
    if not receipts:
        return {"score": 0.0, "completeness": 0.0}
    
    required_fields = ["timestamp", "attester", "action", "outcome"]
    optional_fields = ["proof_class", "delegation_proof", "evidence_hash", "counterparty"]
    
    completeness_scores = []
    for r in receipts:
        required_present = sum(1 for f in required_fields if r.get(f)) / len(required_fields)
        optional_present = sum(1 for f in optional_fields if r.get(f)) / len(optional_fields)
        completeness_scores.append(required_present * 0.7 + optional_present * 0.3)
    
    avg = sum(completeness_scores) / len(completeness_scores)
    
    # Proof class diversity bonus
    proof_classes = set(r.get("proof_class", "none") for r in receipts)
    diversity_bonus = min(0.1, len(proof_classes) * 0.025)
    
    return {
        "score": round(min(1.0, avg + diversity_bonus), 3),
        "avg_completeness": round(avg, 3),
        "proof_class_diversity": len(proof_classes),
        "diversity_bonus": round(diversity_bonus, 3),
    }


def score_diversification(receipts: list) -> dict:
    """Score counterparty and temporal diversification."""
    if not receipts:
        return {"score": 0.0}
    
    counterparties = set(r.get("counterparty", "unknown") for r in receipts)
    attesters = set(r.get("attester", "unknown") for r in receipts)
    
    # Counterparty concentration (Herfindahl index)
    cp_counts = Counter(r.get("counterparty", "unknown") for r in receipts)
    total = len(receipts)
    hhi = sum((c/total)**2 for c in cp_counts.values())
    concentration_score = 1.0 - hhi  # Lower HHI = more diversified
    
    # Temporal spread
    timestamps = sorted(r.get("timestamp", 0) for r in receipts if r.get("timestamp"))
    if len(timestamps) >= 2:
        span_days = (timestamps[-1] - timestamps[0]) / 86400
        temporal_score = min(1.0, span_days / 90)  # 90 days = full score
    else:
        temporal_score = 0.0
    
    score = concentration_score * 0.5 + temporal_score * 0.3 + min(1.0, len(attesters) / 5) * 0.2
    
    return {
        "score": round(score, 3),
        "unique_counterparties": len(counterparties),
        "unique_attesters": len(attesters),
        "herfindahl_index": round(hhi, 3),
        "temporal_span_days": round((timestamps[-1] - timestamps[0]) / 86400, 1) if len(timestamps) >= 2 else 0,
    }


def verisk_coverage(audit_score: float, scope_score: float, loss_score: float) -> dict:
    """Map scores to Verisk exclusion category coverage."""
    coverage = {}
    for cat, info in VERISK_CATEGORIES.items():
        if not info["receipt_addressable"]:
            coverage[cat] = {"addressable": False, "score": 0.0, "status": "requires_content_analysis"}
        else:
            # Different categories weight different factors
            if cat == "privacy_violations":
                s = scope_score * 0.6 + audit_score * 0.4
            elif cat == "hallucination_liability":
                s = audit_score * 0.5 + loss_score * 0.5
            elif cat == "cybersecurity_failures":
                s = scope_score * 0.4 + audit_score * 0.4 + loss_score * 0.2
            elif cat == "regulatory_penalties":
                s = audit_score * 0.7 + scope_score * 0.3
            else:
                s = (audit_score + scope_score + loss_score) / 3
            
            status = "covered" if s > 0.7 else "partial" if s > 0.4 else "excluded"
            coverage[cat] = {"addressable": True, "score": round(s, 3), "status": status}
    
    return coverage


def analyze_insurability(receipts: list) -> dict:
    """Full insurability analysis."""
    loss = score_loss_history(receipts)
    scope = score_scope_compliance(receipts)
    audit = score_audit_completeness(receipts)
    diversification = score_diversification(receipts)
    
    # Composite insurability score
    composite = (
        loss["score"] * 0.35 +
        scope["score"] * 0.20 +
        audit["score"] * 0.25 +
        diversification["score"] * 0.20
    )
    
    # Premium multiplier (1.0 = standard, <1.0 = discount, >1.0 = surcharge)
    premium_multiplier = max(0.5, 2.5 - composite * 2.0)
    
    coverage = verisk_coverage(audit["score"], scope["score"], loss["score"])
    covered = sum(1 for v in coverage.values() if v["status"] == "covered")
    
    return {
        "composite_score": round(composite, 3),
        "premium_multiplier": round(premium_multiplier, 2),
        "insurance_tier": loss["tier"],
        "verisk_coverage": f"{covered}/6 categories covered",
        "loss_history": loss,
        "scope_compliance": scope,
        "audit_completeness": audit,
        "diversification": diversification,
        "verisk_detail": coverage,
    }


def demo():
    """Demo with agent receipt scenarios."""
    now = int(datetime.now().timestamp())
    day = 86400
    
    print("=" * 60)
    print("Actuarial Receipt Scorer")
    print("Based on Setnor Byer/Verisk 2025 AI exclusions")
    print("=" * 60)
    
    # Scenario 1: Kit's actual history (tc3 + clean track record)
    kit_receipts = [
        {"timestamp": now - 30*day, "attester": "bro_agent", "action": "research_delivery", "outcome": "success",
         "counterparty": "bro_agent", "proof_class": "payment", "delegation_proof": True, "evidence_hash": "abc123", "in_scope": True},
        {"timestamp": now - 25*day, "attester": "santaclawd", "action": "spec_review", "outcome": "success",
         "counterparty": "santaclawd", "proof_class": "generation", "evidence_hash": "def456", "in_scope": True},
        {"timestamp": now - 20*day, "attester": "gerundium", "action": "provenance_collab", "outcome": "success",
         "counterparty": "gerundium", "proof_class": "transport", "delegation_proof": True, "evidence_hash": "ghi789", "in_scope": True},
        {"timestamp": now - 15*day, "attester": "gendolf", "action": "isnad_attestation", "outcome": "success",
         "counterparty": "gendolf", "proof_class": "witness", "evidence_hash": "jkl012", "in_scope": True},
        {"timestamp": now - 5*day, "attester": "braindiff", "action": "trust_quality_review", "outcome": "success",
         "counterparty": "braindiff", "proof_class": "witness", "delegation_proof": True, "evidence_hash": "mno345", "in_scope": True},
    ]
    
    print("\n--- Kit Fox: 5 clean contracts, 5 counterparties ---")
    result = analyze_insurability(kit_receipts)
    print(f"Tier: {result['insurance_tier']} | Score: {result['composite_score']} | Premium: {result['premium_multiplier']}x")
    print(f"Verisk: {result['verisk_coverage']}")
    print(f"Loss rate: {result['loss_history']['bayesian_rate']:.1%} | Scope: {result['scope_compliance']['score']:.0%}")
    
    # Scenario 2: Risky agent (disputes + scope violations)
    risky_receipts = [
        {"timestamp": now - 60*day, "attester": "agent_a", "action": "task", "outcome": "success", "counterparty": "agent_a", "in_scope": True},
        {"timestamp": now - 50*day, "attester": "agent_a", "action": "task", "outcome": "failed", "counterparty": "agent_a", "disputed": True, "in_scope": False},
        {"timestamp": now - 40*day, "attester": "agent_b", "action": "task", "outcome": "success", "counterparty": "agent_b", "in_scope": True},
        {"timestamp": now - 30*day, "attester": "agent_a", "action": "task", "outcome": "failed", "counterparty": "agent_a", "disputed": True, "in_scope": False},
        {"timestamp": now - 20*day, "attester": "agent_a", "action": "task", "outcome": "success", "counterparty": "agent_a", "in_scope": True},
    ]
    
    print("\n--- Risky Agent: 2 disputes, 2 scope violations ---")
    result = analyze_insurability(risky_receipts)
    print(f"Tier: {result['insurance_tier']} | Score: {result['composite_score']} | Premium: {result['premium_multiplier']}x")
    print(f"Verisk: {result['verisk_coverage']}")
    print(f"Loss rate: {result['loss_history']['bayesian_rate']:.1%} | Scope: {result['scope_compliance']['score']:.0%}")
    
    # Scenario 3: New agent (no history)
    print("\n--- New Agent: 0 receipts ---")
    result = analyze_insurability([])
    print(f"Tier: {result['insurance_tier']} | Score: {result['composite_score']} | Premium: {result['premium_multiplier']}x")
    print(f"Verisk: {result['verisk_coverage']}")
    
    # Scenario 4: High volume, concentrated counterparty
    concentrated = [
        {"timestamp": now - i*day, "attester": "same_agent", "action": "task", "outcome": "success",
         "counterparty": "same_agent", "proof_class": "payment", "evidence_hash": f"h{i}", "in_scope": True}
        for i in range(20)
    ]
    
    print("\n--- Concentrated: 20 clean but single counterparty ---")
    result = analyze_insurability(concentrated)
    print(f"Tier: {result['insurance_tier']} | Score: {result['composite_score']} | Premium: {result['premium_multiplier']}x")
    print(f"Diversification: {result['diversification']['score']} (HHI: {result['diversification']['herfindahl_index']})")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        print(json.dumps(analyze_insurability(data.get("receipts", [])), indent=2))
    else:
        demo()
