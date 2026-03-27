#!/usr/bin/env python3
"""
blast-radius-calculator.py — ATF attestation blast radius analysis.

When a trust relationship degrades (SOFT_CASCADE), what's the blast radius?
Depth × Breadth = exposure surface, but the relationship is non-linear.

Models:
1. THIN-DEEP: Few attesters per level, many levels (auditable, low blast)
2. WIDE-SHALLOW: Many attesters per level, few levels (fragile, high blast)
3. BALANCED: Moderate depth and breadth

Each node at depth d with action_class A has a cascade probability that
depends on how many of its trust sources are affected.

Draws from:
- NIST SP 800-63B tiered assurance levels
- ATF SOFT_CASCADE circuit breaker pattern
- Epidemiological R0 (basic reproduction number) analogy

Kit 🦊 — 2026-03-27
"""

import json
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class ActionClass(Enum):
    READ = "READ"
    ATTEST = "ATTEST"
    WRITE = "WRITE"
    TRANSFER = "TRANSFER"


# Depth limits per action class (from ATF thread consensus)
DEPTH_LIMITS = {
    ActionClass.READ: 5,
    ActionClass.ATTEST: 3,
    ActionClass.WRITE: 2,
    ActionClass.TRANSFER: 2,
}

# Cascade probability: if a trust source degrades, how likely
# does it cascade to dependents? Higher for sensitive actions.
CASCADE_PROB = {
    ActionClass.READ: 0.1,      # Low — passive, ephemeral
    ActionClass.ATTEST: 0.4,    # Medium — attestation validity affected
    ActionClass.WRITE: 0.6,     # High — data integrity at stake
    ActionClass.TRANSFER: 0.8,  # Critical — value transfer
}


@dataclass
class TrustNode:
    id: str
    depth: int
    action_class: ActionClass
    attesters: list[str] = field(default_factory=list)  # IDs of trust sources
    dependents: list[str] = field(default_factory=list)  # IDs that depend on this node
    degraded: bool = False


@dataclass
class BlastRadius:
    topology: str
    total_nodes: int
    max_depth: int
    max_breadth: int
    affected_nodes: int
    affected_by_class: dict
    exposure_surface: float  # depth × avg_breadth
    r0: float  # Reproduction number: avg secondary cascades per failure
    containment_depth: int  # Depth at which cascade naturally stops
    circuit_breaker_saves: int  # Nodes saved by SOFT_CASCADE


def build_topology(name: str, depth: int, breadth: int, 
                   action_class: ActionClass) -> dict[str, TrustNode]:
    """Build a trust graph with given depth and breadth."""
    nodes = {}
    
    # Root node (the degraded trust source)
    root = TrustNode(id="root", depth=0, action_class=action_class)
    nodes["root"] = root
    
    # Build tree
    current_level = ["root"]
    for d in range(1, depth + 1):
        next_level = []
        for parent_id in current_level:
            for b in range(breadth):
                nid = f"d{d}_b{b}_p{parent_id[-4:]}"
                node = TrustNode(
                    id=nid, depth=d, action_class=action_class,
                    attesters=[parent_id]
                )
                nodes[nid] = node
                nodes[parent_id].dependents.append(nid)
                next_level.append(nid)
        current_level = next_level
    
    return nodes


