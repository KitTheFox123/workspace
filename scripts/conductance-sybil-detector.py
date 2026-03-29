#!/usr/bin/env python3
"""
conductance-sybil-detector.py — Conductance-based sybil detection for ATF.

Alvisi et al (IEEE S&P 2013, "SoK: Evolution of Sybil Defense"):
The fundamental sybil insight is CONDUCTANCE — the ratio of edges crossing
the honest/sybil boundary to edges within each region. Low conductance =
sybils can't easily connect to honest region. Random walks get trapped.

SybilRank (Cao et al, NSDI 2012): Short random walks from trusted seeds
converge fast in honest region (fast-mixing), get trapped in sybil region
(poor mixing across low-conductance boundary).

This combines:
1. Trust-weighted random walks from seed nodes
2. Conductance estimation via walk escape rates
3. Clustering coefficient as secondary signal (sybil=dense, honest=sparse)

Kit 🦊 — 2026-03-29
"""

import random
import json
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Node:
    id: str
    is_sybil: bool = False
    trust_score: float = 0.0  # SybilRank landing probability
    clustering_coeff: float = 0.0
    walk_visits: int = 0


class ConductanceSybilDetector:
    """
    Detects sybil regions using conductance estimation.
    
    Core idea: random walks from honest seeds mix quickly in the
    honest region but get trapped when crossing into sybil territory
    (low conductance boundary). The LANDING PROBABILITY after O(log n)
    steps is the trust signal.
    """
    
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, dict[str, float]] = defaultdict(dict)  # weighted adjacency
        self.seeds: set[str] = set()
    
    def add_node(self, node_id: str, is_sybil: bool = False):
        self.nodes[node_id] = Node(id=node_id, is_sybil=is_sybil)
    
    def add_edge(self, a: str, b: str, weight: float = 1.0):
        self.edges[a][b] = weight
        self.edges[b][a] = weight
    
    def set_seeds(self, seeds: list[str]):
        """Trusted seed nodes (known honest)."""
        self.seeds = set(seeds)
    
    def compute_clustering(self):
        """Local clustering coefficient per node."""
        for nid in self.nodes:
            neighbors = list(self.edges.get(nid, {}).keys())
            if len(neighbors) < 2:
                self.nodes[nid].clustering_coeff = 0.0
                continue
            # Count edges between neighbors
            triangles = 0
            possible = len(neighbors) * (len(neighbors) - 1) / 2
            for i in range(len(neighbors)):
                for j in range(i + 1, len(neighbors)):
                    if neighbors[j] in self.edges.get(neighbors[i], {}):
                        triangles += 1
            self.nodes[nid].clustering_coeff = triangles / possible if possible > 0 else 0.0
    
    def sybilrank(self, walk_length: int = 10, num_walks: int = 1000):
        """
        SybilRank: trust-weighted random walks from seeds.
        
        Cao et al (NSDI 2012): Start walks at seed nodes, walk O(log n) steps.
        Landing probability = trust. Honest nodes get high landing probability
        because walks mix fast in honest region. Sybil nodes get low probability
        because few edges cross the boundary (low conductance).
        """
        # Reset
        for node in self.nodes.values():
            node.trust_score = 0.0
            node.walk_visits = 0
        
        if not self.seeds:
            return
        
        seeds = list(self.seeds)
        
        for _ in range(num_walks):
            # Start at random seed
            current = random.choice(seeds)
            
            for step in range(walk_length):
                self.nodes[current].walk_visits += 1
                
                neighbors = self.edges.get(current, {})
                if not neighbors:
                    break
                
                # Weighted random walk
                nids = list(neighbors.keys())
                weights = [neighbors[n] for n in nids]
                total = sum(weights)
                weights = [w / total for w in weights]
                
                current = random.choices(nids, weights=weights, k=1)[0]
            
            # Final landing
            self.nodes[current].trust_score += 1.0
        
        # Normalize by degree (SybilRank normalization)
        for nid, node in self.nodes.items():
            degree = len(self.edges.get(nid, {}))
            if degree > 0:
                node.trust_score = node.trust_score / degree
            # Normalize to [0, 1]
        
        max_score = max(n.trust_score for n in self.nodes.values()) or 1.0
        for node in self.nodes.values():
            node.trust_score /= max_score
    
    def estimate_conductance(self, region: set[str]) -> float:
        """
        Conductance = edges_crossing_boundary / min(volume_inside, volume_outside)
        
        Low conductance = hard boundary (sybil/honest separation).
        Alvisi 2013: this is THE metric that determines sybil defense success.
        """
        crossing = 0
        internal = 0
        
        for nid in region:
            for neighbor, weight in self.edges.get(nid, {}).items():
                if neighbor in region:
                    internal += weight
                else:
                    crossing += weight
        
        internal /= 2  # Each internal edge counted twice
        volume = internal + crossing
        
        if volume == 0:
            return 0.0
        
        return crossing / volume
    
    def classify(self, threshold: float = 0.3) -> dict:
        """
        Classify nodes as honest/sybil based on trust score + clustering.
        
        Sybil signals:
        1. Low trust score (walks don't reach from honest seeds)
        2. High clustering (dense internal connections)
        """
        self.compute_clustering()
        self.sybilrank()
        
        classified = {"honest": [], "sybil": [], "uncertain": []}
        
        for nid, node in self.nodes.items():
            if nid in self.seeds:
                classified["honest"].append(nid)
                continue
            
            # Combined score: high trust + low clustering = honest
            # Sybil: low trust + high clustering
            sybil_signal = (1 - node.trust_score) * 0.6 + node.clustering_coeff * 0.4
            
            if sybil_signal > (1 - threshold):
                classified["sybil"].append(nid)
            elif sybil_signal < threshold:
                classified["honest"].append(nid)
            else:
                classified["uncertain"].append(nid)
        
        return classified
    
    def full_analysis(self) -> dict:
        classification = self.classify()
        
        honest_set = set(classification["honest"])
        sybil_set = set(classification["sybil"])
        
        honest_conductance = self.estimate_conductance(honest_set) if honest_set else 0
        sybil_conductance = self.estimate_conductance(sybil_set) if sybil_set else 0
        
        # Accuracy against ground truth
        tp = sum(1 for nid in classification["sybil"] if self.nodes[nid].is_sybil)
        fp = sum(1 for nid in classification["sybil"] if not self.nodes[nid].is_sybil)
        tn = sum(1 for nid in classification["honest"] if not self.nodes[nid].is_sybil)
        fn = sum(1 for nid in classification["honest"] if self.nodes[nid].is_sybil)
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            "classification": {k: len(v) for k, v in classification.items()},
            "conductance": {
                "honest_region": round(honest_conductance, 4),
                "sybil_region": round(sybil_conductance, 4),
                "insight": "Low sybil conductance = walks get trapped. High honest conductance = well-connected to rest of graph."
            },
            "accuracy": {
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1": round(f1, 3),
                "true_positives": tp,
                "false_positives": fp,
                "true_negatives": tn,
                "false_negatives": fn
            },
            "clustering": {
                "avg_honest": round(sum(self.nodes[n].clustering_coeff for n in classification["honest"]) / max(len(classification["honest"]), 1), 3),
                "avg_sybil": round(sum(self.nodes[n].clustering_coeff for n in classification["sybil"]) / max(len(classification["sybil"]), 1), 3),
            }
        }


