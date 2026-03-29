#!/usr/bin/env python3
"""
conductance-sybil-detector.py — Conductance-based sybil detection for ATF.

Alvisi et al (IEEE S&P 2013, "SoK: The Evolution of Sybil Defense via
Social Networks"): the FOUNDATION of sybil defense is CONDUCTANCE, not
density or clustering. Conductance of a set S = edges leaving S / min(vol(S), vol(V\S)).
Low conductance between regions = hard for random walks to cross = sybil boundary.

Key insights from Alvisi 2013:
- Universal sybil defense FAILS because honest graph isn't homogeneous
- Honest region = loosely-coupled communities, NOT one homogeneous blob
- LOCAL whitelisting > global classification (cost = O(whitelist), not O(network))
- Maginot syndrome warning: sophisticated defense vs attacks that bypass it
- Mixing time = 1/conductance gap -- fast within community, slow across boundary
- RenRen data: real sybils differ from theoretical assumptions

Implementation: personalized PageRank from ego node, then sweep cut to find
lowest-conductance partition. Nodes on the ego side = whitelist. Nodes across
the conductance gap = potential sybils.

Kit 🦊 — 2026-03-29
"""

import random
import json
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class TrustGraph:
    """Weighted directed trust graph."""
    edges: dict[str, dict[str, float]] = field(default_factory=lambda: defaultdict(dict))
    
    def add_edge(self, src: str, dst: str, weight: float = 1.0):
        self.edges[src][dst] = weight
        
    def add_undirected(self, a: str, b: str, weight: float = 1.0):
        self.add_edge(a, b, weight)
        self.add_edge(b, a, weight)
    
    def nodes(self) -> set[str]:
        nodes = set(self.edges.keys())
        for neighbors in self.edges.values():
            nodes.update(neighbors.keys())
        return nodes
    
    def degree(self, node: str) -> float:
        """Weighted degree."""
        return sum(self.edges.get(node, {}).values())
    
    def volume(self, subset: set[str]) -> float:
        """Volume = sum of degrees in subset."""
        return sum(self.degree(n) for n in subset)
    
    def conductance(self, subset: set[str]) -> float:
        """
        Conductance(S) = cut(S, V-S) / min(vol(S), vol(V-S))
        Lower = harder to cross = stronger boundary.
        """
        all_nodes = self.nodes()
        complement = all_nodes - subset
        
        if not subset or not complement:
            return 1.0  # Trivial partition
        
        # Cut = sum of edge weights crossing the boundary
        cut = 0.0
        for node in subset:
            for neighbor, weight in self.edges.get(node, {}).items():
                if neighbor in complement:
                    cut += weight
        
        vol_s = self.volume(subset)
        vol_c = self.volume(complement)
        
        if min(vol_s, vol_c) == 0:
            return 1.0
        
        return cut / min(vol_s, vol_c)
    
    def personalized_pagerank(self, seed: str, alpha: float = 0.15, 
                               iterations: int = 50) -> dict[str, float]:
        """
        Personalized PageRank from seed node.
        alpha = teleport probability (back to seed).
        Higher alpha = more local. Alvisi: local whitelisting is the goal.
        """
        nodes = list(self.nodes())
        scores = {n: 0.0 for n in nodes}
        scores[seed] = 1.0
        
        for _ in range(iterations):
            new_scores = {n: 0.0 for n in nodes}
            for node in nodes:
                if scores[node] == 0:
                    continue
                neighbors = self.edges.get(node, {})
                total_weight = sum(neighbors.values())
                if total_weight == 0:
                    new_scores[seed] += scores[node]
                    continue
                for neighbor, weight in neighbors.items():
                    new_scores[neighbor] += (1 - alpha) * scores[node] * (weight / total_weight)
                new_scores[seed] += alpha * scores[node]
            scores = new_scores
        
        return scores
    
    def sweep_cut(self, scores: dict[str, float]) -> tuple[set[str], float]:
        """
        Sweep cut: sort nodes by score/degree ratio, find lowest-conductance cut.
        This is the standard technique from spectral graph theory.
        Returns (best_subset, best_conductance).
        """
        # Sort by score/degree ratio (descending)
        nodes_sorted = sorted(
            scores.keys(),
            key=lambda n: scores[n] / max(self.degree(n), 1e-10),
            reverse=True
        )
        
        best_subset = set()
        best_conductance = 1.0
        current_subset = set()
        
        all_nodes = self.nodes()
        
        for i, node in enumerate(nodes_sorted):
            current_subset.add(node)
            if len(current_subset) >= len(all_nodes):
                break
            
            c = self.conductance(current_subset)
            if c < best_conductance and len(current_subset) > 1:
                best_conductance = c
                best_subset = current_subset.copy()
        
        return best_subset, best_conductance


def detect_sybils(graph: TrustGraph, ego: str, 
                  conductance_threshold: float = 0.3) -> dict:
    """
    Detect sybils from ego node's perspective using conductance-based sweep cut.
    
    Returns classification + conductance metrics.
    """
    # Step 1: Personalized PageRank from ego
    ppr = graph.personalized_pagerank(ego, alpha=0.2)
    
    # Step 2: Sweep cut to find natural boundary
    whitelist, boundary_conductance = graph.sweep_cut(ppr)
    
    # Step 3: Classify
    all_nodes = graph.nodes()
    outside = all_nodes - whitelist
    
    # Step 4: Compute conductance of sybil-suspected region
    if outside:
        sybil_conductance = graph.conductance(outside)
    else:
        sybil_conductance = 1.0
    
    return {
        "ego": ego,
        "whitelist": sorted(whitelist),
        "suspected_sybils": sorted(outside),
        "boundary_conductance": round(boundary_conductance, 4),
        "sybil_region_conductance": round(sybil_conductance, 4),
        "whitelist_size": len(whitelist),
        "network_size": len(all_nodes),
        "classification_confidence": "HIGH" if boundary_conductance < 0.1 else
                                     "MEDIUM" if boundary_conductance < conductance_threshold else
                                     "LOW"
    }


