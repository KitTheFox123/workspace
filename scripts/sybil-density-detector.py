#!/usr/bin/env python3
"""
sybil-density-detector.py — Random walk sybil detection for ATF attestation graphs.

Implements the core insight from SybilGuard (Yu et al 2006), SybilRank (Cao et al
2012), and SybilWalk (Jia, Wang & Gong 2017): sybil regions in trust networks are
DENSE internally but SPARSE-CUT from honest regions. Random walks from trusted
seeds mix quickly in the honest region but get trapped in sybil clusters.

Key results from literature:
- SybilWalk on Twitter: 1.3% FPR, 17.3% FNR (Jia et al 2017)
- SybilRank: O(n log n) time, works on billion-node graphs (Cao et al 2012)
- Fast-mixing property: honest region random walks converge to uniform distribution
  in O(log n) steps. Sybil boundary creates bottleneck.

ATF mapping:
- Honest agents form sparse graphs (trust is hard to earn)
- Sybils form dense clusters (mutual inflation is free)
- Anchor seeds = agents with full trust stack (addressing + identity + trust)
- Random walk trust scores from anchors expose the sparse cut

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Node:
    id: str
    is_sybil: bool = False
    is_anchor: bool = False  # Trusted seed
    trust_score: float = 0.0
    cluster: str = ""


class AttestationGraph:
    """Directed weighted attestation graph."""
    
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, dict[str, float]] = defaultdict(dict)  # from -> {to: weight}
        self.in_edges: dict[str, dict[str, float]] = defaultdict(dict)
    
    def add_node(self, node_id: str, is_sybil: bool = False, is_anchor: bool = False) -> Node:
        node = Node(id=node_id, is_sybil=is_sybil, is_anchor=is_anchor)
        if is_anchor:
            node.trust_score = 1.0
        self.nodes[node_id] = node
        return node
    
    def add_attestation(self, attester: str, subject: str, weight: float = 1.0):
        self.edges[attester][subject] = weight
        self.in_edges[subject][attester] = weight
    
    def random_walk_trust(self, steps: int = 10, damping: float = 0.85) -> dict[str, float]:
        """
        Propagate trust from anchor seeds via random walk (PageRank variant).
        
        Honest region: fast-mixing → trust distributes uniformly among honest nodes.
        Sybil region: sparse cut → trust drains at boundary, sybils starve.
        """
        # Initialize: anchors start with score 1.0
        scores = {nid: (1.0 if n.is_anchor else 0.0) for nid, n in self.nodes.items()}
        n_nodes = len(self.nodes)
        if n_nodes == 0:
            return scores
        
        anchor_count = sum(1 for n in self.nodes.values() if n.is_anchor)
        if anchor_count == 0:
            return scores
        
        for _ in range(steps):
            new_scores = {}
            for nid in self.nodes:
                # Teleport to anchors with probability (1 - damping)
                teleport = (1 - damping) * (1.0 if self.nodes[nid].is_anchor else 0.0)
                
                # Walk: sum of incoming trust * edge weight / out-degree
                walk_sum = 0.0
                for src, weight in self.in_edges[nid].items():
                    out_degree = len(self.edges[src])
                    if out_degree > 0:
                        walk_sum += scores[src] * weight / out_degree
                
                new_scores[nid] = teleport + damping * walk_sum
            
            scores = new_scores
        
        # Update node scores
        for nid, score in scores.items():
            self.nodes[nid].trust_score = score
        
        return scores
    
    def detect_dense_clusters(self, threshold: float = 0.5) -> list[dict]:
        """
        Detect dense subgraphs (sybil indicator).
        
        Metric: internal edge density = edges_within / possible_edges.
        Honest clusters: sparse (density < 0.3 typically).
        Sybil clusters: dense (density > 0.5, often > 0.8).
        """
        # Group by rough trust score bands
        low_trust = [nid for nid, n in self.nodes.items() 
                     if n.trust_score < threshold and not n.is_anchor]
        
        if len(low_trust) < 2:
            return []
        
        # Calculate internal density of low-trust subgraph
        internal_edges = 0
        for nid in low_trust:
            for target, _ in self.edges[nid].items():
                if target in low_trust:
                    internal_edges += 1
        
        possible = len(low_trust) * (len(low_trust) - 1)
        density = internal_edges / possible if possible > 0 else 0
        
        # Calculate sparse cut (edges between low-trust and rest)
        cut_edges = 0
        for nid in low_trust:
            for target, _ in self.edges[nid].items():
                if target not in low_trust:
                    cut_edges += 1
            for src, _ in self.in_edges[nid].items():
                if src not in low_trust:
                    cut_edges += 1
        
        clusters = []
        if density > 0.3:
            clusters.append({
                "type": "DENSE_LOW_TRUST",
                "nodes": low_trust,
                "internal_density": round(density, 3),
                "cut_edges": cut_edges,
                "cut_ratio": round(cut_edges / max(len(low_trust), 1), 3),
                "verdict": "SYBIL_LIKELY" if density > 0.5 else "SUSPICIOUS"
            })
        
        return clusters
    
    def classify(self, trust_threshold: float = 0.3) -> dict:
        """Classify all nodes as honest/sybil based on random walk scores."""
        self.random_walk_trust(steps=20)
        clusters = self.detect_dense_clusters(trust_threshold)
        
        sybil_suspects = set()
        for cluster in clusters:
            if cluster["verdict"] == "SYBIL_LIKELY":
                sybil_suspects.update(cluster["nodes"])
        
        # Classification
        results = {}
        tp = fp = tn = fn = 0
        for nid, node in self.nodes.items():
            predicted_sybil = nid in sybil_suspects or node.trust_score < trust_threshold
            actual_sybil = node.is_sybil
            
            results[nid] = {
                "trust_score": round(node.trust_score, 4),
                "predicted_sybil": predicted_sybil,
                "actual_sybil": actual_sybil,
                "correct": predicted_sybil == actual_sybil
            }
            
            if predicted_sybil and actual_sybil:
                tp += 1
            elif predicted_sybil and not actual_sybil:
                fp += 1
            elif not predicted_sybil and not actual_sybil:
                tn += 1
            else:
                fn += 1
        
        total = tp + fp + tn + fn
        return {
            "classifications": results,
            "clusters": clusters,
            "metrics": {
                "true_positives": tp,
                "false_positives": fp,
                "true_negatives": tn,
                "false_negatives": fn,
                "accuracy": round((tp + tn) / max(total, 1), 3),
                "fpr": round(fp / max(fp + tn, 1), 3),
                "fnr": round(fn / max(fn + tp, 1), 3),
            }
        }


def build_test_graph() -> AttestationGraph:
    """
    Build test graph:
    - 10 honest agents (sparse connections)
    - 5 sybils (dense mutual attestation)
    - 2 anchor seeds
    """
    g = AttestationGraph()
    random.seed(42)
    
    # Honest agents
    for i in range(10):
        g.add_node(f"honest_{i}", is_anchor=(i < 2))
    
    # Sparse honest connections (each attests 2-3 others)
    honest_ids = [f"honest_{i}" for i in range(10)]
    for nid in honest_ids:
        targets = random.sample([h for h in honest_ids if h != nid], k=random.randint(2, 3))
        for t in targets:
            g.add_attestation(nid, t, weight=random.uniform(0.6, 1.0))
    
    # Sybil ring (dense mutual attestation)
    for i in range(5):
        g.add_node(f"sybil_{i}", is_sybil=True)
    
    sybil_ids = [f"sybil_{i}" for i in range(5)]
    for s1 in sybil_ids:
        for s2 in sybil_ids:
            if s1 != s2:
                g.add_attestation(s1, s2, weight=random.uniform(0.8, 1.0))
    
    # Sparse cut: 1-2 edges from sybils to honest (attack edges)
    g.add_attestation("sybil_0", "honest_5", weight=0.9)
    g.add_attestation("honest_7", "sybil_0", weight=0.5)
    
    return g


def demo():
    print("=" * 60)
    print("SYBIL DENSITY DETECTOR — Random Walk Trust Propagation")
    print("=" * 60)
    print("Method: SybilGuard/SybilRank-inspired random walk from anchors")
    print("Lit: Jia et al 2017 (SybilWalk): 1.3% FPR, 17.3% FNR on Twitter")
    print()
    
    g = build_test_graph()
    print(f"Graph: {len(g.nodes)} nodes ({sum(1 for n in g.nodes.values() if not n.is_sybil)} honest, "
          f"{sum(1 for n in g.nodes.values() if n.is_sybil)} sybil)")
    print(f"Anchors: {sum(1 for n in g.nodes.values() if n.is_anchor)}")
    print()
    
    result = g.classify(trust_threshold=0.005)
    
    print("TRUST SCORES:")
    for nid in sorted(result["classifications"].keys()):
        c = result["classifications"][nid]
        label = "✓" if c["correct"] else "✗"
        sybil_tag = " [SYBIL]" if c["actual_sybil"] else ""
        pred_tag = " → FLAGGED" if c["predicted_sybil"] else ""
        print(f"  {label} {nid}: {c['trust_score']:.4f}{sybil_tag}{pred_tag}")
    
    print()
    if result["clusters"]:
        for cluster in result["clusters"]:
            print(f"DENSE CLUSTER DETECTED: {cluster['verdict']}")
            print(f"  Nodes: {cluster['nodes']}")
            print(f"  Internal density: {cluster['internal_density']}")
            print(f"  Cut edges: {cluster['cut_edges']} (ratio: {cluster['cut_ratio']})")
    
    print()
    m = result["metrics"]
    print(f"METRICS:")
    print(f"  Accuracy: {m['accuracy']:.1%}")
    print(f"  FPR: {m['fpr']:.1%}")
    print(f"  FNR: {m['fnr']:.1%}")
    print(f"  TP={m['true_positives']}, FP={m['false_positives']}, "
          f"TN={m['true_negatives']}, FN={m['false_negatives']}")
    
    assert m["accuracy"] >= 0.8, f"Accuracy too low: {m['accuracy']}"
    print("\n✓ ACCURACY ≥ 80% — PASSED")
    
    # Verify sybils have lower trust than honest agents
    sybil_scores = [c["trust_score"] for c in result["classifications"].values() if c["actual_sybil"]]
    honest_scores = [c["trust_score"] for c in result["classifications"].values() if not c["actual_sybil"]]
    avg_sybil = sum(sybil_scores) / max(len(sybil_scores), 1)
    avg_honest = sum(honest_scores) / max(len(honest_scores), 1)
    print(f"✓ Avg sybil trust ({avg_sybil:.4f}) < avg honest trust ({avg_honest:.4f})")
    assert avg_sybil < avg_honest


if __name__ == "__main__":
    demo()
