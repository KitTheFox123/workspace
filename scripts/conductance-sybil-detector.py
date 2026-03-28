#!/usr/bin/env python3
"""
conductance-sybil-detector.py — Conductance-based sybil detection for ATF.

Alvisi et al (IEEE S&P 2013, "SoK: The Evolution of Sybil Defense via Social
Networks"): conductance is THE structural property for sybil defense. Not
clustering coefficient, not popularity — conductance, because it directly
measures mixing time of random walks.

Conductance of a set S:
  φ(S) = |edges crossing boundary of S| / min(vol(S), vol(V\S))

Where vol(S) = sum of degrees in S.

Sybil regions have LOW conductance to the honest region (sparse attack edges)
but HIGH internal conductance (dense mutual attestation). This is the
structural signature we detect.

Method: Local spectral clustering (Spielman-Teng 2004, Andersen-Chung-Lang 2006).
Start from a trusted seed, do personalized PageRank, sweep-cut to find
the community boundary. Nodes outside the low-conductance cut = suspicious.

Kit 🦊 — 2026-03-28
"""

import json
import random
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class AttestationGraph:
    """Directed graph of attestations between agents."""
    edges: dict[str, dict[str, float]] = field(default_factory=lambda: defaultdict(dict))
    
    def add_attestation(self, attester: str, subject: str, score: float = 1.0):
        self.edges[attester][subject] = score
        # Ensure subject exists as node
        if subject not in self.edges:
            self.edges[subject] = {}
    
    @property
    def nodes(self) -> set[str]:
        nodes = set(self.edges.keys())
        for targets in self.edges.values():
            nodes.update(targets.keys())
        return nodes
    
    def undirected_neighbors(self, node: str) -> dict[str, float]:
        """Get all neighbors (both directions) with max edge weight."""
        neighbors = {}
        # Outgoing
        for target, score in self.edges.get(node, {}).items():
            neighbors[target] = max(neighbors.get(target, 0), score)
        # Incoming
        for source, targets in self.edges.items():
            if node in targets:
                neighbors[source] = max(neighbors.get(source, 0), targets[node])
        return neighbors
    
    def degree(self, node: str) -> int:
        return len(self.undirected_neighbors(node))
    
    def volume(self, node_set: set[str]) -> int:
        return sum(self.degree(n) for n in node_set)


def personalized_pagerank(graph: AttestationGraph, seed: str, 
                          alpha: float = 0.15, iterations: int = 50) -> dict[str, float]:
    """
    Personalized PageRank from seed node.
    
    alpha = teleport probability (back to seed).
    Higher alpha = more local (tighter community).
    Andersen-Chung-Lang (2006): PPR + sweep cut gives
    near-optimal local conductance guarantee.
    """
    nodes = graph.nodes
    scores = {n: 0.0 for n in nodes}
    scores[seed] = 1.0
    
    for _ in range(iterations):
        new_scores = {n: 0.0 for n in nodes}
        for node in nodes:
            neighbors = graph.undirected_neighbors(node)
            if not neighbors:
                new_scores[seed] += scores[node]  # dangling → teleport
                continue
            
            # Teleport
            new_scores[seed] += alpha * scores[node]
            
            # Spread
            total_weight = sum(neighbors.values())
            for neighbor, weight in neighbors.items():
                new_scores[neighbor] += (1 - alpha) * scores[node] * (weight / total_weight)
        
        scores = new_scores
    
    return scores


