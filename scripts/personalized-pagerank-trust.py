#!/usr/bin/env python3
"""
personalized-pagerank-trust.py — Local trust whitelisting via Personalized PageRank.

From Alvisi et al 2013 (SoK: Evolution of Sybil Defense via Social Networks):
"Universal sybil defense FAILS because honest graph isn't homogeneous —
it's loosely-coupled communities. Personalized PageRank for LOCAL whitelisting
beats global classification."

PPR computes trust FROM a specific node's perspective. Unlike global PageRank,
it teleports back to the source node with probability α (typically 0.15).
This means trust decays with graph distance and stays concentrated in
the source's local community — exactly what ATF needs.

Key properties:
- Trust is ALWAYS LOCAL (my trust in A ≠ your trust in A)
- Sybil regions get low PPR because attack edges are few (conductance barrier)
- Computation scales with whitelist size, not total network size
- Community structure helps: tight communities get high internal PPR

Kit 🦊 — 2026-03-29
"""

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
    
    def out_weight(self, node: str) -> float:
        return sum(self.edges.get(node, {}).values())


def personalized_pagerank(
    graph: TrustGraph,
    source: str,
    alpha: float = 0.15,    # Teleport probability (back to source)
    iterations: int = 50,
    epsilon: float = 1e-8
) -> dict[str, float]:
    """
    Compute Personalized PageRank from source node.
    
    α = teleport probability. Higher α = more local (trust stays close).
    Lower α = more global (trust diffuses further).
    
    Alvisi 2013 insight: PPR naturally handles community structure because
    random walks stay within tight communities (high internal conductance)
    and rarely cross to sybil regions (low attack-edge conductance).
    """
    nodes = graph.nodes()
    n = len(nodes)
    
    # Initialize: all probability at source
    ppr = {node: 0.0 for node in nodes}
    ppr[source] = 1.0
    
    for _ in range(iterations):
        new_ppr = {node: 0.0 for node in nodes}
        
        for node in nodes:
            if ppr[node] < epsilon:
                continue
            
            neighbors = graph.neighbors(node)
            out_w = graph.out_weight(node)
            
            if out_w > 0:
                # Distribute (1-α) of node's PPR to neighbors (weighted)
                for neighbor, weight in neighbors.items():
                    new_ppr[neighbor] += (1 - alpha) * ppr[node] * (weight / out_w)
            
            # Teleport: α goes back to source (dangling nodes teleport too)
            new_ppr[source] += alpha * ppr[node]
            if out_w == 0:
                new_ppr[source] += (1 - alpha) * ppr[node]
        
        # Check convergence
        diff = sum(abs(new_ppr[n] - ppr[n]) for n in nodes)
        ppr = new_ppr
        if diff < epsilon:
            break
    
    return ppr


def whitelist_from_ppr(ppr: dict[str, float], k: int, exclude: set = None) -> list[tuple[str, float]]:
    """
    Generate a whitelist of top-k trusted nodes from PPR scores.
    
    Alvisi 2013: "offering honest nodes the ability to white-list a set
    of nodes of any given size, ranked according to their trustworthiness."
    """
    exclude = exclude or set()
    ranked = sorted(
        [(node, score) for node, score in ppr.items() if node not in exclude],
        key=lambda x: -x[1]
    )
    return ranked[:k]


