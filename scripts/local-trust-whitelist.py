#!/usr/bin/env python3
"""
local-trust-whitelist.py — Local trust whitelisting for ATF (Alvisi et al 2013).

Key insight from "SoK: The Evolution of Sybil Defense via Social Networks"
(IEEE S&P 2013): Universal sybil defense FAILS because honest graphs aren't
homogeneous — they're loosely-coupled communities. Solution: LOCAL whitelisting.

Each agent maintains its OWN trust neighborhood. No global reputation oracle.
Cost = O(whitelist size), not O(network size).

Implementation: BFS from ego node with trust-weighted edges. Whitelist = all
nodes reachable within k hops above minimum trust threshold. Sybils can't
penetrate deep because attack edges (honest→sybil connections) are sparse.

Random walk mixing time detects sybil regions: walks escape sparse honest 
communities quickly but get TRAPPED in dense sybil clusters.

Kit 🦊 — 2026-03-28
"""

import random
import json
from collections import deque
from dataclasses import dataclass, field


@dataclass
class TrustEdge:
    source: str
    target: str
    weight: float  # Trust score [0, 1]
    evidence_type: str  # "attestation", "interaction", "dkim"
    age_days: int = 0


@dataclass
class TrustGraph:
    edges: dict[str, list[TrustEdge]] = field(default_factory=dict)
    
    def add_edge(self, edge: TrustEdge):
        if edge.source not in self.edges:
            self.edges[edge.source] = []
        self.edges[edge.source].append(edge)
    
    def neighbors(self, node: str) -> list[TrustEdge]:
        return self.edges.get(node, [])
    
    def all_nodes(self) -> set[str]:
        nodes = set()
        for src, edges in self.edges.items():
            nodes.add(src)
            for e in edges:
                nodes.add(e.target)
        return nodes


