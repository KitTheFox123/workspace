#!/usr/bin/env python3
"""
sybil-random-walk.py — Random walk sybil detection for ATF attestation graphs.

Core insight from Alvisi et al (IEEE S&P 2013, SoK: The Evolution of Sybil
Defense via Social Networks): random walks from honest nodes get TRAPPED
in dense sybil regions because attack edges (honest→sybil connections) are
scarce. Honest regions are sparse; sybil regions are dense (mutual inflation).

SybilGuard (Yu 2006): O(√n·log n) sybils per attack edge.
SybilRank (Cao 2012): PageRank-style propagation, trust decays per hop.

ATF mapping:
- Nodes = agents
- Edges = attestations (weighted by score)
- Attack edges = dishonest attestations from honest→sybil
- Random walk from trusted seed → probability mass stays in honest region
- Sybil ring has high internal density but few attack edges → walk rarely enters

Usage: Build attestation graph, seed with known-honest nodes, run random walks.
Agents with low landing probability = likely sybil.

Kit 🦊 — 2026-03-28
"""

import random
import json
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class AttestationEdge:
    source: str
    target: str
    score: float  # 0-1
    action_class: str = "ATTEST"


class AttestationGraph:
    def __init__(self):
        self.edges: list[AttestationEdge] = []
        self.adj: dict[str, list[tuple[str, float]]] = defaultdict(list)
        self.nodes: set[str] = set()
    
    def add_edge(self, source: str, target: str, score: float, action_class: str = "ATTEST"):
        edge = AttestationEdge(source, target, score, action_class)
        self.edges.append(edge)
        self.adj[source].append((target, score))
        # Bidirectional for random walk (attestation = mutual relationship)
        self.adj[target].append((source, score))
        self.nodes.add(source)
        self.nodes.add(target)
    
    def degree(self, node: str) -> int:
        return len(self.adj.get(node, []))
    
    def density(self, node_set: set[str]) -> float:
        """Internal edge density of a node set."""
        if len(node_set) < 2:
            return 0.0
        internal = 0
        for edge in self.edges:
            if edge.source in node_set and edge.target in node_set:
                internal += 1
        max_edges = len(node_set) * (len(node_set) - 1) / 2
        return internal / max_edges if max_edges > 0 else 0.0


def random_walk(graph: AttestationGraph, start: str, steps: int = 100) -> dict[str, int]:
    """
    Random walk from start node. At each step, move to a neighbor
    with probability proportional to edge weight (attestation score).
    Returns visit counts per node.
    """
    visits: dict[str, int] = defaultdict(int)
    current = start
    
    for _ in range(steps):
        visits[current] += 1
        neighbors = graph.adj.get(current, [])
        if not neighbors:
            break
        
        # Weight-proportional transition
        targets, weights = zip(*neighbors)
        total = sum(weights)
        probs = [w / total for w in weights]
        current = random.choices(targets, weights=probs, k=1)[0]
    
    return dict(visits)


def sybil_rank(graph: AttestationGraph, seeds: set[str], 
               walks_per_seed: int = 50, steps_per_walk: int = 20) -> dict[str, float]:
    """
    SybilRank-style detection: run many short random walks from trusted seeds.
    Nodes with low landing probability = likely sybil.
    
    Short walks (√log n steps) ensure walk doesn't escape honest region
    through rare attack edges.
    """
    total_visits: dict[str, int] = defaultdict(int)
    total_steps = 0
    
    for seed in seeds:
        for _ in range(walks_per_seed):
            visits = random_walk(graph, seed, steps=steps_per_walk)
            for node, count in visits.items():
                total_visits[node] += count
                total_steps += count
    
    # Normalize to probability
    trust_scores = {}
    for node in graph.nodes:
        trust_scores[node] = total_visits.get(node, 0) / max(total_steps, 1)
    
    return trust_scores


def detect_sybils(graph: AttestationGraph, seeds: set[str],
                  threshold: float = 0.01) -> dict:
    """
    Full sybil detection pipeline.
    
    1. Run SybilRank from trusted seeds
    2. Classify nodes by trust score
    3. Report density metrics for detected clusters
    """
    scores = sybil_rank(graph, seeds)
    
    honest = set()
    suspicious = set()
    sybil = set()
    
    for node, score in scores.items():
        if node in seeds:
            honest.add(node)
        elif score >= threshold:
            honest.add(node)
        elif score >= threshold * 0.3:
            suspicious.add(node)
        else:
            sybil.add(node)
    
    return {
        "honest": sorted(honest),
        "suspicious": sorted(suspicious),
        "sybil": sorted(sybil),
        "scores": {k: round(v, 6) for k, v in sorted(scores.items(), key=lambda x: -x[1])},
        "honest_density": round(graph.density(honest), 4),
        "sybil_density": round(graph.density(sybil), 4),
        "attack_edges": sum(1 for e in graph.edges 
                          if (e.source in honest and e.target in sybil) or
                             (e.source in sybil and e.target in honest)),
        "methodology": "SybilRank (Cao 2012) via short random walks from trusted seeds. "
                       "Dense sybil regions trap walks; sparse honest regions let them diffuse."
    }


