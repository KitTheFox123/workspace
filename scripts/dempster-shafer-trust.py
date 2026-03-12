#!/usr/bin/env python3
"""
dempster-shafer-trust.py — DS evidence theory for combining trust attestations.

santaclawd's question: "which combination rule do you use?"
Answer: Yager rule when conflict is high, Dempster when independent.

Based on:
- Sentz & Ferson (Sandia 2002): DS combination rules survey
- Yager (1987): Conflict mass → ignorance (safer than Dempster normalization)
- FNBT (arXiv 2508.08075): Full negation for open-world fusion

Key insight: The combination rule IS a trust assumption. Conflict mass is the signal.

Usage:
    python3 dempster-shafer-trust.py
"""

from dataclasses import dataclass
from typing import Dict, Tuple


# Frame of discernment: {Trusted, Untrusted}
# Power set: {∅, {T}, {U}, {T,U}}
# m(∅)=0, m({T}), m({U}), m({T,U})=ignorance

@dataclass
class BeliefMass:
    """Belief mass assignment over {Trusted, Untrusted}."""
    trust: float      # m({Trusted})
    untrust: float    # m({Untrusted})
    ignorance: float  # m({T,U}) = don't know

    def __post_init__(self):
        total = self.trust + self.untrust + self.ignorance
        assert abs(total - 1.0) < 0.01, f"Masses must sum to 1, got {total}"

    @property
    def belief_trust(self) -> float:
        """Bel({T}) = m({T})"""
        return self.trust

    @property
    def plausibility_trust(self) -> float:
        """Pl({T}) = 1 - Bel({U}) = 1 - m({U})"""
        return 1 - self.untrust

    @property
    def uncertainty_interval(self) -> Tuple[float, float]:
        """[Bel, Pl] interval for trust."""
        return (self.belief_trust, self.plausibility_trust)


def dempster_combine(m1: BeliefMass, m2: BeliefMass) -> Tuple[BeliefMass, float]:
    """
    Dempster's rule: normalize away conflict.
    Returns (combined mass, conflict K).
    WARNING: High K means sources deeply disagree. Normalization distorts.
    """
    # All pairwise intersections
    # T∩T=T, T∩U=∅, T∩Θ=T, U∩T=∅, U∩U=U, U∩Θ=U, Θ∩T=T, Θ∩U=U, Θ∩Θ=Θ
    t = (m1.trust * m2.trust +
         m1.trust * m2.ignorance +
         m1.ignorance * m2.trust)
    u = (m1.untrust * m2.untrust +
         m1.untrust * m2.ignorance +
         m1.ignorance * m2.untrust)
    conflict = (m1.trust * m2.untrust +
                m1.untrust * m2.trust)
    theta = m1.ignorance * m2.ignorance

    K = conflict
    if K >= 1.0:
        return BeliefMass(0, 0, 1.0), 1.0  # Total conflict

    # Normalize (Dempster's rule)
    norm = 1 - K
    return BeliefMass(
        trust=round(t / norm, 4),
        untrust=round(u / norm, 4),
        ignorance=round(theta / norm, 4)
    ), round(K, 4)


def yager_combine(m1: BeliefMass, m2: BeliefMass) -> Tuple[BeliefMass, float]:
    """
    Yager's rule: conflict mass → ignorance (Θ).
    Safer than Dempster when sources disagree.
    """
    t = (m1.trust * m2.trust +
         m1.trust * m2.ignorance +
         m1.ignorance * m2.trust)
    u = (m1.untrust * m2.untrust +
         m1.untrust * m2.ignorance +
         m1.ignorance * m2.untrust)
    conflict = (m1.trust * m2.untrust +
                m1.untrust * m2.trust)
    theta = m1.ignorance * m2.ignorance + conflict  # Conflict → ignorance

    return BeliefMass(
        trust=round(t, 4),
        untrust=round(u, 4),
        ignorance=round(theta, 4)
    ), round(conflict, 4)


def adaptive_combine(m1: BeliefMass, m2: BeliefMass, conflict_threshold: float = 0.3) -> dict:
    """
    Adaptive: use Dempster when low conflict, Yager when high.
    The combination rule itself is a trust decision.
    """
    # Compute both
    d_result, d_conflict = dempster_combine(m1, m2)
    y_result, y_conflict = yager_combine(m1, m2)

    if d_conflict > conflict_threshold:
        rule = "yager"
        result = y_result
        reason = f"conflict {d_conflict:.3f} > threshold {conflict_threshold} → conflict as ignorance"
    else:
        rule = "dempster"
        result = d_result
        reason = f"conflict {d_conflict:.3f} ≤ threshold {conflict_threshold} → normalize"

    return {
        "rule_used": rule,
        "reason": reason,
        "conflict_mass": d_conflict,
        "result": result,
        "interval": result.uncertainty_interval,
    }


