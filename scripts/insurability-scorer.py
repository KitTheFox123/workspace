#!/usr/bin/env python3
"""Insurability Scorer — score agent receipts for insurance underwriting.

Post-Verisk CG-35-08 (Jan 2026): AI excluded from general liability.
Reinstatement path = auditable behavior via receipt chains.

Scores agent portfolios on dimensions insurers care about:
- Attestation completeness (proof classes)
- Behavioral consistency (CUSUM drift)
- Incident history (disputes, failures)
- Governance compliance (Ostrom principles)

Usage:
  python insurability-scorer.py --demo
  echo '{"agent": {...}}' | python insurability-scorer.py --json
"""

import json
import sys
import math


# Verisk-inspired risk factors
RISK_FACTORS = {
    "attestation_coverage": {
        "weight": 0.25,
        "description": "Proof class diversity and completeness",
    },
    "behavioral_stability": {
        "weight": 0.20,
        "description": "CUSUM drift rate over time",
    },
    "incident_history": {
        "weight": 0.20,
        "description": "Dispute and failure record",
    },
    "governance_compliance": {
        "weight": 0.15,
        "description": "Ostrom principle adherence",
    },
    "operational_maturity": {
        "weight": 0.10,
        "description": "Age, volume, consistency of operations",
    },
    "transparency": {
        "weight": 0.10,
        "description": "Audit trail completeness and accessibility",
    },
}

# Insurance tiers
TIERS = [
    {"name": "UNINSURABLE", "min": 0.0, "max": 0.3, "premium_mult": None, "note": "CG-35-08 excluded. No coverage available."},
    {"name": "HIGH_RISK", "min": 0.3, "max": 0.5, "premium_mult": 3.0, "note": "Specialty market only. Sublimits apply."},
    {"name": "STANDARD", "min": 0.5, "max": 0.7, "premium_mult": 1.5, "note": "Standard market with endorsements."},
    {"name": "PREFERRED", "min": 0.7, "max": 0.85, "premium_mult": 1.0, "note": "Full coverage, standard terms."},
    {"name": "PRIME", "min": 0.85, "max": 1.0, "premium_mult": 0.7, "note": "Best rates. Reduced deductibles."},
]


def score_attestation_coverage(agent: dict) -> float:
    """Score based on proof class diversity."""
    proof_classes = agent.get("proof_classes", [])
    total_classes = 4  # payment, generation, transport, witness
    coverage = len(set(proof_classes)) / total_classes
    
    # Bonus for verified proofs
    verified_pct = agent.get("verified_pct", 0)
    return min(1.0, coverage * 0.7 + verified_pct * 0.3)


def score_behavioral_stability(agent: dict) -> float:
    """Score based on drift metrics."""
    drift_alarms = agent.get("drift_alarms_30d", 0)
    total_observations = agent.get("observations_30d", 1)
    alarm_rate = drift_alarms / max(total_observations, 1)
    
    # Low alarm rate = stable = high score
    return max(0, 1.0 - alarm_rate * 10)


def score_incident_history(agent: dict) -> float:
    """Score based on disputes and failures."""
    total_contracts = agent.get("total_contracts", 0)
    disputes = agent.get("disputes", 0)
    failures = agent.get("failures", 0)
    
    if total_contracts == 0:
        return 0.3  # Unknown = risky
    
    success_rate = 1.0 - (disputes + failures) / total_contracts
    # Bonus for dispute resolution (not just avoidance)
    resolved_pct = agent.get("disputes_resolved_pct", 0)
    return success_rate * 0.8 + resolved_pct * 0.2


def score_governance(agent: dict) -> float:
    """Score based on Ostrom compliance."""
    ostrom_score = agent.get("ostrom_compliance", 0)  # 0-1
    has_dispute_mechanism = agent.get("has_dispute_mechanism", False)
    has_graduated_sanctions = agent.get("has_graduated_sanctions", False)
    
    base = ostrom_score * 0.6
    base += 0.2 if has_dispute_mechanism else 0
    base += 0.2 if has_graduated_sanctions else 0
    return min(1.0, base)


def score_maturity(agent: dict) -> float:
    """Score based on operational history."""
    age_days = agent.get("age_days", 0)
    total_receipts = agent.get("total_receipts", 0)
    
    # Log scale for both
    age_score = min(1.0, math.log1p(age_days) / math.log1p(365))
    volume_score = min(1.0, math.log1p(total_receipts) / math.log1p(1000))
    return age_score * 0.5 + volume_score * 0.5


def score_transparency(agent: dict) -> float:
    """Score based on audit trail quality."""
    has_provenance_log = agent.get("has_provenance_log", False)
    log_completeness = agent.get("log_completeness", 0)
    public_receipts = agent.get("public_receipts", False)
    
    score = 0
    if has_provenance_log:
        score += 0.4
    score += log_completeness * 0.4
    if public_receipts:
        score += 0.2
    return min(1.0, score)


