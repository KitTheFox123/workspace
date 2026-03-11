#!/usr/bin/env python3
"""
bt-blame-tracer.py — Behavior tree failure propagation as cert DAG blame model.

BTs replaced FSMs because failure paths are traceable (Iovino et al 2022).
Failure propagates UP through sequence/selector nodes = blame propagates
BACK through parent_hash in cert DAGs.

Inspired by claudecraft's agent combat system + cert DAG convergence.
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NodeType(Enum):
    SEQUENCE = "sequence"   # All children must succeed (AND)
    SELECTOR = "selector"   # First child that succeeds (OR)
    ACTION = "action"       # Leaf node — actual work
    CONDITION = "condition"  # Leaf node — check


class Status(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    RUNNING = "running"


@dataclass
class BTNode:
    name: str
    node_type: NodeType
    children: list = field(default_factory=list)
    status: Status = Status.SUCCESS
    evidence_hash: str = ""
    blame_path: list = field(default_factory=list)
    
    def hash(self) -> str:
        payload = f"{self.name}:{self.node_type.value}:{self.status.value}"
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


def propagate_failure(node: BTNode) -> list:
    """Trace failure propagation path through BT (bottom-up blame)."""
    if not node.children:
        # Leaf node
        if node.status == Status.FAILURE:
            return [node.name]
        return []
    
    blame_paths = []
    
    if node.node_type == NodeType.SEQUENCE:
        # Sequence: first failure causes parent failure
        for child in node.children:
            child_blame = propagate_failure(child)
            if child_blame:
                blame_paths = child_blame + [node.name]
                break  # First failure is the cause
    
    elif node.node_type == NodeType.SELECTOR:
        # Selector: ALL must fail for parent to fail
        all_failed = all(c.status == Status.FAILURE for c in node.children)
        if all_failed:
            # All alternatives exhausted — blame the most specific
            for child in node.children:
                child_blame = propagate_failure(child)
                if child_blame:
                    blame_paths = child_blame + [node.name]
                    break
    
    return blame_paths


def build_demo_tree() -> BTNode:
    """
    Build a cert-DAG-as-BT for agent trust verification:
    
    root (sequence)
    ├── scope_check (sequence)
    │   ├── hash_match (condition) ✓
    │   └── manifest_diff (condition) ✗  ← BLAME ORIGIN
    ├── behavioral_check (selector)
    │   ├── cusum_normal (condition) ✓
    │   └── pattern_match (condition) ✓
    └── remediation (sequence)
        ├── detect (action) ✓
        ├── contain (action) ✓
        └── verify (action) ✓
    """
    # Scope check branch — has a failure
    hash_match = BTNode("hash_match", NodeType.CONDITION, status=Status.SUCCESS)
    manifest_diff = BTNode("manifest_diff", NodeType.CONDITION, status=Status.FAILURE)
    scope_check = BTNode("scope_check", NodeType.SEQUENCE, 
                         children=[hash_match, manifest_diff], status=Status.FAILURE)
    
    # Behavioral check branch — passes
    cusum = BTNode("cusum_normal", NodeType.CONDITION, status=Status.SUCCESS)
    pattern = BTNode("pattern_match", NodeType.CONDITION, status=Status.SUCCESS)
    behavioral = BTNode("behavioral_check", NodeType.SELECTOR,
                       children=[cusum, pattern], status=Status.SUCCESS)
    
    # Remediation branch — passes
    detect = BTNode("detect", NodeType.ACTION, status=Status.SUCCESS)
    contain = BTNode("contain", NodeType.ACTION, status=Status.SUCCESS)
    verify = BTNode("verify", NodeType.ACTION, status=Status.SUCCESS)
    remediation = BTNode("remediation", NodeType.SEQUENCE,
                        children=[detect, contain, verify], status=Status.SUCCESS)
    
    # Root — fails because scope_check fails (sequence = AND)
    root = BTNode("trust_verification", NodeType.SEQUENCE,
                 children=[scope_check, behavioral, remediation], status=Status.FAILURE)
    
    return root


def print_tree(node: BTNode, indent: int = 0):
    status_icon = {"success": "✓", "failure": "✗", "running": "~"}[node.status.value]
    type_label = f"[{node.node_type.value}]" if node.children else f"({node.node_type.value})"
    print(f"{'  ' * indent}{status_icon} {node.name} {type_label} [{node.hash()}]")
    for child in node.children:
        print_tree(child, indent + 1)


def demo():
    tree = build_demo_tree()
    
    print("=" * 55)
    print("BT BLAME TRACER — Cert DAG as Behavior Tree")
    print("=" * 55)
    
    print("\nTree structure:")
    print_tree(tree)
    
    # Trace blame
    blame = propagate_failure(tree)
    
    print(f"\n{'─' * 55}")
    print("BLAME PROPAGATION (bottom-up):")
    if blame:
        print(f"  Path: {' → '.join(blame)}")
        print(f"  Origin: {blame[0]}")
        print(f"  Cascade: {len(blame)} nodes affected")
        print(f"\n  BT reading: {blame[0]} FAILED")
        print(f"  → parent sequence '{blame[1]}' FAILED (AND requires all)")
        print(f"  → root sequence '{blame[-1]}' FAILED")
    
    # Cert DAG equivalent
    print(f"\n{'─' * 55}")
    print("CERT DAG EQUIVALENT:")
    print(f"  manifest_diff scope_hash MISMATCH = blame origin")
    print(f"  → scope_check cert REVOKED (parent_hash chain)")
    print(f"  → trust_verification cert SUSPENDED")
    print(f"\n  Same traversal. BT goes UP, cert DAG goes BACK.")
    print(f"  Structurally identical. Modularity is the point.")
    
    # Grade
    failed_leaves = sum(1 for n in [tree] + tree.children 
                       for c in (n.children if n.children else [n])
                       if c.status == Status.FAILURE and not c.children)
    total_leaves = 7  # hardcoded for demo
    reliability = 1 - (failed_leaves / total_leaves)
    grade = "A" if reliability >= 0.9 else "B" if reliability >= 0.8 else "C" if reliability >= 0.6 else "F"
    
    print(f"\n{'─' * 55}")
    print(f"RELIABILITY: {reliability:.1%} | Grade: {grade}")
    print(f"  {total_leaves - failed_leaves}/{total_leaves} leaf checks passed")
    print(f"  1 failure cascaded to 3 nodes (43% tree affected)")
    
    print(f"\n{'=' * 55}")
    print("KEY: BTs replaced FSMs because failure is traceable.")
    print("Cert DAGs replace flat attestation lists for the same reason.")
    print("(Iovino et al 2022, Robotics & Autonomous Systems)")
    print("=" * 55)


if __name__ == "__main__":
    demo()
