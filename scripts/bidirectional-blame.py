#!/usr/bin/env python3
"""
bidirectional-blame.py — Combine BT upward failure propagation with cert DAG downward contamination.

BT: leaf fails → propagates UP through selector/sequence → root knows which subtree broke.
Cert DAG: root scope → contamination DOWN through parent_hash → leaf knows which ancestor contaminated.
Combined: trace from ANY node in EITHER direction.

Inspired by hash's insight: "opposite direction, same traceability principle."
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NodeType(Enum):
    SELECTOR = "selector"    # OR: any child success = success
    SEQUENCE = "sequence"    # AND: all children must succeed
    ACTION = "action"        # Leaf: actual check/attestation
    DECORATOR = "decorator"  # Modifier: trust weight, timeout, retry


class Status(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    RUNNING = "running"


@dataclass
class BlameNode:
    node_id: str
    node_type: NodeType
    label: str
    parent_id: Optional[str] = None
    children: list = field(default_factory=list)
    status: Status = Status.RUNNING
    scope_hash: str = ""
    blame_source: Optional[str] = None  # who caused failure
    contaminated_by: Optional[str] = None  # upstream contamination

    def __post_init__(self):
        if not self.scope_hash:
            self.scope_hash = hashlib.sha256(f"{self.node_id}:{self.label}".encode()).hexdigest()[:12]


class BidirectionalBlameTree:
    def __init__(self):
        self.nodes: dict[str, BlameNode] = {}
        self.root_id: Optional[str] = None

    def add_node(self, node_id: str, node_type: NodeType, label: str, parent_id: str = None) -> BlameNode:
        node = BlameNode(node_id=node_id, node_type=node_type, label=label, parent_id=parent_id)
        self.nodes[node_id] = node
        if parent_id and parent_id in self.nodes:
            self.nodes[parent_id].children.append(node_id)
        if parent_id is None:
            self.root_id = node_id
        return node

    def set_leaf_status(self, node_id: str, status: Status):
        """Set a leaf node's status and trigger propagation."""
        node = self.nodes[node_id]
        node.status = status
        if status == Status.FAILURE:
            node.blame_source = node_id

    def propagate_up(self):
        """BT-style: propagate failure upward from leaves to root."""
        def _eval(node_id: str) -> Status:
            node = self.nodes[node_id]
            if not node.children:
                return node.status

            child_statuses = [_eval(c) for c in node.children]

            if node.node_type == NodeType.SEQUENCE:
                # All must succeed
                for i, s in enumerate(child_statuses):
                    if s == Status.FAILURE:
                        node.status = Status.FAILURE
                        child_node = self.nodes[node.children[i]]
                        node.blame_source = child_node.blame_source or child_node.node_id
                        return Status.FAILURE
                node.status = Status.SUCCESS
                return Status.SUCCESS

            elif node.node_type == NodeType.SELECTOR:
                # Any can succeed
                for i, s in enumerate(child_statuses):
                    if s == Status.SUCCESS:
                        node.status = Status.SUCCESS
                        return Status.SUCCESS
                node.status = Status.FAILURE
                # Blame = all children failed
                node.blame_source = ",".join(
                    self.nodes[c].blame_source or c
                    for c in node.children
                    if self.nodes[c].status == Status.FAILURE
                )
                return Status.FAILURE

            elif node.node_type == NodeType.DECORATOR:
                # Pass through first child
                node.status = child_statuses[0] if child_statuses else Status.FAILURE
                if node.status == Status.FAILURE and node.children:
                    child = self.nodes[node.children[0]]
                    node.blame_source = child.blame_source
                return node.status

            return Status.RUNNING

        if self.root_id:
            _eval(self.root_id)

    def propagate_down(self, contaminated_node_id: str):
        """Cert DAG-style: propagate contamination downward from compromised ancestor."""
        def _contaminate(node_id: str, source: str):
            node = self.nodes[node_id]
            node.contaminated_by = source
            for child_id in node.children:
                _contaminate(child_id, source)

        _contaminate(contaminated_node_id, contaminated_node_id)

    def trace_from(self, node_id: str) -> dict:
        """Bidirectional trace from any node."""
        node = self.nodes[node_id]

        # Trace UP: who does this node blame?
        up_trace = []
        current = node_id
        while current:
            n = self.nodes[current]
            up_trace.append({
                "node": n.node_id,
                "type": n.node_type.value,
                "status": n.status.value,
                "blame": n.blame_source
            })
            current = n.parent_id

        # Trace DOWN: what's contaminated below?
        down_trace = []
        def _collect(nid):
            n = self.nodes[nid]
            if n.contaminated_by:
                down_trace.append({
                    "node": n.node_id,
                    "type": n.node_type.value,
                    "contaminated_by": n.contaminated_by
                })
            for child_id in n.children:
                _collect(child_id)
        _collect(node_id)

        return {"up": up_trace, "down": down_trace}

    def grade(self) -> str:
        if not self.root_id:
            return "F"
        root = self.nodes[self.root_id]
        if root.status == Status.SUCCESS and not any(n.contaminated_by for n in self.nodes.values()):
            return "A"
        elif root.status == Status.SUCCESS:
            return "B"  # Success but some contamination
        elif root.status == Status.FAILURE:
            contaminated = sum(1 for n in self.nodes.values() if n.contaminated_by)
            if contaminated > len(self.nodes) // 2:
                return "F"
            return "C"
        return "D"


