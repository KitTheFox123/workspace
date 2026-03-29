#!/usr/bin/env python3
"""
conductance-sybil-detector.py — Sybil detection via graph conductance.

From Alvisi et al (IEEE S&P 2013, "SoK: The Evolution of Sybil Defense
via Social Networks"): sybil defense is fundamentally a CONDUCTANCE problem.

Key insights from the paper:
1. Honest region is NOT homogeneous — it's loosely-coupled tightly-knit communities
2. Universal sybil defense fails because it assumes homogeneity
3. Local whitelisting works because communities ARE real structures
4. Conductance = edges leaving community / min(volume of community, volume of rest)
5. Low conductance between honest and sybil regions = hard to cross

Maginot syndrome (Alvisi): "ever-more-sophisticated defense against attacks
the enemy easily circumvents." RenRen data showed sybils that all existing
defenses missed.

This tool computes conductance between regions of a trust graph and flags
potential sybil regions (dense internally, sparse connections outward).

Kit 🦊 — 2026-03-29
"""

import json
import random
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class TrustGraph:
    """Directed trust graph with weighted edges."""
    edges: dict[str, dict[str, float]] = field(default_factory=lambda: defaultdict(dict))
    
    def add_edge(self, src: str, dst: str, weight: float = 1.0):
        self.edges[src][dst] = weight
    
    def nodes(self) -> set[str]:
        nodes = set(self.edges.keys())
        for neighbors in self.edges.values():
            nodes.update(neighbors.keys())
        return nodes
    
    def degree(self, node: str) -> int:
        """Out-degree + in-degree."""
        out = len(self.edges.get(node, {}))
        in_deg = sum(1 for neighbors in self.edges.values() if node in neighbors)
        return out + in_deg
    
    def volume(self, subset: set[str]) -> float:
        """Sum of degrees of nodes in subset."""
        return sum(self.degree(n) for n in subset)
    
    def cut_weight(self, s: set[str], t: set[str]) -> float:
        """Total weight of edges crossing from s to t (directed)."""
        weight = 0.0
        for src in s:
            for dst, w in self.edges.get(src, {}).items():
                if dst in t:
                    weight += w
        for src in t:
            for dst, w in self.edges.get(src, {}).items():
                if dst in s:
                    weight += w
        return weight
    
    def conductance(self, subset: set[str]) -> float:
        """
        Conductance φ(S) = cut(S, V\S) / min(vol(S), vol(V\S))
        
        Low conductance = well-separated from rest of graph.
        Sybil regions have LOW conductance to honest region
        but HIGH internal density.
        """
        all_nodes = self.nodes()
        complement = all_nodes - subset
        
        if not subset or not complement:
            return 1.0  # Trivial partition
        
        cut = self.cut_weight(subset, complement)
        vol_s = self.volume(subset)
        vol_c = self.volume(complement)
        
        denominator = min(vol_s, vol_c)
        if denominator == 0:
            return 0.0
        
        return cut / denominator
    
    def internal_density(self, subset: set[str]) -> float:
        """Fraction of possible internal edges that exist."""
        if len(subset) < 2:
            return 0.0
        
        internal_edges = 0
        for src in subset:
            for dst in self.edges.get(src, {}):
                if dst in subset:
                    internal_edges += 1
        
        max_edges = len(subset) * (len(subset) - 1)  # Directed
        return internal_edges / max_edges if max_edges > 0 else 0.0


@dataclass
class SybilAnalysis:
    region_name: str
    nodes: set[str]
    conductance: float
    internal_density: float
    is_suspicious: bool
    reason: str
    alvisi_score: float  # Combined suspicion score


class ConductanceSybilDetector:
    """
    Detects sybil regions via conductance analysis.
    
    Alvisi's key observation: sybil regions are
    - Dense internally (mutual attestation is cheap)
    - Sparse connections to honest region (attack edges are expensive)
    - Low conductance = isolated from honest graph
    
    But honest communities ALSO have low conductance!
    Distinguishing factor: honest communities have MODERATE internal density.
    Sybil rings have VERY HIGH internal density (everyone attests everyone).
    """
    
    # Thresholds from Alvisi 2013 + empirical
    CONDUCTANCE_THRESHOLD = 0.15     # Below = suspicious isolation
    DENSITY_THRESHOLD = 0.7          # Above = suspiciously dense
    HONEST_DENSITY_RANGE = (0.1, 0.5)  # Honest communities: moderate density
    
    def analyze_region(self, graph: TrustGraph, region: set[str], 
                       name: str = "unknown") -> SybilAnalysis:
        conductance = graph.conductance(region)
        density = graph.internal_density(region)
        
        suspicious = False
        reason = "Normal"
        
        # Alvisi pattern: low conductance + high density = sybil ring
        if conductance < self.CONDUCTANCE_THRESHOLD and density > self.DENSITY_THRESHOLD:
            suspicious = True
            reason = (f"Sybil pattern: low conductance ({conductance:.3f}) + "
                     f"high density ({density:.3f}). Alvisi 2013: dense internal "
                     f"connections with few attack edges to honest region.")
        elif conductance < self.CONDUCTANCE_THRESHOLD and density <= self.HONEST_DENSITY_RANGE[1]:
            reason = (f"Legitimate community: low conductance ({conductance:.3f}) "
                     f"but moderate density ({density:.3f}). Tightly-knit but not "
                     f"suspiciously dense.")
        elif density > self.DENSITY_THRESHOLD and conductance >= self.CONDUCTANCE_THRESHOLD:
            reason = (f"Dense but connected: high density ({density:.3f}) but "
                     f"adequate conductance ({conductance:.3f}). Engaged cluster.")
        
        # Alvisi score: higher = more suspicious
        # Combines isolation (low conductance) with density (high internal)
        isolation = max(0, 1.0 - conductance / self.CONDUCTANCE_THRESHOLD)
        excess_density = max(0, (density - self.HONEST_DENSITY_RANGE[1]) / 
                           (1.0 - self.HONEST_DENSITY_RANGE[1]))
        alvisi_score = (isolation * 0.5 + excess_density * 0.5)
        
        return SybilAnalysis(
            region_name=name,
            nodes=region,
            conductance=conductance,
            internal_density=density,
            is_suspicious=suspicious,
            reason=reason,
            alvisi_score=alvisi_score
        )
    
    def detect_all(self, graph: TrustGraph, 
                   regions: dict[str, set[str]]) -> list[SybilAnalysis]:
        results = []
        for name, nodes in regions.items():
            analysis = self.analyze_region(graph, nodes, name)
            results.append(analysis)
        return sorted(results, key=lambda x: -x.alvisi_score)


