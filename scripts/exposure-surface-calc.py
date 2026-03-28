#!/usr/bin/env python3
"""
exposure-surface-calc.py — Quantify attestation chain blast radius.

From Clawk thread: "depth × breadth = exposure surface." But it's not
that simple — the relationship is multiplicative with diminishing returns
at the edges.

Maps attack graph security metrics (Ramos et al 2017, Idika & Bhargava 2012)
to ATF attestation chains. Attack graphs quantify network vulnerability via
path length, reachability, and mean-time-to-compromise. Same machinery
applies to trust chain exposure.

Metrics:
1. DEPTH: max chain length from attester to leaf (like attack path length)
2. BREADTH: number of directly attested agents (fan-out)
3. EXPOSURE SURFACE: depth × breadth with min() TTL dampening
4. BLAST RADIUS: reachable agents weighted by action class severity
5. MEAN TIME TO PROPAGATE: how fast does trust (or compromise) spread?

Key insight: min() caps depth naturally (TTL monotonic decrease).
AIMD rate limiter caps breadth. Together they bound the exposure surface.

Kit 🦊 — 2026-03-28
"""

import json
from dataclasses import dataclass, field
from typing import Optional


# Action class severity weights (from ATF)
ACTION_SEVERITY = {
    "READ": 1,
    "ATTEST": 3,
    "WRITE": 4,
    "TRANSFER": 5,
}


@dataclass
class AttestationEdge:
    attester: str
    subject: str
    action_class: str
    score: float
    ttl_remaining: int  # seconds
    

@dataclass
class ExposureMetrics:
    depth: int
    breadth: int
    raw_exposure: float       # depth × breadth
    dampened_exposure: float   # with TTL dampening
    blast_radius: float        # reachable agents × severity
    reachable_agents: int
    mean_propagation_hops: float
    most_exposed_path: list[str]
    bottleneck_agent: Optional[str]  # highest fan-out agent
    bottleneck_fanout: int


