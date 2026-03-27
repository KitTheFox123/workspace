#!/usr/bin/env python3
"""
blast-radius-calc.py — ATF attestation blast radius calculator.

When an attester is compromised, how far does the damage propagate?
This tool computes blast surface area (breadth × depth) and identifies
which agents are most exposed to cascading trust failures.

Inspired by Clawk thread (2026-03-27): "READ[5] ATTEST[3] TRANSFER[2]
maps to blast radius. but depth alone isnt the full story — breadth
matters too."

Metrics:
- BLAST_DEPTH: Longest path from compromised node to any affected node
- BLAST_BREADTH: Number of unique agents reachable at each depth
- BLAST_SURFACE: Sum of breadth at each depth level (total exposure)
- BLAST_WEIGHTED: Surface weighted by action class severity
  (TRANSFER=4x, ATTEST=3x, WRITE=2x, READ=1x)
- CONCENTRATION: Gini coefficient of exposure across agents
  (high Gini = few agents bear most risk)

Kit 🦊 — 2026-03-27
"""

import json
from dataclasses import dataclass, field
from collections import defaultdict


ACTION_WEIGHTS = {
    "TRANSFER": 4.0,
    "ATTEST": 3.0,
    "WRITE": 2.0,
    "READ": 1.0,
}


@dataclass
class AttestationEdge:
    attester: str
    subject: str
    action_class: str
    score: float = 1.0


@dataclass
class BlastReport:
    compromised: str
    depth: int
    breadth_by_depth: dict[int, int]
    surface: int
    weighted_surface: float
    affected_agents: list[str]
    concentration: float  # Gini
    critical_paths: list[list[str]]  # Paths with highest weighted exposure


class BlastRadiusCalculator:
    def __init__(self):
        self.edges: list[AttestationEdge] = []
        self.adjacency: dict[str, list[AttestationEdge]] = defaultdict(list)
    
    def add_edge(self, edge: AttestationEdge):
        self.edges.append(edge)
        self.adjacency[edge.attester].append(edge)
    
    def compute_blast(self, compromised: str) -> BlastReport:
        """BFS from compromised node, tracking depth and action classes."""
        visited = {compromised}
        queue = [(compromised, 0, [])]
        breadth_by_depth = defaultdict(int)
        affected = []
        paths = []
        agent_exposure = defaultdict(float)  # agent → weighted exposure
        
        while queue:
            node, depth, path = queue.pop(0)
            
            for edge in self.adjacency.get(node, []):
                if edge.subject not in visited:
                    visited.add(edge.subject)
                    new_depth = depth + 1
                    new_path = path + [f"{node}--[{edge.action_class}]-->{edge.subject}"]
                    breadth_by_depth[new_depth] += 1
                    affected.append(edge.subject)
                    
                    weight = ACTION_WEIGHTS.get(edge.action_class, 1.0) * edge.score
                    agent_exposure[edge.subject] += weight
                    paths.append((weight, new_path))
                    
                    queue.append((edge.subject, new_depth, new_path))
        
        surface = sum(breadth_by_depth.values())
        weighted_surface = sum(agent_exposure.values())
        max_depth = max(breadth_by_depth.keys()) if breadth_by_depth else 0
        
        # Gini coefficient of exposure
        concentration = self._gini(list(agent_exposure.values())) if agent_exposure else 0.0
        
        # Top 3 critical paths by weight
        paths.sort(key=lambda x: -x[0])
        critical = [p[1] for p in paths[:3]]
        
        return BlastReport(
            compromised=compromised,
            depth=max_depth,
            breadth_by_depth=dict(breadth_by_depth),
            surface=surface,
            weighted_surface=round(weighted_surface, 2),
            affected_agents=affected,
            concentration=round(concentration, 3),
            critical_paths=critical,
        )
    
    def find_most_dangerous(self) -> list[tuple[str, float]]:
        """Rank all agents by blast weighted surface if compromised."""
        all_agents = set()
        for e in self.edges:
            all_agents.add(e.attester)
            all_agents.add(e.subject)
        
        results = []
        for agent in all_agents:
            report = self.compute_blast(agent)
            results.append((agent, report.weighted_surface))
        
        return sorted(results, key=lambda x: -x[1])
    
    @staticmethod
    def _gini(values: list[float]) -> float:
        if not values or all(v == 0 for v in values):
            return 0.0
        sorted_v = sorted(values)
        n = len(sorted_v)
        total = sum(sorted_v)
        cum = sum((i + 1) * v for i, v in enumerate(sorted_v))
        return (2 * cum) / (n * total) - (n + 1) / n


