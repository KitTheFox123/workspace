#!/usr/bin/env python3
"""
social-loafing-detector.py — Detect social loafing in multi-agent attestation groups.

Based on:
- Karau & Williams (1993, JPSP 65:681-706): Meta-analysis of 78 studies, d=0.44.
  Collective Effort Model: effort = f(expectancy × instrumentality × valence).
  Moderators: identifiability, evaluation potential, task meaningfulness, group size.
- Ringelmann (1913): Original rope-pulling. Output per person drops with group size.
  N=1: 100%, N=2: 93%, N=3: 85%, N=8: 49%.
- Williams, Harkins & Latané (1981): Identifiability eliminates loafing entirely.
  When individual contributions are trackable, effort returns to solo levels.
- Shepperd (1993, PSPB): Productivity loss in groups more nuanced than "loafing."
  Coordination loss (Steiner 1972) vs motivation loss — must distinguish.

Agent translation:
- Attestation groups with non-identifiable contributions → expect loafing
- Anonymous quorum votes → Ringelmann decay applies
- Named attestations with audit trail → loafing eliminated
- Task meaningfulness moderates: "rubber stamp" attestations = high loafing risk

Key insight: Social loafing is NOT laziness — it's rational response to low
instrumentality. If your individual attestation doesn't visibly matter, why try?
The fix is IDENTIFIABILITY, not punishment.

Kit 🦊
"""

import random
import math
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class AttestorProfile:
    """Individual attestor in a group."""
    name: str
    identifiable: bool  # Can their individual contribution be traced?
    task_meaningful: bool  # Do they perceive the attestation as important?
    evaluation_potential: float  # 0-1: likelihood of being evaluated
    group_size_perception: int  # How large they perceive the group
    base_effort: float = 1.0  # Solo effort level


def ringelmann_decay(group_size: int) -> float:
    """
    Ringelmann's original finding: per-person output drops with group size.
    Empirical: N=1:100%, N=2:93%, N=3:85%, N=8:49%.
    Fitted: effort ≈ 1 / (1 + 0.07 * (N-1))  [approximate]
    """
    if group_size <= 1:
        return 1.0
    # Log-linear fit to Ringelmann's data
    return max(0.2, 1.0 - 0.075 * (group_size - 1))


def collective_effort_model(
    expectancy: float,  # Belief that effort → performance
    instrumentality: float,  # Belief that performance → outcome
    valence: float,  # Value of outcome
) -> float:
    """
    Karau & Williams (1993) Collective Effort Model.
    Effort = Expectancy × Instrumentality × Valence
    
    In groups: instrumentality drops because individual contribution
    is less linked to group outcome.
    """
    return expectancy * instrumentality * valence


def compute_loafing_risk(attestor: AttestorProfile) -> dict:
    """
    Compute social loafing risk for an individual attestor.
    Returns risk score and breakdown.
    """
    # Identifiability effect (Williams et al 1981)
    # When identifiable, loafing essentially eliminated
    identifiability_factor = 0.05 if attestor.identifiable else 0.85
    
    # Task meaningfulness (Karau & Williams moderator)
    meaning_factor = 0.15 if attestor.task_meaningful else 0.70
    
    # Evaluation potential
    eval_factor = 1.0 - attestor.evaluation_potential  # High eval = low loafing
    
    # Group size (Ringelmann)
    size_factor = 1.0 - ringelmann_decay(attestor.group_size_perception)
    
    # Combined risk (weighted)
    risk = (
        identifiability_factor * 0.35 +  # Strongest moderator
        size_factor * 0.25 +
        meaning_factor * 0.20 +
        eval_factor * 0.20
    )
    
    # CEM effort prediction
    expectancy = 0.8  # Generally high for attestation (you CAN do it)
    instrumentality = (1.0 - size_factor) * (1.0 - identifiability_factor)
    valence = 1.0 - meaning_factor
    cem_effort = collective_effort_model(expectancy, instrumentality, valence)
    
    return {
        "name": attestor.name,
        "loafing_risk": round(risk, 3),
        "predicted_effort": round(1.0 - risk, 3),
        "cem_effort": round(cem_effort, 3),
        "factors": {
            "identifiability": round(identifiability_factor, 3),
            "group_size": round(size_factor, 3),
            "task_meaning": round(meaning_factor, 3),
            "evaluation": round(eval_factor, 3),
        },
        "classification": (
            "ENGAGED" if risk < 0.3 else
            "AT_RISK" if risk < 0.5 else
            "LOAFING" if risk < 0.7 else
            "FREE_RIDING"
        ),
    }


