#!/usr/bin/env python3
"""
friendship-paradox.py — Friendship paradox network seeding simulator.

Demonstrates that "your friends have more friends than you" enables
more efficient information spread without mapping the entire network.

Based on Christakis & Fowler (Science 2024): friendship-nomination
targeting outperforms random targeting for social contagion.

Usage:
    python3 friendship-paradox.py [--nodes N] [--seed-frac F] [--steps S]
"""

import argparse
import random
from collections import defaultdict

def generate_ba_network(n: int, m: int = 3) -> dict[int, set[int]]:
    """Barabási-Albert preferential attachment network."""
    adj: dict[int, set[int]] = defaultdict(set)
    # Start with complete graph on m+1 nodes
    for i in range(m + 1):
        for j in range(i + 1, m + 1):
            adj[i].add(j)
            adj[j].add(i)
    
    for new in range(m + 1, n):
        # Build degree list for preferential attachment
        targets = set()
        degree_list = []
        for node in range(new):
            degree_list.extend([node] * len(adj[node]))
        
        while len(targets) < m:
            chosen = random.choice(degree_list)
            targets.add(chosen)
        
        for t in targets:
            adj[new].add(t)
            adj[t].add(new)
    
    return adj

def random_seeds(adj: dict, frac: float) -> set[int]:
    """Pick seeds uniformly at random."""
    n = len(adj)
    k = max(1, int(n * frac))
    return set(random.sample(list(adj.keys()), k))

def friendship_nomination_seeds(adj: dict, frac: float) -> set[int]:
    """Pick random nodes, then select one of their friends as seed."""
    n = len(adj)
    k = max(1, int(n * frac))
    seeds = set()
    nodes = list(adj.keys())
    attempts = 0
    while len(seeds) < k and attempts < k * 10:
        node = random.choice(nodes)
        if adj[node]:
            friend = random.choice(list(adj[node]))
            seeds.add(friend)
        attempts += 1
    return seeds

def simulate_spread(adj: dict, seeds: set[int], steps: int, threshold: float = 0.3) -> list[int]:
    """Simple threshold contagion: adopt if >= threshold fraction of neighbors adopted."""
    adopted = set(seeds)
    history = [len(adopted)]
    
    for _ in range(steps):
        new_adopters = set()
        for node in adj:
            if node in adopted:
                continue
            neighbors = adj[node]
            if not neighbors:
                continue
            frac_adopted = len(neighbors & adopted) / len(neighbors)
            if frac_adopted >= threshold:
                new_adopters.add(node)
        adopted |= new_adopters
        history.append(len(adopted))
        if not new_adopters:
            break
    
    return history

def main():
    parser = argparse.ArgumentParser(description="Friendship paradox seeding simulator")
    parser.add_argument("--nodes", type=int, default=200, help="Network size")
    parser.add_argument("--seed-frac", type=float, default=0.1, help="Fraction seeded")
    parser.add_argument("--steps", type=int, default=10, help="Simulation steps")
    parser.add_argument("--trials", type=int, default=50, help="Monte Carlo trials")
    parser.add_argument("--threshold", type=float, default=0.25, help="Adoption threshold")
    args = parser.parse_args()

    print(f"Network: {args.nodes} nodes (BA model, m=3)")
    print(f"Seed fraction: {args.seed_frac:.0%} | Threshold: {args.threshold:.0%} | Trials: {args.trials}")
    print()

    random_results = []
    nomination_results = []

    for trial in range(args.trials):
        adj = generate_ba_network(args.nodes)
        
        # Random targeting
        seeds_r = random_seeds(adj, args.seed_frac)
        hist_r = simulate_spread(adj, seeds_r, args.steps, args.threshold)
        random_results.append(hist_r[-1] / args.nodes)
        
        # Friendship nomination targeting
        seeds_fn = friendship_nomination_seeds(adj, args.seed_frac)
        hist_fn = simulate_spread(adj, seeds_fn, args.steps, args.threshold)
        nomination_results.append(hist_fn[-1] / args.nodes)

    # Stats
    avg_random = sum(random_results) / len(random_results)
    avg_nomination = sum(nomination_results) / len(nomination_results)
    
    # Degree comparison
    adj = generate_ba_network(args.nodes)
    seeds_r = random_seeds(adj, args.seed_frac)
    seeds_fn = friendship_nomination_seeds(adj, args.seed_frac)
    deg_r = sum(len(adj[s]) for s in seeds_r) / len(seeds_r)
    deg_fn = sum(len(adj[s]) for s in seeds_fn) / len(seeds_fn)

    print("═══════════════════════════════════════════")
    print(f"  Strategy          Avg Adoption  Avg Degree")
    print(f"  ─────────────────────────────────────────")
    print(f"  Random            {avg_random:>8.1%}      {deg_r:>6.1f}")
    print(f"  Friend-Nomination {avg_nomination:>8.1%}      {deg_fn:>6.1f}")
    print(f"  ─────────────────────────────────────────")
    advantage = avg_nomination - avg_random
    print(f"  Nomination advantage: {advantage:+.1%}")
    print(f"  Degree advantage:     {deg_fn/deg_r:.1f}x")
    print("═══════════════════════════════════════════")
    
    # Sweep seed fractions
    print(f"\nSeed fraction sweep (threshold={args.threshold:.0%}):")
    print(f"  Frac    Random    Nomination  Δ")
    for frac in [0.05, 0.1, 0.2, 0.3, 0.5]:
        rr = []
        nr = []
        for _ in range(args.trials):
            adj = generate_ba_network(args.nodes)
            sr = random_seeds(adj, frac)
            sn = friendship_nomination_seeds(adj, frac)
            rr.append(simulate_spread(adj, sr, args.steps, args.threshold)[-1] / args.nodes)
            nr.append(simulate_spread(adj, sn, args.steps, args.threshold)[-1] / args.nodes)
        ar = sum(rr)/len(rr)
        an = sum(nr)/len(nr)
        print(f"  {frac:>4.0%}    {ar:>6.1%}    {an:>8.1%}    {an-ar:+.1%}")

if __name__ == "__main__":
    main()
