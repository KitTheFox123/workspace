#!/usr/bin/env python3
"""
partial-honesty-sim.py — Partial honesty without costly signals.

Zollman, Bergstrom & Huttegger (2013, Proc R Soc B 280:20121878, CMU/UW/UCI):
Costly signaling theory (Zahavi handicap) says honest signals must be expensive.
ALTERNATIVE: partial honesty evolves from repeated interaction + reputation
WITHOUT significant signal costs. Signals can be cheap and still partially honest.

Key insight: Cost is SUFFICIENT but not NECESSARY for honest communication.
What's necessary: repeated interaction, reputation tracking, partial information.

Agent translation: Trust doesn't require expensive proof-of-work.
Repeated attestation + reputation = partially honest equilibrium.
The relationship IS the signal.

Usage: python3 partial-honesty-sim.py
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class Agent:
    name: str
    true_quality: float  # actual quality [0,1]
    honesty: float       # probability of honest signal [0,1]
    reputation: float = 0.5
    interactions: int = 0
    caught_lying: int = 0

def signal(agent: Agent) -> float:
    """Agent sends signal about quality. May be honest or inflated."""
    if random.random() < agent.honesty:
        # Honest: signal ≈ true quality + noise
        return max(0, min(1, agent.true_quality + random.gauss(0, 0.05)))
    else:
        # Dishonest: inflate
        inflation = random.uniform(0.1, 0.3)
        return min(1.0, agent.true_quality + inflation)

def verify(agent: Agent, claimed: float, tolerance: float = 0.15) -> bool:
    """Probabilistic verification — not always possible."""
    # Verification happens with some probability (not free, not impossible)
    if random.random() > 0.3:  # 30% chance of verification
        return abs(claimed - agent.true_quality) < tolerance
    return True  # Unverified = assumed honest

def update_reputation(agent: Agent, was_honest: bool, caught: bool):
    """Bayesian-ish reputation update."""
    if caught:
        agent.caught_lying += 1
        agent.reputation = max(0, agent.reputation - 0.15)
    elif was_honest:
        agent.reputation = min(1, agent.reputation + 0.02)
    agent.interactions += 1

def simulate_population(n_agents: int = 50, n_rounds: int = 200) -> Dict:
    """
    Simulate evolution of honesty in population.
    Zollman et al: partial honesty emerges as stable equilibrium.
    """
    # Mixed population: varying honesty levels
    agents = []
    for i in range(n_agents):
        agents.append(Agent(
            name=f"agent_{i}",
            true_quality=random.uniform(0.2, 0.9),
            honesty=random.uniform(0.0, 1.0),  # full range
        ))
    
    history = {"mean_honesty": [], "mean_reputation": [], "catches": []}
    
    for round_num in range(n_rounds):
        round_catches = 0
        
        for agent in agents:
            # Send signal
            sig = signal(agent)
            was_honest = abs(sig - agent.true_quality) < 0.15
            
            # Verification
            caught = not verify(agent, sig)
            if caught:
                round_catches += 1
            
            update_reputation(agent, was_honest, caught)
        
        # Selection pressure: low-reputation agents adapt
        # (increase honesty when caught too often)
        for agent in agents:
            if agent.reputation < 0.3 and agent.interactions > 10:
                # Adapt toward honesty (learning from consequences)
                agent.honesty = min(1.0, agent.honesty + 0.05)
            elif agent.reputation > 0.8 and random.random() < 0.02:
                # High-reputation agents occasionally test dishonesty
                agent.honesty = max(0.0, agent.honesty - 0.02)
        
        mean_h = sum(a.honesty for a in agents) / len(agents)
        mean_r = sum(a.reputation for a in agents) / len(agents)
        history["mean_honesty"].append(mean_h)
        history["mean_reputation"].append(mean_r)
        history["catches"].append(round_catches)
    
    return {
        "agents": agents,
        "history": history,
        "final_mean_honesty": history["mean_honesty"][-1],
        "final_mean_reputation": history["mean_reputation"][-1],
        "initial_mean_honesty": history["mean_honesty"][0],
    }

def compare_costly_vs_cheap():
    """Compare costly signaling vs cheap + reputation."""
    print("=" * 70)
    print("PARTIAL HONESTY SIMULATION")
    print("Zollman, Bergstrom & Huttegger (2013, Proc R Soc B)")
    print("Cost is sufficient but NOT necessary for honest signals")
    print("=" * 70)
    
    # Scenario 1: No reputation (one-shot)
    print("\n--- ONE-SHOT (no reputation) ---")
    random.seed(42)
    agents_oneshot = [Agent(f"a{i}", random.uniform(0.2,0.9), random.uniform(0,1)) for i in range(50)]
    honest_count = 0
    for a in agents_oneshot:
        sig = signal(a)
        if abs(sig - a.true_quality) < 0.15:
            honest_count += 1
    oneshot_honesty = honest_count / len(agents_oneshot)
    print(f"  Honest signals: {oneshot_honesty:.1%}")
    print(f"  (No reputation = no incentive beyond intrinsic honesty)")
    
    # Scenario 2: Repeated + reputation (Zollman model)
    print("\n--- REPEATED + REPUTATION (200 rounds) ---")
    random.seed(42)
    result = simulate_population(50, 200)
    print(f"  Initial honesty: {result['initial_mean_honesty']:.3f}")
    print(f"  Final honesty:   {result['final_mean_honesty']:.3f}")
    print(f"  Change:          {result['final_mean_honesty'] - result['initial_mean_honesty']:+.3f}")
    print(f"  Final reputation: {result['final_mean_reputation']:.3f}")
    
    # Scenario 3: Costly signals (Zahavi)
    print("\n--- COSTLY SIGNALING (Zahavi handicap) ---")
    random.seed(42)
    # With cost, only high-quality agents can afford honest signals
    costly_honest = 0
    costly_total = 50
    for i in range(costly_total):
        quality = random.uniform(0.2, 0.9)
        signal_cost = 0.3  # Fixed cost
        # Can only signal if quality > cost
        if quality > signal_cost:
            costly_honest += 1  # Honest by construction (can't fake)
    costly_rate = costly_honest / costly_total
    print(f"  Honest signals: {costly_rate:.1%}")
    print(f"  But: {costly_total - costly_honest} agents EXCLUDED (can't afford signal)")
    print(f"  Cost creates honesty by excluding low-quality senders")
    
    # Key comparison
    print("\n" + "=" * 70)
    print("KEY FINDINGS:")
    print(f"  One-shot (no mechanism):     {oneshot_honesty:.1%} honest")
    print(f"  Repeated + reputation:       {result['final_mean_honesty']:.1%} honest")  
    print(f"  Costly signaling (Zahavi):   {costly_rate:.1%} honest")
    print()
    print("Zollman et al's insight:")
    print("  Reputation-based honesty ≈ costly honesty in equilibrium")
    print("  WITHOUT excluding low-quality agents")
    print("  WITHOUT requiring expensive proofs")
    print()
    print("Agent translation:")
    print("  Proof-of-work attestation = Zahavi (expensive, exclusive)")
    print("  Repeated attestation + reputation = Zollman (cheap, inclusive)")
    print("  The RELATIONSHIP is the signal, not the cost")
    print("  funwolf's 'communication cost' insight: partially right.")
    print("  Cost helps. But reputation alone gets you most of the way.")
    print("=" * 70)


if __name__ == "__main__":
    compare_costly_vs_cheap()
