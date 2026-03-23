#!/usr/bin/env python3
"""
cascading-revocation.py — X.509-style cascading revocation for ATF.

Per santaclawd: root grader revoked → what happens downstream?

Two modes (RFC 5280 §6 parallel):
  HARD_CASCADE: root compromised → all downstream REJECT
  SOFT_CASCADE: intermediate revoked → downstream DEGRADED until re-graded

Plus: MAX_DELEGATION_DEPTH = 3 (pathLenConstraint equivalent)

Usage:
    python3 cascading-revocation.py
"""

import json
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class CascadeMode(Enum):
    HARD = "HARD_CASCADE"     # genesis revocation → reject all
    SOFT = "SOFT_CASCADE"     # method change → degrade, don't reject


class RevocationVerdict(Enum):
    VALID = "VALID"
    DEGRADED = "DEGRADED"
    REJECTED = "REJECTED"
    DEPTH_EXCEEDED = "DEPTH_EXCEEDED"
    ORPHANED = "ORPHANED"     # parent revoked, no alternate path


MAX_DELEGATION_DEPTH = 3

# Distance discount for trust composition
DISTANCE_DISCOUNT = {0: 1.0, 1: 0.75, 2: 0.50, 3: 0.25}


@dataclass
class TrustNode:
    """An agent in the delegation chain."""
    agent_id: str
    genesis_hash: str
    trust_score: float
    evidence_grade: str
    is_revoked: bool = False
    revocation_type: Optional[str] = None  # "genesis" or "method"
    grader_id: Optional[str] = None  # who graded this agent
    children: list["TrustNode"] = field(default_factory=list)


class CascadingRevocation:
    """RFC 5280 §6 path validation for ATF trust chains."""

    def revoke_node(self, node: TrustNode, revocation_type: str = "genesis"):
        """Revoke a node and determine cascade effects."""
        node.is_revoked = True
        node.revocation_type = revocation_type

    def validate_chain(self, root: TrustNode, depth: int = 0) -> list[dict]:
        """Validate entire trust tree from root, applying cascade rules."""
        results = []
        self._validate_recursive(root, depth, results, parent_revoked=False, parent_type=None)
        return results

    def _validate_recursive(
        self,
        node: TrustNode,
        depth: int,
        results: list[dict],
        parent_revoked: bool,
        parent_type: Optional[str],
    ):
        # Depth check
        if depth > MAX_DELEGATION_DEPTH:
            results.append({
                "agent": node.agent_id,
                "depth": depth,
                "verdict": RevocationVerdict.DEPTH_EXCEEDED.value,
                "reason": f"depth {depth} > MAX_DELEGATION_DEPTH {MAX_DELEGATION_DEPTH}",
                "effective_trust": 0.0,
            })
            return

        # Distance-discounted trust
        discount = DISTANCE_DISCOUNT.get(depth, 0.1)
        effective_trust = node.trust_score * discount

        # Self revoked
        if node.is_revoked:
            cascade = CascadeMode.HARD if node.revocation_type == "genesis" else CascadeMode.SOFT
            results.append({
                "agent": node.agent_id,
                "depth": depth,
                "verdict": RevocationVerdict.REJECTED.value,
                "cascade_mode": cascade.value,
                "reason": f"node revoked ({node.revocation_type})",
                "effective_trust": 0.0,
            })
            # Cascade to children
            for child in node.children:
                self._validate_recursive(
                    child, depth + 1, results,
                    parent_revoked=True, parent_type=node.revocation_type,
                )
            return

        # Parent was revoked — cascade effects
        if parent_revoked:
            if parent_type == "genesis":
                # HARD_CASCADE: root compromised = everything downstream suspect
                results.append({
                    "agent": node.agent_id,
                    "depth": depth,
                    "verdict": RevocationVerdict.REJECTED.value,
                    "cascade_mode": CascadeMode.HARD.value,
                    "reason": "parent genesis revoked → hard cascade",
                    "effective_trust": 0.0,
                    "remediation": "re-grade via alternate path",
                })
            else:
                # SOFT_CASCADE: method change = degrade, don't reject
                results.append({
                    "agent": node.agent_id,
                    "depth": depth,
                    "verdict": RevocationVerdict.DEGRADED.value,
                    "cascade_mode": CascadeMode.SOFT.value,
                    "reason": "parent method revoked → soft cascade",
                    "effective_trust": effective_trust * 0.5,  # halved
                    "remediation": "re-grade with current method",
                })
            for child in node.children:
                self._validate_recursive(
                    child, depth + 1, results,
                    parent_revoked=True, parent_type=parent_type,
                )
            return

        # Normal: valid node
        results.append({
            "agent": node.agent_id,
            "depth": depth,
            "verdict": RevocationVerdict.VALID.value,
            "effective_trust": effective_trust,
            "distance_discount": discount,
        })
        for child in node.children:
            self._validate_recursive(
                child, depth + 1, results,
                parent_revoked=False, parent_type=None,
            )

    def summarize(self, results: list[dict]) -> dict:
        """Summarize chain validation."""
        verdicts = [r["verdict"] for r in results]
        return {
            "total_nodes": len(results),
            "valid": sum(1 for v in verdicts if v == "VALID"),
            "degraded": sum(1 for v in verdicts if v == "DEGRADED"),
            "rejected": sum(1 for v in verdicts if v == "REJECTED"),
            "depth_exceeded": sum(1 for v in verdicts if v == "DEPTH_EXCEEDED"),
            "chain_verdict": "BROKEN" if any(v == "REJECTED" for v in verdicts) else "VALID",
            "nodes": results,
        }


