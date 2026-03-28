#!/usr/bin/env python3
"""
precision-reinforcement.py — Targeted redundancy allocation for ATF networks.

Insight from TEC-GNN (Liu & Zhao, PLOS ONE Feb 2026): removing top 10%
critical nodes drops LCC to 0.4. But redundancy (β) has DIMINISHING
MARGINAL RETURNS — R rises fast β=[0, 0.5], then plateaus. So: reinforce
critical nodes ONLY, not blanket hardening.

Maps to ATF:
- Critical attesters = high betweenness centrality + entropy
- Redundancy = backup attestation paths (witness pools)
- Precision reinforcement: add witness coverage to top-K critical attesters
  rather than hardening every node equally

Usage: Analyzes an attestation graph, identifies critical attesters,
recommends minimum redundancy allocation to maintain connectivity
under targeted attack.

Kit 🦊 — 2026-03-28
"""

import json
import random
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class AttestationEdge:
    attester: str
    subject: str
    score: float
    ttl_remaining: int  # seconds


@dataclass
class ATFNetwork:
    edges: list[AttestationEdge] = field(default_factory=list)
    
    def adjacency(self) -> dict[str, list[str]]:
        adj = defaultdict(list)
        for e in self.edges:
            adj[e.attester].append(e.subject)
        return dict(adj)
    
    def all_nodes(self) -> set[str]:
        nodes = set()
        for e in self.edges:
            nodes.add(e.attester)
            nodes.add(e.subject)
        return nodes
    
    def betweenness_centrality(self) -> dict[str, float]:
        """Simplified betweenness: fraction of shortest paths through each node."""
        nodes = list(self.all_nodes())
        adj = self.adjacency()
        centrality = {n: 0.0 for n in nodes}
        
        for source in nodes:
            # BFS from source
            visited = {source}
            queue = [source]
            parents = defaultdict(list)
            depth = {source: 0}
            
            while queue:
                current = queue.pop(0)
                for neighbor in adj.get(current, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
                        depth[neighbor] = depth[current] + 1
                        parents[neighbor].append(current)
                    elif depth.get(neighbor, -1) == depth[current] + 1:
                        parents[neighbor].append(current)
            
            # Count paths through each intermediate node
            for target in nodes:
                if target == source or target not in parents:
                    continue
                # Trace back paths
                path_nodes = set()
                trace = [target]
                while trace:
                    node = trace.pop()
                    for p in parents.get(node, []):
                        if p != source:
                            path_nodes.add(p)
                            trace.append(p)
                
                for n in path_nodes:
                    centrality[n] += 1.0
        
        # Normalize
        n = len(nodes)
        if n > 2:
            norm = 1.0 / ((n - 1) * (n - 2))
            centrality = {k: v * norm for k, v in centrality.items()}
        
        return centrality
    
    def entropy_score(self) -> dict[str, float]:
        """Node entropy: diversity of connections (in-degree + out-degree variety)."""
        import math
        nodes = self.all_nodes()
        in_degree = defaultdict(int)
        out_degree = defaultdict(int)
        
        for e in self.edges:
            out_degree[e.attester] += 1
            in_degree[e.subject] += 1
        
        entropy = {}
        total_edges = len(self.edges) or 1
        for n in nodes:
            # Normalized entropy based on connection pattern
            in_d = in_degree.get(n, 0)
            out_d = out_degree.get(n, 0)
            total = in_d + out_d
            if total == 0:
                entropy[n] = 0.0
                continue
            probs = [in_d / total, out_d / total] if total > 0 else [1.0]
            probs = [p for p in probs if p > 0]
            ent = -sum(p * math.log2(p) for p in probs)
            entropy[n] = ent * (total / total_edges)
        
        return entropy
    
    def critical_nodes(self, top_k: int = 3) -> list[dict]:
        """Identify top-K critical nodes using combined betweenness + entropy."""
        bc = self.betweenness_centrality()
        ent = self.entropy_score()
        
        # Combined score (weighted: 60% betweenness, 40% entropy)
        # Following TEC-GNN's feature combination approach
        combined = {}
        for n in self.all_nodes():
            combined[n] = 0.6 * bc.get(n, 0) + 0.4 * ent.get(n, 0)
        
        ranked = sorted(combined.items(), key=lambda x: -x[1])
        return [{"node": n, "criticality": round(s, 4), 
                 "betweenness": round(bc.get(n, 0), 4),
                 "entropy": round(ent.get(n, 0), 4)} 
                for n, s in ranked[:top_k]]
    
    def lcc_after_removal(self, removed: set[str]) -> float:
        """Largest connected component ratio after removing nodes."""
        remaining = self.all_nodes() - removed
        if not remaining:
            return 0.0
        
        adj = self.adjacency()
        # BFS to find connected components (treating as undirected)
        undirected = defaultdict(set)
        for e in self.edges:
            if e.attester not in removed and e.subject not in removed:
                undirected[e.attester].add(e.subject)
                undirected[e.subject].add(e.attester)
        
        visited = set()
        max_component = 0
        
        for start in remaining:
            if start in visited:
                continue
            component = set()
            queue = [start]
            while queue:
                node = queue.pop(0)
                if node in visited:
                    continue
                visited.add(node)
                component.add(node)
                for neighbor in undirected.get(node, set()):
                    if neighbor not in visited:
                        queue.append(neighbor)
            max_component = max(max_component, len(component))
        
        return max_component / len(self.all_nodes())
    
    def recommend_redundancy(self, budget: int = 3) -> dict:
        """
        Precision reinforcement: recommend which nodes need backup attesters.
        
        TEC-GNN finding: β has diminishing returns after 0.5.
        So allocate β=0.5 redundancy to critical nodes, not β=1.0 to all.
        """
        critical = self.critical_nodes(top_k=budget)
        
        # Simulate attack: remove critical nodes
        critical_set = {c["node"] for c in critical}
        lcc_before = self.lcc_after_removal(set())
        lcc_after_attack = self.lcc_after_removal(critical_set)
        
        # Simulate random removal of same count
        random_removed = set(random.sample(list(self.all_nodes()), min(len(critical), len(self.all_nodes()))))
        lcc_random = self.lcc_after_removal(random_removed)
        
        return {
            "critical_nodes": critical,
            "lcc_baseline": round(lcc_before, 3),
            "lcc_after_targeted_attack": round(lcc_after_attack, 3),
            "lcc_after_random_attack": round(lcc_random, 3),
            "targeted_vs_random_damage": round(lcc_random - lcc_after_attack, 3),
            "recommendation": f"Add backup attestation paths for {[c['node'] for c in critical]}. "
                            f"β=0.5 redundancy (1 witness each) sufficient — diminishing returns above 0.5 "
                            f"(Liu & Zhao, PLOS ONE 2026).",
            "cost": f"{budget} witness attestations (vs {len(self.all_nodes())} for blanket hardening)"
        }


def demo():
    random.seed(42)
    
    # Build a realistic ATF network
    net = ATFNetwork()
    
    # Hub-and-spoke: genesis attests early adopters
    for agent in ["alice", "bob", "carol"]:
        net.edges.append(AttestationEdge("genesis", agent, 0.9, 86400))
    
    # Chain: alice → dave → eve → frank
    net.edges.append(AttestationEdge("alice", "dave", 0.8, 72000))
    net.edges.append(AttestationEdge("dave", "eve", 0.75, 60000))
    net.edges.append(AttestationEdge("eve", "frank", 0.7, 48000))
    
    # Cross-links
    net.edges.append(AttestationEdge("bob", "dave", 0.7, 50000))
    net.edges.append(AttestationEdge("carol", "eve", 0.65, 40000))
    net.edges.append(AttestationEdge("frank", "grace", 0.6, 30000))
    net.edges.append(AttestationEdge("bob", "grace", 0.55, 25000))
    
    # Sybil cluster (internal only)
    for s1, s2 in [("sybil1", "sybil2"), ("sybil2", "sybil3"), ("sybil3", "sybil1")]:
        net.edges.append(AttestationEdge(s1, s2, 0.95, 3600))
    # Sybils try to connect to honest network
    net.edges.append(AttestationEdge("sybil1", "frank", 0.4, 1800))
    
    print("=" * 60)
    print("PRECISION REINFORCEMENT ANALYSIS")
    print(f"Network: {len(net.all_nodes())} nodes, {len(net.edges)} edges")
    print("=" * 60)
    print()
    
    # Identify critical nodes
    critical = net.critical_nodes(top_k=5)
    print("TOP 5 CRITICAL NODES:")
    for c in critical:
        print(f"  {c['node']}: criticality={c['criticality']}, "
              f"betweenness={c['betweenness']}, entropy={c['entropy']}")
    print()
    
    # Recommend redundancy
    rec = net.recommend_redundancy(budget=3)
    print("ATTACK SIMULATION:")
    print(f"  LCC baseline: {rec['lcc_baseline']}")
    print(f"  LCC after targeted attack (top 3): {rec['lcc_after_targeted_attack']}")
    print(f"  LCC after random attack (3 nodes): {rec['lcc_after_random_attack']}")
    print(f"  Targeted vs random damage: {rec['targeted_vs_random_damage']}")
    print()
    print(f"RECOMMENDATION: {rec['recommendation']}")
    print(f"COST: {rec['cost']}")
    print()
    
    # Verify targeted > random damage
    assert rec["lcc_after_targeted_attack"] <= rec["lcc_after_random_attack"], \
        "Targeted attack should cause more damage than random"
    
    # Verify critical nodes found
    assert len(critical) == 5
    assert all(c["criticality"] >= 0 for c in critical)
    
    print("ALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
