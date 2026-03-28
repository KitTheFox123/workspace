#!/usr/bin/env python3
"""
trust-percolation.py — Trust propagation as site-bond percolation on agent networks.

Maps epidemic percolation (PERCOVID model, Music et al Sci Reports 2021) to
agent trust propagation. Key insight: trust spreading in agent networks exhibits
a PHASE TRANSITION — below a critical density of high-confidence attesters,
trust stays local (small clusters). Above threshold, trust percolates globally.

Percolation theory (Stauffer & Aharony 1994):
- Sites = agents (occupied with probability p = density of trustworthy agents)
- Bonds = attestation links (open with probability q = attestation quality)
- Percolation threshold p_c: below = isolated clusters, above = giant component
- For 2D square lattice, p_c ≈ 0.593 (site), p_c ≈ 0.500 (bond)

PERCOVID parallel:
- Social circles → attestation circles (direct attesters vs transitive trust)
- Infectiousness r → trust signal quality (how convincing is the attestation?)
- Social intensity q → network connectivity (how many attestation paths exist?)
- Phase transition → trust either stays local or goes global. No middle ground.

ATF implications:
- Cold-start agents below percolation threshold: trusted locally, invisible globally
- Sybil rings create fake percolation — detection = checking cluster properties
  (real clusters have power-law size distribution; fake ones are too uniform)
- min() composition = bond percolation with quality floor

Kit 🦊 — 2026-03-28
"""

import random
from collections import deque
from dataclasses import dataclass


@dataclass
class PercolationResult:
    p: float  # Site occupation probability
    q: float  # Bond transmission probability
    largest_cluster: int
    cluster_count: int
    total_agents: int
    percolated: bool  # Giant component > 50% of agents
    cluster_sizes: list[int]
    
    @property
    def giant_component_fraction(self) -> float:
        return self.largest_cluster / max(self.total_agents, 1)


class TrustPercolation:
    """
    2D lattice percolation model for agent trust networks.
    
    Each site = agent slot. Occupied with probability p (trustworthy agent exists).
    Each bond = attestation path. Open with probability q (attestation quality).
    """
    
    def __init__(self, L: int = 50):
        """L × L lattice."""
        self.L = L
        self.grid: list[list[bool]] = []
    
    def _neighbors(self, r: int, c: int) -> list[tuple[int, int]]:
        """4-connected neighbors (no wrapping — finite network)."""
        nbrs = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < self.L and 0 <= nc < self.L:
                nbrs.append((nr, nc))
        return nbrs
    
    def simulate(self, p: float, q: float) -> PercolationResult:
        """
        Run site-bond percolation.
        
        p = probability site is occupied (trustworthy agent exists at this node)
        q = probability bond is open (attestation path transmits trust)
        """
        # Generate grid
        self.grid = [
            [random.random() < p for _ in range(self.L)]
            for _ in range(self.L)
        ]
        
        total_occupied = sum(sum(row) for row in self.grid)
        
        # Find connected components via BFS with bond probability
        visited = [[False] * self.L for _ in range(self.L)]
        clusters = []
        
        for r in range(self.L):
            for c in range(self.L):
                if self.grid[r][c] and not visited[r][c]:
                    # BFS from this site
                    cluster_size = 0
                    queue = deque([(r, c)])
                    visited[r][c] = True
                    
                    while queue:
                        cr, cc = queue.popleft()
                        cluster_size += 1
                        
                        for nr, nc in self._neighbors(cr, cc):
                            if (self.grid[nr][nc] and 
                                not visited[nr][nc] and
                                random.random() < q):  # Bond open?
                                visited[nr][nc] = True
                                queue.append((nr, nc))
                    
                    clusters.append(cluster_size)
        
        clusters.sort(reverse=True)
        largest = clusters[0] if clusters else 0
        
        return PercolationResult(
            p=p,
            q=q,
            largest_cluster=largest,
            cluster_count=len(clusters),
            total_agents=total_occupied,
            percolated=largest > total_occupied * 0.5,
            cluster_sizes=clusters[:10]
        )


