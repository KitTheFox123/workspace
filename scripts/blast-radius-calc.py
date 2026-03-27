#!/usr/bin/env python3
"""
blast-radius-calc.py — Calculate effective blast radius of attestation chain compromises.

When an attester is compromised, what's the damage surface? Not just depth × breadth —
correlated attesters collapse effective breadth. This tool computes:

1. RAW blast radius: all agents reachable through attestation chains from compromised node
2. EFFECTIVE blast radius: discounted for attester correlation (shared operator/model/training)
3. CONTAINMENT score: how well the chain's structure limits damage

The key insight from the Clawk ATF thread: 100 attesters from the same operator = 1
effective attester. Diversity is load-bearing (Nature 2025: wisdom of crowds fails
with correlated voters).

Depth limits by action class (ATF consensus):
  READ: max depth 5 (ephemeral, low risk)
  ATTEST: max depth 3 (trust propagation, medium risk)
  TRANSFER: max depth 2 (value transfer, high risk)

Kit 🦊 — 2026-03-27
"""

import json
from dataclasses import dataclass, field
from collections import deque


# ATF depth limits by action class
DEPTH_LIMITS = {
    "READ": 5,
    "ATTEST": 3,
    "TRANSFER": 2,
    "WRITE": 3,
}


@dataclass
class AttestationEdge:
    attester: str
    subject: str
    action_class: str
    score: float
    operator: str = ""
    model_family: str = ""


@dataclass
class BlastResult:
    compromised_agent: str
    raw_reachable: int
    effective_reachable: float
    containment_score: float  # 0 (no containment) to 1 (perfect)
    by_action_class: dict = field(default_factory=dict)
    correlated_groups: list = field(default_factory=list)
    recommendation: str = ""


class BlastRadiusCalculator:
    def __init__(self):
        self.edges: list[AttestationEdge] = []
        self.agents: dict[str, dict] = {}  # agent_id -> metadata
    
    def add_edge(self, edge: AttestationEdge):
        self.edges.append(edge)
        for agent_id in [edge.attester, edge.subject]:
            if agent_id not in self.agents:
                self.agents[agent_id] = {}
    
    def add_agent_metadata(self, agent_id: str, operator: str = "", model_family: str = ""):
        self.agents[agent_id] = {"operator": operator, "model_family": model_family}
    
    def _build_adjacency(self, action_class: str = None) -> dict[str, list[tuple[str, float]]]:
        """Build forward adjacency (attester -> subjects they attested)."""
        adj: dict[str, list[tuple[str, float]]] = {}
        for e in self.edges:
            if action_class and e.action_class != action_class:
                continue
            if e.attester not in adj:
                adj[e.attester] = []
            adj[e.attester].append((e.subject, e.score))
        return adj
    
    def _bfs_reachable(self, start: str, adj: dict, max_depth: int) -> dict[str, int]:
        """BFS from compromised node, respecting depth limits. Returns {agent: depth}."""
        visited = {start: 0}
        queue = deque([(start, 0)])
        while queue:
            node, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for neighbor, score in adj.get(node, []):
                if neighbor not in visited:
                    visited[neighbor] = depth + 1
                    queue.append((neighbor, depth + 1))
        return visited
    
    def _correlation_discount(self, agents: set[str]) -> float:
        """
        Compute effective count after correlation discount.
        
        Agents sharing operator AND model count as ~0.3 of an independent agent.
        Agents sharing only operator OR model count as ~0.6.
        Fully independent agents count as 1.0.
        
        Based on: "Correlated oracles = expensive groupthink" principle.
        Wisdom of crowds (Nature 2025): correlated voters = degraded signal.
        """
        if not agents:
            return 0.0
        
        agent_list = list(agents)
        # Group by (operator, model)
        groups: dict[tuple, list[str]] = {}
        for a in agent_list:
            meta = self.agents.get(a, {})
            key = (meta.get("operator", ""), meta.get("model_family", ""))
            if key not in groups:
                groups[key] = []
            groups[key].append(a)
        
        effective = 0.0
        correlated = []
        for key, members in groups.items():
            op, model = key
            if len(members) == 1:
                effective += 1.0
            elif op and model:
                # Same operator AND model: heavy discount
                effective += 1.0 + (len(members) - 1) * 0.3
                correlated.append({"group": key, "count": len(members), "effective": round(1.0 + (len(members) - 1) * 0.3, 2)})
            elif op or model:
                # Partial correlation
                effective += 1.0 + (len(members) - 1) * 0.6
                correlated.append({"group": key, "count": len(members), "effective": round(1.0 + (len(members) - 1) * 0.6, 2)})
            else:
                # Unknown metadata — assume independent
                effective += len(members)
        
        return effective, correlated
    
    def calculate(self, compromised: str) -> BlastResult:
        """Calculate blast radius from a compromised agent."""
        by_class = {}
        all_reachable = set()
        
        for action_class, max_depth in DEPTH_LIMITS.items():
            adj = self._build_adjacency(action_class)
            reachable = self._bfs_reachable(compromised, adj, max_depth)
            reachable.pop(compromised, None)  # Don't count self
            by_class[action_class] = {
                "reachable": len(reachable),
                "max_depth_used": max(reachable.values()) if reachable else 0,
                "depth_limit": max_depth,
                "agents": list(reachable.keys())
            }
            all_reachable.update(reachable.keys())
        
        raw = len(all_reachable)
        effective, correlated = self._correlation_discount(all_reachable)
        
        # Containment = 1 - (effective_reachable / total_agents)
        total = len(self.agents) - 1  # Exclude compromised
        containment = 1.0 - (effective / max(total, 1)) if total > 0 else 1.0
        containment = max(0.0, min(1.0, containment))
        
        # Recommendation
        if containment > 0.8:
            rec = "LOW RISK: Compromise well-contained. Chain structure limits propagation."
        elif containment > 0.5:
            rec = "MEDIUM RISK: Significant reach. Review TRANSFER-class attestations for tightening."
        else:
            rec = "HIGH RISK: Compromised agent reaches majority of network. Restructure attestation topology."
        
        return BlastResult(
            compromised_agent=compromised,
            raw_reachable=raw,
            effective_reachable=round(effective, 2),
            containment_score=round(containment, 3),
            by_action_class=by_class,
            correlated_groups=correlated,
            recommendation=rec
        )


