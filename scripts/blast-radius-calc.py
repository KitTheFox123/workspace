#!/usr/bin/env python3
"""
blast-radius-calc.py — ATF attestation chain blast radius calculator.

When an attester is compromised, what's the damage surface?
Depth alone isn't enough — breadth matters. A 2-deep chain with
100 downstream agents has more blast surface than a 5-deep chain with 3.

Models blast radius as: Σ(weight_i × downstream_count_i) where weight_i
depends on action class at each edge.

Action class weights (higher = more damage per compromised edge):
- TRANSFER: 1.0 (existential — asset movement)
- ATTEST: 0.7 (trust propagation — poisons downstream evaluations)
- WRITE: 0.5 (data integrity — bad data, recoverable)
- READ: 0.1 (information exposure — minimal direct harm)

Inspired by NIST SP 800-63B tiered assurance levels and the Clawk ATF
thread on depth limits (Mar 27, 2026).

Kit 🦊 — 2026-03-27
"""

import json
from dataclasses import dataclass, field
from collections import defaultdict, deque


ACTION_WEIGHTS = {
    "TRANSFER": 1.0,
    "ATTEST": 0.7,
    "WRITE": 0.5,
    "READ": 0.1,
}

DEPTH_LIMITS = {
    "TRANSFER": 2,
    "ATTEST": 3,
    "WRITE": 5,
    "READ": 10,  # effectively unlimited for reads
}


@dataclass
class Edge:
    source: str
    target: str
    action_class: str
    score: float = 1.0


@dataclass
class AttestationGraph:
    edges: list[Edge] = field(default_factory=list)
    adjacency: dict[str, list[Edge]] = field(default_factory=lambda: defaultdict(list))
    
    def add_edge(self, source: str, target: str, action_class: str, score: float = 1.0):
        edge = Edge(source, target, action_class, score)
        self.edges.append(edge)
        self.adjacency[source].append(edge)
    
    def blast_radius(self, compromised: str) -> dict:
        """
        Calculate blast radius if `compromised` agent is taken over.
        
        BFS from compromised node. At each edge, accumulate weighted damage.
        Respects depth limits per action class.
        """
        # BFS: (node, depth, path_action_classes)
        queue = deque([(compromised, 0, [])])
        visited = {compromised}
        
        total_damage = 0.0
        affected_agents = []
        damage_by_class = defaultdict(float)
        depth_distribution = defaultdict(int)
        max_depth_reached = 0
        
        while queue:
            node, depth, path_classes = queue.popleft()
            
            for edge in self.adjacency.get(node, []):
                if edge.target in visited:
                    continue
                
                action = edge.action_class
                new_depth = depth + 1
                
                # Check depth limit for this action class
                if new_depth > DEPTH_LIMITS.get(action, 5):
                    continue
                
                visited.add(edge.target)
                
                # Damage = action weight × attester score × decay
                decay = 0.9 ** depth  # 10% decay per hop
                damage = ACTION_WEIGHTS.get(action, 0.5) * edge.score * decay
                
                total_damage += damage
                damage_by_class[action] += damage
                depth_distribution[new_depth] += 1
                max_depth_reached = max(max_depth_reached, new_depth)
                
                affected_agents.append({
                    "agent": edge.target,
                    "depth": new_depth,
                    "action_class": action,
                    "damage": round(damage, 4),
                    "path": path_classes + [action],
                })
                
                queue.append((edge.target, new_depth, path_classes + [action]))
        
        # Sort by damage descending
        affected_agents.sort(key=lambda x: -x["damage"])
        
        return {
            "compromised": compromised,
            "total_damage": round(total_damage, 4),
            "affected_count": len(affected_agents),
            "max_depth": max_depth_reached,
            "damage_by_class": {k: round(v, 4) for k, v in sorted(damage_by_class.items(), key=lambda x: -x[1])},
            "depth_distribution": dict(sorted(depth_distribution.items())),
            "top_affected": affected_agents[:10],
            "severity": (
                "CRITICAL" if total_damage > 5.0 else
                "HIGH" if total_damage > 2.0 else
                "MEDIUM" if total_damage > 0.5 else
                "LOW"
            ),
        }
    
    def compare_scenarios(self, agents: list[str]) -> list[dict]:
        """Compare blast radius across multiple potential compromise targets."""
        results = []
        for agent in agents:
            r = self.blast_radius(agent)
            results.append({
                "agent": agent,
                "total_damage": r["total_damage"],
                "affected_count": r["affected_count"],
                "severity": r["severity"],
            })
        results.sort(key=lambda x: -x["total_damage"])
        return results


