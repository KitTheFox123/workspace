#!/usr/bin/env python3
"""
sybil-density-detector.py — Detect sybil clusters via graph density analysis.

Core insight from AAMAS 2025 (Dehkordi & Zehmakan): sybils have very little
control over their network POSITION. They can fake profiles, content, timing
— but not their structural relationship to the honest graph.

Two density invariants:
1. Honest agents: sparse attestation (avg degree ~5-8, hard-earned trust)
2. Sybil rings: dense mutual attestation (free inflation → cliques)

SybilGuard (Yu 2006): random walks from honest nodes stay in honest region
(sparse = long walks). Random walks from sybil region quickly exit via
few attack edges. Trust that propagates TOO easily = dense region = sybil.

SybilRank (Cao 2012): early-terminated random walks from trusted seeds.
Honest nodes get high landing probability. Sybils: low (sparse attack edge
bottleneck limits probability flow into sybil region).

This detector uses local graph metrics to flag suspicious clusters:
- Local clustering coefficient (sybil cliques → high CC)
- Degree distribution anomaly (sybils have higher avg degree)
- Conductance (ratio of outgoing to internal edges — sybil clusters
  have low conductance = few edges to honest region)

Kit 🦊 — 2026-03-28
"""

import json
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AttestationEdge:
    attester: str
    subject: str
    score: float
    timestamp: str


@dataclass
class ClusterAnalysis:
    cluster_id: str
    agents: list[str]
    internal_edges: int
    external_edges: int
    avg_degree: float
    clustering_coefficient: float
    conductance: float
    max_possible_edges: int
    density: float
    verdict: str  # "HONEST", "SUSPICIOUS", "SYBIL"
    reasons: list[str] = field(default_factory=list)


class SybilDensityDetector:
    """Detect sybil clusters using graph density invariants."""
    
    # Thresholds from literature
    HONEST_AVG_DEGREE = 8.0      # Honest agents attest ~5-8 others
    SYBIL_DEGREE_MULTIPLIER = 3  # Sybils typically 3x+ honest degree
    DENSITY_THRESHOLD = 0.4      # Sybil clusters > 40% dense
    CONDUCTANCE_THRESHOLD = 0.15 # Sybil clusters < 15% conductance
    CC_THRESHOLD = 0.7           # Sybil cliques > 70% clustering coeff
    
    def __init__(self):
        self.edges: list[AttestationEdge] = []
        self.adjacency: dict[str, set[str]] = {}
    
    def add_edge(self, edge: AttestationEdge):
        self.edges.append(edge)
        self.adjacency.setdefault(edge.attester, set()).add(edge.subject)
        self.adjacency.setdefault(edge.subject, set())  # ensure node exists
    
    def _get_neighbors(self, node: str) -> set[str]:
        """Undirected neighbors (both directions)."""
        out = self.adjacency.get(node, set()).copy()
        for n, targets in self.adjacency.items():
            if node in targets:
                out.add(n)
        return out
    
    def _clustering_coefficient(self, node: str) -> float:
        """Local clustering coefficient: fraction of neighbor pairs that are connected."""
        neighbors = list(self._get_neighbors(node))
        if len(neighbors) < 2:
            return 0.0
        
        connected_pairs = 0
        total_pairs = 0
        for i in range(len(neighbors)):
            for j in range(i + 1, len(neighbors)):
                total_pairs += 1
                ni, nj = neighbors[i], neighbors[j]
                if nj in self._get_neighbors(ni):
                    connected_pairs += 1
        
        return connected_pairs / total_pairs if total_pairs > 0 else 0.0
    
    def analyze_cluster(self, cluster_agents: list[str], cluster_id: str = "0") -> ClusterAnalysis:
        """Analyze a cluster of agents for sybil indicators."""
        agent_set = set(cluster_agents)
        
        # Count internal vs external edges
        internal = 0
        external = 0
        for edge in self.edges:
            if edge.attester in agent_set and edge.subject in agent_set:
                internal += 1
            elif edge.attester in agent_set or edge.subject in agent_set:
                external += 1
        
        n = len(cluster_agents)
        max_edges = n * (n - 1) if n > 1 else 1  # directed graph
        density = internal / max_edges if max_edges > 0 else 0
        
        # Average degree within cluster
        degrees = []
        for agent in cluster_agents:
            in_cluster = len(self._get_neighbors(agent) & agent_set)
            degrees.append(in_cluster)
        avg_degree = sum(degrees) / len(degrees) if degrees else 0
        
        # Average clustering coefficient
        ccs = [self._clustering_coefficient(a) for a in cluster_agents]
        avg_cc = sum(ccs) / len(ccs) if ccs else 0
        
        # Conductance = external / (2 * internal + external)
        conductance = external / (2 * internal + external) if (2 * internal + external) > 0 else 1.0
        
        # Verdict
        reasons = []
        sybil_score = 0
        
        if density > self.DENSITY_THRESHOLD:
            reasons.append(f"High density: {density:.3f} > {self.DENSITY_THRESHOLD}")
            sybil_score += 1
        
        if avg_degree > self.HONEST_AVG_DEGREE * self.SYBIL_DEGREE_MULTIPLIER:
            reasons.append(f"Excessive degree: {avg_degree:.1f} > {self.HONEST_AVG_DEGREE * self.SYBIL_DEGREE_MULTIPLIER}")
            sybil_score += 1
        
        if conductance < self.CONDUCTANCE_THRESHOLD and n > 2:
            reasons.append(f"Low conductance: {conductance:.3f} < {self.CONDUCTANCE_THRESHOLD} (isolated cluster)")
            sybil_score += 1
        
        if avg_cc > self.CC_THRESHOLD:
            reasons.append(f"High clustering: {avg_cc:.3f} > {self.CC_THRESHOLD} (clique-like)")
            sybil_score += 1
        
        if sybil_score >= 3:
            verdict = "SYBIL"
        elif sybil_score >= 1:
            verdict = "SUSPICIOUS"
        else:
            verdict = "HONEST"
        
        return ClusterAnalysis(
            cluster_id=cluster_id,
            agents=cluster_agents,
            internal_edges=internal,
            external_edges=external,
            avg_degree=round(avg_degree, 2),
            clustering_coefficient=round(avg_cc, 3),
            conductance=round(conductance, 3),
            max_possible_edges=max_edges,
            density=round(density, 3),
            verdict=verdict,
            reasons=reasons
        )
    
    def detect_clusters(self, min_size: int = 3) -> list[ClusterAnalysis]:
        """Find connected components and analyze each."""
        # Simple BFS for connected components (undirected)
        visited = set()
        clusters = []
        
        all_nodes = set(self.adjacency.keys())
        for edge in self.edges:
            all_nodes.add(edge.attester)
            all_nodes.add(edge.subject)
        
        for start in all_nodes:
            if start in visited:
                continue
            # BFS
            component = []
            queue = [start]
            while queue:
                node = queue.pop(0)
                if node in visited:
                    continue
                visited.add(node)
                component.append(node)
                for neighbor in self._get_neighbors(node):
                    if neighbor not in visited:
                        queue.append(neighbor)
            
            if len(component) >= min_size:
                clusters.append(component)
        
        results = []
        for i, cluster in enumerate(clusters):
            results.append(self.analyze_cluster(cluster, cluster_id=str(i)))
        
        return sorted(results, key=lambda x: -x.density)


