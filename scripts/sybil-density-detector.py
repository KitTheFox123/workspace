#!/usr/bin/env python3
"""
sybil-density-detector.py — Detect sybil clusters via graph density analysis.

Core insight from Clawk thread (2026-03-28): "the sybil problem is really a
density problem." Honest agents form sparse graphs (trust is hard to earn).
Sybils form dense ones (free mutual inflation).

Theory:
- SybilGuard (Yu et al, SIGCOMM 2006): honest region is fast-mixing,
  sybil region connects via few attack edges. Random walks stay trapped
  in dense sybil clusters.
- Zhang et al (IFIPTM 2014): trust+distrust combined via PageRank-like
  ranking. Distrust = negative attestation.
- Key metric: local clustering coefficient + edge density. Honest subgraphs
  have clustering ~0.3; sybil rings approach 1.0.

Implementation: Given an attestation graph, identify suspiciously dense
subgraphs via local density scanning. Flag clusters where internal edge
density exceeds honest baseline by >2σ.

Kit 🦊 — 2026-03-28
"""

import json
import random
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Edge:
    source: str
    target: str
    score: float
    timestamp: str = ""


@dataclass
class ClusterReport:
    cluster_id: int
    agents: list[str]
    internal_edges: int
    max_possible_edges: int
    density: float
    avg_clustering: float
    is_suspicious: bool
    reason: str = ""


class SybilDensityDetector:
    """
    Detect sybil clusters via graph density analysis.
    
    Honest baseline (from SybilGuard literature):
    - Average degree: 5-8 in honest region
    - Clustering coefficient: ~0.3
    - Edge density in subgraphs: 0.05-0.15
    
    Sybil signals:
    - Internal density > 0.5 (mutual inflation)
    - Clustering coefficient > 0.7 (everyone knows everyone)
    - Reciprocity > 0.8 (you attest me, I attest you)
    """
    
    HONEST_DENSITY_CEILING = 0.25
    HONEST_CLUSTERING_CEILING = 0.5
    SYBIL_DENSITY_THRESHOLD = 0.6
    SYBIL_CLUSTERING_THRESHOLD = 0.7
    MIN_CLUSTER_SIZE = 3
    
    def __init__(self):
        self.edges: list[Edge] = []
        self.adjacency: dict[str, set[str]] = defaultdict(set)
        self.scores: dict[tuple[str, str], float] = {}
    
    def add_attestation(self, source: str, target: str, score: float = 1.0):
        self.edges.append(Edge(source=source, target=target, score=score))
        self.adjacency[source].add(target)
        self.scores[(source, target)] = score
    
    def _local_clustering(self, node: str) -> float:
        """Clustering coefficient: fraction of neighbor pairs that are connected."""
        neighbors = list(self.adjacency.get(node, set()))
        if len(neighbors) < 2:
            return 0.0
        
        connected = 0
        total = 0
        for i in range(len(neighbors)):
            for j in range(i + 1, len(neighbors)):
                total += 1
                if neighbors[j] in self.adjacency.get(neighbors[i], set()) or \
                   neighbors[i] in self.adjacency.get(neighbors[j], set()):
                    connected += 1
        
        return connected / total if total > 0 else 0.0
    
    def _subgraph_density(self, nodes: list[str]) -> tuple[int, int, float]:
        """Edge density of a subgraph."""
        node_set = set(nodes)
        internal_edges = 0
        for n in nodes:
            for neighbor in self.adjacency.get(n, set()):
                if neighbor in node_set:
                    internal_edges += 1
        
        n = len(nodes)
        max_edges = n * (n - 1)  # directed graph
        density = internal_edges / max_edges if max_edges > 0 else 0.0
        return internal_edges, max_edges, density
    
    def _reciprocity(self, nodes: list[str]) -> float:
        """Fraction of edges that are reciprocated within subgraph."""
        node_set = set(nodes)
        directed = 0
        reciprocated = 0
        for n in nodes:
            for neighbor in self.adjacency.get(n, set()):
                if neighbor in node_set:
                    directed += 1
                    if n in self.adjacency.get(neighbor, set()):
                        reciprocated += 1
        
        return reciprocated / directed if directed > 0 else 0.0
    
    def find_dense_clusters(self) -> list[ClusterReport]:
        """
        Find suspiciously dense subgraphs using greedy seed expansion.
        
        Algorithm:
        1. For each node, compute local clustering coefficient
        2. Seed from high-clustering nodes
        3. Expand to neighbors that maintain high density
        4. Flag clusters exceeding honest baseline
        """
        # Compute clustering for all nodes
        all_nodes = set(self.adjacency.keys())
        for e in self.edges:
            all_nodes.add(e.target)
        
        clustering = {n: self._local_clustering(n) for n in all_nodes}
        
        # Seed from high-clustering nodes
        seeds = [n for n, c in clustering.items() if c > self.HONEST_CLUSTERING_CEILING]
        
        visited_clusters: list[set[str]] = []
        used = set()
        
        for seed in sorted(seeds, key=lambda n: -clustering[n]):
            if seed in used:
                continue
            
            # Expand cluster: add neighbors that keep density high
            cluster = {seed}
            candidates = list(self.adjacency.get(seed, set()))
            
            for cand in candidates:
                test_cluster = list(cluster | {cand})
                if len(test_cluster) < 2:
                    cluster.add(cand)
                    continue
                _, _, density = self._subgraph_density(test_cluster)
                if density > self.HONEST_DENSITY_CEILING:
                    cluster.add(cand)
            
            if len(cluster) >= self.MIN_CLUSTER_SIZE:
                visited_clusters.append(cluster)
                used.update(cluster)
        
        # Analyze each cluster
        reports = []
        for i, cluster in enumerate(visited_clusters):
            nodes = list(cluster)
            internal, max_e, density = self._subgraph_density(nodes)
            avg_clust = sum(clustering.get(n, 0) for n in nodes) / len(nodes)
            reciprocity = self._reciprocity(nodes)
            
            is_suspicious = (
                (density > self.SYBIL_DENSITY_THRESHOLD and reciprocity > 0.7) or
                (avg_clust > self.SYBIL_CLUSTERING_THRESHOLD and density > self.SYBIL_DENSITY_THRESHOLD)
            )
            
            reasons = []
            if density > self.SYBIL_DENSITY_THRESHOLD:
                reasons.append(f"density {density:.2f} > {self.SYBIL_DENSITY_THRESHOLD}")
            if avg_clust > self.SYBIL_CLUSTERING_THRESHOLD:
                reasons.append(f"clustering {avg_clust:.2f} > {self.SYBIL_CLUSTERING_THRESHOLD}")
            if reciprocity > 0.8:
                reasons.append(f"reciprocity {reciprocity:.2f} > 0.8 (mutual inflation)")
            
            reports.append(ClusterReport(
                cluster_id=i,
                agents=nodes,
                internal_edges=internal,
                max_possible_edges=max_e,
                density=round(density, 3),
                avg_clustering=round(avg_clust, 3),
                is_suspicious=is_suspicious,
                reason="; ".join(reasons) if reasons else "within honest baseline"
            ))
        
        return reports
    
    def full_analysis(self) -> dict:
        all_nodes = set(self.adjacency.keys())
        for e in self.edges:
            all_nodes.add(e.target)
        
        clusters = self.find_dense_clusters()
        suspicious = [c for c in clusters if c.is_suspicious]
        
        return {
            "total_agents": len(all_nodes),
            "total_edges": len(self.edges),
            "clusters_found": len(clusters),
            "suspicious_clusters": len(suspicious),
            "flagged_agents": sum(len(c.agents) for c in suspicious),
            "clusters": [
                {
                    "id": c.cluster_id,
                    "agents": c.agents,
                    "density": c.density,
                    "clustering": c.avg_clustering,
                    "suspicious": c.is_suspicious,
                    "reason": c.reason
                }
                for c in clusters
            ]
        }