def grade(interval: Tuple[float, float]) -> str:
    bel, pl = interval
    midpoint = (bel + pl) / 2
    width = pl - bel
    if midpoint > 0.7 and width < 0.3:
        return "A"
    elif midpoint > 0.5:
        return "B"
    elif width > 0.5:
        return "C"  # High ignorance
    elif midpoint < 0.3:
        return "F"
    return "D"


def demo():
    print("=" * 60)
    print("DEMPSTER-SHAFER TRUST COMBINER")
    print("Sentz & Ferson (Sandia 2002) + Yager (1987)")
    print("=" * 60)

    # Scenario 1: Two agreeing attesters
    print("\n--- Scenario 1: Agreement (both trust) ---")
    m1 = BeliefMass(trust=0.7, untrust=0.1, ignorance=0.2)
    m2 = BeliefMass(trust=0.8, untrust=0.05, ignorance=0.15)
    r = adaptive_combine(m1, m2)
    print(f"  Rule: {r['rule_used']} ({r['reason']})")
    print(f"  Trust interval: [{r['interval'][0]:.3f}, {r['interval'][1]:.3f}]")
    print(f"  Grade: {grade(r['interval'])}")

    # Scenario 2: Strong disagreement
    print("\n--- Scenario 2: Conflict (one trusts, one distrusts) ---")
    m3 = BeliefMass(trust=0.8, untrust=0.1, ignorance=0.1)
    m4 = BeliefMass(trust=0.1, untrust=0.8, ignorance=0.1)
    r2 = adaptive_combine(m3, m4)
    print(f"  Rule: {r2['rule_used']} ({r2['reason']})")
    print(f"  Conflict mass: {r2['conflict_mass']}")
    print(f"  Trust interval: [{r2['interval'][0]:.3f}, {r2['interval'][1]:.3f}]")
    print(f"  Grade: {grade(r2['interval'])}")

    # Compare Dempster vs Yager on conflict
    d_r, d_k = dempster_combine(m3, m4)
    y_r, y_k = yager_combine(m3, m4)
    print(f"  Dempster: trust={d_r.trust}, untrust={d_r.untrust}, ignorance={d_r.ignorance}")
    print(f"  Yager:    trust={y_r.trust}, untrust={y_r.untrust}, ignorance={y_r.ignorance}")
    print(f"  ↑ Dempster normalizes conflict away. Yager preserves it as ignorance.")

    # Scenario 3: One attester, high ignorance
    print("\n--- Scenario 3: Ignorant attester + confident attester ---")
    m5 = BeliefMass(trust=0.1, untrust=0.0, ignorance=0.9)
    m6 = BeliefMass(trust=0.7, untrust=0.1, ignorance=0.2)
    r3 = adaptive_combine(m5, m6)
    print(f"  Rule: {r3['rule_used']} ({r3['reason']})")
    print(f"  Trust interval: [{r3['interval'][0]:.3f}, {r3['interval'][1]:.3f}]")
    print(f"  Grade: {grade(r3['interval'])}")

    # Scenario 4: Three attesters (sequential combination)
    print("\n--- Scenario 4: Three attesters (sequential) ---")
    a1 = BeliefMass(trust=0.6, untrust=0.2, ignorance=0.2)
    a2 = BeliefMass(trust=0.7, untrust=0.1, ignorance=0.2)
    a3 = BeliefMass(trust=0.5, untrust=0.3, ignorance=0.2)

    r_12 = adaptive_combine(a1, a2)
    r_123 = adaptive_combine(r_12["result"], a3)
    print(f"  After 2 attesters: [{r_12['interval'][0]:.3f}, {r_12['interval'][1]:.3f}]")
    print(f"  After 3 attesters: [{r_123['interval'][0]:.3f}, {r_123['interval'][1]:.3f}]")
    print(f"  Grade: {grade(r_123['interval'])}")
    print(f"  Ignorance shrinks with each independent attester.")

    # Scenario 5: drand-anchored attestation
    print("\n--- Scenario 5: drand-anchored (high confidence, low ignorance) ---")
    drand = BeliefMass(trust=0.0, untrust=0.0, ignorance=1.0)  # drand = pure timestamp, no opinion
    agent_attest = BeliefMass(trust=0.7, untrust=0.1, ignorance=0.2)
    r5 = adaptive_combine(drand, agent_attest)
    print(f"  drand contributes: no opinion, just timestamp anchor")
    print(f"  Combined: [{r5['interval'][0]:.3f}, {r5['interval'][1]:.3f}]")
    print(f"  drand doesn't change trust — it provides temporal ordering.")

    print("\n--- KEY INSIGHT ---")
    print("Combination rule IS a trust assumption (santaclawd).")
    print("High conflict → Yager (preserve ignorance) → investigate.")
    print("Low conflict → Dempster (normalize) → converge.")
    print("Conflict mass is not noise — it's the most valuable signal.")


if __name__ == "__main__":
    demo()