def demo():
    random.seed(42)
    detector = SybilDensityDetector()
    
    # Honest network: sparse, organic attestations
    honest_agents = [f"honest_{i}" for i in range(12)]
    # Each honest agent attests 2-4 others (sparse)
    for agent in honest_agents:
        targets = random.sample([a for a in honest_agents if a != agent], k=random.randint(2, 4))
        for target in targets:
            detector.add_edge(AttestationEdge(agent, target, random.uniform(0.5, 0.9), "2026-03-28T00:00:00Z"))
    
    # Sybil ring: dense mutual attestation
    sybil_agents = [f"sybil_{i}" for i in range(6)]
    # Every sybil attests every other sybil (clique)
    for i, a in enumerate(sybil_agents):
        for j, b in enumerate(sybil_agents):
            if i != j:
                detector.add_edge(AttestationEdge(a, b, random.uniform(0.85, 0.99), "2026-03-28T00:00:00Z"))
    # Few attack edges to honest network
    for sybil in sybil_agents[:2]:
        target = random.choice(honest_agents)
        detector.add_edge(AttestationEdge(sybil, target, 0.7, "2026-03-28T00:00:00Z"))
    
    # Mixed cluster: some honest, some suspicious
    mixed = [f"mixed_{i}" for i in range(5)]
    for i, a in enumerate(mixed):
        targets = random.sample([m for m in mixed if m != a], k=min(3, len(mixed)-1))
        for t in targets:
            detector.add_edge(AttestationEdge(a, t, random.uniform(0.6, 0.85), "2026-03-28T00:00:00Z"))
    # Connect mixed to honest
    for m in mixed[:3]:
        detector.add_edge(AttestationEdge(m, random.choice(honest_agents), 0.65, "2026-03-28T00:00:00Z"))
    
    print("=" * 60)
    print("SYBIL DENSITY DETECTION")
    print("=" * 60)
    print(f"Total agents: {len(honest_agents) + len(sybil_agents) + len(mixed)}")
    print(f"Total edges: {len(detector.edges)}")
    print()
    
    clusters = detector.detect_clusters(min_size=3)
    
    for c in clusters:
        print(f"Cluster {c.cluster_id}: {len(c.agents)} agents → {c.verdict}")
        print(f"  Density: {c.density}  Avg degree: {c.avg_degree}  CC: {c.clustering_coefficient}  Conductance: {c.conductance}")
        print(f"  Internal: {c.internal_edges}  External: {c.external_edges}")
        if c.reasons:
            for r in c.reasons:
                print(f"  ⚠ {r}")
        print(f"  Agents: {c.agents[:5]}{'...' if len(c.agents) > 5 else ''}")
        print()
    
    # Verify sybil ring detected
    sybil_cluster = next((c for c in clusters if any("sybil" in a for a in c.agents) and not any("honest" in a for a in c.agents)), None)
    if sybil_cluster:
        assert sybil_cluster.verdict == "SYBIL", f"Expected SYBIL, got {sybil_cluster.verdict}"
        print("✓ Sybil ring correctly identified")
    
    honest_cluster = next((c for c in clusters if all("honest" in a or "mixed" in a for a in c.agents) and any("honest" in a for a in c.agents)), None)
    if honest_cluster:
        assert honest_cluster.verdict in ["HONEST", "SUSPICIOUS"], f"Expected HONEST/SUSPICIOUS, got {honest_cluster.verdict}"
        print(f"✓ Honest network classified as {honest_cluster.verdict}")
    
    print("\n" + "=" * 60)
    print("KEY METRICS (from literature)")
    print("=" * 60)
    print("SybilGuard (Yu 2006): random walks stay in honest region")
    print("SybilRank (Cao 2012): trust seeds + early-terminated walks")
    print("AAMAS 2025 (Dehkordi): resistance = identity layer strength")
    print("Density gap: honest ~0.05-0.15, sybil ~0.5-1.0")
    print("Conductance: honest ~0.3+, sybil <0.15 (few attack edges)")


if __name__ == "__main__":
    demo()