def build_demo_graph() -> tuple[TrustGraph, dict[str, set[str]]]:
    """Build a graph with honest communities and a sybil ring."""
    g = TrustGraph()
    random.seed(42)
    
    # Honest community 1: security researchers (moderate density)
    honest_1 = {"kit", "bro_agent", "funwolf", "santaclawd", "gerundium"}
    for a in honest_1:
        for b in honest_1:
            if a != b and random.random() < 0.35:  # ~35% edge probability
                g.add_edge(a, b, 0.7 + random.random() * 0.3)
    
    # Honest community 2: philosophy agents (moderate density)
    honest_2 = {"pi_openclaw", "jarvisz", "aletheaveyra", "drainfun"}
    for a in honest_2:
        for b in honest_2:
            if a != b and random.random() < 0.4:
                g.add_edge(a, b, 0.6 + random.random() * 0.3)
    
    # Cross-community edges (sparse — communities are loosely coupled)
    g.add_edge("kit", "pi_openclaw", 0.8)
    g.add_edge("bro_agent", "aletheaveyra", 0.7)
    g.add_edge("funwolf", "drainfun", 0.6)
    
    # Sybil ring: dense mutual attestation
    sybil_ring = {"sybil_1", "sybil_2", "sybil_3", "sybil_4", "sybil_5"}
    for a in sybil_ring:
        for b in sybil_ring:
            if a != b:  # 100% internal edges
                g.add_edge(a, b, 0.95)
    
    # Attack edges (few connections to honest region)
    g.add_edge("sybil_1", "gerundium", 0.5)  # One attack edge
    g.add_edge("sybil_2", "drainfun", 0.4)   # Another
    
    regions = {
        "security_researchers": honest_1,
        "philosophy_agents": honest_2,
        "suspected_ring": sybil_ring,
    }
    
    return g, regions


def demo():
    g, regions = build_demo_graph()
    detector = ConductanceSybilDetector()
    
    print("=" * 60)
    print("CONDUCTANCE-BASED SYBIL DETECTION")
    print("Alvisi et al, IEEE S&P 2013")
    print("=" * 60)
    print()
    print(f"Graph: {len(g.nodes())} nodes")
    print(f"Regions: {list(regions.keys())}")
    print()
    
    results = detector.detect_all(g, regions)
    
    for r in results:
        flag = "🚨 SYBIL" if r.is_suspicious else "✓ HONEST"
        print(f"[{flag}] {r.region_name}")
        print(f"  Nodes: {sorted(r.nodes)}")
        print(f"  Conductance: {r.conductance:.4f} (threshold: {detector.CONDUCTANCE_THRESHOLD})")
        print(f"  Internal density: {r.internal_density:.4f} (sybil threshold: {detector.DENSITY_THRESHOLD})")
        print(f"  Alvisi score: {r.alvisi_score:.3f} (higher = more suspicious)")
        print(f"  Assessment: {r.reason}")
        print()
    
    # Verify sybil ring detected
    sybil_result = next(r for r in results if r.region_name == "suspected_ring")
    assert sybil_result.is_suspicious, "Sybil ring should be flagged"
    assert sybil_result.internal_density > 0.9, "Sybil ring should be very dense"
    
    # Verify honest communities NOT flagged
    for r in results:
        if "honest" in r.region_name or "security" in r.region_name or "philosophy" in r.region_name:
            assert not r.is_suspicious, f"{r.region_name} should not be flagged"
    
    print("=" * 60)
    print("MAGINOT SYNDROME WARNING (Alvisi 2013)")
    print("=" * 60)
    print("Conductance alone isn't enough. Sophisticated sybils will:")
    print("1. Lower internal density (don't attest everyone)")
    print("2. Increase attack edges (befriend honest nodes)")
    print("3. Mimic honest community structure")
    print()
    print("Defense in depth: conductance + temporal PoW + DKIM chains")
    print("+ behavioral fingerprinting + attester diversity scoring.")
    print()
    print("ALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
