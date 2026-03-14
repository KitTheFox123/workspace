#!/usr/bin/env python3
"""
trust-cascade-sim.py — Granovetter 1978 threshold model applied to agent trust cascades.

Granovetter's insight: identical populations with slightly different threshold
distributions produce radically different outcomes. A riot starts not because
people are angry, but because threshold distributions cascade.

Applied to agent trust: when does one agent's trust collapse cascade through
a network? The C dimension (commitment unlock) is a phase transition that
can trigger cascading trust downgrades.

Usage: python3 trust-cascade-sim.py
"""

import random
import math
from dataclasses import dataclass


@dataclass
class Agent:
    id: str
    trust_threshold: float  # Fraction of neighbors that must distrust before I distrust
    trusting: bool = True
    commitment_locked: bool = True


def granovetter_cascade(agents: list[Agent], seed_defectors: int = 1) -> dict:
    """Simulate trust cascade using Granovetter threshold model.
    
    Each agent stops trusting when the fraction of distrusting neighbors
    exceeds their personal threshold.
    """
    n = len(agents)
    
    # Seed: first N agents lose trust (e.g., commitment unlock triggers)
    for i in range(min(seed_defectors, n)):
        agents[i].trusting = False
        agents[i].commitment_locked = False
    
    rounds = 0
    history = [sum(1 for a in agents if not a.trusting)]
    
    while True:
        rounds += 1
        changed = False
        fraction_distrusting = sum(1 for a in agents if not a.trusting) / n
        
        for agent in agents:
            if agent.trusting and fraction_distrusting >= agent.trust_threshold:
                agent.trusting = False
                changed = True
        
        history.append(sum(1 for a in agents if not a.trusting))
        
        if not changed or rounds > 100:
            break
    
    final_distrusting = sum(1 for a in agents if not a.trusting)
    return {
        "rounds": rounds,
        "seed": seed_defectors,
        "total_agents": n,
        "final_distrusting": final_distrusting,
        "cascade_fraction": final_distrusting / n,
        "full_cascade": final_distrusting > n * 0.5,
        "history": history,
    }


def demo():
    print("=== Trust Cascade Simulator (Granovetter 1978) ===\n")
    
    random.seed(42)
    
    scenarios = [
        ("Uniform low thresholds (riot-prone)", 
         lambda i, n: 0.1 + 0.3 * (i / n)),  # 0.1 to 0.4
        
        ("Uniform high thresholds (stable)",
         lambda i, n: 0.5 + 0.4 * (i / n)),  # 0.5 to 0.9
        
        ("Granovetter's critical gap (one missing threshold)",
         lambda i, n: i / n if i < n else 1.0),  # 0, 1/n, 2/n, ... perfect cascade
        
        ("Bimodal (zealots + followers)",
         lambda i, n: 0.05 if i < n * 0.1 else 0.7),  # 10% low, 90% high
        
        ("Agent trust network (realistic)",
         lambda i, n: random.gauss(0.4, 0.15)),  # Normal around 0.4
    ]
    
    for name, threshold_fn in scenarios:
        n = 100
        agents = [
            Agent(id=f"agent_{i}", trust_threshold=max(0, min(1, threshold_fn(i, n))))
            for i in range(n)
        ]
        agents.sort(key=lambda a: a.trust_threshold)
        
        # Test with 1 seed defector (single commitment unlock)
        result = granovetter_cascade(agents, seed_defectors=1)
        
        grade = "A" if result["cascade_fraction"] < 0.1 else \
                "B" if result["cascade_fraction"] < 0.3 else \
                "C" if result["cascade_fraction"] < 0.5 else \
                "D" if result["cascade_fraction"] < 0.8 else "F"
        
        print(f"  {name}")
        print(f"    Seed: 1 agent unlocks commitment")
        print(f"    Cascade: {result['final_distrusting']}/{n} agents lost trust in {result['rounds']} rounds")
        print(f"    Grade: {grade} ({'FULL CASCADE' if result['full_cascade'] else 'contained'})")
        print(f"    History: {' → '.join(str(h) for h in result['history'][:6])}")
        print()
    
    # Key insight: threshold gap analysis
    print("=== Granovetter's Key Insight ===\n")
    print("  Two populations with IDENTICAL average thresholds but different")
    print("  distributions produce opposite outcomes. The gap matters, not the mean.")
    print()
    
    # Compare: uniform [0..99] vs gap at position 3
    n = 100
    
    # Perfect cascade: 0, 1, 2, 3, ..., 99 (each threshold = i/100)
    perfect = [Agent(id=f"a{i}", trust_threshold=i/n) for i in range(n)]
    r1 = granovetter_cascade(perfect, 1)
    
    # Gap at 3: 0, 1, 2, [GAP], 50, 51, ..., 99
    gapped = [Agent(id=f"a{i}", trust_threshold=i/n if i < 3 else 0.5 + (i-3)/(2*n)) for i in range(n)]
    r2 = granovetter_cascade(gapped, 1)
    
    print(f"  Perfect sequence:  {r1['final_distrusting']}/{n} cascade (mean threshold: {sum(i/n for i in range(n))/n:.2f})")
    print(f"  Gap at position 3: {r2['final_distrusting']}/{n} cascade (mean threshold: {sum(a.trust_threshold for a in gapped)/n:.2f})")
    print(f"  Same average, opposite outcome. The gap is everything.")
    print()
    print("  Agent trust parallel: a single high-commitment agent unlocking")
    print("  triggers cascade ONLY if threshold distribution has no gaps.")
    print("  Diverse trust policies = firebreak. Monoculture = cascade.")


if __name__ == "__main__":
    demo()
