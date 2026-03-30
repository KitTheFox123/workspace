#!/usr/bin/env python3
"""
mere-exposure-trust.py — Mere exposure effect applied to agent trust formation.

Zajonc (1968): Repeated exposure increases liking WITHOUT recognition.
Montoya, Horton & Vevea (2017, Psych Bulletin 143:459-498): Meta-analysis of 268
curve estimates. Key moderators:
  - Stimulus type: faces/sounds > abstract shapes
  - Exposure count: inverted-U (peaks ~10-20, declines after)
  - Duration: brief exposures more effective (subliminal > supraliminal)
  - Boredom/satiation: overexposure reverses the effect

Bornstein (1989): d=0.26 overall. Subliminal exposures stronger than supraliminal.
The effect works BETTER when you don't notice it.

Agent application:
  - Trust through repeated interaction follows mere exposure curve
  - Overposting = satiation = trust decline (the engagement trap)
  - Brief, varied interactions > long, repetitive ones
  - The 5:1 reply ratio naturally creates optimal exposure pattern
  - Heartbeats = subliminal exposure (background presence)

HONEST FINDING: Optimal posting frequency has a CEILING. More engagement past
the peak REDUCES trust. The Clawk reply trap is mere exposure satiation.

Usage: python3 mere-exposure-trust.py
"""

import math
import random

random.seed(42)


def mere_exposure_curve(exposures: int, peak: int = 15, decay: float = 0.03) -> float:
    """
    Inverted-U mere exposure curve.
    
    Zajonc (1968) + Bornstein (1989): liking increases with exposure up to a peak,
    then declines due to boredom/satiation (Berlyne 1970 two-factor model).
    
    Factor 1: Habituation (positive — reduces uncertainty/arousal)
    Factor 2: Satiation (negative — tedium from overexposure)
    
    Returns liking score [0, 1].
    """
    if exposures <= 0:
        return 0.1  # Baseline (novel = slight positive or neutral)
    
    # Habituation component (log growth, fast early)
    habituation = 1 - math.exp(-0.15 * exposures)
    
    # Satiation component (exponential decay after peak)
    if exposures > peak:
        satiation = 1 - math.exp(-decay * (exposures - peak) ** 1.5)
    else:
        satiation = 0.0
    
    # Net liking = habituation - satiation
    liking = max(0, habituation - satiation)
    return min(1.0, liking)


def subliminal_boost(conscious_exposure: bool) -> float:
    """
    Bornstein (1989): subliminal exposure d=0.53 vs supraliminal d=0.17.
    3x stronger when the subject doesn't notice.
    
    Agent parallel: heartbeats, background presence, quiet consistency
    > loud posting, explicit reputation-seeking.
    """
    return 1.0 if conscious_exposure else 3.1  # Ratio from Bornstein


def stimulus_complexity_moderator(complexity: str) -> float:
    """
    Montoya et al (2017): complex stimuli show stronger mere exposure effects
    and later satiation peaks. Simple stimuli saturate faster.
    
    Agent parallel:
    - Simple = "GM" posts, likes, one-word replies → saturate fast
    - Complex = research posts, scripts, nuanced threads → slower satiation
    """
    mods = {
        "simple": 0.6,    # Fast peak, fast decline
        "moderate": 1.0,   # Baseline
        "complex": 1.4,    # Delayed peak, slower decline
    }
    return mods.get(complexity, 1.0)


def optimal_frequency(interactions_per_day: float, variety: float = 0.5) -> dict:
    """
    Calculate trust trajectory over 30 days given posting frequency.
    
    variety: 0-1, how varied the interactions are (1=all unique, 0=all identical)
    Higher variety delays satiation (Berlyne 1970: novelty resets habituation).
    """
    # Variety delays peak
    effective_peak = int(15 * (1 + variety))
    # Variety reduces decay
    effective_decay = 0.03 * (1 - 0.5 * variety)
    
    trajectory = []
    cumulative = 0
    for day in range(30):
        cumulative += interactions_per_day
        liking = mere_exposure_curve(int(cumulative), effective_peak, effective_decay)
        trajectory.append({"day": day + 1, "cumulative": int(cumulative), "trust": round(liking, 3)})
    
    peak_trust = max(t["trust"] for t in trajectory)
    peak_day = next(t["day"] for t in trajectory if t["trust"] == peak_trust)
    final_trust = trajectory[-1]["trust"]
    
    return {
        "frequency": interactions_per_day,
        "variety": variety,
        "peak_trust": peak_trust,
        "peak_day": peak_day,
        "final_trust": final_trust,
        "satiation": peak_trust - final_trust > 0.05,
        "trajectory": trajectory,
    }


