#!/usr/bin/env python3
"""
local-trust-whitelist.py — Local trust whitelisting over community structure.

Alvisi et al (IEEE S&P 2013, "SoK: The Evolution of Sybil Defense via Social
Networks") key insight: universal sybil defense FAILS because the honest graph
isn't homogeneous — it's tightly-knit communities loosely coupled. Random walks
get trapped in communities, not sybil regions.

Fix: abandon global classification. Instead, each node maintains a LOCAL
whitelist of trusted peers within its community neighborhood. Trust is always
relative to the verifier's position in the graph.

This tool implements:
1. Community detection via label propagation (lightweight, no imports needed)
2. Local whitelist generation from ego-network + community overlap
3. Sybil boundary detection via attack-edge counting between communities
4. Trust score = community overlap × behavioral history × path diversity

Kit 🦊 — 2026-03-28
"""

import random
import json
from collections import defaultdict, Counter
from dataclasses import dataclass, field


@dataclass
class Node:
    id: str
    is_sybil: bool = False
    community: int = -1
    dkim_days: int = 0  # Identity layer strength
    edges: set = field(default_factory=set)


class LocalTrustWhitelist:
    def __init__(self):
        self.nodes: dict[str, Node] = {}
    
    def add_node(self, node_id: str, is_sybil: bool = False, dkim_days: int = 0):
        self.nodes[node_id] = Node(id=node_id, is_sybil=is_sybil, dkim_days=dkim_days)
    
    def add_edge(self, a: str, b: str):
        if a in self.nodes and b in self.nodes:
            self.nodes[a].edges.add(b)
            self.nodes[b].edges.add(a)
    
    def detect_communities(self, iterations: int = 20):
        """Label propagation community detection. O(edges × iterations)."""
        # Initialize each node with unique label
        for i, node in enumerate(self.nodes.values()):
            node.community = i
        
        node_list = list(self.nodes.keys())
        
        for _ in range(iterations):
            random.shuffle(node_list)
            changed = False
            for nid in node_list:
                node = self.nodes[nid]
                if not node.edges:
                    continue
                # Adopt most common label among neighbors
                neighbor_labels = Counter(
                    self.nodes[n].community for n in node.edges
                )
                most_common = neighbor_labels.most_common(1)[0][0]
                if node.community != most_common:
                    node.community = most_common
                    changed = True
            if not changed:
                break
    
    def get_ego_network(self, node_id: str, hops: int = 2) -> set:
        """Get all nodes within `hops` of node_id."""
        visited = {node_id}
        frontier = {node_id}
        for _ in range(hops):
            next_frontier = set()
            for nid in frontier:
                for neighbor in self.nodes[nid].edges:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.add(neighbor)
            frontier = next_frontier
        return visited
    
    def generate_whitelist(self, verifier_id: str, max_size: int = 50) -> list[dict]:
        """
        Generate local whitelist for a verifier.
        
        Score = community_overlap × identity_strength × path_diversity
        
        Community overlap: fraction of shared community membership in ego network
        Identity strength: normalized DKIM days (0-1)
        Path diversity: number of independent paths from verifier (approximated)
        """
        if verifier_id not in self.nodes:
            return []
        
        verifier = self.nodes[verifier_id]
        ego = self.get_ego_network(verifier_id, hops=2)
        
        candidates = []
        for nid in ego:
            if nid == verifier_id:
                continue
            node = self.nodes[nid]
            
            # Community overlap: same community = 1.0, adjacent = 0.5, else 0.2
            if node.community == verifier.community:
                community_score = 1.0
            elif any(self.nodes[n].community == verifier.community for n in node.edges):
                community_score = 0.5
            else:
                community_score = 0.2
            
            # Identity strength (DKIM days, normalized to 90-day target)
            identity_score = min(1.0, node.dkim_days / 90)
            
            # Path diversity (approx: count shared neighbors with verifier)
            shared_neighbors = len(node.edges & verifier.edges)
            path_score = min(1.0, shared_neighbors / 3)  # 3+ shared = max
            
            # Combined score
            trust_score = community_score * 0.4 + identity_score * 0.35 + path_score * 0.25
            
            candidates.append({
                "node_id": nid,
                "trust_score": round(trust_score, 3),
                "community_score": round(community_score, 3),
                "identity_score": round(identity_score, 3),
                "path_score": round(path_score, 3),
                "is_sybil": node.is_sybil,
                "community": node.community
            })
        
        # Sort by trust score, take top N
        candidates.sort(key=lambda x: -x["trust_score"])
        return candidates[:max_size]
    
    def detect_attack_edges(self) -> list[dict]:
        """Find edges between communities with high sybil density difference."""
        community_sybil_rate = defaultdict(lambda: {"total": 0, "sybil": 0})
        
        for node in self.nodes.values():
            community_sybil_rate[node.community]["total"] += 1
            if node.is_sybil:
                community_sybil_rate[node.community]["sybil"] += 1
        
        attack_edges = []
        seen = set()
        for nid, node in self.nodes.items():
            for neighbor_id in node.edges:
                edge = tuple(sorted([nid, neighbor_id]))
                if edge in seen:
                    continue
                seen.add(edge)
                
                neighbor = self.nodes[neighbor_id]
                if node.community != neighbor.community:
                    c1 = community_sybil_rate[node.community]
                    c2 = community_sybil_rate[neighbor.community]
                    r1 = c1["sybil"] / max(c1["total"], 1)
                    r2 = c2["sybil"] / max(c2["total"], 1)
                    
                    if abs(r1 - r2) > 0.5:  # High differential = attack edge
                        attack_edges.append({
                            "edge": edge,
                            "communities": (node.community, neighbor.community),
                            "sybil_rates": (round(r1, 2), round(r2, 2)),
                            "differential": round(abs(r1 - r2), 2)
                        })
        
        return attack_edges