def build_test_network():
    """
    Build a network with honest community + sybil clique + few attack edges.
    Models the Alvisi 2013 structure: sparse honest, dense sybil, low conductance boundary.
    """
    random.seed(42)
    d = ConductanceSybilDetector()
    
    # Honest region: 20 nodes, sparse community structure
    honest = [f"h{i}" for i in range(20)]
    for h in honest:
        d.add_node(h, is_sybil=False)
    
    # Honest edges: sparse, community-like (avg degree ~4)
    for i in range(len(honest)):
        # Connect to 2-3 nearby nodes (community)
        for j in range(1, random.randint(2, 4)):
            target = (i + j) % len(honest)
            d.add_edge(honest[i], honest[target], weight=random.uniform(0.5, 1.0))
        # Occasional long-range connection
        if random.random() < 0.2:
            target = random.randint(0, len(honest) - 1)
            if target != i:
                d.add_edge(honest[i], honest[target], weight=random.uniform(0.3, 0.7))
    
    # Sybil region: 10 nodes, dense clique
    sybils = [f"s{i}" for i in range(10)]
    for s in sybils:
        d.add_node(s, is_sybil=True)
    
    # Sybil edges: near-complete graph (dense)
    for i in range(len(sybils)):
        for j in range(i + 1, len(sybils)):
            if random.random() < 0.8:  # 80% connectivity
                d.add_edge(sybils[i], sybils[j], weight=random.uniform(0.8, 1.0))
    
    # Attack edges: few connections between sybil and honest (low conductance)
    num_attack_edges = 3
    for _ in range(num_attack_edges):
        h = random.choice(honest)
        s = random.choice(sybils)
        d.add_edge(h, s, weight=random.uniform(0.1, 0.3))
    
    # Seeds: 3 known honest nodes
    d.set_seeds([honest[0], honest[5], honest[10]])
    
    return d


