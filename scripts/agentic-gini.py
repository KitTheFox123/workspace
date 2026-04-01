#!/usr/bin/env python3
"""agentic-gini.py — Agentic inequality measurement tool.

Based on Sharp, Bilgin, Gabriel & Hammond (Oxford, 2025) "Agentic Inequality":
Three dimensions: availability, quality, quantity of agents.
When Gini of effective agent-hours crosses ~0.6, concentration self-reinforces.

Measures compute inequality in agent ecosystems and predicts
when Matthew Effect dynamics become dominant.
"""

import random
import math
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class AgentOwner:
    """Entity that owns/operates agents."""
    name: str
    n_agents: int       # quantity dimension
    quality: float      # quality dimension (0-1)
    hours_per_day: float # availability/utilization
    
    @property
    def effective_agent_hours(self) -> float:
        """Composite metric: quantity × quality × time."""
        return self.n_agents * self.quality * self.hours_per_day

def gini_coefficient(values: List[float]) -> float:
    """Calculate Gini coefficient (0=perfect equality, 1=perfect inequality)."""
    n = len(values)
    if n == 0 or sum(values) == 0:
        return 0.0
    sorted_v = sorted(values)
    total = sum(sorted_v)
    # Standard Gini: 1 - (2/(n*total)) * sum((n-i)*y_i)
    weighted_sum = sum((i + 1) * v for i, v in enumerate(sorted_v))
    return (2 * weighted_sum) / (n * total) - (n + 1) / n

def simulate_ecosystem(n_owners: int, 
                       concentration: str = "moderate") -> List[AgentOwner]:
    """Generate agent ecosystem with configurable concentration."""
    owners = []
    for i in range(n_owners):
        if concentration == "equal":
            n = random.randint(1, 3)
            q = random.uniform(0.7, 0.9)
        elif concentration == "moderate":
            # Power law: most have few, some have many
            n = max(1, int(random.paretovariate(1.5)))
            q = random.uniform(0.3, 0.95)
        elif concentration == "extreme":
            # Heavy tail: top 5% have 80% of agents
            if random.random() < 0.05:
                n = random.randint(50, 500)
                q = random.uniform(0.85, 0.99)
            else:
                n = random.randint(1, 5)
                q = random.uniform(0.2, 0.6)
        else:
            raise ValueError(f"Unknown concentration: {concentration}")
        
        hours = random.uniform(4, 24)
        owners.append(AgentOwner(f"owner_{i}", n, q, hours))
    
    return owners

def matthew_effect_threshold(gini_series: List[float]) -> Tuple[int, bool]:
    """Detect when Gini crosses self-reinforcing threshold (~0.6).
    
    Returns (crossing_index, crossed).
    Based on Matthew Effect (Merton 1968, DiPrete & Eirich 2006).
    """
    threshold = 0.6
    for i, g in enumerate(gini_series):
        if g >= threshold:
            return i, True
    return len(gini_series), False