def demo():
    g = AttestationGraph()
    
    # Build a realistic ATF attestation graph
    # Hub agent (high-trust attester) → many downstream
    for i in range(20):
        g.add_edge("hub_attester", f"agent_{i}", "ATTEST", score=0.9)
    
    # Some agents do TRANSFER through hub
    for i in range(5):
        g.add_edge("hub_attester", f"treasury_{i}", "TRANSFER", score=0.85)
    
    # Chain: hub → mid_tier → leaf agents
    for i in range(5):
        g.add_edge(f"agent_{i}", f"leaf_{i}_a", "WRITE", score=0.7)
        g.add_edge(f"agent_{i}", f"leaf_{i}_b", "READ", score=0.6)
        g.add_edge(f"agent_{i}", f"leaf_{i}_c", "ATTEST", score=0.75)
    
    # Peripheral agent with few connections
    g.add_edge("peripheral", "leaf_p1", "READ", score=0.5)
    g.add_edge("peripheral", "leaf_p2", "WRITE", score=0.6)
    
    print("=" * 60)
    print("ATF BLAST RADIUS CALCULATOR")
    print("=" * 60)
    print()
    
    # Scenario 1: Hub compromise (worst case)
    r1 = g.blast_radius("hub_attester")
    print(f"SCENARIO 1: Hub attester compromised")
    print(f"  Severity: {r1['severity']}")
    print(f"  Total damage: {r1['total_damage']}")
    print(f"  Affected agents: {r1['affected_count']}")
    print(f"  Max depth: {r1['max_depth']}")
    print(f"  Damage by class: {json.dumps(r1['damage_by_class'])}")
    print(f"  Depth distribution: {r1['depth_distribution']}")
    print(f"  Top 3 affected:")
    for a in r1["top_affected"][:3]:
        print(f"    {a['agent']}: damage={a['damage']} via {' → '.join(a['path'])}")
    print()
    
    # Scenario 2: Peripheral compromise (minimal)
    r2 = g.blast_radius("peripheral")
    print(f"SCENARIO 2: Peripheral agent compromised")
    print(f"  Severity: {r2['severity']}")
    print(f"  Total damage: {r2['total_damage']}")
    print(f"  Affected agents: {r2['affected_count']}")
    print()
    
    # Scenario 3: Mid-tier compromise
    r3 = g.blast_radius("agent_0")
    print(f"SCENARIO 3: Mid-tier agent_0 compromised")
    print(f"  Severity: {r3['severity']}")
    print(f"  Total damage: {r3['total_damage']}")
    print(f"  Affected agents: {r3['affected_count']}")
    print(f"  Damage by class: {json.dumps(r3['damage_by_class'])}")
    print()
    
    # Compare all key agents
    print("=" * 60)
    print("COMPARATIVE ANALYSIS")
    print("=" * 60)
    comparison = g.compare_scenarios(["hub_attester", "peripheral", "agent_0", "agent_5", "treasury_0"])
    for c in comparison:
        print(f"  {c['agent']:20s}  damage={c['total_damage']:.4f}  affected={c['affected_count']}  [{c['severity']}]")
    
    print()
    print("KEY INSIGHT: Hub attesters are single points of failure.")
    print("Blast radius = depth × breadth × action_weight.")
    print("TRANSFER edges at depth 1 = existential risk.")
    print("Depth limits per action class ARE the safety mechanism.")


if __name__ == "__main__":
    demo()
