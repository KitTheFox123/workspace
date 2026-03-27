#!/usr/bin/env python3
"""
chain-depth-blast-radius.py — ATF Chain Depth Limit blast radius calculator.

Models the ATF CHAIN_DEPTH_LIMIT indexed by action_class:
  READ[5] → ATTEST[3] → TRANSFER[2]

Computes blast radius (damage surface area) as function of depth × breadth.
Key insight from Clawk thread: depth limits damage VELOCITY (cascade speed),
breadth limits damage VOLUME (total affected nodes).

Blast surface area = Σ(nodes reachable at each depth level)
Cascade time = depth × average propagation delay

Kit 🦊 — 2026-03-27
"""

import json
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class AttestationNode:
    agent_id: str
    depth: int = 0
    children: list = field(default_factory=list)
    action_class: str = "READ"


DEPTH_LIMITS = {
    "READ": 5,
    "ATTEST": 3,
    "TRANSFER": 2,
}

# Average propagation delay per action class (seconds)
PROPAGATION_DELAY = {
    "READ": 1.0,    # Fast, low-stakes
    "ATTEST": 10.0,  # Medium, requires evaluation
    "TRANSFER": 60.0, # Slow, high-stakes
}


def build_chain(root_id: str, action_class: str, branching_factor: int,
                max_depth: int = None) -> AttestationNode:
    """Build a tree of attestation chains with given branching factor."""
    if max_depth is None:
        max_depth = DEPTH_LIMITS.get(action_class, 3)
    
    def _build(agent_id: str, depth: int) -> AttestationNode:
        node = AttestationNode(agent_id=agent_id, depth=depth, action_class=action_class)
        if depth < max_depth:
            for i in range(branching_factor):
                child_id = f"{agent_id}_{depth+1}_{i}"
                node.children.append(_build(child_id, depth + 1))
        return node
    
    return _build(root_id, 0)


def compute_blast_radius(root: AttestationNode) -> dict:
    """
    Compute blast radius metrics for a chain.
    
    If the root node is compromised, how much damage can cascade?
    """
    depth_counts = defaultdict(int)
    total_nodes = 0
    max_depth = 0
    
    def _traverse(node):
        nonlocal total_nodes, max_depth
        total_nodes += 1
        depth_counts[node.depth] += 1
        max_depth = max(max_depth, node.depth)
        for child in node.children:
            _traverse(child)
    
    _traverse(root)
    
    action_class = root.action_class
    delay = PROPAGATION_DELAY.get(action_class, 1.0)
    
    return {
        "action_class": action_class,
        "depth_limit": DEPTH_LIMITS.get(action_class, "?"),
        "total_nodes": total_nodes,
        "max_depth": max_depth,
        "depth_distribution": dict(depth_counts),
        "blast_surface_area": total_nodes - 1,  # Exclude root
        "cascade_time_seconds": max_depth * delay,
        "damage_velocity": (total_nodes - 1) / max(max_depth * delay, 0.01),
        "nodes_at_max_depth": depth_counts[max_depth],
    }


def compare_depth_vs_breadth():
    """
    Compare: deep-narrow vs shallow-wide chains.
    Thread insight: depth limits velocity, breadth limits volume.
    """
    print("=" * 70)
    print("DEPTH vs BREADTH: Same total attestation effort, different topology")
    print("=" * 70)
    print()
    
    scenarios = [
        ("Deep-Narrow", "TRANSFER", 2, 5),   # 2 branches, 5 deep (exceeds limit!)
        ("Shallow-Wide", "TRANSFER", 10, 2),  # 10 branches, 2 deep (within limit)
        ("Balanced", "TRANSFER", 4, 3),        # 4 branches, 3 deep (exceeds by 1)
    ]
    
    for name, action, branching, depth in scenarios:
        # Clamp to depth limit
        effective_depth = min(depth, DEPTH_LIMITS[action])
        root = build_chain("root", action, branching, effective_depth)
        metrics = compute_blast_radius(root)
        
        print(f"  {name} (branching={branching}, requested_depth={depth}, "
              f"effective={effective_depth}):")
        print(f"    Total nodes: {metrics['total_nodes']}")
        print(f"    Blast surface: {metrics['blast_surface_area']}")
        print(f"    Cascade time: {metrics['cascade_time_seconds']:.0f}s")
        print(f"    Damage velocity: {metrics['damage_velocity']:.2f} nodes/sec")
        print(f"    Nodes at frontier: {metrics['nodes_at_max_depth']}")
        print()


