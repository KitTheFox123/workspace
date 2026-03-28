#!/usr/bin/env python3
"""
sybilwalk-atf.py — SybilWalk-inspired bidirectional random walk for ATF trust graphs.

Adapts Jia, Wang & Gong (Iowa State, 2017) SybilWalk to agent trust:
- Random walks from BOTH honest seeds AND known sybil seeds
- Honest walks propagate trust; sybil walks propagate distrust
- Final score = trust_probability - distrust_probability
- Key insight: sybil-honest edges are the bottleneck — walks get
  trapped in dense sybil clusters (clustering coeff ~0.88 vs honest ~0.19)

SybilWalk advantages over SybilRank:
- Uses both positive and negative labels (bidirectional)
- Tighter bound: O(g·log(n)/w) accepted sybils (g=attack edges, w=walk length)
- More robust to label noise (Twitter: 1.3% FPR, 17.3% FNR)

Agent trust mapping:
- Honest seeds = genesis attesters, high-DKIM-chain agents
- Sybil seeds = agents flagged by density detector or burst detector
- Walk length = attestation chain depth
- Edge weight = attestation score × min(1, dkim_days/90)

Kit 🦊 — 2026-03-28
"""

import random
import json
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class TrustGraph:
    """Directed weighted graph of attestation relationships."""
    edges: dict[str, dict[str, float]] = field(default_factory=lambda: defaultdict(dict))
    node_metadata: dict[str, dict] = field(default_factory=dict)
    
    def add_edge(self, src: str, dst: str, weight: float = 1.0):
        self.edges[src][dst] = weight
        # Ensure nodes exist
        for n in [src, dst]:
            if n not in self.node_metadata:
                self.node_metadata[n] = {}
    
    def neighbors(self, node: str) -> list[tuple[str, float]]:
        return list(self.edges.get(node, {}).items())
    
    def all_nodes(self) -> set[str]:
        nodes = set(self.node_metadata.keys())
        for src, dsts in self.edges.items():
            nodes.add(src)
            nodes.update(dsts.keys())
        return nodes
    
    def clustering_coefficient(self, node: str) -> float:
        """Local clustering coefficient."""
        neighbors = set(self.edges.get(node, {}).keys())
        if len(neighbors) < 2:
            return 0.0
        possible = len(neighbors) * (len(neighbors) - 1)
        actual = 0
        for n1 in neighbors:
            for n2 in neighbors:
                if n1 != n2 and n2 in self.edges.get(n1, {}):
                    actual += 1
        return actual / possible if possible > 0 else 0.0


class SybilWalkATF:
    """
    Bidirectional random walk for sybil detection in ATF trust graphs.
    
    Parameters:
        walk_length: Number of steps per walk (default 10)
        num_walks: Number of walks per seed (default 100)
        decay: Trust decay per hop (default 0.85, like PageRank)
    """
    
    def __init__(self, graph: TrustGraph, walk_length: int = 10,
                 num_walks: int = 100, decay: float = 0.85):
        self.graph = graph
        self.walk_length = walk_length
        self.num_walks = num_walks
        self.decay = decay
    
    def _random_walk(self, start: str, length: int) -> list[str]:
        """Perform weighted random walk from start node."""
        path = [start]
        current = start
        for _ in range(length):
            neighbors = self.graph.neighbors(current)
            if not neighbors:
                break
            nodes, weights = zip(*neighbors)
            total = sum(weights)
            probs = [w / total for w in weights]
            current = random.choices(nodes, weights=probs, k=1)[0]
            path.append(current)
        return path
    
    def _propagate_score(self, seeds: set[str], positive: bool) -> dict[str, float]:
        """Propagate trust/distrust from seeds via random walks."""
        scores = defaultdict(float)
        
        for seed in seeds:
            for _ in range(self.num_walks):
                path = self._random_walk(seed, self.walk_length)
                for i, node in enumerate(path):
                    contribution = self.decay ** i
                    if positive:
                        scores[node] += contribution
                    else:
                        scores[node] -= contribution
        
        # Normalize
        all_nodes = self.graph.all_nodes()
        total_walks = len(seeds) * self.num_walks
        if total_walks > 0:
            for node in all_nodes:
                scores[node] /= total_walks
        
        return dict(scores)
    
    def detect(self, honest_seeds: set[str], sybil_seeds: set[str]) -> dict[str, dict]:
        """
        Run bidirectional SybilWalk.
        
        Returns dict mapping node_id -> {
            trust_score, distrust_score, final_score, classification, confidence
        }
        """
        # Honest walks (positive propagation)
        trust_scores = self._propagate_score(honest_seeds, positive=True)
        
        # Sybil walks (negative propagation)
        distrust_scores = self._propagate_score(sybil_seeds, positive=False)
        
        results = {}
        for node in self.graph.all_nodes():
            trust = trust_scores.get(node, 0.0)
            distrust = distrust_scores.get(node, 0.0)  # Already negative
            final = trust + distrust
            
            # Classification
            if final > 0.1:
                classification = "HONEST"
                confidence = min(1.0, final)
            elif final < -0.1:
                classification = "SYBIL"
                confidence = min(1.0, abs(final))
            else:
                classification = "UNCERTAIN"
                confidence = 1.0 - abs(final) * 10  # Low confidence
            
            # Add clustering coefficient as auxiliary signal
            cc = self.graph.clustering_coefficient(node)
            
            results[node] = {
                "trust_score": round(trust, 4),
                "distrust_score": round(distrust, 4),
                "final_score": round(final, 4),
                "classification": classification,
                "confidence": round(confidence, 4),
                "clustering_coeff": round(cc, 4),
                "is_seed": node in honest_seeds or node in sybil_seeds
            }
        
        return results