def demo():
    tree = BidirectionalBlameTree()

    # Build: root sequence → (scope_check selector, attestation sequence)
    tree.add_node("root", NodeType.SEQUENCE, "trust_evaluation")
    tree.add_node("scope", NodeType.SELECTOR, "scope_verification", "root")
    tree.add_node("attest", NodeType.SEQUENCE, "attestation_chain", "root")

    # Scope check alternatives
    tree.add_node("hash_check", NodeType.ACTION, "scope_hash_match", "scope")
    tree.add_node("manifest_check", NodeType.ACTION, "manifest_diff", "scope")

    # Attestation chain
    tree.add_node("trust_weight", NodeType.DECORATOR, "brier_weight", "attest")
    tree.add_node("liveness", NodeType.ACTION, "heartbeat_fresh", "trust_weight")
    tree.add_node("evidence", NodeType.ACTION, "evidence_gated", "attest")
    tree.add_node("remediation", NodeType.ACTION, "fix_verified", "attest")

    print("=" * 60)
    print("BIDIRECTIONAL BLAME TREE")
    print("=" * 60)

    # Scenario 1: scope hash fails but manifest passes (selector saves it)
    print("\n--- Scenario 1: Scope hash fails, manifest saves ---")
    tree.set_leaf_status("hash_check", Status.FAILURE)
    tree.set_leaf_status("manifest_check", Status.SUCCESS)
    tree.set_leaf_status("liveness", Status.SUCCESS)
    tree.set_leaf_status("evidence", Status.SUCCESS)
    tree.set_leaf_status("remediation", Status.SUCCESS)
    tree.propagate_up()

    root = tree.nodes["root"]
    print(f"  Root status: {root.status.value} | Grade: {tree.grade()}")
    print(f"  Blame: {root.blame_source or 'none'}")

    # Scenario 2: evidence fails → sequence fails → root fails
    print("\n--- Scenario 2: Evidence gate fails ---")
    tree.set_leaf_status("evidence", Status.FAILURE)
    tree.propagate_up()

    root = tree.nodes["root"]
    print(f"  Root status: {root.status.value} | Grade: {tree.grade()}")
    print(f"  Blame (upward): {root.blame_source}")

    # Trace from evidence node
    trace = tree.trace_from("evidence")
    print(f"  Trace UP from evidence:")
    for step in trace["up"]:
        print(f"    {step['node']} ({step['type']}): {step['status']}, blame={step['blame']}")

    # Scenario 3: Contamination from scope node downward
    print("\n--- Scenario 3: Scope contamination propagates down ---")
    tree.propagate_down("scope")
    trace = tree.trace_from("scope")
    print(f"  Contamination DOWN from scope:")
    for step in trace["down"]:
        print(f"    {step['node']} ({step['type']}): contaminated by {step['contaminated_by']}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"KEY INSIGHT: BT failure propagates UP (leaf→root).")
    print(f"Cert DAG contamination propagates DOWN (root→leaf).")
    print(f"Bidirectional = trace from ANY node in EITHER direction.")
    print(f"hash's insight: opposite direction, same principle.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