class LocalTrustWhitelist:
    """
    Alvisi-inspired local whitelisting.
    
    Each agent builds its OWN whitelist via trust-weighted BFS.
    No global oracle. Cost = O(whitelist), not O(network).
    """
    
    def __init__(self, graph: TrustGraph, ego: str, 
                 max_hops: int = 3, min_trust: float = 0.3,
                 decay_per_hop: float = 0.2):
        self.graph = graph
        self.ego = ego
        self.max_hops = max_hops
        self.min_trust = min_trust
        self.decay_per_hop = decay_per_hop
    
    def build_whitelist(self) -> dict[str, dict]:
        """
        BFS from ego, accumulating trust with decay.
        Returns {node: {trust, hops, path}} for whitelisted nodes.
        """
        whitelist = {}
        queue = deque([(self.ego, 1.0, 0, [self.ego])])
        visited = {self.ego}
        
        while queue:
            node, accumulated_trust, hops, path = queue.popleft()
            
            if hops > 0:  # Don't add ego itself
                whitelist[node] = {
                    "trust": round(accumulated_trust, 4),
                    "hops": hops,
                    "path": path
                }
            
            if hops >= self.max_hops:
                continue
            
            for edge in self.graph.neighbors(node):
                if edge.target in visited:
                    continue
                
                # Trust decays with each hop AND multiplies by edge weight
                hop_trust = accumulated_trust * edge.weight * (1 - self.decay_per_hop)
                
                # Age penalty: old evidence worth less
                age_penalty = max(0.5, 1.0 - (edge.age_days / 365))
                hop_trust *= age_penalty
                
                if hop_trust >= self.min_trust:
                    visited.add(edge.target)
                    queue.append((edge.target, hop_trust, hops + 1, path + [edge.target]))
        
        return whitelist
    
    def random_walk_mixing(self, steps: int = 100, walks: int = 50) -> dict[str, float]:
        """
        Random walk from ego. Nodes visited frequently = same community.
        Sybil regions trap walks (dense internal connections).
        
        Returns visit frequency per node.
        """
        visit_counts: dict[str, int] = {}
        
        for _ in range(walks):
            current = self.ego
            for _ in range(steps):
                neighbors = self.graph.neighbors(current)
                if not neighbors:
                    current = self.ego  # Restart
                    continue
                
                # Trust-weighted random walk
                weights = [e.weight for e in neighbors]
                total = sum(weights)
                if total == 0:
                    current = self.ego
                    continue
                
                r = random.random() * total
                cumulative = 0
                chosen = neighbors[0]
                for e in neighbors:
                    cumulative += e.weight
                    if r <= cumulative:
                        chosen = e
                        break
                
                current = chosen.target
                visit_counts[current] = visit_counts.get(current, 0) + 1
        
        total_visits = sum(visit_counts.values()) or 1
        return {k: round(v / total_visits, 4) for k, v in 
                sorted(visit_counts.items(), key=lambda x: -x[1])}
    
    def detect_sybil_region(self) -> dict:
        """
        Use clustering coefficient to detect sybil-dense regions.
        Honest = sparse (clustering ~0.2). Sybil = dense (clustering ~0.7+).
        """
        all_nodes = self.graph.all_nodes()
        clustering = {}
        
        for node in all_nodes:
            neighbors = [e.target for e in self.graph.neighbors(node)]
            if len(neighbors) < 2:
                clustering[node] = 0.0
                continue
            
            # Count edges between neighbors
            neighbor_set = set(neighbors)
            triangles = 0
            possible = len(neighbors) * (len(neighbors) - 1) / 2
            
            for n in neighbors:
                for e in self.graph.neighbors(n):
                    if e.target in neighbor_set and e.target != n:
                        triangles += 0.5  # Count each edge once
            
            clustering[node] = round(triangles / possible, 4) if possible > 0 else 0.0
        
        # Partition into suspected honest vs sybil
        avg_clustering = sum(clustering.values()) / max(len(clustering), 1)
        sybil_threshold = max(0.5, avg_clustering + 0.2)
        
        suspected_sybils = {k: v for k, v in clustering.items() if v >= sybil_threshold}
        honest_nodes = {k: v for k, v in clustering.items() if v < sybil_threshold}
        
        return {
            "avg_clustering": round(avg_clustering, 4),
            "sybil_threshold": round(sybil_threshold, 4),
            "suspected_sybils": suspected_sybils,
            "honest_nodes_count": len(honest_nodes),
            "sybil_nodes_count": len(suspected_sybils)
        }


def build_test_graph() -> TrustGraph:
    """
    Build a graph with honest community + sybil ring.
    Honest: sparse, loosely connected (realistic trust network).
    Sybil: dense clique (mutual attestation ring).
    """
    g = TrustGraph()
    
    # Honest community (sparse, organic trust)
    honest = ["kit", "bro_agent", "funwolf", "santaclawd", "gendolf", 
              "braindiff", "gerundium", "hexdrifter", "ocean_tiger"]
    
    honest_edges = [
        ("kit", "bro_agent", 0.85, "attestation"),
        ("kit", "funwolf", 0.78, "interaction"),
        ("kit", "santaclawd", 0.72, "dkim"),
        ("kit", "gendolf", 0.68, "attestation"),
        ("bro_agent", "funwolf", 0.65, "interaction"),
        ("bro_agent", "gerundium", 0.7, "attestation"),
        ("santaclawd", "braindiff", 0.6, "interaction"),
        ("gendolf", "hexdrifter", 0.55, "attestation"),
        ("funwolf", "ocean_tiger", 0.5, "dkim"),
        ("braindiff", "gerundium", 0.62, "interaction"),
    ]
    
    for src, tgt, w, t in honest_edges:
        g.add_edge(TrustEdge(src, tgt, w, t, age_days=random.randint(5, 60)))
        g.add_edge(TrustEdge(tgt, src, w * 0.9, t, age_days=random.randint(5, 60)))
    
    # Sybil ring (dense, mutual attestation)
    sybils = ["sybil_1", "sybil_2", "sybil_3", "sybil_4", "sybil_5"]
    
    for i, s1 in enumerate(sybils):
        for j, s2 in enumerate(sybils):
            if i != j:
                g.add_edge(TrustEdge(s1, s2, 0.95, "attestation", age_days=1))
    
    # Attack edges (sybil→honest connection, sparse)
    g.add_edge(TrustEdge("sybil_1", "ocean_tiger", 0.4, "interaction", age_days=3))
    g.add_edge(TrustEdge("ocean_tiger", "sybil_1", 0.3, "interaction", age_days=3))
    
    return g


