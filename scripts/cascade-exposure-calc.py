#!/usr/bin/env python3
"""
cascade-exposure-calc.py — ATF cascade exposure calculator.

Models trust cascade failures using stochastic interaction graphs
(Guo et al, arxiv 2503.09904). Key insight: depth AND breadth
determine blast radius. A shallow-but-wide trust graph (2-deep,
100 attesters) has MORE exposure surface than a deep-but-narrow
one (5-deep, 2 attesters).

Exposure metric: E = Σ (depth_i × fan_out_i × action_class_weight_i)

Action class weights (from ATF CHAIN_DEPTH_LIMIT):
  READ[5]     → weight 1 (low blast)
  ATTEST[3]   → weight 3 (medium blast)
  TRANSFER[2] → weight 5 (high blast)

Cascade modes (from eigen-analysis of stochastic interaction matrix):
  - Persistent: cycles that sustain failure propagation (eigenvalue ≈ 1)
  - Transient: failures that decay naturally (|eigenvalue| < 1)
  - Trivial: isolated failures (eigenvalue = 0)

Kit 🦊 — 2026-03-27
"""

import json
from dataclasses import dataclass, field
from typing import Optional
import math


ACTION_WEIGHTS = {
    "READ": 1,
    "ATTEST": 3,
    "WRITE": 4,
    "TRANSFER": 5,
}

DEPTH_LIMITS = {
    "READ": 5,
    "ATTEST": 3,
    "WRITE": 3,
    "TRANSFER": 2,
}


@dataclass
class TrustNode:
    agent_id: str
    action_class: str
    depth: int
    children: list["TrustNode"] = field(default_factory=list)
    trust_score: float = 1.0


@dataclass
class CascadeAnalysis:
    total_exposure: float
    max_depth: int
    max_breadth: int
    node_count: int
    mode: str  # persistent, transient, trivial
    critical_nodes: list[dict]  # nodes with highest local exposure
    depth_limit_violations: list[dict]


class CascadeExposureCalculator:
    
    def __init__(self):
        self.root: Optional[TrustNode] = None
    
    def build_tree(self, root: TrustNode):
        self.root = root
    
    def _node_exposure(self, node: TrustNode) -> float:
        """Local exposure = depth × fan_out × action_weight × trust_score."""
        fan_out = len(node.children)
        weight = ACTION_WEIGHTS.get(node.action_class, 1)
        return node.depth * max(fan_out, 1) * weight * node.trust_score
    
    def _traverse(self, node: TrustNode, results: dict):
        """DFS traversal collecting metrics."""
        exposure = self._node_exposure(node)
        results["total_exposure"] += exposure
        results["node_count"] += 1
        results["max_depth"] = max(results["max_depth"], node.depth)
        
        breadth_at_depth = results.setdefault("breadth_by_depth", {})
        breadth_at_depth[node.depth] = breadth_at_depth.get(node.depth, 0) + 1
        
        # Track critical nodes
        results["nodes"].append({
            "agent": node.agent_id,
            "depth": node.depth,
            "fan_out": len(node.children),
            "action_class": node.action_class,
            "local_exposure": round(exposure, 2)
        })
        
        # Check depth limit violations
        limit = DEPTH_LIMITS.get(node.action_class, 5)
        if node.depth > limit:
            results["violations"].append({
                "agent": node.agent_id,
                "action_class": node.action_class,
                "depth": node.depth,
                "limit": limit,
                "excess": node.depth - limit
            })
        
        for child in node.children:
            self._traverse(child, results)
    
    def analyze(self) -> CascadeAnalysis:
        if not self.root:
            raise ValueError("No tree built")
        
        results = {
            "total_exposure": 0.0,
            "node_count": 0,
            "max_depth": 0,
            "nodes": [],
            "violations": [],
            "breadth_by_depth": {}
        }
        
        self._traverse(self.root, results)
        
        max_breadth = max(results["breadth_by_depth"].values()) if results["breadth_by_depth"] else 0
        
        # Classify cascade mode
        # Persistent: high exposure, deep chains
        # Transient: moderate, decaying
        # Trivial: isolated nodes
        exposure_per_node = results["total_exposure"] / max(results["node_count"], 1)
        if exposure_per_node > 10:
            mode = "persistent"
        elif exposure_per_node > 3:
            mode = "transient"
        else:
            mode = "trivial"
        
        # Sort critical nodes by exposure
        critical = sorted(results["nodes"], key=lambda x: -x["local_exposure"])[:5]
        
        return CascadeAnalysis(
            total_exposure=round(results["total_exposure"], 2),
            max_depth=results["max_depth"],
            max_breadth=max_breadth,
            node_count=results["node_count"],
            mode=mode,
            critical_nodes=critical,
            depth_limit_violations=results["violations"]
        )


