#!/usr/bin/env python3
"""
bt-fault-tracer.py — Behavior Tree fault propagation for cert DAG blame.

BTs replaced FSMs in game AI because fault logic is structural, not dispersed.
Same pattern applies to cert DAGs: node fails → parent knows which child → blame is path.

Iovino et al 2022 (Robotics & Autonomous Systems): BTs win on modularity.
claudecraft insight: shared memory corruption needs per-writer attribution.
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Status(Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    RUNNING = "RUNNING"


class NodeType(Enum):
    SEQUENCE = "sequence"      # All children must succeed (AND)
    FALLBACK = "fallback"      # First child to succeed wins (OR)
    ACTION = "action"          # Leaf node — does work
    CONDITION = "condition"    # Leaf node — checks state


@dataclass
class BTNode:
    name: str
    node_type: NodeType
    agent_id: str = ""
    children: list = field(default_factory=list)
    status: Status = Status.RUNNING
    evidence: str = ""
    node_hash: str = ""

    def __post_init__(self):
        payload = f"{self.name}:{self.node_type.value}:{self.agent_id}"
        self.node_hash = hashlib.sha256(payload.encode()).hexdigest()[:12]

    def add_child(self, child: 'BTNode') -> 'BTNode':
        self.children.append(child)
        return child


def tick(node: BTNode) -> Status:
    """Execute BT tick — propagate status up the tree."""
    if node.node_type == NodeType.ACTION:
        return node.status
    
    if node.node_type == NodeType.CONDITION:
        return node.status

    if node.node_type == NodeType.SEQUENCE:
        for child in node.children:
            result = tick(child)
            if result == Status.FAILURE:
                node.status = Status.FAILURE
                return Status.FAILURE
            if result == Status.RUNNING:
                node.status = Status.RUNNING
                return Status.RUNNING
        node.status = Status.SUCCESS
        return Status.SUCCESS

    if node.node_type == NodeType.FALLBACK:
        for child in node.children:
            result = tick(child)
            if result == Status.SUCCESS:
                node.status = Status.SUCCESS
                return Status.SUCCESS
            if result == Status.RUNNING:
                node.status = Status.RUNNING
                return Status.RUNNING
        node.status = Status.FAILURE
        return Status.FAILURE

    return Status.FAILURE


def trace_failure(node: BTNode, path: list = None) -> list:
    """Trace blame path from root to failing leaf."""
    if path is None:
        path = []
    
    current_path = path + [node]
    
    if node.node_type in (NodeType.ACTION, NodeType.CONDITION):
        if node.status == Status.FAILURE:
            return [current_path]
        return []
    
    blame_paths = []
    for child in node.children:
        if child.status == Status.FAILURE:
            blame_paths.extend(trace_failure(child, current_path))
    
    return blame_paths


def print_tree(node: BTNode, indent: int = 0):
    """Pretty-print the BT with status."""
    status_icon = {"SUCCESS": "✓", "FAILURE": "✗", "RUNNING": "⟳"}
    icon = status_icon.get(node.status.value, "?")
    agent = f" [{node.agent_id}]" if node.agent_id else ""
    evidence = f' "{node.evidence}"' if node.evidence else ""
    print(f"{'  ' * indent}{icon} {node.node_type.value}: {node.name}{agent}{evidence} ({node.node_hash})")
    for child in node.children:
        print_tree(child, indent + 1)


def demo():
    # Build a cert DAG as a behavior tree
    # Scenario: multi-agent task with cascading failure
    
    root = BTNode("task_pipeline", NodeType.SEQUENCE)
    
    # Stage 1: Scope verification (condition)
    scope_check = BTNode("verify_scope", NodeType.CONDITION, "monitor_bot")
    scope_check.status = Status.SUCCESS
    scope_check.evidence = "scope_hash matches"
    root.add_child(scope_check)
    
    # Stage 2: Parallel agent work (sequence — all must succeed)
    work = BTNode("agent_work", NodeType.SEQUENCE)
    root.add_child(work)
    
    # Agent Alpha: research (succeeds)
    alpha = BTNode("research", NodeType.ACTION, "agent_alpha")
    alpha.status = Status.SUCCESS
    alpha.evidence = "12 sources fetched"
    work.add_child(alpha)
    
    # Agent Beta: writing (FAILS — scope drift)
    beta = BTNode("writing", NodeType.ACTION, "agent_beta")
    beta.status = Status.FAILURE
    beta.evidence = "scope_hash mismatch: added unauthorized tools"
    work.add_child(beta)
    
    # Agent Gamma: review (never reached due to sequence)
    gamma = BTNode("review", NodeType.ACTION, "agent_gamma")
    gamma.status = Status.RUNNING
    gamma.evidence = ""
    work.add_child(gamma)
    
    # Stage 3: Verification (never reached)
    verify = BTNode("verify_output", NodeType.CONDITION, "audit_bot")
    verify.status = Status.RUNNING
    root.add_child(verify)
    
    # Tick the tree
    result = tick(root)
    
    print("=" * 60)
    print("BT FAULT TRACER — Cert DAG as Behavior Tree")
    print("=" * 60)
    print()
    print_tree(root)
    
    print(f"\nPipeline result: {result.value}")
    
    # Trace blame
    blame_paths = trace_failure(root)
    
    print(f"\n{'─' * 50}")
    print(f"BLAME TRACE ({len(blame_paths)} failure path(s)):")
    for i, path in enumerate(blame_paths):
        chain = " → ".join(f"{n.name}({n.node_hash})" for n in path)
        failing = path[-1]
        print(f"  Path {i+1}: {chain}")
        print(f"  Blame: {failing.agent_id} | Evidence: {failing.evidence}")
    
    # Compare with FSM approach
    print(f"\n{'─' * 50}")
    print("BT vs FSM for blame attribution:")
    print(f"  BT:  {len(blame_paths)} deterministic path(s), O(depth) traversal")
    print(f"  FSM: O(states × transitions) search, non-deterministic")
    print(f"  BT blame is STRUCTURAL — encoded in tree shape")
    print(f"  FSM blame is ARCHAEOLOGICAL — reconstruct from logs")
    
    # Grade
    total_leaves = sum(1 for _ in _leaves(root))
    failed_leaves = sum(1 for _ in _leaves(root) if _.status == Status.FAILURE)
    success_leaves = sum(1 for _ in _leaves(root) if _.status == Status.SUCCESS)
    
    if failed_leaves == 0:
        grade = "A"
    elif success_leaves > failed_leaves:
        grade = "B"
    elif failed_leaves == 1:
        grade = "C"
    else:
        grade = "F"
    
    print(f"\n{'─' * 50}")
    print(f"Pipeline Grade: {grade}")
    print(f"  Leaves: {total_leaves} total, {success_leaves} success, {failed_leaves} failed")
    print(f"  Blame deterministic: YES")
    print(f"  Remediation path: {blame_paths[0][-1].name if blame_paths else 'N/A'}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: BTs replaced FSMs because fault propagation")
    print("is structural, not dispersed. Cert DAGs = BTs for trust.")
    print("Node fails → parent knows which child → blame is a path.")
    print("(Iovino et al 2022, claudecraft's agent coordination)")
    print("=" * 60)


def _leaves(node):
    if node.node_type in (NodeType.ACTION, NodeType.CONDITION):
        yield node
    for child in node.children:
        yield from _leaves(child)


if __name__ == "__main__":
    demo()
