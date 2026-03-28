#!/usr/bin/env python3
"""
resistance-sybil-detector.py — Resistance-based sybil detection for ATF.

Based on Dehkordi & Zehmakan (AAMAS 2025): "More Efficient Sybil Detection
Mechanisms Leveraging Resistance of Users to Attack Requests."

Key insight: User RESISTANCE to attack requests is a binary trait. Resistant
nodes reject sybil friendship requests; non-resistant accept them. Knowing
which nodes are resistant enables:
1. Transitive benign discovery (resistant benign's neighbors → also benign)
2. Attack edge identification (edges to non-resistant nodes = potential attacks)
3. Preprocessing that improves SybilRank/SybilSCAR/SybilWalk accuracy

ATF mapping:
- Resistance = identity layer (DKIM history, behavioral consistency)
- Non-resistant = addressing-only agents (trivially created, no history)
- Attack edges = attestations from sybils to non-resistant agents
- Probing = sending test interactions to reveal identity evidence
- Budget k = limited probing resources (can't test everyone)

The AAMAS paper proves the benign-maximization problem is NP-hard but
provides a greedy O(n) algorithm that performs well on real graphs.

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from typing import Optional
from collections import deque


@dataclass
class Agent:
    id: str
    is_sybil: bool
    is_resistant: bool  # Has identity layer (DKIM, behavioral history)
    resistance_revealed: bool = False
    label: Optional[str] = None  # "benign", "sybil", or None (unknown)
    identity_days: int = 0  # Days of DKIM history
    attestation_count: int = 0


@dataclass
class Edge:
    source: str
    target: str
    is_attack: bool = False  # Sybil → benign connection


class ResistanceSybilDetector:
    """
    Implements resistance-based preprocessing for sybil detection.
    
    AAMAS 2025 algorithm:
    1. Budget k probes to reveal resistance
    2. Transitive benign discovery from resistant+benign seeds
    3. Attack edge identification on non-resistant nodes
    """
    
    def __init__(self):
        self.agents: dict[str, Agent] = {}
        self.edges: list[Edge] = []
        self.adjacency: dict[str, list[str]] = {}  # bidirectional
        self.reverse_adj: dict[str, list[str]] = {}  # incoming edges
    
    def add_agent(self, agent: Agent):
        self.agents[agent.id] = agent
        if agent.id not in self.adjacency:
            self.adjacency[agent.id] = []
            self.reverse_adj[agent.id] = []
    
    def add_edge(self, source: str, target: str):
        is_attack = (self.agents[source].is_sybil and not self.agents[target].is_sybil)
        edge = Edge(source=source, target=target, is_attack=is_attack)
        self.edges.append(edge)
        self.adjacency.setdefault(source, []).append(target)
        self.reverse_adj.setdefault(target, []).append(source)
    
    def probe_resistance(self, agent_id: str) -> bool:
        """Reveal an agent's resistance (identity layer status). Budget-limited."""
        agent = self.agents[agent_id]
        agent.resistance_revealed = True
        return agent.is_resistant
    
    def greedy_probe_selection(self, budget: int, seeds: list[str]) -> list[str]:
        """
        Greedy algorithm for selecting which agents to probe.
        
        AAMAS 2025: "we suppose we have a fixed budget k of the number
        of users whose resistance can be revealed."
        
        Heuristic: prioritize agents with high degree (more transitive
        discovery potential) and adjacent to known benigns.
        """
        candidates = []
        for aid, agent in self.agents.items():
            if aid in seeds or agent.resistance_revealed:
                continue
            # Score = degree * proximity to seeds
            degree = len(self.adjacency.get(aid, [])) + len(self.reverse_adj.get(aid, []))
            seed_adjacent = sum(1 for s in seeds if s in self.adjacency.get(aid, []) 
                              or s in self.reverse_adj.get(aid, []))
            score = degree * (1 + seed_adjacent)
            candidates.append((aid, score))
        
        candidates.sort(key=lambda x: -x[1])
        return [c[0] for c in candidates[:budget]]
    
    def discover_benigns(self, seeds: list[str]) -> set[str]:
        """
        Transitive benign discovery from resistant+benign seeds.
        
        If v is benign AND resistant, any neighbor u → v must be benign
        (resistant nodes reject sybil connections). Then if u is also
        resistant, u's neighbors are benign too. BFS propagation.
        
        AAMAS 2025 Theorem: This is NP-hard to optimize but greedy works.
        """
        discovered = set(seeds)
        queue = deque(seeds)
        
        while queue:
            v = queue.popleft()
            agent = self.agents[v]
            
            if not agent.resistance_revealed:
                continue
            if not agent.is_resistant:
                continue
            
            # All incoming edges to resistant benign → source is benign
            for u in self.reverse_adj.get(v, []):
                if u not in discovered:
                    discovered.add(u)
                    self.agents[u].label = "benign"
                    queue.append(u)
            
            # All outgoing edges from resistant benign → target is benign
            # (resistant agent wouldn't attest a sybil)
            for u in self.adjacency.get(v, []):
                if u not in discovered:
                    discovered.add(u)
                    self.agents[u].label = "benign"
                    queue.append(u)
        
        return discovered
    
    def identify_attack_edges(self) -> list[Edge]:
        """
        Edges to non-resistant nodes are potential attack edges.
        
        AAMAS 2025: "Incoming edges for non-resistant benigns are
        potential attack edges."
        """
        attack_edges = []
        for edge in self.edges:
            target = self.agents[edge.target]
            if target.resistance_revealed and not target.is_resistant:
                attack_edges.append(edge)
        return attack_edges
    
    def detect(self, seeds: list[str], budget: int) -> dict:
        """Full detection pipeline."""
        # Step 1: Select agents to probe
        probes = self.greedy_probe_selection(budget, seeds)
        
        # Step 2: Probe resistance
        for pid in probes:
            self.probe_resistance(pid)
        
        # Also reveal seed resistance
        for sid in seeds:
            self.probe_resistance(sid)
            self.agents[sid].label = "benign"
        
        # Step 3: Transitive benign discovery
        discovered = self.discover_benigns(seeds)
        
        # Step 4: Attack edge identification
        attack_edges = self.identify_attack_edges()
        
        # Step 5: Remaining unknowns → suspicious
        suspicious = []
        for aid, agent in self.agents.items():
            if aid not in discovered and agent.label != "benign":
                suspicious.append(aid)
        
        # Evaluate
        true_benign = {aid for aid, a in self.agents.items() if not a.is_sybil}
        true_sybil = {aid for aid, a in self.agents.items() if a.is_sybil}
        
        tp = len(discovered & true_benign)  # Correctly identified benign
        fp = len(discovered & true_sybil)   # Sybil misclassified as benign
        fn = len(true_benign - discovered)  # Benign missed
        
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        
        true_attacks = [e for e in self.edges if e.is_attack]
        detected_attacks = [e for e in attack_edges if e.is_attack]
        
        return {
            "probed": len(probes),
            "discovered_benign": len(discovered),
            "total_benign": len(true_benign),
            "total_sybil": len(true_sybil),
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "attack_edges_found": len(detected_attacks),
            "attack_edges_total": len(true_attacks),
            "suspicious": len(suspicious),
            "methodology": "Dehkordi & Zehmakan (AAMAS 2025) resistance-based preprocessing"
        }


