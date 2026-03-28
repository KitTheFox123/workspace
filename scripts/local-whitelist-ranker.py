#!/usr/bin/env python3
"""
local-whitelist-ranker.py — Local whitelisting for ATF sybil defense.

Alvisi et al (IEEE S&P 2013, "SoK: The Evolution of Sybil Defense via
Social Networks"): Universal sybil defense FAILS because honest graphs
aren't homogeneous — they're communities loosely coupled. Solution: 
local whitelisting. Rank nodes by trustworthiness WITHIN your neighborhood.
Cost = O(whitelist size), not O(network).

Implementation: personalized PageRank (PPR) from ego node, combined with
structural features (clustering coefficient, community overlap) to rank
neighbors. Sybils form dense cliques — PPR mass concentrates there but
clustering coefficient is artificially high, creating a detectable signal.

Kit 🦊 — 2026-03-28
"""

import random
import json
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Node:
    id: str
    is_sybil: bool = False
    trust_score: float = 0.0


class TrustGraph:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, set[str]] = defaultdict(set)
    
    def add_node(self, node_id: str, is_sybil: bool = False):
        self.nodes[node_id] = Node(id=node_id, is_sybil=is_sybil)
        if node_id not in self.edges:
            self.edges[node_id] = set()
    
    def add_edge(self, a: str, b: str):
        self.edges[a].add(b)
        self.edges[b].add(a)
    
    def degree(self, node_id: str) -> int:
        return len(self.edges.get(node_id, set()))
    
    def clustering_coefficient(self, node_id: str) -> float:
        """Local clustering coefficient — fraction of neighbor pairs that are connected."""
        neighbors = list(self.edges.get(node_id, set()))
        k = len(neighbors)
        if k < 2:
            return 0.0
        
        triangles = 0
        for i in range(len(neighbors)):
            for j in range(i + 1, len(neighbors)):
                if neighbors[j] in self.edges.get(neighbors[i], set()):
                    triangles += 1
        
        return (2 * triangles) / (k * (k - 1))
    
    def personalized_pagerank(self, ego: str, alpha: float = 0.15, 
                               iterations: int = 50) -> dict[str, float]:
        """
        Personalized PageRank from ego node.
        
        PPR = random walk that teleports back to ego with probability alpha.
        Nodes reachable through many short paths get high rank.
        Sybils behind sparse attack edges get lower PPR from honest egos.
        """
        # Initialize
        scores = {n: 0.0 for n in self.nodes}
        scores[ego] = 1.0
        
        for _ in range(iterations):
            new_scores = {n: 0.0 for n in self.nodes}
            for node_id in self.nodes:
                neighbors = self.edges.get(node_id, set())
                if not neighbors:
                    new_scores[ego] += scores[node_id]  # dangling → teleport
                    continue
                
                share = scores[node_id] / len(neighbors)
                for neighbor in neighbors:
                    new_scores[neighbor] += (1 - alpha) * share
                
                new_scores[ego] += alpha * scores[node_id]
            
            scores = new_scores
        
        # Normalize
        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}
        
        return scores


class LocalWhitelistRanker:
    """
    Rank nodes for local whitelisting using PPR + structural features.
    
    Alvisi et al key insight: "instead of aiming for universal coverage,
    sybil defense should settle for a more limited goal: offering honest
    nodes the ability to white-list a set of nodes of any given size,
    ranked accordingly to their trustworthiness."
    """
    
    def __init__(self, graph: TrustGraph):
        self.graph = graph
    
    def rank_for_ego(self, ego: str, whitelist_size: int = 10) -> list[dict]:
        """
        Produce a ranked whitelist for ego node.
        
        Score = PPR * structural_penalty
        
        Structural penalty: sybils have artificially HIGH clustering
        (dense cliques) but LOW community diversity. Penalize nodes
        whose clustering coefficient is suspiciously close to 1.0
        (perfect clique = sybil signal).
        """
        ppr = self.graph.personalized_pagerank(ego)
        
        candidates = []
        for node_id, ppr_score in ppr.items():
            if node_id == ego:
                continue
            
            cc = self.graph.clustering_coefficient(node_id)
            degree = self.graph.degree(node_id)
            
            # Structural penalty: perfect cliques (cc ≈ 1.0) are suspicious
            # Honest nodes in communities have cc ∈ [0.1, 0.5] typically
            # Sybil cliques have cc → 1.0
            if cc > 0.8 and degree > 2:
                structural_penalty = 0.3  # Heavy penalty for clique-like
            elif cc > 0.6 and degree > 2:
                structural_penalty = 0.6
            else:
                structural_penalty = 1.0
            
            # Degree penalty: very high degree relative to graph = hub or sybil coordinator
            avg_degree = sum(self.graph.degree(n) for n in self.graph.nodes) / max(len(self.graph.nodes), 1)
            if degree > 3 * avg_degree:
                structural_penalty *= 0.5
            
            final_score = ppr_score * structural_penalty
            
            candidates.append({
                "node_id": node_id,
                "ppr_score": round(ppr_score, 6),
                "clustering_coeff": round(cc, 3),
                "degree": degree,
                "structural_penalty": round(structural_penalty, 2),
                "final_score": round(final_score, 6),
                "is_sybil": self.graph.nodes[node_id].is_sybil
            })
        
        # Sort by final score descending
        candidates.sort(key=lambda x: -x["final_score"])
        return candidates[:whitelist_size]
    
    def evaluate_whitelist(self, whitelist: list[dict]) -> dict:
        """Evaluate whitelist quality: how many sybils leaked in?"""
        total = len(whitelist)
        sybils = sum(1 for w in whitelist if w["is_sybil"])
        honest = total - sybils
        
        return {
            "whitelist_size": total,
            "honest_count": honest,
            "sybil_count": sybils,
            "precision": round(honest / max(total, 1), 3),
            "sybil_leak_rate": round(sybils / max(total, 1), 3)
        }


