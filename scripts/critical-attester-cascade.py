#!/usr/bin/env python3
"""
critical-attester-cascade.py — Find critical attesters whose compromise cascades.

Inspired by Liu & Zhao (PLOS ONE, Feb 2026): TEC-GNN framework for critical
node identification in infrastructure networks. Key finding: removing top 10%
of critical nodes reduces largest connected component to 0.4. At 20% removal,
network paralyzed. Redundancy coefficient β shows diminishing marginal returns.

ATF mapping: attesters are nodes, attestations are edges. Which attesters,
if compromised, cause the worst cascading trust failures? "Critical attester"
= one whose compromise invalidates downstream trust chains.

Metrics from the paper adapted for ATF:
1. Degree centrality → How many agents depend on this attester?
2. Betweenness centrality → How many trust paths flow through this attester?
3. Cascade impact → If this attester is compromised, how many downstream
   attestations become invalid (chain-of-trust collapse)?

The "precision reinforcement" strategy applies: redundancy (multiple independent
attesters) for critical nodes only. β optimization = targeted diversity.

Kit 🦊 — 2026-03-28
"""

import json
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class AttestationEdge:
    attester: str
    subject: str
    score: float
    action_class: str  # READ/WRITE/TRANSFER/ATTEST


@dataclass
class CascadeResult:
    compromised_node: str
    direct_invalidated: int      # Immediate dependents
    cascade_invalidated: int     # Total including transitive
    lcc_ratio: float            # Largest connected component ratio after removal
    affected_agents: list = field(default_factory=list)
    cascade_depth: int = 0