def build_test_graph() -> TrustGraph:
    """
    Build a test graph with honest community + sybil ring.
    Honest: loosely-coupled communities (Alvisi's model).
    Sybils: dense clique with few attack edges.
    """
    g = TrustGraph()
    random.seed(42)
    
    # Honest community A (5 nodes, sparse)
    honest_a = [f"honest_a{i}" for i in range(5)]
    for i in range(len(honest_a)):
        for j in range(i + 1, len(honest_a)):
            if random.random() < 0.4:  # Sparse
                g.add_undirected(honest_a[i], honest_a[j], 
                               weight=random.uniform(0.5, 1.0))
    # Ensure connected
    for i in range(len(honest_a) - 1):
        g.add_undirected(honest_a[i], honest_a[i + 1], weight=0.8)
    
    # Honest community B (5 nodes, sparse)
    honest_b = [f"honest_b{i}" for i in range(5)]
    for i in range(len(honest_b)):
        for j in range(i + 1, len(honest_b)):
            if random.random() < 0.4:
                g.add_undirected(honest_b[i], honest_b[j],
                               weight=random.uniform(0.5, 1.0))
    for i in range(len(honest_b) - 1):
        g.add_undirected(honest_b[i], honest_b[i + 1], weight=0.8)
    
    # Loose coupling between honest communities (2 edges)
    g.add_undirected("honest_a2", "honest_b1", weight=0.6)
    g.add_undirected("honest_a4", "honest_b3", weight=0.5)
    
    # Sybil ring (5 nodes, dense clique)
    sybils = [f"sybil{i}" for i in range(5)]
    for i in range(len(sybils)):
        for j in range(i + 1, len(sybils)):
            g.add_undirected(sybils[i], sybils[j], weight=1.0)
    
    # Attack edges (few, connecting sybils to honest)
    g.add_undirected("sybil0", "honest_b4", weight=0.3)  # Single attack edge
    
    return g, honest_a + honest_b, sybils


def demo():
    print("=" * 60)
    print("CONDUCTANCE-BASED SYBIL DETECTION")
    print("Alvisi et al (IEEE S&P 2013)")
    print("=" * 60)
    print()
    
    g, honest_nodes, sybil_nodes = build_test_graph()
    
    print(f"Graph: {len(g.nodes())} nodes")
    print(f"Honest: {len(honest_nodes)} (2 loosely-coupled communities)")
    print(f"Sybils: {len(sybil_nodes)} (dense clique, 1 attack edge)")
    print()
    
    # Compute conductance of known regions
    honest_set = set(honest_nodes)
    sybil_set = set(sybil_nodes)
    
    honest_cond = g.conductance(honest_set)
    sybil_cond = g.conductance(sybil_set)
    
    print(f"Honest region conductance: {honest_cond:.4f}")
    print(f"Sybil region conductance: {sybil_cond:.4f}")
    print(f"Conductance gap: {abs(honest_cond - sybil_cond):.4f}")
    print()
    
    # Detect from ego node (honest_a0)
    print("=" * 60)
    print("DETECTION FROM honest_a0 (ego)")
    print("=" * 60)
    result = detect_sybils(g, "honest_a0")
    print(json.dumps(result, indent=2))
    print()
    
    # Check accuracy
    true_positives = len(set(result["suspected_sybils"]) & sybil_set)
    false_positives = len(set(result["suspected_sybils"]) & honest_set)
    true_negatives = len(set(result["whitelist"]) & honest_set)
    false_negatives = len(set(result["whitelist"]) & sybil_set)
    
    precision = true_positives / max(true_positives + false_positives, 1)
    recall = true_positives / max(true_positives + false_negatives, 1)
    
    print(f"True positives (sybils caught): {true_positives}/{len(sybil_nodes)}")
    print(f"False positives (honest rejected): {false_positives}/{len(honest_nodes)}")
    print(f"Precision: {precision:.2%}")
    print(f"Recall: {recall:.2%}")
    print()
    
    # Test from sybil ego (should whitelist sybils, reject honest)
    print("=" * 60)
    print("DETECTION FROM sybil0 (sybil ego — inverted view)")
    print("=" * 60)
    result_sybil = detect_sybils(g, "sybil0")
    print(f"Whitelist: {result_sybil['whitelist']}")
    print(f"Suspected: {result_sybil['suspected_sybils']}")
    print(f"Conductance: {result_sybil['boundary_conductance']}")
    print()
    print("KEY: Sybils whitelist EACH OTHER. This is expected —")
    print("local whitelisting is perspective-dependent (Alvisi 2013).")
    print("Relying parties choose their OWN ego. Sybils can't")
    print("force honest nodes to include them.")
    print()
    
    # Maginot syndrome warning
    print("=" * 60)
    print("MAGINOT SYNDROME WARNING (Alvisi 2013)")
    print("=" * 60)
    print("Single-layer detection = bypassed by adaptive attacker.")
    print("Defense in depth: conductance + temporal + behavioral +")
    print("trust-layer-validator.py (addressing→identity→trust).")
    print("The conductance gap is ONE signal, not THE answer.")


if __name__ == "__main__":
    demo()
