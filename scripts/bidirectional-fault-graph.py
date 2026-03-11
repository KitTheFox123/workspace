#!/usr/bin/env python3
"""
bidirectional-fault-graph.py — Failures cascade forward, remediation walks backward.

Inspired by cassian's insight: track both directions in a dependency DAG.
- Forward: failure propagation (cascade analysis)
- Backward: remediation path (root cause → fix sequence)

Power grid analogy: cascading blackout (forward) vs islanding + restoration (backward).
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NodeState(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    CONTAINED = "contained"  # isolated from cascade
    REMEDIATED = "remediated"


@dataclass
class CertNode:
    node_id: str
    agent_id: str
    scope_hash: str
    state: NodeState = NodeState.HEALTHY
    dependencies: list = field(default_factory=list)  # nodes this depends on
    dependents: list = field(default_factory=list)  # nodes that depend on this
    remediation_order: Optional[int] = None


class BidirectionalFaultGraph:
    def __init__(self):
        self.nodes: dict[str, CertNode] = {}
    
    def add_node(self, node_id: str, agent_id: str, scope_hash: str) -> CertNode:
        node = CertNode(node_id=node_id, agent_id=agent_id, scope_hash=scope_hash)
        self.nodes[node_id] = node
        return node
    
    def add_dependency(self, from_id: str, to_id: str):
        """from_id depends on to_id."""
        self.nodes[from_id].dependencies.append(to_id)
        self.nodes[to_id].dependents.append(from_id)
    
    def cascade_forward(self, failed_id: str) -> list[str]:
        """Simulate forward failure cascade from a root failure."""
        cascade = []
        queue = [failed_id]
        visited = set()
        
        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            
            node = self.nodes[nid]
            if node.state == NodeState.CONTAINED:
                continue  # containment stops cascade
            
            node.state = NodeState.FAILED
            cascade.append(nid)
            
            # Propagate to dependents
            for dep_id in node.dependents:
                if dep_id not in visited:
                    queue.append(dep_id)
        
        return cascade
    
    def find_root_cause(self, symptom_id: str) -> list[str]:
        """Walk backward from symptom to find root cause(s)."""
        path = []
        queue = [symptom_id]
        visited = set()
        roots = []
        
        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            path.append(nid)
            
            node = self.nodes[nid]
            failed_deps = [d for d in node.dependencies if self.nodes[d].state == NodeState.FAILED]
            
            if not failed_deps:
                roots.append(nid)  # no failed dependencies = root cause
            else:
                queue.extend(failed_deps)
        
        return roots
    
    def remediation_plan(self, cascade: list[str]) -> list[tuple[int, str, str]]:
        """Generate remediation order: fix roots first, then dependents.
        Returns list of (order, node_id, reason)."""
        # Find all root causes
        roots = set()
        for nid in cascade:
            node = self.nodes[nid]
            failed_deps = [d for d in node.dependencies if self.nodes[d].state == NodeState.FAILED]
            if not failed_deps:
                roots.add(nid)
        
        # BFS from roots to generate remediation order
        plan = []
        order = 0
        queue = list(roots)
        visited = set()
        
        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            
            node = self.nodes[nid]
            if nid in roots:
                reason = "ROOT CAUSE — fix first"
            else:
                reason = f"depends on {[d for d in node.dependencies if d in visited]}"
            
            plan.append((order, nid, reason))
            node.remediation_order = order
            order += 1
            
            # After fixing this, dependents can be fixed
            for dep_id in node.dependents:
                if dep_id not in visited and dep_id in cascade:
                    queue.append(dep_id)
        
        return plan
    
    def containment_analysis(self) -> dict:
        """Identify optimal containment points to minimize cascade."""
        # Nodes with most dependents = best containment points
        scores = {}
        for nid, node in self.nodes.items():
            # Count transitive dependents
            count = 0
            queue = list(node.dependents)
            visited = set()
            while queue:
                d = queue.pop(0)
                if d not in visited:
                    visited.add(d)
                    count += 1
                    queue.extend(self.nodes[d].dependents)
            scores[nid] = count
        
        return dict(sorted(scores.items(), key=lambda x: -x[1]))


def demo():
    g = BidirectionalFaultGraph()
    
    # Build dependency graph:
    # auth_service ← api_gateway ← user_service ← frontend
    #                              ← billing_service ← reporting
    g.add_node("auth", "auth_agent", "scope_auth_v1")
    g.add_node("api", "api_agent", "scope_api_v2")
    g.add_node("users", "user_agent", "scope_users_v1")
    g.add_node("billing", "billing_agent", "scope_billing_v1")
    g.add_node("frontend", "frontend_agent", "scope_fe_v3")
    g.add_node("reporting", "report_agent", "scope_report_v1")
    
    g.add_dependency("api", "auth")        # api depends on auth
    g.add_dependency("users", "api")       # users depends on api
    g.add_dependency("billing", "api")     # billing depends on api
    g.add_dependency("frontend", "users")  # frontend depends on users
    g.add_dependency("reporting", "billing")  # reporting depends on billing
    
    print("=" * 60)
    print("BIDIRECTIONAL FAULT GRAPH")
    print("Failures cascade forward. Remediation walks backward.")
    print("=" * 60)
    
    # Containment analysis BEFORE failure
    print("\n--- CONTAINMENT ANALYSIS (pre-failure) ---")
    scores = g.containment_analysis()
    for nid, count in scores.items():
        print(f"  {nid}: {count} transitive dependents {'← BEST CONTAINMENT POINT' if count == max(scores.values()) else ''}")
    
    # Simulate auth failure
    print("\n--- FORWARD CASCADE (auth fails) ---")
    cascade = g.cascade_forward("auth")
    for i, nid in enumerate(cascade):
        node = g.nodes[nid]
        print(f"  Step {i}: {nid} ({node.agent_id}) → FAILED")
    print(f"  Total cascade: {len(cascade)} nodes from 1 root failure")
    
    # Find root cause from symptom
    print("\n--- BACKWARD TRAVERSAL (from frontend symptom) ---")
    roots = g.find_root_cause("frontend")
    print(f"  Symptom: frontend")
    print(f"  Root cause(s): {roots}")
    
    # Generate remediation plan
    print("\n--- REMEDIATION PLAN (fix order) ---")
    plan = g.remediation_plan(cascade)
    for order, nid, reason in plan:
        node = g.nodes[nid]
        grade = "A" if order == 0 else "B" if order < 3 else "C"
        print(f"  [{order}] {nid} — {reason} (Grade {grade})")
    
    # Key insight
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Same graph, opposite traversal.")
    print("Forward = blame propagation. Backward = remediation path.")
    print("Containment = islanding (stop cascade at chokepoint).")
    print("cassian: 'failures cascade forward, remediation backward'")
    print("=" * 60)


if __name__ == "__main__":
    demo()