def sweep_cut(graph: AttestationGraph, ppr_scores: dict[str, float]) -> tuple[set[str], float]:
    """
    Sweep cut: sort nodes by PPR/degree ratio, find minimum conductance cut.
    
    This is the key insight from spectral methods: the Cheeger inequality
    connects the second eigenvalue of the graph Laplacian to conductance.
    PPR approximates the eigenvector locally.
    """
    # Sort by PPR/degree ratio (normalized score)
    nodes_by_score = []
    for node, score in ppr_scores.items():
        deg = max(graph.degree(node), 1)
        nodes_by_score.append((node, score / deg))
    
    nodes_by_score.sort(key=lambda x: -x[1])
    
    all_nodes = graph.nodes
    total_vol = graph.volume(all_nodes)
    
    best_conductance = float('inf')
    best_set = set()
    current_set = set()
    boundary_edges = 0
    current_vol = 0
    
    for node, _ in nodes_by_score[:-1]:  # Don't include last (trivial cut)
        current_set.add(node)
        
        # Update boundary edges and volume
        neighbors = graph.undirected_neighbors(node)
        for neighbor in neighbors:
            if neighbor in current_set:
                boundary_edges -= 1  # Was boundary, now internal
            else:
                boundary_edges += 1  # New boundary edge
        
        current_vol = graph.volume(current_set)
        complement_vol = total_vol - current_vol
        
        if min(current_vol, complement_vol) > 0:
            conductance = boundary_edges / min(current_vol, complement_vol)
            if conductance < best_conductance and len(current_set) > 1:
                best_conductance = conductance
                best_set = current_set.copy()
    
    return best_set, best_conductance


def detect_sybils(graph: AttestationGraph, trusted_seeds: list[str],
                  conductance_threshold: float = 0.3) -> dict:
    """
    Main detection: run PPR from each seed, sweep-cut, flag nodes
    outside the honest community.
    
    Conductance threshold: cuts below this are suspicious boundaries.
    Alvisi et al: sybil regions have conductance O(attack_edges / vol(sybil)).
    """
    # Aggregate PPR from all seeds
    combined_ppr = defaultdict(float)
    for seed in trusted_seeds:
        ppr = personalized_pagerank(graph, seed)
        for node, score in ppr.items():
            combined_ppr[node] += score / len(trusted_seeds)
    
    # Sweep cut on combined PPR
    honest_community, conductance = sweep_cut(graph, dict(combined_ppr))
    
    # Classify
    all_nodes = graph.nodes
    outside = all_nodes - honest_community
    
    # Score each outside node: how connected to honest vs. to other outsiders?
    classifications = {}
    for node in all_nodes:
        neighbors = graph.undirected_neighbors(node)
        honest_edges = sum(1 for n in neighbors if n in honest_community)
        outside_edges = sum(1 for n in neighbors if n in outside)
        total = honest_edges + outside_edges
        
        if node in honest_community:
            classifications[node] = {
                "classification": "HONEST",
                "ppr_score": round(combined_ppr.get(node, 0), 4),
                "honest_ratio": round(honest_edges / max(total, 1), 3)
            }
        else:
            # Check density: sybil regions are internally dense
            internal_density = outside_edges / max(total, 1)
            classifications[node] = {
                "classification": "SUSPICIOUS" if internal_density > 0.5 else "COLD_START",
                "ppr_score": round(combined_ppr.get(node, 0), 4),
                "honest_ratio": round(honest_edges / max(total, 1), 3),
                "internal_density": round(internal_density, 3)
            }
    
    return {
        "honest_community_size": len(honest_community),
        "outside_size": len(outside),
        "conductance": round(conductance, 4),
        "conductance_interpretation": (
            "LOW (< 0.3) = strong community boundary, likely sybil cut"
            if conductance < conductance_threshold else
            "HIGH (≥ 0.3) = weak boundary, may be legitimate periphery"
        ),
        "classifications": classifications,
        "methodology": "Personalized PageRank + sweep cut (Andersen-Chung-Lang 2006). "
                       "Sybil regions = low conductance to honest, high internal density."
    }


