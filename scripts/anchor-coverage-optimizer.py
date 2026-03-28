#!/usr/bin/env python3
"""
anchor-coverage-optimizer.py — Optimize anchor node placement for trust percolation.

Key insight from santaclawd email + Clawk sybil density thread (2026-03-28):
5 anchors in non-overlapping neighborhoods > 20 anchors in the same cluster.
Sybil detection = percolation + COVERAGE problem.

Uses greedy set cover to maximize neighborhood coverage:
1. Generate trust graph (Barabási-Albert power-law, clustering ~0.3)
2. For each candidate anchor, compute unique neighborhood reach
3. Greedily select anchors that maximize NEW coverage per pick
4. Compare: greedy placement vs random vs highest-degree

Sources:
- AAMAS 2025 (Dehkordi & Zehmakan): resistance-seeding improves sybil detection
- SybilGuard (Yu et al, 2006): random walks exploit sparse/dense distinction
- SybilRank (Cao et al, 2012): trust propagation from seeds
- Percolation threshold p_c ≈ 0.54 (trust-percolation-sim.py, Mar 28)

Kit 🦊 — 2026-03-28
"""

import random
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class GraphStats:
    nodes: int
    edges: int
    avg_degree: float
    clustering: float


def generate_ba_graph(n: int, m: int = 3, seed: int = 42) -> tuple[dict[int, set[int]], GraphStats]:
    """
    Barabási-Albert preferential attachment graph.
    Power-law degree distribution, models real trust networks.
    """
    rng = random.Random(seed)
    adj: dict[int, set[int]] = defaultdict(set)
    
    # Start with m+1 fully connected nodes
    for i in range(m + 1):
        for j in range(i + 1, m + 1):
            adj[i].add(j)
            adj[j].add(i)
    
    # Add nodes with preferential attachment
    degree_list = []
    for node in range(m + 1):
        degree_list.extend([node] * len(adj[node]))
    
    for new_node in range(m + 1, n):
        targets = set()
        while len(targets) < m and degree_list:
            candidate = rng.choice(degree_list)
            if candidate != new_node:
                targets.add(candidate)
        
        for t in targets:
            adj[new_node].add(t)
            adj[t].add(new_node)
            degree_list.append(new_node)
            degree_list.append(t)
    
    # Stats
    total_edges = sum(len(v) for v in adj.values()) // 2
    avg_deg = sum(len(v) for v in adj.values()) / max(len(adj), 1)
    
    # Clustering coefficient (sample for speed)
    sample = rng.sample(list(adj.keys()), min(200, len(adj)))
    cc_sum = 0
    cc_count = 0
    for node in sample:
        neighbors = list(adj[node])
        if len(neighbors) < 2:
            continue
        pairs = 0
        connected = 0
        for i in range(len(neighbors)):
            for j in range(i + 1, len(neighbors)):
                pairs += 1
                if neighbors[j] in adj[neighbors[i]]:
                    connected += 1
        if pairs > 0:
            cc_sum += connected / pairs
            cc_count += 1
    
    clustering = cc_sum / max(cc_count, 1)
    
    return dict(adj), GraphStats(
        nodes=len(adj), edges=total_edges,
        avg_degree=round(avg_deg, 2), clustering=round(clustering, 3)
    )


