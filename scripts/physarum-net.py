#!/usr/bin/env python3
"""Physarum-inspired network pruning simulator.
Models tube reinforcement/decay based on flow between food sources.
Inspired by Tero et al. 2006 mathematical model."""

import argparse
import random
import math

def create_grid(n):
    """Create n×n grid network with random initial conductivities."""
    edges = {}
    for i in range(n):
        for j in range(n):
            node = (i, j)
            for di, dj in [(0,1),(1,0)]:
                ni, nj = i+di, j+dj
                if 0 <= ni < n and 0 <= nj < n:
                    edges[(node, (ni,nj))] = random.uniform(0.5, 1.5)
    return edges

def simulate(n=5, food_sources=None, steps=50, mu=1.3, decay=0.1, verbose=False):
    """Run Physarum network optimization.
    
    mu: reinforcement exponent (>1 = positive feedback)
    decay: tube shrinkage rate per step
    """
    if food_sources is None:
        food_sources = [(0,0), (n-1,n-1)]
    
    edges = create_grid(n)
    
    for step in range(steps):
        # Calculate flow pressure (simplified: distance-based)
        src, dst = food_sources[0], food_sources[1]
        
        # Update conductivities based on flow
        total_flow = 0
        for (a, b), cond in list(edges.items()):
            # Edges on shorter paths get more flow
            dist_src = abs(a[0]-src[0]) + abs(a[1]-src[1]) + abs(b[0]-src[0]) + abs(b[1]-src[1])
            dist_dst = abs(a[0]-dst[0]) + abs(a[1]-dst[1]) + abs(b[0]-dst[0]) + abs(b[1]-dst[1])
            direct = abs(src[0]-dst[0]) + abs(src[1]-dst[1])
            
            # Flow is higher for edges on more direct paths
            detour = (dist_src + dist_dst) / 2 - direct
            flow = max(0.01, 1.0 / (1.0 + detour))
            
            # Tero model: dD/dt = f(Q)^mu - decay*D
            new_cond = cond + (flow**mu - decay * cond) * 0.1
            edges[(a,b)] = max(0.01, new_cond)
            total_flow += flow
        
        if verbose and step % 10 == 0:
            alive = sum(1 for c in edges.values() if c > 0.3)
            max_c = max(edges.values())
            print(f"Step {step:3d}: {alive}/{len(edges)} active edges, max conductivity={max_c:.2f}")
    
    return edges

def display(edges, n, threshold=0.3):
    """ASCII display of surviving network."""
    # Show which edges survived
    surviving = {k: v for k, v in edges.items() if v > threshold}
    print(f"\nSurviving edges: {len(surviving)}/{len(edges)} (threshold={threshold})")
    print(f"Total conductivity: {sum(edges.values()):.1f}")
    print(f"Surviving conductivity: {sum(surviving.values()):.1f}")
    
    # Simple grid display
    grid = [['.' for _ in range(n*2-1)] for _ in range(n*2-1)]
    for (a, b), cond in surviving.items():
        ay, ax = a[0]*2, a[1]*2
        by, bx = b[0]*2, b[1]*2
        my, mx = (ay+by)//2, (ax+bx)//2
        grid[ay][ax] = 'O'
        grid[by][bx] = 'O'
        if cond > 1.0:
            grid[my][mx] = '█'
        elif cond > 0.5:
            grid[my][mx] = '▓'
        else:
            grid[my][mx] = '░'
    
    for row in grid:
        print(' '.join(row))

def main():
    parser = argparse.ArgumentParser(description='Physarum network pruning simulator')
    parser.add_argument('--size', '-n', type=int, default=5, help='Grid size (default: 5)')
    parser.add_argument('--steps', '-s', type=int, default=100, help='Simulation steps (default: 100)')
    parser.add_argument('--mu', type=float, default=1.3, help='Reinforcement exponent (default: 1.3)')
    parser.add_argument('--decay', type=float, default=0.1, help='Decay rate (default: 0.1)')
    parser.add_argument('--threshold', '-t', type=float, default=0.3, help='Display threshold (default: 0.3)')
    parser.add_argument('--verbose', '-v', action='store_true')
    parser.add_argument('--food', nargs='+', help='Food sources as x,y pairs (default: corners)')
    
    args = parser.parse_args()
    
    food = None
    if args.food:
        food = [tuple(map(int, f.split(','))) for f in args.food]
    
    print(f"Physarum Network Simulator (Tero et al. 2006 model)")
    print(f"Grid: {args.size}×{args.size}, Steps: {args.steps}, μ={args.mu}, decay={args.decay}")
    if food:
        print(f"Food sources: {food}")
    
    edges = simulate(args.size, food, args.steps, args.mu, args.decay, args.verbose)
    display(edges, args.size, args.threshold)

if __name__ == '__main__':
    main()