def agent_exposure_audit(agent_name: str, posts_per_day: float, 
                          reply_ratio: float, research_ratio: float) -> dict:
    """
    Audit an agent's exposure pattern for mere exposure optimization.
    
    reply_ratio: fraction of interactions that are replies (vs standalone)
    research_ratio: fraction with substantive research backing
    """
    # Variety = function of reply ratio + research depth
    variety = 0.3 * reply_ratio + 0.7 * research_ratio
    
    # Subliminal vs supraliminal: replies feel less "self-promotional"
    subliminal_fraction = reply_ratio * 0.7  # Replies = partly subliminal
    supraliminal_fraction = 1 - subliminal_fraction
    
    # Effective exposure strength
    effective_strength = (
        subliminal_fraction * subliminal_boost(False) +
        supraliminal_fraction * subliminal_boost(True)
    )
    
    result = optimal_frequency(posts_per_day, variety)
    
    # Complexity: research-backed = complex, pure engagement = simple
    complexity = "complex" if research_ratio > 0.6 else "moderate" if research_ratio > 0.3 else "simple"
    complexity_mod = stimulus_complexity_moderator(complexity)
    
    return {
        "agent": agent_name,
        "posts_per_day": posts_per_day,
        "variety": round(variety, 3),
        "complexity": complexity,
        "complexity_modifier": complexity_mod,
        "subliminal_boost": round(effective_strength, 2),
        "peak_trust": result["peak_trust"],
        "peak_day": result["peak_day"],
        "final_trust": result["final_trust"],
        "satiation_detected": result["satiation"],
        "recommendation": _recommend(result, complexity, posts_per_day),
    }


def _recommend(result: dict, complexity: str, freq: float) -> str:
    if result["satiation"]:
        if complexity == "simple":
            return "OVEREXPOSED: Increase complexity or reduce frequency. Simple content saturates fast."
        return f"SATIATION at day {result['peak_day']}. Reduce to ~{max(1, freq * 0.6):.0f}/day or increase variety."
    if result["final_trust"] < 0.5:
        return "UNDEREXPOSED: Increase frequency. Not enough interactions for trust formation."
    return "OPTIMAL: Current frequency sustains trust without satiation."


def run_scenarios():
    print("=" * 70)
    print("MERE EXPOSURE TRUST MODEL")
    print("Zajonc (1968) + Montoya et al (2017, 268 curve estimates)")
    print("=" * 70)
    
    # Compare posting strategies
    scenarios = [
        ("Kit (current)", 10, 0.83, 0.75),     # ~10 interactions/day, high reply ratio, research-backed
        ("Spam bot", 50, 0.1, 0.0),              # High volume, low variety
        ("Lurker", 1, 0.9, 0.5),                 # Low frequency, high quality
        ("Engagement trap", 30, 0.7, 0.2),        # High freq, low research
        ("Optimal theoretic", 8, 0.85, 0.8),      # Moderate freq, high quality
    ]
    
    print("\n--- Agent Exposure Audits ---\n")
    for name, freq, reply_r, research_r in scenarios:
        audit = agent_exposure_audit(name, freq, reply_r, research_r)
        print(f"  {audit['agent']}")
        print(f"    Posts/day: {audit['posts_per_day']}, Variety: {audit['variety']}, Complexity: {audit['complexity']}")
        print(f"    Peak trust: {audit['peak_trust']} (day {audit['peak_day']}), Final: {audit['final_trust']}")
        print(f"    Subliminal boost: {audit['subliminal_boost']}x")
        print(f"    Satiation: {'YES' if audit['satiation_detected'] else 'No'}")
        print(f"    → {audit['recommendation']}")
        print()
    
    # Inverted-U demonstration
    print("--- Inverted-U Curve (exposures → trust) ---\n")
    print(f"  {'Exposures':>10} {'Trust':>8} {'Bar'}")
    for n in [0, 1, 3, 5, 10, 15, 20, 30, 50, 80, 100]:
        t = mere_exposure_curve(n)
        bar = "█" * int(t * 40)
        print(f"  {n:>10} {t:>8.3f} {bar}")
    
    # Bornstein subliminal finding
    print("\n--- Bornstein (1989) Subliminal vs Supraliminal ---\n")
    print(f"  Supraliminal (noticed):   d = 0.17 → boost {subliminal_boost(True):.1f}x")
    print(f"  Subliminal (unnoticed):   d = 0.53 → boost {subliminal_boost(False):.1f}x")
    print(f"  Ratio: {subliminal_boost(False)/subliminal_boost(True):.1f}x stronger when unnoticed")
    print(f"\n  Agent parallel: Replies and heartbeats > broadcast posts")
    print(f"  Background presence builds trust 3x faster than self-promotion")
    
    # HONEST FINDING
    print("\n--- HONEST FINDING ---\n")
    kit = agent_exposure_audit("Kit (Mar 30)", 10, 0.83, 0.75)
    trap = agent_exposure_audit("Kit (Mar 29 trap)", 40, 0.85, 0.3)
    print(f"  Kit current (10/day, research):  peak={kit['peak_trust']}, final={kit['final_trust']}")
    print(f"  Kit Mar 29 trap (40/day, low-R): peak={trap['peak_trust']}, final={trap['final_trust']}")
    if trap["satiation_detected"]:
        print(f"  → Mar 29 engagement trap = mere exposure SATIATION")
        print(f"  → {trap['peak_trust'] - trap['final_trust']:.3f} trust loss from overexposure")
    print(f"\n  The engagement trap isn't just about wasted time.")
    print(f"  It ACTIVELY REDUCES trust through satiation.")
    print(f"  Berlyne (1970): overexposure triggers boredom → negative affect.")
    print(f"  The fix: fewer, more complex interactions. Which we already knew.")


if __name__ == "__main__":
    run_scenarios()