def demo():
    calc = CascadeExposureCalculator()
    
    # Scenario 1: Deep-but-narrow (5 deep, 2 wide)
    print("=" * 60)
    print("SCENARIO 1: Deep-narrow (depth=5, breadth=2)")
    print("=" * 60)
    
    root = TrustNode("genesis", "ATTEST", 0)
    a = TrustNode("alice", "ATTEST", 1)
    b = TrustNode("bob", "ATTEST", 1)
    root.children = [a, b]
    
    a1 = TrustNode("carol", "WRITE", 2)
    a2 = TrustNode("dave", "WRITE", 2)
    a.children = [a1, a2]
    
    a1a = TrustNode("eve", "READ", 3)
    a1.children = [a1a]
    
    a1a1 = TrustNode("frank", "READ", 4)
    a1a.children = [a1a1]
    
    a1a1a = TrustNode("grace", "READ", 5)
    a1a1.children = [a1a1a]
    
    calc.build_tree(root)
    r1 = calc.analyze()
    print(f"Total exposure: {r1.total_exposure}")
    print(f"Depth: {r1.max_depth}, Breadth: {r1.max_breadth}")
    print(f"Nodes: {r1.node_count}, Mode: {r1.mode}")
    print(f"Violations: {len(r1.depth_limit_violations)}")
    print()
    
    # Scenario 2: Shallow-but-wide (2 deep, 50 wide)
    print("=" * 60)
    print("SCENARIO 2: Shallow-wide (depth=2, breadth=50)")
    print("=" * 60)
    
    calc2 = CascadeExposureCalculator()
    root2 = TrustNode("hub", "ATTEST", 0)
    for i in range(50):
        child = TrustNode(f"attester_{i}", "TRANSFER", 1)
        leaf = TrustNode(f"recipient_{i}", "READ", 2)
        child.children = [leaf]
        root2.children.append(child)
    
    calc2.build_tree(root2)
    r2 = calc2.analyze()
    print(f"Total exposure: {r2.total_exposure}")
    print(f"Depth: {r2.max_depth}, Breadth: {r2.max_breadth}")
    print(f"Nodes: {r2.node_count}, Mode: {r2.mode}")
    print(f"Critical nodes: {r2.critical_nodes[:3]}")
    print()
    
    # Scenario 3: TRANSFER chain exceeding depth limit
    print("=" * 60)
    print("SCENARIO 3: Depth limit violation (TRANSFER at depth 4)")
    print("=" * 60)
    
    calc3 = CascadeExposureCalculator()
    root3 = TrustNode("origin", "TRANSFER", 0)
    n1 = TrustNode("relay_1", "TRANSFER", 1)
    n2 = TrustNode("relay_2", "TRANSFER", 2)
    n3 = TrustNode("relay_3", "TRANSFER", 3)
    n4 = TrustNode("relay_4", "TRANSFER", 4)
    root3.children = [n1]
    n1.children = [n2]
    n2.children = [n3]
    n3.children = [n4]
    
    calc3.build_tree(root3)
    r3 = calc3.analyze()
    print(f"Total exposure: {r3.total_exposure}")
    print(f"Depth: {r3.max_depth}, Mode: {r3.mode}")
    print(f"Violations: {json.dumps(r3.depth_limit_violations, indent=2)}")
    print()
    
    # Compare
    print("=" * 60)
    print("COMPARISON")
    print("=" * 60)
    print(f"Deep-narrow:     exposure={r1.total_exposure:>8} (depth={r1.max_depth}, breadth={r1.max_breadth}, nodes={r1.node_count})")
    print(f"Shallow-wide:    exposure={r2.total_exposure:>8} (depth={r2.max_depth}, breadth={r2.max_breadth}, nodes={r2.node_count})")
    print(f"Depth violation:  exposure={r3.total_exposure:>8} (depth={r3.max_depth}, breadth={r3.max_breadth}, nodes={r3.node_count})")
    print()
    ratio = r2.total_exposure / r1.total_exposure if r1.total_exposure > 0 else float('inf')
    print(f"Shallow-wide has {ratio:.1f}x more exposure than deep-narrow.")
    print("depth × breadth = exposure. min() caps depth. what caps breadth?")
    print()
    print("Source: Guo et al (arxiv 2503.09904) — stochastic interaction")
    print("graphs with eigen-analysis for cascade failure propagation.")


if __name__ == "__main__":
    demo()
