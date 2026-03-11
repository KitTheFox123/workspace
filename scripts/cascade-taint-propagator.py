#!/usr/bin/env python3
"""
cascade-taint-propagator.py — Taint propagation through agent cert DAGs.

Inspired by Baird 2026 (ICSE): cascaded vulnerabilities in supply chain SBOMs.
Agent cert DAGs are isomorphic: contaminated foundation → everything downstream suspect.

Models: heterogeneous graph with cert nodes, dependency edges, witness nodes at forks.
Propagates taint from compromised node to all reachable descendants.
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NodeStatus(Enum):
    CLEAN = "clean"
    TAINTED = "tainted"
    QUARANTINED = "quarantined"
    WITNESSED = "witnessed"  # fork point with witness attestation


@dataclass
class CertNode:
    cert_id: str
    agent_id: str
    scope_hash: str
    parent_ids: list = field(default_factory=list)
    children_ids: list = field(default_factory=list)
    status: NodeStatus = NodeStatus.CLEAN
    taint_source: Optional[str] = None
    witness_id: Optional[str] = None  # witness at fork point
    depth: int = 0


class CertDAG:
    def __init__(self):
        self.nodes: dict[str, CertNode] = {}
    
    def add_node(self, cert_id: str, agent_id: str, scope_hash: str, 
                 parent_ids: list = None, witness_id: str = None) -> CertNode:
        parents = parent_ids or []
        depth = 0
        for pid in parents:
            if pid in self.nodes:
                depth = max(depth, self.nodes[pid].depth + 1)
        
        node = CertNode(
            cert_id=cert_id, agent_id=agent_id, scope_hash=scope_hash,
            parent_ids=parents, depth=depth, witness_id=witness_id
        )
        if witness_id:
            node.status = NodeStatus.WITNESSED
        
        self.nodes[cert_id] = node
        for pid in parents:
            if pid in self.nodes:
                self.nodes[pid].children_ids.append(cert_id)
        return node
    
    def taint(self, cert_id: str, reason: str = "scope_mismatch") -> list:
        """Taint a node and propagate to all descendants. Returns tainted nodes."""
        if cert_id not in self.nodes:
            return []
        
        tainted = []
        queue = [cert_id]
        visited = set()
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            
            node = self.nodes[current]
            node.status = NodeStatus.TAINTED
            node.taint_source = cert_id if current != cert_id else reason
            tainted.append(current)
            
            for child_id in node.children_ids:
                child = self.nodes[child_id]
                # Witness nodes can block propagation if they attest clean
                if child.witness_id and child.status == NodeStatus.WITNESSED:
                    child.status = NodeStatus.QUARANTINED  # needs review
                    tainted.append(child_id)
                else:
                    queue.append(child_id)
        
        return tainted
    
    def blast_radius(self, cert_id: str) -> dict:
        """Calculate blast radius without actually tainting."""
        if cert_id not in self.nodes:
            return {"reachable": 0, "blocked": 0}
        
        reachable = set()
        blocked = set()
        queue = [cert_id]
        visited = set()
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            reachable.add(current)
            
            for child_id in self.nodes[current].children_ids:
                child = self.nodes[child_id]
                if child.witness_id:
                    blocked.add(child_id)
                else:
                    queue.append(child_id)
        
        total = len(self.nodes)
        return {
            "reachable": len(reachable),
            "blocked_by_witness": len(blocked),
            "total_nodes": total,
            "blast_pct": round(len(reachable) / max(total, 1) * 100, 1),
            "mitigation_pct": round(len(blocked) / max(len(reachable) + len(blocked), 1) * 100, 1)
        }
    
    def grade(self) -> str:
        tainted = sum(1 for n in self.nodes.values() if n.status == NodeStatus.TAINTED)
        witnessed = sum(1 for n in self.nodes.values() if n.witness_id)
        total = len(self.nodes) or 1
        
        taint_pct = tainted / total
        witness_pct = witnessed / total
        
        if taint_pct == 0 and witness_pct >= 0.3:
            return "A"  # Clean with good witness coverage
        elif taint_pct == 0:
            return "B"  # Clean but low witness coverage
        elif taint_pct < 0.3 and witness_pct >= 0.2:
            return "C"  # Contained taint
        elif taint_pct < 0.5:
            return "D"  # Significant taint
        else:
            return "F"  # Cascade failure


def demo():
    dag = CertDAG()
    
    # Build a cert DAG: root → 3 branches, some with witnesses
    dag.add_node("root", "orchestrator", "scope_abc123")
    dag.add_node("cert_a", "agent_alpha", "scope_abc123", ["root"])
    dag.add_node("cert_b", "agent_beta", "scope_def456", ["root"])  # scope diverges = fork
    dag.add_node("cert_c", "agent_gamma", "scope_abc123", ["root"])
    
    # Branch A: linear chain
    dag.add_node("cert_a1", "agent_alpha", "scope_abc123", ["cert_a"])
    dag.add_node("cert_a2", "agent_alpha", "scope_abc123", ["cert_a1"])
    
    # Branch B: fork with witness
    dag.add_node("cert_b1", "agent_beta", "scope_def456", ["cert_b"], witness_id="witness_w1")
    dag.add_node("cert_b2", "agent_beta", "scope_def456", ["cert_b1"])
    
    # Branch C: merges with A
    dag.add_node("cert_c1", "agent_gamma", "scope_abc123", ["cert_c", "cert_a2"])  # merge point
    dag.add_node("cert_c2", "agent_gamma", "scope_abc123", ["cert_c1"], witness_id="witness_w2")
    
    print("=" * 60)
    print("CASCADE TAINT PROPAGATOR — Supply Chain Cert DAG")
    print("=" * 60)
    print(f"Total nodes: {len(dag.nodes)}")
    print(f"Witnessed forks: {sum(1 for n in dag.nodes.values() if n.witness_id)}")
    
    # Blast radius analysis before tainting
    print(f"\n--- Blast Radius Analysis ---")
    for node_id in ["root", "cert_a", "cert_b"]:
        radius = dag.blast_radius(node_id)
        print(f"  {node_id}: {radius['reachable']} reachable, {radius['blocked_by_witness']} blocked ({radius['blast_pct']}% blast, {radius['mitigation_pct']}% mitigated)")
    
    # Scenario 1: Taint agent_beta (branch B)
    print(f"\n--- Scenario 1: Taint cert_b (agent_beta diverged scope) ---")
    tainted = dag.taint("cert_b")
    print(f"  Tainted: {tainted}")
    print(f"  cert_b1 status: {dag.nodes['cert_b1'].status.value} (witness blocked propagation)")
    print(f"  Grade: {dag.grade()}")
    
    # Reset
    for n in dag.nodes.values():
        n.status = NodeStatus.WITNESSED if n.witness_id else NodeStatus.CLEAN
        n.taint_source = None
    
    # Scenario 2: Taint root (cascade)
    print(f"\n--- Scenario 2: Taint root (full cascade) ---")
    tainted = dag.taint("root")
    print(f"  Tainted: {tainted}")
    print(f"  Witness nodes quarantined: {[k for k,v in dag.nodes.items() if v.status == NodeStatus.QUARANTINED]}")
    print(f"  Grade: {dag.grade()}")
    
    # Key insight
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Witness nodes at forks block taint propagation.")
    print("Without witnesses: root compromise → 100% cascade.")
    print("With witnesses: quarantine at fork, review before propagating.")
    print("Baird 2026 (ICSE): SBOM graph + HGAT → 91% cascade prediction.")
    print("Same structure. Different domain. Same math.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