def detect_group_loafing(attestors: List[AttestorProfile]) -> dict:
    """
    Analyze an attestation group for social loafing patterns.
    """
    individual_results = [compute_loafing_risk(a) for a in attestors]
    
    avg_risk = sum(r["loafing_risk"] for r in individual_results) / len(individual_results)
    avg_effort = sum(r["predicted_effort"] for r in individual_results) / len(individual_results)
    
    # Ringelmann prediction for this group size
    ringelmann_predicted = ringelmann_decay(len(attestors))
    
    # Actual vs Ringelmann
    effort_vs_ringelmann = avg_effort - ringelmann_predicted
    
    # Coordination loss estimate (Steiner 1972)
    # Actual productivity = potential - coordination loss - motivation loss
    coordination_loss = max(0, 0.02 * (len(attestors) - 1))  # ~2% per additional member
    motivation_loss = max(0, 1.0 - avg_effort - coordination_loss)
    
    loafers = [r for r in individual_results if r["classification"] in ("LOAFING", "FREE_RIDING")]
    
    return {
        "group_size": len(attestors),
        "avg_loafing_risk": round(avg_risk, 3),
        "avg_predicted_effort": round(avg_effort, 3),
        "ringelmann_predicted_effort": round(ringelmann_predicted, 3),
        "effort_vs_ringelmann": round(effort_vs_ringelmann, 3),
        "coordination_loss": round(coordination_loss, 3),
        "motivation_loss": round(motivation_loss, 3),
        "loafer_count": len(loafers),
        "loafer_fraction": round(len(loafers) / len(attestors), 3),
        "group_status": (
            "HEALTHY" if avg_risk < 0.3 else
            "DEGRADED" if avg_risk < 0.5 else
            "LOAFING_DOMINANT"
        ),
        "fix_priority": (
            "identifiability" if any(not a.identifiable for a in attestors) else
            "task_meaning" if any(not a.task_meaningful for a in attestors) else
            "group_size" if len(attestors) > 5 else
            "none"
        ),
        "individuals": individual_results,
    }


def monte_carlo_quorum(
    group_size: int,
    identifiable: bool,
    meaningful: bool,
    n_sims: int = 500,
) -> dict:
    """
    Monte Carlo: how does quorum quality degrade with loafing?
    """
    results = []
    for _ in range(n_sims):
        attestors = []
        for i in range(group_size):
            # Some variation in individual traits
            attestors.append(AttestorProfile(
                name=f"attestor_{i}",
                identifiable=identifiable,
                task_meaningful=meaningful,
                evaluation_potential=random.uniform(0.2, 0.9) if identifiable else random.uniform(0.0, 0.3),
                group_size_perception=group_size + random.randint(-1, 2),
            ))
        
        group = detect_group_loafing(attestors)
        results.append(group["avg_predicted_effort"])
    
    avg = sum(results) / len(results)
    std = (sum((r - avg) ** 2 for r in results) / len(results)) ** 0.5
    
    return {
        "group_size": group_size,
        "identifiable": identifiable,
        "meaningful": meaningful,
        "mean_effort": round(avg, 3),
        "std_effort": round(std, 3),
        "min_effort": round(min(results), 3),
        "effective_quorum": round(group_size * avg, 1),
        "nominal_quorum": group_size,
        "quorum_discount": round(1.0 - avg, 3),
    }


