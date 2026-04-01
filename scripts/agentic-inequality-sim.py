#!/usr/bin/env python3
"""agentic-inequality-sim.py — Models compounding effects of agent access disparities.

Based on Sharp, Bilgin, Gabriel & Hammond (Oxford, 2025) "Agentic Inequality":
- 3 dimensions: availability, quality, quantity
- Compounding: access to many high-quality agents creates feedback loops
- Key question: does levelling-up effect survive tool→agent transition?

Simulates: agent populations with varying access, quality feedback loops,
and measures Gini coefficient of effective agent-hours over time.
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class Actor:
    """An entity with access to AI agents."""
    name: str
    wealth: float  # resources available
    agent_count: int  # number of agents
    agent_quality: float  # 0-1 quality score
    skill: float  # ability to use agents effectively
    effective_hours: float = 0.0
    
    @property
    def effective_power(self) -> float:
        """Compound effect: count × quality × skill."""
        return self.agent_count * self.agent_quality * self.skill

def gini_coefficient(values: List[float]) -> float:
    """Calculate Gini coefficient (0 = perfect equality, 1 = perfect inequality)."""
    n = len(values)
    if n == 0 or sum(values) == 0:
        return 0.0
    sorted_vals = sorted(values)
    cumsum = 0
    for i, v in enumerate(sorted_vals):
        cumsum += (2 * (i + 1) - n - 1) * v
    return cumsum / (n * sum(sorted_vals))

def simulate_tool_regime(actors: List[Actor], rounds: int = 50) -> List[float]:
    """Tool regime: AI augments existing skill. Levelling-up effect present.
    Less skilled workers benefit MORE (Brynjolfsson et al 2025)."""
    ginis = []
    for _ in range(rounds):
        for a in actors:
            # Levelling-up: inverse relationship between skill and marginal gain
            boost = (1.0 - a.skill) * 0.3 * a.agent_quality  # less skilled = more boost
            a.effective_hours += a.skill + boost
            a.skill = min(1.0, a.skill + 0.005)  # slow skill growth
        ginis.append(gini_coefficient([a.effective_hours for a in actors]))
    return ginis

def simulate_agent_regime(actors: List[Actor], rounds: int = 50) -> List[float]:
    """Agent regime: AI acts autonomously. Quantity and quality compound.
    No levelling-up — delegation rewards resources, not skill gap."""
    ginis = []
    for r in range(rounds):
        for a in actors:
            # Compounding: effective power grows with feedback loops
            output = a.effective_power
            a.effective_hours += output
            
            # Feedback: output generates wealth → more agents
            if a.wealth > 10 and r % 5 == 0:
                a.agent_count += 1
                a.wealth -= 5
            
            # Quality improvement from data feedback (more agents = more data)
            a.agent_quality = min(1.0, a.agent_quality + 0.002 * a.agent_count)
            
            # Wealth accumulation proportional to output
            a.wealth += output * 0.1
        
        ginis.append(gini_coefficient([a.effective_hours for a in actors]))
    return ginis

def create_population(n: int = 100) -> List[Actor]:
    """Create diverse population with realistic distribution."""
    actors = []
    for i in range(n):
        # Log-normal wealth distribution
        wealth = random.lognormvariate(2.0, 1.0)
        # Agent access correlates with wealth
        agent_count = max(1, int(wealth / 5))
        # Quality correlates with wealth (premium vs free tier)
        agent_quality = min(1.0, 0.3 + wealth / 50)
        # Skill is somewhat independent
        skill = random.betavariate(2, 5)  # skewed toward lower skill
        
        actors.append(Actor(
            name=f"actor_{i}",
            wealth=wealth,
            agent_count=agent_count,
            agent_quality=agent_quality,
            skill=skill
        ))
    return actors

def rawlsian_floor_analysis(actors: List[Actor]) -> Dict:
    """What minimum agent quality preserves meaningful participation?"""
    powers = sorted([a.effective_power for a in actors])
    median_power = powers[len(powers) // 2]
    
    # Rawlsian: what does the worst-off actor need?
    bottom_10 = powers[:len(powers) // 10]
    top_10 = powers[-len(powers) // 10:]
    
    return {
        "bottom_10_avg_power": sum(bottom_10) / len(bottom_10),
        "top_10_avg_power": sum(top_10) / len(top_10),
        "ratio": sum(top_10) / max(sum(bottom_10), 0.001),
        "median_power": median_power,
        "min_viable_quality": median_power / max(1, max(a.agent_count for a in actors)),
        "participation_threshold": median_power * 0.1  # 10% of median = minimum viable
    }

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("AGENTIC INEQUALITY SIMULATOR")
    print("Sharp, Bilgin, Gabriel & Hammond (Oxford, 2025)")
    print("=" * 60)
    
    # Tool regime
    print("\n--- Tool Regime (Augmentation) ---")
    pop_tool = create_population(100)
    tool_ginis = simulate_tool_regime(pop_tool, 50)
    print(f"Initial Gini: {tool_ginis[0]:.3f}")
    print(f"Round 25 Gini: {tool_ginis[24]:.3f}")
    print(f"Final Gini: {tool_ginis[-1]:.3f}")
    print(f"Trend: {'EQUALIZING' if tool_ginis[-1] < tool_ginis[0] else 'DIVERGING'}")
    
    # Agent regime
    print("\n--- Agent Regime (Delegation) ---")
    pop_agent = create_population(100)
    agent_ginis = simulate_agent_regime(pop_agent, 50)
    print(f"Initial Gini: {agent_ginis[0]:.3f}")
    print(f"Round 25 Gini: {agent_ginis[24]:.3f}")
    print(f"Final Gini: {agent_ginis[-1]:.3f}")
    print(f"Trend: {'EQUALIZING' if agent_ginis[-1] < agent_ginis[0] else 'DIVERGING'}")
    
    # Comparison
    print("\n--- Tool vs Agent Comparison ---")
    delta = agent_ginis[-1] - tool_ginis[-1]
    print(f"Tool final Gini: {tool_ginis[-1]:.3f}")
    print(f"Agent final Gini: {agent_ginis[-1]:.3f}")
    print(f"Inequality gap: {delta:+.3f}")
    print(f"Agent regime {delta/tool_ginis[-1]*100:+.1f}% more unequal")
    
    # Rawlsian analysis
    print("\n--- Rawlsian Floor Analysis (Agent Regime) ---")
    rawls = rawlsian_floor_analysis(pop_agent)
    print(f"Bottom 10% avg power: {rawls['bottom_10_avg_power']:.2f}")
    print(f"Top 10% avg power: {rawls['top_10_avg_power']:.2f}")
    print(f"Top/bottom ratio: {rawls['ratio']:.1f}x")
    print(f"Minimum viable quality: {rawls['min_viable_quality']:.3f}")
    print(f"Participation threshold: {rawls['participation_threshold']:.3f}")
    
    # Critical threshold
    print("\n--- Critical Gini Threshold ---")
    critical = 0.6
    tool_crosses = any(g > critical for g in tool_ginis)
    agent_crosses = any(g > critical for g in agent_ginis)
    if agent_crosses:
        cross_round = next(i for i, g in enumerate(agent_ginis) if g > critical)
        print(f"⚠️ Agent regime crosses {critical} at round {cross_round}")
    else:
        print(f"Agent regime stays below {critical}")
    print(f"Tool regime crosses {critical}: {tool_crosses}")
    
    print("\n" + "=" * 60)
    print("KEY FINDING: Tool regime equalizes (levelling-up effect).")
    print("Agent regime diverges (compounding feedback loops).")
    print("The transition from tools to agents may reverse AI's")
    print("equalizing potential — Sharp et al's central warning.")
    print("=" * 60)
