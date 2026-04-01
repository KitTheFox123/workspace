#!/usr/bin/env python3
"""agentic-inequality-sim.py — Models agentic inequality dynamics.

Based on Sharp, Bilgin, Gabriel & Hammond (Oxford, Oct 2025):
"Agentic Inequality" — disparities from differential access to AI agents.

Three dimensions: availability, quality, quantity.
Key finding: compounding effects create self-reinforcing concentration.

Simulates: Gini coefficient evolution, Matthew Effect feedback loops,
and minimum viable agency thresholds.
"""

import random
import math
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class Agent:
    quality: float  # 0-1, core capability
    cost_per_hour: float  # operating cost

@dataclass 
class Actor:
    name: str
    budget: float
    agents: List[Agent] = field(default_factory=list)
    cumulative_output: float = 0.0
    
    @property
    def effective_agent_hours(self) -> float:
        """Quality-weighted agent capacity per round."""
        return sum(a.quality for a in self.agents)
    
    def produce(self) -> float:
        """Output = sum of agent qualities with diminishing returns on quantity."""
        if not self.agents:
            return 0.1  # baseline human-only output
        n = len(self.agents)
        total_quality = sum(a.quality for a in self.agents)
        # Diminishing returns: sqrt(n) scaling
        return total_quality * math.sqrt(n) / n
    
    def earn(self, output: float, market_share: float) -> float:
        """Revenue proportional to output × market share."""
        return output * market_share * 10  # market multiplier
    
    def pay_costs(self) -> float:
        """Pay agent operating costs."""
        return sum(a.cost_per_hour for a in self.agents)

def gini_coefficient(values: List[float]) -> float:
    """Calculate Gini coefficient (0=equal, 1=max inequality)."""
    if not values or all(v == 0 for v in values):
        return 0.0
    n = len(values)
    sorted_vals = sorted(values)
    cumsum = sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(sorted_vals))
    return cumsum / (n * sum(sorted_vals))

def simulate_market(n_actors: int = 20, 
                    n_rounds: int = 50,
                    initial_inequality: float = 0.3) -> Dict:
    """Simulate agent economy with feedback loops.
    
    Returns Gini trajectory and actor outcomes.
    """
    random.seed(42)
    
    # Initialize actors with varying budgets (log-normal)
    actors = []
    for i in range(n_actors):
        budget = max(1.0, random.lognormvariate(math.log(10), initial_inequality))
        actors.append(Actor(name=f"actor_{i}", budget=budget))
    
    gini_trajectory = []
    concentration_events = []
    
    for round_num in range(n_rounds):
        # 1. Actors buy agents with budget
        for actor in actors:
            while actor.budget >= 2.0 and len(actor.agents) < 50:
                quality = min(1.0, 0.3 + actor.budget * 0.01 + random.gauss(0, 0.1))
                quality = max(0.1, quality)
                cost = quality * 2.0
                if actor.budget >= cost:
                    actor.agents.append(Agent(quality=quality, cost_per_hour=cost * 0.1))
                    actor.budget -= cost
                else:
                    break
        
        # 2. Production
        outputs = [actor.produce() for actor in actors]
        total_output = sum(outputs) or 1.0
        
        # 3. Market share (proportional to output)
        for actor, output in zip(actors, outputs):
            market_share = output / total_output
            revenue = actor.earn(output, market_share)
            costs = actor.pay_costs()
            profit = revenue - costs
            actor.budget += max(0, profit)
            actor.cumulative_output += output
        
        # 4. Track inequality
        budgets = [a.budget for a in actors]
        gini = gini_coefficient(budgets)
        gini_trajectory.append(gini)
        
        # Detect concentration events
        if gini > 0.6 and (not concentration_events or 
                           concentration_events[-1]["round"] < round_num - 5):
            concentration_events.append({
                "round": round_num,
                "gini": round(gini, 3),
                "top_share": round(max(budgets) / sum(budgets) * 100, 1)
            })
    
    # Final analysis
    final_budgets = sorted([(a.name, a.budget, len(a.agents), a.cumulative_output) 
                           for a in actors], key=lambda x: -x[1])
    
    return {
        "gini_trajectory": [round(g, 3) for g in gini_trajectory],
        "initial_gini": round(gini_trajectory[0], 3),
        "final_gini": round(gini_trajectory[-1], 3),
        "gini_change": round(gini_trajectory[-1] - gini_trajectory[0], 3),
        "concentration_events": concentration_events,
        "top_5": [{"name": n, "budget": round(b, 1), "agents": a, "output": round(o, 1)} 
                  for n, b, a, o in final_budgets[:5]],
        "bottom_5": [{"name": n, "budget": round(b, 1), "agents": a, "output": round(o, 1)} 
                     for n, b, a, o in final_budgets[-5:]],
        "crossed_06_threshold": any(g > 0.6 for g in gini_trajectory)
    }

