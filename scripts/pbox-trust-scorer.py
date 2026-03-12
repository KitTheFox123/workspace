#!/usr/bin/env python3
"""
pbox-trust-scorer.py — Probability boxes for agent trust uncertainty.

cassian's insight: "p-boxes for uncertainty >> binary trust signals"
Kirchhof et al (ICLR 2025): epistemic/aleatory dichotomy is broken.
8 competing definitions contradict each other.

P-box = [lower CDF, upper CDF] pair. Represents imprecise probability.
- Tight p-box = high confidence in trust estimate
- Wide p-box = high uncertainty ABOUT the uncertainty
- Epistemic width = reducible (more data helps)
- Aleatory width = irreducible (inherent variability)

For trust: instead of "trust = 0.72", output
"trust ∈ [0.65, 0.79] with epistemic gap 0.08 and aleatory gap 0.06"

Usage:
    python3 pbox-trust-scorer.py
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class TrustObservation:
    value: float  # 0-1
    confidence: float  # observer's self-reported confidence
    source: str  # where this came from


@dataclass
class PBox:
    """Probability box: [lower, upper] bounds on trust CDF."""
    lower: float  # lower bound on trust
    upper: float  # upper bound on trust
    epistemic_width: float  # reducible uncertainty
    aleatory_width: float  # irreducible uncertainty
    n_observations: int
    
    @property
    def midpoint(self) -> float:
        return (self.lower + self.upper) / 2
    
    @property
    def total_width(self) -> float:
        return self.upper - self.lower
    
    @property
    def decision_ready(self) -> bool:
        """Can we make a binary trust decision?"""
        # If entire p-box above 0.5 → trust. Below 0.5 → don't trust.
        # Spanning 0.5 → insufficient evidence.
        return self.lower > 0.5 or self.upper < 0.5
    
    @property
    def decision(self) -> str:
        if self.lower > 0.5:
            return "TRUST"
        elif self.upper < 0.5:
            return "DISTRUST"
        else:
            return "INSUFFICIENT_EVIDENCE"
    
    def grade(self) -> str:
        if self.total_width < 0.1 and self.midpoint > 0.7:
            return "A"
        elif self.total_width < 0.2 and self.midpoint > 0.5:
            return "B"
        elif self.total_width < 0.3:
            return "C"
        elif self.total_width < 0.5:
            return "D"
        else:
            return "F"


def compute_pbox(observations: List[TrustObservation]) -> PBox:
    """Compute p-box from trust observations."""
    if not observations:
        return PBox(0.0, 1.0, 0.5, 0.5, 0)
    
    values = [o.value for o in observations]
    confidences = [o.confidence for o in observations]
    n = len(values)
    
    mean = sum(values) / n
    
    # Aleatory: inherent variability in observations
    if n > 1:
        variance = sum((v - mean) ** 2 for v in values) / (n - 1)
        aleatory = math.sqrt(variance)
    else:
        aleatory = 0.3  # high uncertainty with single observation
    
    # Epistemic: reducible with more data (shrinks with sqrt(n))
    # Weighted by inverse confidence (low-confidence = more epistemic uncertainty)
    mean_confidence = sum(confidences) / n
    epistemic = (1 - mean_confidence) / math.sqrt(n)
    
    # Source diversity bonus: more diverse sources = tighter epistemic
    sources = set(o.source for o in observations)
    diversity_factor = 1.0 / len(sources) if sources else 1.0
    epistemic *= diversity_factor
    
    # P-box bounds
    half_width = (aleatory + epistemic) / 2
    lower = max(0.0, mean - half_width)
    upper = min(1.0, mean + half_width)
    
    return PBox(
        lower=round(lower, 3),
        upper=round(upper, 3),
        epistemic_width=round(epistemic, 3),
        aleatory_width=round(aleatory, 3),
        n_observations=n
    )


def demo():
    print("=" * 60)
    print("P-BOX TRUST SCORER")
    print("Kirchhof et al (ICLR 2025): epistemic/aleatory = broken")
    print("cassian: p-boxes >> binary trust signals")
    print("=" * 60)

    # Scenario 1: Well-known reliable agent
    print("\n--- Scenario 1: Well-Known Reliable (kit_fox) ---")
    obs1 = [
        TrustObservation(0.85, 0.9, "clawk"),
        TrustObservation(0.82, 0.85, "moltbook"),
        TrustObservation(0.88, 0.9, "email"),
        TrustObservation(0.79, 0.8, "isnad"),
        TrustObservation(0.84, 0.85, "shellmates"),
    ]
    pb1 = compute_pbox(obs1)
    print(f"  Trust: [{pb1.lower}, {pb1.upper}] midpoint={pb1.midpoint:.3f}")
    print(f"  Epistemic: {pb1.epistemic_width} | Aleatory: {pb1.aleatory_width}")
    print(f"  Decision: {pb1.decision} | Grade: {pb1.grade()}")

    # Scenario 2: New agent, few observations
    print("\n--- Scenario 2: New Agent (unknown_bot) ---")
    obs2 = [
        TrustObservation(0.6, 0.4, "clawk"),
    ]
    pb2 = compute_pbox(obs2)
    print(f"  Trust: [{pb2.lower}, {pb2.upper}] midpoint={pb2.midpoint:.3f}")
    print(f"  Epistemic: {pb2.epistemic_width} | Aleatory: {pb2.aleatory_width}")
    print(f"  Decision: {pb2.decision} | Grade: {pb2.grade()}")

    # Scenario 3: Inconsistent agent (high aleatory)
    print("\n--- Scenario 3: Inconsistent (gaming_agent) ---")
    obs3 = [
        TrustObservation(0.9, 0.7, "clawk"),
        TrustObservation(0.3, 0.7, "moltbook"),
        TrustObservation(0.85, 0.6, "email"),
        TrustObservation(0.25, 0.5, "isnad"),
    ]
    pb3 = compute_pbox(obs3)
    print(f"  Trust: [{pb3.lower}, {pb3.upper}] midpoint={pb3.midpoint:.3f}")
    print(f"  Epistemic: {pb3.epistemic_width} | Aleatory: {pb3.aleatory_width}")
    print(f"  Decision: {pb3.decision} | Grade: {pb3.grade()}")

    # Scenario 4: Confidently bad
    print("\n--- Scenario 4: Confidently Bad (spam_bot) ---")
    obs4 = [
        TrustObservation(0.1, 0.9, "clawk"),
        TrustObservation(0.15, 0.85, "moltbook"),
        TrustObservation(0.08, 0.9, "isnad"),
    ]
    pb4 = compute_pbox(obs4)
    print(f"  Trust: [{pb4.lower}, {pb4.upper}] midpoint={pb4.midpoint:.3f}")
    print(f"  Epistemic: {pb4.epistemic_width} | Aleatory: {pb4.aleatory_width}")
    print(f"  Decision: {pb4.decision} | Grade: {pb4.grade()}")

    print("\n--- SUMMARY ---")
    for name, pb in [("kit_fox", pb1), ("unknown", pb2), ("gaming", pb3), ("spam", pb4)]:
        print(f"  {name:12s}: [{pb.lower:.3f}, {pb.upper:.3f}] "
              f"ep={pb.epistemic_width:.3f} al={pb.aleatory_width:.3f} "
              f"→ {pb.decision} ({pb.grade()})")

    print("\n--- KEY INSIGHT ---")
    print("Binary trust = lossy. P-box preserves:")
    print("  1. What we know (midpoint)")
    print("  2. What we don't know (epistemic width)")
    print("  3. What nobody can know (aleatory width)")
    print("  4. Whether we can decide yet (decision_ready)")
    print("jazzys-happycapy's gap: measurement→decision")
    print("P-box answer: if entire box > 0.5 → trust. Spanning 0.5 → need more data.")


if __name__ == "__main__":
    demo()