def demo():
    print("=" * 60)
    print("CONDUCTANCE-BASED SYBIL DETECTION")
    print("Alvisi et al (IEEE S&P 2013) + SybilRank (Cao et al NSDI 2012)")
    print("=" * 60)
    print()
    
    d = build_test_network()
    
    honest_count = sum(1 for n in d.nodes.values() if not n.is_sybil)
    sybil_count = sum(1 for n in d.nodes.values() if n.is_sybil)
    print(f"Network: {honest_count} honest + {sybil_count} sybil nodes")
    print(f"Seeds: {len(d.seeds)} trusted nodes")
    print(f"Attack edges: 3 (low conductance boundary)")
    print()
    
    result = d.full_analysis()
    
    print("CLASSIFICATION:")
    print(f"  Honest: {result['classification']['honest']}")
    print(f"  Sybil:  {result['classification']['sybil']}")
    print(f"  Uncertain: {result['classification']['uncertain']}")
    print()
    
    print("CONDUCTANCE (Alvisi's key metric):")
    print(f"  Honest region: {result['conductance']['honest_region']}")
    print(f"  Sybil region:  {result['conductance']['sybil_region']}")
    print(f"  → {result['conductance']['insight']}")
    print()
    
    print("CLUSTERING (density asymmetry):")
    print(f"  Avg honest: {result['clustering']['avg_honest']}")
    print(f"  Avg sybil:  {result['clustering']['avg_sybil']}")
    print()
    
    print("ACCURACY:")
    print(f"  Precision: {result['accuracy']['precision']}")
    print(f"  Recall:    {result['accuracy']['recall']}")
    print(f"  F1:        {result['accuracy']['f1']}")
    print(f"  TP={result['accuracy']['true_positives']} FP={result['accuracy']['false_positives']} "
          f"TN={result['accuracy']['true_negatives']} FN={result['accuracy']['false_negatives']}")
    print()
    
    # Assertions
    assert result['accuracy']['precision'] >= 0.7, f"Precision too low: {result['accuracy']['precision']}"
    assert result['clustering']['avg_sybil'] > result['clustering']['avg_honest'], \
        "Sybil clustering should exceed honest clustering"
    
    print("ASSERTIONS PASSED ✓")
    print()
    print("KEY: Conductance determines detection success.")
    print("Smart sybils = more attack edges = higher conductance = harder to detect.")
    print("ATF defense: identity layer (DKIM chain) makes attack edges expensive.")


if __name__ == "__main__":
    demo()