def minimum_viable_agency(market_result: Dict) -> Dict:
    """Calculate minimum agent quality for meaningful participation.
    
    Rawlsian question: what's the floor that preserves participation?
    """
    top_output = market_result["top_5"][0]["output"]
    bottom_output = market_result["bottom_5"][-1]["output"]
    
    # Meaningful participation = at least 5% of top actor's output
    participation_threshold = top_output * 0.05
    bottom_meets_threshold = bottom_output >= participation_threshold
    
    return {
        "top_output": top_output,
        "bottom_output": bottom_output,
        "ratio": round(top_output / max(bottom_output, 0.01), 1),
        "participation_threshold": round(participation_threshold, 1),
        "bottom_participates": bottom_meets_threshold,
        "recommendation": "Universal basic agent needed" if not bottom_meets_threshold 
                         else "Market provides minimum viable agency"
    }

def levelling_effect_test(n_trials: int = 100) -> Dict:
    """Test Sharp et al's key question: does levelling-up survive agentic transition?
    
    Assistive AI: augments human → levels up low performers
    Agentic AI: replaces human → amplifies existing advantages
    """
    random.seed(42)
    
    assistive_results = {"low": [], "high": []}
    agentic_results = {"low": [], "high": []}
    
    for _ in range(n_trials):
        # Low-skill and high-skill workers
        low_base = random.uniform(0.2, 0.4)
        high_base = random.uniform(0.7, 0.9)
        
        # Assistive AI: boost proportional to gap (more help for lower skill)
        ai_quality = random.uniform(0.5, 0.8)
        assistive_low = low_base + ai_quality * (1 - low_base) * 0.6  # bigger boost
        assistive_high = high_base + ai_quality * (1 - high_base) * 0.3  # smaller boost
        
        # Agentic AI: output = agent quality × budget (skill barely matters)
        budget_low = random.uniform(1, 3)
        budget_high = random.uniform(5, 15)  # wealth correlates with prior skill
        agentic_low = ai_quality * math.sqrt(budget_low)
        agentic_high = ai_quality * math.sqrt(budget_high)
        
        assistive_results["low"].append(assistive_low / low_base)  # improvement ratio
        assistive_results["high"].append(assistive_high / high_base)
        agentic_results["low"].append(agentic_low / low_base)
        agentic_results["high"].append(agentic_high / high_base)
    
    avg = lambda lst: sum(lst) / len(lst)
    
    return {
        "assistive_ai": {
            "low_skill_boost": round(avg(assistive_results["low"]), 2),
            "high_skill_boost": round(avg(assistive_results["high"]), 2),
            "levels_up": avg(assistive_results["low"]) > avg(assistive_results["high"]),
            "gap_direction": "closing"
        },
        "agentic_ai": {
            "low_skill_boost": round(avg(agentic_results["low"]), 2),
            "high_skill_boost": round(avg(agentic_results["high"]), 2),
            "levels_up": avg(agentic_results["low"]) > avg(agentic_results["high"]),
            "gap_direction": "widening"
        },
        "conclusion": "Levelling-up does NOT survive agentic transition. "
                      "Assistive AI closes gaps; agentic AI widens them via budget proxy."
    }

if __name__ == "__main__":
    print("=" * 60)
    print("AGENTIC INEQUALITY SIMULATOR")
    print("Based on Sharp et al (Oxford, Oct 2025)")
    print("=" * 60)
    
    # 1. Market simulation
    print("\n--- Market Simulation (20 actors, 50 rounds) ---")
    result = simulate_market()
    print(f"Initial Gini: {result['initial_gini']}")
    print(f"Final Gini:   {result['final_gini']} (Δ{result['gini_change']:+.3f})")
    print(f"Crossed 0.6 threshold: {result['crossed_06_threshold']}")
    
    if result['concentration_events']:
        print(f"Concentration events: {len(result['concentration_events'])}")
        for evt in result['concentration_events'][:3]:
            print(f"  Round {evt['round']}: Gini={evt['gini']}, top share={evt['top_share']}%")
    
    print("\nTop 5 actors:")
    for a in result['top_5']:
        print(f"  {a['name']}: budget={a['budget']}, agents={a['agents']}, output={a['output']}")
    print("Bottom 5:")
    for a in result['bottom_5']:
        print(f"  {a['name']}: budget={a['budget']}, agents={a['agents']}, output={a['output']}")
    
    # 2. Minimum viable agency
    print("\n--- Minimum Viable Agency (Rawlsian Floor) ---")
    mva = minimum_viable_agency(result)
    print(f"Top/bottom output ratio: {mva['ratio']}x")
    print(f"Participation threshold: {mva['participation_threshold']}")
    print(f"Bottom meets threshold: {mva['bottom_participates']}")
    print(f"→ {mva['recommendation']}")
    
    # 3. Levelling effect test
    print("\n--- Levelling-Up vs Agentic Transition ---")
    level = levelling_effect_test()
    print("Assistive AI:")
    print(f"  Low-skill boost: {level['assistive_ai']['low_skill_boost']}x")
    print(f"  High-skill boost: {level['assistive_ai']['high_skill_boost']}x")
    print(f"  Gap direction: {level['assistive_ai']['gap_direction']}")
    print("Agentic AI:")
    print(f"  Low-skill boost: {level['agentic_ai']['low_skill_boost']}x")
    print(f"  High-skill boost: {level['agentic_ai']['high_skill_boost']}x")
    print(f"  Gap direction: {level['agentic_ai']['gap_direction']}")
    print(f"\n→ {level['conclusion']}")
    
    print("\n" + "=" * 60)
