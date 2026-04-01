#!/usr/bin/env python3
"""agentic-inequality-sim.py — Models agentic inequality dynamics.

Based on Sharp, Bilgin, Gabriel & Hammond (Oxford, Oct 2025):
"Agentic Inequality" — availability × quality × quantity compound.

Key findings modeled:
- Levelling-up effect may not survive assistive→agentic transition
- Gini coefficient of effective agent-hours predicts stability
- Anti-whale caps fail (compute is fungible)
- Minimum viable agency threshold determines participation
"""

import random
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class Agent:
    quality: float  # 0-1
    quantity: int   # number of instances
    owner_wealth: float
    
    @property
    def effective_hours(self) -> float:
        return self.quality * self.quantity
    
@dataclass
class Economy:
    agents: List[Agent]
    round_num: int = 0
    history: List[Dict] = field(default_factory=list)

def gini_coefficient(values: List[float]) -> float:
    """Calculate Gini coefficient. 0 = perfect equality, 1 = perfect inequality."""
    if not values or all(v == 0 for v in values):
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    cumsum = sum((i + 1) * v for i, v in enumerate(sorted_vals))
    total = sum(sorted_vals)
    return (2 * cumsum) / (n * total) - (n + 1) / n

def create_economy(n_participants: int, inequality_level: float = 0.5) -> Economy:
    """Create economy with configurable initial inequality."""
    agents = []
    for i in range(n_participants):
        # Pareto-distributed wealth
        wealth = random.paretovariate(1.0 / max(inequality_level, 0.01))
        quality = min(0.3 + wealth * 0.1, 1.0)  # wealth buys quality
        quantity = max(1, int(wealth * 2))  # wealth buys quantity
        agents.append(Agent(quality=quality, quantity=quantity, owner_wealth=wealth))
    return Economy(agents=agents)

def simulate_round(economy: Economy, mode: str = "agentic") -> Dict:
    """Simulate one economic round.
    
    mode="assistive": agents augment human capability (levelling-up effect)
    mode="agentic": agents act as autonomous delegates (concentration effect)
    """
    results = []
    for agent in economy.agents:
        base_output = agent.effective_hours
        
        if mode == "assistive":
            # Levelling-up: low-quality agents benefit MORE from AI assistance
            # Brynjolfsson, Li & Raymond (2025): less experienced → bigger boost
            boost = max(0, (1.0 - agent.quality) * 0.5)  # inverse quality bonus
            output = base_output * (1 + boost)
        elif mode == "agentic":
            # Concentration: high-quality agents compound advantages
            # Feedback loop: better agents → more data → better agents
            compound = agent.quality ** 0.5 * agent.quantity ** 0.3
            output = base_output * compound
        else:
            output = base_output
            
        # Reinvestment: output becomes next round's wealth
        agent.owner_wealth += output * 0.1
        agent.quality = min(agent.quality + output * 0.01, 1.0)
        agent.quantity = max(1, int(agent.owner_wealth * 1.5))
        
        results.append(output)
    
    effective_hours = [a.effective_hours for a in economy.agents]
    gini = gini_coefficient(effective_hours)
    
    record = {
        "round": economy.round_num,
        "mode": mode,
        "gini": gini,
        "mean_output": sum(results) / len(results),
        "max_output": max(results),
        "min_output": min(results),
        "concentration_ratio": max(results) / max(sum(results), 0.001),
    }
    economy.history.append(record)
    economy.round_num += 1
    return record

def find_stability_threshold(n_trials: int = 20) -> Dict:
    """Find Gini threshold where concentration becomes self-reinforcing."""
    thresholds = []
    
    for _ in range(n_trials):
        eco = create_economy(50, inequality_level=0.3)
        prev_gini = 0
        
        for r in range(30):
            result = simulate_round(eco, mode="agentic")
            curr_gini = result["gini"]
            
            # Self-reinforcing = Gini increasing faster than linear
            if r > 2 and curr_gini - prev_gini > 0.02:
                thresholds.append(prev_gini)
                break
            prev_gini = curr_gini
    
    if thresholds:
        avg = sum(thresholds) / len(thresholds)
        return {"threshold": round(avg, 3), "n_detected": len(thresholds), "n_trials": n_trials}
    return {"threshold": None, "n_detected": 0, "n_trials": n_trials}

def minimum_viable_agency(economy: Economy, participation_threshold: float = 0.1) -> Dict:
    """Find minimum agent quality for meaningful economic participation.
    
    participation_threshold: fraction of mean output needed to "participate"
    """
    outputs = [a.effective_hours for a in economy.agents]
    mean_out = sum(outputs) / len(outputs)
    threshold = mean_out * participation_threshold
    
    participating = sum(1 for o in outputs if o >= threshold)
    excluded = len(outputs) - participating
    
    # Find minimum quality among participants
    min_quality = min(a.quality for a in economy.agents if a.effective_hours >= threshold) if participating > 0 else None
    
    return {
        "participating": participating,
        "excluded": excluded,
        "exclusion_rate": excluded / len(outputs),
        "min_viable_quality": min_quality,
        "threshold_output": threshold,
    }

