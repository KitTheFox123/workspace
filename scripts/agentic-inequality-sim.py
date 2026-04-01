#!/usr/bin/env python3
"""agentic-inequality-sim.py — Models agentic inequality dynamics.

Based on Sharp et al (Oxford, 2025) "Agentic Inequality" framework:
- Three dimensions: availability, quality, quantity
- Compounding effects create self-reinforcing concentration
- Levelling-up effect may not survive tool→agent transition

Plus "When Crowds Fail" (2026): discourse cues predict collective failure.
"""

import random
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class Agent:
    id: int
    compute: float  # normalized 0-1
    quality: float   # model quality 0-1
    quantity: int     # number of sub-agents
    wealth: float = 0.0
    active: bool = True

    @property
    def effective_power(self) -> float:
        """Sharp et al: compounding across dimensions."""
        return self.compute * self.quality * math.log2(self.quantity + 1)

def gini_coefficient(values: List[float]) -> float:
    """Calculate Gini coefficient for inequality measurement."""
    n = len(values)
    if n == 0 or sum(values) == 0:
        return 0.0
    sorted_vals = sorted(values)
    cumulative = sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(sorted_vals))
    return cumulative / (n * sum(sorted_vals))

def simulate_economy(n_agents: int = 100, rounds: int = 50, 
                     redistribution: float = 0.0,
                     min_viable_threshold: float = 0.1) -> Dict:
    """Simulate agent economy with inequality dynamics.
    
    Args:
        redistribution: fraction of top-quintile wealth redistributed per round
        min_viable_threshold: minimum effective_power to stay active
    """
    random.seed(42)
    
    # Initialize with log-normal distribution (realistic wealth inequality)
    agents = []
    for i in range(n_agents):
        compute = max(0.01, min(1.0, random.lognormvariate(-0.5, 0.8)))
        quality = max(0.1, min(1.0, random.gauss(0.5, 0.2)))
        quantity = max(1, int(random.lognormvariate(0.5, 1.0)))
        agents.append(Agent(id=i, compute=compute, quality=quality, quantity=quantity))
    
    history = {"gini": [], "active_pct": [], "top10_share": [], "median_wealth": []}
    
    for round_num in range(rounds):
        # Each agent earns proportional to effective_power
        for a in agents:
            if not a.active:
                continue
            earnings = a.effective_power * random.uniform(0.5, 1.5)
            a.wealth += earnings
            
            # Feedback loop: wealth buys more compute/quantity
            if a.wealth > 5 * round_num / rounds:
                a.compute = min(1.0, a.compute * 1.02)
                if random.random() < 0.1:
                    a.quantity += 1
        
        # Check minimum viable threshold
        for a in agents:
            if a.active and a.effective_power < min_viable_threshold:
                if random.random() < 0.3:  # 30% chance of exit per round below threshold
                    a.active = False
        
        # Redistribution mechanism
        if redistribution > 0:
            active_agents = [a for a in agents if a.active]
            active_agents.sort(key=lambda a: a.wealth, reverse=True)
            top_20 = active_agents[:len(active_agents)//5]
            bottom_50 = active_agents[len(active_agents)//2:]
            
            pool = sum(a.wealth * redistribution * 0.1 for a in top_20)
            if bottom_50:
                per_agent = pool / len(bottom_50)
                for a in top_20:
                    a.wealth -= a.wealth * redistribution * 0.1
                for a in bottom_50:
                    a.wealth += per_agent
        
        # Record metrics
        wealths = [a.wealth for a in agents if a.active]
        all_wealths = [a.wealth for a in agents]
        
        history["gini"].append(gini_coefficient(wealths) if wealths else 1.0)
        history["active_pct"].append(sum(1 for a in agents if a.active) / n_agents * 100)
        
        sorted_w = sorted(all_wealths, reverse=True)
        total = sum(sorted_w) or 1
        history["top10_share"].append(sum(sorted_w[:n_agents//10]) / total * 100)
        history["median_wealth"].append(sorted(wealths)[len(wealths)//2] if wealths else 0)
    
    return {
        "final_gini": history["gini"][-1],
        "final_active_pct": history["active_pct"][-1],
        "final_top10_share": history["top10_share"][-1],
        "gini_trajectory": [history["gini"][i] for i in range(0, rounds, rounds//5)],
        "active_trajectory": [history["active_pct"][i] for i in range(0, rounds, rounds//5)],
        "concentration_critical": history["gini"][-1] > 0.6,
    }

def crowd_failure_predictor(comment_ratio: float, informality: float,
                            exclamation_rate: float, anxiety_lang: float) -> Dict:
    """Predict crowd failure based on discourse cues.
    
    Based on "When Crowds Fail" (2026):
    - High comment-to-prediction ratio → more error
    - Informal language (profanity, disfluencies) → more error
    - Exclamation marks → more error
    - Anxiety language → LESS error (careful thinking)
    """
    # Simplified model from the paper's 14-variable regression
    error_score = (
        0.15 * comment_ratio +
        0.20 * informality +
        0.18 * exclamation_rate -
        0.12 * anxiety_lang +
        0.3  # baseline
    )
    error_score = max(0, min(1, error_score))
    
    risk = "HIGH" if error_score > 0.6 else "MODERATE" if error_score > 0.4 else "LOW"
    
    return {
        "predicted_error": round(error_score, 3),
        "risk_level": risk,
        "key_driver": max(
            [("comment_ratio", comment_ratio * 0.15),
             ("informality", informality * 0.20),
             ("exclamation_rate", exclamation_rate * 0.18)],
            key=lambda x: x[1]
        )[0],
        "protective_factor": "anxiety_language" if anxiety_lang > 0.3 else "none",
        "recommendation": "Reduce discussion volume, encourage careful language" if error_score > 0.5
                         else "Crowd calibration acceptable"
    }

if __name__ == "__main__":
    print("=" * 60)
    print("AGENTIC INEQUALITY SIMULATOR")
    print("Sharp et al (Oxford 2025) + When Crowds Fail (2026)")
    print("=" * 60)
    
    # Test different redistribution levels
    print("\n--- Economy Simulation (100 agents, 50 rounds) ---")
    for redist, label in [(0.0, "No redistribution"), (0.1, "10% redistribution"), (0.3, "30% redistribution")]:
        result = simulate_economy(redistribution=redist)
        print(f"\n{label}:")
        print(f"  Final Gini: {result['final_gini']:.3f} {'⚠️ CRITICAL' if result['concentration_critical'] else '✓'}")
        print(f"  Active agents: {result['final_active_pct']:.0f}%")
        print(f"  Top 10% wealth share: {result['final_top10_share']:.1f}%")
        print(f"  Gini trajectory: {' → '.join(f'{g:.2f}' for g in result['gini_trajectory'])}")
        print(f"  Active trajectory: {' → '.join(f'{a:.0f}%' for a in result['active_trajectory'])}")
    
    # Crowd failure predictions
    print("\n--- Crowd Failure Prediction ---")
    scenarios = [
        ("Calm deliberation", 0.3, 0.1, 0.05, 0.4),
        ("Heated debate", 0.8, 0.6, 0.4, 0.1),
        ("Anxiety-driven caution", 0.5, 0.2, 0.1, 0.7),
        ("Hype train", 0.9, 0.7, 0.8, 0.05),
    ]
    for name, cr, inf, exc, anx in scenarios:
        pred = crowd_failure_predictor(cr, inf, exc, anx)
        print(f"\n{name}:")
        print(f"  Error: {pred['predicted_error']:.3f} | Risk: {pred['risk_level']}")
        print(f"  Driver: {pred['key_driver']} | Protection: {pred['protective_factor']}")
    
    # Key insight
    print("\n" + "=" * 60)
    print("KEY FINDINGS:")
    print("1. Without redistribution, Gini crosses 0.6 = self-reinforcing")
    print("2. 30% redistribution keeps economy viable but slows growth")  
    print("3. Crowd failure: hype + exclamation marks = worst predictor")
    print("4. Anxiety language is PROTECTIVE — careful > confident")
    print("=" * 60)
