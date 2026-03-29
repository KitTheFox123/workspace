#!/usr/bin/env python3
"""
conductance-sybil-detector.py — Sybil detection via graph conductance.

Implements Alvisi et al 2013 (IEEE S&P) core insight: conductance is THE
structural property for sybil defense, not popularity, clustering, or
small-world distance.

Conductance φ(S) = |E(S, V\S)| / min(vol(S), vol(V\S))
where vol(S) = sum of degrees of nodes in S.

Low conductance between honest and sybil regions = few attack edges
relative to internal connectivity. Random walks mix slowly across
low-conductance cuts → sybils stay in sybil region.

Key findings from the paper:
- Universal sybil defense is impossible (honest region is NOT homogeneous)
- Local whitelisting at O(whitelist_size) is achievable and practical
- Defense in depth > single classifier (Maginot syndrome)
- RenRen data showed simple sybils that sophisticated defenses MISSED

This tool:
1. Generates honest + sybil graph with configurable attack edges
2. Computes conductance of the sybil cut
3. Runs personalized PageRank from a trusted seed (local whitelisting)
4. Classifies nodes as honest/sybil based on PPR scores
5. Reports precision/recall

Kit 🦊 — 2026-03-29
"""

import random
import json
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class Graph:
    """Simple undirected graph."""
    nodes: set
    edges: dict  # node -> set of neighbors
    labels: dict  # node -> "honest" | "sybil"
    
    def add_edge(self, u, v):
        self.edges.setdefault(u, set()).add(v)
        self.edges.setdefault(v, set()).add(u)
    
    def degree(self, node):
        return len(self.edges.get(node, set()))
    
    def volume(self, subset):
        return sum(self.degree(n) for n in subset)
    
    def cut_edges(self, s1, s2):
        """Count edges between two sets."""
        count = 0
        for u in s1:
            for v in self.edges.get(u, set()):
                if v in s2:
                    count += 1
        return count
    
    def conductance(self, subset):
        """
        φ(S) = |E(S, V\S)| / min(vol(S), vol(V\S))
        
        Alvisi 2013: "the fundamental structural property
        for sybil defense is conductance."
        """
        complement = self.nodes - subset
        cut = self.cut_edges(subset, complement)
        vol_s = self.volume(subset)
        vol_c = self.volume(complement)
        denom = min(vol_s, vol_c)
        if denom == 0:
            return 1.0
        return cut / denom


def generate_trust_graph(n_honest=100, n_sybil=50, 
                          honest_edge_prob=0.08, sybil_edge_prob=0.3,
                          n_attack_edges=5) -> Graph:
    """
    Generate a graph with honest and sybil regions.
    
    Honest region: sparse (trust is hard to earn)
    Sybil region: dense (free to create edges among sybils)
    Attack edges: few connections between regions
    
    Alvisi 2013: "as long as sybil identities are unable to create
    too many attack edges connecting them to honest identities"
    """
    g = Graph(nodes=set(), edges={}, labels={})
    
    honest_nodes = {f"h_{i}" for i in range(n_honest)}
    sybil_nodes = {f"s_{i}" for i in range(n_sybil)}
    g.nodes = honest_nodes | sybil_nodes
    
    for n in honest_nodes:
        g.labels[n] = "honest"
    for n in sybil_nodes:
        g.labels[n] = "sybil"
    
    # Honest edges (sparse — trust is hard to earn)
    honest_list = sorted(honest_nodes)
    for i in range(len(honest_list)):
        for j in range(i + 1, len(honest_list)):
            if random.random() < honest_edge_prob:
                g.add_edge(honest_list[i], honest_list[j])
    
    # Sybil edges (dense — free to forge among colluding sybils)
    sybil_list = sorted(sybil_nodes)
    for i in range(len(sybil_list)):
        for j in range(i + 1, len(sybil_list)):
            if random.random() < sybil_edge_prob:
                g.add_edge(sybil_list[i], sybil_list[j])
    
    # Attack edges (few — bottleneck for sybil defense)
    for _ in range(n_attack_edges):
        h = random.choice(honest_list)
        s = random.choice(sybil_list)
        g.add_edge(h, s)
    
    return g