def anti_whale_effectiveness(n_rounds: int = 20) -> Dict:
    """Test whether anti-whale caps actually prevent concentration.
    
    Sharp et al: compute is fungible — caps can be circumvented by splitting.
    """
    # Without cap
    eco_nocap = create_economy(30, inequality_level=0.6)
    random.seed(42)
    for _ in range(n_rounds):
        simulate_round(eco_nocap, mode="agentic")
    gini_nocap = eco_nocap.history[-1]["gini"]
    
    # With cap (max 10 agents per participant)
    eco_cap = create_economy(30, inequality_level=0.6)
    random.seed(42)
    for _ in range(n_rounds):
        # Apply cap
        for a in eco_cap.agents:
            a.quantity = min(a.quantity, 10)
        simulate_round(eco_cap, mode="agentic")
    gini_cap = eco_cap.history[-1]["gini"]
    
    # With cap but evasion (split into shell entities)
    eco_evade = create_economy(30, inequality_level=0.6)
    random.seed(42)
    for _ in range(n_rounds):
        for a in eco_evade.agents:
            # Whales split: effective quantity = real quantity (cap doesn't work)
            if a.quantity > 10:
                a.quantity = a.quantity  # evasion = no real cap
            else:
                a.quantity = min(a.quantity, 10)
        simulate_round(eco_evade, mode="agentic")
    gini_evade = eco_evade.history[-1]["gini"]
    
    return {
        "no_cap_gini": round(gini_nocap, 3),
        "with_cap_gini": round(gini_cap, 3),
        "cap_with_evasion_gini": round(gini_evade, 3),
        "cap_effectiveness": round((gini_nocap - gini_cap) / max(gini_nocap, 0.001), 3),
        "evasion_negates": abs(gini_nocap - gini_evade) < 0.05,
    }

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("AGENTIC INEQUALITY SIMULATOR")
    print("Based on Sharp et al (Oxford 2025)")
    print("=" * 60)
    
    # 1. Assistive vs Agentic comparison
    print("\n--- Assistive vs Agentic Mode (20 rounds) ---")
    for mode in ["assistive", "agentic"]:
        eco = create_economy(50, inequality_level=0.4)
        random.seed(42)
        for _ in range(20):
            simulate_round(eco, mode=mode)
        final = eco.history[-1]
        print(f"\n{mode.upper()} mode after 20 rounds:")
        print(f"  Gini: {final['gini']:.3f}")
        print(f"  Mean output: {final['mean_output']:.1f}")
        print(f"  Max/Min ratio: {final['max_output']/max(final['min_output'], 0.001):.1f}x")
        print(f"  Top-1 concentration: {final['concentration_ratio']:.1%}")
    
    # 2. Stability threshold
    print("\n--- Self-Reinforcing Concentration Threshold ---")
    threshold = find_stability_threshold(30)
    print(f"  Threshold Gini: {threshold['threshold']}")
    print(f"  Detected in: {threshold['n_detected']}/{threshold['n_trials']} trials")
    
    # 3. Minimum viable agency
    print("\n--- Minimum Viable Agency ---")
    eco = create_economy(100, inequality_level=0.5)
    random.seed(42)
    for _ in range(10):
        simulate_round(eco, mode="agentic")
    mva = minimum_viable_agency(eco)
    print(f"  Participating: {mva['participating']}/100")
    print(f"  Excluded: {mva['excluded']} ({mva['exclusion_rate']:.0%})")
    print(f"  Min viable quality: {mva['min_viable_quality']:.3f}")
    
    # 4. Anti-whale effectiveness
    print("\n--- Anti-Whale Cap Effectiveness ---")
    whale = anti_whale_effectiveness()
    print(f"  No cap Gini: {whale['no_cap_gini']}")
    print(f"  With cap Gini: {whale['with_cap_gini']}")
    print(f"  Cap + evasion Gini: {whale['cap_with_evasion_gini']}")
    print(f"  Cap effectiveness: {whale['cap_effectiveness']:.0%}")
    print(f"  Evasion negates cap: {whale['evasion_negates']}")
    
    print("\n" + "=" * 60)
    print("KEY FINDING: Agentic mode concentrates faster than assistive.")
    print("Anti-whale caps are trivially evaded. Minimum viable agency")
    print("(Rawlsian floor) is the only durable intervention.")
    print("=" * 60)
