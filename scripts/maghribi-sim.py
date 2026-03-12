#!/usr/bin/env python3
"""
maghribi-sim.py — Simulate Greif's Maghribi coalition mechanism for agent trust.

Greif (1989): 11th century Mediterranean traders solved the overseas agent problem
through multilateral punishment. Cheat one merchant → ALL merchants exclude you.
Coalition membership was the asset worth protecting.

This simulator models:
- N agents in a coalition with shared attestation feed
- Cheating detected by victims, propagated to all members
- Bilateral (victim-only) vs multilateral (coalition-wide) punishment
- How coalition size affects cheating incentive

Key insight: multilateral punishment makes cheating irrational even when
bilateral punishment alone wouldn't deter it.
"""

import random
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Agent:
    name: str
    honest: bool = True
    reputation: float = 1.0
    earnings: float = 0.0
    excluded_by: set = field(default_factory=set)
    cheat_count: int = 0
    trade_count: int = 0


def simulate(
    n_agents: int = 20,
    n_rounds: int = 100,
    cheat_prob: float = 0.05,  # probability of cheating per trade
    trade_value: float = 10.0,
    cheat_bonus: float = 15.0,  # one-time gain from cheating
    multilateral: bool = True,  # coalition-wide vs bilateral punishment
    seed: int = 42,
) -> dict:
    random.seed(seed)
    agents = [Agent(name=f"agent_{i}") for i in range(n_agents)]
    
    cheats_detected = 0
    total_trades = 0
    exclusion_events = []
    
    for round_num in range(n_rounds):
        # Each round: random pairs trade
        random.shuffle(agents)
        pairs = [(agents[i], agents[i+1]) for i in range(0, len(agents)-1, 2)]
        
        for merchant, overseas_agent in pairs:
            # Skip if either is excluded by the other
            if merchant.name in overseas_agent.excluded_by:
                continue
            if overseas_agent.name in merchant.excluded_by:
                continue
            
            total_trades += 1
            merchant.trade_count += 1
            overseas_agent.trade_count += 1
            
            # Will the overseas agent cheat?
            if random.random() < cheat_prob:
                # Cheat: agent gets bonus, merchant gets nothing
                overseas_agent.earnings += cheat_bonus
                overseas_agent.cheat_count += 1
                cheats_detected += 1
                
                if multilateral:
                    # Coalition punishment: ALL agents exclude cheater
                    for a in agents:
                        if a.name != overseas_agent.name:
                            overseas_agent.excluded_by.add(a.name)
                    exclusion_events.append({
                        "round": round_num,
                        "cheater": overseas_agent.name,
                        "excluders": n_agents - 1,
                        "type": "multilateral",
                    })
                else:
                    # Bilateral: only victim excludes
                    overseas_agent.excluded_by.add(merchant.name)
                    exclusion_events.append({
                        "round": round_num,
                        "cheater": overseas_agent.name,
                        "excluders": 1,
                        "type": "bilateral",
                    })
            else:
                # Honest trade: both earn
                merchant.earnings += trade_value * 0.6
                overseas_agent.earnings += trade_value * 0.4
    
    # Results
    active_agents = [a for a in agents if len(a.excluded_by) < n_agents - 1]
    excluded_agents = [a for a in agents if len(a.excluded_by) >= n_agents - 1]
    
    avg_earnings_active = (
        sum(a.earnings for a in active_agents) / len(active_agents)
        if active_agents else 0
    )
    avg_earnings_excluded = (
        sum(a.earnings for a in excluded_agents) / len(excluded_agents)
        if excluded_agents else 0
    )
    
    return {
        "config": {
            "n_agents": n_agents,
            "n_rounds": n_rounds,
            "cheat_prob": cheat_prob,
            "punishment": "multilateral" if multilateral else "bilateral",
        },
        "results": {
            "total_trades": total_trades,
            "cheats_detected": cheats_detected,
            "cheat_rate": round(cheats_detected / max(total_trades, 1), 4),
            "active_agents": len(active_agents),
            "excluded_agents": len(excluded_agents),
            "avg_earnings_active": round(avg_earnings_active, 2),
            "avg_earnings_excluded": round(avg_earnings_excluded, 2),
            "exclusion_events": len(exclusion_events),
        },
        "insight": (
            f"{'Multilateral' if multilateral else 'Bilateral'} punishment: "
            f"{len(excluded_agents)} agents excluded, "
            f"active agents earned {avg_earnings_active:.0f} vs excluded {avg_earnings_excluded:.0f}. "
            f"{'Coalition deterrence effective.' if multilateral and avg_earnings_excluded < avg_earnings_active * 0.5 else 'Bilateral punishment insufficient — cheaters still earn.'}"
        ),
    }


def demo():
    print("=== Maghribi Coalition Simulator ===")
    print("(Greif 1989: multilateral vs bilateral punishment)\n")
    
    for mode in [True, False]:
        result = simulate(multilateral=mode)
        label = result["config"]["punishment"].upper()
        r = result["results"]
        print(f"  {label}:")
        print(f"    Trades: {r['total_trades']}, Cheats: {r['cheats_detected']} ({r['cheat_rate']*100:.1f}%)")
        print(f"    Active: {r['active_agents']}, Excluded: {r['excluded_agents']}")
        print(f"    Earnings — active: {r['avg_earnings_active']}, excluded: {r['avg_earnings_excluded']}")
        print(f"    → {result['insight']}")
        print()


if __name__ == "__main__":
    demo()