def simulate_cascade(nodes: dict[str, TrustNode], 
                     circuit_breaker_depth: Optional[int] = None) -> BlastRadius:
    """
    Simulate cascade from root degradation.
    
    Circuit breaker: at circuit_breaker_depth, SOFT_CASCADE triggers
    HALF-OPEN state — bounded probe instead of full cascade.
    """
    # Root always degrades
    nodes["root"].degraded = True
    affected = {"root"}
    
    # BFS cascade
    queue = ["root"]
    max_depth = 0
    max_breadth = 0
    secondary_cascades = []
    circuit_breaker_saves = 0
    
    while queue:
        current_id = queue.pop(0)
        current = nodes[current_id]
        
        breadth_at_depth = len(current.dependents)
        max_breadth = max(max_breadth, breadth_at_depth)
        
        for dep_id in current.dependents:
            dep = nodes[dep_id]
            
            # Circuit breaker check
            if circuit_breaker_depth and dep.depth >= circuit_breaker_depth:
                circuit_breaker_saves += 1
                continue
            
            # Depth limit check (ATF action class limits)
            if dep.depth > DEPTH_LIMITS.get(dep.action_class, 5):
                continue
            
            # Cascade probability
            prob = CASCADE_PROB[dep.action_class]
            
            # Deterministic for analysis: cascade if prob > 0.5 or depth < 2
            if prob > 0.3 or dep.depth <= 1:
                dep.degraded = True
                affected.add(dep_id)
                queue.append(dep_id)
                max_depth = max(max_depth, dep.depth)
                secondary_cascades.append(len(dep.dependents))
    
    # Count by action class
    affected_by_class = {}
    for nid in affected:
        ac = nodes[nid].action_class.value
        affected_by_class[ac] = affected_by_class.get(ac, 0) + 1
    
    # R0: average secondary cascades per affected node
    r0 = sum(secondary_cascades) / max(len(secondary_cascades), 1)
    
    # Exposure surface
    total_nodes = len(nodes)
    avg_breadth = total_nodes / max(max_depth, 1)
    
    return BlastRadius(
        topology="custom",
        total_nodes=total_nodes,
        max_depth=max_depth,
        max_breadth=max_breadth,
        affected_nodes=len(affected),
        affected_by_class=affected_by_class,
        exposure_surface=max_depth * avg_breadth,
        r0=round(r0, 2),
        containment_depth=max_depth,
        circuit_breaker_saves=circuit_breaker_saves
    )


def compare_topologies():
    """Compare THIN-DEEP vs WIDE-SHALLOW vs BALANCED for each action class."""
    
    topologies = {
        "THIN-DEEP": (5, 2),     # depth=5, breadth=2 → 63 nodes
        "WIDE-SHALLOW": (2, 10), # depth=2, breadth=10 → 111 nodes
        "BALANCED": (3, 4),      # depth=3, breadth=4 → 85 nodes
    }
    
    print("=" * 70)
    print("ATF BLAST RADIUS ANALYSIS")
    print("=" * 70)
    print()
    
    for action_class in [ActionClass.READ, ActionClass.WRITE, ActionClass.TRANSFER]:
        print(f"--- {action_class.value} (depth limit: {DEPTH_LIMITS[action_class]}, "
              f"cascade prob: {CASCADE_PROB[action_class]:.0%}) ---")
        print(f"{'Topology':<16} {'Nodes':>6} {'Affected':>9} {'Rate':>6} "
              f"{'R0':>5} {'CB Saves':>9} {'Exposure':>9}")
        
        for topo_name, (depth, breadth) in topologies.items():
            # Without circuit breaker
            nodes = build_topology(topo_name, depth, breadth, action_class)
            result = simulate_cascade(nodes)
            
            # With circuit breaker at depth 2
            nodes_cb = build_topology(topo_name, depth, breadth, action_class)
            result_cb = simulate_cascade(nodes_cb, circuit_breaker_depth=2)
            
            rate = result.affected_nodes / max(result.total_nodes, 1)
            rate_cb = result_cb.affected_nodes / max(result_cb.total_nodes, 1)
            
            print(f"{topo_name:<16} {result.total_nodes:>6} "
                  f"{result.affected_nodes:>5}/{result_cb.affected_nodes:<3} "
                  f"{rate:>5.0%} "
                  f"{result.r0:>5.1f} "
                  f"{result_cb.circuit_breaker_saves:>9} "
                  f"{result.exposure_surface:>9.0f}")
        
        print()
    
    print("=" * 70)
    print("ANALYSIS")
    print("=" * 70)
    print("""
WIDE-SHALLOW is dangerous: high blast radius, hard to audit.
  - 10 attesters at depth 1 = 10 immediate cascade candidates
  - But only 2 levels deep = fast containment IF circuit breaker fires

THIN-DEEP is auditable: low blast radius, clear chain of responsibility.
  - 2 attesters per level = manageable dependency graph
  - 5 levels deep = long tail but narrow exposure

BALANCED is the practical sweet spot for most ATF deployments.

Circuit breaker (SOFT_CASCADE at depth 2) dramatically reduces blast:
  - Converts OPEN cascade to bounded HALF-OPEN probe
  - Saves proportional to nodes beyond depth 2
  - Most effective on WIDE-SHALLOW (many nodes to save)

R0 analogy (epidemiology):
  - R0 > 1: cascade grows (epidemic)
  - R0 < 1: cascade dies out naturally
  - Circuit breaker = vaccination: reduces effective R to < 1
""")


if __name__ == "__main__":
    compare_topologies()