def build_test_graph() -> TrustGraph:
    """
    Build a graph with:
    - 20 honest nodes in 2 loose communities (power-law-ish)
    - 10 sybil nodes in a dense clique
    - 3 attack edges connecting sybils to honest region
    """
    g = TrustGraph()
    random.seed(42)
    
    # Community A: honest nodes h_a0..h_a9
    for i in range(10):
        g.add_node(f"h_a{i}", is_sybil=False)
    # Sparse internal connections (avg degree ~4)
    a_edges = [(0,1),(0,2),(1,2),(1,3),(2,4),(3,4),(3,5),(4,5),(5,6),(6,7),(7,8),(8,9),(6,9),(0,5)]
    for i, j in a_edges:
        g.add_edge(f"h_a{i}", f"h_a{j}")
    
    # Community B: honest nodes h_b0..h_b9
    for i in range(10):
        g.add_node(f"h_b{i}", is_sybil=False)
    b_edges = [(0,1),(0,3),(1,2),(2,3),(2,4),(3,5),(4,5),(4,6),(5,7),(6,7),(7,8),(8,9),(6,8),(1,4)]
    for i, j in b_edges:
        g.add_edge(f"h_b{i}", f"h_b{j}")
    
    # Inter-community bridges (loose coupling — Alvisi's key observation)
    g.add_edge("h_a3", "h_b0")
    g.add_edge("h_a7", "h_b5")
    
    # Sybil clique: s0..s9 (fully connected = dense)
    for i in range(10):
        g.add_node(f"s{i}", is_sybil=True)
    for i in range(10):
        for j in range(i + 1, 10):
            g.add_edge(f"s{i}", f"s{j}")
    
    # Attack edges (sparse — hard to create many in real systems)
    g.add_edge("s0", "h_a2")
    g.add_edge("s1", "h_a8")
    g.add_edge("s2", "h_b3")
    
    return g


def demo():
    g = build_test_graph()
    ranker = LocalWhitelistRanker(g)
    
    print("=" * 60)
    print("LOCAL WHITELIST RANKER — Alvisi et al (IEEE S&P 2013)")
    print("=" * 60)
    print(f"Graph: {len(g.nodes)} nodes (20 honest + 10 sybil)")
    print(f"Sybil structure: dense clique (cc→1.0)")
    print(f"Honest structure: 2 loose communities (cc~0.2-0.4)")
    print(f"Attack edges: 3")
    print()
    
    # Test from different ego positions
    test_egos = ["h_a0", "h_a3", "h_b5", "h_a8"]
    
    for ego in test_egos:
        print(f"{'='*60}")
        print(f"EGO: {ego} (whitelist size=10)")
        print(f"{'='*60}")
        
        whitelist = ranker.rank_for_ego(ego, whitelist_size=10)
        eval_result = ranker.evaluate_whitelist(whitelist)
        
        for w in whitelist:
            marker = "⚠ SYBIL" if w["is_sybil"] else "✓ honest"
            print(f"  {w['node_id']:8s} score={w['final_score']:.6f} "
                  f"ppr={w['ppr_score']:.6f} cc={w['clustering_coeff']:.3f} "
                  f"deg={w['degree']:2d} pen={w['structural_penalty']:.2f} [{marker}]")
        
        print(f"\n  Precision: {eval_result['precision']:.1%} "
              f"({eval_result['honest_count']} honest, {eval_result['sybil_count']} sybil)")
        print()
    
    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    all_precisions = []
    for ego in [f"h_a{i}" for i in range(10)] + [f"h_b{i}" for i in range(10)]:
        wl = ranker.rank_for_ego(ego, whitelist_size=10)
        ev = ranker.evaluate_whitelist(wl)
        all_precisions.append(ev["precision"])
    
    avg_precision = sum(all_precisions) / len(all_precisions)
    min_precision = min(all_precisions)
    max_precision = max(all_precisions)
    
    print(f"Avg precision across all honest egos: {avg_precision:.1%}")
    print(f"Min: {min_precision:.1%}, Max: {max_precision:.1%}")
    print()
    print("KEY INSIGHT (Alvisi 2013): Universal defense fails because")
    print("honest graph has communities. Local whitelisting succeeds")
    print("because it only needs to rank YOUR neighborhood correctly.")
    print("Sybil dense cliques get penalized by structural features.")
    
    # Assert reasonable performance
    assert avg_precision >= 0.7, f"Avg precision too low: {avg_precision}"
    print(f"\n✓ ALL CHECKS PASSED (avg precision {avg_precision:.1%} >= 70%)")


if __name__ == "__main__":
    demo()
