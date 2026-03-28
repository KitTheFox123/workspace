#!/usr/bin/env python3
"""
sybil-density-detector.py — Density asymmetry sybil detection for ATF.

Core insight from Alvisi et al (IEEE S&P 2013, "SoK: The Evolution of
Sybil Defense via Social Networks"):
- Honest social graphs = loosely-coupled communities (sparse)
- Sybil graphs = dense cliques (cheap to create mutual attestations)
- The ATTACK EDGE bottleneck limits sybil-honest connections

This detector uses three signals:
1. LOCAL CLUSTERING COEFFICIENT — sybil cliques have high clustering
   (everyone attests everyone). Honest networks are sparser.
2. CONDUCTANCE — ratio of external to internal edges. Sybil clusters
   have low conductance (few attack edges to honest network).
3. RANDOM WALK MIXING — walks starting from honest seeds mix fast
   (O(log n) steps). Walks from sybil regions get trapped in cliques.

The key Alvisi contribution: global sybil defense fails because honest
graphs aren't homogeneous. LOCAL whitelisting from ego node works.

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class TrustGraph:
    """Directed weighted trust graph."""
    edges: dict[str, dict[str, float]] = field(default_factory=lambda: defaultdict(dict))
    labels: dict[str, str] = field(default_factory=dict)  # node → "honest"/"sybil"
    
    def add_edge(self, src: str, dst: str, weight: float = 1.0):
        self.edges[src][dst] = weight
    
    def add_node(self, node: str, label: str):
        self.labels[node] = label
        if node not in self.edges:
            self.edges[node] = {}
    
    def neighbors(self, node: str) -> dict[str, float]:
        return self.edges.get(node, {})
    
    def nodes(self) -> set[str]:
        all_nodes = set(self.edges.keys())
        for neighbors in self.edges.values():
            all_nodes.update(neighbors.keys())
        return all_nodes
    
    def degree(self, node: str) -> int:
        outgoing = len(self.edges.get(node, {}))
        incoming = sum(1 for n in self.edges.values() if node in n)
        return outgoing + incoming


@dataclass
class SybilScore:
    node: str
    clustering_coeff: float
    conductance: float
    walk_escape_rate: float
    sybil_probability: float
    detected_as: str  # "honest" or "sybil"
    actual_label: str


class SybilDensityDetector:
    """
    Alvisi-inspired local sybil detection.
    
    Three signals combined:
    - High clustering + low conductance + low escape rate = sybil
    - Low clustering + high conductance + high escape rate = honest
    """
    
    def __init__(self, graph: TrustGraph, 
                 clustering_threshold: float = 0.6,
                 conductance_threshold: float = 0.3,
                 escape_threshold: float = 0.4):
        self.graph = graph
        self.clustering_threshold = clustering_threshold
        self.conductance_threshold = conductance_threshold
        self.escape_threshold = escape_threshold
    
    def local_clustering_coefficient(self, node: str) -> float:
        """
        Fraction of neighbor pairs that are also connected.
        Sybil cliques → ~1.0. Honest sparse graphs → ~0.1-0.3.
        """
        neighbors = set(self.graph.neighbors(node).keys())
        # Add nodes that point TO this node
        for n, edges in self.graph.edges.items():
            if node in edges:
                neighbors.add(n)
        
        if len(neighbors) < 2:
            return 0.0
        
        connected_pairs = 0
        total_pairs = 0
        neighbor_list = list(neighbors)
        
        for i in range(len(neighbor_list)):
            for j in range(i + 1, len(neighbor_list)):
                total_pairs += 1
                n1, n2 = neighbor_list[i], neighbor_list[j]
                if n2 in self.graph.edges.get(n1, {}) or n1 in self.graph.edges.get(n2, {}):
                    connected_pairs += 1
        
        return connected_pairs / total_pairs if total_pairs > 0 else 0.0
    
    def neighborhood_conductance(self, node: str) -> float:
        """
        Conductance = external_edges / total_edges for node's neighborhood.
        Low conductance = isolated cluster (sybil pattern).
        High conductance = well-connected to broader graph (honest).
        """
        neighbors = set(self.graph.neighbors(node).keys())
        for n, edges in self.graph.edges.items():
            if node in edges:
                neighbors.add(n)
        
        neighborhood = neighbors | {node}
        
        internal_edges = 0
        external_edges = 0
        
        for n in neighborhood:
            for target in self.graph.neighbors(n):
                if target in neighborhood:
                    internal_edges += 1
                else:
                    external_edges += 1
        
        total = internal_edges + external_edges
        return external_edges / total if total > 0 else 0.0
    
    def random_walk_escape_rate(self, node: str, steps: int = 20, walks: int = 100) -> float:
        """
        Fraction of random walks that escape the node's local cluster.
        
        Alvisi: honest graphs are fast-mixing (walks escape quickly).
        Sybil cliques trap walks (low escape rate).
        """
        neighbors = set(self.graph.neighbors(node).keys())
        for n, edges in self.graph.edges.items():
            if node in edges:
                neighbors.add(n)
        local_cluster = neighbors | {node}
        
        escaped = 0
        for _ in range(walks):
            current = node
            for _ in range(steps):
                nbrs = list(self.graph.neighbors(current).keys())
                # Add incoming edges
                for n, edges in self.graph.edges.items():
                    if current in edges and n not in nbrs:
                        nbrs.append(n)
                
                if not nbrs:
                    break
                current = random.choice(nbrs)
            
            if current not in local_cluster:
                escaped += 1
        
        return escaped / walks
    
    def score_node(self, node: str) -> SybilScore:
        cc = self.local_clustering_coefficient(node)
        cond = self.neighborhood_conductance(node)
        escape = self.random_walk_escape_rate(node)
        
        # Combine signals: high clustering + low conductance + low escape = sybil
        # Weighted: clustering 0.4, conductance 0.3, escape 0.3
        sybil_prob = (
            0.4 * cc +                    # High clustering = sybil
            0.3 * (1.0 - cond) +          # Low conductance = sybil
            0.3 * (1.0 - escape)          # Low escape = sybil
        )
        
        detected = "sybil" if sybil_prob > 0.55 else "honest"
        actual = self.graph.labels.get(node, "unknown")
        
        return SybilScore(
            node=node,
            clustering_coeff=round(cc, 3),
            conductance=round(cond, 3),
            walk_escape_rate=round(escape, 3),
            sybil_probability=round(sybil_prob, 3),
            detected_as=detected,
            actual_label=actual
        )
    
    def scan_all(self) -> dict:
        results = []
        tp = fp = tn = fn = 0
        
        for node in self.graph.nodes():
            score = self.score_node(node)
            results.append(score)
            
            if score.actual_label == "sybil":
                if score.detected_as == "sybil":
                    tp += 1
                else:
                    fn += 1
            elif score.actual_label == "honest":
                if score.detected_as == "honest":
                    tn += 1
                else:
                    fp += 1
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            "scores": results,
            "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "total_nodes": len(results),
            "detected_sybils": sum(1 for s in results if s.detected_as == "sybil"),
            "actual_sybils": sum(1 for s in results if s.actual_label == "sybil")
        }


def build_test_graph() -> TrustGraph:
    """
    Build a graph with:
    - 10 honest nodes (sparse, community structure)
    - 5 sybil nodes (dense clique)
    - 2 attack edges connecting sybil to honest
    """
    g = TrustGraph()
    
    # Honest network: two communities, loosely connected
    honest_a = [f"h_a{i}" for i in range(5)]
    honest_b = [f"h_b{i}" for i in range(5)]
    
    for h in honest_a + honest_b:
        g.add_node(h, "honest")
    
    # Community A: chain + a few cross-links
    for i in range(len(honest_a) - 1):
        g.add_edge(honest_a[i], honest_a[i+1], 0.7)
        g.add_edge(honest_a[i+1], honest_a[i], 0.6)
    g.add_edge(honest_a[0], honest_a[3], 0.5)
    
    # Community B: similar
    for i in range(len(honest_b) - 1):
        g.add_edge(honest_b[i], honest_b[i+1], 0.7)
        g.add_edge(honest_b[i+1], honest_b[i], 0.6)
    g.add_edge(honest_b[1], honest_b[4], 0.4)
    
    # Inter-community bridge
    g.add_edge(honest_a[2], honest_b[0], 0.5)
    g.add_edge(honest_b[2], honest_a[4], 0.4)
    
    # Sybil clique: everyone attests everyone
    sybils = [f"s{i}" for i in range(5)]
    for s in sybils:
        g.add_node(s, "sybil")
    
    for i in range(len(sybils)):
        for j in range(len(sybils)):
            if i != j:
                g.add_edge(sybils[i], sybils[j], 0.9)
    
    # Attack edges (limited connection to honest network)
    g.add_edge(sybils[0], honest_a[0], 0.3)
    g.add_edge(sybils[1], honest_b[3], 0.2)
    
    return g


def demo():
    random.seed(42)
    
    g = build_test_graph()
    detector = SybilDensityDetector(g)
    
    print("=" * 65)
    print("SYBIL DENSITY DETECTOR (Alvisi et al 2013)")
    print("=" * 65)
    print(f"Graph: {len(g.nodes())} nodes, "
          f"{sum(1 for n in g.labels.values() if n == 'honest')} honest, "
          f"{sum(1 for n in g.labels.values() if n == 'sybil')} sybil")
    print(f"Attack edges: 2 (sybil→honest)")
    print()
    
    results = detector.scan_all()
    
    print(f"{'Node':<10} {'Clust':>6} {'Cond':>6} {'Escape':>7} {'P(sybil)':>9} {'Detected':>9} {'Actual':>8}")
    print("-" * 65)
    for s in sorted(results["scores"], key=lambda x: -x.sybil_probability):
        marker = "✓" if s.detected_as == s.actual_label else "✗"
        print(f"{s.node:<10} {s.clustering_coeff:>6.3f} {s.conductance:>6.3f} "
              f"{s.walk_escape_rate:>7.3f} {s.sybil_probability:>9.3f} "
              f"{s.detected_as:>9} {s.actual_label:>7} {marker}")
    
    print()
    print(f"Precision: {results['precision']:.3f}")
    print(f"Recall:    {results['recall']:.3f}")
    print(f"F1:        {results['f1']:.3f}")
    print(f"Detected:  {results['detected_sybils']}/{results['actual_sybils']} sybils")
    print()
    
    # Key insight
    avg_sybil_cc = sum(s.clustering_coeff for s in results["scores"] if s.actual_label == "sybil") / max(1, results["actual_sybils"])
    avg_honest_cc = sum(s.clustering_coeff for s in results["scores"] if s.actual_label == "honest") / max(1, results["total_nodes"] - results["actual_sybils"])
    
    print(f"Avg clustering - Sybil: {avg_sybil_cc:.3f}, Honest: {avg_honest_cc:.3f}")
    print(f"Density ratio: {avg_sybil_cc / max(0.001, avg_honest_cc):.1f}x")
    print()
    print("INSIGHT: Density asymmetry IS the fundamental sybil tell.")
    print("Honest trust is expensive → sparse. Sybil trust is free → dense.")
    print("Local detection (Alvisi) > global detection because honest")
    print("graphs aren't homogeneous — they're communities.")


if __name__ == "__main__":
    demo()
