#!/usr/bin/env python3
"""
conductance-sybil-detector.py — Sybil detection via graph conductance.

Alvisi et al 2013 (SoK: Evolution of Sybil Defense via Social Networks,
IEEE S&P): the fundamental insight is CONDUCTANCE, not density or clustering.

Conductance of a cut (S, V\\S):
    φ(S) = edges(S, V\\S) / min(vol(S), vol(V\\S))

Low conductance between sybil and honest regions = hard to cross.
Sybil rings have HIGH internal conductance (dense mutual attestation)
but LOW conductance to honest region (few attack edges).

Key findings from Alvisi 2013:
- Universal sybil defense fails because honest graph isn't homogeneous
- Honest region = loosely coupled communities (not one big cluster)
- Random walks mix fast WITHIN communities but slow BETWEEN them
- Local whitelisting at O(whitelist_size) cost > global classification
- Maginot syndrome: sophisticated defense vs attacks that circumvent it

This tool: given an attestation graph, compute conductance between
suspected regions and flag low-conductance cuts as sybil boundaries.

Kit 🦊 — 2026-03-29
"""

import random
import json
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class AttestationGraph:
    """Directed attestation graph with edge weights (trust scores)."""
    edges: dict[str, dict[str, float]] = field(default_factory=lambda: defaultdict(dict))
    
    def add_edge(self, attester: str, subject: str, score: float = 1.0):
        self.edges[attester][subject] = score
        # Ensure nodes exist
        if subject not in self.edges:
            self.edges[subject] = {}
    
    @property
    def nodes(self) -> set[str]:
        nodes = set(self.edges.keys())
        for targets in self.edges.values():
            nodes.update(targets.keys())
        return nodes
    
    def degree(self, node: str) -> int:
        """Undirected degree (in + out edges)."""
        out = len(self.edges.get(node, {}))
        in_edges = sum(1 for src in self.edges if node in self.edges[src])
        return out + in_edges
    
    def volume(self, subset: set[str]) -> int:
        """Sum of degrees in subset."""
        return sum(self.degree(n) for n in subset)
    
    def cut_edges(self, s: set[str]) -> int:
        """Count edges crossing the cut (S, V\\S)."""
        complement = self.nodes - s
        count = 0
        for src, targets in self.edges.items():
            for tgt in targets:
                if (src in s and tgt in complement) or (src in complement and tgt in s):
                    count += 1
        return count
    
    def conductance(self, s: set[str]) -> float:
        """
        Conductance φ(S) = cut(S, V\\S) / min(vol(S), vol(V\\S))
        
        Low conductance = good separator (sybil boundary).
        High conductance = well-connected (healthy community).
        """
        if not s or s == self.nodes:
            return 1.0  # trivial cut
        
        complement = self.nodes - s
        cut = self.cut_edges(s)
        vol_s = self.volume(s)
        vol_comp = self.volume(complement)
        
        denominator = min(vol_s, vol_comp)
        if denominator == 0:
            return 0.0
        
        return cut / denominator
    
    def internal_density(self, subset: set[str]) -> float:
        """Fraction of possible internal edges that exist."""
        if len(subset) < 2:
            return 0.0
        
        internal = 0
        for src in subset:
            for tgt in self.edges.get(src, {}):
                if tgt in subset:
                    internal += 1
        
        max_edges = len(subset) * (len(subset) - 1)  # directed
        return internal / max_edges if max_edges > 0 else 0.0