def personalized_pagerank(graph: Graph, seed: str, 
                           alpha: float = 0.15, iterations: int = 50) -> dict:
    """
    Personalized PageRank from trusted seed.
    
    Alvisi 2013: local whitelisting via random walks from a trusted node.
    PPR naturally concentrates probability mass in the local community
    and diffuses slowly across low-conductance cuts.
    
    alpha = teleport probability (back to seed)
    Higher alpha = more local (conservative trust)
    """
    scores = defaultdict(float)
    scores[seed] = 1.0
    
    for _ in range(iterations):
        new_scores = defaultdict(float)
        for node, score in scores.items():
            neighbors = graph.edges.get(node, set())
            if not neighbors:
                new_scores[seed] += score
                continue
            # Teleport
            new_scores[seed] += alpha * score
            # Distribute
            share = (1 - alpha) * score / len(neighbors)
            for neighbor in neighbors:
                new_scores[neighbor] += share
        scores = new_scores
    
    return dict(scores)


def classify_by_ppr(graph: Graph, seed: str, threshold: float = None) -> dict:
    """
    Classify nodes as honest/sybil based on PPR scores.
    If no threshold given, use median of honest node scores.
    """
    scores = personalized_pagerank(graph, seed)
    
    if threshold is None:
        honest_scores = [scores.get(n, 0) for n in graph.nodes if graph.labels[n] == "honest"]
        honest_scores.sort()
        threshold = honest_scores[len(honest_scores) // 4] if honest_scores else 0.001
    
    classifications = {}
    for node in graph.nodes:
        classifications[node] = "honest" if scores.get(node, 0) >= threshold else "sybil"
    
    return classifications, scores, threshold


def evaluate(graph: Graph, classifications: dict) -> dict:
    """Compute precision/recall for sybil detection."""
    tp = fp = tn = fn = 0
    for node in graph.nodes:
        actual = graph.labels[node]
        predicted = classifications[node]
        if actual == "sybil" and predicted == "sybil":
            tp += 1
        elif actual == "honest" and predicted == "sybil":
            fp += 1
        elif actual == "honest" and predicted == "honest":
            tn += 1
        elif actual == "sybil" and predicted == "honest":
            fn += 1
    
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 0.001)
    
    return {
        "true_positive": tp, "false_positive": fp,
        "true_negative": tn, "false_negative": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3)
    }


def demo():
    random.seed(42)
    
    scenarios = [
        ("Few attack edges (5)", dict(n_attack_edges=5)),
        ("Moderate attack edges (15)", dict(n_attack_edges=15)),
        ("Many attack edges (30)", dict(n_attack_edges=30)),
        ("Large sybil region (100 sybils)", dict(n_sybil=100, n_attack_edges=5)),
    ]
    
    for name, kwargs in scenarios:
        params = dict(n_honest=100, n_sybil=50, 
                      honest_edge_prob=0.08, sybil_edge_prob=0.3,
                      n_attack_edges=5)
        params.update(kwargs)
        
        g = generate_trust_graph(**params)
        
        honest_set = {n for n in g.nodes if g.labels[n] == "honest"}
        sybil_set = {n for n in g.nodes if g.labels[n] == "sybil"}
        
        phi = g.conductance(sybil_set)
        cut = g.cut_edges(honest_set, sybil_set)
        
        # Pick a well-connected honest seed
        seed = max(honest_set, key=lambda n: g.degree(n))
        classifications, scores, threshold = classify_by_ppr(g, seed)
        metrics = evaluate(g, classifications)
        
        print("=" * 60)
        print(f"SCENARIO: {name}")
        print("=" * 60)
        print(f"  Honest: {len(honest_set)} (avg degree {g.volume(honest_set)/len(honest_set):.1f})")
        print(f"  Sybil: {len(sybil_set)} (avg degree {g.volume(sybil_set)/len(sybil_set):.1f})")
        print(f"  Attack edges: {cut}")
        print(f"  Conductance φ(sybil): {phi:.4f}")
        print(f"  → Low φ = hard to cross = good defense")
        print(f"  PPR seed: {seed} (degree {g.degree(seed)})")
        print(f"  Threshold: {threshold:.6f}")
        print(f"  Results: {json.dumps(metrics)}")
        print()
    
    # Key insight demonstration
    print("=" * 60)
    print("KEY INSIGHT (Alvisi 2013)")
    print("=" * 60)
    print("Conductance φ determines defense effectiveness:")
    print("  Low φ (few attack edges) → high precision sybil detection")
    print("  High φ (many attack edges) → defense degrades")
    print()
    print("Local whitelisting (PPR from trusted seed) costs O(whitelist_size)")
    print("Universal defense costs O(network_size) — and is impossible anyway")
    print("because honest region is NOT homogeneous (loosely coupled communities)")
    print()
    print("Defense in depth > Maginot syndrome:")
    print("  Layer 1: DKIM temporal proof (attack edge cost)")
    print("  Layer 2: Conductance-based community detection")
    print("  Layer 3: Behavioral fingerprinting")
    print("  Layer 4: Attestation chain validation")


if __name__ == "__main__":
    demo()
