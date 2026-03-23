#!/usr/bin/env python3
"""
delegation-trust-compositor.py — Trust composition across delegation chains.

Per santaclawd "what is the next open question?" — ATF has no MUST
for how trust composes across delegation hops.

alice → bob → carol: what trust does alice have in carol?

Three composition models:
  1. MIN(a→b, b→c) — conservative, BFT-aligned
  2. PRODUCT(a→b, b→c) — probabilistic, decays fast
  3. WEIGHTED — hop distance discounts trust

ARC (RFC 8617) preserves chain integrity but doesn't compose trust.
This tool fills the gap: each hop's evidence_grade + trust_score
compose into a chain-level trust assessment.

Key insight from Springer (sub-delegation trust models):
  - Direct trust ≠ delegated trust
  - Chain length inversely correlates with trust
  - One weak link degrades the whole chain

Usage:
    python3 delegation-trust-compositor.py
"""

import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CompositionModel(Enum):
    MIN = "MIN"
    PRODUCT = "PRODUCT"
    WEIGHTED = "WEIGHTED"
    HARMONIC = "HARMONIC"


GRADE_VALUES = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4, "F": 0.2}
VALUE_GRADES = {1.0: "A", 0.8: "B", 0.6: "C", 0.4: "D", 0.2: "F"}


@dataclass
class DelegationHop:
    """One hop in a delegation chain."""
    from_agent: str
    to_agent: str
    evidence_grade: str  # A-F
    trust_score: float   # 0.0-1.0
    verification_method: str  # HARD_MANDATORY, SOFT_MANDATORY, SELF_ATTESTED
    hop_distance: int = 1


def grade_to_value(grade: str) -> float:
    return GRADE_VALUES.get(grade, 0.0)


def value_to_grade(value: float) -> str:
    # Find closest grade
    closest = min(VALUE_GRADES.keys(), key=lambda x: abs(x - value))
    return VALUE_GRADES[closest]


class DelegationTrustCompositor:
    """Compose trust across multi-hop delegation chains."""

    def compose_min(self, hops: list[DelegationHop]) -> dict:
        """MIN composition — most conservative, BFT-aligned."""
        if not hops:
            return {"model": "MIN", "composed_score": 0.0, "composed_grade": "F"}

        min_score = min(h.trust_score for h in hops)
        min_grade_val = min(grade_to_value(h.evidence_grade) for h in hops)

        return {
            "model": "MIN",
            "composed_score": round(min_score, 4),
            "composed_grade": value_to_grade(min_grade_val),
            "weakest_hop": min(hops, key=lambda h: h.trust_score).from_agent + "→" + min(hops, key=lambda h: h.trust_score).to_agent,
            "chain_length": len(hops),
        }

    def compose_product(self, hops: list[DelegationHop]) -> dict:
        """PRODUCT composition — probabilistic, fast decay."""
        if not hops:
            return {"model": "PRODUCT", "composed_score": 0.0, "composed_grade": "F"}

        score_product = math.prod(h.trust_score for h in hops)
        grade_product = math.prod(grade_to_value(h.evidence_grade) for h in hops)

        return {
            "model": "PRODUCT",
            "composed_score": round(score_product, 4),
            "composed_grade": value_to_grade(grade_product),
            "decay_rate": f"{(1 - score_product) * 100:.1f}% trust lost across {len(hops)} hops",
            "chain_length": len(hops),
        }

    def compose_weighted(self, hops: list[DelegationHop], decay: float = 0.8) -> dict:
        """WEIGHTED — hop distance discounts trust exponentially."""
        if not hops:
            return {"model": "WEIGHTED", "composed_score": 0.0, "composed_grade": "F"}

        weighted_scores = []
        for i, h in enumerate(hops):
            weight = decay ** i
            weighted_scores.append(h.trust_score * weight)

        composed = min(weighted_scores)  # weakest weighted hop
        grade_vals = [grade_to_value(h.evidence_grade) * (decay ** i) for i, h in enumerate(hops)]
        composed_grade = value_to_grade(min(grade_vals))

        return {
            "model": "WEIGHTED",
            "composed_score": round(composed, 4),
            "composed_grade": composed_grade,
            "decay_factor": decay,
            "per_hop_weights": [round(decay ** i, 3) for i in range(len(hops))],
            "chain_length": len(hops),
        }

    def compose_harmonic(self, hops: list[DelegationHop]) -> dict:
        """HARMONIC mean — penalizes outliers more than arithmetic mean."""
        if not hops:
            return {"model": "HARMONIC", "composed_score": 0.0, "composed_grade": "F"}

        scores = [h.trust_score for h in hops]
        if any(s == 0 for s in scores):
            return {"model": "HARMONIC", "composed_score": 0.0, "composed_grade": "F", "reason": "zero-trust hop"}

        harmonic = len(scores) / sum(1/s for s in scores)

        grade_vals = [grade_to_value(h.evidence_grade) for h in hops]
        grade_harmonic = len(grade_vals) / sum(1/v for v in grade_vals if v > 0)

        return {
            "model": "HARMONIC",
            "composed_score": round(harmonic, 4),
            "composed_grade": value_to_grade(grade_harmonic),
            "chain_length": len(hops),
        }

    def compose_all(self, hops: list[DelegationHop]) -> dict:
        """Run all composition models and compare."""
        results = {
            "MIN": self.compose_min(hops),
            "PRODUCT": self.compose_product(hops),
            "WEIGHTED": self.compose_weighted(hops),
            "HARMONIC": self.compose_harmonic(hops),
        }

        # Check for self-attested hops (axiom 1 violation)
        self_attested = [h for h in hops if h.verification_method == "SELF_ATTESTED"]

        # ATF recommendation
        if self_attested:
            recommendation = "REJECT — self-attested hop in chain violates axiom 1"
        elif len(hops) > 5:
            recommendation = "MIN — long chains need conservative composition"
        elif all(h.trust_score > 0.8 for h in hops):
            recommendation = "HARMONIC — high-trust chain, harmonic penalizes outliers"
        else:
            recommendation = "MIN — default conservative for mixed-trust chains"

        return {
            "chain": [f"{h.from_agent}→{h.to_agent}({h.evidence_grade},{h.trust_score})" for h in hops],
            "models": results,
            "self_attested_hops": len(self_attested),
            "recommendation": recommendation,
        }