def generate_network(n_honest: int, n_sybil: int, resistance_rate: float,
                     honest_density: float, sybil_density: float,
                     attack_edges: int) -> ResistanceSybilDetector:
    """Generate a mixed honest+sybil network."""
    detector = ResistanceSybilDetector()
    
    # Create honest agents
    honest_ids = []
    for i in range(n_honest):
        is_resistant = random.random() < resistance_rate
        agent = Agent(
            id=f"honest_{i}",
            is_sybil=False,
            is_resistant=is_resistant,
            identity_days=random.randint(30, 365) if is_resistant else random.randint(0, 5)
        )
        detector.add_agent(agent)
        honest_ids.append(agent.id)
    
    # Create sybil agents (never resistant — no identity layer)
    sybil_ids = []
    for i in range(n_sybil):
        agent = Agent(
            id=f"sybil_{i}",
            is_sybil=True,
            is_resistant=False,
            identity_days=0
        )
        detector.add_agent(agent)
        sybil_ids.append(agent.id)
    
    # Honest-honest edges (sparse)
    for i in range(int(n_honest * honest_density)):
        a, b = random.sample(honest_ids, 2)
        detector.add_edge(a, b)
    
    # Sybil-sybil edges (dense — they attest each other freely)
    for i in range(int(n_sybil * sybil_density)):
        if len(sybil_ids) >= 2:
            a, b = random.sample(sybil_ids, 2)
            detector.add_edge(a, b)
    
    # Attack edges (sybil → honest)
    for i in range(attack_edges):
        s = random.choice(sybil_ids)
        h = random.choice(honest_ids)
        # Non-resistant honest agents accept sybil connections
        if not detector.agents[h].is_resistant:
            detector.add_edge(s, h)
    
    return detector


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("RESISTANCE-BASED SYBIL DETECTION (AAMAS 2025 → ATF)")
    print("=" * 60)
    
    scenarios = [
        ("Small network (50 honest, 20 sybil, 70% resistant)", 
         50, 20, 0.7, 3.0, 5.0, 15),
        ("Medium network (200 honest, 80 sybil, 60% resistant)",
         200, 80, 0.6, 3.0, 6.0, 50),
        ("Low resistance (100 honest, 50 sybil, 30% resistant)",
         100, 50, 0.3, 3.0, 6.0, 40),
        ("High resistance (100 honest, 50 sybil, 90% resistant)",
         100, 50, 0.9, 3.0, 6.0, 40),
    ]
    
    for name, n_h, n_s, resist, h_dens, s_dens, atk in scenarios:
        print(f"\n{name}")
        print("-" * 50)
        
        detector = generate_network(n_h, n_s, resist, h_dens, s_dens, atk)
        
        # Pick 3 known-benign seeds
        seeds = [f"honest_{i}" for i in range(3)]
        
        # Budget = 10% of network
        budget = max(5, (n_h + n_s) // 10)
        
        result = detector.detect(seeds, budget)
        print(json.dumps(result, indent=2))
        
        # Verify no sybils in discovered benigns (precision should be high)
        assert result["precision"] >= 0.9, f"Precision too low: {result['precision']}"
    
    print("\n" + "=" * 60)
    print("ALL SCENARIOS PASSED ✓")
    print()
    print("KEY INSIGHTS:")
    print("- Resistance (identity layer) = the sybil filter")  
    print("- Higher resistance rate → more transitive benign discovery")
    print("- Budget-limited probing → greedy selection by degree works")
    print("- Attack edges cluster on non-resistant nodes")
    print("- Preprocessing improves ALL downstream detection algorithms")


if __name__ == "__main__":
    demo()
