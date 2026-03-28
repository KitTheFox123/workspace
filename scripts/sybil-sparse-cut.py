#!/usr/bin/env python3
"""
sybil-sparse-cut.py — Detect sybil clusters via sparse cut analysis.

Core insight from SybilGuard (Yu et al, SIGCOMM 2006), SybilRank (Cao et al,
NSDI 2012), and Kurve & Kesidis (ICC 2011): sybil regions are DENSE internally
but connect to the honest region through a SPARSE CUT (few edges crossing).

This is because:
- Sybils can create unlimited fake identities (dense internal connections)
- But each sybil-honest connection requires a real social/trust relationship
- The bottleneck = attack edges crossing the cut

Algorithm:
1. Build attestation graph from trust interactions
2. Compute edge density per local neighborhood
3. Find communities via label propagation
4. Identify dense communities with sparse external connections
5. Flag as potential sybil clusters

Metric: cut ratio = external_edges / internal_edges
- Honest communities: high cut ratio (well-connected to broader network)
- Sybil clusters: low cut ratio (dense internal, sparse external)

Kit 🦊 — 2026-03-28
"""

import random
import json
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class TrustEdge:
    source: str
    target: str
    weight: float = 1.0
    timestamp: str = ""


@dataclass
class SybilDetectionResult:
    clusters: list[dict] = field(default_factory=list)
    flagged_agents: list[str] = field(default_factory=list)
    honest_agents: list[str] = field(default_factory=list)
    cut_ratio_threshold: float = 0.0
    graph_stats: dict = field(default_factory=dict)


class SparseCutDetector:
    """
    Detects sybil clusters using graph density + sparse cut analysis.
    
    SybilGuard insight: random walks from honest nodes rarely cross
    into sybil region (sparse cut = low crossing probability).
    SybilRank: trust propagated from seed nodes attenuates at cut.
    """
    
    def __init__(self, cut_ratio_threshold: float = 0.3):
        self.edges: list[TrustEdge] = []
        self.adjacency: dict[str, dict[str, float]] = defaultdict(dict)
        self.cut_ratio_threshold = cut_ratio_threshold
    
    def add_edge(self, source: str, target: str, weight: float = 1.0):
        self.edges.append(TrustEdge(source=source, target=target, weight=weight))
        self.adjacency[source][target] = weight
        self.adjacency[target][source] = weight  # Undirected for community detection
    
    def _label_propagation(self, max_iterations: int = 50) -> dict[str, int]:
        """Simple label propagation for community detection."""
        nodes = list(self.adjacency.keys())
        labels = {node: i for i, node in enumerate(nodes)}
        
        for _ in range(max_iterations):
            changed = False
            random.shuffle(nodes)
            for node in nodes:
                if not self.adjacency[node]:
                    continue
                # Count neighbor labels weighted by edge weight
                label_weights: dict[int, float] = defaultdict(float)
                for neighbor, weight in self.adjacency[node].items():
                    label_weights[labels[neighbor]] += weight
                
                if label_weights:
                    best_label = max(label_weights, key=label_weights.get)
                    if labels[node] != best_label:
                        labels[node] = best_label
                        changed = True
            
            if not changed:
                break
        
        return labels
    
    def _compute_cluster_metrics(self, labels: dict[str, int]) -> list[dict]:
        """Compute density and cut ratio for each community."""
        # Group nodes by label
        communities: dict[int, list[str]] = defaultdict(list)
        for node, label in labels.items():
            communities[label].append(node)
        
        results = []
        for label, members in communities.items():
            member_set = set(members)
            n = len(members)
            if n < 2:
                continue
            
            internal_edges = 0
            external_edges = 0
            
            for node in members:
                for neighbor, weight in self.adjacency[node].items():
                    if neighbor in member_set:
                        internal_edges += 1
                    else:
                        external_edges += 1
            
            # Each internal edge counted twice (undirected)
            internal_edges //= 2
            
            # Density = actual internal edges / possible internal edges
            max_internal = n * (n - 1) // 2
            density = internal_edges / max_internal if max_internal > 0 else 0
            
            # Cut ratio = external / internal (high = well-connected, low = insular)
            cut_ratio = external_edges / max(internal_edges, 1)
            
            results.append({
                "community_id": label,
                "members": members,
                "size": n,
                "internal_edges": internal_edges,
                "external_edges": external_edges,
                "density": round(density, 4),
                "cut_ratio": round(cut_ratio, 4),
                "is_sybil_candidate": density > 0.5 and cut_ratio < self.cut_ratio_threshold
            })
        
        return results
    
    def detect(self) -> SybilDetectionResult:
        """Run full sybil detection pipeline."""
        labels = self._label_propagation()
        cluster_metrics = self._compute_cluster_metrics(labels)
        
        flagged = []
        honest = []
        
        for cluster in cluster_metrics:
            if cluster["is_sybil_candidate"]:
                flagged.extend(cluster["members"])
            else:
                honest.extend(cluster["members"])
        
        all_nodes = list(self.adjacency.keys())
        avg_degree = sum(len(n) for n in self.adjacency.values()) / max(len(all_nodes), 1)
        
        return SybilDetectionResult(
            clusters=cluster_metrics,
            flagged_agents=flagged,
            honest_agents=honest,
            cut_ratio_threshold=self.cut_ratio_threshold,
            graph_stats={
                "total_nodes": len(all_nodes),
                "total_edges": len(self.edges),
                "avg_degree": round(avg_degree, 2),
                "num_communities": len(cluster_metrics),
                "num_flagged_communities": sum(1 for c in cluster_metrics if c["is_sybil_candidate"]),
            }
        )


