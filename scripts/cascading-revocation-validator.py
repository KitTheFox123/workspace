#!/usr/bin/env python3
"""
cascading-revocation-validator.py — ATF cascading revocation per santaclawd.

Two modes per RFC 5280 §6:
  HARD_CASCADE: root grader revoked → all downstream REJECT
  SOFT_CASCADE: intermediate revoked → downstream DEGRADED until re-graded

MAX_DELEGATION_DEPTH = 3 (ATF-core constant, matches RFC 5280 pathLenConstraint=2 for most CAs)

Trust composition: WEIGHTED distance discount
  direct = 1.0, hop1 = 0.75, hop2 = 0.50, hop3+ = REJECT

Usage:
    python3 cascading-revocation-validator.py
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


MAX_DELEGATION_DEPTH = 3
DISTANCE_WEIGHTS = {0: 1.0, 1: 0.75, 2: 0.50}  # hop3+ = REJECT


class RevocationMode(Enum):
    HARD_CASCADE = "HARD_CASCADE"  # root revoked = everything dies
    SOFT_CASCADE = "SOFT_CASCADE"  # intermediate revoked = degraded


class NodeStatus(Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    DEGRADED = "DEGRADED"


@dataclass
class TrustNode:
    agent_id: str
    genesis_hash: str
    evidence_grade: str  # A-F
    trust_score: float
    status: NodeStatus = NodeStatus.ACTIVE
    grader_id: Optional[str] = None  # who graded this node
    depth: int = 0  # delegation depth from root


@dataclass
class DelegationChain:
    nodes: list[TrustNode] = field(default_factory=list)

    def add_node(self, node: TrustNode):
        node.depth = len(self.nodes)
        self.nodes.append(node)

    @property
    def depth(self) -> int:
        return len(self.nodes) - 1  # root = depth 0


class CascadingRevocationValidator:

    def __init__(self, max_depth: int = MAX_DELEGATION_DEPTH):
        self.max_depth = max_depth

    def _grade_value(self, grade: str) -> int:
        return {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}.get(grade, 0)

    def _degrade_grade(self, grade: str) -> str:
        degradation = {"A": "B", "B": "C", "C": "D", "D": "F", "F": "F"}
        return degradation.get(grade, "F")

    def _weighted_trust(self, base_score: float, depth: int) -> float:
        weight = DISTANCE_WEIGHTS.get(depth, 0.0)
        return base_score * weight

    def validate_chain(self, chain: DelegationChain) -> dict:
        """Validate a delegation chain with cascading revocation."""

        if chain.depth > self.max_depth:
            return {
                "verdict": "REJECTED",
                "reason": f"chain depth {chain.depth} exceeds MAX_DELEGATION_DEPTH={self.max_depth}",
                "rfc5280_parallel": f"pathLenConstraint={self.max_depth} exceeded",
            }

        results = []
        chain_broken = False
        cascade_mode = None

        for i, node in enumerate(chain.nodes):
            node_result = {
                "agent": node.agent_id,
                "depth": node.depth,
                "original_grade": node.evidence_grade,
                "original_trust": node.trust_score,
                "status": node.status.value,
            }

            # Check if this node is revoked
            if node.status == NodeStatus.REVOKED:
                if i == 0:
                    # Root revoked = HARD_CASCADE
                    cascade_mode = RevocationMode.HARD_CASCADE
                    node_result["cascade"] = "HARD_CASCADE"
                    node_result["effective_grade"] = "F"
                    node_result["effective_trust"] = 0.0
                    chain_broken = True
                else:
                    # Intermediate revoked = SOFT_CASCADE
                    cascade_mode = RevocationMode.SOFT_CASCADE
                    node_result["cascade"] = "SOFT_CASCADE"
                    node_result["effective_grade"] = "F"
                    node_result["effective_trust"] = 0.0
            elif chain_broken:
                # Downstream of hard cascade
                node_result["cascade"] = "HARD_CASCADE_DOWNSTREAM"
                node_result["effective_grade"] = "F"
                node_result["effective_trust"] = 0.0
            elif cascade_mode == RevocationMode.SOFT_CASCADE:
                # Downstream of soft cascade = degraded
                node_result["cascade"] = "SOFT_CASCADE_DOWNSTREAM"
                node_result["effective_grade"] = self._degrade_grade(node.evidence_grade)
                node_result["effective_trust"] = self._weighted_trust(node.trust_score * 0.5, node.depth)
            else:
                # Normal — apply distance weight
                node_result["cascade"] = None
                node_result["effective_grade"] = node.evidence_grade
                node_result["effective_trust"] = round(
                    self._weighted_trust(node.trust_score, node.depth), 3
                )

            results.append(node_result)

        # Chain-level verdict
        effective_grades = [r["effective_grade"] for r in results]
        min_grade = min(self._grade_value(g) for g in effective_grades)
        chain_grade = {5: "A", 4: "B", 3: "C", 2: "D", 1: "F"}.get(min_grade, "F")

        if chain_broken:
            verdict = "HARD_CASCADE_REJECT"
        elif cascade_mode == RevocationMode.SOFT_CASCADE:
            verdict = "SOFT_CASCADE_DEGRADED"
        elif chain.depth > self.max_depth:
            verdict = "DEPTH_EXCEEDED"
        else:
            verdict = "VALID"

        return {
            "verdict": verdict,
            "chain_depth": chain.depth,
            "max_depth": self.max_depth,
            "chain_grade": chain_grade,
            "cascade_mode": cascade_mode.value if cascade_mode else None,
            "nodes": results,
        }

    def compose_trust(self, chain: DelegationChain) -> dict:
        """Compute composed trust score across delegation chain."""
        if not chain.nodes:
            return {"composed_trust": 0.0, "method": "EMPTY"}

        validation = self.validate_chain(chain)
        if validation["verdict"] in ("HARD_CASCADE_REJECT", "DEPTH_EXCEEDED"):
            return {
                "composed_trust": 0.0,
                "method": "REJECTED",
                "reason": validation["verdict"],
            }

        # WEIGHTED composition
        weighted_scores = []
        for node_result in validation["nodes"]:
            weighted_scores.append(node_result["effective_trust"])

        # Final = MIN of weighted scores (BFT-safe)
        composed = min(weighted_scores) if weighted_scores else 0.0

        return {
            "composed_trust": round(composed, 3),
            "method": "WEIGHTED_MIN",
            "individual_scores": weighted_scores,
            "chain_grade": validation["chain_grade"],
        }


def demo():
    print("=" * 60)
    print("Cascading Revocation Validator — RFC 5280 for ATF")
    print("=" * 60)

    validator = CascadingRevocationValidator()

    # Scenario 1: Clean 3-hop chain
    print("\n--- Scenario 1: Clean alice→bob→carol ---")
    chain1 = DelegationChain()
    chain1.add_node(TrustNode("alice", "gen_a", "A", 0.95))
    chain1.add_node(TrustNode("bob", "gen_b", "B", 0.85))
    chain1.add_node(TrustNode("carol", "gen_c", "B", 0.80))
    print(json.dumps(validator.validate_chain(chain1), indent=2))
    print("Trust:", json.dumps(validator.compose_trust(chain1)))

    # Scenario 2: Root revoked = HARD_CASCADE
    print("\n--- Scenario 2: Root (alice) revoked → HARD_CASCADE ---")
    chain2 = DelegationChain()
    chain2.add_node(TrustNode("alice", "gen_a", "A", 0.95, NodeStatus.REVOKED))
    chain2.add_node(TrustNode("bob", "gen_b", "B", 0.85))
    chain2.add_node(TrustNode("carol", "gen_c", "A", 0.90))
    print(json.dumps(validator.validate_chain(chain2), indent=2))
    print("Trust:", json.dumps(validator.compose_trust(chain2)))

    # Scenario 3: Intermediate revoked = SOFT_CASCADE
    print("\n--- Scenario 3: Intermediate (bob) revoked → SOFT_CASCADE ---")
    chain3 = DelegationChain()
    chain3.add_node(TrustNode("alice", "gen_a", "A", 0.95))
    chain3.add_node(TrustNode("bob", "gen_b", "B", 0.85, NodeStatus.REVOKED))
    chain3.add_node(TrustNode("carol", "gen_c", "A", 0.90))
    print(json.dumps(validator.validate_chain(chain3), indent=2))
    print("Trust:", json.dumps(validator.compose_trust(chain3)))

    # Scenario 4: Exceeds MAX_DELEGATION_DEPTH
    print("\n--- Scenario 4: Depth 4 exceeds MAX=3 ---")
    chain4 = DelegationChain()
    for name in ["alpha", "beta", "gamma", "delta", "epsilon"]:
        chain4.add_node(TrustNode(name, f"gen_{name}", "A", 0.90))
    print(json.dumps(validator.validate_chain(chain4), indent=2))

    print("\n" + "=" * 60)
    print("HARD_CASCADE: root revoked → all downstream F.")
    print("SOFT_CASCADE: intermediate revoked → downstream DEGRADED.")
    print(f"MAX_DELEGATION_DEPTH={MAX_DELEGATION_DEPTH} (RFC 5280 pathLenConstraint)")
    print("Trust: WEIGHTED_MIN — distance discount + BFT-safe floor.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
