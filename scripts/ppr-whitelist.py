#!/usr/bin/env python3
"""
ppr-whitelist.py — Personalized PageRank local whitelisting for ATF.

Alvisi et al (IEEE S&P 2013, "SoK: The Evolution of Sybil Defense via
Social Networks"): Universal sybil defense FAILS because honest graphs
aren't homogeneous — they're communities loosely coupled. The fix:
Personalized PageRank (PPR) from honest seeds produces LOCAL whitelists
with provable guarantees.

Key insight: PPR cost = O(whitelist size), NOT O(network size).
ATF attestation chains from known seeds ARE PPR walks.

This implements PPR-based whitelisting for an agent trust graph:
1. Start from trusted seed(s) — genesis attesters
2. Random walk with teleport (alpha) back to seed
3. Rank all nodes by visit frequency
4. Top-k = whitelist

Sybil regions get low PPR because:
- Few attack edges connect sybil → honest (low conductance boundary)
- Random walks rarely cross into sybil region
- Even when they do, teleport pulls them back to honest seed

Kit 🦊 — 2026-03-29
"""

import random
import json
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class TrustGraph:
    """Directed weighted trust graph."""
    edges: dict[str, dict[str, float]] = field(default_factory=lambda: defaultdict(dict))
    # edges[a][b] = weight means a trusts b with weight
    
    def add_edge(self, src: str, dst: str, weight: float = 1.0):
        self.edges[src][dst] = weight
    
    def neighbors(self, node: str) -> dict[str, float]:
        return self.edges.get(node, {})
    
    def all_nodes(self) -> set[str]:
        nodes = set(self.edges.keys())
        for src in self.edges:
            nodes.update(self.edges[src].keys())
        return nodes


def personalized_pagerank(
    graph: TrustGraph,
    seeds: list[str],
    alpha: float = 0.15,   # Teleport probability (back to seed)
    num_walks: int = 10000,
    walk_length: int = 50,
) -> dict[str, float]:
    """
    Compute PPR via random walks with restart.
    
    alpha = probability of teleporting back to seed at each step.
    Higher alpha = more local (tighter whitelist).
    Lower alpha = more global (broader exploration).
    
    Alvisi: alpha ∈ [0.10, 0.20] typical for sybil defense.
    """
    visit_count: dict[str, int] = defaultdict(int)
    
    for _ in range(num_walks):
        # Start at random seed
        current = random.choice(seeds)
        visit_count[current] += 1
        
        for _ in range(walk_length):
            # Teleport back to seed?
            if random.random() < alpha:
                current = random.choice(seeds)
                visit_count[current] += 1
                continue
            
            # Walk to neighbor (weighted by trust)
            neighbors = graph.neighbors(current)
            if not neighbors:
                # Dead end → teleport
                current = random.choice(seeds)
                visit_count[current] += 1
                continue
            
            # Weighted random choice
            nodes = list(neighbors.keys())
            weights = [neighbors[n] for n in nodes]
            total = sum(weights)
            weights = [w / total for w in weights]
            
            current = random.choices(nodes, weights=weights, k=1)[0]
            visit_count[current] += 1
    
    # Normalize to probabilities
    total_visits = sum(visit_count.values())
    ppr = {node: count / total_visits for node, count in visit_count.items()}
    
    return dict(sorted(ppr.items(), key=lambda x: -x[1]))


def whitelist_from_ppr(ppr: dict[str, float], k: int) -> list[tuple[str, float]]:
    """Top-k nodes by PPR score = whitelist."""
    return [(node, score) for node, score in list(ppr.items())[:k]]


