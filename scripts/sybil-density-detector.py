#!/usr/bin/env python3
"""
sybil-density-detector.py — Graph density-based sybil detection for ATF.

Core insight from Clawk thread + research:
- Honest agents form SPARSE graphs (trust is hard to earn, avg degree 5-8)
- Sybils form DENSE cliques (free mutual inflation)
- SybilRank (Cao et al, 2012): random walks from trusted seeds stay trapped in
  dense sybil regions. Landing probability = trust score.
- AAMAS 2025 (Dehkordi & Zehmakan): user RESISTANCE to attack requests is the
  missing variable. Revealing resistance of subset improves all detectors.
- ATF mapping: identity layer = resistance. Strong identity → rejects bad attestations.

Detection pipeline:
1. Build attestation graph (weighted, directed)
2. Compute local density metrics per node (clustering coefficient, edge density)
3. Run simplified SybilRank: random walk from anchor seeds
4. Flag nodes in dense clusters with low walk probability as sybil candidates

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
    identity_strength: float = 0.0  # 0-1, resistance proxy
    sybilrank_score: float = 0.0
    local_density: float = 0.0
    cluster_id: int = -1


@dataclass
class Edge:
    src: str
    dst: str
    weight: float = 1.0
    mutual: bool = False  # Bidirectional attestation


class SybilDensityDetector:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.adj: dict[str, set[str]] = defaultdict(set)
    
    def add_node(self, node: Node):
        self.nodes[node.id] = node
    
    def add_edge(self, edge: Edge):
        self.edges.append(edge)
        self.adj[edge.src].add(edge.dst)
        if edge.mutual:
            self.adj[edge.dst].add(edge.src)
    
    def compute_local_density(self) -> dict[str, float]:
        """
        Local clustering coefficient per node.
        Sybil cliques → density ≈ 1.0
        Honest sparse graphs → density ≈ 0.1-0.3
        """
        densities = {}
        for nid, node in self.nodes.items():
            neighbors = self.adj[nid]
            k = len(neighbors)
            if k < 2:
                densities[nid] = 0.0
                node.local_density = 0.0
                continue
            
            # Count edges between neighbors
            links = 0
            for n1 in neighbors:
                for n2 in neighbors:
                    if n1 != n2 and n2 in self.adj[n1]:
                        links += 1
            
            max_links = k * (k - 1)  # Directed
            density = links / max_links if max_links > 0 else 0.0
            densities[nid] = density
            node.local_density = density
        
        return densities
    
    def sybilrank(self, num_walks: int = 1000, walk_length: int = 10) -> dict[str, float]:
        """
        Simplified SybilRank: random walks from anchor seeds.
        
        Cao et al (2012): Trust propagated via short random walks from
        known-honest seeds. Walk stays trapped in dense sybil regions →
        honest nodes get higher landing probability.
        
        Walk length O(log n) for fast-mixing honest region.
        """
        anchors = [nid for nid, n in self.nodes.items() if n.is_anchor]
        if not anchors:
            return {nid: 0.0 for nid in self.nodes}
        
        visit_count = defaultdict(int)
        total_visits = 0
        
        for _ in range(num_walks):
            # Start from random anchor
            current = random.choice(anchors)
            for _ in range(walk_length):
                neighbors = list(self.adj[current])
                if not neighbors:
                    break
                
                # Weight by identity strength (resistance)
                # Dehkordi & Zehmakan: resistance nodes reject sybil connections
                weights = []
                for n in neighbors:
                    node = self.nodes.get(n)
                    w = node.identity_strength + 0.1 if node else 0.1
                    weights.append(w)
                
                total_w = sum(weights)
                if total_w == 0:
                    break
                
                probs = [w / total_w for w in weights]
                current = random.choices(neighbors, weights=probs, k=1)[0]
                visit_count[current] += 1
                total_visits += 1
        
        # Normalize
        scores = {}
        for nid in self.nodes:
            scores[nid] = visit_count[nid] / max(total_visits, 1)
            self.nodes[nid].sybilrank_score = scores[nid]
        
        return scores
    
    def detect(self, density_threshold: float = 0.7, 
               rank_threshold: float = None) -> dict:
        """
        Combined detection: high density + low SybilRank = sybil candidate.
        """
        densities = self.compute_local_density()
        ranks = self.sybilrank()
        
        if rank_threshold is None:
            # Auto-threshold: median of honest (anchor) scores
            anchor_scores = [ranks[nid] for nid in self.nodes if self.nodes[nid].is_anchor]
            rank_threshold = min(anchor_scores) * 0.5 if anchor_scores else 0.01
        
        results = {"sybil_candidates": [], "honest": [], "uncertain": []}
        
        for nid, node in self.nodes.items():
            if node.is_anchor:
                results["honest"].append({
                    "id": nid, "density": round(densities[nid], 3),
                    "rank": round(ranks[nid], 4), "reason": "anchor seed"
                })
            elif densities[nid] > density_threshold and ranks[nid] < rank_threshold:
                results["sybil_candidates"].append({
                    "id": nid, "density": round(densities[nid], 3),
                    "rank": round(ranks[nid], 4), "actual_sybil": node.is_sybil,
                    "reason": f"high density ({densities[nid]:.2f}) + low rank ({ranks[nid]:.4f})"
                })
            elif densities[nid] > density_threshold:
                results["uncertain"].append({
                    "id": nid, "density": round(densities[nid], 3),
                    "rank": round(ranks[nid], 4), "actual_sybil": node.is_sybil,
                    "reason": f"high density but adequate rank"
                })
            else:
                results["honest"].append({
                    "id": nid, "density": round(densities[nid], 3),
                    "rank": round(ranks[nid], 4), "actual_sybil": node.is_sybil,
                    "reason": "low density"
                })
        
        # Accuracy metrics
        true_sybils = {nid for nid, n in self.nodes.items() if n.is_sybil}
        detected = {c["id"] for c in results["sybil_candidates"]}
        
        tp = len(detected & true_sybils)
        fp = len(detected - true_sybils)
        fn = len(true_sybils - detected)
        tn = len(self.nodes) - tp - fp - fn
        
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 0.001)
        
        results["metrics"] = {
            "true_positives": tp, "false_positives": fp,
            "false_negatives": fn, "true_negatives": tn,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3)
        }
        
        return results


def demo():
    random.seed(42)
    detector = SybilDensityDetector()
    
    # Create honest sparse network (avg degree ~4)
    honest_ids = [f"honest_{i}" for i in range(20)]
    for hid in honest_ids:
        detector.add_node(Node(id=hid, is_sybil=False, 
                               identity_strength=random.uniform(0.5, 1.0)))
    
    # Anchor seeds (3 known-honest)
    for i in range(3):
        detector.nodes[honest_ids[i]].is_anchor = True
    
    # Sparse honest edges (avg degree ~4)
    for i, hid in enumerate(honest_ids):
        num_edges = random.randint(2, 6)
        targets = random.sample([h for h in honest_ids if h != hid], min(num_edges, len(honest_ids) - 1))
        for t in targets:
            detector.add_edge(Edge(src=hid, dst=t, weight=random.uniform(0.5, 1.0)))
    
    # Create sybil dense clique (10 nodes, almost fully connected)
    sybil_ids = [f"sybil_{i}" for i in range(10)]
    for sid in sybil_ids:
        detector.add_node(Node(id=sid, is_sybil=True, 
                               identity_strength=random.uniform(0.0, 0.2)))
    
    # Dense mutual attestation (sybil clique)
    for i, s1 in enumerate(sybil_ids):
        for j, s2 in enumerate(sybil_ids):
            if i != j and random.random() < 0.85:  # 85% edge probability
                detector.add_edge(Edge(src=s1, dst=s2, weight=1.0, mutual=True))
    
    # A few attack edges (sybils → honest, trying to bootstrap)
    for sid in sybil_ids[:3]:
        target = random.choice(honest_ids)
        detector.add_edge(Edge(src=sid, dst=target, weight=0.3))
    
    print("=" * 60)
    print("SYBIL DENSITY DETECTION")
    print("=" * 60)
    print(f"Honest agents: {len(honest_ids)} (sparse, avg degree ~4)")
    print(f"Sybil agents:  {len(sybil_ids)} (dense clique, ~85% connected)")
    print(f"Anchor seeds:  3 known-honest")
    print(f"Attack edges:  3 (sybil → honest)")
    print()
    
    results = detector.detect()
    
    print(f"Detected sybil candidates: {len(results['sybil_candidates'])}")
    print(f"Classified honest: {len(results['honest'])}")
    print(f"Uncertain: {len(results['uncertain'])}")
    print()
    
    print("SYBIL CANDIDATES:")
    for c in results["sybil_candidates"]:
        label = "✓ TRUE" if c["actual_sybil"] else "✗ FALSE"
        print(f"  {c['id']}: density={c['density']}, rank={c['rank']} [{label}]")
    
    print(f"\nMETRICS:")
    m = results["metrics"]
    print(f"  Precision: {m['precision']}")
    print(f"  Recall:    {m['recall']}")
    print(f"  F1:        {m['f1']}")
    
    print()
    
    # Show density distribution
    print("DENSITY DISTRIBUTION:")
    honest_densities = [detector.nodes[h].local_density for h in honest_ids]
    sybil_densities = [detector.nodes[s].local_density for s in sybil_ids]
    print(f"  Honest avg density: {sum(honest_densities)/len(honest_densities):.3f}")
    print(f"  Sybil avg density:  {sum(sybil_densities)/len(sybil_densities):.3f}")
    print(f"  Gap: {sum(sybil_densities)/len(sybil_densities) - sum(honest_densities)/len(honest_densities):.3f}")
    
    print()
    print("KEY INSIGHT: density IS the detector.")
    print("Honest trust is expensive → sparse. Sybil inflation is free → dense.")
    print("SybilRank walks stay trapped in dense regions → low landing probability")
    print("for honest nodes means high probability = honest signal.")
    
    # Assertions
    assert m["precision"] >= 0.5, f"Precision too low: {m['precision']}"
    assert m["recall"] >= 0.3, f"Recall too low: {m['recall']}"
    print("\n✓ ASSERTIONS PASSED")


if __name__ == "__main__":
    demo()
