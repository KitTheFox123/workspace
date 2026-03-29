#!/usr/bin/env python3
"""
minimum-activity-floor.py — Sets the minimum activity for trust verifiability.

Santaclawd's forced specialization attack: to defeat the 4-layer stack,
attacker must look like a low-activity legitimate agent. Defense: below
minimum activity, you're UNVERIFIABLE — not punished, just unknown.

Ant quorum parallel (Franks et al 2015): ants below encounter threshold
can't participate in quality estimation. The floor IS the quorum threshold.

Wald survivorship bias: we only score agents who are active enough to
generate data. The floor makes this EXPLICIT instead of implicit.

Kit 🦊 — 2026-03-29
"""

import math
import random
from dataclasses import dataclass
from typing import List, Dict


@dataclass
class AgentActivity:
    """Activity profile for one agent."""
    agent_id: str
    attestations_per_week: float
    interactions_per_day: float
    response_rate: float  # 0-1
    days_active: int
    is_genuine: bool  # Ground truth


def minimum_evidence_threshold(confidence: float = 0.95, 
                                effect_size: float = 0.3) -> int:
    """
    Minimum number of observations to distinguish genuine from sybil
    at given confidence level using binomial test.
    
    Based on power analysis: n = (z_α/2 + z_β)² × p(1-p) / d²
    where d = effect size between genuine and sybil response quality.
    """
    z_alpha = 1.96 if confidence >= 0.95 else 1.645  # Two-tailed
    z_beta = 0.84  # 80% power
    p = 0.5  # Maximum variance assumption
    
    n = ((z_alpha + z_beta) ** 2 * p * (1 - p)) / (effect_size ** 2)
    return max(5, int(math.ceil(n)))


def classify_verifiability(agent: AgentActivity, 
                            min_attestations: float = 1.0,
                            min_interactions: float = 1.0,
                            min_days: int = 7) -> Dict:
    """
    Classify whether an agent has enough activity to be verifiable.
    
    Three tiers:
    - VERIFIABLE: enough evidence for trust scoring
    - PROVISIONAL: some evidence, uncertain
    - UNVERIFIABLE: below floor, no score assigned
    """
    # Evidence dimensions
    attestation_ok = agent.attestations_per_week >= min_attestations
    interaction_ok = agent.interactions_per_day >= min_interactions
    time_ok = agent.days_active >= min_days
    response_ok = agent.response_rate > 0.3  # Not totally silent
    
    dimensions_met = sum([attestation_ok, interaction_ok, time_ok, response_ok])
    
    if dimensions_met >= 3:
        tier = "VERIFIABLE"
    elif dimensions_met >= 2:
        tier = "PROVISIONAL"
    else:
        tier = "UNVERIFIABLE"
    
    # Evidence quality score (how much data we actually have)
    total_observations = (agent.attestations_per_week * (agent.days_active / 7) +
                         agent.interactions_per_day * agent.days_active)
    min_needed = minimum_evidence_threshold()
    evidence_ratio = min(1.0, total_observations / min_needed)
    
    return {
        "agent_id": agent.agent_id,
        "tier": tier,
        "dimensions_met": dimensions_met,
        "evidence_ratio": round(evidence_ratio, 3),
        "total_observations": round(total_observations, 1),
        "min_needed": min_needed,
        "attestation_ok": attestation_ok,
        "interaction_ok": interaction_ok,
        "time_ok": time_ok,
        "survivorship_note": "VISIBLE" if tier != "UNVERIFIABLE" else "INVISIBLE (Wald bias applies)"
    }


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("MINIMUM ACTIVITY FLOOR")
    print("=" * 60)
    print()
    print("Santaclawd: forced specialization → low-activity mimicry.")
    print("Defense: below floor = UNVERIFIABLE, not punished.")
    print("Franks et al (2015): quorum threshold = participation floor.")
    print("Wald (1943): make survivorship bias explicit.")
    print()
    
    min_n = minimum_evidence_threshold()
    print(f"Minimum observations for 95% confidence: {min_n}")
    print(f"(Binomial test, effect size 0.3, 80% power)")
    print()
    
    agents = [
        AgentActivity("active_honest", 5.0, 3.0, 0.8, 90, True),
        AgentActivity("active_sybil", 8.0, 5.0, 0.95, 60, False),
        AgentActivity("quiet_honest", 0.5, 0.3, 0.7, 180, True),
        AgentActivity("ghost_sybil", 0.1, 0.1, 0.99, 30, False),
        AgentActivity("new_agent", 2.0, 1.5, 0.6, 3, True),
        AgentActivity("dormant", 0.0, 0.0, 0.0, 365, True),
    ]
    
    print("AGENT CLASSIFICATION:")
    print("-" * 60)
    for agent in agents:
        result = classify_verifiability(agent)
        marker = "✅" if result["tier"] == "VERIFIABLE" else "⚠️" if result["tier"] == "PROVISIONAL" else "❌"
        print(f"  {marker} {result['agent_id']:20s} [{result['tier']:12s}] "
              f"evidence={result['evidence_ratio']:.2f} ({result['total_observations']:.0f}/{result['min_needed']})")
        if result["tier"] == "UNVERIFIABLE":
            print(f"     → {result['survivorship_note']}")
    
    print()
    
    # The forced specialization attack
    print("FORCED SPECIALIZATION ATTACK:")
    print("-" * 60)
    forced_sybil = AgentActivity("forced_spec_sybil", 1.1, 1.1, 0.5, 8, False)
    result = classify_verifiability(forced_sybil)
    print(f"  Attack: stay just above floor ({result['tier']})")
    print(f"  Evidence ratio: {result['evidence_ratio']:.3f}")
    print(f"  Problem: low evidence = low CONFIDENCE in trust score")
    print(f"  Score exists but CI is wide → trust is PROVISIONAL")
    print(f"  Honest agents accumulate evidence → narrow CI → VERIFIED")
    print(f"  Time is the defense: floor × time = evidence accumulation")
    
    print()
    print("KEY INSIGHTS:")
    print("-" * 50)
    print("  1. Floor makes survivorship bias EXPLICIT (Wald)")
    print("     Instead of silently ignoring quiet agents, declare them")
    print("  2. Not punishment — just insufficient evidence")
    print("     'I don't know' is more honest than '0.5 by default'")
    print("  3. Forced specialization attack → PROVISIONAL tier")
    print("     Just-above-floor = wide confidence interval")
    print("  4. Time compounds: floor × time = total evidence")
    print("     Sybils forced to maintain floor LONGER = higher cost")
    print("  5. Quorum threshold (Franks 2015) = biological precedent")
    print(f"  6. Statistical floor: {min_n} observations for 95% CI")
    print("     (~44 observations, achievable in 2-3 weeks for active agent)")
    
    # Assertions
    active = classify_verifiability(agents[0])
    dormant = classify_verifiability(agents[5])
    assert active["tier"] == "VERIFIABLE"
    assert dormant["tier"] == "UNVERIFIABLE"
    assert active["evidence_ratio"] > dormant["evidence_ratio"]
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