def build_test_graph() -> tuple[TrustGraph, list[str], list[str]]:
    """
    Build a test graph with honest community + sybil ring.
    
    Honest: 20 nodes, sparse connections (realistic trust network).
    Sybils: 10 nodes, dense internal connections (mutual attestation).
    Attack edges: 2 edges connecting sybil → honest (low conductance).
    """
    g = TrustGraph()
    honest = [f"honest_{i}" for i in range(20)]
    sybils = [f"sybil_{i}" for i in range(10)]
    
    # Honest community: sparse, organic trust
    # Two sub-communities (reflecting Alvisi's community structure)
    community_a = honest[:10]
    community_b = honest[10:]
    
    # Intra-community edges (moderate density)
    for comm in [community_a, community_b]:
        for i in range(len(comm)):
            for j in range(i + 1, len(comm)):
                if random.random() < 0.3:  # 30% edge probability
                    weight = random.uniform(0.5, 1.0)
                    g.add_edge(comm[i], comm[j], weight)
                    g.add_edge(comm[j], comm[i], weight * random.uniform(0.7, 1.0))
    
    # Inter-community edges (sparse — loosely coupled)
    for a in community_a:
        for b in community_b:
            if random.random() < 0.05:  # 5% edge probability
                weight = random.uniform(0.3, 0.7)
                g.add_edge(a, b, weight)
                g.add_edge(b, a, weight * random.uniform(0.5, 0.9))
    
    # Sybil ring: dense mutual attestation (cheap trust)
    for i in range(len(sybils)):
        for j in range(i + 1, len(sybils)):
            if random.random() < 0.8:  # 80% edge probability (dense!)
                g.add_edge(sybils[i], sybils[j], 0.95)
                g.add_edge(sybils[j], sybils[i], 0.95)
    
    # Attack edges: sybils try to connect to honest (few)
    attack_edges = [
        (sybils[0], honest[3], 0.6),
        (sybils[1], honest[7], 0.5),
    ]
    for src, dst, w in attack_edges:
        g.add_edge(src, dst, w)
        g.add_edge(dst, src, w * 0.3)  # Honest node gives low reciprocal trust
    
    return g, honest, sybils


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("PPR-BASED LOCAL WHITELISTING FOR ATF")
    print("Alvisi et al, IEEE S&P 2013")
    print("=" * 60)
    print()
    
    graph, honest, sybils = build_test_graph()
    all_nodes = graph.all_nodes()
    
    print(f"Graph: {len(all_nodes)} nodes ({len(honest)} honest, {len(sybils)} sybil)")
    print(f"Attack edges: 2 (low conductance boundary)")
    print()
    
    # Seed with known honest nodes (genesis attesters)
    seeds = ["honest_0", "honest_1", "honest_10"]
    print(f"Seeds: {seeds}")
    print()
    
    # Compute PPR
    ppr = personalized_pagerank(graph, seeds, alpha=0.15, num_walks=50000)
    
    # Whitelist top-15
    whitelist = whitelist_from_ppr(ppr, k=15)
    
    print("TOP-15 WHITELIST (by PPR score):")
    print("-" * 45)
    honest_in_wl = 0
    sybil_in_wl = 0
    for node, score in whitelist:
        is_sybil = node.startswith("sybil")
        marker = "⚠ SYBIL" if is_sybil else "✓ honest"
        print(f"  {node:15s}  PPR={score:.4f}  {marker}")
        if is_sybil:
            sybil_in_wl += 1
        else:
            honest_in_wl += 1
    
    print()
    print(f"Whitelist composition: {honest_in_wl} honest, {sybil_in_wl} sybil")
    print(f"Sybil infiltration rate: {sybil_in_wl / len(whitelist):.1%}")
    print()
    
    # Show sybil PPR scores vs honest
    honest_scores = [ppr.get(n, 0) for n in honest]
    sybil_scores = [ppr.get(n, 0) for n in sybils]
    
    avg_honest = sum(honest_scores) / max(len(honest_scores), 1)
    avg_sybil = sum(sybil_scores) / max(len(sybil_scores), 1)
    
    print(f"Average PPR score:")
    print(f"  Honest: {avg_honest:.4f}")
    print(f"  Sybil:  {avg_sybil:.4f}")
    print(f"  Ratio:  {avg_honest / max(avg_sybil, 0.0001):.1f}x")
    print()
    
    # Test different alpha values
    print("ALPHA SENSITIVITY (teleport probability):")
    print("-" * 50)
    for alpha in [0.05, 0.10, 0.15, 0.20, 0.30]:
        ppr_a = personalized_pagerank(graph, seeds, alpha=alpha, num_walks=20000)
        wl = whitelist_from_ppr(ppr_a, k=15)
        sybils_in = sum(1 for n, _ in wl if n.startswith("sybil"))
        print(f"  alpha={alpha:.2f}: {sybils_in}/15 sybils in whitelist "
              f"({'CLEAN' if sybils_in == 0 else 'INFILTRATED'})")
    
    print()
    print("KEY FINDINGS:")
    print("  1. PPR naturally isolates sybil region (low conductance boundary)")
    print("  2. Dense sybil connections DONT help — walks rarely enter")
    print("  3. Higher alpha = more local = cleaner whitelist (but smaller reach)")
    print("  4. Cost = O(walks × walk_length), independent of network size")
    print("  5. ATF attestation chains from seeds ARE PPR walks")
    print()
    
    # Assertions
    assert sybil_in_wl <= 2, f"Too many sybils in whitelist: {sybil_in_wl}"
    assert avg_honest > avg_sybil * 2, "Honest should score 2x+ higher than sybil"
    print("ALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
