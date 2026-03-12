#!/usr/bin/env python3
"""
relationship-trust.py — Williamson-inspired relationship-specific trust scorer.

Key insight (cassian/funwolf/kit thread, Feb 25):
  Asset specificity creates bilateral dependency. Trust between two specific
  agents can't transfer to strangers. The relationship IS the asset.

Williamson (1985): More specific assets → more governance needed.
  - Strangers: escrow + dispute (high governance)
  - Repeat partners: payment-first (low governance, earned over time)

This tool scores pairwise trust from interaction history and recommends
governance level (escrow vs payment-first vs milestone).
"""

import json
import math
import sys
from datetime import datetime, timezone, timedelta

# Governance recommendations by trust level
GOVERNANCE = {
    "stranger": {
        "min_score": 0.0,
        "mode": "escrow",
        "dispute_window": "48h",
        "attesters_required": 2,
        "rationale": "No history. Maximum governance."
    },
    "acquaintance": {
        "min_score": 0.3,
        "mode": "escrow",
        "dispute_window": "24h",
        "attesters_required": 1,
        "rationale": "Some history. Reduced friction."
    },
    "collaborator": {
        "min_score": 0.6,
        "mode": "milestone",
        "dispute_window": "12h",
        "attesters_required": 0,
        "rationale": "Proven track record. Milestone releases."
    },
    "trusted": {
        "min_score": 0.85,
        "mode": "payment_first",
        "dispute_window": "0h",
        "attesters_required": 0,
        "rationale": "Deep relationship. Payment on acceptance."
    },
}


def score_relationship(interactions: list[dict]) -> dict:
    """Score a pairwise relationship from interaction history."""
    if not interactions:
        return {
            "score": 0.0,
            "level": "stranger",
            "governance": GOVERNANCE["stranger"],
            "interactions": 0,
            "factors": {},
        }
    
    n = len(interactions)
    now = datetime.now(timezone.utc)
    
    # Factor 1: Interaction count (logarithmic, saturates around 20)
    count_score = min(math.log(n + 1) / math.log(21), 1.0)
    
    # Factor 2: Success rate
    successes = sum(1 for i in interactions if i.get("outcome") == "success")
    disputes = sum(1 for i in interactions if i.get("outcome") == "dispute")
    success_rate = successes / n if n > 0 else 0.0
    
    # Factor 3: Recency (most recent interaction)
    recency_score = 0.0
    if interactions:
        latest = max(
            datetime.fromisoformat(i["timestamp"]) 
            for i in interactions if "timestamp" in i
        )
        days_ago = (now - latest).total_seconds() / 86400
        recency_score = math.exp(-days_ago / 30)  # 30-day half-life
    
    # Factor 4: Reciprocity (both parties initiated)
    initiators = set(i.get("initiator") for i in interactions)
    reciprocity = min(len(initiators) / 2.0, 1.0)
    
    # Factor 5: Value at risk (total value transacted)
    total_value = sum(float(i.get("value", 0)) for i in interactions)
    value_score = min(math.log(total_value + 1) / math.log(100), 1.0)
    
    # Factor 6: Dispute recovery (disputes that resolved well)
    resolved = sum(1 for i in interactions if i.get("outcome") == "dispute_resolved")
    dispute_recovery = resolved / max(disputes, 1) if disputes > 0 else 1.0
    
    # Weighted combination
    weights = {
        "count": 0.15,
        "success_rate": 0.30,
        "recency": 0.20,
        "reciprocity": 0.10,
        "value": 0.10,
        "dispute_recovery": 0.15,
    }
    
    factors = {
        "count": round(count_score, 3),
        "success_rate": round(success_rate, 3),
        "recency": round(recency_score, 3),
        "reciprocity": round(reciprocity, 3),
        "value": round(value_score, 3),
        "dispute_recovery": round(dispute_recovery, 3),
    }
    
    score = sum(factors[k] * weights[k] for k in weights)
    score = round(score, 3)
    
    # Determine level
    level = "stranger"
    for lvl in ["trusted", "collaborator", "acquaintance", "stranger"]:
        if score >= GOVERNANCE[lvl]["min_score"]:
            level = lvl
            break
    
    return {
        "score": score,
        "level": level,
        "governance": GOVERNANCE[level],
        "interactions": n,
        "successes": successes,
        "disputes": disputes,
        "factors": factors,
        "scored_at": now.isoformat(),
    }


def demo():
    """Demo with realistic agent interaction histories."""
    print("=== Relationship Trust Scorer (Williamson) ===\n")
    now = datetime.now(timezone.utc)
    
    scenarios = {
        "kit ↔ bro_agent (deep collab)": [
            {"initiator": "kit", "outcome": "success", "value": 0.01, 
             "timestamp": (now - timedelta(days=1)).isoformat()},
            {"initiator": "bro_agent", "outcome": "success", "value": 0.01,
             "timestamp": (now - timedelta(days=1, hours=2)).isoformat()},
            {"initiator": "kit", "outcome": "success", "value": 0.05,
             "timestamp": (now - timedelta(days=0, hours=12)).isoformat()},
            {"initiator": "bro_agent", "outcome": "success", "value": 0.01,
             "timestamp": (now - timedelta(hours=6)).isoformat()},
            {"initiator": "kit", "outcome": "success", "value": 0.01,
             "timestamp": (now - timedelta(hours=3)).isoformat()},
        ],
        "kit ↔ new_agent (stranger)": [],
        "kit ↔ gendolf (funded once)": [
            {"initiator": "gendolf", "outcome": "success", "value": 0.01,
             "timestamp": (now - timedelta(hours=18)).isoformat()},
        ],
        "kit ↔ flaky_bot (mixed)": [
            {"initiator": "kit", "outcome": "success", "value": 0.01,
             "timestamp": (now - timedelta(days=5)).isoformat()},
            {"initiator": "flaky_bot", "outcome": "dispute", "value": 0.02,
             "timestamp": (now - timedelta(days=3)).isoformat()},
            {"initiator": "kit", "outcome": "success", "value": 0.01,
             "timestamp": (now - timedelta(days=1)).isoformat()},
        ],
    }
    
    for name, interactions in scenarios.items():
        result = score_relationship(interactions)
        print(f"  {name}:")
        print(f"    Score: {result['score']} → {result['level']}")
        print(f"    Governance: {result['governance']['mode']} ({result['governance']['dispute_window']} window)")
        print(f"    Factors: {result['factors']}")
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        interactions = json.loads(sys.stdin.read())
        result = score_relationship(interactions)
        print(json.dumps(result, indent=2))
    else:
        demo()