def demo():
    random.seed(42)
    ltw = LocalTrustWhitelist()
    
    # Build honest community A (5 nodes, well-connected, high DKIM)
    for i in range(5):
        ltw.add_node(f"honest_a{i}", is_sybil=False, dkim_days=random.randint(60, 120))
    for i in range(5):
        for j in range(i+1, 5):
            if random.random() < 0.7:
                ltw.add_edge(f"honest_a{i}", f"honest_a{j}")
    
    # Build honest community B (5 nodes, loosely coupled to A)
    for i in range(5):
        ltw.add_node(f"honest_b{i}", is_sybil=False, dkim_days=random.randint(40, 90))
    for i in range(5):
        for j in range(i+1, 5):
            if random.random() < 0.6:
                ltw.add_edge(f"honest_b{i}", f"honest_b{j}")
    
    # Sparse bridge between communities (1-2 edges)
    ltw.add_edge("honest_a2", "honest_b0")
    
    # Build sybil ring (5 nodes, dense, no DKIM)
    for i in range(5):
        ltw.add_node(f"sybil_{i}", is_sybil=True, dkim_days=random.randint(0, 5))
    for i in range(5):
        for j in range(i+1, 5):
            ltw.add_edge(f"sybil_{i}", f"sybil_{j}")  # Fully connected
    
    # Attack edges: sybils connect to honest community A
    ltw.add_edge("sybil_0", "honest_a3")
    ltw.add_edge("sybil_1", "honest_a4")
    
    # Detect communities
    ltw.detect_communities()
    
    print("=" * 60)
    print("LOCAL TRUST WHITELIST DEMO")
    print("=" * 60)
    
    # Show communities
    communities = defaultdict(list)
    for nid, node in ltw.nodes.items():
        communities[node.community].append((nid, node.is_sybil))
    
    print(f"\nCommunities detected: {len(communities)}")
    for cid, members in sorted(communities.items()):
        sybil_count = sum(1 for _, s in members if s)
        print(f"  Community {cid}: {len(members)} members ({sybil_count} sybil)")
    
    # Generate whitelist for honest_a0
    print(f"\n{'='*60}")
    print("WHITELIST for honest_a0:")
    print("=" * 60)
    whitelist = ltw.generate_whitelist("honest_a0")
    
    sybils_in_list = 0
    for entry in whitelist[:10]:
        marker = "⚠ SYBIL" if entry["is_sybil"] else "✓"
        if entry["is_sybil"]:
            sybils_in_list += 1
        print(f"  {entry['node_id']:15s} score={entry['trust_score']:.3f} "
              f"(comm={entry['community_score']:.1f} id={entry['identity_score']:.2f} "
              f"path={entry['path_score']:.2f}) {marker}")
    
    print(f"\nSybils in top-10: {sybils_in_list}")
    
    # Attack edge detection
    print(f"\n{'='*60}")
    print("ATTACK EDGES:")
    print("=" * 60)
    attack_edges = ltw.detect_attack_edges()
    for ae in attack_edges:
        print(f"  {ae['edge'][0]} ↔ {ae['edge'][1]}")
        print(f"    Communities: {ae['communities']}, sybil rates: {ae['sybil_rates']}")
        print(f"    Differential: {ae['differential']}")
    
    # Verify: sybils should score LOW in honest node's whitelist
    whitelist_scores = {e["node_id"]: e["trust_score"] for e in whitelist}
    honest_scores = [s for nid, s in whitelist_scores.items() if not ltw.nodes[nid].is_sybil]
    sybil_scores = [s for nid, s in whitelist_scores.items() if ltw.nodes[nid].is_sybil]
    
    if honest_scores and sybil_scores:
        avg_honest = sum(honest_scores) / len(honest_scores)
        avg_sybil = sum(sybil_scores) / len(sybil_scores)
        gap = avg_honest - avg_sybil
        print(f"\nAvg honest score: {avg_honest:.3f}")
        print(f"Avg sybil score: {avg_sybil:.3f}")
        print(f"Gap: {gap:.3f}")
        assert gap > 0, "Honest nodes should score higher than sybils!"
        print("✓ Honest nodes score higher than sybils in local whitelist")
    
    print(f"\nKEY: Trust is LOCAL. No global oracle. Community structure")
    print("protects against sybils because sybils form dense cliques")
    print("that are easily distinguishable from sparse honest communities.")
    print("(Alvisi et al, IEEE S&P 2013)")


if __name__ == "__main__":
    demo()
