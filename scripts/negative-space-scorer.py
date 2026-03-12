#!/usr/bin/env python3
"""
negative-space-scorer.py — Score trust by what DIDN'T happen.

Insight (santaclawd/kit, Feb 25-26): Consistent absence of bad behavior
is a costly signal. Spence (1973) inverted: restraint = costly signaling.

Tracks: scope creep, deadline violations, unilateral escalations,
unauthorized actions. Each non-occurrence across N deliveries
strengthens the Beta posterior.
"""

import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class DeliveryRecord:
    """One completed delivery with negative-space observations."""
    delivery_id: str
    agent: str
    scope_creep: bool = False      # did agent exceed defined scope?
    deadline_violation: bool = False # missed deadline?
    unilateral_escalation: bool = False  # escalated without protocol?
    unauthorized_sub_agent: bool = False  # spawned undeclared sub-agent?
    budget_overrun: bool = False    # exceeded budget/resource limits?
    
    @property
    def violations(self) -> int:
        return sum([
            self.scope_creep,
            self.deadline_violation,
            self.unilateral_escalation,
            self.unauthorized_sub_agent,
            self.budget_overrun,
        ])
    
    @property 
    def clean(self) -> bool:
        return self.violations == 0


def beta_score(successes: int, failures: int, prior_a: float = 1.0, prior_b: float = 1.0) -> dict:
    """Jøsang Beta reputation: Beta(α+r, β+s)."""
    a = prior_a + successes
    b = prior_b + failures
    # Expected value of Beta distribution
    expected = a / (a + b)
    # Confidence (1 - variance, normalized)
    variance = (a * b) / ((a + b) ** 2 * (a + b + 1))
    max_var = 0.25  # max variance of Beta is at a=b=1
    confidence = 1.0 - (variance / max_var)
    return {
        "score": round(expected, 4),
        "confidence": round(confidence, 4),
        "alpha": round(a, 2),
        "beta": round(b, 2),
        "n": successes + failures,
    }


def score_agent(records: list[DeliveryRecord]) -> dict:
    """Score an agent by negative-space trust across all dimensions."""
    if not records:
        return {"score": 0.5, "confidence": 0.0, "dimensions": {}, "n": 0}
    
    dimensions = {
        "scope_discipline": {"s": 0, "f": 0},
        "deadline_reliability": {"s": 0, "f": 0},
        "escalation_restraint": {"s": 0, "f": 0},
        "delegation_transparency": {"s": 0, "f": 0},
        "budget_discipline": {"s": 0, "f": 0},
    }
    
    dim_map = {
        "scope_discipline": "scope_creep",
        "deadline_reliability": "deadline_violation",
        "escalation_restraint": "unilateral_escalation",
        "delegation_transparency": "unauthorized_sub_agent",
        "budget_discipline": "budget_overrun",
    }
    
    for r in records:
        for dim, attr in dim_map.items():
            if getattr(r, attr):
                dimensions[dim]["f"] += 1
            else:
                dimensions[dim]["s"] += 1
    
    dim_scores = {}
    for dim, counts in dimensions.items():
        dim_scores[dim] = beta_score(counts["s"], counts["f"])
    
    # Overall: geometric mean of dimension scores (one bad dimension drags everything)
    scores = [d["score"] for d in dim_scores.values()]
    geo_mean = math.exp(sum(math.log(s) for s in scores if s > 0) / len(scores))
    
    # Overall confidence from minimum dimension confidence
    min_confidence = min(d["confidence"] for d in dim_scores.values())
    
    # Costly signal multiplier: more deliveries = more expensive to fake
    n = len(records)
    costly_signal = 1.0 - math.exp(-n / 10.0)  # approaches 1.0 asymptotically
    
    return {
        "score": round(geo_mean, 4),
        "confidence": round(min_confidence, 4),
        "costly_signal_strength": round(costly_signal, 4),
        "n_deliveries": n,
        "clean_deliveries": sum(1 for r in records if r.clean),
        "dimensions": dim_scores,
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }


def demo():
    """Demo with tc3-like scenarios."""
    print("=== Negative Space Trust Scorer ===\n")
    
    # Perfect agent: 20 clean deliveries
    perfect = [DeliveryRecord(f"d{i}", "kit_fox") for i in range(20)]
    result = score_agent(perfect)
    print(f"  Perfect (20 clean):")
    print(f"    Score: {result['score']} | Confidence: {result['confidence']}")
    print(f"    Signal strength: {result['costly_signal_strength']}")
    print()
    
    # One scope creep in 20
    mostly_good = [DeliveryRecord(f"d{i}", "agent_b") for i in range(20)]
    mostly_good[7].scope_creep = True
    result = score_agent(mostly_good)
    print(f"  1 scope creep in 20:")
    print(f"    Score: {result['score']} | Confidence: {result['confidence']}")
    print(f"    Scope discipline: {result['dimensions']['scope_discipline']['score']}")
    print()
    
    # New agent: 3 deliveries
    new_agent = [DeliveryRecord(f"d{i}", "agent_c") for i in range(3)]
    result = score_agent(new_agent)
    print(f"  New agent (3 clean):")
    print(f"    Score: {result['score']} | Confidence: {result['confidence']}")
    print(f"    Signal strength: {result['costly_signal_strength']}")
    print()
    
    # Bad actor: violations across dimensions
    bad = [DeliveryRecord(f"d{i}", "agent_d") for i in range(10)]
    bad[1].scope_creep = True
    bad[3].deadline_violation = True
    bad[5].unauthorized_sub_agent = True
    bad[7].scope_creep = True
    bad[9].unilateral_escalation = True
    result = score_agent(bad)
    print(f"  Bad actor (5 violations in 10):")
    print(f"    Score: {result['score']} | Confidence: {result['confidence']}")
    for dim, ds in result['dimensions'].items():
        if ds['score'] < 0.9:
            print(f"    ⚠️  {dim}: {ds['score']}")
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        data = json.loads(sys.stdin.read())
        records = [DeliveryRecord(**r) for r in data]
        print(json.dumps(score_agent(records), indent=2))
    else:
        demo()
