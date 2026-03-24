#!/usr/bin/env python3
"""
scope-hash-merkle.py — Merkle-tree scope hashing for partial delivery attestation.

Per santaclawd: "scope_hash divergence is the unsolved ATF problem."
Binary pass/fail loses everyone. Partial delivery needs a gradient.

Solution: scope_hash_v2 = merkle root of deliverable leaves.
Each leaf = independently attestable. Partial = proportion verified.

Per Melnikov et al. (arXiv 2409.10727): VRF-based witness selection
for grader committees. No central committee, local selection.
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LeafStatus(Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    DISPUTED = "DISPUTED"
    EXPIRED = "EXPIRED"


class DeliveryGrade(Enum):
    FULL = "FULL"          # 100% leaves verified
    SUBSTANTIAL = "SUBSTANTIAL"  # ≥75% verified, 0 disputed
    PARTIAL = "PARTIAL"    # ≥50% verified
    INSUFFICIENT = "INSUFFICIENT"  # <50% verified
    FAILED = "FAILED"      # any disputed leaf OR <25% verified


@dataclass
class DeliverableLeaf:
    """Single attestable unit of work."""
    leaf_id: str
    description: str
    hash: str  # SHA-256 of deliverable content
    weight: float = 1.0  # relative importance (default equal)
    status: LeafStatus = LeafStatus.PENDING
    attester_id: Optional[str] = None
    attestation_hash: Optional[str] = None


@dataclass 
class ScopeTree:
    """Merkle tree of deliverable leaves."""
    contract_id: str
    leaves: list[DeliverableLeaf]
    root_hash: str = ""
    locked_at: Optional[float] = None
    
    def __post_init__(self):
        self.root_hash = self._compute_root()
    
    def _compute_root(self) -> str:
        """Compute merkle root from leaf hashes."""
        if not self.leaves:
            return hashlib.sha256(b"empty").hexdigest()[:16]
        
        hashes = [leaf.hash for leaf in self.leaves]
        while len(hashes) > 1:
            if len(hashes) % 2:
                hashes.append(hashes[-1])  # duplicate last for odd
            hashes = [
                hashlib.sha256(f"{hashes[i]}:{hashes[i+1]}".encode()).hexdigest()[:16]
                for i in range(0, len(hashes), 2)
            ]
        return hashes[0]
    
    def inclusion_proof(self, leaf_idx: int) -> list[str]:
        """Generate merkle inclusion proof for a leaf."""
        hashes = [leaf.hash for leaf in self.leaves]
        proof = []
        idx = leaf_idx
        while len(hashes) > 1:
            if len(hashes) % 2:
                hashes.append(hashes[-1])
            sibling = idx ^ 1  # XOR to get sibling
            if sibling < len(hashes):
                proof.append(hashes[sibling])
            idx //= 2
            hashes = [
                hashlib.sha256(f"{hashes[i]}:{hashes[i+1]}".encode()).hexdigest()[:16]
                for i in range(0, len(hashes), 2)
            ]
        return proof


@dataclass
class DeliveryAttestation:
    """Third-party attestation of partial delivery."""
    contract_id: str
    scope_root: str
    leaves_total: int
    leaves_verified: int
    leaves_disputed: int
    weighted_completion: float
    grade: DeliveryGrade
    grader_id: str
    grader_stake: float  # skin in the game
    leaf_attestations: dict  # leaf_id -> status


def compute_weighted_completion(tree: ScopeTree) -> float:
    """Weighted completion ratio."""
    total_weight = sum(l.weight for l in tree.leaves)
    verified_weight = sum(l.weight for l in tree.leaves if l.status == LeafStatus.VERIFIED)
    return round(verified_weight / total_weight, 4) if total_weight > 0 else 0.0


def assign_delivery_grade(tree: ScopeTree) -> DeliveryGrade:
    """Assign delivery grade based on leaf status distribution."""
    completion = compute_weighted_completion(tree)
    disputed = any(l.status == LeafStatus.DISPUTED for l in tree.leaves)
    
    if disputed:
        return DeliveryGrade.FAILED
    elif completion >= 1.0:
        return DeliveryGrade.FULL
    elif completion >= 0.75:
        return DeliveryGrade.SUBSTANTIAL
    elif completion >= 0.50:
        return DeliveryGrade.PARTIAL
    elif completion >= 0.25:
        return DeliveryGrade.INSUFFICIENT
    else:
        return DeliveryGrade.FAILED


def compute_refund_ratio(grade: DeliveryGrade, completion: float) -> float:
    """
    Refund ratio based on delivery grade.
    FULL = 0% refund, SUBSTANTIAL = 0-25%, PARTIAL = 25-50%, etc.
    """
    ratios = {
        DeliveryGrade.FULL: 0.0,
        DeliveryGrade.SUBSTANTIAL: round(1.0 - completion, 4),
        DeliveryGrade.PARTIAL: round(1.0 - completion, 4),
        DeliveryGrade.INSUFFICIENT: round(1.0 - completion * 0.5, 4),  # penalty
        DeliveryGrade.FAILED: 1.0,  # full refund
    }
    return ratios.get(grade, 1.0)


def attest_delivery(tree: ScopeTree, grader_id: str, grader_stake: float) -> DeliveryAttestation:
    """Generate delivery attestation from scope tree state."""
    completion = compute_weighted_completion(tree)
    grade = assign_delivery_grade(tree)
    
    leaf_attestations = {
        l.leaf_id: l.status.value for l in tree.leaves
    }
    
    return DeliveryAttestation(
        contract_id=tree.contract_id,
        scope_root=tree.root_hash,
        leaves_total=len(tree.leaves),
        leaves_verified=sum(1 for l in tree.leaves if l.status == LeafStatus.VERIFIED),
        leaves_disputed=sum(1 for l in tree.leaves if l.status == LeafStatus.DISPUTED),
        weighted_completion=completion,
        grade=grade,
        grader_id=grader_id,
        grader_stake=grader_stake,
        leaf_attestations=leaf_attestations
    )


# === Scenarios ===

def scenario_full_delivery():
    """All deliverables verified — FULL grade."""
    print("=== Scenario: Full Delivery ===")
    leaves = [
        DeliverableLeaf("d1", "Research section", hashlib.sha256(b"research").hexdigest()[:16], 2.0, LeafStatus.VERIFIED),
        DeliverableLeaf("d2", "Analysis section", hashlib.sha256(b"analysis").hexdigest()[:16], 1.5, LeafStatus.VERIFIED),
        DeliverableLeaf("d3", "Conclusion", hashlib.sha256(b"conclusion").hexdigest()[:16], 1.0, LeafStatus.VERIFIED),
    ]
    tree = ScopeTree("contract_001", leaves)
    att = attest_delivery(tree, "bro_agent", 0.01)
    refund = compute_refund_ratio(att.grade, att.weighted_completion)
    print(f"  Completion: {att.weighted_completion:.0%}, Grade: {att.grade.value}, Refund: {refund:.0%}")
    print(f"  Root hash: {tree.root_hash}")
    print()


def scenario_partial_delivery():
    """Some deliverables pending — PARTIAL grade with proportional refund."""
    print("=== Scenario: Partial Delivery (TC3-like) ===")
    leaves = [
        DeliverableLeaf("d1", "5 sections", hashlib.sha256(b"sections").hexdigest()[:16], 3.0, LeafStatus.VERIFIED),
        DeliverableLeaf("d2", "12 sources", hashlib.sha256(b"sources").hexdigest()[:16], 2.0, LeafStatus.VERIFIED),
        DeliverableLeaf("d3", "Counter-thesis", hashlib.sha256(b"counter").hexdigest()[:16], 2.0, LeafStatus.PENDING),
        DeliverableLeaf("d4", "7500 chars", hashlib.sha256(b"length").hexdigest()[:16], 1.0, LeafStatus.VERIFIED),
    ]
    tree = ScopeTree("contract_tc3", leaves)
    att = attest_delivery(tree, "bro_agent", 0.01)
    refund = compute_refund_ratio(att.grade, att.weighted_completion)
    print(f"  Verified: {att.leaves_verified}/{att.leaves_total}")
    print(f"  Weighted completion: {att.weighted_completion:.0%}, Grade: {att.grade.value}")
    print(f"  Refund ratio: {refund:.0%} (proportional to undelivered weight)")
    proof = tree.inclusion_proof(0)
    print(f"  Inclusion proof for leaf 0: {proof}")
    print()


def scenario_disputed_leaf():
    """One leaf disputed — FAILED grade, full refund."""
    print("=== Scenario: Disputed Leaf ===")
    leaves = [
        DeliverableLeaf("d1", "Code", hashlib.sha256(b"code").hexdigest()[:16], 3.0, LeafStatus.VERIFIED),
        DeliverableLeaf("d2", "Tests", hashlib.sha256(b"tests").hexdigest()[:16], 2.0, LeafStatus.DISPUTED),
        DeliverableLeaf("d3", "Docs", hashlib.sha256(b"docs").hexdigest()[:16], 1.0, LeafStatus.VERIFIED),
    ]
    tree = ScopeTree("contract_dispute", leaves)
    att = attest_delivery(tree, "grader_neutral", 0.005)
    refund = compute_refund_ratio(att.grade, att.weighted_completion)
    print(f"  Verified: {att.leaves_verified}/{att.leaves_total}, Disputed: {att.leaves_disputed}")
    print(f"  Grade: {att.grade.value} (any dispute = FAILED)")
    print(f"  Refund: {refund:.0%}")
    print()


def scenario_weighted_deliverables():
    """Unequal weights — critical deliverable missing tanks completion."""
    print("=== Scenario: Weighted Deliverables (Critical Missing) ===")
    leaves = [
        DeliverableLeaf("d1", "MVP feature", hashlib.sha256(b"mvp").hexdigest()[:16], 5.0, LeafStatus.PENDING),
        DeliverableLeaf("d2", "Nice-to-have A", hashlib.sha256(b"nice_a").hexdigest()[:16], 0.5, LeafStatus.VERIFIED),
        DeliverableLeaf("d3", "Nice-to-have B", hashlib.sha256(b"nice_b").hexdigest()[:16], 0.5, LeafStatus.VERIFIED),
        DeliverableLeaf("d4", "Documentation", hashlib.sha256(b"docs2").hexdigest()[:16], 1.0, LeafStatus.VERIFIED),
    ]
    tree = ScopeTree("contract_weighted", leaves)
    att = attest_delivery(tree, "grader_x", 0.02)
    refund = compute_refund_ratio(att.grade, att.weighted_completion)
    print(f"  Leaf count verified: {att.leaves_verified}/{att.leaves_total} (3 of 4 done!)")
    print(f"  BUT weighted completion: {att.weighted_completion:.0%} (MVP weight=5.0 missing)")
    print(f"  Grade: {att.grade.value}, Refund: {refund:.0%}")
    print(f"  Lesson: count ≠ completion when weights differ")
    print()


def scenario_scope_drift():
    """Scope changes after escrow lock — root hash diverges."""
    print("=== Scenario: Scope Drift Detection ===")
    original_leaves = [
        DeliverableLeaf("d1", "Feature A", hashlib.sha256(b"feat_a").hexdigest()[:16]),
        DeliverableLeaf("d2", "Feature B", hashlib.sha256(b"feat_b").hexdigest()[:16]),
    ]
    original_tree = ScopeTree("contract_drift", original_leaves)
    
    # Scope drifts: Feature B replaced with Feature C
    drifted_leaves = [
        DeliverableLeaf("d1", "Feature A", hashlib.sha256(b"feat_a").hexdigest()[:16], 1.0, LeafStatus.VERIFIED),
        DeliverableLeaf("d3", "Feature C", hashlib.sha256(b"feat_c").hexdigest()[:16], 1.0, LeafStatus.VERIFIED),
    ]
    drifted_tree = ScopeTree("contract_drift", drifted_leaves)
    
    match = original_tree.root_hash == drifted_tree.root_hash
    print(f"  Original root: {original_tree.root_hash}")
    print(f"  Drifted root:  {drifted_tree.root_hash}")
    print(f"  Match: {match} ← SCOPE DRIFT DETECTED")
    print(f"  Escrow locked original hash. Delivery against drifted scope = REJECTED.")
    print()


if __name__ == "__main__":
    print("Scope-Hash Merkle — Partial Delivery Attestation for ATF")
    print("Per santaclawd: 'scope_hash divergence is the unsolved ATF problem'")
    print("=" * 70)
    print()
    scenario_full_delivery()
    scenario_partial_delivery()
    scenario_disputed_leaf()
    scenario_weighted_deliverables()
    scenario_scope_drift()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. scope_hash_v2 = merkle root of deliverable leaves")
    print("2. Each leaf independently attestable with inclusion proof")
    print("3. Weighted completion = proportional refund (not binary)")
    print("4. Any disputed leaf = FAILED (zero tolerance)")
    print("5. Scope drift detected by root hash divergence from escrow lock")
    print("6. Grader stake = skin in the game (Melnikov et al. sortition)")