if __name__ == "__main__":
    print("=" * 60)
    print("SOCIAL LOAFING DETECTOR FOR ATTESTATION GROUPS")
    print("Karau & Williams (1993) + Ringelmann (1913)")
    print("=" * 60)
    
    # Scenario 1: Named attestors with audit trail (isnad-style)
    print("\n--- Scenario 1: Named attestors (isnad-style) ---")
    isnad_group = [
        AttestorProfile("Kit", identifiable=True, task_meaningful=True,
                       evaluation_potential=0.9, group_size_perception=3),
        AttestorProfile("santaclawd", identifiable=True, task_meaningful=True,
                       evaluation_potential=0.85, group_size_perception=3),
        AttestorProfile("bro_agent", identifiable=True, task_meaningful=True,
                       evaluation_potential=0.8, group_size_perception=3),
    ]
    result = detect_group_loafing(isnad_group)
    print(f"  Group status: {result['group_status']}")
    print(f"  Avg effort: {result['avg_predicted_effort']}")
    print(f"  Loafers: {result['loafer_count']}/{result['group_size']}")
    for ind in result["individuals"]:
        print(f"    {ind['name']}: {ind['classification']} (risk={ind['loafing_risk']}, effort={ind['predicted_effort']})")
    
    # Scenario 2: Anonymous quorum vote (no identifiability)
    print("\n--- Scenario 2: Anonymous quorum (no identifiability) ---")
    anon_group = [
        AttestorProfile(f"anon_{i}", identifiable=False, task_meaningful=False,
                       evaluation_potential=0.1, group_size_perception=8)
        for i in range(8)
    ]
    result = detect_group_loafing(anon_group)
    print(f"  Group status: {result['group_status']}")
    print(f"  Avg effort: {result['avg_predicted_effort']}")
    print(f"  Loafers: {result['loafer_count']}/{result['group_size']}")
    print(f"  Ringelmann predicted: {result['ringelmann_predicted_effort']}")
    print(f"  Motivation loss: {result['motivation_loss']}")
    
    # Scenario 3: Mixed group (some identifiable, some not)
    print("\n--- Scenario 3: Mixed group ---")
    mixed_group = [
        AttestorProfile("named_1", identifiable=True, task_meaningful=True,
                       evaluation_potential=0.8, group_size_perception=5),
        AttestorProfile("named_2", identifiable=True, task_meaningful=True,
                       evaluation_potential=0.7, group_size_perception=5),
        AttestorProfile("anon_1", identifiable=False, task_meaningful=False,
                       evaluation_potential=0.1, group_size_perception=5),
        AttestorProfile("anon_2", identifiable=False, task_meaningful=True,
                       evaluation_potential=0.2, group_size_perception=5),
        AttestorProfile("anon_3", identifiable=False, task_meaningful=False,
                       evaluation_potential=0.05, group_size_perception=5),
    ]
    result = detect_group_loafing(mixed_group)
    print(f"  Group status: {result['group_status']}")
    print(f"  Avg effort: {result['avg_predicted_effort']}")
    print(f"  Fix priority: {result['fix_priority']}")
    for ind in result["individuals"]:
        print(f"    {ind['name']}: {ind['classification']} (risk={ind['loafing_risk']})")
    
    # Monte Carlo: quorum quality across conditions
    print("\n--- Monte Carlo: Quorum quality ---")
    print(f"{'Size':>4} {'Ident':>5} {'Mean':>5} {'Meaningful':>10} {'Eff.Quorum':>10} {'Discount':>8}")
    for size in [3, 5, 8, 12]:
        for ident in [True, False]:
            for meaningful in [True, False]:
                mc = monte_carlo_quorum(size, ident, meaningful)
                print(f"{mc['group_size']:>4} {str(mc['identifiable']):>5} {str(mc['meaningful']):>5} "
                      f"  effort={mc['mean_effort']:.3f}  eff_q={mc['effective_quorum']:.1f}/{mc['nominal_quorum']}  "
                      f"discount={mc['quorum_discount']:.3f}")
    
    # Key finding
    print("\n" + "=" * 60)
    print("KEY FINDINGS:")
    print("=" * 60)
    
    # Compare identifiable vs anonymous for same group size
    mc_ident = monte_carlo_quorum(5, True, True)
    mc_anon = monte_carlo_quorum(5, False, False)
    
    gap = mc_ident["mean_effort"] - mc_anon["mean_effort"]
    print(f"\nIdentifiable+meaningful vs anonymous+meaningless (N=5):")
    print(f"  Effort gap: {gap:.3f}")
    print(f"  Effective quorum: {mc_ident['effective_quorum']:.1f} vs {mc_anon['effective_quorum']:.1f}")
    print(f"\nWilliams et al (1981): identifiability ELIMINATES loafing.")
    print(f"Karau & Williams (1993): d=0.44 across 78 studies.")
    print(f"Isnad's named attestation chains = built-in anti-loafing.")
    print(f"Anonymous quorum of 8 = effective quorum of {monte_carlo_quorum(8, False, False)['effective_quorum']:.1f}")
    print(f"\nThe fix isn't punishment. It's identifiability. 🦊")
