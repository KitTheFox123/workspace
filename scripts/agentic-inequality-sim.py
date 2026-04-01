#!/usr/bin/env python3
"""agentic-inequality-sim.py — Models agentic inequality dynamics.

Based on Sharp, Bilgin, Gabriel & Hammond (Oxford, Oct 2025):
"Agentic Inequality" — three dimensions: availability, quality, quantity.
Compounding creates feedback loops. Levelling-up effect may not survive
transition from assistive to autonomous agents.

Simulates Gini coefficient evolution under different policy regimes.
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class Agent:
    quality: float  # 0-1
    compute_hours: float  # per period

@dataclass 
class Participant:
    name: str
    agents: List[Agent] = field(default_factory=list)
    wealth: float = 100.0
    
    @property
    def effective_power(self) -> float:
        """Total agent-hours × quality."""
        return sum(a.quality * a.compute_hours for a in self.agents)
    
    @property
    def agent_count(self) -> int:
        return len(self.agents)

def gini_coefficient(values: List[float]) -> float:
    """Calculate Gini coefficient of a distribution."""
    if not values or all(v == 0 for v in values):
        return 0.0
    n = len(values)
    sorted_vals = sorted(values)
    cumsum = sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(sorted_vals))
    return cumsum / (n * sum(sorted_vals))

def simulate_market(n_participants: int = 50,
                    n_rounds: int = 20,
                    policy: str = "none",
                    initial_inequality: float = 0.3) -> Dict:
    """Simulate agent economy with feedback loops.
    
    Policies:
    - "none": pure market, feedback loops compound
    - "floor": minimum viable agency (everyone gets 1 basic agent)
    - "cap": anti-whale (max 10 agents per participant)
    - "tax": progressive compute tax redistributed as quality upgrades
    - "open": open-source quality floor (min quality = 0.5)
    """
    # Initialize with inequality
    participants = []
    for i in range(n_participants):
        # Pareto-distributed initial wealth
        w = 100 * (random.paretovariate(1.5) if random.random() > initial_inequality else 1.0)
        p = Participant(name=f"p_{i}", wealth=w)
        
        # Initial agent allocation proportional to wealth
        n_agents = max(1, int(w / 50))
        for _ in range(n_agents):
            q = min(1.0, random.gauss(w / 500, 0.1))
            p.agents.append(Agent(quality=max(0.1, q), compute_hours=random.uniform(1, 10)))
        participants.append(p)
    
    gini_history = []
    power_history = []
    
    for round_num in range(n_rounds):
        # Apply policy
        if policy == "floor":
            for p in participants:
                if not p.agents:
                    p.agents.append(Agent(quality=0.3, compute_hours=2.0))
        
        elif policy == "cap":
            for p in participants:
                if len(p.agents) > 10:
                    p.agents = sorted(p.agents, key=lambda a: a.quality, reverse=True)[:10]
        
        elif policy == "tax":
            total_power = sum(p.effective_power for p in participants)
            if total_power > 0:
                tax_pool = 0
                for p in participants:
                    share = p.effective_power / total_power
                    if share > 0.05:  # tax top earners
                        tax = (share - 0.05) * p.effective_power * 0.2
                        tax_pool += tax
                # Redistribute as quality upgrades to bottom half
                bottom = sorted(participants, key=lambda p: p.effective_power)[:n_participants//2]
                per_agent = tax_pool / max(1, sum(p.agent_count for p in bottom))
                for p in bottom:
                    for a in p.agents:
                        a.quality = min(1.0, a.quality + per_agent * 0.01)
        
        elif policy == "open":
            for p in participants:
                for a in p.agents:
                    a.quality = max(0.5, a.quality)
        
        # Market dynamics: agents generate returns proportional to power
        for p in participants:
            returns = p.effective_power * random.uniform(0.8, 1.2) * 0.1
            p.wealth += returns
            
            # Feedback loop: wealth enables acquiring more/better agents
            if p.wealth > 200 and random.random() < 0.3:
                new_q = min(1.0, p.wealth / 1000 + random.gauss(0, 0.1))
                p.agents.append(Agent(quality=max(0.1, new_q), compute_hours=random.uniform(1, 8)))
                p.wealth -= 50
        
        # Record metrics
        powers = [p.effective_power for p in participants]
        gini_history.append(gini_coefficient(powers))
        power_history.append({
            "top_10pct": sum(sorted(powers, reverse=True)[:n_participants//10]) / max(1, sum(powers)),
            "bottom_50pct": sum(sorted(powers)[:n_participants//2]) / max(1, sum(powers)),
            "median_agents": sorted([p.agent_count for p in participants])[n_participants//2],
        })
    
    return {
        "policy": policy,
        "final_gini": gini_history[-1],
        "gini_trajectory": [round(g, 3) for g in gini_history[::5]],
        "final_top10_share": power_history[-1]["top_10pct"],
        "final_bottom50_share": power_history[-1]["bottom_50pct"],
        "final_median_agents": power_history[-1]["median_agents"],
        "concentration_ratio": power_history[-1]["top_10pct"] / max(0.01, power_history[-1]["bottom_50pct"]),
    }

def levelling_effect_test() -> Dict:
    """Test whether levelling-up survives assistive → autonomous transition.
    
    Sharp et al hypothesis: assistive AI levels up novices, but autonomous
    agents may not — because delegation ≠ augmentation.
    """
    results = {}
    
    for mode in ["assistive", "autonomous"]:
        novice_gains = []
        expert_gains = []
        
        for _ in range(100):
            novice_skill = random.uniform(0.2, 0.4)
            expert_skill = random.uniform(0.7, 0.9)
            agent_quality = random.uniform(0.6, 0.9)
            
            if mode == "assistive":
                # Augmentation: AI fills skill gaps → novices gain more
                novice_output = novice_skill + agent_quality * (1 - novice_skill) * 0.7
                expert_output = expert_skill + agent_quality * (1 - expert_skill) * 0.7
            else:
                # Delegation: AI acts independently → quality determines outcome
                # Experts better at delegation (specify goals, verify output)
                novice_delegation = novice_skill * 0.5  # poor at specifying
                expert_delegation = expert_skill * 0.9  # good at specifying
                novice_output = agent_quality * novice_delegation + novice_skill * 0.3
                expert_output = agent_quality * expert_delegation + expert_skill * 0.3
            
            novice_gains.append(novice_output - novice_skill)
            expert_gains.append(expert_output - expert_skill)
        
        avg_novice = sum(novice_gains) / len(novice_gains)
        avg_expert = sum(expert_gains) / len(expert_gains)
        
        results[mode] = {
            "novice_avg_gain": round(avg_novice, 3),
            "expert_avg_gain": round(avg_expert, 3),
            "levelling_effect": avg_novice > avg_expert,
            "gap_change": round(avg_novice - avg_expert, 3),
        }
    
    return results

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("AGENTIC INEQUALITY SIMULATOR")
    print("Based on Sharp et al (Oxford, 2025)")
    print("=" * 60)
    
    # 1. Policy comparison
    print("\n--- Policy Comparison (50 participants, 20 rounds) ---")
    policies = ["none", "floor", "cap", "tax", "open"]
    
    for policy in policies:
        result = simulate_market(policy=policy)
        print(f"\n{policy.upper()}:")
        print(f"  Final Gini: {result['final_gini']:.3f}")
        print(f"  Top 10% share: {result['final_top10_share']:.1%}")
        print(f"  Bottom 50% share: {result['final_bottom50_share']:.1%}")
        print(f"  Concentration ratio: {result['concentration_ratio']:.1f}x")
        print(f"  Gini trajectory: {result['gini_trajectory']}")
    
    # 2. Levelling effect test
    print("\n--- Levelling-Up Effect: Assistive vs Autonomous ---")
    levelling = levelling_effect_test()
    
    for mode, data in levelling.items():
        print(f"\n{mode.upper()}:")
        print(f"  Novice gain: +{data['novice_avg_gain']:.3f}")
        print(f"  Expert gain: +{data['expert_avg_gain']:.3f}")
        print(f"  Levelling effect: {'YES ✓' if data['levelling_effect'] else 'NO ✗'}")
        print(f"  Gap change: {data['gap_change']:+.3f} ({'narrows' if data['gap_change'] > 0 else 'WIDENS'})")
    
    print("\n" + "=" * 60)
    print("KEY FINDING: Assistive AI levels up novices (+gap narrowing).")
    print("Autonomous AI reverses this — experts delegate better.")
    print("The levelling-up effect does NOT survive the transition.")
    print("=" * 60)
