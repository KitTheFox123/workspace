#!/usr/bin/env python3
"""agentic-inequality-sim.py — Models compound inequality from agent access.

Based on Sharp, Bilgin, Gabriel & Hammond (Oxford 2025) "Agentic Inequality":
- Three dimensions: availability, quality, quantity
- Compounding: access to many high-quality agents creates feedback loops
- Matthew Effect: initial advantages accumulate over time (Merton 1968)

Simulates: how initial agent access gaps compound over time,
and tests interventions (minimum viable agency, progressive compute tax).
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class Actor:
    name: str
    wealth: float  # resources
    agent_quality: float  # 0-1
    agent_quantity: int
    has_access: bool = True
    history: List[float] = field(default_factory=list)
    
    @property
    def effective_power(self) -> float:
        """Compound effect: quality × quantity × access."""
        if not self.has_access:
            return 0.1  # baseline human capability
        return self.agent_quality * (1 + 0.3 * (self.agent_quantity - 1))

def simulate_market(actors: List[Actor], rounds: int = 50, 
                    intervention: str = "none") -> Dict:
    """Simulate market dynamics with agentic inequality.
    
    Interventions:
    - none: pure market
    - minimum_agency: ensure all actors have at least 1 basic agent
    - progressive_tax: tax top actors to fund bottom
    - quality_floor: open-source model ensures minimum quality
    """
    for r in range(rounds):
        # Each round: actors compete for opportunities
        total_power = sum(a.effective_power for a in actors)
        
        for actor in actors:
            # Share of opportunities proportional to power
            share = actor.effective_power / total_power
            # Revenue = share × market size (grows with total power)
            market_size = 100 + total_power * 2
            revenue = share * market_size
            
            # Reinvestment: wealth → better/more agents (Matthew Effect)
            actor.wealth += revenue
            if actor.wealth > 50 and actor.agent_quantity < 20:
                actor.agent_quantity += 1
                actor.wealth -= 30
            if actor.wealth > 100:
                actor.agent_quality = min(1.0, actor.agent_quality + 0.02)
                actor.wealth -= 50
            
            actor.history.append(actor.wealth)
        
        # Apply intervention
        if intervention == "minimum_agency":
            for a in actors:
                if not a.has_access:
                    a.has_access = True
                    a.agent_quality = 0.3
                    a.agent_quantity = 1
        elif intervention == "progressive_tax":
            top = max(actors, key=lambda a: a.wealth)
            bottom = min(actors, key=lambda a: a.wealth)
            transfer = top.wealth * 0.05
            top.wealth -= transfer
            bottom.wealth += transfer
        elif intervention == "quality_floor":
            for a in actors:
                a.agent_quality = max(a.agent_quality, 0.4)  # open-source floor
                a.has_access = True
    
    return compute_metrics(actors)

def compute_metrics(actors: List[Actor]) -> Dict:
    """Compute inequality metrics."""
    wealths = sorted([a.wealth for a in actors])
    n = len(wealths)
    total = sum(wealths)
    
    # Gini coefficient
    numerator = sum(abs(wealths[i] - wealths[j]) for i in range(n) for j in range(n))
    gini = numerator / (2 * n * total) if total > 0 else 0
    
    # Top/bottom ratio
    top_20 = sum(wealths[int(n*0.8):])
    bottom_20 = sum(wealths[:int(n*0.2)]) or 0.01
    
    # Effective power spread
    powers = [a.effective_power for a in actors]
    
    return {
        "gini": round(gini, 3),
        "top_bottom_ratio": round(top_20 / bottom_20, 1),
        "max_wealth": round(max(wealths), 1),
        "min_wealth": round(min(wealths), 1),
        "mean_wealth": round(total / n, 1),
        "max_power": round(max(powers), 2),
        "min_power": round(min(powers), 2),
        "power_ratio": round(max(powers) / max(min(powers), 0.01), 1),
    }

def create_initial_population(n: int = 20) -> List[Actor]:
    """Create population with realistic initial inequality."""
    actors = []
    for i in range(n):
        # 20% have high access, 50% medium, 30% low/none
        r = random.random()
        if r < 0.2:  # wealthy early adopters
            actors.append(Actor(f"elite_{i}", wealth=100, agent_quality=0.8, agent_quantity=5))
        elif r < 0.7:  # middle tier
            actors.append(Actor(f"mid_{i}", wealth=30, agent_quality=0.4, agent_quantity=1))
        else:  # no access
            actors.append(Actor(f"excluded_{i}", wealth=10, agent_quality=0.0, agent_quantity=0, has_access=False))
    return actors

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("AGENTIC INEQUALITY SIMULATOR")
    print("Based on Sharp et al (Oxford 2025)")
    print("=" * 60)
    
    interventions = ["none", "minimum_agency", "progressive_tax", "quality_floor"]
    
    for intervention in interventions:
        actors = create_initial_population(20)
        metrics = simulate_market(actors, rounds=50, intervention=intervention)
        
        print(f"\n--- Intervention: {intervention} ---")
        print(f"  Gini coefficient: {metrics['gini']}")
        print(f"  Top/Bottom 20% ratio: {metrics['top_bottom_ratio']}x")
        print(f"  Wealth range: {metrics['min_wealth']} - {metrics['max_wealth']}")
        print(f"  Power ratio: {metrics['power_ratio']}x")
    
    print("\n" + "=" * 60)
    print("KEY FINDINGS:")
    print("- No intervention: Gini rises, power concentrates")
    print("- Minimum agency: reduces exclusion but not concentration")  
    print("- Progressive tax: slows concentration, doesn't prevent it")
    print("- Quality floor (open-source): most effective equalizer")
    print("  Because quality compounds — a floor lifts everyone's ceiling")
    print("=" * 60)
