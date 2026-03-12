#!/usr/bin/env python3
"""
coalition-punishment-sim.py — Maghribi-style multilateral punishment for agent networks.

Greif (1989): 11th-century Mediterranean traders enforced honesty through
MULTILATERAL punishment — cheat one merchant, lose access to ALL merchants.
This compressed reputation-building from years to transactions.

Simulates: bilateral vs multilateral punishment in agent trade networks.
Key insight: multilateral punishment makes cheating cost O(N) not O(1).
"""

import random
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Agent:
    name: str
    honest: bool = True  # disposition
    cheat_prob: float = 0.0  # probability of cheating per transaction
    reputation: dict = field(default_factory=dict)  # agent -> score
    blacklisted_by: set = field(default_factory=set)
    completed: int = 0
    cheated: int = 0
    revenue: float = 0.0


def simulate(n_agents: int = 20, n_rounds: int = 200, n_cheaters: int = 3,
             cheat_prob: float = 0.3, mode: str = "multilateral") -> dict:
    """Run coalition punishment simulation.
    
    mode: "bilateral" (only victim punishes) or "multilateral" (all punish)
    """
    agents = []
    for i in range(n_agents):
        is_cheater = i < n_cheaters
        agents.append(Agent(
            name=f"agent_{i:02d}",
            honest=not is_cheater,
            cheat_prob=cheat_prob if is_cheater else 0.0,
        ))
    
    events = []
    
    for round_num in range(n_rounds):
        # Random pair selection
        a, b = random.sample(agents, 2)
        
        # Check if blacklisted
        if mode == "multilateral":
            if a.name in b.blacklisted_by or b.name in a.blacklisted_by:
                continue
        elif mode == "bilateral":
            if a.reputation.get(b.name, 1.0) <= 0 or b.reputation.get(a.name, 1.0) <= 0:
                continue
        
        # Transaction
        a_cheats = random.random() < a.cheat_prob
        b_cheats = random.random() < b.cheat_prob
        
        if a_cheats:
            a.cheated += 1
            a.revenue += 2.0  # short-term gain
            b.revenue -= 1.0  # victim loss
            
            if mode == "multilateral":
                # ALL agents blacklist cheater (Maghribi style)
                for agent in agents:
                    if agent.name != a.name:
                        agent.blacklisted_by.add(a.name)  # wrong direction, fix:
                a.blacklisted_by = {ag.name for ag in agents if ag.name != a.name}
                events.append({"round": round_num, "cheater": a.name, "victim": b.name, "punishment": "multilateral"})
            else:
                # Only victim knows
                b.reputation[a.name] = 0.0
                events.append({"round": round_num, "cheater": a.name, "victim": b.name, "punishment": "bilateral"})
        
        if b_cheats:
            b.cheated += 1
            b.revenue += 2.0
            a.revenue -= 1.0
            
            if mode == "multilateral":
                b.blacklisted_by = {ag.name for ag in agents if ag.name != b.name}
                events.append({"round": round_num, "cheater": b.name, "victim": a.name, "punishment": "multilateral"})
            else:
                a.reputation[b.name] = 0.0
                events.append({"round": round_num, "cheater": b.name, "victim": a.name, "punishment": "bilateral"})
        
        if not a_cheats and not b_cheats:
            a.revenue += 1.0
            b.revenue += 1.0
            a.completed += 1
            b.completed += 1
    
    # Analyze
    honest_agents = [a for a in agents if a.honest]
    cheater_agents = [a for a in agents if not a.honest]
    
    honest_rev = sum(a.revenue for a in honest_agents) / len(honest_agents) if honest_agents else 0
    cheater_rev = sum(a.revenue for a in cheater_agents) / len(cheater_agents) if cheater_agents else 0
    total_cheats = sum(a.cheated for a in agents)
    total_completed = sum(a.completed for a in agents) // 2  # each tx counted twice
    
    return {
        "mode": mode,
        "n_agents": n_agents,
        "n_cheaters": n_cheaters,
        "n_rounds": n_rounds,
        "cheat_prob": cheat_prob,
        "total_cheats": total_cheats,
        "total_completed": total_completed,
        "honest_avg_revenue": round(honest_rev, 2),
        "cheater_avg_revenue": round(cheater_rev, 2),
        "cheating_profitable": cheater_rev > honest_rev,
        "cheat_events": len(events),
    }


def demo():
    random.seed(42)
    print("=== Maghribi Coalition Punishment Simulator ===\n")
    print("Greif (1989): multilateral punishment makes cheating cost O(N)\n")
    
    for mode in ["bilateral", "multilateral"]:
        result = simulate(mode=mode)
        profitable = "YES ⚠️" if result["cheating_profitable"] else "NO ✅"
        print(f"  {mode.upper()}:")
        print(f"    Honest avg revenue:  {result['honest_avg_revenue']}")
        print(f"    Cheater avg revenue: {result['cheater_avg_revenue']}")
        print(f"    Cheating profitable: {profitable}")
        print(f"    Total cheats: {result['total_cheats']}, Completed: {result['total_completed']}")
        print()
    
    print("  Insight: multilateral punishment (shared attestation feeds)")
    print("  makes cheating unprofitable by making cost = losing ALL partners.")
    print("  Bilateral = lose one partner. Multilateral = lose the network.")


if __name__ == "__main__":
    import sys
    if "--json" in sys.argv:
        results = {
            "bilateral": simulate(mode="bilateral"),
            "multilateral": simulate(mode="multilateral"),
        }
        print(json.dumps(results, indent=2))
    else:
        demo()