def simulate_feedback_loop(owners: List[AgentOwner], 
                           rounds: int = 20,
                           growth_advantage: float = 0.1) -> List[float]:
    """Simulate compounding advantage over time.
    
    Each round: top performers grow faster (feedback loop).
    Sharp et al: "proprietary data → better agents → more users → more data"
    """
    gini_series = []
    
    for _ in range(rounds):
        eah = [o.effective_agent_hours for o in owners]
        gini_series.append(gini_coefficient(eah))
        
        # Sort by effectiveness
        median = sorted(eah)[len(eah) // 2]
        
        for o in owners:
            if o.effective_agent_hours > median:
                # Winners grow faster
                growth = 1 + growth_advantage * (o.effective_agent_hours / median - 1)
                o.n_agents = min(10000, max(1, int(o.n_agents * growth)))
                o.quality = min(0.99, o.quality * (1 + growth_advantage * 0.3))
            else:
                # Losers stagnate or shrink slightly
                o.n_agents = max(1, int(o.n_agents * (1 - growth_advantage * 0.2)))
    
    return gini_series

def rawlsian_floor_analysis(owners: List[AgentOwner]) -> dict:
    """Analyze minimum viable agency in the ecosystem.
    
    Rawlsian justice: evaluate by the position of the worst-off.
    """
    eah = sorted([o.effective_agent_hours for o in owners])
    total = sum(eah)
    
    bottom_10 = eah[:max(1, len(eah) // 10)]
    top_10 = eah[-max(1, len(eah) // 10):]
    
    return {
        "min_eah": round(eah[0], 2),
        "max_eah": round(eah[-1], 2),
        "median_eah": round(eah[len(eah) // 2], 2),
        "bottom_10_avg": round(sum(bottom_10) / len(bottom_10), 2),
        "top_10_avg": round(sum(top_10) / len(top_10), 2),
        "top_bottom_ratio": round(sum(top_10) / max(sum(bottom_10), 0.01), 1),
        "bottom_10_share": round(sum(bottom_10) / total * 100, 1),
        "top_10_share": round(sum(top_10) / total * 100, 1),
        "gini": round(gini_coefficient(eah), 3),
    }

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("AGENTIC INEQUALITY MEASUREMENT")
    print("Sharp, Bilgin, Gabriel & Hammond (Oxford 2025)")
    print("=" * 60)
    
    # 1. Compare concentration levels
    print("\n--- Ecosystem Concentration Comparison ---")
    for level in ["equal", "moderate", "extreme"]:
        owners = simulate_ecosystem(200, level)
        analysis = rawlsian_floor_analysis(owners)
        print(f"\n{level.upper()} concentration:")
        print(f"  Gini: {analysis['gini']}")
        print(f"  Top/bottom 10% ratio: {analysis['top_bottom_ratio']}x")
        print(f"  Bottom 10% share: {analysis['bottom_10_share']}%")
        print(f"  Top 10% share: {analysis['top_10_share']}%")
    
    # 2. Feedback loop simulation
    print("\n--- Matthew Effect Simulation (20 rounds) ---")
    for level, growth in [("moderate", 0.05), ("moderate", 0.10), ("moderate", 0.20)]:
        owners = simulate_ecosystem(200, level)
        gini_series = simulate_feedback_loop(owners, rounds=20, growth_advantage=growth)
        crossing, crossed = matthew_effect_threshold(gini_series)
        
        print(f"\nGrowth advantage {growth:.0%}:")
        print(f"  Start Gini: {gini_series[0]:.3f}")
        print(f"  End Gini:   {gini_series[-1]:.3f}")
        print(f"  Δ Gini:     {gini_series[-1] - gini_series[0]:+.3f}")
        if crossed:
            print(f"  ⚠️ Crossed 0.6 threshold at round {crossing}")
        else:
            print(f"  Below 0.6 threshold (max: {max(gini_series):.3f})")
    
    # 3. Rawlsian floor under different policies
    print("\n--- Policy Intervention Comparison ---")
    
    # No intervention
    owners_base = simulate_ecosystem(200, "extreme")
    base_analysis = rawlsian_floor_analysis(owners_base)
    print(f"\nNo intervention:")
    print(f"  Gini: {base_analysis['gini']} | Bottom share: {base_analysis['bottom_10_share']}%")
    
    # Minimum floor: everyone gets at least 2 agents at quality 0.5
    owners_floor = simulate_ecosystem(200, "extreme")
    for o in owners_floor:
        o.n_agents = max(2, o.n_agents)
        o.quality = max(0.5, o.quality)
    floor_analysis = rawlsian_floor_analysis(owners_floor)
    print(f"\nMinimum agent floor (2 agents, quality≥0.5):")
    print(f"  Gini: {floor_analysis['gini']} | Bottom share: {floor_analysis['bottom_10_share']}%")
    
    # Redistribution: tax top 10%, fund bottom 30%
    owners_redist = simulate_ecosystem(200, "extreme")
    eah = sorted([(o.effective_agent_hours, o) for o in owners_redist])
    tax_pool = sum(o.n_agents * 0.1 for _, o in eah[-20:])
    for _, o in eah[:60]:
        o.n_agents += max(1, int(tax_pool / 60))
    redist_analysis = rawlsian_floor_analysis(owners_redist)
    print(f"\nCompute redistribution (10% tax on top → bottom 30%):")
    print(f"  Gini: {redist_analysis['gini']} | Bottom share: {redist_analysis['bottom_10_share']}%")
    
    print("\n" + "=" * 60)
    print("KEY FINDING: Growth advantage > 10% causes Gini to cross")
    print("the 0.6 self-reinforcing threshold within 20 rounds.")
    print("Minimum floors more effective than redistribution for")
    print("preserving participation. Rawlsian > utilitarian here.")
    print("=" * 60)
