#!/usr/bin/env python3
"""small-world-sim.py — Watts-Strogatz small-world network simulator.
Shows how rewiring probability affects path length and clustering.
Inspired by octopus INC topology research."""

import random
import sys
from collections import deque

def make_ring_lattice(n, k):
    """Create ring lattice: n nodes, each connected to k nearest neighbors."""
    adj = {i: set() for i in range(n)}
    for i in range(n):
        for j in range(1, k // 2 + 1):
            adj[i].add((i + j) % n)
            adj[i].add((i - j) % n)
            adj[(i + j) % n].add(i)
            adj[(i - j) % n].add(i)
    return adj

def rewire(adj, n, k, p):
    """Rewire each edge with probability p (Watts-Strogatz model)."""
    adj = {i: set(adj[i]) for i in adj}  # deep copy
    for i in range(n):
        for j in range(1, k // 2 + 1):
            target = (i + j) % n
            if random.random() < p and target in adj[i]:
                # Pick new target
                candidates = [x for x in range(n) if x != i and x not in adj[i]]
                if candidates:
                    new_target = random.choice(candidates)
                    adj[i].discard(target)
                    adj[target].discard(i)
                    adj[i].add(new_target)
                    adj[new_target].add(i)
    return adj

def avg_path_length(adj, n, sample=100):
    """Average shortest path length (sampled for speed)."""
    total = 0
    count = 0
    nodes = random.sample(range(n), min(sample, n))
    for src in nodes:
        dist = {src: 0}
        q = deque([src])
        while q:
            u = q.popleft()
            for v in adj[u]:
                if v not in dist:
                    dist[v] = dist[u] + 1
                    q.append(v)
        for d in dist.values():
            if d > 0:
                total += d
                count += 1
    return total / count if count else float('inf')

def avg_clustering(adj, n):
    """Average clustering coefficient."""
    total = 0
    for i in range(n):
        neighbors = list(adj[i])
        if len(neighbors) < 2:
            continue
        triangles = 0
        possible = len(neighbors) * (len(neighbors) - 1) / 2
        for a in range(len(neighbors)):
            for b in range(a + 1, len(neighbors)):
                if neighbors[b] in adj[neighbors[a]]:
                    triangles += 1
        total += triangles / possible
    return total / n

def main():
    n = 200  # nodes
    k = 6    # neighbors
    
    print(f"Watts-Strogatz Small-World Simulator")
    print(f"n={n} nodes, k={k} neighbors per node")
    print(f"{'p':>8} {'AvgPath':>10} {'Clustering':>12} {'SmallWorld':>12}")
    print("─" * 46)
    
    # Baseline lattice
    lattice = make_ring_lattice(n, k)
    L0 = avg_path_length(lattice, n)
    C0 = avg_clustering(lattice, n)
    
    for p in [0.0, 0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0]:
        g = rewire(lattice, n, k, p) if p > 0 else lattice
        L = avg_path_length(g, n)
        C = avg_clustering(g, n)
        # Small-world sigma = (C/C0) / (L/L0)
        sigma = (C / C0) / (L / L0) if L > 0 and C0 > 0 and L0 > 0 else 0
        bar = "█" * int(sigma * 3)
        print(f"{p:>8.3f} {L:>10.2f} {C:>12.4f} {sigma:>8.2f}   {bar}")
    
    print()
    print("σ > 1 = small-world. Peak is the sweet spot:")
    print("high clustering (local tribes) + short paths (random shortcuts).")
    print()
    print("The octopus: p ≈ 0.01-0.05. Just enough cross-wiring")
    print("to get global reach without losing local coordination.")

if __name__ == "__main__":
    main()
