#!/usr/bin/env python3
"""
gossip-free-rider-sim.py — Dunbar meets agent trust

Models Enquist & Leimar 1993: honest reciprocators vs free riders,
with and without gossip (information exchange about defectors).

Dunbar (2004): "If community members were able to pass on even a
modest amount of information about free riders, the free riders'
freedom of movement would be greatly curtailed."

Tests: Does gossip-based reputation destroy free rider advantage?
"""

import random
import json
from dataclasses import dataclass, field

@dataclass
class Agent:
    id: int
    strategy: str  # "honest" or "freerider"
    reputation: dict = field(default_factory=dict)  # {agent_id: score}
    fitness: float = 0.0
    gossip_received: int = 0

def run_simulation(
    n_agents: int = 200,
    frac_freeriders: float = 0.10,
    rounds: int = 50,
    interactions_per_round: int = 100,
    gossip_enabled: bool = True,
    gossip_reach: int = 3,  # how many peers you gossip with per round
    cooperation_benefit: float = 3.0,
    cooperation_cost: float = 1.0,
    trust_threshold: float = -2.0,  # below this, refuse to interact
):
    n_fr = int(n_agents * frac_freeriders)
    agents = []
    for i in range(n_agents):
        strategy = "freerider" if i < n_fr else "honest"
        agents.append(Agent(id=i, strategy=strategy))
    random.shuffle(agents)
    
    history = []
    
    for r in range(rounds):
        # Interactions: random pairs
        for _ in range(interactions_per_round):
            a, b = random.sample(agents, 2)
            
            # Check reputation — refuse if below threshold
            a_trusts_b = a.reputation.get(b.id, 0.0) > trust_threshold
            b_trusts_a = b.reputation.get(a.id, 0.0) > trust_threshold
            
            if not (a_trusts_b and b_trusts_a):
                continue  # interaction refused
            
            # Prisoner's dilemma
            a_cooperates = a.strategy == "honest"
            b_cooperates = b.strategy == "honest"
            
            if a_cooperates and b_cooperates:
                a.fitness += cooperation_benefit - cooperation_cost
                b.fitness += cooperation_benefit - cooperation_cost
            elif a_cooperates and not b_cooperates:
                a.fitness -= cooperation_cost
                b.fitness += cooperation_benefit
                # a learns b is a defector
                a.reputation[b.id] = a.reputation.get(b.id, 0.0) - 3.0
            elif not a_cooperates and b_cooperates:
                b.fitness -= cooperation_cost
                a.fitness += cooperation_benefit
                b.reputation[a.id] = b.reputation.get(a.id, 0.0) - 3.0
            else:
                pass  # mutual defection, nothing happens
        
        # Gossip phase
        if gossip_enabled:
            for a in agents:
                peers = random.sample(agents, min(gossip_reach, len(agents) - 1))
                for peer in peers:
                    if peer.id == a.id:
                        continue
                    # Share worst reputation scores
                    for target_id, score in a.reputation.items():
                        if score < -1.0:  # only gossip about bad actors
                            old = peer.reputation.get(target_id, 0.0)
                            # Weighted update — don't fully trust gossip
                            peer.reputation[target_id] = min(old, old * 0.7 + score * 0.3)
                            peer.gossip_received += 1
        
        # Snapshot
        honest_fitness = [a.fitness for a in agents if a.strategy == "honest"]
        fr_fitness = [a.fitness for a in agents if a.strategy == "freerider"]
        history.append({
            "round": r + 1,
            "honest_mean": sum(honest_fitness) / len(honest_fitness) if honest_fitness else 0,
            "freerider_mean": sum(fr_fitness) / len(fr_fitness) if fr_fitness else 0,
        })
    
    return history, agents

def main():
    random.seed(42)
    print("=" * 60)
    print("Gossip as Free Rider Control (Dunbar 2004 / Enquist & Leimar 1993)")
    print("=" * 60)
    
    for gossip in [False, True]:
        label = "WITH GOSSIP" if gossip else "NO GOSSIP"
        history, agents = run_simulation(gossip_enabled=gossip)
        
        print(f"\n--- {label} ---")
        for snap in [history[0], history[9], history[24], history[49]]:
            print(f"  Round {snap['round']:3d}: honest={snap['honest_mean']:7.1f}  freerider={snap['freerider_mean']:7.1f}  "
                  f"gap={snap['freerider_mean'] - snap['honest_mean']:+.1f}")
        
        # Final stats
        honest = [a for a in agents if a.strategy == "honest"]
        fr = [a for a in agents if a.strategy == "freerider"]
        
        fr_advantage = (sum(a.fitness for a in fr) / len(fr)) - (sum(a.fitness for a in honest) / len(honest))
        gossip_msgs = sum(a.gossip_received for a in agents)
        
        print(f"  Free rider advantage: {fr_advantage:+.1f}")
        if gossip:
            print(f"  Gossip messages exchanged: {gossip_msgs}")
            # How many honest agents learned about ALL free riders?
            fr_ids = {a.id for a in fr}
            detected = sum(1 for a in honest if all(a.reputation.get(fid, 0) < -1 for fid in fr_ids))
            print(f"  Honest agents detecting ALL free riders: {detected}/{len(honest)} ({100*detected/len(honest):.0f}%)")

if __name__ == "__main__":
    main()
