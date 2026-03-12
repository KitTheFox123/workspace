#!/usr/bin/env python3
"""
sybil-ring-detector.py — Graph-based sybil ring detection using k-clique percolation + temporal burst analysis.

Combines:
1. Pairwise mutual information (from collusion-detector.py) to build agreement graph
2. k-clique percolation (NetworkX) to find overlapping sybil communities  
3. Temporal burst clustering (from attestation-burst-detector.py) as corroboration

Usage:
    python3 sybil-ring-detector.py [--attesters N] [--sybils K] [--k-clique K] [--threshold T]
    
References:
- Palla et al. (2005) "Uncovering the overlapping community structure of complex networks"
- NetworkX k_clique_communities: networkx.algorithms.community.kclique
- ACM SIGMOD 2025: "Scaling Up k-Clique Percolation Community Detection"
"""

import argparse
import json
import random
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import combinations

# Inline minimal graph + clique detection (no networkx dependency)

class Graph:
    """Minimal undirected graph."""
    def __init__(self):
        self.adj = defaultdict(set)
        self.edges = set()
    
    def add_edge(self, u, v, weight=1.0):
        self.adj[u].add(v)
        self.adj[v].add(u)
        self.edges.add((min(u,v), max(u,v)))
    
    @property
    def nodes(self):
        return set(self.adj.keys())
    
    def neighbors(self, n):
        return self.adj[n]
    
    def subgraph_has_edge(self, u, v):
        return (min(u,v), max(u,v)) in self.edges


def find_cliques(graph):
    """Bron-Kerbosch with pivoting. Returns all maximal cliques."""
    cliques = []
    
    def bron_kerbosch(R, P, X):
        if not P and not X:
            cliques.append(frozenset(R))
            return
        # pivot: choose node in P∪X with most connections to P
        pivot = max(P | X, key=lambda v: len(graph.neighbors(v) & P))
        for v in list(P - graph.neighbors(pivot)):
            neighbors_v = graph.neighbors(v)
            bron_kerbosch(R | {v}, P & neighbors_v, X & neighbors_v)
            P.remove(v)
            X.add(v)
    
    nodes = graph.nodes
    bron_kerbosch(set(), set(nodes), set())
    return cliques


def k_clique_communities(graph, k):
    """
    k-clique percolation: find overlapping communities.
    Two k-cliques are adjacent if they share k-1 nodes.
    A community = connected component of k-clique adjacency graph.
    """
    # Find all cliques of size >= k
    all_cliques = find_cliques(graph)
    k_cliques = [c for c in all_cliques if len(c) >= k]
    
    # Extract all k-subcliques
    k_subcliques = set()
    for clique in k_cliques:
        if len(clique) == k:
            k_subcliques.add(clique)
        else:
            for sub in combinations(clique, k):
                k_subcliques.add(frozenset(sub))
    
    if not k_subcliques:
        return []
    
    # Build adjacency: two k-cliques adjacent if they share k-1 nodes
    clique_list = list(k_subcliques)
    clique_adj = defaultdict(set)
    for i, c1 in enumerate(clique_list):
        for j, c2 in enumerate(clique_list):
            if i < j and len(c1 & c2) >= k - 1:
                clique_adj[i].add(j)
                clique_adj[j].add(i)
    
    # Connected components via BFS
    visited = set()
    communities = []
    for i in range(len(clique_list)):
        if i in visited:
            continue
        component = set()
        queue = [i]
        while queue:
            node = queue.pop()
            if node in visited:
                continue
            visited.add(node)
            component |= clique_list[node]
            for neighbor in clique_adj[node]:
                if neighbor not in visited:
                    queue.append(neighbor)
        if component:
            communities.append(component)
    
    return communities


def mutual_information(votes_a, votes_b):
    """Compute MI between two binary vote sequences."""
    n = len(votes_a)
    if n == 0:
        return 0.0
    
    # Joint distribution
    joint = defaultdict(int)
    margin_a = defaultdict(int)
    margin_b = defaultdict(int)
    
    for a, b in zip(votes_a, votes_b):
        joint[(a, b)] += 1
        margin_a[a] += 1
        margin_b[b] += 1
    
    mi = 0.0
    for (a, b), count in joint.items():
        p_joint = count / n
        p_a = margin_a[a] / n
        p_b = margin_b[b] / n
        if p_joint > 0 and p_a > 0 and p_b > 0:
            mi += p_joint * math.log2(p_joint / (p_a * p_b))
    
    return mi


def detect_temporal_bursts(timestamps, window_seconds=30):
    """Find clusters of attestations within a time window."""
    if len(timestamps) < 2:
        return []
    
    sorted_ts = sorted(timestamps)
    bursts = []
    current_burst = [sorted_ts[0]]
    
    for i in range(1, len(sorted_ts)):
        if (sorted_ts[i] - sorted_ts[i-1]).total_seconds() <= window_seconds:
            current_burst.append(sorted_ts[i])
        else:
            if len(current_burst) >= 3:
                bursts.append(current_burst)
            current_burst = [sorted_ts[i]]
    
    if len(current_burst) >= 3:
        bursts.append(current_burst)
    
    return bursts