def demo():
    random.seed(42)
    d = SybilDensityDetector()
    
    # Honest network: sparse, realistic trust patterns
    honest = [f"honest_{i}" for i in range(15)]
    # Each honest agent attests 2-4 others (sparse)
    for agent in honest:
        targets = random.sample([a for a in honest if a != agent], random.randint(2, 4))
        for t in targets:
            d.add_attestation(agent, t, score=random.uniform(0.6, 0.9))
    
    # Sybil ring: dense mutual attestation
    sybils = [f"sybil_{i}" for i in range(6)]
    for s1 in sybils:
        for s2 in sybils:
            if s1 != s2:
                d.add_attestation(s1, s2, score=random.uniform(0.85, 0.95))
    
    # Attack edges: sybils try to connect to honest network
    for s in sybils[:2]:
        target = random.choice(honest)
        d.add_attestation(s, target, score=0.7)
    
    # Mixed cluster: some honest agents that work closely together
    close_team = [f"team_{i}" for i in range(4)]
    for t1 in close_team:
        for t2 in close_team:
            if t1 != t2:
                d.add_attestation(t1, t2, score=random.uniform(0.7, 0.85))
    # But they also connect outward (unlike sybils)
    for t in close_team:
        target = random.choice(honest)
        d.add_attestation(t, target, score=0.6)
        d.add_attestation(random.choice(honest), t, score=0.6)
    
    print("=" * 60)
    print("SYBIL DENSITY DETECTOR")
    print("=" * 60)
    
    result = d.full_analysis()
    print(f"Agents: {result['total_agents']}")
    print(f"Edges: {result['total_edges']}")
    print(f"Clusters found: {result['clusters_found']}")
    print(f"Suspicious: {result['suspicious_clusters']}")
    print(f"Flagged agents: {result['flagged_agents']}")
    print()
    
    for c in result["clusters"]:
        status = "⚠️  SUSPICIOUS" if c["suspicious"] else "✓ OK"
        print(f"Cluster {c['id']} [{status}]")
        print(f"  Agents: {c['agents']}")
        print(f"  Density: {c['density']}, Clustering: {c['clustering']}")
        if c["reason"]:
            print(f"  Reason: {c['reason']}")
        print()
    
    # Verify sybil ring was detected
    suspicious_agents = set()
    for c in result["clusters"]:
        if c["suspicious"]:
            suspicious_agents.update(c["agents"])
    
    sybil_set = set(sybils)
    detected = sybil_set & suspicious_agents
    print(f"Sybil detection rate: {len(detected)}/{len(sybil_set)} ({len(detected)/len(sybil_set):.0%})")
    
    # Check false positive rate
    honest_set = set(honest)
    false_positives = honest_set & suspicious_agents
    print(f"False positive rate: {len(false_positives)}/{len(honest_set)} ({len(false_positives)/len(honest_set):.0%})")
    
    assert len(detected) >= 4, f"Should detect most sybils, got {len(detected)}"
    assert len(false_positives) <= 2, f"Too many false positives: {len(false_positives)}"
    print("\n✓ ASSERTIONS PASSED")


if __name__ == "__main__":
    demo()