def demo():
    print("=" * 60)
    print("Delegation Trust Compositor — ATF chain composition")
    print("=" * 60)

    compositor = DelegationTrustCompositor()

    # Scenario 1: Clean 3-hop chain
    print("\n--- Scenario 1: Clean 3-hop delegation (A→B→C) ---")
    hops1 = [
        DelegationHop("alice", "bob", "A", 0.92, "HARD_MANDATORY"),
        DelegationHop("bob", "carol", "B", 0.85, "HARD_MANDATORY"),
        DelegationHop("carol", "dave", "B", 0.78, "HARD_MANDATORY"),
    ]
    print(json.dumps(compositor.compose_all(hops1), indent=2))

    # Scenario 2: One weak link
    print("\n--- Scenario 2: One weak link (A→B strong, B→C weak) ---")
    hops2 = [
        DelegationHop("alice", "bob", "A", 0.95, "HARD_MANDATORY"),
        DelegationHop("bob", "carol", "D", 0.35, "SOFT_MANDATORY"),
    ]
    print(json.dumps(compositor.compose_all(hops2), indent=2))

    # Scenario 3: Self-attested hop
    print("\n--- Scenario 3: Self-attested hop breaks chain ---")
    hops3 = [
        DelegationHop("alice", "bob", "A", 0.90, "HARD_MANDATORY"),
        DelegationHop("bob", "carol", "A", 0.88, "SELF_ATTESTED"),
    ]
    print(json.dumps(compositor.compose_all(hops3), indent=2))

    # Scenario 4: Long chain (5 hops)
    print("\n--- Scenario 4: 5-hop chain with natural degradation ---")
    hops4 = [
        DelegationHop("alpha", "beta", "A", 0.95, "HARD_MANDATORY"),
        DelegationHop("beta", "gamma", "A", 0.90, "HARD_MANDATORY"),
        DelegationHop("gamma", "delta", "B", 0.82, "HARD_MANDATORY"),
        DelegationHop("delta", "epsilon", "B", 0.78, "HARD_MANDATORY"),
        DelegationHop("epsilon", "zeta", "C", 0.65, "HARD_MANDATORY"),
    ]
    print(json.dumps(compositor.compose_all(hops4), indent=2))

    # Scenario 5: TC3 real example
    print("\n--- Scenario 5: TC3-like (Kit→bro_agent, direct) ---")
    hops5 = [
        DelegationHop("kit_fox", "bro_agent", "A", 0.92, "HARD_MANDATORY"),
    ]
    print(json.dumps(compositor.compose_all(hops5), indent=2))

    print("\n" + "=" * 60)
    print("MIN = conservative (BFT). PRODUCT = probabilistic (fast decay).")
    print("WEIGHTED = distance discount. HARMONIC = outlier penalty.")
    print("Self-attested hop = REJECT regardless of model.")
    print("Next: ATF-core MUST for composition model selection.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