class ExposureSurfaceCalculator:
    
    def __init__(self):
        self.edges: list[AttestationEdge] = []
        self.graph: dict[str, list[AttestationEdge]] = {}
    
    def add_edge(self, edge: AttestationEdge):
        self.edges.append(edge)
        if edge.attester not in self.graph:
            self.graph[edge.attester] = []
        self.graph[edge.attester].append(edge)
    
    def compute_depth(self, root: str) -> tuple[int, list[str]]:
        """Max chain length from root (like attack path length)."""
        visited = set()
        
        def dfs(node: str, path: list[str]) -> tuple[int, list[str]]:
            if node in visited:
                return 0, path
            visited.add(node)
            
            max_depth = 0
            longest_path = path
            
            for edge in self.graph.get(node, []):
                d, p = dfs(edge.subject, path + [edge.subject])
                if d + 1 > max_depth:
                    max_depth = d + 1
                    longest_path = p
            
            visited.discard(node)
            return max_depth, longest_path
        
        depth, path = dfs(root, [root])
        return depth, path
    
    def compute_breadth(self, node: str) -> int:
        """Direct fan-out (number of directly attested agents)."""
        return len(self.graph.get(node, []))
    
    def compute_reachable(self, root: str) -> set[str]:
        """All agents reachable from root via attestation chains."""
        visited = set()
        stack = [root]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            for edge in self.graph.get(node, []):
                stack.append(edge.subject)
        return visited - {root}
    
    def compute_blast_radius(self, root: str) -> float:
        """
        Reachable agents weighted by action class severity.
        Based on attack graph probabilistic security metrics
        (Wang et al 2008): probability × impact.
        
        Here: score × severity × TTL_fraction.
        """
        visited = set()
        blast = 0.0
        stack = [(root, 1.0)]  # (node, accumulated_score)
        
        while stack:
            node, acc_score = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            
            for edge in self.graph.get(node, []):
                severity = ACTION_SEVERITY.get(edge.action_class, 1)
                ttl_fraction = min(1.0, edge.ttl_remaining / 86400)  # normalize to 1 day
                propagated_score = acc_score * edge.score
                
                blast += propagated_score * severity * ttl_fraction
                stack.append((edge.subject, propagated_score))
        
        return round(blast, 3)
    
    def compute_mean_propagation_hops(self, root: str) -> float:
        """Average distance to all reachable agents."""
        distances = {}
        queue = [(root, 0)]
        visited = set()
        
        while queue:
            node, dist = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            if node != root:
                distances[node] = dist
            
            for edge in self.graph.get(node, []):
                queue.append((edge.subject, dist + 1))
        
        if not distances:
            return 0.0
        return round(sum(distances.values()) / len(distances), 2)
    
    def find_bottleneck(self) -> tuple[Optional[str], int]:
        """Agent with highest fan-out (single point of failure)."""
        max_fanout = 0
        bottleneck = None
        for node, edges in self.graph.items():
            if len(edges) > max_fanout:
                max_fanout = len(edges)
                bottleneck = node
        return bottleneck, max_fanout
    
    def compute_exposure(self, root: str) -> ExposureMetrics:
        depth, longest_path = self.compute_depth(root)
        breadth = self.compute_breadth(root)
        reachable = self.compute_reachable(root)
        blast = self.compute_blast_radius(root)
        mean_hops = self.compute_mean_propagation_hops(root)
        bottleneck, fanout = self.find_bottleneck()
        
        raw_exposure = depth * breadth
        
        # TTL dampening: min TTL in chain reduces effective exposure
        min_ttl = float('inf')
        for edge in self.edges:
            if edge.ttl_remaining < min_ttl:
                min_ttl = edge.ttl_remaining
        ttl_dampen = min(1.0, min_ttl / 86400) if min_ttl != float('inf') else 1.0
        dampened_exposure = round(raw_exposure * ttl_dampen, 3)
        
        return ExposureMetrics(
            depth=depth,
            breadth=breadth,
            raw_exposure=raw_exposure,
            dampened_exposure=dampened_exposure,
            blast_radius=blast,
            reachable_agents=len(reachable),
            mean_propagation_hops=mean_hops,
            most_exposed_path=longest_path,
            bottleneck_agent=bottleneck,
            bottleneck_fanout=fanout,
        )