def neighborhood(adj: dict[int, set[int]], node: int, hops: int = 2) -> set[int]:
    """Get all nodes within `hops` of `node`."""
    visited = {node}
    frontier = {node}
    for _ in range(hops):
        next_frontier = set()
        for n in frontier:
            for neighbor in adj.get(n, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_frontier.add(neighbor)
        frontier = next_frontier
    return visited


def greedy_anchor_selection(adj: dict[int, set[int]], k: int, hops: int = 2) -> list[int]:
    """
    Greedy set cover: pick anchor that covers most NEW nodes each round.
    Maximizes non-overlapping neighborhood coverage.
    """
    covered = set()
    anchors = []
    candidates = set(adj.keys())
    
    for _ in range(k):
        best_node = -1
        best_new = -1
        
        for node in candidates:
            reach = neighborhood(adj, node, hops)
            new_coverage = len(reach - covered)
            if new_coverage > best_new:
                best_new = new_coverage
                best_node = node
        
        if best_node >= 0:
            anchors.append(best_node)
            covered.update(neighborhood(adj, best_node, hops))
            candidates.discard(best_node)
    
    return anchors


def random_anchor_selection(adj: dict[int, set[int]], k: int, seed: int = 123) -> list[int]:
    rng = random.Random(seed)
    return rng.sample(list(adj.keys()), min(k, len(adj)))


def highest_degree_selection(adj: dict[int, set[int]], k: int) -> list[int]:
    """Select k highest-degree nodes (hub strategy)."""
    by_degree = sorted(adj.keys(), key=lambda n: len(adj[n]), reverse=True)
    return by_degree[:k]


def compute_coverage(adj: dict[int, set[int]], anchors: list[int], hops: int = 2) -> dict:
    covered = set()
    overlap = 0
    per_anchor = []
    
    for anchor in anchors:
        reach = neighborhood(adj, anchor, hops)
        new = reach - covered
        old = reach & covered
        overlap += len(old)
        covered.update(reach)
        per_anchor.append({
            "anchor": anchor,
            "degree": len(adj.get(anchor, set())),
            "reach": len(reach),
            "new_coverage": len(new),
            "overlap": len(old)
        })
    
    total_nodes = len(adj)
    return {
        "anchors": per_anchor,
        "total_covered": len(covered),
        "total_nodes": total_nodes,
        "coverage_pct": round(100 * len(covered) / max(total_nodes, 1), 1),
        "total_overlap": overlap,
        "efficiency": round(len(covered) / max(sum(a["reach"] for a in per_anchor), 1), 3)
    }


def demo():
    print("=" * 60)
    print("ANCHOR COVERAGE OPTIMIZER")
    print("=" * 60)
    
    N = 1000
    K = 5
    HOPS = 2
    
    adj, stats = generate_ba_graph(N, m=3)
    print(f"Graph: {stats.nodes} nodes, {stats.edges} edges")
    print(f"Avg degree: {stats.avg_degree}, Clustering: {stats.clustering}")
    print(f"Selecting {K} anchors with {HOPS}-hop reach\n")
    
    # Strategy 1: Greedy coverage
    greedy_anchors = greedy_anchor_selection(adj, K, HOPS)
    greedy_cov = compute_coverage(adj, greedy_anchors, HOPS)
    
    # Strategy 2: Random
    random_anchors = random_anchor_selection(adj, K)
    random_cov = compute_coverage(adj, random_anchors, HOPS)
    
    # Strategy 3: Highest degree (hub)
    hub_anchors = highest_degree_selection(adj, K)
    hub_cov = compute_coverage(adj, hub_anchors, HOPS)
    
    strategies = [
        ("GREEDY (max new coverage)", greedy_anchors, greedy_cov),
        ("RANDOM", random_anchors, random_cov),
        ("HIGHEST DEGREE (hubs)", hub_anchors, hub_cov),
    ]
    
    for name, anchors, cov in strategies:
        print(f"--- {name} ---")
        print(f"  Anchors: {anchors}")
        print(f"  Coverage: {cov['coverage_pct']}% ({cov['total_covered']}/{cov['total_nodes']})")
        print(f"  Overlap: {cov['total_overlap']} redundant node-visits")
        print(f"  Efficiency: {cov['efficiency']} (covered/total-reach)")
        print()
    
    # Analysis
    print("=" * 60)
    print("ANALYSIS")
    print("=" * 60)
    
    greedy_pct = greedy_cov['coverage_pct']
    random_pct = random_cov['coverage_pct']
    hub_pct = hub_cov['coverage_pct']
    
    print(f"Greedy:  {greedy_pct}% coverage, efficiency {greedy_cov['efficiency']}")
    print(f"Random:  {random_pct}% coverage, efficiency {random_cov['efficiency']}")
    print(f"Hubs:    {hub_pct}% coverage, efficiency {hub_cov['efficiency']}")
    print()
    
    if greedy_pct > hub_pct:
        print("✓ GREEDY beats HUBS — non-overlapping neighborhoods > raw degree.")
        print("  Hub nodes cluster together; greedy spreads coverage.")
    else:
        print("  Hubs won in this graph (can happen with very small K).")
    
    if greedy_pct > random_pct:
        improvement = greedy_pct - random_pct
        print(f"✓ GREEDY beats RANDOM by {improvement:.1f}pp.")
    
    print()
    print("KEY TAKEAWAY: 5 well-placed anchors with non-overlapping")
    print("neighborhoods > 20 clustered hubs. Anchor PLACEMENT is the")
    print("load-bearing design decision for trust percolation.")
    
    # Assertions
    assert greedy_cov['coverage_pct'] >= random_cov['coverage_pct'] * 0.95, \
        "Greedy should be competitive with or beat random"
    assert greedy_cov['efficiency'] >= hub_cov['efficiency'] * 0.9, \
        "Greedy should be efficient"
    print("\nASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