def build_test_graph() -> tuple[TrustGraph, set[str], set[str]]:
    """
    Build a test graph with honest sparse network + dense sybil cluster.
    
    Honest: 20 agents, sparse connections (avg degree ~4)
    Sybil: 10 agents, dense mutual attestation (avg degree ~8)
    Attack edges: 3 edges connecting sybil to honest (the bottleneck)
    """
    random.seed(42)
    g = TrustGraph()
    
    # Honest agents: sparse, realistic connections
    honest = [f"honest_{i}" for i in range(20)]
    for h in honest:
        g.node_metadata[h] = {"type": "honest", "dkim_days": random.randint(30, 200)}
    
    # Sparse honest edges (avg degree ~4)
    for i, h in enumerate(honest):
        num_conn = random.randint(2, 6)
        targets = random.sample([x for x in honest if x != h], min(num_conn, len(honest) - 1))
        for t in targets:
            weight = random.uniform(0.5, 0.95)
            g.add_edge(h, t, weight)
    
    # Sybil agents: dense mutual attestation
    sybils = [f"sybil_{i}" for i in range(10)]
    for s in sybils:
        g.node_metadata[s] = {"type": "sybil", "dkim_days": random.randint(0, 5)}
    
    # Dense sybil edges (nearly complete graph)
    for i, s1 in enumerate(sybils):
        for j, s2 in enumerate(sybils):
            if i != j and random.random() < 0.85:
                g.add_edge(s1, s2, random.uniform(0.8, 1.0))
    
    # Attack edges (sybil → honest, the bottleneck)
    attack_edges = [
        ("sybil_0", "honest_0"),
        ("sybil_1", "honest_5"),
        ("sybil_2", "honest_12"),
    ]
    for s, h in attack_edges:
        g.add_edge(s, h, random.uniform(0.3, 0.6))
    
    # Seeds: first 3 honest as trusted, first 2 sybils as known-bad
    honest_seeds = {honest[0], honest[1], honest[2]}
    sybil_seeds = {sybils[0], sybils[1]}
    
    return g, honest_seeds, sybil_seeds


def demo():
    print("=" * 60)
    print("SybilWalk-ATF: Bidirectional Random Walk Sybil Detection")
    print("=" * 60)
    
    g, honest_seeds, sybil_seeds = build_test_graph()
    
    print(f"Graph: {len(g.all_nodes())} nodes")
    print(f"Honest seeds: {honest_seeds}")
    print(f"Sybil seeds: {sybil_seeds}")
    
    # Density comparison
    honest_cc = []
    sybil_cc = []
    for node in g.all_nodes():
        cc = g.clustering_coefficient(node)
        if "honest" in node:
            honest_cc.append(cc)
        else:
            sybil_cc.append(cc)
    
    print(f"\nClustering coefficient:")
    print(f"  Honest avg: {sum(honest_cc)/max(len(honest_cc),1):.3f}")
    print(f"  Sybil avg:  {sum(sybil_cc)/max(len(sybil_cc),1):.3f}")
    
    # Run SybilWalk
    sw = SybilWalkATF(g, walk_length=8, num_walks=200, decay=0.85)
    results = sw.detect(honest_seeds, sybil_seeds)
    
    # Classification summary
    tp = fp = tn = fn = 0
    for node, r in results.items():
        actual = "honest" if "honest" in node else "sybil"
        predicted = r["classification"]
        
        if actual == "sybil" and predicted == "SYBIL":
            tp += 1
        elif actual == "honest" and predicted == "SYBIL":
            fp += 1
        elif actual == "honest" and predicted != "SYBIL":
            tn += 1
        elif actual == "sybil" and predicted != "SYBIL":
            fn += 1
    
    print(f"\nClassification Results:")
    print(f"  True Positives (sybil→SYBIL): {tp}")
    print(f"  False Positives (honest→SYBIL): {fp}")
    print(f"  True Negatives (honest→HONEST): {tn}")
    print(f"  False Negatives (sybil→HONEST/UNCERTAIN): {fn}")
    
    fpr = fp / max(fp + tn, 1)
    fnr = fn / max(fn + tp, 1)
    print(f"  FPR: {fpr:.1%}")
    print(f"  FNR: {fnr:.1%}")
    
    # Show some individual scores
    print(f"\nSample scores:")
    for node in sorted(results.keys())[:5]:
        r = results[node]
        print(f"  {node}: final={r['final_score']:.3f} "
              f"class={r['classification']} cc={r['clustering_coeff']:.3f}")
    for node in sorted(results.keys()):
        if "sybil" in node:
            r = results[node]
            print(f"  {node}: final={r['final_score']:.3f} "
                  f"class={r['classification']} cc={r['clustering_coeff']:.3f}")
            break
    
    # Assertions
    assert fpr < 0.15, f"FPR too high: {fpr:.1%}"
    assert tp > 0, "No true positives detected"
    
    # Sybil seeds should be classified as SYBIL
    for seed in sybil_seeds:
        assert results[seed]["classification"] == "SYBIL", \
            f"Sybil seed {seed} misclassified as {results[seed]['classification']}"
    
    # Honest seeds should be classified as HONEST
    for seed in honest_seeds:
        assert results[seed]["classification"] == "HONEST", \
            f"Honest seed {seed} misclassified as {results[seed]['classification']}"
    
    print("\n✓ ALL ASSERTIONS PASSED")
    print()
    print("Key insight: random walks from honest seeds get trapped in honest")
    print("subgraph. Walks from sybil seeds get trapped in dense sybil cluster.")
    print("The attack edges (sybil→honest) are too few to bridge the gap.")
    print("Bidirectional walks detect both sides simultaneously.")


if __name__ == "__main__":
    demo()
