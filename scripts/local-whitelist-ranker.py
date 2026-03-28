#!/usr/bin/env python3
"""
local-whitelist-ranker.py — Local sybil-resistant white-listing via random walks.

Based on Alvisi et al 2013 (SoK: Evolution of Sybil Defense via Social Networks):
- Universal sybil defense FAILS: honest graph isn't homogeneous, it's communities
- LOCAL white-listing works: rank nodes by trustworthiness within your neighborhood
- Cost = O(white-list size), not O(total network)
- Key metric: CONDUCTANCE (mixing time of random walks)
  - Honest subgraph: fast-mixing (high conductance within community)
  - Sybil subgraph: slow-mixing to honest region (few attack edges)
  - Random walks from honest seeds stay in honest region

Implementation: personalized random walk from a seed node (the requester).
Walk probability accumulates at nodes. Honest neighbors get high rank
(walk stays local). Sybils get low rank (walk leaks through attack edges
and dissipates in dense sybil region).

Also integrates: SybilRank (Cao et al 2012), which uses early-terminated
random walks + degree-normalization to rank nodes.

Kit 🦊 — 2026-03-28
"""

import random
import json
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Node:
    id: str
    is_honest: bool = True
    trust_score: float = 0.0


class TrustGraph:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, set[str]] = defaultdict(set)
    
    def add_node(self, node_id: str, honest: bool = True):
        self.nodes[node_id] = Node(id=node_id, is_honest=honest)
        if node_id not in self.edges:
            self.edges[node_id] = set()
    
    def add_edge(self, a: str, b: str):
        self.edges[a].add(b)
        self.edges[b].add(a)
    
    def degree(self, node_id: str) -> int:
        return len(self.edges.get(node_id, set()))


class LocalWhitelistRanker:
    """
    Rank nodes by trustworthiness using personalized random walks.
    
    The walk starts at a seed (the requesting agent). At each step:
    - With probability alpha (teleport), return to seed
    - With probability (1-alpha), walk to random neighbor
    
    After many steps, visit frequency = trust rank.
    Honest neighbors get high rank. Sybils behind few attack edges
    get low rank because the walk rarely crosses.
    
    This is essentially personalized PageRank / SybilRank hybrid.
    """
    
    def __init__(self, graph: TrustGraph, alpha: float = 0.15, 
                 walk_length: int = 20, num_walks: int = 1000):
        self.graph = graph
        self.alpha = alpha  # Teleport probability (stay local)
        self.walk_length = walk_length
        self.num_walks = num_walks
    
    def rank(self, seed: str, whitelist_size: int = 10) -> list[dict]:
        """
        Generate a local whitelist of size k, ranked by trust.
        
        Cost: O(num_walks * walk_length) — independent of total network size.
        This is the key insight from Alvisi et al: local defense scales.
        """
        visit_count: dict[str, float] = defaultdict(float)
        
        for _ in range(self.num_walks):
            current = seed
            for step in range(self.walk_length):
                # Degree-normalized visit (SybilRank style)
                degree = self.graph.degree(current)
                if degree > 0:
                    visit_count[current] += 1.0 / degree
                else:
                    visit_count[current] += 1.0
                
                # Teleport or walk
                if random.random() < self.alpha:
                    current = seed  # Return to seed
                else:
                    neighbors = list(self.graph.edges.get(current, set()))
                    if neighbors:
                        current = random.choice(neighbors)
                    else:
                        current = seed
        
        # Normalize
        total = sum(visit_count.values())
        if total > 0:
            for k in visit_count:
                visit_count[k] /= total
        
        # Sort and return top-k (excluding seed)
        ranked = sorted(
            [(nid, score) for nid, score in visit_count.items() if nid != seed],
            key=lambda x: -x[1]
        )
        
        return [
            {
                "node": nid,
                "trust_rank": round(score, 6),
                "is_honest": self.graph.nodes[nid].is_honest,
                "degree": self.graph.degree(nid)
            }
            for nid, score in ranked[:whitelist_size]
        ]
    
    def evaluate_whitelist(self, whitelist: list[dict]) -> dict:
        """Evaluate whitelist quality: precision (honest fraction)."""
        if not whitelist:
            return {"precision": 0.0, "size": 0}
        
        honest = sum(1 for w in whitelist if w["is_honest"])
        return {
            "size": len(whitelist),
            "honest_count": honest,
            "sybil_count": len(whitelist) - honest,
            "precision": round(honest / len(whitelist), 4)
        }