def demo():
    random.seed(42)
    
    detector = SparseCutDetector(cut_ratio_threshold=0.3)
    
    # Build honest network: sparse, well-connected
    honest = [f"honest_{i}" for i in range(20)]
    for i in range(len(honest)):
        # Each honest node connects to 2-4 random others (sparse)
        num_connections = random.randint(2, 4)
        targets = random.sample([h for h in honest if h != honest[i]], num_connections)
        for t in targets:
            detector.add_edge(honest[i], t, weight=random.uniform(0.5, 1.0))
    
    # Build sybil cluster 1: dense, few connections to honest
    sybil1 = [f"sybil1_{i}" for i in range(8)]
    for i in range(len(sybil1)):
        for j in range(i + 1, len(sybil1)):
            # Dense: almost fully connected
            if random.random() < 0.85:
                detector.add_edge(sybil1[i], sybil1[j], weight=random.uniform(0.8, 1.0))
    # Sparse cut: only 2 attack edges
    detector.add_edge(sybil1[0], honest[0], weight=0.5)
    detector.add_edge(sybil1[1], honest[3], weight=0.4)
    
    # Build sybil cluster 2: smaller, very dense
    sybil2 = [f"sybil2_{i}" for i in range(5)]
    for i in range(len(sybil2)):
        for j in range(i + 1, len(sybil2)):
            detector.add_edge(sybil2[i], sybil2[j], weight=0.9)
    # Single attack edge
    detector.add_edge(sybil2[0], honest[10], weight=0.3)
    
    # Build legitimate dense group (e.g., a team): dense BUT well-connected externally
    team = [f"team_{i}" for i in range(5)]
    for i in range(len(team)):
        for j in range(i + 1, len(team)):
            detector.add_edge(team[i], team[j], weight=0.8)
    # Many external connections (not a sybil — just a team)
    for t in team:
        targets = random.sample(honest, 3)
        for h in targets:
            detector.add_edge(t, h, weight=random.uniform(0.4, 0.7))
    
    print("=" * 60)
    print("SYBIL SPARSE-CUT DETECTION")
    print("=" * 60)
    print("Graph: 20 honest + 8 sybil1 + 5 sybil2 + 5 team")
    print()
    
    result = detector.detect()
    
    print(f"Graph stats: {json.dumps(result.graph_stats, indent=2)}")
    print()
    
    for cluster in sorted(result.clusters, key=lambda c: c["cut_ratio"]):
        flag = "⚠ SYBIL" if cluster["is_sybil_candidate"] else "✓ OK"
        sample_members = cluster["members"][:3]
        prefix = sample_members[0].split("_")[0] if sample_members else "?"
        print(f"  [{flag}] Community (size={cluster['size']}, prefix={prefix})")
        print(f"    Density: {cluster['density']:.3f} | Cut ratio: {cluster['cut_ratio']:.3f}")
        print(f"    Internal: {cluster['internal_edges']} | External: {cluster['external_edges']}")
        print()
    
    print(f"Flagged: {len(result.flagged_agents)} agents")
    print(f"Honest: {len(result.honest_agents)} agents")
    print()
    
    # Verify: sybil clusters flagged, team and honest not flagged
    sybil_set = set(sybil1 + sybil2)
    team_set = set(team)
    honest_set = set(honest)
    flagged_set = set(result.flagged_agents)
    
    # Check sybils detected
    sybil_detected = len(flagged_set & sybil_set)
    team_falsely_flagged = len(flagged_set & team_set)
    honest_falsely_flagged = len(flagged_set & honest_set)
    
    print(f"Sybils correctly flagged: {sybil_detected}/{len(sybil_set)}")
    print(f"Team false positives: {team_falsely_flagged}/{len(team_set)}")
    print(f"Honest false positives: {honest_falsely_flagged}/{len(honest_set)}")
    print()
    
    # Key insight
    print("KEY INSIGHT: Dense ≠ sybil. Dense + sparse cut = sybil.")
    print("The team is dense but well-connected externally (high cut ratio).")
    print("Sybil clusters are dense AND insular (low cut ratio).")
    print("SybilGuard/SybilRank exploit this same structural difference.")


if __name__ == "__main__":
    demo()