def assess_insurability(agent: dict) -> dict:
    """Full insurability assessment."""
    scores = {
        "attestation_coverage": score_attestation_coverage(agent),
        "behavioral_stability": score_behavioral_stability(agent),
        "incident_history": score_incident_history(agent),
        "governance_compliance": score_governance(agent),
        "operational_maturity": score_maturity(agent),
        "transparency": score_transparency(agent),
    }
    
    # Weighted composite
    composite = sum(
        scores[k] * RISK_FACTORS[k]["weight"]
        for k in scores
    )
    
    # Determine tier
    tier = TIERS[0]
    for t in TIERS:
        if t["min"] <= composite < t["max"] or (t["max"] == 1.0 and composite >= t["min"]):
            tier = t
            break
    
    # Estimate annual premium (base: $1000 for standard agent)
    base_premium = 1000
    annual_premium = base_premium * tier["premium_mult"] if tier["premium_mult"] else None
    
    return {
        "agent": agent.get("name", "unknown"),
        "composite_score": round(composite, 3),
        "tier": tier["name"],
        "tier_note": tier["note"],
        "annual_premium_est": f"${annual_premium:.0f}" if annual_premium else "N/A (excluded)",
        "scores": {k: round(v, 3) for k, v in scores.items()},
        "weakest_factor": min(scores, key=scores.get),
        "strongest_factor": max(scores, key=scores.get),
        "recommendations": _recommendations(scores, tier),
    }


def _recommendations(scores, tier):
    recs = []
    if tier["name"] == "UNINSURABLE":
        recs.append("Add proof class diversity (need 3+ classes for minimum coverage)")
    weak = [(k, v) for k, v in scores.items() if v < 0.4]
    for k, v in sorted(weak, key=lambda x: x[1]):
        recs.append(f"Improve {k} ({v:.0%} → target 60%+)")
    if not recs:
        recs.append("Maintain current practices. Consider expanding proof classes for PRIME tier.")
    return recs


def demo():
    print("=" * 60)
    print("Insurability Scorer — Post-Verisk CG-35-08")
    print("AI excluded from liability. Receipts = reinstatement.")
    print("=" * 60)
    
    agents = [
        {
            "name": "kit_fox (established)",
            "proof_classes": ["payment", "generation", "transport"],
            "verified_pct": 0.9,
            "drift_alarms_30d": 1,
            "observations_30d": 90,
            "total_contracts": 3,
            "disputes": 0,
            "failures": 0,
            "disputes_resolved_pct": 1.0,
            "ostrom_compliance": 0.69,
            "has_dispute_mechanism": True,
            "has_graduated_sanctions": False,
            "age_days": 25,
            "total_receipts": 50,
            "has_provenance_log": True,
            "log_completeness": 0.85,
            "public_receipts": True,
        },
        {
            "name": "new_agent (no history)",
            "proof_classes": [],
            "verified_pct": 0,
            "drift_alarms_30d": 0,
            "observations_30d": 0,
            "total_contracts": 0,
            "disputes": 0,
            "failures": 0,
            "ostrom_compliance": 0,
            "has_dispute_mechanism": False,
            "has_graduated_sanctions": False,
            "age_days": 1,
            "total_receipts": 0,
            "has_provenance_log": False,
            "log_completeness": 0,
            "public_receipts": False,
        },
        {
            "name": "bad_actor (disputed)",
            "proof_classes": ["payment"],
            "verified_pct": 0.3,
            "drift_alarms_30d": 12,
            "observations_30d": 30,
            "total_contracts": 10,
            "disputes": 4,
            "failures": 2,
            "disputes_resolved_pct": 0.25,
            "ostrom_compliance": 0.2,
            "has_dispute_mechanism": False,
            "has_graduated_sanctions": False,
            "age_days": 60,
            "total_receipts": 15,
            "has_provenance_log": False,
            "log_completeness": 0.1,
            "public_receipts": False,
        },
    ]
    
    for agent in agents:
        print(f"\n--- {agent['name']} ---")
        result = assess_insurability(agent)
        print(f"Tier: {result['tier']} (score: {result['composite_score']})")
        print(f"Premium: {result['annual_premium_est']}")
        print(f"Weakest: {result['weakest_factor']} ({result['scores'][result['weakest_factor']]})")
        print(f"Strongest: {result['strongest_factor']} ({result['scores'][result['strongest_factor']]})")
        for rec in result['recommendations'][:2]:
            print(f"  → {rec}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = assess_insurability(data.get("agent", data))
        print(json.dumps(result, indent=2))
    else:
        demo()
