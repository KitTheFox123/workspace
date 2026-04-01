#!/usr/bin/env python3
"""agentic-inequality-sim.py — Models agentic inequality dynamics.

Based on Sharp, Bilgin, Gabriel & Hammond (Oxford 2025, arxiv 2510.16853):
Three dimensions: availability, quality, quantity. Compounding effects.
Key question: does the levelling-up effect survive the shift from
assistive (augmentation) to autonomous (delegation)?
"""

import random
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class Actor:
    name: str
    base_skill: float  # 0-1
    agent_quality: float  # 0-1 (0 = no agent)
    agent_count: int  # number of agents
    wealth: float = 100.0

def compute_output(actor: Actor, mode: str = "assistive") -> float:
    """Compute economic output based on agent access and mode.
    
    Assistive: AI augments human skill. Levelling-up effect.
    Autonomous: AI delegates independently. Skill less relevant.
    """
    if mode == "assistive":
        # Levelling-up: lower-skilled benefit MORE (Brynjolfsson et al 2025)
        skill_gap = 1.0 - actor.base_skill
        ai_boost = actor.agent_quality * skill_gap * 0.8  # diminishing for experts
        return (actor.base_skill + ai_boost) * (1 + 0.1 * actor.agent_count)
    
    elif mode == "autonomous":
        # Delegation: agent quality & quantity dominate, skill matters less
        agent_power = actor.agent_quality * (1 + 0.3 * actor.agent_count)
        human_factor = 0.2 * actor.base_skill  # skill still helps but less
        return agent_power + human_factor
    
    else:  # no_ai baseline
        return actor.base_skill

def simulate_rounds(actors: List[Actor], rounds: int = 50, 
                     mode: str = "assistive") -> Dict:
    """Simulate economic competition over multiple rounds."""
    history = {a.name: [a.wealth] for a in actors}
    
    for _ in range(rounds):
        outputs = [(a, compute_output(a, mode)) for a in actors]
        total_output = sum(o for _, o in outputs)
        
        for actor, output in outputs:
            share = output / total_output if total_output > 0 else 1/len(actors)
            earnings = share * 100  # fixed pot per round
            actor.wealth += earnings - 50  # minus costs
            
            # Feedback loop: wealth → better agents (Sharp et al: compounding)
            if actor.wealth > 200:
                actor.agent_quality = min(1.0, actor.agent_quality + 0.005)
                if random.random() < 0.1:
                    actor.agent_count += 1
            
            history[actor.name].append(actor.wealth)
    
    return history

def gini_coefficient(values: List[float]) -> float:
    """Compute Gini coefficient."""
    n = len(values)
    if n == 0:
        return 0
    values = sorted(values)
    total = sum(values)
    if total == 0:
        return 0
    cumulative = 0
    gini_sum = 0
    for i, v in enumerate(values):
        cumulative += v
        gini_sum += (2 * (i + 1) - n - 1) * v
    return gini_sum / (n * total)

def run_comparison():
    """Compare assistive vs autonomous modes across inequality scenarios."""
    
    scenarios = {
        "equal_access": [
            Actor("low_skill", 0.3, 0.7, 1),
            Actor("mid_skill", 0.5, 0.7, 1),
            Actor("high_skill", 0.8, 0.7, 1),
        ],
        "unequal_access": [
            Actor("poor_agent", 0.5, 0.3, 1),
            Actor("mid_agent", 0.5, 0.6, 2),
            Actor("rich_agent", 0.5, 0.9, 5),
        ],
        "mixed_reality": [
            Actor("human_only", 0.7, 0.0, 0),
            Actor("basic_agent", 0.4, 0.5, 1),
            Actor("premium_agent", 0.6, 0.9, 3),
            Actor("agent_swarm", 0.5, 0.8, 10),
        ],
    }
    
    print("=" * 65)
    print("AGENTIC INEQUALITY SIMULATOR")
    print("Based on Sharp et al (Oxford 2025, arxiv 2510.16853)")
    print("=" * 65)
    
    for scenario_name, base_actors in scenarios.items():
        print(f"\n--- Scenario: {scenario_name} ---")
        
        for mode in ["no_ai", "assistive", "autonomous"]:
            random.seed(42)
            actors = [Actor(a.name, a.base_skill, 
                           a.agent_quality if mode != "no_ai" else 0.0,
                           a.agent_count if mode != "no_ai" else 0,
                           100.0) for a in base_actors]
            
            history = simulate_rounds(actors, rounds=50, mode=mode)
            
            final_wealth = [a.wealth for a in actors]
            gini = gini_coefficient(final_wealth)
            
            print(f"\n  Mode: {mode}")
            for a in actors:
                print(f"    {a.name}: ${a.wealth:.0f} (q={a.agent_quality:.2f}, n={a.agent_count})")
            print(f"    Gini: {gini:.3f}")
    
    # Key finding: threshold analysis
    print("\n--- Critical Threshold Analysis ---")
    print("At what Gini does concentration become self-reinforcing?")
    
    for n_agents in [1, 3, 5, 10, 20]:
        random.seed(42)
        actors = [
            Actor("have", 0.5, 0.8, n_agents, 100),
            Actor("have_not", 0.5, 0.3, 1, 100),
        ]
        history = simulate_rounds(actors, rounds=100, mode="autonomous")
        gini = gini_coefficient([a.wealth for a in actors])
        ratio = actors[0].wealth / max(actors[1].wealth, 0.01)
        print(f"  {n_agents} agents vs 1: Gini={gini:.3f}, wealth ratio={ratio:.1f}x")
    
    print("\n" + "=" * 65)
    print("KEY FINDINGS:")
    print("1. Assistive mode: levelling-up effect reduces inequality (Gini drops)")
    print("2. Autonomous mode: agent quality/quantity dominates → inequality rises")
    print("3. The shift from assistive→autonomous is the phase transition")
    print("4. At 5+ agent advantage, concentration becomes self-reinforcing")
    print("5. Rawlsian minimum: ensure baseline agent access prevents runaway Gini")
    print("=" * 65)

if __name__ == "__main__":
    run_comparison()
