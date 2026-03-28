#!/usr/bin/env python3
"""
attack-edge-analyzer.py — Detect sybil regions via attack edge analysis.

Implements the core insight from Alvisi et al (IEEE S&P 2013, SoK: The
Evolution of Sybil Defense via Social Networks):

1. Honest regions are NOT homogeneous — they're tightly-knit communities
   loosely coupled to each other.
2. Sybil regions are densely self-connected (mutual inflation is cheap).
3. Attack edges (between honest and sybil regions) are the bottleneck.
4. Sybil defense = community detection + attack edge counting.

The paper's key contribution: universal sybil defense (classify ALL nodes)
is too ambitious. Practical goal: securely white-list a LOCAL region.
Random walks from a trusted seed stay in the honest community because
attack edges are few.

Also implements resistance model from AAMAS 2025 (Dehkordi & Zehmakan):
node resistance to sybil friendship requests determines attack edge count.
Identity layer thickness (DKIM chain duration) = resistance proxy.

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Node:
    id: str
    is_sybil: bool = False
    community: str = "default"
    identity_days: int = 0  # DKIM chain days = resistance proxy
    trust_score: float = 0.0
    
    @property
    def resistance(self) -> float:
        """Resistance to sybil friendship requests. Higher = harder to trick."""
        # Identity layer thickness determines resistance
        # 0 days = 0.1 resistance (easy target)
        # 90+ days = 0.9 resistance (hard target)
        return min(0.9, 0.1 + (self.identity_days / 100))


@dataclass
class Edge:
    source: str
    target: str
    weight: float = 1.0
    is_attack_edge: bool = False  # Crosses honest/sybil boundary


class AttackEdgeAnalyzer:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.adj: dict[str, list[str]] = defaultdict(list)
    
    def add_node(self, node: Node):
        self.nodes[node.id] = node
    
    def add_edge(self, source: str, target: str, weight: float = 1.0):
        s = self.nodes.get(source)
        t = self.nodes.get(target)
        if not s or not t:
            return
        
        is_attack = s.is_sybil != t.is_sybil
        self.edges.append(Edge(source, target, weight, is_attack))
        self.adj[source].append(target)
        self.adj[target].append(source)
    
    def random_walk_whitelist(self, seed: str, walk_length: int = 10, 
                              num_walks: int = 100) -> dict[str, float]:
        """
        SybilGuard-style random walk from trusted seed.
        
        Alvisi et al: random walks from honest seed stay in honest region
        because attack edges are few. Visit frequency = trust proxy.
        """
        visit_count: dict[str, int] = defaultdict(int)
        
        for _ in range(num_walks):
            current = seed
            for _ in range(walk_length):
                neighbors = self.adj.get(current, [])
                if not neighbors:
                    break
                current = random.choice(neighbors)
                visit_count[current] += 1
        
        total = sum(visit_count.values()) or 1
        return {nid: count / total for nid, count in visit_count.items()}
    
    def compute_community_density(self) -> dict[str, dict]:
        """
        Compute internal density per community.
        
        Honest communities: sparse but connected (trust is hard to earn).
        Sybil clusters: dense (mutual inflation is free).
        """
        communities: dict[str, list[str]] = defaultdict(list)
        for nid, node in self.nodes.items():
            communities[node.community].append(nid)
        
        results = {}
        for comm, members in communities.items():
            member_set = set(members)
            n = len(members)
            if n < 2:
                results[comm] = {"size": n, "density": 0.0, "internal_edges": 0}
                continue
            
            internal = sum(1 for e in self.edges 
                          if e.source in member_set and e.target in member_set)
            max_edges = n * (n - 1) / 2
            density = internal / max_edges if max_edges > 0 else 0
            
            is_sybil = any(self.nodes[m].is_sybil for m in members)
            results[comm] = {
                "size": n,
                "density": round(density, 4),
                "internal_edges": internal,
                "is_sybil": is_sybil,
                "avg_identity_days": round(sum(self.nodes[m].identity_days for m in members) / n, 1)
            }
        
        return results
    
    def count_attack_edges(self) -> dict:
        """Count and characterize attack edges."""
        attack = [e for e in self.edges if e.is_attack_edge]
        honest_to_sybil = sum(1 for e in attack 
                             if not self.nodes[e.source].is_sybil)
        sybil_to_honest = len(attack) - honest_to_sybil
        
        return {
            "total_edges": len(self.edges),
            "attack_edges": len(attack),
            "attack_ratio": round(len(attack) / max(len(self.edges), 1), 4),
            "honest_initiated": honest_to_sybil,
            "sybil_initiated": sybil_to_honest
        }
    
    def resistance_simulation(self, sybil_requests: int = 50) -> dict:
        """
        AAMAS 2025 model: sybils send friendship requests.
        Resistant nodes (thick identity layer) reject them.
        """
        honest_nodes = [n for n in self.nodes.values() if not n.is_sybil]
        
        accepted = 0
        rejected = 0
        for _ in range(sybil_requests):
            target = random.choice(honest_nodes)
            # Accept with probability (1 - resistance)
            if random.random() > target.resistance:
                accepted += 1
            else:
                rejected += 1
        
        return {
            "sybil_requests": sybil_requests,
            "accepted": accepted,
            "rejected": rejected,
            "accept_rate": round(accepted / max(sybil_requests, 1), 3),
            "avg_honest_resistance": round(
                sum(n.resistance for n in honest_nodes) / max(len(honest_nodes), 1), 3
            )
        }
    
    def full_analysis(self, seed: str) -> dict:
        communities = self.compute_community_density()
        attack = self.count_attack_edges()
        whitelist = self.random_walk_whitelist(seed)
        resistance = self.resistance_simulation()
        
        # Whitelist accuracy: how many sybils got whitelisted?
        threshold = 0.01  # Visit frequency threshold
        whitelisted = {nid for nid, freq in whitelist.items() if freq >= threshold}
        sybils_whitelisted = sum(1 for nid in whitelisted if self.nodes[nid].is_sybil)
        honest_whitelisted = len(whitelisted) - sybils_whitelisted
        
        return {
            "communities": communities,
            "attack_edges": attack,
            "resistance": resistance,
            "whitelist": {
                "seed": seed,
                "whitelisted_count": len(whitelisted),
                "honest_whitelisted": honest_whitelisted,
                "sybils_whitelisted": sybils_whitelisted,
                "precision": round(
                    honest_whitelisted / max(len(whitelisted), 1), 3
                )
            },
            "methodology": (
                "Alvisi et al (IEEE S&P 2013): sybil defense via community structure. "
                "Honest regions = sparse communities. Sybil regions = dense clusters. "
                "Random walks from trusted seeds stay honest. "
                "Dehkordi & Zehmakan (AAMAS 2025): resistance to attack requests "
                "= identity layer thickness."
            )
        }


def build_test_network() -> AttackEdgeAnalyzer:
    """Build a test network with honest communities and sybil cluster."""
    analyzer = AttackEdgeAnalyzer()
    random.seed(42)
    
    # Honest community A (established agents)
    for i in range(15):
        analyzer.add_node(Node(
            id=f"honest_a_{i}", community="community_a",
            identity_days=random.randint(30, 120),
            trust_score=random.uniform(0.5, 0.9)
        ))
    
    # Honest community B (newer agents)
    for i in range(10):
        analyzer.add_node(Node(
            id=f"honest_b_{i}", community="community_b",
            identity_days=random.randint(5, 45),
            trust_score=random.uniform(0.3, 0.7)
        ))
    
    # Sybil cluster
    for i in range(12):
        analyzer.add_node(Node(
            id=f"sybil_{i}", is_sybil=True, community="sybil_ring",
            identity_days=random.randint(0, 3),  # Minimal history
            trust_score=random.uniform(0.7, 0.95)  # Inflated scores
        ))
    
    # Honest community A: sparse internal connections (trust is hard)
    for i in range(15):
        for j in range(i + 1, 15):
            if random.random() < 0.25:  # Sparse
                analyzer.add_edge(f"honest_a_{i}", f"honest_a_{j}")
    
    # Honest community B: sparse internal
    for i in range(10):
        for j in range(i + 1, 10):
            if random.random() < 0.2:
                analyzer.add_edge(f"honest_b_{i}", f"honest_b_{j}")
    
    # Cross-community honest links (loose coupling)
    for i in range(15):
        for j in range(10):
            if random.random() < 0.05:  # Very sparse
                analyzer.add_edge(f"honest_a_{i}", f"honest_b_{j}")
    
    # Sybil cluster: dense internal connections (mutual inflation is free)
    for i in range(12):
        for j in range(i + 1, 12):
            if random.random() < 0.8:  # Dense!
                analyzer.add_edge(f"sybil_{i}", f"sybil_{j}")
    
    # Attack edges (few, targeting low-resistance nodes)
    for i in range(12):
        for j in range(10):
            target = analyzer.nodes[f"honest_b_{j}"]
            if random.random() < 0.03 * (1 - target.resistance):
                analyzer.add_edge(f"sybil_{i}", f"honest_b_{j}")
    
    return analyzer


def demo():
    analyzer = build_test_network()
    
    print("=" * 60)
    print("ATTACK EDGE ANALYSIS")
    print("Alvisi et al (IEEE S&P 2013) + Dehkordi (AAMAS 2025)")
    print("=" * 60)
    print()
    
    result = analyzer.full_analysis(seed="honest_a_0")
    
    print("COMMUNITY DENSITY:")
    for comm, stats in result["communities"].items():
        sybil_tag = " [SYBIL]" if stats.get("is_sybil") else ""
        print(f"  {comm}{sybil_tag}: {stats['size']} nodes, "
              f"density={stats['density']}, "
              f"avg_identity={stats['avg_identity_days']}d")
    
    print(f"\nATTACK EDGES:")
    ae = result["attack_edges"]
    print(f"  Total edges: {ae['total_edges']}")
    print(f"  Attack edges: {ae['attack_edges']} ({ae['attack_ratio']:.1%})")
    print(f"  Sybil-initiated: {ae['sybil_initiated']}")
    
    print(f"\nRESISTANCE (identity layer):")
    r = result["resistance"]
    print(f"  Sybil requests: {r['sybil_requests']}")
    print(f"  Accepted: {r['accepted']} ({r['accept_rate']:.1%})")
    print(f"  Avg honest resistance: {r['avg_honest_resistance']}")
    
    print(f"\nWHITELIST (random walk from honest_a_0):")
    w = result["whitelist"]
    print(f"  Whitelisted: {w['whitelisted_count']}")
    print(f"  Honest: {w['honest_whitelisted']}")
    print(f"  Sybils leaked: {w['sybils_whitelisted']}")
    print(f"  Precision: {w['precision']:.1%}")
    
    print()
    
    # Key assertions
    comm = result["communities"]
    assert comm["sybil_ring"]["density"] > comm["community_a"]["density"], \
        "Sybil density should exceed honest density"
    assert comm["sybil_ring"]["avg_identity_days"] < 5, \
        "Sybils should have minimal identity history"
    assert result["whitelist"]["precision"] >= 0.8, \
        "Random walk whitelist should be >80% precise"
    
    print("KEY ASSERTIONS PASSED:")
    print(f"  ✓ Sybil density ({comm['sybil_ring']['density']}) > "
          f"honest density ({comm['community_a']['density']})")
    print(f"  ✓ Sybil identity days ({comm['sybil_ring']['avg_identity_days']}) < 5")
    print(f"  ✓ Whitelist precision ({w['precision']}) >= 80%")
    print()
    print("INSIGHT: Dense subgraph + low identity days = sybil signal.")
    print("Random walks from trusted seeds naturally stay in honest communities.")
    print("Identity layer (DKIM chain) = resistance to attack edge creation.")


if __name__ == "__main__":
    demo()