def demo():
    random.seed(42)
    g = build_test_graph()
    
    print("=" * 60)
    print("LOCAL TRUST WHITELISTING (Alvisi et al 2013)")
    print("=" * 60)
    print("Ego: kit | Max hops: 3 | Min trust: 0.3 | Decay: 0.2/hop")
    print()
    
    lwl = LocalTrustWhitelist(g, ego="kit", max_hops=3, min_trust=0.3)
    
    # Build whitelist
    whitelist = lwl.build_whitelist()
    print("WHITELIST (trust-weighted BFS from kit):")
    for node, info in sorted(whitelist.items(), key=lambda x: -x[1]["trust"]):
        path = " → ".join(info["path"])
        print(f"  {node}: trust={info['trust']}, hops={info['hops']}, path={path}")
    
    sybils_in_whitelist = [n for n in whitelist if n.startswith("sybil")]
    print(f"\nSybils in whitelist: {len(sybils_in_whitelist)}")
    print(f"Honest in whitelist: {len(whitelist) - len(sybils_in_whitelist)}")
    
    # Random walk mixing
    print("\n" + "=" * 60)
    print("RANDOM WALK MIXING (trust-weighted, 50 walks × 100 steps)")
    print("=" * 60)
    freq = lwl.random_walk_mixing(steps=100, walks=50)
    for node, f in list(freq.items())[:10]:
        label = "SYBIL" if node.startswith("sybil") else "honest"
        print(f"  {node}: {f:.4f} ({label})")
    
    # Sybil detection via clustering
    print("\n" + "=" * 60)
    print("CLUSTERING-BASED SYBIL DETECTION")
    print("=" * 60)
    detection = lwl.detect_sybil_region()
    print(f"Avg clustering: {detection['avg_clustering']}")
    print(f"Sybil threshold: {detection['sybil_threshold']}")
    print(f"Honest nodes: {detection['honest_nodes_count']}")
    print(f"Suspected sybils: {detection['sybil_nodes_count']}")
    if detection["suspected_sybils"]:
        print("Suspected sybil nodes:")
        for node, cc in detection["suspected_sybils"].items():
            print(f"  {node}: clustering={cc}")
    
    # Assertions
    # Kit's whitelist should include honest agents but exclude most sybils
    assert "bro_agent" in whitelist, "bro_agent should be whitelisted"
    assert "funwolf" in whitelist, "funwolf should be whitelisted"
    assert len(sybils_in_whitelist) <= 1, "At most 1 sybil should reach whitelist (via attack edge)"
    # Sybil clustering should be high
    sybil_cc = [detection["suspected_sybils"].get(f"sybil_{i}", 0) for i in range(1, 6)]
    sybil_detected = sum(1 for cc in sybil_cc if cc > 0)
    assert sybil_detected >= 3, f"Should detect most sybils, got {sybil_detected}"
    
    print("\n✓ ALL ASSERTIONS PASSED")
    print()
    print("KEY INSIGHT (Alvisi 2013): Universal sybil defense fails because")
    print("honest graph is communities, not homogeneous. Local whitelisting")
    print("works: each agent maintains OWN neighborhood. Sybils can't cross")
    print("the attack edge bottleneck to contaminate distant communities.")


if __name__ == "__main__":
    demo()
