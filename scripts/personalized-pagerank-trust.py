#!/usr/bin/env python3
"""
personalized-pagerank-trust.py — Local trust whitelisting via Personalized PageRank.

Alvisi et al (IEEE S&P 2013, "SoK: Evolution of Sybil Defense via Social Networks"):
- Universal sybil defense FAILS because honest graph isn't homogeneous
- Honest region = loosely-coupled communities, NOT a single well-connected blob
- Solution: Personalized PageRank (PPR) from a trusted seed
- PPR cost = O(whitelist_size), not O(network_size)
- Conductance (not density/clustering) is the right foundation

This implements PPR-based local trust whitelisting for ATF:
1. Start from a trusted seed (e.g., your own agent ID)
2. Random walk with restart (teleport back to seed with probability α)
3. Rank all reachable agents by PPR score
4. Whitelist top-K as locally trusted

Sybil regions have low conductance connection to honest region →
random walks rarely cross the attack edge → sybils get low PPR scores.

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
    
    def add_edge(self, src: str, dst: str, weight: float = 1.0):
        self.edges[src][dst] = weight
    
    def neighbors(self, node: str) -> dict[str, float]:
        return self.edges.get(node, {})
    
    def nodes(self) -> set[str]:
        all_nodes = set(self.edges.keys())
        for neighbors in self.edges.values():
            all_nodes.update(neighbors.keys())
        return all_nodes


def personalized_pagerank(
    graph: TrustGraph,
    seed: str,
    alpha: float = 0.15,     # Teleport probability (restart to seed)
    iterations: int = 50,
    epsilon: float = 1e-8
) -> dict[str, float]:
    """
    Compute Personalized PageRank from a seed node.
    
    α = teleport probability. Higher α = more local (biased toward seed).
    Alvisi 2013: PPR naturally concentrates mass in the seed's community.
    Random walks rarely escape through low-conductance cuts (attack edges).
    
    Returns: {node: ppr_score} sorted by score descending.
    """
    nodes = graph.nodes()
    if seed not in nodes:
        return {}
    
    # Initialize: all mass on seed
    scores = {n: 0.0 for n in nodes}
    scores[seed] = 1.0
    
    for _ in range(iterations):
        new_scores = {n: 0.0 for n in nodes}
        
        for node in nodes:
            if scores[node] < epsilon:
                continue
            
            neighbors = graph.neighbors(node)
            if not neighbors:
                # Dangling node: teleport all mass to seed
                new_scores[seed] += scores[node]
                continue
            
            # Teleport component
            new_scores[seed] += alpha * scores[node]
            
            # Walk component: distribute (1-α) to neighbors proportional to weight
            total_weight = sum(neighbors.values())
            if total_weight > 0:
                walk_mass = (1 - alpha) * scores[node]
                for neighbor, weight in neighbors.items():
                    new_scores[neighbor] += walk_mass * (weight / total_weight)
        
        # Check convergence
        diff = sum(abs(new_scores[n] - scores[n]) for n in nodes)
        scores = new_scores
        if diff < epsilon:
            break
    
    # Normalize
    total = sum(scores.values())
    if total > 0:
        scores = {n: s / total for n, s in scores.items()}
    
    return dict(sorted(scores.items(), key=lambda x: -x[1]))


def whitelist_from_ppr(
    ppr_scores: dict[str, float],
    k: int = 10,
    min_score: float = 0.001
) -> list[dict]:
    """
    Extract top-K whitelist from PPR scores.
    Alvisi 2013: cost = O(K), not O(network).
    """
    whitelist = []
    for node, score in ppr_scores.items():
        if len(whitelist) >= k:
            break
        if score >= min_score:
            whitelist.append({"agent": node, "ppr_score": round(score, 6)})
    return whitelist


def build_test_graph(
    n_honest: int = 20,
    n_sybil: int = 15,
    honest_density: float = 0.15,
    sybil_density: float = 0.6,
    attack_edges: int = 2,
    seed: int = 42
) -> tuple[TrustGraph, set[str], set[str]]:
    """
    Build a graph with honest and sybil regions.
    
    Honest: sparse, community structure (Alvisi: real social graphs)
    Sybil: dense, mutual attestation (cheap to create)
    Attack edges: few connections between regions (low conductance)
    """
    rng = random.Random(seed)
    graph = TrustGraph()
    
    honest = {f"honest_{i}" for i in range(n_honest)}
    sybils = {f"sybil_{i}" for i in range(n_sybil)}
    
    # Honest region: sparse with community structure
    honest_list = sorted(honest)
    # Two communities within honest region
    community_a = honest_list[:n_honest // 2]
    community_b = honest_list[n_honest // 2:]
    
    # Intra-community edges (moderate density)
    for comm in [community_a, community_b]:
        for i, a in enumerate(comm):
            for j, b in enumerate(comm):
                if i < j and rng.random() < honest_density * 2:
                    w = rng.uniform(0.5, 1.0)
                    graph.add_edge(a, b, w)
                    graph.add_edge(b, a, w)
    
    # Inter-community edges (sparse — loosely coupled)
    for a in community_a:
        for b in community_b:
            if rng.random() < honest_density * 0.3:
                w = rng.uniform(0.3, 0.7)
                graph.add_edge(a, b, w)
                graph.add_edge(b, a, w)
    
    # Sybil region: dense mutual attestation
    sybil_list = sorted(sybils)
    for i, a in enumerate(sybil_list):
        for j, b in enumerate(sybil_list):
            if i < j and rng.random() < sybil_density:
                w = rng.uniform(0.8, 1.0)  # High mutual scores
                graph.add_edge(a, b, w)
                graph.add_edge(b, a, w)
    
    # Attack edges: few connections from sybil to honest
    honest_targets = rng.sample(honest_list, min(attack_edges, len(honest_list)))
    sybil_sources = rng.sample(sybil_list, min(attack_edges, len(sybil_list)))
    for h, s in zip(honest_targets, sybil_sources):
        graph.add_edge(s, h, rng.uniform(0.3, 0.6))
        graph.add_edge(h, s, rng.uniform(0.1, 0.3))  # Honest less trusting back
    
    return graph, honest, sybils


def demo():
    print("=" * 60)
    print("PERSONALIZED PAGERANK LOCAL TRUST WHITELISTING")
    print("Alvisi et al (IEEE S&P 2013)")
    print("=" * 60)
    print()
    
    graph, honest, sybils = build_test_graph(
        n_honest=20, n_sybil=15,
        honest_density=0.15, sybil_density=0.6,
        attack_edges=2
    )
    
    print(f"Graph: {len(honest)} honest, {len(sybils)} sybil, "
          f"{2} attack edges")
    print(f"Honest density: sparse (0.15), Sybil density: dense (0.6)")
    print()
    
    # PPR from an honest seed
    seed = "honest_0"
    ppr = personalized_pagerank(graph, seed, alpha=0.15, iterations=100)
    
    # Classify results
    honest_scores = {n: s for n, s in ppr.items() if n in honest}
    sybil_scores = {n: s for n, s in ppr.items() if n in sybils}
    
    avg_honest = sum(honest_scores.values()) / max(len(honest_scores), 1)
    avg_sybil = sum(sybil_scores.values()) / max(len(sybil_scores), 1)
    
    print(f"PPR from seed '{seed}' (α=0.15):")
    print(f"  Avg honest PPR: {avg_honest:.6f}")
    print(f"  Avg sybil PPR:  {avg_sybil:.6f}")
    print(f"  Separation ratio: {avg_honest / max(avg_sybil, 1e-10):.1f}x")
    print()
    
    # Whitelist top-10
    whitelist = whitelist_from_ppr(ppr, k=10)
    n_honest_in_whitelist = sum(1 for w in whitelist if w["agent"] in honest)
    n_sybil_in_whitelist = sum(1 for w in whitelist if w["agent"] in sybils)
    
    print(f"Top-10 whitelist:")
    print(f"  Honest: {n_honest_in_whitelist}, Sybil: {n_sybil_in_whitelist}")
    for w in whitelist[:5]:
        label = "✓" if w["agent"] in honest else "✗ SYBIL"
        print(f"  {w['agent']}: {w['ppr_score']} {label}")
    print(f"  ... ({len(whitelist) - 5} more)")
    print()
    
    # Test with different α values
    print("=" * 60)
    print("ALPHA SENSITIVITY (teleport probability)")
    print("=" * 60)
    for alpha in [0.05, 0.15, 0.30, 0.50]:
        ppr_a = personalized_pagerank(graph, seed, alpha=alpha)
        wl = whitelist_from_ppr(ppr_a, k=10)
        n_h = sum(1 for w in wl if w["agent"] in honest)
        n_s = sum(1 for w in wl if w["agent"] in sybils)
        h_scores = [s for n, s in ppr_a.items() if n in honest]
        s_scores = [s for n, s in ppr_a.items() if n in sybils]
        avg_h = sum(h_scores) / max(len(h_scores), 1)
        avg_s = sum(s_scores) / max(len(s_scores), 1)
        ratio = avg_h / max(avg_s, 1e-10)
        print(f"  α={alpha:.2f}: whitelist {n_h}H/{n_s}S, separation={ratio:.1f}x")
    
    print()
    print("KEY INSIGHT: Higher α = more local = better sybil separation.")
    print("But too high = only seed's immediate neighbors.")
    print("α=0.15 is standard (Page et al 1998).")
    print()
    
    # Verify: top-10 should be majority honest
    assert n_honest_in_whitelist > n_sybil_in_whitelist, \
        f"Expected majority honest in whitelist, got {n_honest_in_whitelist}H/{n_sybil_in_whitelist}S"
    assert avg_honest > avg_sybil, \
        f"Expected honest PPR > sybil PPR"
    
    print("ALL ASSERTIONS PASSED ✓")
    print()
    print("Alvisi 2013 confirmed: PPR concentrates mass in honest community.")
    print("Low-conductance cut (attack edges) blocks sybil mass propagation.")
    print("Local whitelisting > universal defense. ATF already does this.")


if __name__ == "__main__":
    demo()