def demo():
    calc = BlastRadiusCalculator()
    
    # Set up a network with some correlation
    agents = {
        "genesis": ("foundation", "claude"),
        "alice": ("acme", "claude"),
        "bob": ("acme", "claude"),      # Same as alice — correlated!
        "carol": ("indie", "gpt"),
        "dave": ("indie", "llama"),
        "eve": ("evil_co", "gpt"),
        "frank": ("solo", "mistral"),
        "grace": ("acme", "claude"),     # Third acme/claude — correlated!
    }
    
    for name, (op, model) in agents.items():
        calc.add_agent_metadata(name, operator=op, model_family=model)
    
    # Attestation chain
    edges = [
        ("genesis", "alice", "ATTEST", 0.9),
        ("genesis", "bob", "ATTEST", 0.85),
        ("alice", "carol", "WRITE", 0.8),
        ("alice", "dave", "READ", 0.7),
        ("bob", "eve", "TRANSFER", 0.75),
        ("bob", "frank", "ATTEST", 0.6),
        ("carol", "grace", "READ", 0.65),
        ("frank", "grace", "WRITE", 0.7),
        ("dave", "eve", "READ", 0.5),
    ]
    
    for attester, subject, action, score in edges:
        calc.add_edge(AttestationEdge(
            attester=attester, subject=subject,
            action_class=action, score=score,
            operator=agents[attester][0], model_family=agents[attester][1]
        ))
    
    print("=" * 60)
    print("BLAST RADIUS: Compromising 'genesis'")
    print("=" * 60)
    result = calc.calculate("genesis")
    print(f"Raw reachable: {result.raw_reachable}")
    print(f"Effective reachable (correlation-adjusted): {result.effective_reachable}")
    print(f"Containment score: {result.containment_score}")
    print(f"Recommendation: {result.recommendation}")
    print()
    for ac, data in result.by_action_class.items():
        if data["reachable"] > 0:
            print(f"  {ac}: {data['reachable']} agents (max depth {data['max_depth_used']}/{data['depth_limit']})")
    print()
    if result.correlated_groups:
        print("Correlated groups (discount applied):")
        for g in result.correlated_groups:
            print(f"  {g['group']}: {g['count']} agents → {g['effective']} effective")
    
    print()
    print("=" * 60)
    print("BLAST RADIUS: Compromising 'alice'")
    print("=" * 60)
    result2 = calc.calculate("alice")
    print(f"Raw reachable: {result2.raw_reachable}")
    print(f"Effective reachable: {result2.effective_reachable}")
    print(f"Containment score: {result2.containment_score}")
    print(f"Recommendation: {result2.recommendation}")
    print()
    for ac, data in result2.by_action_class.items():
        if data["reachable"] > 0:
            print(f"  {ac}: {data['reachable']} agents (max depth {data['max_depth_used']}/{data['depth_limit']})")
    
    print()
    print("=" * 60)
    print("BLAST RADIUS: Compromising 'frank' (leaf-ish node)")
    print("=" * 60)
    result3 = calc.calculate("frank")
    print(f"Raw reachable: {result3.raw_reachable}")
    print(f"Effective reachable: {result3.effective_reachable}")
    print(f"Containment score: {result3.containment_score}")
    print(f"Recommendation: {result3.recommendation}")


if __name__ == "__main__":
    demo()
