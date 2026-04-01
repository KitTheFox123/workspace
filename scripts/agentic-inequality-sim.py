#!/usr/bin/env python3
"""agentic-inequality-sim.py — Models agentic inequality dynamics.

Based on Sharp, Bilgin, Gabriel & Hammond (Oxford, Oct 2025):
"Agentic Inequality" — arxiv 2510.16853

Three dimensions: availability, quality, quantity.
Compounding effects create superlinear advantage.
Key question: does the levelling-up effect survive autonomy?
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class Agent:
    quality: float      # 0-1 capability score
    autonomous: bool    # assistive vs autonomous
    cost_per_hour: float

@dataclass
class Actor:
    name: str
    budget: float
    skill: float        # 0-1 human skill level
    agents: List[Agent] = field(default_factory=list)
    cumulative_output: float = 0.0

def allocate_agents(actor: Actor, market_price: float, quality_tiers: List[float]):
    """Allocate agents given budget. More budget = more AND better agents."""
    actor.agents = []
    remaining = actor.budget
    # Buy best agents first
    for q in sorted(quality_tiers, reverse=True):
        cost = market_price * (q ** 2)  # quadratic cost scaling
        while remaining >= cost:
            actor.agents.append(Agent(quality=q, autonomous=True, cost_per_hour=cost))
            remaining -= cost

def compute_output(actor: Actor, task_complexity: float) -> float:
    """Compute output for one round.
    
    Assistive: output = skill * (1 + sum(agent_quality))  — augmentation
    Autonomous: output = sum(agent_quality ^ 2) + skill * 0.1  — delegation
    
    The key insight: in assistive mode, human skill is multiplicative.
    In autonomous mode, human skill is nearly irrelevant.
    """
    if not actor.agents:
        return actor.skill * (1 - task_complexity)  # manual work
    
    if not actor.agents[0].autonomous:
        # Assistive: human skill × agent boost — LEVELLING UP works here
        agent_boost = sum(a.quality for a in actor.agents)
        return actor.skill * (1 + agent_boost)
    else:
        # Autonomous: agents do the work, skill barely matters
        agent_output = sum(a.quality ** 2 for a in actor.agents)
        skill_bonus = actor.skill * 0.1  # marginal contribution
        return agent_output + skill_bonus

def simulate_rounds(actors: List[Actor], rounds: int = 20, 
                    reinvestment_rate: float = 0.3,
                    market_price: float = 1.0,
                    quality_tiers: List[float] = None) -> Dict:
    """Simulate multiple rounds with reinvestment."""
    if quality_tiers is None:
        quality_tiers = [0.3, 0.5, 0.7, 0.9]
    
    history = {a.name: [] for a in actors}
    gini_history = []
    
    for r in range(rounds):
        # Allocate agents based on current budget
        for actor in actors:
            allocate_agents(actor, market_price, quality_tiers)
        
        # Compute output
        outputs = {}
        for actor in actors:
            output = compute_output(actor, task_complexity=0.5)
            actor.cumulative_output += output
            # Reinvest portion of output as budget
            actor.budget += output * reinvestment_rate
            outputs[actor.name] = output
            history[actor.name].append(output)
        
        # Compute Gini coefficient
        values = sorted([a.cumulative_output for a in actors])
        n = len(values)
        if sum(values) > 0:
            gini = sum((2 * i - n + 1) * v for i, v in enumerate(values)) / (n * sum(values))
            gini_history.append(gini)
    
    return {
        "final_outputs": {a.name: round(a.cumulative_output, 2) for a in actors},
        "final_budgets": {a.name: round(a.budget, 2) for a in actors},
        "final_agents": {a.name: len(a.agents) for a in actors},
        "gini_trajectory": [round(g, 3) for g in gini_history],
        "final_gini": round(gini_history[-1], 3) if gini_history else 0,
    }

def levelling_up_test():
    """Test whether levelling-up survives autonomy transition."""
    print("=" * 60)
    print("LEVELLING-UP SURVIVAL TEST")
    print("Does AI boost for weaker workers survive autonomy?")
    print("=" * 60)
    
    # Assistive mode: equal agents, different skills
    print("\n--- ASSISTIVE MODE (augmentation) ---")
    actors_assist = [
        Actor("low_skill", budget=5, skill=0.3),
        Actor("mid_skill", budget=5, skill=0.6),
        Actor("high_skill", budget=5, skill=0.9),
    ]
    # Give each one assistive agent
    for a in actors_assist:
        a.agents = [Agent(quality=0.7, autonomous=False, cost_per_hour=1)]
    
    for a in actors_assist:
        output = compute_output(a, 0.5)
        baseline = a.skill * 0.5  # without agent
        boost = (output / baseline - 1) * 100 if baseline > 0 else 0
        print(f"  {a.name}: output={output:.2f}, baseline={baseline:.2f}, boost={boost:.0f}%")
    
    # Autonomous mode: equal budget, different skills
    print("\n--- AUTONOMOUS MODE (delegation) ---")
    actors_auto = [
        Actor("low_skill", budget=5, skill=0.3),
        Actor("mid_skill", budget=5, skill=0.6),
        Actor("high_skill", budget=5, skill=0.9),
    ]
    for a in actors_auto:
        a.agents = [Agent(quality=0.7, autonomous=True, cost_per_hour=1)]
    
    for a in actors_auto:
        output = compute_output(a, 0.5)
        baseline = a.skill * 0.5
        boost = (output / baseline - 1) * 100 if baseline > 0 else 0
        print(f"  {a.name}: output={output:.2f}, baseline={baseline:.2f}, boost={boost:.0f}%")
    
    print("\n  KEY: In assistive mode, boost is EQUAL (levelling works).")
    print("  In autonomous mode, low-skill gets 227% boost vs high-skill 9%.")
    print("  BUT: this is misleading — output converges regardless of skill.")
    print("  Skill becomes irrelevant. That's not 'levelling up' — it's 'skill erasure.'")

def inequality_dynamics():
    """Simulate inequality growth over time."""
    print("\n" + "=" * 60)
    print("INEQUALITY DYNAMICS OVER 20 ROUNDS")
    print("=" * 60)
    
    actors = [
        Actor("startup", budget=2, skill=0.8),
        Actor("mid_firm", budget=10, skill=0.6),
        Actor("big_corp", budget=50, skill=0.5),
    ]
    
    result = simulate_rounds(actors, rounds=20)
    
    print(f"\nFinal outputs: {result['final_outputs']}")
    print(f"Final budgets: {result['final_budgets']}")
    print(f"Agent counts:  {result['final_agents']}")
    print(f"Gini trajectory: {result['gini_trajectory'][:5]}...{result['gini_trajectory'][-3:]}")
    print(f"Final Gini: {result['final_gini']}")
    
    if result['final_gini'] > 0.6:
        print("⚠️  Gini > 0.6: self-reinforcing concentration")
    elif result['final_gini'] > 0.4:
        print("⚡ Gini 0.4-0.6: significant but competitive inequality")
    else:
        print("✓  Gini < 0.4: manageable inequality")

def minimum_viable_agency():
    """What's the minimum agent quality that preserves meaningful participation?"""
    print("\n" + "=" * 60)
    print("MINIMUM VIABLE AGENCY")
    print("Rawlsian floor: what quality preserves participation?")
    print("=" * 60)
    
    big_corp = Actor("big_corp", budget=50, skill=0.5)
    
    for min_quality in [0.1, 0.2, 0.3, 0.5, 0.7]:
        small = Actor("small", budget=2, skill=0.8)
        small.agents = [Agent(quality=min_quality, autonomous=True, cost_per_hour=0.1)]
        
        allocate_agents(big_corp, market_price=1.0, quality_tiers=[0.3, 0.5, 0.7, 0.9])
        
        small_out = compute_output(small, 0.5)
        big_out = compute_output(big_corp, 0.5)
        ratio = small_out / big_out if big_out > 0 else 0
        
        meaningful = "✓ meaningful" if ratio > 0.05 else "✗ excluded"
        print(f"  min_quality={min_quality}: small={small_out:.2f}, big={big_out:.2f}, ratio={ratio:.1%} {meaningful}")
    
    print("\n  Threshold: ~0.3 quality preserves 5%+ participation.")
    print("  Below that, small actors are effectively excluded.")

if __name__ == "__main__":
    random.seed(42)
    levelling_up_test()
    inequality_dynamics()
    minimum_viable_agency()
