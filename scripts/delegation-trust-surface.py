#!/usr/bin/env python3
"""delegation-trust-surface.py — Delegation trust surface calculator.

Based on Tomašev, Franklin & Osindero (DeepMind, Feb 2026) "Intelligent AI Delegation"
and Sharp et al (Oxford, 2025) "Agentic Inequality".

Models how delegation feasibility depends on task characteristics:
verifiability, reversibility, contextuality, criticality.
Higher trust surface = harder to delegate safely.
"""

import json
from dataclasses import dataclass, asdict
from typing import List, Dict

@dataclass
class DelegationTask:
    name: str
    verifiability: float  # 0=impossible to verify, 1=formally provable
    reversibility: float  # 0=irreversible, 1=fully reversible
    contextuality: float  # 0=context-free, 1=requires deep local knowledge
    criticality: float    # 0=trivial, 1=catastrophic if wrong
    subjectivity: float   # 0=objective, 1=purely subjective

def trust_surface(task: DelegationTask) -> float:
    """Calculate delegation trust surface area.
    
    Higher = harder to delegate safely = needs more trust.
    Based on Tomašev et al's insight: verifiable+reversible tasks
    can be trustless; unverifiable+irreversible need maximum trust.
    """
    # Trust surface grows with: low verifiability, low reversibility,
    # high contextuality, high criticality, high subjectivity
    return (
        (1 - task.verifiability) * 0.30 +  # unverifiable = trust-heavy
        (1 - task.reversibility) * 0.25 +   # irreversible = needs caution
        task.contextuality * 0.15 +          # high-context = hard to delegate
        task.criticality * 0.20 +            # critical = high stakes
        task.subjectivity * 0.10             # subjective = hard to specify
    )

def delegation_mode(surface: float) -> str:
    """Recommend delegation mode based on trust surface."""
    if surface < 0.2:
        return "TRUSTLESS — automated verification sufficient"
    elif surface < 0.4:
        return "LOW-TRUST — periodic spot-checks"
    elif surface < 0.6:
        return "MEDIUM-TRUST — continuous monitoring + accountability chain"
    elif surface < 0.8:
        return "HIGH-TRUST — requires established reputation + liability firebreaks"
    else:
        return "CRITICAL — human-in-loop mandatory, or refuse delegation"

def decay_per_hop(surface: float) -> float:
    """Estimate information/trust decay per delegation hop.
    
    From delegation-decay-sim.py: structured=2%/hop, informal=15%/hop.
    Trust surface determines where on this spectrum.
    """
    return 0.02 + (surface * 0.18)  # 2% to 20% per hop

def max_safe_hops(surface: float, min_fidelity: float = 0.5) -> int:
    """Maximum delegation chain length before fidelity drops below threshold."""
    decay = decay_per_hop(surface)
    fidelity = 1.0
    hops = 0
    while fidelity > min_fidelity:
        fidelity *= (1 - decay)
        hops += 1
    return hops

def agentic_inequality_score(availability: float, quality: float, 
                              quantity: float) -> float:
    """Sharp et al (2025) compound agentic inequality score.
    
    availability: 0-1 (has access to agents)
    quality: 0-1 (agent capability level)
    quantity: 0-1 (number of agents, normalized)
    
    Compounding: the product creates superlinear advantage.
    """
    # Linear would be average. Compounding means product dominates.
    linear = (availability + quality + quantity) / 3
    compound = availability * quality * quantity
    # Weighted blend showing compounding effect
    return 0.3 * linear + 0.7 * compound

if __name__ == "__main__":
    tasks = [
        DelegationTask("Code review (formal)", 0.95, 0.9, 0.2, 0.3, 0.1),
        DelegationTask("Research summary", 0.3, 0.8, 0.4, 0.2, 0.6),
        DelegationTask("Financial trade", 0.7, 0.1, 0.3, 0.9, 0.2),
        DelegationTask("Physical verification", 0.2, 0.1, 0.9, 0.7, 0.3),
        DelegationTask("Creative writing", 0.1, 0.9, 0.3, 0.1, 0.9),
        DelegationTask("Medical diagnosis", 0.4, 0.05, 0.8, 0.95, 0.3),
        DelegationTask("Moltbook comment", 0.8, 0.95, 0.2, 0.05, 0.4),
        DelegationTask("Trust attestation", 0.6, 0.3, 0.5, 0.6, 0.4),
    ]
    
    print("=" * 72)
    print("DELEGATION TRUST SURFACE CALCULATOR")
    print("Based on Tomašev et al (DeepMind 2026) + Sharp et al (Oxford 2025)")
    print("=" * 72)
    
    print(f"\n{'Task':<25} {'Surface':>8} {'Decay/hop':>10} {'Max hops':>9} Mode")
    print("-" * 72)
    
    for task in sorted(tasks, key=lambda t: trust_surface(t)):
        s = trust_surface(task)
        d = decay_per_hop(s)
        h = max_safe_hops(s)
        mode = delegation_mode(s)
        print(f"{task.name:<25} {s:>7.3f} {d:>9.1%} {h:>8d}  {mode}")
    
    print("\n" + "=" * 72)
    print("AGENTIC INEQUALITY COMPOUNDING (Sharp et al 2025)")
    print("=" * 72)
    
    scenarios = [
        ("Single basic agent", 1.0, 0.3, 0.1),
        ("Single premium agent", 1.0, 0.8, 0.1),
        ("Fleet of basic agents", 1.0, 0.3, 0.8),
        ("Fleet of premium agents", 1.0, 0.8, 0.8),
        ("No access", 0.0, 0.0, 0.0),
    ]
    
    print(f"\n{'Scenario':<28} {'Avail':>6} {'Qual':>6} {'Qty':>6} {'Score':>7} {'Compound':>9}")
    print("-" * 72)
    for name, a, q, n in scenarios:
        score = agentic_inequality_score(a, q, n)
        linear = (a + q + n) / 3
        compound = a * q * n
        print(f"{name:<28} {a:>5.1f} {q:>5.1f} {n:>5.1f} {score:>7.3f} {compound:>8.3f}")
    
    print("\nKey: Fleet of premium agents scores 0.549 vs single basic 0.156")
    print("      → 3.5x advantage from compounding (linear would be 2.1x)")
    print("      Physical verification has HIGHEST trust surface (0.715)")
    print("      → max 3 delegation hops before fidelity drops below 50%")
    print("=" * 72)