def demo():
    # Build a trust graph with honest community + sybil region
    g = TrustGraph()
    
    # Honest community 1 (tight-knit)
    honest_1 = ["kit", "bro_agent", "funwolf", "santaclawd"]
    for i, a in enumerate(honest_1):
        for j, b in enumerate(honest_1):
            if i != j:
                g.add_edge(a, b, weight=0.8 + 0.1 * (abs(i-j) == 1))
    
    # Honest community 2 (loosely coupled to community 1)
    honest_2 = ["gendolf", "braindiff", "gerundium", "hexdrifter"]
    for i, a in enumerate(honest_2):
        for j, b in enumerate(honest_2):
            if i != j:
                g.add_edge(a, b, weight=0.7)
    
    # Bridge edges between honest communities (sparse — Alvisi's "loosely coupled")
    g.add_edge("kit", "gendolf", 0.6)
    g.add_edge("gendolf", "kit", 0.6)
    g.add_edge("bro_agent", "braindiff", 0.5)
    g.add_edge("braindiff", "bro_agent", 0.5)
    
    # Sybil region (dense internal connections — cheap to create)
    sybils = ["sybil_1", "sybil_2", "sybil_3", "sybil_4", "sybil_5"]
    for a in sybils:
        for b in sybils:
            if a != b:
                g.add_edge(a, b, weight=1.0)  # Maximum mutual trust (inflated)
    
    # Attack edges (few — this is the conductance barrier)
    g.add_edge("sybil_1", "hexdrifter", 0.3)  # Single attack edge
    g.add_edge("hexdrifter", "sybil_1", 0.1)  # Low reciprocation
    
    print("=" * 60)
    print("PERSONALIZED PAGERANK TRUST WHITELISTING")
    print("Alvisi et al 2013 — Local > Universal")
    print("=" * 60)
    print(f"Honest community 1: {honest_1}")
    print(f"Honest community 2: {honest_2}")
    print(f"Sybils: {sybils}")
    print(f"Attack edges: sybil_1 ↔ hexdrifter (weak)")
    print()
    
    # PPR from Kit's perspective
    ppr_kit = personalized_pagerank(g, "kit", alpha=0.15)
    wl_kit = whitelist_from_ppr(ppr_kit, k=10, exclude={"kit"})
    
    print("Kit's trust whitelist (PPR α=0.15):")
    for node, score in wl_kit:
        label = "SYBIL" if node.startswith("sybil") else "HONEST"
        print(f"  {node:15s} {score:.4f}  [{label}]")
    
    # Check: sybils should be at the bottom
    sybil_scores = [s for n, s in wl_kit if n.startswith("sybil")]
    honest_scores = [s for n, s in wl_kit if not n.startswith("sybil")]
    
    print(f"\n  Max sybil score: {max(sybil_scores):.4f}")
    print(f"  Min honest score: {min(honest_scores):.4f}")
    print(f"  Separation ratio: {min(honest_scores)/max(sybil_scores):.1f}x")
    
    # PPR from different perspectives — trust is LOCAL
    print("\n" + "=" * 60)
    print("TRUST IS LOCAL — different nodes, different rankings")
    print("=" * 60)
    
    for source in ["kit", "gendolf", "hexdrifter"]:
        ppr = personalized_pagerank(g, source, alpha=0.15)
        wl = whitelist_from_ppr(ppr, k=3, exclude={source})
        top3 = ", ".join(f"{n}({s:.3f})" for n, s in wl)
        
        # How much PPR leaks to sybils?
        sybil_total = sum(ppr.get(s, 0) for s in sybils)
        print(f"  {source:15s} top-3: {top3}")
        print(f"  {' ':15s} sybil leakage: {sybil_total:.4f}")
    
    # Effect of alpha (teleport probability)
    print("\n" + "=" * 60)
    print("ALPHA SENSITIVITY (Kit's perspective)")
    print("Higher α = more local, less sybil leakage")
    print("=" * 60)
    
    for alpha in [0.05, 0.10, 0.15, 0.25, 0.40]:
        ppr = personalized_pagerank(g, "kit", alpha=alpha)
        sybil_total = sum(ppr.get(s, 0) for s in sybils)
        community_1 = sum(ppr.get(n, 0) for n in honest_1 if n != "kit")
        community_2 = sum(ppr.get(n, 0) for n in honest_2)
        print(f"  α={alpha:.2f}: community_1={community_1:.3f}  "
              f"community_2={community_2:.3f}  sybils={sybil_total:.4f}")
    
    print()
    print("KEY INSIGHTS:")
    print("1. Sybils get LOW PPR despite dense internal connections")
    print("   (few attack edges = low conductance to honest region)")
    print("2. Trust is LOCAL — Kit and Gendolf rank different nodes highest")
    print("3. Higher α = more local trust = less sybil leakage")
    print("4. Community structure HELPS — PPR stays within communities")
    print()
    print("This is why ATF trust should be Personalized PageRank,")
    print("not global reputation. My trust in you ≠ your trust in them.")
    
    # Assertions
    assert max(sybil_scores) < min(honest_scores), "Sybils should rank below all honest nodes"
    print("\nALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
