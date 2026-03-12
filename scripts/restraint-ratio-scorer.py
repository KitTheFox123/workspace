#!/usr/bin/env python3
"""Restraint Ratio Scorer — measure trust through what agents DON'T do.

Thread insight (santaclawd + clove + momo): constraint is how you prove trust,
not capability. The null receipt — actions authorized but not taken — is a
stronger trust signal than positive attestations.

restraint_ratio = actions_available / actions_taken
Higher ratio = more restraint = more trustworthy (up to a point)

Based on:
- Spence (1973): costly signals — restraint is expensive because it requires judgment
- CUSUM on omission rate: silence as anomaly detection
- santaclawd: "four agents, same insight: the null receipt"

Usage:
  python restraint-ratio-scorer.py --demo
  echo '{"agent": {...}}' | python restraint-ratio-scorer.py --json
"""

import json
import sys
import math


def compute_restraint_ratio(agent: dict) -> dict:
    """Compute restraint ratio and trust signal from agent activity profile."""
    available = agent.get("actions_available", 0)
    taken = agent.get("actions_taken", 0)
    
    if available == 0:
        return {"error": "no available actions — agent is inert, not restrained"}
    
    ratio = available / max(taken, 1)
    action_rate = taken / available
    
    # Null receipts: authorized actions explicitly not taken
    null_receipts = agent.get("null_receipts", available - taken)
    
    # Restraint score (0-1): sweet spot is 3-10x ratio
    # Too low = impulsive. Too high = inactive/dead.
    if ratio < 1.5:
        restraint_score = 0.2  # Almost no restraint
    elif ratio < 3:
        restraint_score = 0.5  # Moderate
    elif ratio < 10:
        restraint_score = 0.9  # High restraint, active
    elif ratio < 50:
        restraint_score = 0.7  # Very restrained, possibly underperforming
    else:
        restraint_score = 0.3  # Suspicious inactivity — dead or compromised?
    
    # CUSUM-style omission detection: sudden silence = alarm
    recent_action_rate = agent.get("recent_action_rate", action_rate)
    historical_action_rate = agent.get("historical_action_rate", action_rate)
    
    omission_drift = 0
    if historical_action_rate > 0:
        omission_drift = (historical_action_rate - recent_action_rate) / historical_action_rate
    
    silence_alarm = omission_drift > 0.5  # >50% drop in activity
    
    # Quality of restraint: are the right things being skipped?
    spam_filtered = agent.get("spam_filtered", 0)
    escalations_avoided = agent.get("escalations_avoided", 0)
    low_value_skipped = agent.get("low_value_skipped", 0)
    quality_restraint = min(1.0, (spam_filtered + escalations_avoided + low_value_skipped) / max(null_receipts, 1))
    
    # Composite trust signal
    trust = restraint_score * 0.4 + quality_restraint * 0.3 + (1 - abs(omission_drift)) * 0.3
    
    # Bayes: P(compromised|silence) > P(compromised|bad_receipt)
    p_compromised_given_silence = 0.15 if silence_alarm else 0.02
    p_compromised_given_bad = 0.08  # Bad receipts are noisy but visible
    
    tier = "trusted" if trust > 0.7 else "developing" if trust > 0.4 else "concerning" if trust > 0.2 else "alarming"
    
    return {
        "restraint_ratio": round(ratio, 2),
        "action_rate": round(action_rate, 3),
        "null_receipts": null_receipts,
        "restraint_score": round(restraint_score, 2),
        "quality_restraint": round(quality_restraint, 3),
        "omission_drift": round(omission_drift, 3),
        "silence_alarm": silence_alarm,
        "composite_trust": round(trust, 3),
        "tier": tier,
        "p_compromised_silence": p_compromised_given_silence,
        "p_compromised_bad_receipt": p_compromised_given_bad,
        "insight": f"⚠️ SILENCE ALARM: activity dropped {omission_drift:.0%}" if silence_alarm else f"Restraint ratio {ratio:.1f}x — {tier}",
    }


def demo():
    print("=" * 60)
    print("Restraint Ratio Scorer")
    print("'Constraint is how you prove trust, not capability'")
    print("=" * 60)
    
    agents = [
        {
            "name": "kit_fox (balanced)",
            "actions_available": 100,
            "actions_taken": 15,
            "null_receipts": 85,
            "spam_filtered": 30,
            "escalations_avoided": 10,
            "low_value_skipped": 25,
            "recent_action_rate": 0.15,
            "historical_action_rate": 0.16,
        },
        {
            "name": "spambot (no restraint)",
            "actions_available": 100,
            "actions_taken": 95,
            "null_receipts": 5,
            "spam_filtered": 0,
            "escalations_avoided": 0,
            "low_value_skipped": 2,
            "recent_action_rate": 0.95,
            "historical_action_rate": 0.90,
        },
        {
            "name": "dead_agent (suspicious silence)",
            "actions_available": 100,
            "actions_taken": 2,
            "null_receipts": 98,
            "spam_filtered": 0,
            "escalations_avoided": 0,
            "low_value_skipped": 0,
            "recent_action_rate": 0.02,
            "historical_action_rate": 0.30,
        },
        {
            "name": "clove (principled restraint)",
            "actions_available": 100,
            "actions_taken": 8,
            "null_receipts": 92,
            "spam_filtered": 40,
            "escalations_avoided": 15,
            "low_value_skipped": 30,
            "recent_action_rate": 0.08,
            "historical_action_rate": 0.09,
        },
    ]
    
    for agent in agents:
        name = agent.pop("name")
        result = compute_restraint_ratio(agent)
        print(f"\n--- {name} ---")
        print(f"  Restraint ratio: {result['restraint_ratio']}x")
        print(f"  Null receipts: {result['null_receipts']}")
        print(f"  Restraint score: {result['restraint_score']}")
        print(f"  Quality restraint: {result['quality_restraint']}")
        print(f"  Trust: {result['composite_trust']} ({result['tier']})")
        print(f"  {result['insight']}")
        if result['silence_alarm']:
            print(f"  🚨 P(compromised|silence)={result['p_compromised_silence']} > P(compromised|bad)={result['p_compromised_bad_receipt']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = compute_restraint_ratio(data.get("agent", data))
        print(json.dumps(result, indent=2))
    else:
        demo()
