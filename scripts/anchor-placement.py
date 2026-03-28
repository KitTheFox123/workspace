#!/usr/bin/env python3
"""
anchor-placement.py — Greedy anchor placement for sybil-resilient trust networks.

The insight (santaclawd email, 2026-03-28): anchor redundancy only helps if
anchors have DISTINCT reach. Five anchors in a tight clique = one anchor.

SybilRank (Cao et al 2012): trust propagates via early-stopping random walks
from honest anchors. SybilGAT (Heeb et al, ETH 2024, arxiv 2409.08631):
k=1 anchor → F1 0.889, but only with distinct neighborhood coverage.

This is the minimum dominating set problem (NP-hard, greedy ≤ ln(n)+1 approx).
Greedy: pick the node that covers the most uncovered neighbors, repeat.

Kit 🦊 — 2026-03-28
"""

import random
import json
from collections import defaultdict


def generate_trust_network(n_honest: int, n_sybil: int, 
                           honest_avg_degree: int = 6,
                           sybil_internal_density: float = 0.3,
                           attack_edges: int = 5) -> dict:
    """
    Generate a trust network with honest + sybil regions.
    
    Honest region: preferential attachment (power-law, like real social networks).
    Sybil region: dense random (free mutual inflation).
    Attack edges: sparse connections between regions.
    """
    adj = defaultdict(set)
    labels = {}
    
    # Honest region: Barabási-Albert-like
    honest_nodes = [f"h_{i}" for i in range(n_honest)]
    for node in honest_nodes:
        labels[node] = "honest"
    
    # Build honest graph with preferential attachment
    for i, node in enumerate(honest_nodes):
        if i < honest_avg_degree:
            # Connect initial nodes to each other
            for j in range(i):
                adj[node].add(honest_nodes[j])
                adj[honest_nodes[j]].add(node)
        else:
            # Preferential attachment: connect to `m` existing nodes
            m = min(honest_avg_degree // 2, i)
            degrees = [len(adj[honest_nodes[j]]) + 1 for j in range(i)]
            total = sum(degrees)
            probs = [d / total for d in degrees]
            targets = set()
            attempts = 0
            while len(targets) < m and attempts < m * 10:
                idx = random.choices(range(i), weights=probs[:i], k=1)[0]
                targets.add(honest_nodes[idx])
                attempts += 1
            for t in targets:
                adj[node].add(t)
                adj[t].add(node)
    
    # Sybil region: dense random
    sybil_nodes = [f"s_{i}" for i in range(n_sybil)]
    for node in sybil_nodes:
        labels[node] = "sybil"
    
    for i in range(n_sybil):
        for j in range(i + 1, n_sybil):
            if random.random() < sybil_internal_density:
                adj[sybil_nodes[i]].add(sybil_nodes[j])
                adj[sybil_nodes[j]].add(sybil_nodes[i])
    
    # Attack edges: sparse connections
    for _ in range(attack_edges):
        h = random.choice(honest_nodes)
        s = random.choice(sybil_nodes)
        adj[h].add(s)
        adj[s].add(h)
    
    return {"adj": dict(adj), "labels": labels, 
            "honest": honest_nodes, "sybil": sybil_nodes}


def greedy_anchor_placement(adj: dict, k: int, candidates: list = None) -> list:
    """
    Greedy anchor placement: pick node covering most uncovered neighbors.
    
    Approximation ratio: ln(n) + 1 for dominating set.
    Each anchor covers itself + its 1-hop neighborhood.
    
    Returns list of (node, marginal_coverage) tuples.
    """
    if candidates is None:
        candidates = list(adj.keys())
    
    covered = set()
    anchors = []
    
    for _ in range(k):
        best_node = None
        best_gain = -1
        
        for node in candidates:
            if node in [a[0] for a in anchors]:
                continue
            # Coverage = self + neighbors not yet covered
            neighborhood = {node} | adj.get(node, set())
            gain = len(neighborhood - covered)
            if gain > best_gain:
                best_gain = gain
                best_node = node
        
        if best_node is None or best_gain == 0:
            break
        
        neighborhood = {best_node} | adj.get(best_node, set())
        covered |= neighborhood
        anchors.append((best_node, best_gain))
    
    return anchors


def evaluate_anchor_set(adj: dict, labels: dict, anchors: list, 
                        walk_length: int = 3) -> dict:
    """
    Evaluate anchor set via simplified SybilRank-style trust propagation.
    
    Early-stopping random walks from anchors. Trust score = landing probability.
    Higher trust → more likely honest.
    """
    all_nodes = list(adj.keys())
    trust = {n: 0.0 for n in all_nodes}
    
    # Seed anchors with trust
    anchor_nodes = [a[0] for a in anchors]
    for a in anchor_nodes:
        trust[a] = 1.0
    
    # Propagate via random walks (simplified)
    for _ in range(walk_length):
        new_trust = {n: 0.0 for n in all_nodes}
        for node in all_nodes:
            neighbors = adj.get(node, set())
            if not neighbors:
                new_trust[node] += trust[node]
                continue
            # Distribute trust equally to neighbors
            share = trust[node] / (len(neighbors) + 1)  # +1 for self-loop
            new_trust[node] += share
            for nb in neighbors:
                new_trust[nb] += share
        trust = new_trust
    
    # Classify: threshold at median trust
    scores = sorted(trust.values())
    threshold = scores[len(scores) // 2]
    
    tp = fp = tn = fn = 0
    for node, score in trust.items():
        predicted_honest = score >= threshold
        actual_honest = labels[node] == "honest"
        if predicted_honest and actual_honest:
            tp += 1
        elif predicted_honest and not actual_honest:
            fp += 1
        elif not predicted_honest and not actual_honest:
            tn += 1
        else:
            fn += 1
    
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 0.001)
    
    # Coverage metrics
    total_nodes = len(all_nodes)
    covered = set()
    for a in anchor_nodes:
        covered.add(a)
        covered |= adj.get(a, set())
    
    # Neighborhood overlap between anchors
    neighborhoods = []
    for a in anchor_nodes:
        neighborhoods.append({a} | adj.get(a, set()))
    
    overlap = 0
    pairs = 0
    for i in range(len(neighborhoods)):
        for j in range(i + 1, len(neighborhoods)):
            if neighborhoods[i] and neighborhoods[j]:
                jaccard = len(neighborhoods[i] & neighborhoods[j]) / len(neighborhoods[i] | neighborhoods[j])
                overlap += jaccard
                pairs += 1
    
    avg_overlap = overlap / max(pairs, 1)
    
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "coverage": round(len(covered) / total_nodes, 3),
        "anchor_overlap": round(avg_overlap, 3),
        "honest_avg_trust": round(sum(trust[n] for n in all_nodes if labels[n] == "honest") / max(sum(1 for n in all_nodes if labels[n] == "honest"), 1), 4),
        "sybil_avg_trust": round(sum(trust[n] for n in all_nodes if labels[n] == "sybil") / max(sum(1 for n in all_nodes if labels[n] == "sybil"), 1), 4),
    }


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("ANCHOR PLACEMENT FOR SYBIL-RESILIENT TRUST NETWORKS")
    print("=" * 60)
    
    net = generate_trust_network(
        n_honest=200, n_sybil=50,
        honest_avg_degree=6,
        sybil_internal_density=0.3,
        attack_edges=8
    )
    
    honest_degrees = [len(net["adj"].get(n, set())) for n in net["honest"]]
    sybil_degrees = [len(net["adj"].get(n, set())) for n in net["sybil"]]
    
    print(f"Network: {len(net['honest'])} honest + {len(net['sybil'])} sybil = {len(net['labels'])} total")
    print(f"Honest avg degree: {sum(honest_degrees)/len(honest_degrees):.1f}")
    print(f"Sybil avg degree: {sum(sybil_degrees)/len(sybil_degrees):.1f}")
    print(f"Attack edges: 8")
    print()
    
    # Compare: greedy vs random anchor placement
    for k in [1, 3, 5, 10]:
        print(f"--- k={k} anchors ---")
        
        # Greedy (optimal placement)
        greedy_anchors = greedy_anchor_placement(net["adj"], k, candidates=net["honest"])
        greedy_eval = evaluate_anchor_set(net["adj"], net["labels"], greedy_anchors)
        
        # Random (baseline)
        random_anchors = [(random.choice(net["honest"]), 0) for _ in range(k)]
        random_eval = evaluate_anchor_set(net["adj"], net["labels"], random_anchors)
        
        # Clique (worst case — clustered anchors)
        hub = max(net["honest"], key=lambda n: len(net["adj"].get(n, set())))
        hub_neighbors = [n for n in net["adj"].get(hub, set()) if n in set(net["honest"])]
        clique_anchors = [(hub, 0)] + [(n, 0) for n in hub_neighbors[:k-1]]
        clique_eval = evaluate_anchor_set(net["adj"], net["labels"], clique_anchors)
        
        print(f"  Greedy:  F1={greedy_eval['f1']}, coverage={greedy_eval['coverage']}, overlap={greedy_eval['anchor_overlap']}")
        print(f"  Random:  F1={random_eval['f1']}, coverage={random_eval['coverage']}, overlap={random_eval['anchor_overlap']}")
        print(f"  Clique:  F1={clique_eval['f1']}, coverage={clique_eval['coverage']}, overlap={clique_eval['anchor_overlap']}")
        print()
    
    print("KEY INSIGHTS:")
    print("1. Greedy placement maximizes coverage → better sybil detection")
    print("2. Clique placement = high overlap → wasted redundancy")
    print("3. Non-overlapping neighborhoods > raw anchor count")
    print("4. This is dominating set: NP-hard, greedy gets ln(n)+1 approx")
    print("5. santaclawd was right: 5 anchors in a clique = 1 anchor")


if __name__ == "__main__":
    demo()
