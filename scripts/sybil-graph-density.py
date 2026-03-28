#!/usr/bin/env python3
"""
sybil-graph-density.py — Detect sybil clusters via graph density analysis.

Core insight (AAMAS 2025, Dehkordi & Zehmakan): sybils have little control
over their position in the overall network structure. While they can fake
profiles, content, and behavior, they can't fake graph topology.

Honest graphs: sparse, power-law degree distribution, low clustering
within attestation subgraphs (trust is hard to earn).

Sybil graphs: dense cliques, high clustering coefficient (free mutual
inflation), uniform degree distribution within cluster.

Detection method: compute local clustering coefficient + degree distribution
for each agent's neighborhood. High clustering + uniform degree = sybil signal.

Also from percolation research: sybil clusters percolate easily (dense =
well-connected giant component), honest clusters fragment under strict
thresholds (sparse = many small components).

Kit 🦊 — 2026-03-28
"""

import random
import json
import math
from dataclasses import dataclass, field
from collections import Counter


@dataclass
class AttestationGraph:
    """Directed graph of attestations between agents."""
    edges: dict[str, set[str]] = field(default_factory=dict)  # attester → set of subjects
    
    def add_edge(self, attester: str, subject: str):
        if attester not in self.edges:
            self.edges[attester] = set()
        self.edges[attester].add(subject)
    
    @property
    def nodes(self) -> set[str]:
        nodes = set()
        for a, subjects in self.edges.items():
            nodes.add(a)
            nodes.update(subjects)
        return nodes
    
    def neighbors(self, node: str) -> set[str]:
        """Undirected neighbors (attested or attested-by)."""
        out = self.edges.get(node, set())
        inc = {a for a, subs in self.edges.items() if node in subs}
        return out | inc
    
    def degree(self, node: str) -> int:
        return len(self.neighbors(node))
    
    def local_clustering(self, node: str) -> float:
        """
        Local clustering coefficient: fraction of pairs of neighbors
        that are also connected. High = clique-like = sybil signal.
        """
        nbrs = list(self.neighbors(node))
        k = len(nbrs)
        if k < 2:
            return 0.0
        
        # Count edges between neighbors
        connected = 0
        for i in range(len(nbrs)):
            for j in range(i + 1, len(nbrs)):
                a, b = nbrs[i], nbrs[j]
                if b in self.edges.get(a, set()) or a in self.edges.get(b, set()):
                    connected += 1
        
        max_edges = k * (k - 1) / 2
        return connected / max_edges
    
    def degree_distribution_uniformity(self, nodes: set[str]) -> float:
        """
        Gini coefficient of degree distribution within a subset.
        Low Gini (uniform) = sybil signal. High Gini (power-law) = honest.
        Returns 1 - Gini so higher = MORE uniform = MORE suspicious.
        """
        if not nodes:
            return 0.0
        
        degrees = sorted(self.degree(n) for n in nodes)
        n = len(degrees)
        if n == 0 or sum(degrees) == 0:
            return 1.0  # All zero = maximally uniform
        
        # Gini coefficient
        total = sum(degrees)
        cum = 0
        gini_sum = 0
        for i, d in enumerate(degrees):
            cum += d
            gini_sum += cum
        gini = 1 - (2 * gini_sum) / (n * total) + 1/n
        
        return 1 - gini  # Higher = more uniform = more suspicious


@dataclass
class SybilDetection:
    agent: str
    clustering_coeff: float
    degree: int
    sybil_score: float  # 0-1, higher = more likely sybil
    reasons: list[str] = field(default_factory=list)


