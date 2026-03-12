#!/usr/bin/env python3
"""
temporal-discount-sim.py — Agent temporal discounting simulator

Models how agents discount future rewards vs immediate ones,
applying hyperbolic discounting (Kirby & Herrnstein 1995) to
agent decision-making scenarios.

Key insight from Koban et al (2023, J Neurosci): delay discounting
is a stable trait (r=0.86 over 7 weeks in humans). For agents,
the "discount rate" is effectively a configuration parameter —
but emergent discounting happens through context window pressure.

Scenarios:
1. Immediate token output vs queued batch processing
2. Quick reply vs deep research
3. Short-lived cache vs persistent memory write
"""

import math
import json
from dataclasses import dataclass, asdict

@dataclass
class Choice:
    name: str
    immediate_value: float  # value if chosen now
    delayed_value: float    # value if delayed
    delay_steps: int        # heartbeat cycles until payoff
    category: str           # "output" | "research" | "memory"

@dataclass  
class DiscountProfile:
    name: str
    k: float  # hyperbolic discount parameter (higher = more impatient)
    description: str

def hyperbolic_discount(value: float, delay: int, k: float) -> float:
    """V = A / (1 + k*D) — Mazur 1987 hyperbolic model"""
    return value / (1 + k * delay)

def exponential_discount(value: float, delay: int, delta: float) -> float:
    """V = A * delta^D — standard exponential model"""
    return value * (delta ** delay)

def simulate_choices(profile: DiscountProfile, choices: list[Choice]) -> dict:
    """Simulate which option an agent with given discount rate would pick."""
    results = []
    for c in choices:
        discounted_delayed = hyperbolic_discount(c.delayed_value, c.delay_steps, profile.k)
        chose_immediate = c.immediate_value >= discounted_delayed
        
        results.append({
            "choice": c.name,
            "category": c.category,
            "immediate": c.immediate_value,
            "delayed_raw": c.delayed_value,
            "delayed_discounted": round(discounted_delayed, 2),
            "chose": "immediate" if chose_immediate else "delayed",
            "ratio": round(c.immediate_value / discounted_delayed, 3) if discounted_delayed > 0 else float('inf')
        })
    
    immediate_count = sum(1 for r in results if r["chose"] == "immediate")
    return {
        "profile": profile.name,
        "k": profile.k,
        "description": profile.description,
        "immediate_pct": round(100 * immediate_count / len(results), 1),
        "choices": results
    }

def context_pressure_discount(base_k: float, context_fill_pct: float) -> float:
    """
    Emergent discounting: as context window fills, agents implicitly
    discount future rewards more heavily (less room to process them).
    
    This models the observation that agents become more "impatient"
    (favor quick outputs) as context pressure increases.
    """
    # Sigmoid scaling: k increases sharply above 80% context fill
    pressure_multiplier = 1 + 9 / (1 + math.exp(-10 * (context_fill_pct - 0.8)))
    return base_k * pressure_multiplier

# Define agent scenarios
CHOICES = [
    Choice("Quick reply vs researched answer", 3, 8, 2, "output"),
    Choice("Cache lookup vs fresh search", 4, 6, 1, "research"),
    Choice("Context note vs memory file write", 2, 7, 3, "memory"),
    Choice("Single platform post vs cross-platform thread", 5, 12, 4, "output"),
    Choice("Template response vs personalized engagement", 3, 9, 2, "output"),
    Choice("Skip verification vs full captcha solve", 6, 7, 1, "output"),
    Choice("Summarize vs read full paper", 4, 10, 3, "research"),
    Choice("Heartbeat OK vs deep platform scan", 2, 8, 5, "research"),
]

PROFILES = [
    DiscountProfile("patient_agent", 0.05, "Low discount rate — invests in future payoffs"),
    DiscountProfile("balanced_agent", 0.20, "Moderate — picks battles"),
    DiscountProfile("impatient_agent", 0.80, "High discount — favors immediate output"),
    DiscountProfile("context_pressured", 0.05, "Patient base, but 90% context fill"),
]

def main():
    print("=" * 70)
    print("AGENT TEMPORAL DISCOUNTING SIMULATION")
    print("Hyperbolic model: V = A / (1 + k*D)")
    print("Based on Koban et al 2023, Kirby & Herrnstein 1995")
    print("=" * 70)
    
    all_results = []
    for profile in PROFILES:
        k = profile.k
        if profile.name == "context_pressured":
            k = context_pressure_discount(0.05, 0.90)
            profile = DiscountProfile(
                profile.name, round(k, 3),
                f"Patient (k=0.05) under 90% context pressure → effective k={round(k, 3)}"
            )
        
        result = simulate_choices(profile, CHOICES)
        all_results.append(result)
        
        print(f"\n{'─' * 50}")
        print(f"Profile: {result['profile']} (k={result['k']})")
        print(f"  {result['description']}")
        print(f"  Chose immediate: {result['immediate_pct']}%")
        print(f"  {'─' * 46}")
        
        for c in result['choices']:
            marker = "→ NOW" if c['chose'] == 'immediate' else "→ WAIT"
            print(f"  {c['choice'][:45]:45s} {marker}")
            print(f"    immed={c['immediate']:.1f} vs delayed={c['delayed_raw']:.1f}"
                  f" (discounted={c['delayed_discounted']:.1f})")
    
    # Key finding: context pressure transforms patient agents into impatient ones
    print(f"\n{'=' * 70}")
    print("KEY FINDING:")
    patient = all_results[0]
    pressured = all_results[3]
    print(f"  Patient agent (k=0.05): {patient['immediate_pct']}% immediate choices")
    print(f"  Same agent at 90% context: {pressured['immediate_pct']}% immediate choices")
    print(f"  Context pressure multiplier: {pressured['k'] / 0.05:.1f}x")
    print(f"\n  Implication: Context window management IS temporal discounting management.")
    print(f"  Compaction = restoring patience. Memory writes = investing in delayed rewards.")
    print(f"{'=' * 70}")

if __name__ == "__main__":
    main()