def simulate_attestations(n_attesters, n_sybils, n_items=50, sybil_agreement=0.92):
    """Generate synthetic attestation data with embedded sybil ring."""
    attesters = [f"agent_{i:03d}" for i in range(n_attesters)]
    sybil_ring = attesters[:n_sybils]
    honest = attesters[n_sybils:]
    
    # Generate votes: sybils coordinate, honest agents vote independently
    votes = {}
    timestamps = {}
    base_time = datetime(2026, 3, 6, 12, 0, 0)
    
    # Sybil leader's votes
    leader_votes = [random.choice([0, 1]) for _ in range(n_items)]
    
    for agent in attesters:
        agent_votes = []
        agent_times = []
        
        for item in range(n_items):
            if agent in sybil_ring:
                # Sybils follow leader with high probability
                if random.random() < sybil_agreement:
                    agent_votes.append(leader_votes[item])
                else:
                    agent_votes.append(1 - leader_votes[item])
                # Sybils attest in tight temporal clusters
                agent_times.append(base_time + timedelta(
                    hours=item,
                    seconds=random.uniform(0, 15)  # tight window
                ))
            else:
                # Honest agents vote independently
                agent_votes.append(random.choice([0, 1]))
                # Honest agents attest at varied times
                agent_times.append(base_time + timedelta(
                    hours=item,
                    seconds=random.uniform(0, 3600)  # spread across hour
                ))
        
        votes[agent] = agent_votes
        timestamps[agent] = agent_times
    
    return attesters, sybil_ring, votes, timestamps


def run_detection(n_attesters=20, n_sybils=5, k=3, mi_threshold=0.3):
    """Full detection pipeline."""
    print(f"\n{'='*60}")
    print(f"Sybil Ring Detection via k-Clique Percolation")
    print(f"{'='*60}")
    print(f"Attesters: {n_attesters} | Embedded sybils: {n_sybils} | k: {k} | MI threshold: {mi_threshold}")
    
    # 1. Simulate
    attesters, true_sybils, votes, timestamps = simulate_attestations(n_attesters, n_sybils)
    print(f"\nTrue sybil ring: {true_sybils}")
    
    # 2. Build MI graph
    print(f"\n--- Phase 1: Mutual Information Graph ---")
    g = Graph()
    mi_scores = {}
    
    for a1, a2 in combinations(attesters, 2):
        mi = mutual_information(votes[a1], votes[a2])
        mi_scores[(a1, a2)] = mi
        if mi > mi_threshold:
            g.add_edge(a1, a2, weight=mi)
    
    high_mi_edges = sum(1 for v in mi_scores.values() if v > mi_threshold)
    print(f"Edges (MI > {mi_threshold}): {high_mi_edges} / {len(mi_scores)}")
    
    # 3. k-clique percolation
    print(f"\n--- Phase 2: k-Clique Percolation (k={k}) ---")
    communities = k_clique_communities(g, k)
    
    if not communities:
        print("No k-clique communities found. Try lower k or threshold.")
    
    for i, community in enumerate(communities):
        print(f"Community {i+1}: {sorted(community)}")
        
        # Check overlap with true sybils
        true_pos = community & set(true_sybils)
        false_pos = community - set(true_sybils)
        precision = len(true_pos) / len(community) if community else 0
        recall = len(true_pos) / len(true_sybils) if true_sybils else 0
        
        print(f"  True positives: {len(true_pos)}, False positives: {len(false_pos)}")
        print(f"  Precision: {precision:.2%}, Recall: {recall:.2%}")
    
    # 4. Temporal burst corroboration
    print(f"\n--- Phase 3: Temporal Burst Corroboration ---")
    
    # Flatten all sybil candidate timestamps
    if communities:
        largest = max(communities, key=len)
        candidate_times = []
        for agent in largest:
            candidate_times.extend(timestamps[agent])
        
        bursts = detect_temporal_bursts(candidate_times, window_seconds=30)
        print(f"Temporal bursts (30s window): {len(bursts)}")
        if bursts:
            avg_burst_size = sum(len(b) for b in bursts) / len(bursts)
            print(f"Average burst size: {avg_burst_size:.1f} attestations")
            print(f"Burst density confirms coordinated timing: {'YES' if avg_burst_size > 3 else 'WEAK'}")
    
    # 5. Summary
    print(f"\n--- Detection Summary ---")
    detected = set()
    for c in communities:
        detected |= c
    
    true_pos_total = detected & set(true_sybils)
    false_pos_total = detected - set(true_sybils)
    false_neg_total = set(true_sybils) - detected
    
    precision = len(true_pos_total) / len(detected) if detected else 0
    recall = len(true_pos_total) / len(true_sybils) if true_sybils else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    result = {
        "detected_sybils": sorted(detected),
        "true_positives": len(true_pos_total),
        "false_positives": len(false_pos_total),
        "false_negatives": len(false_neg_total),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "communities_found": len(communities),
        "method": f"MI(threshold={mi_threshold}) + k-clique(k={k}) + temporal-burst(30s)"
    }
    
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sybil ring detection via k-clique percolation")
    parser.add_argument("--attesters", type=int, default=20, help="Total attesters")
    parser.add_argument("--sybils", type=int, default=5, help="Embedded sybils")
    parser.add_argument("--k-clique", type=int, default=3, help="k for k-clique percolation")
    parser.add_argument("--threshold", type=float, default=0.3, help="MI threshold for edges")
    parser.add_argument("--runs", type=int, default=1, help="Number of simulation runs")
    
    args = parser.parse_args()
    
    if args.runs == 1:
        run_detection(args.attesters, args.sybils, args.k_clique, args.threshold)
    else:
        # Multi-run averaging
        totals = {"precision": 0, "recall": 0, "f1": 0}
        for i in range(args.runs):
            random.seed(i * 42)
            result = run_detection(args.attesters, args.sybils, args.k_clique, args.threshold)
            for k in totals:
                totals[k] += result[k]
        
        print(f"\n{'='*60}")
        print(f"Average over {args.runs} runs:")
        for k, v in totals.items():
            print(f"  {k}: {v/args.runs:.4f}")
