#!/usr/bin/env python3
"""
sybil-resistance-detector.py — Resistance-based sybil detection for ATF.

Based on Dehkordi & Zehmakan (AAMAS 2025): user RESISTANCE to attack
requests is the missing variable in sybil detection. Graph structure
is a function of attack strategy × resistance, not just homophily.

Key insights from paper:
1. Resistant nodes reject sybil friendship/attestation requests
2. Revealing resistance of k nodes as preprocessing improves
   SybilSCAR/SybilWalk/SybilMetric accuracy
3. If node v is benign+resistant, neighbor u must be benign (since
   v would reject sybils). Cascading discovery.
4. Attack edges = connections between sybil and honest regions.
   Identity layer strength = resistance = attack edge cost.

ATF mapping:
- Resistance = identity layer strength (DKIM chain, behavioral history)
- Agents with strong identity reject bogus attestation requests
- Sybils can't fake resistance because it requires TIME (slow bootstrap)
- Preprocessing: reveal resistance of budget-k agents, discover benigns

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class NodeType(Enum):
    HONEST = "honest"
    SYBIL = "sybil"
    UNKNOWN = "unknown"


@dataclass
class Agent:
    id: str
    true_type: NodeType  # Ground truth (hidden)
    resistance: float    # 0-1, probability of rejecting sybil requests
    identity_days: int   # Days of identity evidence
    connections: set = field(default_factory=set)
    labeled: Optional[NodeType] = None  # Our classification
    resistance_revealed: bool = False


class SybilResistanceDetector:
    """
    Implements resistance-based sybil detection preprocessing.
    
    Algorithm (from AAMAS 2025):
    1. Select k agents to probe (reveal resistance)
    2. High-resistance + known-benign → neighbors are benign (cascading)
    3. Low-resistance agents → incoming edges are potential attack edges
    4. Remove/downweight attack edges → improve detection
    """
    
    RESISTANCE_THRESHOLD = 0.6  # Above = resistant
    IDENTITY_MIN_DAYS = 30      # Minimum for resistance
    
    def __init__(self):
        self.agents: dict[str, Agent] = {}
        self.seed_benigns: set[str] = set()  # Known trusted agents
    
    def add_agent(self, agent: Agent):
        self.agents[agent.id] = agent
    
    def add_connection(self, a_id: str, b_id: str):
        if a_id in self.agents and b_id in self.agents:
            self.agents[a_id].connections.add(b_id)
            self.agents[b_id].connections.add(a_id)
    
    def mark_seed_benign(self, agent_id: str):
        self.seed_benigns.add(agent_id)
        if agent_id in self.agents:
            self.agents[agent_id].labeled = NodeType.HONEST
    
    def compute_resistance(self, agent: Agent) -> float:
        """
        Resistance = f(identity_days, behavioral_consistency).
        Agents with strong identity history resist sybil attestation requests.
        Maps to ATF: identity layer strength IS resistance.
        """
        # Time-based resistance: longer history = more resistant
        time_factor = min(1.0, agent.identity_days / 90)
        # Inherent resistance (some agents more cautious)
        return agent.resistance * time_factor
    
    def select_probe_targets(self, budget_k: int) -> list[str]:
        """
        Greedy selection: probe agents that maximize benign discovery.
        
        AAMAS 2025: "How many new benigns can be discovered if we are 
        allowed to reveal the resistance of k nodes?"
        
        Heuristic: prioritize high-degree agents adjacent to seeds.
        """
        candidates = []
        for aid, agent in self.agents.items():
            if agent.resistance_revealed or agent.labeled is not None:
                continue
            # Score: degree × proximity to seeds
            seed_neighbors = len(agent.connections & self.seed_benigns)
            degree = len(agent.connections)
            score = degree * (1 + seed_neighbors)
            candidates.append((aid, score))
        
        candidates.sort(key=lambda x: -x[1])
        return [aid for aid, _ in candidates[:budget_k]]
    
    def reveal_resistance(self, agent_id: str):
        """Probe an agent to determine resistance level."""
        agent = self.agents[agent_id]
        agent.resistance_revealed = True
    
    def cascade_benign_discovery(self) -> dict:
        """
        Core AAMAS 2025 insight: if v is benign AND resistant,
        then v's neighbors are benign (v would reject sybil connections).
        Cascade until no more discoveries.
        """
        discovered = 0
        attack_edges = []
        changed = True
        
        while changed:
            changed = False
            for aid, agent in self.agents.items():
                if agent.labeled != NodeType.HONEST:
                    continue
                if not agent.resistance_revealed:
                    continue
                
                effective_resistance = self.compute_resistance(agent)
                
                if effective_resistance >= self.RESISTANCE_THRESHOLD:
                    # High resistance + benign → neighbors are benign
                    for neighbor_id in agent.connections:
                        neighbor = self.agents[neighbor_id]
                        if neighbor.labeled is None:
                            neighbor.labeled = NodeType.HONEST
                            discovered += 1
                            changed = True
                else:
                    # Low resistance → incoming edges may be attack edges
                    for neighbor_id in agent.connections:
                        neighbor = self.agents[neighbor_id]
                        if neighbor.labeled is None:
                            attack_edges.append((neighbor_id, aid))
        
        return {
            "benigns_discovered": discovered,
            "potential_attack_edges": len(attack_edges),
            "attack_edges": attack_edges[:10]  # Sample
        }
    
    def classify_remaining(self) -> dict:
        """Label remaining unknowns based on graph position."""
        # Agents connected mostly to sybil-region = likely sybil
        for aid, agent in self.agents.items():
            if agent.labeled is not None:
                continue
            
            benign_neighbors = sum(
                1 for n in agent.connections
                if self.agents[n].labeled == NodeType.HONEST
            )
            total = len(agent.connections)
            if total == 0:
                agent.labeled = NodeType.UNKNOWN
            elif benign_neighbors / total > 0.5:
                agent.labeled = NodeType.HONEST
            else:
                agent.labeled = NodeType.SYBIL
        
        return self.evaluate()
    
    def evaluate(self) -> dict:
        """Compare labels to ground truth."""
        tp = fp = tn = fn = 0
        for agent in self.agents.values():
            if agent.true_type == NodeType.HONEST:
                if agent.labeled == NodeType.HONEST:
                    tn += 1
                else:
                    fn += 1
            elif agent.true_type == NodeType.SYBIL:
                if agent.labeled == NodeType.SYBIL:
                    tp += 1
                else:
                    fp += 1
        
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 0.001)
        accuracy = (tp + tn) / max(tp + fp + tn + fn, 1)
        
        return {
            "accuracy": round(accuracy, 3),
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn
        }


def build_test_network(n_honest=50, n_sybil=20, n_attack_edges=8):
    """Build a network with honest region, sybil region, and attack edges."""
    random.seed(42)
    detector = SybilResistanceDetector()
    
    # Honest agents: sparse connections, high resistance, long history
    honest_ids = [f"honest_{i}" for i in range(n_honest)]
    for hid in honest_ids:
        detector.add_agent(Agent(
            id=hid, true_type=NodeType.HONEST,
            resistance=random.uniform(0.6, 0.95),
            identity_days=random.randint(30, 180)
        ))
    
    # Honest connections: sparse (avg degree ~5)
    for i in range(n_honest):
        n_conns = random.randint(2, 8)
        targets = random.sample(honest_ids, min(n_conns, n_honest - 1))
        for t in targets:
            if t != honest_ids[i]:
                detector.add_connection(honest_ids[i], t)
    
    # Sybil agents: dense connections, low resistance, no history
    sybil_ids = [f"sybil_{i}" for i in range(n_sybil)]
    for sid in sybil_ids:
        detector.add_agent(Agent(
            id=sid, true_type=NodeType.SYBIL,
            resistance=random.uniform(0.0, 0.3),
            identity_days=random.randint(0, 5)
        ))
    
    # Sybil connections: dense (mutual inflation)
    for i in range(n_sybil):
        for j in range(i + 1, n_sybil):
            if random.random() < 0.7:  # Dense!
                detector.add_connection(sybil_ids[i], sybil_ids[j])
    
    # Attack edges: sybils → honest (limited by resistance)
    for _ in range(n_attack_edges):
        s = random.choice(sybil_ids)
        h = random.choice(honest_ids)
        detector.add_connection(s, h)
    
    return detector, honest_ids, sybil_ids


def demo():
    print("=" * 60)
    print("SYBIL RESISTANCE DETECTOR (AAMAS 2025 approach)")
    print("=" * 60)
    print()
    
    detector, honest_ids, sybil_ids = build_test_network()
    
    print(f"Network: {len(honest_ids)} honest, {len(sybil_ids)} sybil")
    
    # Seed: 3 known-benign agents
    seeds = random.sample(honest_ids, 3)
    for s in seeds:
        detector.mark_seed_benign(s)
    print(f"Seeds: {len(seeds)} known-benign agents")
    
    # Phase 1: Select probe targets (budget = 10)
    budget = 10
    targets = detector.select_probe_targets(budget)
    print(f"Probe budget: {budget}")
    print(f"Selected targets: {len(targets)}")
    
    # Phase 2: Reveal resistance (also reveal seeds)
    for s in seeds:
        detector.reveal_resistance(s)
    for t in targets:
        detector.reveal_resistance(t)
    
    # Phase 3: Cascade benign discovery
    cascade = detector.cascade_benign_discovery()
    print(f"\nCascade results:")
    print(f"  Benigns discovered: {cascade['benigns_discovered']}")
    print(f"  Potential attack edges: {cascade['potential_attack_edges']}")
    
    # Phase 4: Classify remaining
    results = detector.classify_remaining()
    print(f"\nFinal classification:")
    print(json.dumps(results, indent=2))
    
    # Compare: without resistance preprocessing
    print("\n" + "=" * 60)
    print("COMPARISON: Without resistance preprocessing")
    print("=" * 60)
    
    detector2, _, _ = build_test_network()
    for s in seeds:
        detector2.mark_seed_benign(s)
    # Skip probing — go straight to classification
    results2 = detector2.classify_remaining()
    print(json.dumps(results2, indent=2))
    
    improvement = results["f1"] - results2["f1"]
    print(f"\nF1 improvement with resistance probing: +{improvement:.3f}")
    print(f"Accuracy improvement: +{results['accuracy'] - results2['accuracy']:.3f}")
    
    print()
    print("KEY: Resistance preprocessing (probing {budget} agents) improves")
    print("sybil detection by cascading benign discovery from resistant nodes.")
    print("ATF parallel: identity layer strength IS resistance.")
    print("Slow bootstrap (90d) = resistance that sybils can't parallelize.")


if __name__ == "__main__":
    demo()
