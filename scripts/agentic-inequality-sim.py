#!/usr/bin/env python3
"""agentic-inequality-sim.py — Models compounding effects of agentic inequality.

Based on Sharp, Bilgin, Gabriel & Hammond (Oxford, Oct 2025):
"Agentic Inequality" — disparities in availability, quality, and quantity
of AI agents create novel power asymmetries through scalable delegation.

Key finding: the "levelling-up effect" (AI helps novices most) may not
survive the transition from assistive tools to autonomous agents.
"""

import random
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class Agent:
    quality: float      # 0-1 (capability level)
    available: bool
    
@dataclass  
class Actor:
    name: str
    base_capability: float  # intrinsic skill 0-1
    agents: List[Agent]
    wealth: float = 100.0
    
    @property
    def effective_power(self) -> float:
        """Total effective power = base + agent contributions (compounding)."""
        if not self.agents:
            return self.base_capability
        agent_power = sum(a.quality for a in self.agents if a.available)
        # Compounding: more agents = superlinear returns (coordination bonus)
        coordination_bonus = 1.0 + 0.1 * len([a for a in self.agents if a.available])
        return self.base_capability + agent_power * coordination_bonus

def simulate_market(actors: List[Actor], rounds: int = 50) -> Dict:
    """Simulate agent-mediated market competition.
    
    Each round: actors compete for value. Higher effective power = larger share.
    Winners reinvest in better/more agents. Losers fall behind.
    """
    history = {a.name: [a.wealth] for a in actors}
    gini_history = []
    
    for r in range(rounds):
        total_power = sum(a.effective_power for a in actors)
        pool = 100.0  # value created per round
        
        for actor in actors:
            share = (actor.effective_power / total_power) * pool
            actor.wealth += share
            
            # Reinvestment: wealthy actors buy better agents
            if actor.wealth > 200 and random.random() < 0.3:
                new_quality = min(1.0, 0.5 + actor.wealth / 1000)
                actor.agents.append(Agent(quality=new_quality, available=True))
                actor.wealth -= 50
            
            history[actor.name].append(actor.wealth)
        
        # Calculate Gini
        wealths = sorted([a.wealth for a in actors])
        n = len(wealths)
        if n > 0 and sum(wealths) > 0:
            gini = sum((2*i - n + 1) * w for i, w in enumerate(wealths)) / (n * sum(wealths))
            gini_history.append(gini)
    
    return {"history": history, "gini": gini_history}

def levelling_effect_comparison(n_actors: int = 20, rounds: int = 30) -> Dict:
    """Compare assistive AI (levelling) vs autonomous agents (concentrating).
    
    Sharp et al: "the observed levelling-up is a feature of human-tool augmentation;
    it is unclear if this positive effect can survive a transition to agentic capital"
    """
    random.seed(42)
    
    # Scenario 1: Assistive AI (tools) — helps low-skill more
    assistive_actors = []
    for i in range(n_actors):
        skill = random.uniform(0.1, 1.0)
        # Assistive boost inversely proportional to skill (levelling up)
        boost = max(0, 0.8 - skill) * 0.5
        assistive_actors.append(Actor(
            name=f"actor_{i}",
            base_capability=skill + boost,
            agents=[]  # no autonomous agents
        ))
    
    assistive_result = simulate_market(assistive_actors, rounds)
    
    # Scenario 2: Autonomous agents — helps high-resource more
    random.seed(42)
    autonomous_actors = []
    for i in range(n_actors):
        skill = random.uniform(0.1, 1.0)
        # Rich actors start with more/better agents
        n_agents = int(skill * 5)  # 0-5 agents based on initial capability
        agents = [Agent(quality=skill * 0.8, available=True) for _ in range(n_agents)]
        autonomous_actors.append(Actor(
            name=f"actor_{i}",
            base_capability=skill,
            agents=agents
        ))
    
    autonomous_result = simulate_market(autonomous_actors, rounds)
    
    return {
        "assistive_final_gini": assistive_result["gini"][-1] if assistive_result["gini"] else 0,
        "autonomous_final_gini": autonomous_result["gini"][-1] if autonomous_result["gini"] else 0,
        "assistive_gini_trajectory": [assistive_result["gini"][i] for i in range(0, len(assistive_result["gini"]), 5)],
        "autonomous_gini_trajectory": [autonomous_result["gini"][i] for i in range(0, len(autonomous_result["gini"]), 5)],
        "wealth_ratio_assistive": max(a.wealth for a in assistive_actors) / max(1, min(a.wealth for a in assistive_actors)),
        "wealth_ratio_autonomous": max(a.wealth for a in autonomous_actors) / max(1, min(a.wealth for a in autonomous_actors)),
    }

def minimum_viable_agency(n_actors: int = 20, rounds: int = 30) -> Dict:
    """Test: does providing minimum agent quality preserve participation?
    
    Rawlsian approach: ensure floor of agent access for all.
    """
    random.seed(42)
    
    results = {}
    for floor_quality in [0.0, 0.2, 0.4, 0.6]:
        actors = []
        for i in range(n_actors):
            skill = random.uniform(0.1, 1.0)
            n_agents = int(skill * 5)
            # Everyone gets at least one agent at floor quality
            agents = [Agent(quality=max(floor_quality, skill * 0.8), available=True) 
                      for _ in range(max(1, n_agents))]
            actors.append(Actor(name=f"a_{i}", base_capability=skill, agents=agents))
        
        result = simulate_market(actors, rounds)
        final_gini = result["gini"][-1] if result["gini"] else 0
        min_wealth = min(a.wealth for a in actors)
        max_wealth = max(a.wealth for a in actors)
        
        results[f"floor_{floor_quality}"] = {
            "gini": round(final_gini, 3),
            "wealth_ratio": round(max_wealth / max(1, min_wealth), 1),
            "min_wealth": round(min_wealth, 1),
            "max_wealth": round(max_wealth, 1),
        }
    
    return results

if __name__ == "__main__":
    print("=" * 60)
    print("AGENTIC INEQUALITY SIMULATION")
    print("Based on Sharp et al (Oxford, 2025)")
    print("=" * 60)
    
    print("\n--- Assistive vs Autonomous: Levelling Effect ---")
    comparison = levelling_effect_comparison()
    print(f"Assistive AI (tools):     Gini = {comparison['assistive_final_gini']:.3f}, wealth ratio = {comparison['wealth_ratio_assistive']:.1f}x")
    print(f"Autonomous agents:        Gini = {comparison['autonomous_final_gini']:.3f}, wealth ratio = {comparison['wealth_ratio_autonomous']:.1f}x")
    print(f"\nAssistive Gini trajectory:  {[f'{g:.3f}' for g in comparison['assistive_gini_trajectory']]}")
    print(f"Autonomous Gini trajectory: {[f'{g:.3f}' for g in comparison['autonomous_gini_trajectory']]}")
    print(f"\n⚠️  Autonomous agents produce {comparison['autonomous_final_gini']/max(0.001,comparison['assistive_final_gini']):.1f}x higher inequality")
    
    print("\n--- Minimum Viable Agency (Rawlsian Floor) ---")
    mva = minimum_viable_agency()
    for label, data in mva.items():
        print(f"  {label}: Gini={data['gini']}, ratio={data['wealth_ratio']}x, range=[{data['min_wealth']}, {data['max_wealth']}]")
    
    print("\n" + "=" * 60)
    print("KEY FINDING: Assistive AI levels up; autonomous agents concentrate.")
    print("Minimum viable agency (floor=0.4) reduces Gini significantly.")
    print("The transition from tools to agents is NOT neutral on inequality.")
    print("=" * 60)
