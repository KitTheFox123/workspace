#!/usr/bin/env python3
"""
sybil-percolation-cost.py — Sybil attack cost analysis via percolation theory.

Core insight: sybil rings percolate (form giant connected component) when
mutual attestation creates zero-cost edges. COMMIT_ANCHOR requirement
makes attestation nonzero-cost, creating asymmetric attack economics.

Honest network: N agents, each creates ~k attestations → O(N*k) anchors.
Sybil ring: N fake agents, must attest each other → O(N²) anchors for
fully-connected ring, O(N*k) for sparse ring.

The defense: require COMMIT_ANCHOR (Sigstore hash + RFC 3161 timestamp)
per attestation. Each anchor has compute + time cost. Sybils need
quadratic anchors to achieve percolation; honest nets need linear.

Percolation threshold (Erdos-Renyi): p_c = 1/N for giant component.
For sybils to blend in, they need enough cross-edges to honest network
to exceed p_c. Each cross-edge costs an anchor. Defense: rate-limit
anchor creation per identity (AIMD).

Sources:
- Artime et al (Nature Reviews Physics, Feb 2024): Robustness and
  resilience of complex networks. Percolation framework.
- Erdos & Renyi (1959): Random graph giant component threshold.
- Douceur (2002): The Sybil Attack. Identity cost as defense.

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field


@dataclass
class AttestationAnchor:
    """A COMMIT_ANCHOR: Sigstore hash + RFC 3161 timestamp."""
    from_agent: str
    to_agent: str
    cost: float  # Compute + time cost units
    timestamp: float  # Simulated time


@dataclass 
class NetworkAnalysis:
    total_agents: int
    honest_agents: int
    sybil_agents: int
    honest_anchors: int
    sybil_anchors: int
    honest_cost: float
    sybil_cost: float
    cost_ratio: float  # sybil_cost / honest_cost
    sybil_percolated: bool  # Did sybils form giant component?
    sybil_detected: bool    # Were sybils detected by cost anomaly?
    largest_sybil_component: int
    percolation_threshold: float


def find_components(agents: list[str], edges: list[tuple[str, str]]) -> list[set]:
    """Find connected components via BFS."""
    adj = {a: set() for a in agents}
    for a, b in edges:
        if a in adj and b in adj:
            adj[a].add(b)
            adj[b].add(a)
    
    visited = set()
    components = []
    
    for agent in agents:
        if agent in visited:
            continue
        comp = set()
        queue = [agent]
        while queue:
            node = queue.pop()
            if node in visited:
                continue
            visited.add(node)
            comp.add(node)
            for neighbor in adj[node]:
                if neighbor not in visited:
                    queue.append(neighbor)
        components.append(comp)
    
    return sorted(components, key=len, reverse=True)


def simulate_network(
    n_honest: int = 50,
    n_sybil: int = 20,
    honest_k: int = 4,       # Avg attestations per honest agent
    sybil_internal_k: int = 8,  # Avg internal sybil attestations
    sybil_bridge_k: int = 2,    # Cross-edges to honest network
    anchor_cost: float = 1.0,   # Cost per COMMIT_ANCHOR
    seed: int = 42
) -> NetworkAnalysis:
    """
    Simulate honest + sybil network and analyze percolation + costs.
    """
    rng = random.Random(seed)
    
    honest = [f"honest_{i}" for i in range(n_honest)]
    sybils = [f"sybil_{i}" for i in range(n_sybil)]
    all_agents = honest + sybils
    
    honest_edges = []
    sybil_internal_edges = []
    sybil_bridge_edges = []
    
    # Honest network: sparse, organic attestation
    for agent in honest:
        targets = rng.sample([a for a in honest if a != agent], 
                           min(honest_k, n_honest - 1))
        for t in targets:
            honest_edges.append((agent, t))
    
    # Sybil internal: dense mutual attestation (ring structure)
    for agent in sybils:
        targets = rng.sample([s for s in sybils if s != agent],
                           min(sybil_internal_k, n_sybil - 1))
        for t in targets:
            sybil_internal_edges.append((agent, t))
    
    # Sybil bridge: cross-edges to honest network
    for agent in sybils:
        targets = rng.sample(honest, min(sybil_bridge_k, n_honest))
        for t in targets:
            sybil_bridge_edges.append((agent, t))
    
    # Cost analysis
    honest_anchors = len(honest_edges)
    sybil_anchors = len(sybil_internal_edges) + len(sybil_bridge_edges)
    honest_cost = honest_anchors * anchor_cost
    sybil_cost = sybil_anchors * anchor_cost
    
    # Per-agent costs
    honest_per_agent = honest_cost / max(n_honest, 1)
    sybil_per_agent = sybil_cost / max(n_sybil, 1)
    
    # Percolation analysis: do sybils form giant component?
    sybil_components = find_components(sybils, sybil_internal_edges)
    largest_sybil = len(sybil_components[0]) if sybil_components else 0
    sybil_percolated = largest_sybil > n_sybil * 0.5
    
    # Detection: cost anomaly
    # Sybils spend more per-agent on internal attestation
    sybil_detected = sybil_per_agent > honest_per_agent * 1.5
    
    # Erdos-Renyi threshold
    p_c = 1.0 / max(len(all_agents), 1)
    
    return NetworkAnalysis(
        total_agents=len(all_agents),
        honest_agents=n_honest,
        sybil_agents=n_sybil,
        honest_anchors=honest_anchors,
        sybil_anchors=sybil_anchors,
        honest_cost=honest_cost,
        sybil_cost=sybil_cost,
        cost_ratio=sybil_cost / max(honest_cost, 0.01),
        sybil_percolated=sybil_percolated,
        sybil_detected=sybil_detected,
        largest_sybil_component=largest_sybil,
        percolation_threshold=p_c
    )


def demo():
    print("=" * 65)
    print("SYBIL PERCOLATION COST ANALYSIS")
    print("=" * 65)
    print()
    print("Defense: COMMIT_ANCHOR (Sigstore + RFC 3161) per attestation.")
    print("Honest agents: sparse, organic attestation patterns.")
    print("Sybil rings: dense internal + bridge edges to honest net.")
    print()
    
    scenarios = [
        ("Baseline: no anchor cost", 0.0),
        ("Low anchor cost (0.5)", 0.5),
        ("Standard anchor cost (1.0)", 1.0),
        ("High anchor cost (2.0)", 2.0),
    ]
    
    print(f"{'Scenario':<30} {'Honest$':>8} {'Sybil$':>8} {'Ratio':>6} {'Percolated':>11} {'Detected':>9}")
    print("-" * 80)
    
    for name, cost in scenarios:
        result = simulate_network(
            n_honest=50, n_sybil=20,
            honest_k=4, sybil_internal_k=8, sybil_bridge_k=2,
            anchor_cost=cost
        )
        print(f"{name:<30} {result.honest_cost:>8.1f} {result.sybil_cost:>8.1f} "
              f"{result.cost_ratio:>6.2f} {str(result.sybil_percolated):>11} {str(result.sybil_detected):>9}")
    
    print()
    print("=" * 65)
    print("SCALING ANALYSIS: Sybil ring size vs cost")
    print("=" * 65)
    print()
    print(f"{'Sybil N':>8} {'Sybil Anchors':>14} {'Cost':>8} {'Per-Agent':>10} {'Percolated':>11}")
    print("-" * 55)
    
    for n_sybil in [5, 10, 20, 50, 100]:
        result = simulate_network(
            n_honest=50, n_sybil=n_sybil,
            honest_k=4, sybil_internal_k=min(8, n_sybil - 1),
            sybil_bridge_k=2, anchor_cost=1.0
        )
        per_agent = result.sybil_cost / max(n_sybil, 1)
        print(f"{n_sybil:>8} {result.sybil_anchors:>14} {result.sybil_cost:>8.1f} "
              f"{per_agent:>10.1f} {str(result.sybil_percolated):>11}")
    
    print()
    print("=" * 65)
    print("KEY INSIGHT")
    print("=" * 65)
    print()
    print("Without anchor costs: sybil rings are free to create.")
    print("With anchor costs: dense internal attestation becomes expensive.")
    print("Honest networks are sparse (O(N*k)). Sybil rings need density")
    print("for percolation (O(N*k') where k' >> k).")
    print()
    print("The quadratic scaling kicks in when sybils need to FULLY connect")
    print("(k' → N). Sparse sybil rings are cheaper but don't percolate.")
    print("Dense sybil rings percolate but cost anomaly = detectable.")
    print()
    print("This is Douceur (2002) + Artime et al (2024):")
    print("make identity creation expensive + use percolation theory")
    print("to set the cost threshold where sybil attacks become uneconomic.")
    
    # Detailed result for reference
    print()
    result = simulate_network(n_honest=50, n_sybil=20, anchor_cost=1.0)
    print(f"Reference scenario: {result.honest_agents} honest + {result.sybil_agents} sybil")
    print(f"  Honest anchors: {result.honest_anchors} (cost: {result.honest_cost})")
    print(f"  Sybil anchors: {result.sybil_anchors} (cost: {result.sybil_cost})")
    print(f"  Cost ratio: {result.cost_ratio:.2f}x")
    print(f"  Largest sybil component: {result.largest_sybil_component}/{result.sybil_agents}")
    print(f"  Sybil percolated: {result.sybil_percolated}")
    print(f"  Detected by cost anomaly: {result.sybil_detected}")


if __name__ == "__main__":
    demo()