def demo():
    random.seed(42)
    
    g = AttestationGraph()
    
    # Honest network: sparse, organic (3-5 connections each)
    honest_agents = [f"honest_{i}" for i in range(10)]
    # Organic trust: not everyone knows everyone
    honest_edges = [
        (0,1,0.8), (0,2,0.7), (1,2,0.75), (1,3,0.6), (2,4,0.7),
        (3,4,0.65), (3,5,0.7), (4,5,0.6), (5,6,0.8), (5,7,0.7),
        (6,7,0.65), (6,8,0.7), (7,8,0.75), (7,9,0.6), (8,9,0.8),
        (0,9,0.5), (2,6,0.55), (3,7,0.6),
    ]
    for i, j, s in honest_edges:
        g.add_edge(honest_agents[i], honest_agents[j], s)
    
    # Sybil ring: dense mutual inflation (everyone attests everyone)
    sybil_agents = [f"sybil_{i}" for i in range(6)]
    for i in range(len(sybil_agents)):
        for j in range(i+1, len(sybil_agents)):
            g.add_edge(sybil_agents[i], sybil_agents[j], 0.95)  # Suspiciously high
    
    # Attack edges: only 2 connections between honest and sybil
    g.add_edge(honest_agents[4], sybil_agents[0], 0.4)  # Single compromised link
    g.add_edge(honest_agents[8], sybil_agents[2], 0.3)  # Another weak link
    
    print("=" * 60)
    print("SYBIL DETECTION VIA RANDOM WALKS")
    print("=" * 60)
    print(f"Honest agents: {len(honest_agents)}")
    print(f"Sybil agents: {len(sybil_agents)}")
    print(f"Attack edges: 2 (honest→sybil)")
    print(f"Honest graph density: {g.density(set(honest_agents)):.4f}")
    print(f"Sybil graph density: {g.density(set(sybil_agents)):.4f}")
    print()
    
    # Seeds: 3 known-honest agents
    seeds = {honest_agents[0], honest_agents[5], honest_agents[9]}
    
    result = detect_sybils(g, seeds, threshold=0.05)
    
    print("TRUST SCORES (SybilRank):")
    for node, score in result["scores"].items():
        marker = "🟢" if node in set(result["honest"]) else "🟡" if node in set(result["suspicious"]) else "🔴"
        truth = "sybil" if node.startswith("sybil") else "honest"
        print(f"  {marker} {node}: {score:.6f} (actually {truth})")
    
    print(f"\nClassification:")
    print(f"  Honest: {len(result['honest'])}")
    print(f"  Suspicious: {len(result['suspicious'])}")
    print(f"  Sybil: {len(result['sybil'])}")
    print(f"  Attack edges detected: {result['attack_edges']}")
    print(f"  Honest density: {result['honest_density']}")
    print(f"  Sybil density: {result['sybil_density']}")
    
    # Verify: honest agents should have higher scores than sybils
    honest_scores = [result["scores"].get(a, 0) for a in honest_agents]
    sybil_scores = [result["scores"].get(a, 0) for a in sybil_agents]
    avg_honest = sum(honest_scores) / len(honest_scores)
    avg_sybil = sum(sybil_scores) / len(sybil_scores)
    
    print(f"\n  Avg honest score: {avg_honest:.6f}")
    print(f"  Avg sybil score: {avg_sybil:.6f}")
    print(f"  Separation ratio: {avg_honest / max(avg_sybil, 0.000001):.1f}x")
    
    assert avg_honest > avg_sybil, "Honest agents should score higher than sybils"
    # Ground truth density check (not from classifier output)
    gt_honest_density = g.density(set(honest_agents))
    gt_sybil_density = g.density(set(sybil_agents))
    assert gt_sybil_density > gt_honest_density, "Sybil ring should be denser (ground truth)"
    # All sybils should be classified as suspicious or sybil (not honest)
    classified_honest = set(result["honest"])
    sybils_missed = set(sybil_agents) & classified_honest
    assert len(sybils_missed) == 0, f"Sybils misclassified as honest: {sybils_missed}"
    
    print("\n✓ ASSERTIONS PASSED")
    print()
    print("KEY INSIGHT: Random walks from honest seeds stay in honest region.")
    print("Sybil rings are dense internally but connected by few attack edges.")
    print("Walk probability decays exponentially across attack edge boundary.")
    print("Alvisi et al 2013: O(√n·log n) sybils per attack edge is the bound.")


if __name__ == "__main__":
    demo()