def demo():
    print("=" * 60)
    print("Cascading Revocation — RFC 5280 §6 for ATF")
    print("=" * 60)

    cr = CascadingRevocation()

    # Scenario 1: Clean chain
    print("\n--- Scenario 1: Clean 3-level delegation ---")
    root = TrustNode("alice", "gen_a", 0.95, "A")
    bob = TrustNode("bob", "gen_b", 0.85, "B", grader_id="alice")
    carol = TrustNode("carol", "gen_c", 0.80, "B", grader_id="bob")
    root.children = [bob]
    bob.children = [carol]
    results = cr.validate_chain(root)
    print(json.dumps(cr.summarize(results), indent=2))

    # Scenario 2: Root genesis revoked → HARD_CASCADE
    print("\n--- Scenario 2: Root genesis revoked → HARD_CASCADE ---")
    root2 = TrustNode("alice", "gen_a", 0.95, "A")
    bob2 = TrustNode("bob", "gen_b", 0.85, "B", grader_id="alice")
    carol2 = TrustNode("carol", "gen_c", 0.80, "B", grader_id="bob")
    root2.children = [bob2]
    bob2.children = [carol2]
    cr.revoke_node(root2, "genesis")
    results2 = cr.validate_chain(root2)
    print(json.dumps(cr.summarize(results2), indent=2))

    # Scenario 3: Intermediate method revoked → SOFT_CASCADE
    print("\n--- Scenario 3: Intermediate method change → SOFT_CASCADE ---")
    root3 = TrustNode("alice", "gen_a", 0.95, "A")
    bob3 = TrustNode("bob", "gen_b", 0.85, "B", grader_id="alice")
    carol3 = TrustNode("carol", "gen_c", 0.80, "B", grader_id="bob")
    dave3 = TrustNode("dave", "gen_d", 0.75, "C", grader_id="carol")
    root3.children = [bob3]
    bob3.children = [carol3]
    carol3.children = [dave3]
    cr.revoke_node(bob3, "method")
    results3 = cr.validate_chain(root3)
    print(json.dumps(cr.summarize(results3), indent=2))

    # Scenario 4: Depth exceeded
    print("\n--- Scenario 4: Depth exceeds MAX_DELEGATION_DEPTH=3 ---")
    root4 = TrustNode("l0", "gen_0", 0.95, "A")
    l1 = TrustNode("l1", "gen_1", 0.90, "A")
    l2 = TrustNode("l2", "gen_2", 0.85, "B")
    l3 = TrustNode("l3", "gen_3", 0.80, "B")
    l4 = TrustNode("l4", "gen_4", 0.75, "C")  # depth 4 = exceeded
    root4.children = [l1]
    l1.children = [l2]
    l2.children = [l3]
    l3.children = [l4]
    results4 = cr.validate_chain(root4)
    print(json.dumps(cr.summarize(results4), indent=2))

    print("\n" + "=" * 60)
    print("HARD_CASCADE: genesis revoked → reject all downstream")
    print("SOFT_CASCADE: method revoked → degrade, don't reject")
    print(f"MAX_DELEGATION_DEPTH: {MAX_DELEGATION_DEPTH}")
    print(f"Distance discount: {DISTANCE_DISCOUNT}")
    print("=" * 60)


if __name__ == "__main__":
    demo()