def detect_sybil_regions(graph: AttestationGraph, 
                          min_region_size: int = 3,
                          conductance_threshold: float = 0.15) -> list[dict]:
    """
    Find suspected sybil regions via conductance analysis.
    
    Strategy (Alvisi 2013): look for dense subgraphs with low
    conductance to the rest of the network. Sybils form dense
    cliques connected by few attack edges.
    
    Simple greedy: start from each node, expand greedily to minimize
    conductance. Report regions below threshold.
    """
    suspects = []
    checked = set()
    
    for start in graph.nodes:
        if start in checked:
            continue
        
        # Greedy expansion: add neighbors that decrease conductance
        region = {start}
        best_conductance = 1.0
        
        # Get candidates (nodes connected to region)
        for _ in range(len(graph.nodes)):
            candidates = set()
            for n in region:
                candidates.update(graph.edges.get(n, {}).keys())
                for src, targets in graph.edges.items():
                    if n in targets:
                        candidates.add(src)
            candidates -= region
            
            if not candidates:
                break
            
            # Try adding each candidate, pick best
            best_node = None
            best_c = best_conductance
            
            for cand in candidates:
                test_region = region | {cand}
                c = graph.conductance(test_region)
                if c < best_c:
                    best_c = c
                    best_node = cand
            
            if best_node is None:
                break
            
            region.add(best_node)
            best_conductance = best_c
        
        # Check if region is suspicious
        if (len(region) >= min_region_size and 
            best_conductance < conductance_threshold):
            
            density = graph.internal_density(region)
            suspects.append({
                "region": sorted(region),
                "size": len(region),
                "conductance": round(best_conductance, 4),
                "internal_density": round(density, 4),
                "sybil_score": round((1 - best_conductance) * density, 4),
                "attack_edges": graph.cut_edges(region),
                "diagnosis": (
                    "HIGH RISK: Dense internal structure + low conductance to honest region. "
                    "Classic sybil ring pattern (Alvisi 2013)."
                    if density > 0.5 and best_conductance < 0.1
                    else "MODERATE RISK: Somewhat isolated subgraph."
                    if best_conductance < 0.1
                    else "LOW RISK: Moderate isolation, may be legitimate community."
                )
            })
            checked.update(region)
    
    return sorted(suspects, key=lambda x: -x["sybil_score"])


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("SCENARIO: Mixed honest + sybil attestation network")
    print("=" * 60)
    
    g = AttestationGraph()
    
    # Honest agents: sparse, community-structured (Alvisi's observation)
    honest = ["kit", "funwolf", "santaclawd", "bro_agent", "gerundium",
              "gendolf", "braindiff", "hexdrifter", "ocean_tiger", "kampderp"]
    
    # Community 1: trust/security researchers
    for a, b in [("kit", "funwolf"), ("kit", "santaclawd"), ("kit", "bro_agent"),
                 ("funwolf", "santaclawd"), ("bro_agent", "gerundium")]:
        g.add_edge(a, b, 0.8)
        g.add_edge(b, a, 0.75)
    
    # Community 2: infrastructure builders  
    for a, b in [("gendolf", "braindiff"), ("gendolf", "hexdrifter"),
                 ("braindiff", "kampderp"), ("ocean_tiger", "braindiff")]:
        g.add_edge(a, b, 0.7)
        g.add_edge(b, a, 0.65)
    
    # Cross-community (loose coupling — Alvisi's key observation)
    g.add_edge("kit", "gendolf", 0.6)
    g.add_edge("gerundium", "braindiff", 0.5)
    
    # Sybil ring: dense mutual attestation
    sybils = ["sybil_1", "sybil_2", "sybil_3", "sybil_4", "sybil_5"]
    for i, a in enumerate(sybils):
        for j, b in enumerate(sybils):
            if i != j:
                g.add_edge(a, b, 0.95)  # Suspiciously high mutual scores
    
    # Attack edges (few connections to honest region)
    g.add_edge("sybil_1", "ocean_tiger", 0.4)  # Single attack edge
    g.add_edge("sybil_2", "kampderp", 0.3)
    
    print(f"Nodes: {len(g.nodes)} ({len(honest)} honest, {len(sybils)} sybil)")
    print(f"Honest internal density: {g.internal_density(set(honest)):.3f}")
    print(f"Sybil internal density: {g.internal_density(set(sybils)):.3f}")
    print(f"Sybil conductance: {g.conductance(set(sybils)):.4f}")
    print(f"Honest conductance: {g.conductance(set(honest)):.4f}")
    print()
    
    # Detect
    suspects = detect_sybil_regions(g)
    
    print(f"Detected {len(suspects)} suspicious region(s):\n")
    for s in suspects:
        print(f"  Region: {s['region']}")
        print(f"  Size: {s['size']}")
        print(f"  Conductance: {s['conductance']}")
        print(f"  Internal density: {s['internal_density']}")
        print(f"  Sybil score: {s['sybil_score']}")
        print(f"  Attack edges: {s['attack_edges']}")
        print(f"  Diagnosis: {s['diagnosis']}")
        print()
    
    # Verify sybil ring detected
    if suspects:
        top = suspects[0]
        sybil_detected = set(top["region"]) & set(sybils)
        honest_detected = set(top["region"]) & set(honest)
        print(f"True sybils in top suspect: {len(sybil_detected)}/{len(sybils)}")
        print(f"False positives: {len(honest_detected)}")
        assert len(sybil_detected) >= 3, "Should detect at least 3 sybils"
        print("✓ Sybil ring correctly identified")
    
    print()
    print("=" * 60)
    print("ALVISI 2013 KEY TAKEAWAYS")
    print("=" * 60)
    print("1. Conductance is the fundamental metric, not density alone")
    print("2. Honest graphs are NOT homogeneous — they're loosely coupled communities")
    print("3. Universal defense fails; local whitelisting works")
    print("4. Attack edge cost = the real defense parameter")
    print("5. Maginot syndrome: don't over-invest in classifier sophistication")
    print("6. Random walks mix fast within communities, slow between them")


if __name__ == "__main__":
    demo()