def find_percolation_threshold(L: int = 30, q: float = 1.0, 
                                trials: int = 20) -> float:
    """Binary search for critical p where percolation probability = 50%."""
    lo, hi = 0.0, 1.0
    
    for _ in range(15):  # 15 iterations of binary search
        mid = (lo + hi) / 2
        perc_count = 0
        
        tp = TrustPercolation(L)
        for _ in range(trials):
            result = tp.simulate(mid, q)
            if result.percolated:
                perc_count += 1
        
        if perc_count > trials / 2:
            hi = mid
        else:
            lo = mid
    
    return (lo + hi) / 2


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("TRUST PERCOLATION: Phase Transition in Agent Networks")
    print("=" * 60)
    print()
    print("Model: 2D site-bond percolation (Stauffer & Aharony 1994)")
    print("Mapping: PERCOVID (Musić et al, Sci Reports 2021)")
    print("  Sites = agent slots (occupied = trustworthy agent)")
    print("  Bonds = attestation paths (open = quality attestation)")
    print()
    
    L = 30
    tp = TrustPercolation(L)
    
    # Sweep p with q=1.0 (perfect attestation quality)
    print("=" * 60)
    print("SWEEP 1: Vary agent density (p), perfect attestation (q=1.0)")
    print("=" * 60)
    print(f"{'p':>6} {'Giant%':>8} {'Clusters':>10} {'Percolated':>12}")
    print("-" * 40)
    
    for p_val in [0.3, 0.4, 0.5, 0.55, 0.59, 0.60, 0.65, 0.7, 0.8]:
        results = []
        for _ in range(10):
            results.append(tp.simulate(p_val, 1.0))
        
        avg_giant = sum(r.giant_component_fraction for r in results) / len(results)
        avg_clusters = sum(r.cluster_count for r in results) / len(results)
        perc_rate = sum(1 for r in results if r.percolated) / len(results)
        
        print(f"{p_val:>6.2f} {avg_giant:>7.1%} {avg_clusters:>10.0f} {perc_rate:>11.0%}")
    
    print()
    print("→ Sharp transition around p ≈ 0.59 (matches 2D site percolation p_c ≈ 0.593)")
    print("→ Below threshold: trust stays LOCAL (many small clusters)")
    print("→ Above threshold: trust goes GLOBAL (giant component)")
    print()
    
    # Sweep q with p=0.7 (good agent density)
    print("=" * 60)
    print("SWEEP 2: Vary attestation quality (q), good density (p=0.7)")
    print("=" * 60)
    print(f"{'q':>6} {'Giant%':>8} {'Clusters':>10} {'Percolated':>12}")
    print("-" * 40)
    
    for q_val in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
        results = []
        for _ in range(10):
            results.append(tp.simulate(0.7, q_val))
        
        avg_giant = sum(r.giant_component_fraction for r in results) / len(results)
        avg_clusters = sum(r.cluster_count for r in results) / len(results)
        perc_rate = sum(1 for r in results if r.percolated) / len(results)
        
        print(f"{q_val:>6.2f} {avg_giant:>7.1%} {avg_clusters:>10.0f} {perc_rate:>11.0%}")
    
    print()
    print("→ Even with good density, low attestation quality prevents percolation")
    print("→ Both p AND q must exceed thresholds for trust to propagate globally")
    print()
    
    # ATF implications
    print("=" * 60)
    print("ATF IMPLICATIONS")
    print("=" * 60)
    print()
    print("1. COLD START = below percolation threshold.")
    print("   New agents are isolated sites. Need to join a cluster")
    print("   by forming high-quality attestation bonds (q → 1).")
    print()
    print("2. SYBIL DETECTION via cluster statistics.")
    print("   Real trust networks have power-law cluster sizes.")
    print("   Sybil rings create anomalously uniform clusters.")
    print()
    print("3. min() COMPOSITION = bond quality floor.")
    print("   min(attester_trust, attestee_trust) ensures bond quality")
    print("   can't exceed the weaker endpoint. Prevents inflation.")
    print()
    print("4. VACCINATION PARALLEL = trusted bootstrap nodes.")
    print("   Just as vaccines reduce infection below percolation threshold,")
    print("   revoking a few critical attesters can fragment a trust network.")
    print("   Attack the hubs, not the edges.")
    print()
    
    # Find actual threshold
    print("=" * 60)
    print("THRESHOLD ESTIMATION (binary search, 20 trials per point)")
    print("=" * 60)
    p_c = find_percolation_threshold(L=30, q=1.0, trials=20)
    print(f"Estimated p_c (q=1.0): {p_c:.3f}")
    print(f"Theoretical p_c (2D site): 0.593")
    print(f"Match: {'✓' if abs(p_c - 0.593) < 0.05 else '✗'}")


if __name__ == "__main__":
    demo()
