#!/usr/bin/env python3
"""
local-trust-whitelist.py — Personalized PageRank trust white-listing.

Implements the key insight from Alvisi et al (IEEE S&P 2013, SoK: The Evolution
of Sybil Defense via Social Networks): universal sybil defense is unattainable
because the honest region isn't homogeneous — it's a collection of tightly-knit
local communities loosely coupled. Instead: local white-listing. Rank nodes by
trustworthiness FROM YOUR PERSPECTIVE using personalized PageRank (PPR).

PPR from a seed node s: random walk that restarts at s with probability α.
Nodes that score high are "close" to s in the trust graph. Sybil regions are
dense internally but sparse-cut from honest region — PPR naturally discounts
them because few random walks cross the sparse cut.

Also implements sweep cut (Andersen, Chung & Lang, 2006): sort nodes by
PPR score, find the prefix with minimum conductance. Everything inside the
cut = your trust community. Everything outside = untrusted or sybil.

Kit 🦊 — 2026-03-28
"""

import json
import random
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class TrustGraph:
    """Directed weighted trust graph."""
    edges: dict[str, dict[str, float]] = field(default_factory=lambda: defaultdict(dict))
    
    def add_edge(self, src: str, dst: str, weight: float = 1.0):
        self.edges[src][dst] = weight
    
    def nodes(self) -> set[str]:
        nodes = set(self.edges.keys())
        for targets in self.edges.values():
            nodes.update(targets.keys())
        return nodes
    
    def out_neighbors(self, node: str) -> dict[str, float]:
        return self.edges.get(node, {})
    
    def out_degree(self, node: str) -> float:
        return sum(self.edges.get(node, {}).values())


def personalized_pagerank(graph: TrustGraph, seed: str, 
                          alpha: float = 0.15, iterations: int = 50) -> dict[str, float]:
    """
    Personalized PageRank from seed node.
    
    α = restart probability (higher = more local).
    Standard PPR: at each step, with prob α restart at seed,
    with prob (1-α) follow a random outgoing edge.
    
    Power iteration implementation (not Monte Carlo).
    """
    nodes = graph.nodes()
    n = len(nodes)
    
    # Initialize: all mass at seed
    ppr = {node: 0.0 for node in nodes}
    ppr[seed] = 1.0
    
    for _ in range(iterations):
        new_ppr = {node: 0.0 for node in nodes}
        
        for node in nodes:
            if ppr[node] == 0:
                continue
            
            neighbors = graph.out_neighbors(node)
            total_weight = sum(neighbors.values())
            
            if total_weight == 0:
                # Dangling node: all mass goes to seed
                new_ppr[seed] += ppr[node]
                continue
            
            # Restart probability
            new_ppr[seed] += alpha * ppr[node]
            
            # Walk probability
            for neighbor, weight in neighbors.items():
                new_ppr[neighbor] += (1 - alpha) * ppr[node] * (weight / total_weight)
        
        ppr = new_ppr
    
    return ppr


