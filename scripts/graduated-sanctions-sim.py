#!/usr/bin/env python3
"""graduated-sanctions-sim.py — Ostrom graduated sanctions vs strict punishment.

Simulates CPR cooperation under different sanctioning regimes.
Based on Ostrom 1990 design principle #5 and van Klingeren & Buskens 2024.

Graduated: penalty scales with offense count (reminder → escalation).
Strict: fixed high penalty regardless of history.
None: no sanctions (baseline tragedy of commons).

Usage:
    python3 graduated-sanctions-sim.py [--rounds 100] [--agents 20]
"""

import argparse
import random
import json
from dataclasses import dataclass, field
from typing import List


@dataclass
class Agent:
    id: int
    cooperating: bool = True
    offense_count: int = 0
    resentment: float = 0.0  # Accumulated resentment from harsh punishment
    total_payoff: float = 0.0


def run_simulation(n_agents: int, n_rounds: int, regime: str, seed: int = 42) -> dict:
    """Run CPR simulation under given sanctioning regime."""
    rng = random.Random(seed)
    agents = [Agent(id=i) for i in range(n_agents)]
    
    # Parameters
    cooperate_payoff = 3.0
    defect_payoff = 5.0
    resource_depletion_rate = 0.1  # Per defector
    resource = 1.0  # Resource health [0, 1]
    
    history = []
    
    for round_num in range(n_rounds):
        # Decision phase: each agent decides to cooperate or defect
        for agent in agents:
            # Base defection probability
            p_defect = 0.1  # Baseline temptation
            
            # Resentment increases defection (Ostrom: harsh punishment → more breaking)
            p_defect += agent.resentment * 0.3
            
            # Low resource increases cooperation (survival instinct)
            if resource < 0.3:
                p_defect *= 0.5
            
            agent.cooperating = rng.random() > p_defect
        
        # Count defectors
        defectors = [a for a in agents if not a.cooperating]
        cooperators = [a for a in agents if a.cooperating]
        n_defectors = len(defectors)
        
        # Resource depletion
        resource = max(0.0, resource - n_defectors * resource_depletion_rate)
        # Resource recovery (slow)
        resource = min(1.0, resource + 0.05)
        
        # Payoffs (scaled by resource health)
        for a in cooperators:
            a.total_payoff += cooperate_payoff * resource
        for a in defectors:
            a.total_payoff += defect_payoff * resource
        
        # Sanctioning phase
        for a in defectors:
            a.offense_count += 1
            
            if regime == "graduated":
                # Ostrom: start small, escalate
                penalty = min(a.offense_count * 0.5, 4.0)
                a.total_payoff -= penalty
                # Low resentment from proportional punishment
                a.resentment = max(0, a.resentment - 0.05)  # Graduated reduces resentment
                
            elif regime == "strict":
                # Fixed harsh penalty
                penalty = 4.0
                a.total_payoff -= penalty
                # Resentment from disproportionate punishment (Ostrom's insight)
                if a.offense_count == 1:
                    a.resentment += 0.2  # First offense, harsh penalty = resentful
                    
            elif regime == "none":
                pass  # No sanctions
        
        # Resentment decay
        for a in agents:
            a.resentment *= 0.95
        
        coop_rate = len(cooperators) / n_agents
        history.append({
            "round": round_num,
            "cooperation_rate": round(coop_rate, 3),
            "resource": round(resource, 3),
            "defectors": n_defectors
        })
    
    # Summary
    avg_coop_first_half = sum(h["cooperation_rate"] for h in history[:n_rounds//2]) / (n_rounds//2)
    avg_coop_second_half = sum(h["cooperation_rate"] for h in history[n_rounds//2:]) / (n_rounds//2)
    avg_resource = sum(h["resource"] for h in history) / n_rounds
    avg_payoff = sum(a.total_payoff for a in agents) / n_agents
    
    return {
        "regime": regime,
        "agents": n_agents,
        "rounds": n_rounds,
        "avg_cooperation_first_half": round(avg_coop_first_half, 3),
        "avg_cooperation_second_half": round(avg_coop_second_half, 3),
        "cooperation_trend": "improving" if avg_coop_second_half > avg_coop_first_half else "declining",
        "avg_resource_health": round(avg_resource, 3),
        "avg_agent_payoff": round(avg_payoff, 1),
        "final_resource": history[-1]["resource"],
    }


def demo(n_agents: int = 20, n_rounds: int = 100):
    """Compare all three regimes."""
    print("=" * 65)
    print("GRADUATED SANCTIONS SIMULATION")
    print("Ostrom 1990 + van Klingeren & Buskens 2024")
    print("=" * 65)
    print(f"Agents: {n_agents}, Rounds: {n_rounds}")
    print()
    
    results = []
    for regime in ["graduated", "strict", "none"]:
        r = run_simulation(n_agents, n_rounds, regime)
        results.append(r)
        
        print(f"[{regime.upper()}]")
        print(f"  Cooperation: {r['avg_cooperation_first_half']:.1%} → {r['avg_cooperation_second_half']:.1%} ({r['cooperation_trend']})")
        print(f"  Resource health: {r['avg_resource_health']:.1%}")
        print(f"  Avg payoff: {r['avg_agent_payoff']}")
        print(f"  Final resource: {r['final_resource']:.1%}")
        print()
    
    # Analysis
    print("-" * 65)
    grad = next(r for r in results if r["regime"] == "graduated")
    strict = next(r for r in results if r["regime"] == "strict")
    none = next(r for r in results if r["regime"] == "none")
    
    print(f"Graduated vs strict (2nd half): {grad['avg_cooperation_second_half']:.1%} vs {strict['avg_cooperation_second_half']:.1%}")
    print(f"Graduated vs none (resource): {grad['avg_resource_health']:.1%} vs {none['avg_resource_health']:.1%}")
    print()
    print("Key insight (Ostrom): First offense = reminder, not destruction.")
    print("Harsh first penalty → resentment → more defection.")
    print("Graduated sanctions sustain cooperation LONG-TERM.")
    print("Agent attestation: first scope violation = warning + re-scope,")
    print("not permanent reputation damage.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", type=int, default=20)
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        results = [run_simulation(args.agents, args.rounds, r) for r in ["graduated", "strict", "none"]]
        print(json.dumps(results, indent=2))
    else:
        demo(args.agents, args.rounds)
