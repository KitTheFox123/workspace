#!/usr/bin/env python3
"""
sybilguard-walk.py — SybilGuard-inspired random walk sybil detection for ATF.

Based on Yu et al (SIGCOMM 2006): honest social graphs have fast mixing
(O(log n) mixing time). Sybil regions attached by few "attack edges."
Random walks from honest nodes stay in honest region with high probability.

Key insight for ATF: attestation graphs encode trust relationships.
Honest attestation graphs are sparse (trust is hard to earn) with no
small quotient cuts. Sybil clusters are dense (mutual inflation is free)
but attached to honest region by few edges.

Algorithm:
1. Start random walks from known-honest "seed" nodes
2. Walk length = O(sqrt(n * log n)) per SybilGuard
3. Count how many walks reach each node
4. Nodes reachable by many walks = likely honest (well-connected to honest region)
5. Nodes reachable by few/no walks = likely sybil (behind quotient cut)

Also implements: density analysis (sybil clusters have higher internal
density than honest regions) and quotient cut detection.

Kit 🦊 — 2026-03-28
"""

import random
import math
import json
from dataclasses import dataclass, field
from collections import Counter


@dataclass
class AttestationEdge:
    attester: str
    subject: str
    score: float
    bidirectional: bool = False  # Mutual attestation (sybil indicator)


class SybilGuardWalker:
    """Random walk sybil detection for attestation graphs."""
    
    def __init__(self):
        self.edges: list[AttestationEdge] = []
        self.adjacency: dict[str, list[str]] = {}
        self.nodes: set[str] = set()
    
    def add_edge(self, attester: str, subject: str, score: float = 0.5):
        self.edges.append(AttestationEdge(attester, subject, score))
        self.nodes.add(attester)
        self.nodes.add(subject)
        
        if attester not in self.adjacency:
            self.adjacency[attester] = []
        self.adjacency[attester].append(subject)
        
        # Treat attestation as undirected for random walk (trust is relational)
        if subject not in self.adjacency:
            self.adjacency[subject] = []
        self.adjacency[subject].append(attester)
    
    def random_walk(self, start: str, length: int) -> list[str]:
        """Single random walk from start node."""
        path = [start]
        current = start
        for _ in range(length):
            neighbors = self.adjacency.get(current, [])
            if not neighbors:
                break
            current = random.choice(neighbors)
            path.append(current)
        return path
    
    def sybilguard_classify(self, seeds: list[str], 
                             walks_per_seed: int = 100) -> dict[str, dict]:
        """
        SybilGuard classification.
        
        Walk length = O(sqrt(n * log n)) per original paper.
        Nodes reached by many walks from seeds = likely honest.
        """
        n = len(self.nodes)
        walk_length = max(3, int(math.sqrt(n * math.log(max(n, 2)))))
        
        # Count walks reaching each node
        reach_count: Counter = Counter()
        
        for seed in seeds:
            for _ in range(walks_per_seed):
                path = self.random_walk(seed, walk_length)
                for node in set(path):  # Count unique visits per walk
                    reach_count[node] += 1
        
        total_walks = len(seeds) * walks_per_seed
        
        # Classify
        results = {}
        for node in self.nodes:
            count = reach_count.get(node, 0)
            reach_fraction = count / total_walks
            
            # Threshold: nodes reached by < 10% of walks = suspect
            if reach_fraction >= 0.3:
                label = "HONEST"
            elif reach_fraction >= 0.1:
                label = "BORDERLINE"
            else:
                label = "SYBIL_SUSPECT"
            
            results[node] = {
                "reach_count": count,
                "reach_fraction": round(reach_fraction, 4),
                "label": label,
                "walk_length": walk_length,
            }
        
        return results
    
    def density_analysis(self) -> dict:
        """
        Analyze graph density to detect sybil clusters.
        
        Sybil insight: honest graphs are sparse (avg degree 5-8).
        Sybil clusters are dense (mutual inflation = high degree).
        """
        degrees = {}
        for node in self.nodes:
            degrees[node] = len(self.adjacency.get(node, []))
        
        if not degrees:
            return {"error": "empty graph"}
        
        avg_degree = sum(degrees.values()) / len(degrees)
        max_degree = max(degrees.values())
        
        # Detect mutual attestations (bidirectional = potential sybil signal)
        mutual_pairs = set()
        for edge in self.edges:
            reverse = (edge.subject, edge.attester)
            if any(e.attester == edge.subject and e.subject == edge.attester for e in self.edges):
                mutual_pairs.add(tuple(sorted([edge.attester, edge.subject])))
        
        mutual_rate = len(mutual_pairs) / max(len(self.edges), 1)
        
        # Clustering coefficient (local)
        clustering = {}
        for node in self.nodes:
            neighbors = set(self.adjacency.get(node, []))
            if len(neighbors) < 2:
                clustering[node] = 0.0
                continue
            # Count edges between neighbors
            neighbor_edges = 0
            for n1 in neighbors:
                for n2 in neighbors:
                    if n1 != n2 and n2 in self.adjacency.get(n1, []):
                        neighbor_edges += 1
            possible = len(neighbors) * (len(neighbors) - 1)
            clustering[node] = neighbor_edges / possible if possible > 0 else 0.0
        
        avg_clustering = sum(clustering.values()) / max(len(clustering), 1)
        
        return {
            "avg_degree": round(avg_degree, 2),
            "max_degree": max_degree,
            "mutual_attestation_rate": round(mutual_rate, 3),
            "avg_clustering": round(avg_clustering, 3),
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "density_assessment": (
                "HEALTHY" if avg_degree < 10 and mutual_rate < 0.4 and avg_clustering < 0.5
                else "SYBIL_SUSPECT" if mutual_rate > 0.6 or avg_clustering > 0.7
                else "MIXED"
            ),
            "sybilguard_note": (
                f"SybilGuard (Yu 2006): honest social networks have avg degree 5-8, "
                f"clustering ~0.3. Sybil regions have higher density due to free mutual inflation."
            )
        }
    
    def find_quotient_cuts(self, min_cut_ratio: float = 0.3) -> list[dict]:
        """
        Find suspicious quotient cuts (small edge set separating large node group).
        Not NP-hard optimal — greedy approximation using BFS expansion.
        """
        if len(self.nodes) < 4:
            return []
        
        cuts = []
        # Try expanding from each node, looking for bottlenecks
        for start in list(self.nodes)[:10]:  # Sample for performance
            visited = {start}
            frontier = set(self.adjacency.get(start, []))
            boundary_edges = len(frontier)
            
            while frontier and len(visited) < len(self.nodes) // 2:
                node = frontier.pop()
                visited.add(node)
                for neighbor in self.adjacency.get(node, []):
                    if neighbor not in visited:
                        frontier.add(neighbor)
                
                # Recalculate boundary
                boundary = 0
                for v in visited:
                    for n in self.adjacency.get(v, []):
                        if n not in visited:
                            boundary += 1
                
                quotient = boundary / max(len(visited), 1)
                if quotient < min_cut_ratio and len(visited) >= 3:
                    cuts.append({
                        "seed": start,
                        "partition_size": len(visited),
                        "boundary_edges": boundary,
                        "quotient": round(quotient, 3),
                        "nodes": sorted(visited),
                    })
                    break
        
        return cuts


