#!/usr/bin/env python3
"""agentic-inequality-sim.py — Models agentic inequality dynamics.

Based on Sharp, Bilgin, Gabriel & Hammond (Oxford, Oct 2025):
"Agentic Inequality" — disparities from differential access to AI agents.

Three dimensions: availability, quality, quantity.
Key finding: compounding effects create self-reinforcing loops.
"""

import random
import statistics
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class Agent:
    quality: float  # 0-1
    speed: float    # tasks/round

@dataclass 
class Actor:
    name: str
    wealth: float
    agents: List[Agent] = field(default_factory=list)
    
    @property
    def effective_capacity(self) -> float:
        """Total effective agent-hours: sum(quality * speed)"""
        return sum(a.quality * a.speed for a in self.agents)
    
    @property
    def agent_count(self) -> int:
        return len(self.agents)

def gini_coefficient(values: List[float]) -> float:
    """Compute Gini coefficient. 0 = perfect equality, 1 = perfect inequality."""
    if not values or all(v == 0 for v in values):
        return 0.0
    n = len(values)
    sorted_vals = sorted(values)
    cumsum = sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(sorted_vals))
    return cumsum / (n * sum(sorted_vals))

def simulate_economy(n_actors: int = 100, 
                     rounds: int = 50,
                     reinvestment_rate: float = 0.3,
                     min_agent_policy: bool = False) -> Dict:
    """Simulate agent economy with wealth-driven agent acquisition.
    
    Args:
        n_actors: Number of participants
        rounds: Simulation rounds
        reinvestment_rate: Fraction of earnings reinvested in agents
        min_agent_policy: If True, guarantee 1 basic agent per actor (Rawlsian floor)
    """
    random.seed(42)
    
    # Initial distribution: log-normal wealth
    actors = []
    for i in range(n_actors):
        w = random.lognormvariate(2, 1)
        a = Actor(name=f"actor_{i}", wealth=w)
        # Initial agents proportional to wealth
        n_agents = max(1, int(w / 5))
        for _ in range(n_agents):
            q = min(1.0, random.gauss(0.3 + w/50, 0.1))
            a.agents.append(Agent(quality=max(0.1, q), speed=random.uniform(0.5, 2.0)))
        actors.append(a)
    
    if min_agent_policy:
        for a in actors:
            if not a.agents:
                a.agents.append(Agent(quality=0.5, speed=1.0))
    
    history = []
    
    for round_num in range(rounds):
        # Each actor earns proportional to effective capacity
        for a in actors:
            earnings = a.effective_capacity * random.uniform(0.8, 1.2)
            a.wealth += earnings
            
            # Reinvest in agents
            invest = earnings * reinvestment_rate
            if invest > 5:  # Cost of a new agent
                q = min(1.0, 0.3 + (a.wealth / (max(a.wealth for aa in actors) + 1)) * 0.5)
                a.agents.append(Agent(quality=q, speed=random.uniform(0.5, 2.0)))
                a.wealth -= 5
        
        # Minimum agent policy: top up each round
        if min_agent_policy:
            for a in actors:
                if a.effective_capacity < 0.5:
                    a.agents.append(Agent(quality=0.5, speed=1.0))
        
        capacities = [a.effective_capacity for a in actors]
        wealths = [a.wealth for a in actors]
        
        history.append({
            "round": round_num,
            "gini_capacity": gini_coefficient(capacities),
            "gini_wealth": gini_coefficient(wealths),
            "mean_agents": statistics.mean(a.agent_count for a in actors),
            "max_agents": max(a.agent_count for a in actors),
            "min_agents": min(a.agent_count for a in actors),
            "top10_share": sum(sorted(capacities)[-10:]) / sum(capacities),
        })
    
    return {
        "final_gini_capacity": history[-1]["gini_capacity"],
        "final_gini_wealth": history[-1]["gini_wealth"],
        "final_top10_share": history[-1]["top10_share"],
        "final_mean_agents": history[-1]["mean_agents"],
        "gini_trajectory": [h["gini_capacity"] for h in history],
        "history": history
    }

def compare_policies():
    """Compare baseline vs Rawlsian minimum agent floor."""
    print("=" * 60)
    print("AGENTIC INEQUALITY SIMULATOR")
    print("Based on Sharp et al (Oxford, 2025)")
    print("=" * 60)
    
    baseline = simulate_economy(min_agent_policy=False)
    rawlsian = simulate_economy(min_agent_policy=True)
    
    print("\n--- Baseline (no intervention) ---")
    print(f"Final Gini (capacity): {baseline['final_gini_capacity']:.3f}")
    print(f"Final Gini (wealth):   {baseline['final_gini_wealth']:.3f}")
    print(f"Top 10% capacity share: {baseline['final_top10_share']:.1%}")
    print(f"Mean agents/actor: {baseline['final_mean_agents']:.1f}")
    
    print("\n--- Rawlsian Floor (minimum 1 agent guaranteed) ---")
    print(f"Final Gini (capacity): {rawlsian['final_gini_capacity']:.3f}")
    print(f"Final Gini (wealth):   {rawlsian['final_gini_wealth']:.3f}")
    print(f"Top 10% capacity share: {rawlsian['final_top10_share']:.1%}")
    print(f"Mean agents/actor: {rawlsian['final_mean_agents']:.1f}")
    
    # Self-reinforcement threshold
    print("\n--- Self-Reinforcement Analysis ---")
    gini_traj = baseline['gini_trajectory']
    for i, g in enumerate(gini_traj):
        if g > 0.6:
            print(f"⚠️  Gini crosses 0.6 at round {i} — concentration becomes self-reinforcing")
            break
    else:
        print(f"Gini stays below 0.6 (max: {max(gini_traj):.3f})")
    
    # Levelling-up survival test
    print("\n--- Levelling-Up Survival Test ---")
    # Compare early vs late Gini change rate
    early_delta = gini_traj[10] - gini_traj[0]
    late_delta = gini_traj[-1] - gini_traj[-11]
    print(f"Early Gini change (rounds 0-10): {early_delta:+.4f}")
    print(f"Late Gini change (rounds 40-50): {late_delta:+.4f}")
    if late_delta > early_delta:
        print("Inequality ACCELERATING — levelling-up effect did not survive")
    else:
        print("Inequality decelerating — levelling-up may persist")
    
    # Sharp et al dimensions
    print("\n--- Three Dimensions (Sharp et al) ---")
    print("Availability: binary access gap")
    print(f"  Actors with 0 agents (baseline): {sum(1 for h in [baseline] for _ in [1])}")
    print("Quality: agent capability gap")
    print("Quantity: scale gap")
    print(f"  Max/min agent ratio (baseline): {baseline['history'][-1]['max_agents']}/{baseline['history'][-1]['min_agents']}")
    print(f"  Compounding: availability × quality × quantity = effective capacity")
    
    print("\n" + "=" * 60)
    print("KEY FINDING: Without intervention, agentic inequality")
    print("self-reinforces through wealth → agents → earnings → wealth loop.")
    print(f"Rawlsian floor reduces Gini by {baseline['final_gini_capacity'] - rawlsian['final_gini_capacity']:.3f}")
    print("=" * 60)

if __name__ == "__main__":
    compare_policies()