def demo():
    random.seed(42)
    g = AttestationGraph()
    
    # Honest cluster: sparse, organically connected
    honest = ["kit", "bro_agent", "funwolf", "santaclawd", "gendolf", 
              "braindiff", "gerundium", "holly", "arnold", "pi_openclaw"]
    
    # Organic honest attestations (sparse — trust is hard to earn)
    honest_edges = [
        ("kit", "bro_agent", 0.9), ("bro_agent", "kit", 0.85),
        ("kit", "funwolf", 0.8), ("funwolf", "kit", 0.75),
        ("kit", "santaclawd", 0.7), ("santaclawd", "kit", 0.8),
        ("bro_agent", "gendolf", 0.7), ("gendolf", "bro_agent", 0.65),
        ("funwolf", "braindiff", 0.6), ("braindiff", "funwolf", 0.7),
        ("gerundium", "kit", 0.65), ("holly", "kit", 0.7),
        ("arnold", "bro_agent", 0.6), ("pi_openclaw", "gendolf", 0.5),
        ("santaclawd", "braindiff", 0.55), ("holly", "arnold", 0.5),
    ]
    
    # Sybil ring: dense mutual attestation (free inflation)
    sybils = ["sybil_1", "sybil_2", "sybil_3", "sybil_4", "sybil_5"]
    sybil_edges = []
    for i, s1 in enumerate(sybils):
        for j, s2 in enumerate(sybils):
            if i != j:
                sybil_edges.append((s1, s2, 0.95))  # Dense! Everyone trusts everyone.
    
    # Attack edges: sparse connection to honest region
    attack_edges = [
        ("sybil_1", "pi_openclaw", 0.4),  # Single attack edge
    ]
    
    # Cold-start agent: genuinely new, not sybil
    coldstart_edges = [
        ("newbie", "kit", 0.3),  # One tentative attestation
    ]
    
    # Build graph
    for src, dst, score in honest_edges + sybil_edges + attack_edges + coldstart_edges:
        g.add_attestation(src, dst, score)
    
    print("=" * 60)
    print("CONDUCTANCE-BASED SYBIL DETECTION")
    print("=" * 60)
    print(f"Graph: {len(g.nodes)} nodes")
    print(f"Honest agents: {len(honest)}")
    print(f"Sybil ring: {len(sybils)} (dense mutual attestation)")
    print(f"Attack edges: {len(attack_edges)}")
    print(f"Cold-start: 1 (newbie)")
    print()
    
    # Detect with 2 trusted seeds
    result = detect_sybils(g, trusted_seeds=["kit", "bro_agent"])
    
    print(f"Honest community detected: {result['honest_community_size']} nodes")
    print(f"Outside community: {result['outside_size']} nodes")
    print(f"Cut conductance: {result['conductance']}")
    print(f"Interpretation: {result['conductance_interpretation']}")
    print()
    
    print("CLASSIFICATIONS:")
    for node, info in sorted(result["classifications"].items()):
        status = info["classification"]
        ppr = info["ppr_score"]
        marker = "✓" if status == "HONEST" else ("⚠" if status == "COLD_START" else "✗")
        extra = f" | internal_density={info.get('internal_density', 'n/a')}" if status != "HONEST" else ""
        print(f"  {marker} {node:15s} → {status:12s} PPR={ppr:.4f} honest_ratio={info['honest_ratio']}{extra}")
    
    print()
    
    # Verify: all honest nodes classified correctly
    honest_correct = sum(1 for h in honest 
                        if result["classifications"].get(h, {}).get("classification") == "HONEST")
    sybil_detected = sum(1 for s in sybils 
                        if result["classifications"].get(s, {}).get("classification") == "SUSPICIOUS")
    
    print(f"Honest recall: {honest_correct}/{len(honest)}")
    print(f"Sybil detection: {sybil_detected}/{len(sybils)}")
    print()
    print("Alvisi et al (2013): 'Instead of aiming for universal coverage,")
    print("sybil defense should settle for white-listing ranked by trust.'")
    print("ATF already does this — local trust, not global reputation.")


if __name__ == "__main__":
    demo()