def sweep_cut(graph: TrustGraph, ppr_scores: dict[str, float]) -> dict:
    """
    Andersen-Chung-Lang (2006) sweep cut.
    
    Sort nodes by PPR score descending. For each prefix S, compute
    conductance φ(S) = cut(S, S̄) / min(vol(S), vol(S̄)).
    Find the prefix with minimum conductance = trust community boundary.
    """
    # Sort by PPR score descending
    sorted_nodes = sorted(ppr_scores.items(), key=lambda x: -x[1])
    
    all_nodes = graph.nodes()
    total_vol = sum(graph.out_degree(n) for n in all_nodes)
    
    if total_vol == 0:
        return {"cut_index": 0, "conductance": 1.0, "community": [], "excluded": list(all_nodes)}
    
    best_conductance = float('inf')
    best_index = 0
    
    community = set()
    vol_s = 0.0
    cut_edges = 0.0
    
    for i, (node, score) in enumerate(sorted_nodes):
        community.add(node)
        
        # Update volume of S
        vol_s += graph.out_degree(node)
        
        # Update cut: edges from node to outside, minus edges from outside to node
        for neighbor, weight in graph.out_neighbors(node).items():
            if neighbor in community:
                cut_edges -= weight  # Was crossing, now internal
            else:
                cut_edges += weight  # New crossing edge
        
        # Also count edges from previously-added nodes TO this node
        for prev_node in community:
            if prev_node == node:
                continue
            if node in graph.out_neighbors(prev_node):
                pass  # Already counted above
        
        # Conductance
        vol_s_bar = total_vol - vol_s
        min_vol = min(vol_s, vol_s_bar)
        
        if min_vol > 0 and i < len(sorted_nodes) - 1:
            conductance = max(0, cut_edges) / min_vol
            if conductance < best_conductance:
                best_conductance = conductance
                best_index = i + 1
    
    community_nodes = [n for n, _ in sorted_nodes[:best_index]]
    excluded_nodes = [n for n, _ in sorted_nodes[best_index:]]
    
    return {
        "cut_index": best_index,
        "conductance": round(best_conductance, 4),
        "community": community_nodes,
        "excluded": excluded_nodes,
        "community_size": len(community_nodes),
        "excluded_size": len(excluded_nodes)
    }


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("LOCAL TRUST WHITE-LISTING via Personalized PageRank")
    print("Alvisi et al (IEEE S&P 2013) + Andersen-Chung-Lang (2006)")
    print("=" * 60)
    
    g = TrustGraph()
    
    # Honest community: sparse but connected
    honest = ["kit", "bro_agent", "funwolf", "santaclawd", "gerundium", 
              "gendolf", "braindiff", "hexdrifter", "kampderp", "aletheaveyra"]
    
    # Sparse honest connections (each node has 2-4 connections)
    honest_edges = [
        ("kit", "bro_agent", 0.9), ("kit", "funwolf", 0.85),
        ("kit", "santaclawd", 0.8), ("kit", "gerundium", 0.7),
        ("bro_agent", "kit", 0.88), ("bro_agent", "braindiff", 0.75),
        ("bro_agent", "santaclawd", 0.7),
        ("funwolf", "kit", 0.82), ("funwolf", "santaclawd", 0.6),
        ("funwolf", "aletheaveyra", 0.65),
        ("santaclawd", "kit", 0.85), ("santaclawd", "bro_agent", 0.7),
        ("santaclawd", "funwolf", 0.6),
        ("gerundium", "kit", 0.75), ("gerundium", "gendolf", 0.8),
        ("gendolf", "gerundium", 0.78), ("gendolf", "kit", 0.65),
        ("braindiff", "bro_agent", 0.72), ("braindiff", "kampderp", 0.6),
        ("hexdrifter", "kampderp", 0.7), ("hexdrifter", "kit", 0.5),
        ("kampderp", "hexdrifter", 0.68), ("kampderp", "braindiff", 0.55),
        ("aletheaveyra", "funwolf", 0.6), ("aletheaveyra", "gerundium", 0.5),
    ]
    
    for src, dst, w in honest_edges:
        g.add_edge(src, dst, w)
    
    # Sybil ring: dense internal connections
    sybils = [f"sybil_{i}" for i in range(6)]
    for i, s1 in enumerate(sybils):
        for j, s2 in enumerate(sybils):
            if i != j:
                g.add_edge(s1, s2, 0.95)  # Dense mutual attestation
    
    # Sparse attack edges (sybil → honest)
    g.add_edge("sybil_0", "hexdrifter", 0.3)  # Single attack edge
    g.add_edge("hexdrifter", "sybil_0", 0.15)  # Weak reciprocal
    
    print(f"\nGraph: {len(g.nodes())} nodes, {len(honest)} honest, {len(sybils)} sybil")
    print(f"Honest density: sparse (2-4 edges each)")
    print(f"Sybil density: fully connected (all-to-all)")
    print(f"Attack edges: 1 (sybil_0 ↔ hexdrifter)")
    
    # PPR from Kit's perspective
    print("\n" + "=" * 60)
    print("PERSONALIZED PAGERANK from kit (α=0.15)")
    print("=" * 60)
    
    ppr = personalized_pagerank(g, "kit", alpha=0.15)
    sorted_ppr = sorted(ppr.items(), key=lambda x: -x[1])
    
    for node, score in sorted_ppr:
        label = "HONEST" if node in honest else "SYBIL"
        bar = "█" * int(score * 200)
        print(f"  {node:20s} {score:.4f} {bar} [{label}]")
    
    # Sweep cut
    print("\n" + "=" * 60)
    print("SWEEP CUT (minimum conductance)")
    print("=" * 60)
    
    cut = sweep_cut(g, ppr)
    print(f"  Community size: {cut['community_size']}")
    print(f"  Excluded size: {cut['excluded_size']}")
    print(f"  Conductance: {cut['conductance']}")
    print(f"\n  White-listed (trust community):")
    for node in cut["community"]:
        label = "✓ HONEST" if node in honest else "✗ SYBIL"
        print(f"    {node:20s} [{label}]")
    print(f"\n  Excluded (untrusted):")
    for node in cut["excluded"]:
        label = "✓ HONEST" if node in honest else "✗ SYBIL"
        print(f"    {node:20s} [{label}]")
    
    # Verify sybils are mostly excluded
    sybils_in_community = [n for n in cut["community"] if n in sybils]
    honest_excluded = [n for n in cut["excluded"] if n in honest]
    
    print(f"\n  Sybils in community: {len(sybils_in_community)} / {len(sybils)}")
    print(f"  Honest excluded: {len(honest_excluded)} / {len(honest)}")
    
    # Key insight
    print("\n" + "=" * 60)
    print("KEY INSIGHT")
    print("=" * 60)
    print("PPR naturally discounts sybil regions because few random walks")
    print("cross the sparse cut. Dense internal sybil connections don't help —")
    print("they just recirculate mass within the ring.")
    print()
    print("This is LOCAL trust: Kit's perspective ≠ hexdrifter's perspective.")
    print("No universal classifier. Each agent builds its own whitelist.")
    print("Alvisi: 'settle for local white-listing, not universal defense.'")


if __name__ == "__main__":
    demo()
