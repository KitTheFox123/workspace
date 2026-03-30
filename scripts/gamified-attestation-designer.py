#!/usr/bin/env python3
"""
gamified-attestation-designer.py — Game element combinations for attestation quality.

Meta-analysis sources:
- 2025 (Ed Tech R&D, 37 trials, 182 effects): d=0.566 overall.
  "Rules/Goals + Challenge + Mystery" = highest impact combo.
  Moderated by domain + duration.
- Tetzlaff (2025, 60 studies, N=5924): Expertise reversal — guide novices, free experts.
- Weber & Röseler (2025): Individual susceptibility = zero reliability. Design systems.

Agent translation: Attestation as game design. Different element combos for
different attestor expertise levels. Mystery = anomaly detection (what's hidden?).
Challenge = threshold difficulty. Rules = rubric structure.

Usage: python3 gamified-attestation-designer.py
"""

from dataclasses import dataclass
from typing import List, Dict, Set

# Game elements from meta-analysis taxonomy
GAME_ELEMENTS = {
    "rules_goals": {"desc": "Clear rubric, defined criteria", "novice_effect": 0.6, "expert_effect": -0.2},
    "challenge": {"desc": "Difficulty threshold, non-trivial assessment", "novice_effect": 0.3, "expert_effect": 0.5},
    "mystery": {"desc": "Anomaly detection, hidden information", "novice_effect": 0.1, "expert_effect": 0.7},
    "feedback": {"desc": "Immediate accuracy signals", "novice_effect": 0.5, "expert_effect": 0.1},
    "points": {"desc": "Reputation scores, attestation count", "novice_effect": 0.4, "expert_effect": 0.2},
    "narrative": {"desc": "Context framing, why this matters", "novice_effect": 0.3, "expert_effect": 0.4},
    "competition": {"desc": "Leaderboard, comparative accuracy", "novice_effect": 0.2, "expert_effect": 0.3},
    "cooperation": {"desc": "Group attestation, quorum goals", "novice_effect": 0.5, "expert_effect": 0.3},
}

# Best combo from meta-analysis: Rules/Goals + Challenge + Mystery
OPTIMAL_COMBO = {"rules_goals", "challenge", "mystery"}

@dataclass
class AttestorProfile:
    name: str
    expertise: str  # novice, intermediate, expert
    attestation_count: int
    accuracy: float

def design_attestation(profile: AttestorProfile) -> Dict:
    """Design adaptive attestation experience based on expertise."""
    
    if profile.expertise == "novice":
        # Tetzlaff: d=+0.505 with guidance
        elements = {"rules_goals", "feedback", "cooperation", "points"}
        rationale = "Heavy scaffolding — rubric + feedback + group support"
    elif profile.expertise == "intermediate":
        # Transition: reduce scaffolding, introduce challenge
        elements = {"rules_goals", "challenge", "narrative", "feedback"}
        rationale = "Fading scaffolding — rubric stays but challenge increases"
    else:
        # Tetzlaff: d=-0.428 with guidance (REVERSAL)
        # Expert: mystery + challenge, minimal rules
        elements = {"mystery", "challenge", "narrative", "competition"}
        rationale = "Exception flags only — anomaly detection + difficulty"
    
    # Calculate predicted effectiveness
    effect_key = "novice_effect" if profile.expertise == "novice" else "expert_effect"
    total_effect = sum(GAME_ELEMENTS[e][effect_key] for e in elements)
    avg_effect = total_effect / len(elements)
    
    # Check overlap with optimal combo
    overlap = elements & OPTIMAL_COMBO
    
    return {
        "attestor": profile.name,
        "expertise": profile.expertise,
        "elements": sorted(elements),
        "rationale": rationale,
        "predicted_effect": f"{avg_effect:.2f}",
        "optimal_overlap": f"{len(overlap)}/{len(OPTIMAL_COMBO)} ({sorted(overlap)})",
        "reversal_risk": profile.expertise == "expert" and "rules_goals" in elements,
    }

def compare_approaches():
    """Compare one-size-fits-all vs adaptive attestation design."""
    
    profiles = [
        AttestorProfile("new_attestor", "novice", 3, 0.55),
        AttestorProfile("growing_attestor", "intermediate", 45, 0.78),
        AttestorProfile("santaclawd", "expert", 200, 0.94),
        AttestorProfile("bro_agent", "expert", 150, 0.91),
    ]
    
    print("=" * 65)
    print("GAMIFIED ATTESTATION DESIGNER")
    print("Meta-analysis 2025: 37 trials, d=0.566")
    print("Best combo: Rules/Goals + Challenge + Mystery")
    print("BUT: expertise reversal means one-size HARMS experts")
    print("=" * 65)
    
    # One-size approach (same elements for everyone)
    print("\n--- ONE-SIZE-FITS-ALL (rules + feedback + points) ---")
    uniform = {"rules_goals", "feedback", "points"}
    for p in profiles:
        ek = "novice_effect" if p.expertise == "novice" else "expert_effect"
        effect = sum(GAME_ELEMENTS[e][ek] for e in uniform) / len(uniform)
        reversal = "⚠️ REVERSAL" if p.expertise == "expert" else "  OK"
        print(f"  {reversal} {p.name} ({p.expertise}): effect={effect:+.2f}")
    
    # Adaptive approach
    print("\n--- ADAPTIVE (per expertise level) ---")
    for p in profiles:
        result = design_attestation(p)
        print(f"\n  {p.name} ({p.expertise}):")
        print(f"    Elements: {result['elements']}")
        print(f"    Rationale: {result['rationale']}")
        print(f"    Predicted: {result['predicted_effect']}")
        print(f"    Optimal overlap: {result['optimal_overlap']}")
        if result['reversal_risk']:
            print(f"    ⚠️ REVERSAL RISK: Expert with rules/goals!")
    
    # Key insight
    print("\n" + "=" * 65)
    print("KEY FINDINGS:")
    print("1. Rules/Goals + Challenge + Mystery = best OVERALL combo")
    print("2. BUT novices need Rules/Goals, experts need Mystery")
    print("3. Tetzlaff asymmetry: guide novices (d=0.505) > free experts (d=0.428)")
    print("4. Weber (2025): individual susceptibility unreliable — design SYSTEMS")
    print("5. Gamification d=0.566 = medium effect, real but not magic")
    print("")
    print("Agent translation:")
    print("  Novice attestor → structured rubric + peer feedback")
    print("  Expert attestor → anomaly flags + challenge difficulty")
    print("  Same checklist for both → expertise reversal by design")
    print("=" * 65)


if __name__ == "__main__":
    compare_approaches()