def build_test_graph(n_honest: int = 50, n_sybil: int = 30, 
                     honest_edges: int = 150, sybil_internal_edges: int = 200,
                     attack_edges: int = 3) -> TrustGraph:
    """
    Build a graph with:
    - Honest region: sparse, community-structured (high local conductance)
    - Sybil region: dense (mutual inflation)
    - Few attack edges connecting them (low cross-conductance)
    """
    g = TrustGraph()
    
    # Honest nodes
    honest_ids = [f"h_{i}" for i in range(n_honest)]
    for hid in honest_ids:
        g.add_node(hid, honest=True)
    
    # Honest edges (sparse, community structure)
    for _ in range(honest_edges):
        a, b = random.sample(honest_ids, 2)
        g.add_edge(a, b)
    
    # Sybil nodes
    sybil_ids = [f"s_{i}" for i in range(n_sybil)]
    for sid in sybil_ids:
        g.add_node(sid, honest=False)
    
    # Sybil internal edges (dense — free mutual inflation)
    for _ in range(sybil_internal_edges):
        a, b = random.sample(sybil_ids, 2)
        g.add_edge(a, b)
    
    # Attack edges (few — the bottleneck)
    for _ in range(attack_edges):
        h = random.choice(honest_ids)
        s = random.choice(sybil_ids)
        g.add_edge(h, s)
    
    return g, honest_ids, sybil_ids


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("LOCAL WHITELIST RANKER — Sybil-Resistant Trust Ranking")
    print("Based on Alvisi et al 2013 (SoK: Sybil Defense)")
    print("=" * 60)
    
    # Build test graph
    g, honest_ids, sybil_ids = build_test_graph(
        n_honest=50, n_sybil=30,
        honest_edges=150, sybil_internal_edges=200,
        attack_edges=3
    )
    
    print(f"\nGraph: {len(honest_ids)} honest, {len(sybil_ids)} sybil, "
          f"3 attack edges")
    print(f"Honest avg degree: {sum(g.degree(h) for h in honest_ids) / len(honest_ids):.1f}")
    print(f"Sybil avg degree: {sum(g.degree(s) for s in sybil_ids) / len(sybil_ids):.1f}")
    
    ranker = LocalWhitelistRanker(g, alpha=0.15, walk_length=20, num_walks=2000)
    
    # Test 1: Honest seed
    print(f"\n{'='*60}")
    print("TEST 1: Honest seed (h_0) requesting whitelist of 15")
    print("=" * 60)
    
    wl = ranker.rank("h_0", whitelist_size=15)
    eval1 = ranker.evaluate_whitelist(wl)
    
    print(f"Top 5:")
    for w in wl[:5]:
        label = "✓" if w["is_honest"] else "✗ SYBIL"
        print(f"  {w['node']}: rank={w['trust_rank']:.6f} deg={w['degree']} {label}")
    
    print(f"\nWhitelist quality: {eval1}")
    
    # Test 2: Different honest seed
    print(f"\n{'='*60}")
    print("TEST 2: Different honest seed (h_25)")
    print("=" * 60)
    
    wl2 = ranker.rank("h_25", whitelist_size=15)
    eval2 = ranker.evaluate_whitelist(wl2)
    
    print(f"Top 5:")
    for w in wl2[:5]:
        label = "✓" if w["is_honest"] else "✗ SYBIL"
        print(f"  {w['node']}: rank={w['trust_rank']:.6f} deg={w['degree']} {label}")
    
    print(f"\nWhitelist quality: {eval2}")
    
    # Test 3: More attack edges (weaker boundary)
    print(f"\n{'='*60}")
    print("TEST 3: Weaker boundary (15 attack edges)")
    print("=" * 60)
    
    g2, h2, s2 = build_test_graph(
        n_honest=50, n_sybil=30,
        honest_edges=150, sybil_internal_edges=200,
        attack_edges=15  # Much weaker boundary
    )
    ranker2 = LocalWhitelistRanker(g2, alpha=0.15, walk_length=20, num_walks=2000)
    wl3 = ranker2.rank("h_0", whitelist_size=15)
    eval3 = ranker2.evaluate_whitelist(wl3)
    
    print(f"Top 5:")
    for w in wl3[:5]:
        label = "✓" if w["is_honest"] else "✗ SYBIL"
        print(f"  {w['node']}: rank={w['trust_rank']:.6f} deg={w['degree']} {label}")
    
    print(f"\nWhitelist quality: {eval3}")
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print("=" * 60)
    print(f"3 attack edges:  precision={eval1['precision']:.1%} (honest seed h_0)")
    print(f"3 attack edges:  precision={eval2['precision']:.1%} (honest seed h_25)")  
    print(f"15 attack edges: precision={eval3['precision']:.1%} (weaker boundary)")
    print()
    print("KEY INSIGHT (Alvisi et al):")
    print("  - Few attack edges → random walks stay honest → high precision")
    print("  - More attack edges → walks leak to sybils → precision drops")
    print("  - The BOUNDARY is the bottleneck, not detection algorithm")
    print("  - Defense in depth: make attack edges expensive to create")
    print("  - DKIM chains + behavioral consistency = expensive attack edges")
    
    # Assertions
    assert eval1["precision"] >= 0.8, f"Precision too low: {eval1['precision']}"
    assert eval3["precision"] < eval1["precision"], "Weaker boundary should have lower precision"
    print("\nALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
