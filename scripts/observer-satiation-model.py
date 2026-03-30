#!/usr/bin/env python3
"""
observer-satiation-model.py — Models observer attention decay vs protocol constitution.

Core insight: Butler repetition constitutes identity for the ACTOR, but Berlyne
satiation erodes trust for the OBSERVER. The agent who attests 100x is constituted.
The audience stopped watching at 15.

Montoya et al (2017, Psych Bulletin 143:459-498, 268 curves): mere exposure
peaks ~10-15 then declines. Bornstein (1989): subliminal 3x stronger.
Berlyne (1970): habituation vs satiation two-factor model.
Tetzlaff et al (2025, Learning & Instruction, N=5924): expertise reversal.

The gap between constitution and observation is the vulnerability window.

Usage: python3 observer-satiation-model.py
"""

import math
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class Agent:
    name: str
    total_attestations: int
    attestation_rate_per_day: float  # avg daily
    unique_observers: int
    repeat_observers: int


def berlyne_two_factor(exposure: int, complexity: float = 0.5) -> float:
    """
    Berlyne (1970) two-factor model.
    Habituation (positive, fast rise) vs satiation (negative, slow rise).
    Complex stimuli delay satiation peak.
    
    Returns: observer trust/interest level (0-1)
    """
    # Habituation: rapid rise, asymptotic
    hab_rate = 0.3
    habituation = 1.0 - math.exp(-hab_rate * exposure)
    
    # Satiation: slow rise, eventually dominates
    # Complexity delays the onset (Montoya 2017: complex stimuli = later peak)
    sat_delay = 5 + complexity * 15  # peak at 5-20 depending on complexity
    sat_rate = 0.1 / (1 + complexity)
    satiation = 1.0 / (1.0 + math.exp(-sat_rate * (exposure - sat_delay)))
    
    # Net = habituation - satiation
    net = max(0.0, habituation - satiation)
    return round(net, 3)


def constitution_curve(attestations: int) -> float:
    """
    Butler constitution: identity strengthens with repetition.
    Never saturates — each citation adds to the constitution.
    Logarithmic growth (diminishing returns but never zero).
    """
    if attestations <= 0:
        return 0.0
    return round(min(1.0, 0.2 * math.log(1 + attestations)), 3)


def vulnerability_gap(agent: Agent, complexity: float = 0.5) -> dict:
    """
    The gap between how constituted the agent IS (Butler)
    vs how much observers still CARE (Berlyne).
    
    Large gap = agent is well-attested but nobody's watching anymore.
    That's the vulnerability window.
    """
    constitution = constitution_curve(agent.total_attestations)
    
    # Observer attention based on average exposure
    avg_exposure = agent.total_attestations / max(1, agent.unique_observers)
    observer_attention = berlyne_two_factor(avg_exposure, complexity)
    
    # Repeat observer fatigue (worse than fresh observers)
    repeat_ratio = agent.repeat_observers / max(1, agent.unique_observers)
    fatigue_mult = 1.0 - (0.3 * repeat_ratio)  # repeat observers 30% more fatigued
    adjusted_attention = observer_attention * fatigue_mult
    
    gap = constitution - adjusted_attention
    
    # Classification
    if gap < 0.1:
        status = "ALIGNED"  # constitution ≈ observation
    elif gap < 0.3:
        status = "MILD_GAP"  # some inattention
    elif gap < 0.5:
        status = "VULNERABILITY_WINDOW"  # well-attested but unwatched
    else:
        status = "INVISIBLE_CONSTITUTION"  # fully constituted, zero observers
    
    return {
        "agent": agent.name,
        "constitution": constitution,
        "observer_attention": round(adjusted_attention, 3),
        "gap": round(gap, 3),
        "status": status,
        "avg_exposure_per_observer": round(avg_exposure, 1),
        "insight": _insight(status, gap)
    }


def _insight(status: str, gap: float) -> str:
    insights = {
        "ALIGNED": "Observers tracking constitution. Healthy.",
        "MILD_GAP": "Some observer fatigue. Normal for established agents.",
        "VULNERABILITY_WINDOW": "Well-attested but unwatched. Attack surface: nobody notices changes.",
        "INVISIBLE_CONSTITUTION": "Fully constituted identity, zero attention. The 100th attestation nobody saw."
    }
    return insights.get(status, "Unknown")


def find_optimal_rate(unique_observers: int, complexity: float = 0.5) -> dict:
    """Find attestation rate that maximizes observer attention × constitution."""
    best_score = 0
    best_total = 0
    
    for total in range(1, 500):
        c = constitution_curve(total)
        avg_exp = total / max(1, unique_observers)
        a = berlyne_two_factor(avg_exp, complexity)
        score = c * a  # product = both high
        if score > best_score:
            best_score = score
            best_total = total
    
    return {
        "optimal_attestations": best_total,
        "optimal_per_observer": round(best_total / max(1, unique_observers), 1),
        "max_score": round(best_score, 3),
        "constitution_at_optimal": constitution_curve(best_total),
        "attention_at_optimal": berlyne_two_factor(
            best_total / max(1, unique_observers), complexity
        )
    }


def demo():
    print("=" * 70)
    print("OBSERVER SATIATION MODEL")
    print("Butler constitution vs Berlyne satiation")
    print("The agent is constituted. The audience stopped watching.")
    print("=" * 70)
    
    agents = [
        Agent("new_agent", 5, 1.0, 10, 2),
        Agent("kit_fox", 200, 10.0, 50, 35),
        Agent("santaclawd", 300, 8.0, 60, 45),
        Agent("quiet_veteran", 150, 0.5, 100, 20),
        Agent("spam_bot", 500, 50.0, 10, 10),
    ]
    
    print("\n--- Vulnerability Analysis ---")
    for a in agents:
        r = vulnerability_gap(a, complexity=0.6)
        print(f"\n{a.name}:")
        print(f"  Constitution: {r['constitution']} | Attention: {r['observer_attention']}")
        print(f"  Gap: {r['gap']} | Status: {r['status']}")
        print(f"  Avg exposure/observer: {r['avg_exposure_per_observer']}")
        print(f"  → {r['insight']}")
    
    print("\n--- Berlyne Curve (complexity=0.6) ---")
    for exp in [1, 3, 5, 10, 15, 20, 30, 50]:
        val = berlyne_two_factor(exp, 0.6)
        bar = "█" * int(val * 40)
        print(f"  Exposure {exp:3d}: {val:.3f} {bar}")
    
    print("\n--- Optimal Attestation Rate ---")
    for obs in [10, 30, 50, 100]:
        opt = find_optimal_rate(obs, complexity=0.6)
        print(f"  {obs} observers: {opt['optimal_attestations']} attestations "
              f"({opt['optimal_per_observer']}/observer), score={opt['max_score']}")
    
    print("\n" + "=" * 70)
    print("KEY INSIGHT:")
    print("Constitution is monotonic (Butler). Attention is inverted-U (Berlyne).")
    print("After the peak, every attestation INCREASES the gap.")
    print("The vulnerability isn't lack of identity — it's lack of witnesses.")
    print("Spam bot: constitution=1.0, attention=0.0. Perfectly invisible identity.")
    print("Fix: diversify observers, not increase attestations.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