class CriticalAttesterAnalyzer:
    def __init__(self):
        self.edges: list[AttestationEdge] = []
        self.graph: dict[str, set[str]] = defaultdict(set)  # attester → subjects
        self.reverse: dict[str, set[str]] = defaultdict(set)  # subject → attesters
        self.all_nodes: set[str] = set()
    
    def add_edge(self, edge: AttestationEdge):
        self.edges.append(edge)
        self.graph[edge.attester].add(edge.subject)
        self.reverse[edge.subject].add(edge.attester)
        self.all_nodes.add(edge.attester)
        self.all_nodes.add(edge.subject)
    
    def degree_centrality(self) -> dict[str, float]:
        """Out-degree centrality: how many agents depend on this attester."""
        n = len(self.all_nodes)
        if n <= 1:
            return {node: 0 for node in self.all_nodes}
        return {node: len(self.graph.get(node, set())) / (n - 1) 
                for node in self.all_nodes}
    
    def betweenness_centrality(self) -> dict[str, float]:
        """
        Simplified betweenness: how many shortest trust paths flow through node.
        Full Brandes algorithm is O(VE); this is a simplified version for
        demonstration counting reachable pairs through each node.
        """
        betweenness = {node: 0.0 for node in self.all_nodes}
        
        for source in self.all_nodes:
            # BFS from source
            visited = {source}
            queue = [source]
            parents = defaultdict(list)
            
            while queue:
                current = queue.pop(0)
                for neighbor in self.graph.get(current, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
                        parents[neighbor].append(current)
            
            # Count paths through each intermediate node
            for target in visited:
                if target == source:
                    continue
                # Trace back through parents
                path_nodes = set()
                trace = [target]
                while trace:
                    node = trace.pop()
                    for parent in parents.get(node, []):
                        if parent != source:
                            path_nodes.add(parent)
                            trace.append(parent)
                
                for node in path_nodes:
                    betweenness[node] += 1.0
        
        # Normalize
        n = len(self.all_nodes)
        norm = max(1, (n - 1) * (n - 2))
        return {node: b / norm for node, b in betweenness.items()}
    
    def cascade_impact(self, compromised: str) -> CascadeResult:
        """
        Simulate cascading trust failure when an attester is compromised.
        
        Rules:
        1. All attestations FROM compromised node become invalid
        2. Subjects who lose their ONLY attester lose trust status
        3. Those subjects' own attestations may cascade (if they were sole attesters)
        4. Continue until stable
        """
        invalid_attesters = {compromised}
        affected = set()
        depth = 0
        
        while True:
            new_invalid = set()
            for node in invalid_attesters:
                for subject in self.graph.get(node, set()):
                    if subject in affected:
                        continue
                    # Check if subject has any REMAINING valid attesters
                    valid_attesters = self.reverse[subject] - invalid_attesters
                    if len(valid_attesters) == 0:
                        # Subject loses all trust — cascades
                        new_invalid.add(subject)
                        affected.add(subject)
            
            if not new_invalid:
                break
            
            invalid_attesters = invalid_attesters | new_invalid
            depth += 1
        
        # Calculate LCC ratio after removal
        remaining = self.all_nodes - invalid_attesters
        lcc_ratio = self._lcc_ratio(remaining)
        
        direct = len(self.graph.get(compromised, set()))
        
        return CascadeResult(
            compromised_node=compromised,
            direct_invalidated=direct,
            cascade_invalidated=len(affected),
            lcc_ratio=round(lcc_ratio, 3),
            affected_agents=sorted(affected),
            cascade_depth=depth
        )
    
    def _lcc_ratio(self, remaining_nodes: set) -> float:
        """Largest connected component ratio (undirected)."""
        if not remaining_nodes:
            return 0.0
        
        # Build undirected adjacency for remaining nodes
        adj = defaultdict(set)
        for edge in self.edges:
            if edge.attester in remaining_nodes and edge.subject in remaining_nodes:
                adj[edge.attester].add(edge.subject)
                adj[edge.subject].add(edge.attester)
        
        visited = set()
        max_component = 0
        
        for node in remaining_nodes:
            if node in visited:
                continue
            # BFS
            component = set()
            queue = [node]
            while queue:
                current = queue.pop(0)
                if current in component:
                    continue
                component.add(current)
                visited.add(current)
                for neighbor in adj.get(current, set()):
                    if neighbor not in component:
                        queue.append(neighbor)
            
            max_component = max(max_component, len(component))
        
        return max_component / len(self.all_nodes)
    
    def rank_critical_attesters(self) -> list[dict]:
        """
        Composite ranking using all three metrics.
        Weighted: cascade_impact 0.5, betweenness 0.3, degree 0.2
        (cascade is most important — it's what actually breaks things)
        """
        degree = self.degree_centrality()
        between = self.betweenness_centrality()
        
        cascades = {}
        for node in self.all_nodes:
            cascades[node] = self.cascade_impact(node)
        
        # Normalize cascade impact
        max_cascade = max(c.cascade_invalidated for c in cascades.values()) or 1
        
        rankings = []
        for node in self.all_nodes:
            c = cascades[node]
            composite = (
                0.5 * (c.cascade_invalidated / max_cascade) +
                0.3 * between[node] / max(between.values() or [1]) +
                0.2 * degree[node] / max(degree.values() or [1])
            )
            rankings.append({
                "node": node,
                "composite_score": round(composite, 4),
                "degree_centrality": round(degree[node], 4),
                "betweenness": round(between[node], 4),
                "cascade_invalidated": c.cascade_invalidated,
                "cascade_depth": c.cascade_depth,
                "lcc_ratio_after": c.lcc_ratio,
                "recommendation": self._recommend(c, degree[node])
            })
        
        return sorted(rankings, key=lambda x: -x["composite_score"])
    
    def _recommend(self, cascade: CascadeResult, degree: float) -> str:
        """Precision reinforcement: targeted redundancy for critical nodes."""
        if cascade.cascade_invalidated >= 3 or cascade.lcc_ratio < 0.6:
            return "CRITICAL: Add 2+ independent attesters for all dependents. β reinforcement priority."
        elif cascade.cascade_invalidated >= 1 or degree > 0.3:
            return "HIGH: Add 1+ independent attester for dependents."
        else:
            return "LOW: Current redundancy sufficient."


def demo():
    analyzer = CriticalAttesterAnalyzer()
    
    # Build a realistic ATF network
    # Genesis seed → A, B (two trust roots)
    # A → C, D, E (A is a hub attester)
    # B → D, F (B also attests D — redundancy)
    # C → G, H (C chains from A)
    # D → I (D has two attesters: A and B — resilient)
    # E → J (single chain from A → E → J)
    
    edges = [
        ("genesis", "A", 0.9, "ATTEST"),
        ("genesis", "B", 0.85, "ATTEST"),
        ("A", "C", 0.8, "WRITE"),
        ("A", "D", 0.75, "WRITE"),
        ("A", "E", 0.7, "TRANSFER"),
        ("B", "D", 0.8, "WRITE"),  # Redundant attestation for D
        ("B", "F", 0.75, "READ"),
        ("C", "G", 0.7, "ATTEST"),
        ("C", "H", 0.65, "READ"),
        ("D", "I", 0.7, "WRITE"),
        ("E", "J", 0.6, "TRANSFER"),
    ]
    
    for attester, subject, score, action in edges:
        analyzer.add_edge(AttestationEdge(attester, subject, score, action))
    
    print("=" * 65)
    print("CRITICAL ATTESTER CASCADE ANALYSIS")
    print("=" * 65)
    print(f"Network: {len(analyzer.all_nodes)} nodes, {len(edges)} attestation edges")
    print()
    
    # Show individual cascade scenarios
    print("--- Individual Cascade Scenarios ---")
    for node in ["A", "B", "genesis", "C", "D"]:
        result = analyzer.cascade_impact(node)
        print(f"\nCompromise {node}:")
        print(f"  Direct dependents: {result.direct_invalidated}")
        print(f"  Cascade invalidated: {result.cascade_invalidated}")
        print(f"  Cascade depth: {result.cascade_depth}")
        print(f"  LCC ratio after: {result.lcc_ratio}")
        if result.affected_agents:
            print(f"  Affected: {result.affected_agents}")
    
    # Full ranking
    print("\n" + "=" * 65)
    print("CRITICAL ATTESTER RANKING (composite score)")
    print("=" * 65)
    rankings = analyzer.rank_critical_attesters()
    
    for i, r in enumerate(rankings[:6]):
        print(f"\n#{i+1}: {r['node']} (score: {r['composite_score']})")
        print(f"  Degree: {r['degree_centrality']}, Betweenness: {r['betweenness']}")
        print(f"  Cascade: {r['cascade_invalidated']} nodes, depth {r['cascade_depth']}")
        print(f"  LCC after removal: {r['lcc_ratio_after']}")
        print(f"  → {r['recommendation']}")
    
    # Key insight
    print("\n" + "=" * 65)
    print("KEY INSIGHTS")
    print("=" * 65)
    print("1. A is the most critical attester (hub with longest cascade chains)")
    print("2. D survives A's compromise because B also attests D (redundancy works)")
    print("3. genesis compromise = total network failure (single root of trust)")
    print("4. Precision reinforcement: add redundancy ONLY for critical attesters'")
    print("   dependents. β optimization (Liu & Zhao 2026): diminishing returns")
    print("   after β=0.5, so target the top 10-20% critical nodes.")
    
    # Verify key assertions
    a_cascade = analyzer.cascade_impact("A")
    b_cascade = analyzer.cascade_impact("B")
    genesis_cascade = analyzer.cascade_impact("genesis")
    
    # A should cascade more than B (A is bigger hub)
    assert a_cascade.cascade_invalidated > b_cascade.cascade_invalidated, \
        f"A ({a_cascade.cascade_invalidated}) should cascade more than B ({b_cascade.cascade_invalidated})"
    
    # D should NOT be in A's cascade (B also attests D)
    assert "D" not in a_cascade.affected_agents, \
        "D should survive A's compromise (redundant attestation from B)"
    
    # Genesis should cascade everything
    assert genesis_cascade.cascade_invalidated >= 8, \
        f"Genesis should cascade most nodes (got {genesis_cascade.cascade_invalidated})"
    
    print("\nALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