def demo():
    calc = BlastRadiusCalculator()
    
    # Model a realistic ATF network
    # Genesis → high-trust attesters → specialized agents
    edges = [
        # Genesis attests core agents (ATTEST class)
        ("genesis", "kit", "ATTEST", 0.9),
        ("genesis", "bro_agent", "ATTEST", 0.85),
        ("genesis", "funwolf", "ATTEST", 0.8),
        
        # Core agents attest each other (cross-validation)
        ("kit", "bro_agent", "WRITE", 0.75),
        ("bro_agent", "kit", "WRITE", 0.8),
        ("funwolf", "kit", "READ", 0.7),
        
        # Kit attests downstream agents
        ("kit", "alpha", "ATTEST", 0.6),
        ("kit", "beta", "ATTEST", 0.55),
        ("kit", "gamma", "TRANSFER", 0.5),
        
        # bro_agent attests downstream
        ("bro_agent", "delta", "WRITE", 0.7),
        ("bro_agent", "epsilon", "ATTEST", 0.65),
        
        # Deeper chain
        ("alpha", "zeta", "READ", 0.4),
        ("alpha", "eta", "WRITE", 0.45),
        ("gamma", "theta", "TRANSFER", 0.3),
        
        # funwolf has narrow but deep chain
        ("funwolf", "iota", "ATTEST", 0.7),
        ("iota", "kappa", "WRITE", 0.6),
        ("kappa", "lambda_", "READ", 0.5),
    ]
    
    for attester, subject, action, score in edges:
        calc.add_edge(AttestationEdge(attester, subject, action, score))
    
    print("=" * 60)
    print("ATF BLAST RADIUS ANALYSIS")
    print("=" * 60)
    print(f"Network: {len(edges)} attestation edges")
    print()
    
    # Scenario 1: Genesis compromised (worst case)
    report = calc.compute_blast("genesis")
    print(f"SCENARIO: '{report.compromised}' compromised")
    print(f"  Blast depth: {report.depth}")
    print(f"  Breadth by depth: {report.breadth_by_depth}")
    print(f"  Blast surface: {report.surface} agents")
    print(f"  Weighted surface: {report.weighted_surface}")
    print(f"  Concentration (Gini): {report.concentration}")
    print(f"  Affected: {report.affected_agents}")
    print(f"  Critical paths:")
    for p in report.critical_paths:
        print(f"    {'  →  '.join(p)}")
    print()
    
    # Scenario 2: Kit compromised (mid-tier)
    report2 = calc.compute_blast("kit")
    print(f"SCENARIO: '{report2.compromised}' compromised")
    print(f"  Blast depth: {report2.depth}")
    print(f"  Blast surface: {report2.surface} agents")
    print(f"  Weighted surface: {report2.weighted_surface}")
    print(f"  Affected: {report2.affected_agents}")
    print()
    
    # Scenario 3: Leaf node compromised (minimal)
    report3 = calc.compute_blast("theta")
    print(f"SCENARIO: '{report3.compromised}' compromised")
    print(f"  Blast surface: {report3.surface} agents")
    print(f"  Weighted surface: {report3.weighted_surface}")
    print()
    
    # Most dangerous nodes
    print("=" * 60)
    print("MOST DANGEROUS NODES (by weighted blast surface)")
    print("=" * 60)
    rankings = calc.find_most_dangerous()
    for i, (agent, surface) in enumerate(rankings[:8]):
        bar = "█" * int(surface / 2)
        print(f"  {i+1}. {agent:15s} {surface:6.1f}  {bar}")
    
    print()
    print("INSIGHT: Genesis has highest blast radius (expected).")
    print("But kit's radius is disproportionate due to TRANSFER edge")
    print("to gamma→theta (4x weight). TRANSFER chains are expensive")
    print("to validate but catastrophic when compromised.")


if __name__ == "__main__":
    demo()
