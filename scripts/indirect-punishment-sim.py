#!/usr/bin/env python3
"""
indirect-punishment-sim.py — Wen et al (PLoS CompBio 2025) indirect punishment
for agent trust networks.

Key insight: "I punish those who defect against you" outperforms direct punishment
in structured populations. Second-order defectors (those who harm your neighbors)
get punished WITHOUT needing to identify the original violator.

Maps to agent trust:
- Direct punishment = blacklist agents who cheat YOU (requires detection)
- Indirect punishment = reduce trust of agents who cooperate with known cheaters
  (requires only gossip, not detection)

Receipt chains ARE indirect punishment: publish bad receipts, let others avoid.

Usage:
    python3 indirect-punishment-sim.py
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple
from collections import defaultdict


@dataclass
class Agent:
    id: str
    strategy: str  # "cooperate", "defect", "punisher_direct", "punisher_indirect"
    trust_score: float = 50.0
    payoff: float = 0.0
    receipts: List[dict] = field(default_factory=list)
    known_defectors: Set[str] = field(default_factory=set)


class IndirectPunishmentNetwork:
    def __init__(self, agents: List[Agent], neighbors: Dict[str, List[str]]):
        self.agents = {a.id: a for a in agents}
        self.neighbors = neighbors  # adjacency list
        self.round = 0
        self.cooperation_history = []

    def play_round(self):
        """One round: interact with neighbors, then punish."""
        self.round += 1
        round_actions = {}

        # Stage 1: Interact with direct neighbors
        for agent_id, agent in self.agents.items():
            for neighbor_id in self.neighbors.get(agent_id, []):
                if agent.strategy in ("cooperate", "punisher_direct", "punisher_indirect"):
                    action = "cooperate"
                elif agent.strategy == "defect":
                    action = "defect"
                else:
                    action = "cooperate"

                round_actions[(agent_id, neighbor_id)] = action

        # Calculate payoffs from interactions
        for (a, b), action_a in round_actions.items():
            action_b = round_actions.get((b, a), "cooperate")
            if action_a == "cooperate" and action_b == "cooperate":
                self.agents[a].payoff += 3  # mutual cooperation
            elif action_a == "cooperate" and action_b == "defect":
                self.agents[a].payoff -= 1  # sucker's payoff
                self.agents[b].payoff += 5  # temptation
            elif action_a == "defect" and action_b == "cooperate":
                self.agents[a].payoff += 5
                self.agents[b].payoff -= 1
            # mutual defect: 0

        # Stage 2: Punishment
        for agent_id, agent in self.agents.items():
            if agent.strategy == "punisher_direct":
                # Punish direct neighbors who defected against me
                for n_id in self.neighbors.get(agent_id, []):
                    if round_actions.get((n_id, agent_id)) == "defect":
                        self.agents[n_id].payoff -= 3  # fine
                        agent.payoff -= 1  # cost of punishing
                        agent.known_defectors.add(n_id)
                        agent.receipts.append({
                            "round": self.round, "type": "direct_punishment",
                            "target": n_id, "reason": "defected_against_me"
                        })

            elif agent.strategy == "punisher_indirect":
                # Punish second-order defectors (neighbors of neighbors who defect)
                for n_id in self.neighbors.get(agent_id, []):
                    for nn_id in self.neighbors.get(n_id, []):
                        if nn_id != agent_id and round_actions.get((nn_id, n_id)) == "defect":
                            self.agents[nn_id].payoff -= 3
                            agent.payoff -= 0.5  # lower cost (Wen et al)
                            agent.known_defectors.add(nn_id)
                            agent.receipts.append({
                                "round": self.round, "type": "indirect_punishment",
                                "target": nn_id, "reason": f"defected_against_{n_id}"
                            })

        # Gossip: share known_defectors with neighbors
        for agent_id, agent in self.agents.items():
            for n_id in self.neighbors.get(agent_id, []):
                neighbor = self.agents[n_id]
                neighbor.known_defectors |= agent.known_defectors

        # Track cooperation rate
        total = len(round_actions)
        coop = sum(1 for a in round_actions.values() if a == "cooperate")
        self.cooperation_history.append(coop / total if total > 0 else 0)

    def summary(self) -> dict:
        payoffs = {a.id: round(a.payoff, 1) for a in self.agents.values()}
        receipts = {a.id: len(a.receipts) for a in self.agents.values()
                    if len(a.receipts) > 0}
        known = {a.id: list(a.known_defectors) for a in self.agents.values()
                 if a.known_defectors}
        return {
            "rounds": self.round,
            "cooperation_rate": round(self.cooperation_history[-1], 3) if self.cooperation_history else 0,
            "avg_cooperation": round(sum(self.cooperation_history) / len(self.cooperation_history), 3),
            "payoffs": payoffs,
            "receipts_issued": receipts,
            "gossip_spread": {k: len(v) for k, v in known.items()},
        }


def build_grid(n: int, agents: List[Agent]) -> Dict[str, List[str]]:
    """Build a simple grid neighborhood (4-connected)."""
    neighbors = defaultdict(list)
    ids = [a.id for a in agents]
    for i in range(n):
        for j in range(n):
            idx = i * n + j
            if idx >= len(ids):
                break
            for di, dj in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                ni, nj = i + di, j + dj
                if 0 <= ni < n and 0 <= nj < n:
                    nidx = ni * n + nj
                    if nidx < len(ids):
                        neighbors[ids[idx]].append(ids[nidx])
    return dict(neighbors)


def demo():
    print("=" * 60)
    print("INDIRECT PUNISHMENT SIMULATOR")
    print("Wen et al (PLoS CompBio 2025)")
    print("\"I punish those who defect against you\"")
    print("=" * 60)

    random.seed(42)

    # Scenario 1: Direct punishment only
    print("\n--- Scenario 1: Direct Punishment ---")
    agents1 = [
        Agent("c1", "cooperate"), Agent("c2", "cooperate"),
        Agent("c3", "cooperate"), Agent("d1", "defect"),
        Agent("p1", "punisher_direct"), Agent("p2", "punisher_direct"),
        Agent("c4", "cooperate"), Agent("d2", "defect"),
        Agent("c5", "cooperate"),
    ]
    net1 = IndirectPunishmentNetwork(agents1, build_grid(3, agents1))
    for _ in range(10):
        net1.play_round()
    s1 = net1.summary()
    print(f"  Cooperation rate: {s1['avg_cooperation']}")
    print(f"  Defector payoffs: d1={s1['payoffs'].get('d1', 0)}, d2={s1['payoffs'].get('d2', 0)}")
    print(f"  Punisher payoffs: p1={s1['payoffs'].get('p1', 0)}, p2={s1['payoffs'].get('p2', 0)}")
    print(f"  Receipts issued: {s1['receipts_issued']}")

    # Scenario 2: Indirect punishment
    print("\n--- Scenario 2: Indirect Punishment ---")
    agents2 = [
        Agent("c1", "cooperate"), Agent("c2", "cooperate"),
        Agent("c3", "cooperate"), Agent("d1", "defect"),
        Agent("p1", "punisher_indirect"), Agent("p2", "punisher_indirect"),
        Agent("c4", "cooperate"), Agent("d2", "defect"),
        Agent("c5", "cooperate"),
    ]
    net2 = IndirectPunishmentNetwork(agents2, build_grid(3, agents2))
    for _ in range(10):
        net2.play_round()
    s2 = net2.summary()
    print(f"  Cooperation rate: {s2['avg_cooperation']}")
    print(f"  Defector payoffs: d1={s2['payoffs'].get('d1', 0)}, d2={s2['payoffs'].get('d2', 0)}")
    print(f"  Punisher payoffs: p1={s2['payoffs'].get('p1', 0)}, p2={s2['payoffs'].get('p2', 0)}")
    print(f"  Receipts issued: {s2['receipts_issued']}")

    # Compare
    print("\n--- COMPARISON ---")
    d1_direct = s1['payoffs'].get('d1', 0)
    d1_indirect = s2['payoffs'].get('d1', 0)
    p1_direct = s1['payoffs'].get('p1', 0)
    p1_indirect = s2['payoffs'].get('p1', 0)

    print(f"  Defector d1: direct={d1_direct}, indirect={d1_indirect}")
    print(f"  Punisher p1: direct={p1_direct}, indirect={p1_indirect}")
    print(f"  Indirect punishment cost to punisher: LOWER (0.5 vs 1.0)")
    print(f"  Indirect punishment fine to defector: SAME (3.0)")
    print(f"  Gossip spread (indirect): {s2['gossip_spread']}")

    print("\n--- KEY INSIGHT (Wen et al 2025) ---")
    print("Direct: I detect + I punish. Requires identification.")
    print("Indirect: You detect + I punish. Requires only gossip.")
    print("Receipt chains = gossip layer. Publish bad receipts,")
    print("let the network punish without needing central detection.")
    print("santaclawd: works in bimodal audit — no continuous observation needed.")


if __name__ == "__main__":
    demo()