class SybilGraphDetector:
    """
    Detect sybil clusters using graph structure analysis.
    
    Two signals:
    1. Local clustering coefficient > threshold → clique-like neighborhood
    2. Degree distribution within neighborhood is uniform → mutual inflation
    
    Honest agents: sparse connections, power-law degree distribution
    Sybils: dense connections, uniform degree distribution
    """
    
    CLUSTERING_THRESHOLD = 0.6  # Above = suspicious
    UNIFORMITY_THRESHOLD = 0.7  # Above = suspicious
    MIN_DEGREE_FOR_ANALYSIS = 3
    
    def __init__(self, graph: AttestationGraph):
        self.graph = graph
    
    def analyze_agent(self, agent: str) -> SybilDetection:
        cc = self.graph.local_clustering(agent)
        deg = self.graph.degree(agent)
        reasons = []
        score = 0.0
        
        if deg < self.MIN_DEGREE_FOR_ANALYSIS:
            return SybilDetection(
                agent=agent, clustering_coeff=cc, degree=deg,
                sybil_score=0.0, reasons=["Insufficient connections for analysis"]
            )
        
        # Signal 1: High clustering = clique
        if cc > self.CLUSTERING_THRESHOLD:
            score += 0.4 * (cc - self.CLUSTERING_THRESHOLD) / (1 - self.CLUSTERING_THRESHOLD)
            reasons.append(f"High clustering ({cc:.3f} > {self.CLUSTERING_THRESHOLD}): clique-like neighborhood")
        
        # Signal 2: Uniform degree in neighborhood
        nbrs = self.graph.neighbors(agent) | {agent}
        uniformity = self.graph.degree_distribution_uniformity(nbrs)
        if uniformity > self.UNIFORMITY_THRESHOLD:
            score += 0.3 * (uniformity - self.UNIFORMITY_THRESHOLD) / (1 - self.UNIFORMITY_THRESHOLD)
            reasons.append(f"Uniform degree ({uniformity:.3f} > {self.UNIFORMITY_THRESHOLD}): mutual inflation pattern")
        
        # Signal 3: Reciprocity ratio (bidirectional edges / total edges)
        outgoing = self.graph.edges.get(agent, set())
        incoming = {a for a, subs in self.graph.edges.items() if agent in subs}
        if outgoing and incoming:
            reciprocal = len(outgoing & incoming)
            total = len(outgoing | incoming)
            reciprocity = reciprocal / total if total > 0 else 0
            if reciprocity > 0.8:
                score += 0.3
                reasons.append(f"High reciprocity ({reciprocity:.2f}): mutual attestation ring")
        
        if not reasons:
            reasons.append("No sybil signals detected")
        
        return SybilDetection(
            agent=agent, clustering_coeff=cc, degree=deg,
            sybil_score=min(1.0, score), reasons=reasons
        )
    
    def detect_clusters(self) -> dict:
        """Analyze all agents and identify suspicious clusters."""
        results = {}
        for node in self.graph.nodes:
            results[node] = self.analyze_agent(node)
        
        suspicious = {k: v for k, v in results.items() if v.sybil_score > 0.3}
        honest = {k: v for k, v in results.items() if v.sybil_score <= 0.1}
        uncertain = {k: v for k, v in results.items() if 0.1 < v.sybil_score <= 0.3}
        
        return {
            "total_agents": len(results),
            "suspicious": len(suspicious),
            "honest": len(honest),
            "uncertain": len(uncertain),
            "results": {k: {
                "sybil_score": v.sybil_score,
                "clustering": v.clustering_coeff,
                "degree": v.degree,
                "reasons": v.reasons
            } for k, v in sorted(results.items(), key=lambda x: -x[1].sybil_score)}
        }


def demo():
    random.seed(42)
    g = AttestationGraph()
    
    # Honest network: sparse, power-law-ish
    honest = [f"honest_{i}" for i in range(15)]
    # Hub-and-spoke: a few hubs, many leaf nodes
    hubs = honest[:3]
    leaves = honest[3:]
    for hub in hubs:
        # Hubs connect to ~5 leaves each
        for leaf in random.sample(leaves, min(5, len(leaves))):
            g.add_edge(hub, leaf)
    # A couple cross-hub connections
    g.add_edge(hubs[0], hubs[1])
    g.add_edge(hubs[1], hubs[2])
    
    # Sybil cluster: dense, mutual attestation
    sybils = [f"sybil_{i}" for i in range(6)]
    for i in range(len(sybils)):
        for j in range(len(sybils)):
            if i != j:
                g.add_edge(sybils[i], sybils[j])  # Full clique
    
    # Attack edges: sybils try to connect to honest network
    g.add_edge(sybils[0], honest[0])
    g.add_edge(sybils[1], honest[1])
    
    print("=" * 60)
    print("SYBIL GRAPH DENSITY ANALYSIS")
    print("=" * 60)
    print(f"Honest agents: {len(honest)}, Sybil agents: {len(sybils)}")
    print(f"Total edges: {sum(len(s) for s in g.edges.values())}")
    print()
    
    detector = SybilGraphDetector(g)
    results = detector.detect_clusters()
    
    print(f"Suspicious: {results['suspicious']}")
    print(f"Honest: {results['honest']}")
    print(f"Uncertain: {results['uncertain']}")
    print()
    
    # Show top suspicious
    print("TOP SUSPICIOUS:")
    for name, data in list(results["results"].items())[:6]:
        if data["sybil_score"] > 0.1:
            print(f"  {name}: score={data['sybil_score']:.2f} clustering={data['clustering']:.3f} degree={data['degree']}")
            for r in data["reasons"]:
                print(f"    → {r}")
    
    print("\nHONEST AGENTS (sample):")
    honest_results = [(n, d) for n, d in results["results"].items() if d["sybil_score"] <= 0.1]
    for name, data in honest_results[:5]:
        print(f"  {name}: score={data['sybil_score']:.2f} clustering={data['clustering']:.3f} degree={data['degree']}")
    
    # Verify: all sybils should be flagged
    sybil_scores = [results["results"][s]["sybil_score"] for s in sybils if s in results["results"]]
    honest_scores = [results["results"][h]["sybil_score"] for h in honest if h in results["results"]]
    
    avg_sybil = sum(sybil_scores) / len(sybil_scores) if sybil_scores else 0
    avg_honest = sum(honest_scores) / len(honest_scores) if honest_scores else 0
    
    print(f"\nAvg sybil score (sybil nodes): {avg_sybil:.3f}")
    print(f"Avg sybil score (honest nodes): {avg_honest:.3f}")
    print(f"Separation: {avg_sybil - avg_honest:.3f}")
    
    assert avg_sybil > avg_honest, "Sybils should score higher than honest agents"
    assert avg_sybil > 0.3, "Sybils should be flagged as suspicious"
    print("\n✓ SYBIL DETECTION ASSERTIONS PASSED")
    
    print(f"\nKey insight (AAMAS 2025): sybils can fake profiles,")
    print(f"content, behavior — but not graph topology. Dense cliques")
    print(f"with uniform degree + high reciprocity = structural sybil signal.")


if __name__ == "__main__":
    demo()
