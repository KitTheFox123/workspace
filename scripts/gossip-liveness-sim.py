#!/usr/bin/env python3
"""gossip-liveness-sim.py — Gossip protocol simulation for agent liveness detection.

Compares gossip-based vs registry-based liveness in agent networks.
Measures: convergence time, message overhead, partition tolerance.

Build action for 2026-03-07 heartbeat.
"""

import random
import statistics
from dataclasses import dataclass, field

@dataclass
class Agent:
    id: int
    alive: bool = True
    known_dead: set = field(default_factory=set)
    known_alive: set = field(default_factory=set)
    heartbeat_count: int = 0

class GossipNetwork:
    def __init__(self, n_agents: int, fanout: int = 3):
        self.agents = {i: Agent(id=i) for i in range(n_agents)}
        self.fanout = fanout
        self.total_messages = 0
        self.rounds = 0
        
    def kill_agent(self, agent_id: int):
        self.agents[agent_id].alive = False
        
    def gossip_round(self):
        """Each alive agent gossips with `fanout` random peers."""
        self.rounds += 1
        alive_agents = [a for a in self.agents.values() if a.alive]
        
        for agent in alive_agents:
            agent.heartbeat_count += 1
            peers = random.sample(
                [a for a in alive_agents if a.id != agent.id],
                min(self.fanout, len(alive_agents) - 1)
            )
            for peer in peers:
                self.total_messages += 1
                # Exchange known-dead sets
                peer.known_dead |= agent.known_dead
                agent.known_dead |= peer.known_dead
                # Exchange liveness
                peer.known_alive.add(agent.id)
                agent.known_alive.add(peer.id)
        
        # Detect dead agents: if not seen in known_alive after round
        for agent in alive_agents:
            for other_id, other in self.agents.items():
                if not other.alive and other_id not in agent.known_dead:
                    # Probabilistic detection: if enough peers report absence
                    reporters = sum(
                        1 for a in alive_agents 
                        if other_id not in a.known_alive and a.id != agent.id
                    )
                    if reporters >= self.fanout:
                        agent.known_dead.add(other_id)
    
    def convergence_check(self, dead_id: int) -> float:
        """What fraction of alive agents know about the dead agent?"""
        alive = [a for a in self.agents.values() if a.alive]
        if not alive:
            return 0.0
        return sum(1 for a in alive if dead_id in a.known_dead) / len(alive)


class RegistryNetwork:
    def __init__(self, n_agents: int, heartbeat_interval: int = 1):
        self.agents = {i: Agent(id=i) for i in range(n_agents)}
        self.registry_alive = set(range(n_agents))
        self.total_messages = 0
        self.rounds = 0
        self.heartbeat_interval = heartbeat_interval
        self.missed_heartbeats: dict[int, int] = {i: 0 for i in range(n_agents)}
        self.threshold = 3  # miss 3 heartbeats = declared dead
        
    def kill_agent(self, agent_id: int):
        self.agents[agent_id].alive = False
        
    def heartbeat_round(self):
        self.rounds += 1
        for agent in self.agents.values():
            if agent.alive:
                self.total_messages += 1  # heartbeat to registry
                self.missed_heartbeats[agent.id] = 0
            else:
                self.missed_heartbeats[agent.id] += 1
                if self.missed_heartbeats[agent.id] >= self.threshold:
                    self.registry_alive.discard(agent.id)
    
    def convergence_check(self, dead_id: int) -> float:
        """Registry is centralized — either everyone knows or nobody does."""
        return 0.0 if dead_id in self.registry_alive else 1.0


def run_comparison(n_agents: int = 50, fanout: int = 3, trials: int = 100):
    print(f"=== Gossip vs Registry Liveness Detection ===")
    print(f"Agents: {n_agents}, Fanout: {fanout}, Trials: {trials}\n")
    
    gossip_convergence_rounds = []
    gossip_messages = []
    registry_convergence_rounds = []
    registry_messages = []
    
    for _ in range(trials):
        # Gossip
        gn = GossipNetwork(n_agents, fanout)
        dead_id = random.randint(0, n_agents - 1)
        gn.kill_agent(dead_id)
        
        for r in range(50):
            gn.gossip_round()
            if gn.convergence_check(dead_id) >= 0.95:
                gossip_convergence_rounds.append(r + 1)
                gossip_messages.append(gn.total_messages)
                break
        else:
            gossip_convergence_rounds.append(50)
            gossip_messages.append(gn.total_messages)
        
        # Registry
        rn = RegistryNetwork(n_agents)
        rn.kill_agent(dead_id)
        
        for r in range(50):
            rn.heartbeat_round()
            if rn.convergence_check(dead_id) >= 0.95:
                registry_convergence_rounds.append(r + 1)
                registry_messages.append(rn.total_messages)
                break
        else:
            registry_convergence_rounds.append(50)
            registry_messages.append(rn.total_messages)
    
    print("GOSSIP PROTOCOL:")
    print(f"  Convergence: {statistics.mean(gossip_convergence_rounds):.1f} rounds (median {statistics.median(gossip_convergence_rounds):.0f})")
    print(f"  Messages: {statistics.mean(gossip_messages):.0f} (median {statistics.median(gossip_messages):.0f})")
    print(f"  Messages/round/agent: {statistics.mean(gossip_messages) / (statistics.mean(gossip_convergence_rounds) * n_agents):.1f}")
    
    print("\nREGISTRY (centralized):")
    print(f"  Convergence: {statistics.mean(registry_convergence_rounds):.1f} rounds (always {rn.threshold})")
    print(f"  Messages: {statistics.mean(registry_messages):.0f}")
    print(f"  Messages/round/agent: 1.0 (heartbeat only)")
    
    print("\nTRADEOFFS:")
    g_msg = statistics.mean(gossip_messages)
    r_msg = statistics.mean(registry_messages)
    print(f"  Gossip uses {g_msg/r_msg:.1f}x more messages")
    print(f"  But: no single point of failure")
    print(f"  Registry detects in exactly {rn.threshold} rounds (deterministic)")
    print(f"  Gossip detects in ~{statistics.mean(gossip_convergence_rounds):.0f} rounds (probabilistic)")
    
    # Partition tolerance test
    print("\n=== PARTITION TOLERANCE ===")
    gn2 = GossipNetwork(n_agents, fanout)
    # Kill the "registry" equivalent — first 3 agents
    for i in range(3):
        gn2.kill_agent(i)
    # Kill target
    gn2.kill_agent(10)
    
    for r in range(20):
        gn2.gossip_round()
    
    conv = gn2.convergence_check(10)
    print(f"  Gossip after losing 3 nodes + target: {conv*100:.0f}% convergence")
    print(f"  Registry after losing registry: 0% (total failure)")


if __name__ == "__main__":
    run_comparison()
