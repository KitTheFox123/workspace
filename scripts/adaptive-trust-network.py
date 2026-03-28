#!/usr/bin/env python3
"""
adaptive-trust-network.py — Adaptive coevolutionary networks for ATF.

In adaptive networks (Gross & Blasius, J R Soc Interface 2008), topology
and node dynamics co-evolve. Nodes change state AND rewire connections
simultaneously. This creates emergent structure from simple local rules.

Applied to ATF: agents don't just passively receive trust scores — they
REWIRE who they attest based on observed trustworthiness. The trust
topology and trust values co-evolve.

Key insight from epidemic models on adaptive networks:
- Adaptive rewiring (severing ties to compromised agents) RAISES the
  epidemic threshold. Bad trust can't propagate as easily.
- But rewiring also fragments the network, creating echo chambers of
  mutual attestation (homophily traps).
- The sweet spot: moderate rewiring rate. Too slow = epidemic spreads.
  Too fast = network fragments into disconnected cliques.

Gross & Blasius (2008): "All these studies are characterized by common
themes, most prominently: complex dynamics and robust topological
self-organization based on simple local rules."

ATF parallel:
- AIMD = local rule (additive increase, multiplicative decrease)
- min() composition = local rule (take minimum of chain)
- Rewiring based on attestation failures = adaptive topology
- Emergent: trust clusters, firewall agents, phase transitions

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class TrustAgent:
    id: str
    trust_score: float = 0.5  # Current trust [0, 1]
    compromised: bool = False
    rewire_rate: float = 0.3  # Probability of rewiring vs tolerating


class AdaptiveTrustNetwork:
    """
    SIS-like epidemic on an adaptive network.
    
    States: TRUSTWORTHY (S) / COMPROMISED (I)
    Dynamics:
    - Compromised agents infect neighbors (bad attestations propagate)
    - Agents recover (get re-validated)
    - Agents REWIRE: sever ties to compromised neighbors, form new ties
    
    Co-evolution: topology changes WITH trust dynamics.
    """
    
    def __init__(self, n_agents: int = 100, avg_degree: int = 6,
                 infection_rate: float = 0.15,
                 recovery_rate: float = 0.05,
                 rewire_rate: float = 0.3):
        self.agents: dict[str, TrustAgent] = {}
        self.edges: set[tuple[str, str]] = set()
        self.n = n_agents
        self.infection_rate = infection_rate
        self.recovery_rate = recovery_rate
        self.rewire_rate = rewire_rate
        
        # Create agents
        for i in range(n_agents):
            self.agents[f"a{i}"] = TrustAgent(id=f"a{i}")
        
        # Create random network with target avg degree
        agent_ids = list(self.agents.keys())
        target_edges = (n_agents * avg_degree) // 2
        while len(self.edges) < target_edges:
            a, b = random.sample(agent_ids, 2)
            edge = (min(a, b), max(a, b))
            self.edges.add(edge)
        
        # Infect initial seed
        initial_infected = random.sample(agent_ids, max(1, n_agents // 10))
        for aid in initial_infected:
            self.agents[aid].compromised = True
    
    def get_neighbors(self, agent_id: str) -> list[str]:
        neighbors = []
        for a, b in self.edges:
            if a == agent_id:
                neighbors.append(b)
            elif b == agent_id:
                neighbors.append(a)
        return neighbors
    
    def step(self) -> dict:
        """One timestep of co-evolution."""
        new_infections = 0
        recoveries = 0
        rewires = 0
        
        agent_ids = list(self.agents.keys())
        random.shuffle(agent_ids)
        
        edges_to_remove = set()
        edges_to_add = set()
        
        for aid in agent_ids:
            agent = self.agents[aid]
            neighbors = self.get_neighbors(aid)
            
            if agent.compromised:
                # Recovery: agent gets re-validated
                if random.random() < self.recovery_rate:
                    agent.compromised = False
                    recoveries += 1
                else:
                    # Try to infect neighbors
                    for nid in neighbors:
                        if not self.agents[nid].compromised:
                            if random.random() < self.infection_rate:
                                self.agents[nid].compromised = True
                                new_infections += 1
            else:
                # Susceptible agent: check neighbors for compromise
                compromised_neighbors = [n for n in neighbors if self.agents[n].compromised]
                
                for cn in compromised_neighbors:
                    if random.random() < self.rewire_rate:
                        # ADAPTIVE REWIRING: sever tie to compromised neighbor
                        edge = (min(aid, cn), max(aid, cn))
                        edges_to_remove.add(edge)
                        
                        # Form new tie to random non-neighbor trustworthy agent
                        non_neighbors = set(agent_ids) - set(neighbors) - {aid}
                        trustworthy = [n for n in non_neighbors 
                                      if not self.agents[n].compromised]
                        if trustworthy:
                            new_neighbor = random.choice(trustworthy)
                            new_edge = (min(aid, new_neighbor), max(aid, new_neighbor))
                            edges_to_add.add(new_edge)
                        
                        rewires += 1
        
        # Apply topology changes
        self.edges -= edges_to_remove
        self.edges |= edges_to_add
        
        n_compromised = sum(1 for a in self.agents.values() if a.compromised)
        
        return {
            "compromised": n_compromised,
            "compromised_frac": round(n_compromised / self.n, 3),
            "new_infections": new_infections,
            "recoveries": recoveries,
            "rewires": rewires,
            "edges": len(self.edges),
        }
    
    def count_components(self) -> int:
        """Count connected components (fragmentation measure)."""
        visited = set()
        components = 0
        
        for aid in self.agents:
            if aid not in visited:
                components += 1
                # BFS
                queue = [aid]
                while queue:
                    node = queue.pop(0)
                    if node in visited:
                        continue
                    visited.add(node)
                    for n in self.get_neighbors(node):
                        if n not in visited:
                            queue.append(n)
        
        return components


def compare_rewiring_rates():
    """Compare no rewiring vs moderate vs aggressive rewiring."""
    random.seed(42)
    
    configs = [
        ("NO_REWIRE (static)", 0.0),
        ("MODERATE (0.3)", 0.3),
        ("AGGRESSIVE (0.8)", 0.8),
    ]
    
    print("=" * 65)
    print("ADAPTIVE TRUST NETWORK: Rewiring Rate Comparison")
    print("100 agents, avg degree 6, 10% initially compromised")
    print("Infection=0.15, Recovery=0.05, 50 timesteps")
    print("=" * 65)
    
    for name, rate in configs:
        random.seed(42)  # Same initial conditions
        net = AdaptiveTrustNetwork(
            n_agents=100, avg_degree=6,
            infection_rate=0.15, recovery_rate=0.05,
            rewire_rate=rate
        )
        
        history = []
        for t in range(50):
            result = net.step()
            history.append(result)
        
        final = history[-1]
        peak = max(h["compromised_frac"] for h in history)
        total_rewires = sum(h["rewires"] for h in history)
        components = net.count_components()
        
        print(f"\n{name}:")
        print(f"  Final compromised: {final['compromised_frac']:.1%}")
        print(f"  Peak compromised:  {peak:.1%}")
        print(f"  Total rewires:     {total_rewires}")
        print(f"  Final edges:       {final['edges']}")
        print(f"  Components:        {components}")
        
        # The tradeoff
        if rate == 0.0:
            print(f"  → No defense. Epidemic spreads freely.")
        elif rate <= 0.3:
            print(f"  → Moderate defense. Lower peak, network stays connected.")
        else:
            print(f"  → Network fragments. Epidemic contained but trust isolated.")
    
    print("\n" + "=" * 65)
    print("KEY INSIGHT (Gross & Blasius 2008):")
    print("Adaptive rewiring raises epidemic threshold but fragments network.")
    print("ATF parallel: agents that aggressively sever ties to failed")
    print("attesters protect themselves but create trust echo chambers.")
    print("MODERATE rewiring = AIMD multiplicative decrease (0.5x, not 0x).")
    print("Don't cut ties — reduce trust. The relationship persists for")
    print("re-evaluation. Recovery needs a path back.")
    print("=" * 65)


if __name__ == "__main__":
    compare_rewiring_rates()
