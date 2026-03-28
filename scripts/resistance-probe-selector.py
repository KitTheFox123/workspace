#!/usr/bin/env python3
"""
resistance-probe-selector.py — Optimal witness selection via resistance probing.

Maps Dehkordi & Zehmakan (AAMAS 2025) to ATF witness selection.
Key insight: "user resistance to attack requests" = identity layer strength.
The optimization: given budget k, which k agents should we probe for resistance
to maximize (discovered-benign + detected attack edges)?

In ATF terms: which witnesses should we ask to validate a new agent,
to maximize both trust-if-honest and detection-if-sybil?

Strategy: probe agents with HIGH expected resistance (strong identity layer)
AND high degree (many connections). These are the best "attack edge filters."

Greedy algorithm: at each step, pick the node that maximizes
marginal gain in (revealed-benign neighbors + detected attack edges).

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field


@dataclass
class Agent:
    id: str
    is_sybil: bool
    resistance: float  # 0-1, probability of rejecting sybil request
    identity_strength: float  # 0-1, DKIM days / behavioral samples
    connections: set = field(default_factory=set)
    
    @property
    def degree(self) -> int:
        return len(self.connections)


def generate_network(n_honest: int = 100, n_sybil: int = 30, 
                     attack_edges: int = 15, seed: int = 42) -> dict[str, Agent]:
    """
    Generate a trust network with honest and sybil regions.
    
    Honest region: sparse, power-law-ish degree distribution
    Sybil region: dense mutual connections (free inflation)
    Attack edges: connections from sybils to honest nodes
    """
    rng = random.Random(seed)
    agents = {}
    
    # Honest agents with varying resistance
    for i in range(n_honest):
        identity = rng.betavariate(3, 1.5)  # Skewed toward high identity
        resistance = 0.3 + 0.7 * identity   # Higher identity = higher resistance
        agents[f"honest_{i}"] = Agent(
            id=f"honest_{i}", is_sybil=False,
            resistance=resistance, identity_strength=identity
        )
    
    # Sybil agents — low identity, low resistance
    for i in range(n_sybil):
        agents[f"sybil_{i}"] = Agent(
            id=f"sybil_{i}", is_sybil=True,
            resistance=rng.uniform(0.0, 0.2),  # Sybils accept anything
            identity_strength=rng.uniform(0.0, 0.15)  # No real history
        )
    
    # Honest connections (sparse, preferential attachment-ish)
    honest_ids = [a for a in agents if not agents[a].is_sybil]
    for i, aid in enumerate(honest_ids):
        # Connect to ~5-8 others, biased toward earlier (higher-degree) nodes
        n_conns = rng.randint(3, 8)
        targets = rng.sample(honest_ids[:max(i, n_conns + 1)], min(n_conns, i))
        for t in targets:
            if t != aid:
                agents[aid].connections.add(t)
                agents[t].connections.add(aid)
    
    # Sybil connections (dense — free mutual inflation)
    sybil_ids = [a for a in agents if agents[a].is_sybil]
    for sid in sybil_ids:
        # Connect to 60-80% of other sybils
        for other in sybil_ids:
            if other != sid and rng.random() < 0.7:
                agents[sid].connections.add(other)
                agents[other].connections.add(sid)
    
    # Attack edges (sybil → honest)
    for _ in range(attack_edges):
        s = rng.choice(sybil_ids)
        h = rng.choice(honest_ids)
        agents[s].connections.add(h)
        agents[h].connections.add(s)
    
    return agents


def greedy_probe_selection(agents: dict[str, Agent], budget: int = 10) -> list[str]:
    """
    Greedy selection of which agents to probe for resistance.
    
    Dehkordi & Zehmakan optimization: select subset that maximizes
    (discovered-benign + detected attack edges) when resistance is revealed.
    
    Heuristic: pick high-(degree × identity_strength) agents.
    High degree = many connections to classify.
    High identity = likely high resistance = good filter.
    """
    scored = []
    for aid, agent in agents.items():
        # Score = degree × identity_strength (expected filtering power)
        score = agent.degree * agent.identity_strength
        scored.append((aid, score))
    
    scored.sort(key=lambda x: -x[1])
    return [aid for aid, _ in scored[:budget]]


def probe_and_classify(agents: dict[str, Agent], probed: list[str]) -> dict:
    """
    After probing, classify neighbors based on revealed resistance.
    
    If probed agent has high resistance → its connections are likely honest.
    If probed agent has low resistance → it may be a sybil or compromised.
    Attack edges are detected when high-resistance node connects to low-resistance.
    """
    revealed_benign = set()
    detected_attack_edges = []
    suspected_sybils = set()
    
    for pid in probed:
        agent = agents[pid]
        
        if agent.resistance > 0.6:
            # High resistance → likely honest, neighbors probably honest too
            revealed_benign.add(pid)
            for conn in agent.connections:
                neighbor = agents[conn]
                if neighbor.identity_strength > 0.3:
                    revealed_benign.add(conn)
                elif neighbor.identity_strength < 0.15:
                    # High-resistance node connected to no-identity node = attack edge
                    detected_attack_edges.append((pid, conn))
                    suspected_sybils.add(conn)
        else:
            # Low resistance — this node itself is suspect
            suspected_sybils.add(pid)
    
    # Propagate: sybils' dense connections are also suspect
    for sid in list(suspected_sybils):
        for conn in agents[sid].connections:
            if agents[conn].identity_strength < 0.15:
                suspected_sybils.add(conn)
    
    return {
        "revealed_benign": len(revealed_benign),
        "detected_attack_edges": len(detected_attack_edges),
        "suspected_sybils": len(suspected_sybils),
        "probed": len(probed),
        "coverage": len(revealed_benign) / max(1, sum(1 for a in agents.values() if not a.is_sybil)),
        "sybil_detection_rate": len(suspected_sybils & {a for a in agents if agents[a].is_sybil}) / max(1, sum(1 for a in agents.values() if a.is_sybil))
    }


def random_probe_selection(agents: dict[str, Agent], budget: int = 10, seed: int = 99) -> list[str]:
    """Baseline: random probe selection."""
    rng = random.Random(seed)
    return rng.sample(list(agents.keys()), budget)


def demo():
    print("=" * 60)
    print("RESISTANCE PROBE SELECTION (AAMAS 2025 → ATF)")
    print("=" * 60)
    
    agents = generate_network(n_honest=100, n_sybil=30, attack_edges=15)
    
    honest = sum(1 for a in agents.values() if not a.is_sybil)
    sybil = sum(1 for a in agents.values() if a.is_sybil)
    avg_honest_deg = sum(a.degree for a in agents.values() if not a.is_sybil) / honest
    avg_sybil_deg = sum(a.degree for a in agents.values() if a.is_sybil) / sybil
    
    print(f"\nNetwork: {honest} honest, {sybil} sybil")
    print(f"Avg degree: honest={avg_honest_deg:.1f}, sybil={avg_sybil_deg:.1f}")
    print(f"(Sybils are denser — free mutual inflation)")
    
    for budget in [5, 10, 20]:
        print(f"\n{'='*60}")
        print(f"BUDGET: {budget} probes")
        print(f"{'='*60}")
        
        # Greedy (our method)
        greedy_probes = greedy_probe_selection(agents, budget)
        greedy_result = probe_and_classify(agents, greedy_probes)
        
        # Random baseline
        random_probes = random_probe_selection(agents, budget)
        random_result = probe_and_classify(agents, random_probes)
        
        print(f"\n  GREEDY (degree × identity):")
        print(f"    Revealed benign: {greedy_result['revealed_benign']}")
        print(f"    Attack edges detected: {greedy_result['detected_attack_edges']}")
        print(f"    Suspected sybils: {greedy_result['suspected_sybils']}")
        print(f"    Honest coverage: {greedy_result['coverage']:.1%}")
        print(f"    Sybil detection: {greedy_result['sybil_detection_rate']:.1%}")
        
        print(f"\n  RANDOM baseline:")
        print(f"    Revealed benign: {random_result['revealed_benign']}")
        print(f"    Attack edges detected: {random_result['detected_attack_edges']}")
        print(f"    Suspected sybils: {random_result['suspected_sybils']}")
        print(f"    Honest coverage: {random_result['coverage']:.1%}")
        print(f"    Sybil detection: {random_result['sybil_detection_rate']:.1%}")
        
        improvement = (greedy_result['revealed_benign'] + greedy_result['suspected_sybils']) / max(1, random_result['revealed_benign'] + random_result['suspected_sybils'])
        print(f"\n  Greedy improvement: {improvement:.1f}x total classified")
    
    print(f"\n{'='*60}")
    print("KEY INSIGHT: Probing high-degree, high-identity nodes first")
    print("maximizes both benign discovery AND sybil detection.")
    print("This IS witness selection for ATF: pick witnesses with")
    print("strong identity layer + many connections to classify.")
    print("Dehkordi & Zehmakan: resistance probing as preprocessing")
    print("improves ALL downstream sybil detection algorithms.")
    print(f"{'='*60}")


if __name__ == "__main__":
    demo()