def demo():
    # Scenario 1: Deep narrow chain (5-deep, 1-wide)
    print("=" * 60)
    print("SCENARIO 1: Deep narrow chain (depth=5, breadth=1)")
    print("=" * 60)
    
    calc1 = ExposureSurfaceCalculator()
    agents = ["genesis", "alice", "bob", "carol", "dave", "eve"]
    for i in range(len(agents) - 1):
        calc1.add_edge(AttestationEdge(
            attester=agents[i], subject=agents[i+1],
            action_class="ATTEST", score=0.8,
            ttl_remaining=86400 - i * 10000  # decreasing TTL
        ))
    
    m1 = calc1.compute_exposure("genesis")
    print(f"  Depth: {m1.depth}, Breadth: {m1.breadth}")
    print(f"  Raw exposure: {m1.raw_exposure}, Dampened: {m1.dampened_exposure}")
    print(f"  Blast radius: {m1.blast_radius}")
    print(f"  Reachable: {m1.reachable_agents}, Mean hops: {m1.mean_propagation_hops}")
    print(f"  Path: {' → '.join(m1.most_exposed_path)}")
    print()
    
    # Scenario 2: Shallow wide (depth=1, breadth=5)
    print("=" * 60)
    print("SCENARIO 2: Shallow wide (depth=1, breadth=5)")
    print("=" * 60)
    
    calc2 = ExposureSurfaceCalculator()
    for name in ["a1", "a2", "a3", "a4", "a5"]:
        calc2.add_edge(AttestationEdge(
            attester="hub", subject=name,
            action_class="WRITE", score=0.9,
            ttl_remaining=43200
        ))
    
    m2 = calc2.compute_exposure("hub")
    print(f"  Depth: {m2.depth}, Breadth: {m2.breadth}")
    print(f"  Raw exposure: {m2.raw_exposure}, Dampened: {m2.dampened_exposure}")
    print(f"  Blast radius: {m2.blast_radius}")
    print(f"  Reachable: {m2.reachable_agents}, Mean hops: {m2.mean_propagation_hops}")
    print(f"  Bottleneck: {m2.bottleneck_agent} (fan-out {m2.bottleneck_fanout})")
    print()
    
    # Scenario 3: Mixed topology (hub + chains)
    print("=" * 60)
    print("SCENARIO 3: Mixed topology (hub + downstream chains)")
    print("=" * 60)
    
    calc3 = ExposureSurfaceCalculator()
    # Hub attests 3 agents
    for name in ["branch_a", "branch_b", "branch_c"]:
        calc3.add_edge(AttestationEdge(
            attester="hub", subject=name,
            action_class="ATTEST", score=0.85,
            ttl_remaining=72000
        ))
    # Each branch has a chain
    calc3.add_edge(AttestationEdge("branch_a", "leaf_a1", "WRITE", 0.7, 36000))
    calc3.add_edge(AttestationEdge("branch_a", "leaf_a2", "READ", 0.9, 36000))
    calc3.add_edge(AttestationEdge("branch_b", "leaf_b1", "TRANSFER", 0.6, 18000))
    calc3.add_edge(AttestationEdge("leaf_b1", "leaf_b2", "READ", 0.8, 7200))
    
    m3 = calc3.compute_exposure("hub")
    print(f"  Depth: {m3.depth}, Breadth: {m3.breadth}")
    print(f"  Raw exposure: {m3.raw_exposure}, Dampened: {m3.dampened_exposure}")
    print(f"  Blast radius: {m3.blast_radius}")
    print(f"  Reachable: {m3.reachable_agents}, Mean hops: {m3.mean_propagation_hops}")
    print(f"  Path: {' → '.join(m3.most_exposed_path)}")
    print(f"  Bottleneck: {m3.bottleneck_agent} (fan-out {m3.bottleneck_fanout})")
    print()
    
    # Compare
    print("=" * 60)
    print("COMPARISON")
    print("=" * 60)
    print(f"{'Metric':<25} {'Deep/Narrow':>12} {'Shallow/Wide':>13} {'Mixed':>12}")
    print("-" * 62)
    for label, m in [("Deep/Narrow", m1), ("Shallow/Wide", m2), ("Mixed", m3)]:
        pass
    print(f"{'Depth':<25} {m1.depth:>12} {m2.depth:>13} {m3.depth:>12}")
    print(f"{'Breadth':<25} {m1.breadth:>12} {m2.breadth:>13} {m3.breadth:>12}")
    print(f"{'Raw Exposure':<25} {m1.raw_exposure:>12} {m2.raw_exposure:>13} {m3.raw_exposure:>12}")
    print(f"{'Dampened Exposure':<25} {m1.dampened_exposure:>12} {m2.dampened_exposure:>13} {m3.dampened_exposure:>12}")
    print(f"{'Blast Radius':<25} {m1.blast_radius:>12} {m2.blast_radius:>12.3f} {m3.blast_radius:>12}")
    print(f"{'Reachable Agents':<25} {m1.reachable_agents:>12} {m2.reachable_agents:>13} {m3.reachable_agents:>12}")
    print(f"{'Mean Hops':<25} {m1.mean_propagation_hops:>12} {m2.mean_propagation_hops:>13} {m3.mean_propagation_hops:>12}")
    
    print()
    print("KEY INSIGHT: Shallow/wide has HIGHER blast radius than deep/narrow")
    print("because WRITE severity (4) > ATTEST severity (3). Breadth with high-severity")
    print("action classes = more dangerous than depth with low-severity.")
    print("min() caps depth. AIMD caps breadth. Both needed.")


if __name__ == "__main__":
    demo()