def demo():
    random.seed(42)
    
    g = SybilGuardWalker()
    
    # Build honest region: sparse, well-connected
    honest = [f"h_{i}" for i in range(15)]
    for i in range(len(honest)):
        # Each honest node connected to 3-5 random others
        for _ in range(random.randint(3, 5)):
            j = random.choice([x for x in range(len(honest)) if x != i])
            g.add_edge(honest[i], honest[j], score=0.7 + random.random() * 0.3)
    
    # Build sybil region: dense, mutually attesting
    sybils = [f"s_{i}" for i in range(8)]
    for i in range(len(sybils)):
        for j in range(len(sybils)):
            if i != j:
                g.add_edge(sybils[i], sybils[j], score=0.9)
    
    # Attack edges: only 2 connections between regions
    g.add_edge(sybils[0], honest[0], score=0.5)
    g.add_edge(sybils[1], honest[3], score=0.4)
    
    print("=" * 60)
    print("SYBILGUARD WALK SIMULATION")
    print(f"Honest nodes: {len(honest)}, Sybil nodes: {len(sybils)}")
    print(f"Attack edges: 2")
    print("=" * 60)
    
    # Density analysis
    density = g.density_analysis()
    print(f"\nDENSITY ANALYSIS:")
    print(f"  Avg degree: {density['avg_degree']}")
    print(f"  Mutual attestation rate: {density['mutual_attestation_rate']}")
    print(f"  Avg clustering: {density['avg_clustering']}")
    print(f"  Assessment: {density['density_assessment']}")
    
    # SybilGuard classification (seeds = known honest nodes)
    seeds = honest[:3]  # 3 known-honest seeds
    results = g.sybilguard_classify(seeds, walks_per_seed=200)
    
    print(f"\nSYBILGUARD CLASSIFICATION (walk length: {results[honest[0]]['walk_length']}):")
    
    honest_correct = sum(1 for h in honest if results[h]["label"] == "HONEST")
    sybil_correct = sum(1 for s in sybils if results[s]["label"] == "SYBIL_SUSPECT")
    
    print(f"\n  Honest nodes classified correctly: {honest_correct}/{len(honest)}")
    for h in honest[:5]:
        r = results[h]
        print(f"    {h}: reach={r['reach_fraction']:.3f} → {r['label']}")
    
    print(f"\n  Sybil nodes classified correctly: {sybil_correct}/{len(sybils)}")
    for s in sybils:
        r = results[s]
        print(f"    {s}: reach={r['reach_fraction']:.3f} → {r['label']}")
    
    # Quotient cuts
    cuts = g.find_quotient_cuts(min_cut_ratio=0.5)
    print(f"\n  Suspicious quotient cuts found: {len(cuts)}")
    for cut in cuts[:3]:
        print(f"    Partition {cut['partition_size']} nodes, "
              f"{cut['boundary_edges']} boundary edges, "
              f"quotient={cut['quotient']}")
    
    print(f"\nSUMMARY:")
    print(f"  Honest precision: {honest_correct/len(honest):.0%}")
    print(f"  Sybil detection: {sybil_correct/len(sybils):.0%}")
    print(f"  Key: {len(sybils)} sybils connected by only 2 attack edges")
    print(f"  Random walks from honest seeds stay in honest region")
    
    # Assertions
    assert honest_correct >= len(honest) * 0.7, f"Too many honest misclassified: {honest_correct}"
    assert sybil_correct >= len(sybils) * 0.5, f"Too few sybils detected: {sybil_correct}"
    print("\nASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