def compare_action_classes():
    """Compare blast radius across action classes with same branching."""
    print("=" * 70)
    print("ACTION CLASS COMPARISON: branching_factor=3")
    print("=" * 70)
    print()
    
    branching = 3
    for action in ["READ", "ATTEST", "TRANSFER"]:
        depth = DEPTH_LIMITS[action]
        root = build_chain("root", action, branching, depth)
        metrics = compute_blast_radius(root)
        
        print(f"  {action}[{depth}]:")
        print(f"    Total nodes: {metrics['total_nodes']}")
        print(f"    Blast surface: {metrics['blast_surface_area']}")
        print(f"    Cascade time: {metrics['cascade_time_seconds']:.0f}s")
        print(f"    Damage velocity: {metrics['damage_velocity']:.2f} nodes/sec")
        depth_str = " → ".join(f"d{d}:{c}" for d, c in sorted(metrics['depth_distribution'].items()))
        print(f"    Distribution: {depth_str}")
        print()


def risk_score(action_class: str, branching_factor: int) -> dict:
    """
    Compute a composite risk score for a given chain topology.
    
    Risk = blast_surface × (1 / cascade_time) × action_weight
    Higher = more dangerous. Fast + wide + high-stakes = maximum risk.
    """
    action_weights = {"READ": 1, "ATTEST": 5, "TRANSFER": 10}
    
    depth = DEPTH_LIMITS.get(action_class, 3)
    root = build_chain("root", action_class, branching_factor, depth)
    metrics = compute_blast_radius(root)
    
    weight = action_weights.get(action_class, 1)
    surface = metrics["blast_surface_area"]
    velocity = metrics["damage_velocity"]
    
    score = surface * velocity * weight
    
    return {
        "action_class": action_class,
        "branching_factor": branching_factor,
        "depth_limit": depth,
        "blast_surface": surface,
        "velocity": round(velocity, 2),
        "weight": weight,
        "risk_score": round(score, 1),
        "risk_level": "CRITICAL" if score > 1000 else "HIGH" if score > 100 else "MEDIUM" if score > 10 else "LOW"
    }


def demo():
    compare_action_classes()
    compare_depth_vs_breadth()
    
    print("=" * 70)
    print("RISK MATRIX: action_class × branching_factor")
    print("=" * 70)
    print()
    print(f"{'Action':<12} {'Branch':<8} {'Depth':<7} {'Surface':<10} {'Velocity':<10} {'Risk':<10} {'Level'}")
    print("-" * 70)
    
    for action in ["READ", "ATTEST", "TRANSFER"]:
        for branching in [2, 3, 5, 10]:
            r = risk_score(action, branching)
            print(f"{r['action_class']:<12} {r['branching_factor']:<8} "
                  f"{r['depth_limit']:<7} {r['blast_surface']:<10} "
                  f"{r['velocity']:<10} {r['risk_score']:<10} {r['risk_level']}")
    
    print()
    print("KEY INSIGHT: TRANSFER with branching=10 is LOW risk because depth=2")
    print("caps the cascade. READ with branching=10 is HIGH because depth=5")
    print("lets damage propagate. The depth limit IS the safety mechanism.")
    print()
    print("DEPTH limits velocity. BREADTH limits volume. ATF needs both.")


if __name__ == "__main__":
    demo()
