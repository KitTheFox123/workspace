#!/usr/bin/env python3
"""
scope-divergence-handler.py — Partial delivery grading for ATF scope_hash divergence.

Per santaclawd: "binary pass/fail loses everyone. partial refund needs a gradient."
Per Asgaonkar & Krishnamachari (USC, arXiv 1806.08379): dual-deposit escrow.

Solution: Split scope into N milestones, hash each independently.
Grade = fraction of milestones CONFIRMED. No third-party grader needed
if milestones are hash-verifiable.

Three delivery states:
  COMPLETE    — all milestone hashes match (scope_hash = H(m1||m2||...||mN))
  PARTIAL     — K of N milestones match (gradient: K/N)
  DIVERGENT   — scope_hash changed after contract creation (dispute)
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DeliveryState(Enum):
    COMPLETE = "COMPLETE"       # All milestones verified
    PARTIAL = "PARTIAL"         # K/N milestones verified
    DIVERGENT = "DIVERGENT"     # Scope changed after contract
    DISPUTED = "DISPUTED"       # Parties disagree on milestone verification
    EXPIRED = "EXPIRED"         # Delivery window passed


class MilestoneState(Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    VERIFIED = "VERIFIED"       # Counterparty confirmed hash match
    REJECTED = "REJECTED"       # Hash mismatch
    CONTESTED = "CONTESTED"     # Parties disagree


@dataclass
class Milestone:
    id: str
    description: str
    expected_hash: str          # Hash of expected deliverable
    weight: float = 1.0         # Relative importance (default equal)
    state: MilestoneState = MilestoneState.PENDING
    delivered_hash: Optional[str] = None
    verification_timestamp: Optional[float] = None


@dataclass
class ScopeContract:
    contract_id: str
    scope_hash: str             # H(milestone_hashes) at creation
    milestones: list[Milestone]
    total_value: float
    creation_timestamp: float
    delivery_deadline: float
    
    def compute_scope_hash(self) -> str:
        """Recompute scope_hash from milestone expected_hashes."""
        combined = "||".join(m.expected_hash for m in self.milestones)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    def scope_integrity(self) -> bool:
        """Check if scope_hash matches current milestones."""
        return self.compute_scope_hash() == self.scope_hash


@dataclass
class DeliveryReport:
    contract_id: str
    state: DeliveryState
    milestones_total: int
    milestones_verified: int
    milestones_rejected: int
    milestones_pending: int
    completion_ratio: float     # weighted
    payout_ratio: float         # adjusted for disputes
    scope_integrity: bool
    details: list[dict] = field(default_factory=list)


def hash_content(content: str) -> str:
    """Hash deliverable content."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def verify_milestone(milestone: Milestone, delivered_content: str) -> MilestoneState:
    """Verify a single milestone delivery."""
    delivered_hash = hash_content(delivered_content)
    milestone.delivered_hash = delivered_hash
    
    if delivered_hash == milestone.expected_hash:
        milestone.state = MilestoneState.VERIFIED
    else:
        milestone.state = MilestoneState.REJECTED
    
    return milestone.state


def compute_delivery_grade(contract: ScopeContract) -> DeliveryReport:
    """
    Compute delivery grade for a scope contract.
    
    Payout model (per Escrow.com milestones + dual-deposit):
    - VERIFIED milestones: full weight payout
    - REJECTED milestones: 0 payout
    - CONTESTED milestones: held in escrow pending dispute
    - PENDING milestones: not yet due
    """
    total_weight = sum(m.weight for m in contract.milestones)
    verified_weight = sum(m.weight for m in contract.milestones 
                          if m.state == MilestoneState.VERIFIED)
    rejected_weight = sum(m.weight for m in contract.milestones 
                          if m.state == MilestoneState.REJECTED)
    contested_weight = sum(m.weight for m in contract.milestones 
                           if m.state == MilestoneState.CONTESTED)
    
    completion_ratio = verified_weight / total_weight if total_weight > 0 else 0
    # Payout excludes contested (held in escrow) and rejected
    payout_ratio = verified_weight / total_weight if total_weight > 0 else 0
    
    # Determine overall state
    verified_count = sum(1 for m in contract.milestones if m.state == MilestoneState.VERIFIED)
    rejected_count = sum(1 for m in contract.milestones if m.state == MilestoneState.REJECTED)
    pending_count = sum(1 for m in contract.milestones if m.state == MilestoneState.PENDING)
    contested_count = sum(1 for m in contract.milestones if m.state == MilestoneState.CONTESTED)
    
    if not contract.scope_integrity():
        state = DeliveryState.DIVERGENT
    elif contested_count > 0:
        state = DeliveryState.DISPUTED
    elif verified_count == len(contract.milestones):
        state = DeliveryState.COMPLETE
    elif verified_count > 0:
        state = DeliveryState.PARTIAL
    else:
        state = DeliveryState.EXPIRED if pending_count == len(contract.milestones) else DeliveryState.PARTIAL
    
    details = []
    for m in contract.milestones:
        details.append({
            "milestone": m.id,
            "state": m.state.value,
            "weight": m.weight,
            "hash_match": m.delivered_hash == m.expected_hash if m.delivered_hash else None,
        })
    
    return DeliveryReport(
        contract_id=contract.contract_id,
        state=state,
        milestones_total=len(contract.milestones),
        milestones_verified=verified_count,
        milestones_rejected=rejected_count,
        milestones_pending=pending_count,
        completion_ratio=round(completion_ratio, 4),
        payout_ratio=round(payout_ratio, 4),
        scope_integrity=contract.scope_integrity(),
        details=details
    )


# === Scenarios ===

def scenario_complete_delivery():
    """All milestones delivered and verified."""
    print("=== Scenario: Complete Delivery ===")
    import time
    now = time.time()
    
    content_a = "research report on trust systems"
    content_b = "working prototype code"
    content_c = "documentation and tests"
    
    milestones = [
        Milestone("m1", "Research report", hash_content(content_a), weight=0.3),
        Milestone("m2", "Prototype", hash_content(content_b), weight=0.5),
        Milestone("m3", "Documentation", hash_content(content_c), weight=0.2),
    ]
    
    contract = ScopeContract("c001", "", milestones, 1.0, now, now + 86400*30)
    contract.scope_hash = contract.compute_scope_hash()
    
    # Deliver all correctly
    verify_milestone(milestones[0], content_a)
    verify_milestone(milestones[1], content_b)
    verify_milestone(milestones[2], content_c)
    
    report = compute_delivery_grade(contract)
    print(f"  State: {report.state.value}")
    print(f"  Completion: {report.completion_ratio:.0%}")
    print(f"  Payout: {report.payout_ratio:.0%}")
    print(f"  Scope integrity: {report.scope_integrity}")
    print()


def scenario_partial_delivery():
    """2 of 3 milestones delivered correctly."""
    print("=== Scenario: Partial Delivery (2/3) ===")
    import time
    now = time.time()
    
    content_a = "research report"
    content_b = "prototype code"
    content_c = "documentation"
    
    milestones = [
        Milestone("m1", "Research", hash_content(content_a), weight=0.3),
        Milestone("m2", "Prototype", hash_content(content_b), weight=0.5),
        Milestone("m3", "Docs", hash_content(content_c), weight=0.2),
    ]
    
    contract = ScopeContract("c002", "", milestones, 1.0, now, now + 86400*30)
    contract.scope_hash = contract.compute_scope_hash()
    
    verify_milestone(milestones[0], content_a)      # Match
    verify_milestone(milestones[1], content_b)      # Match
    verify_milestone(milestones[2], "wrong docs")   # Mismatch
    
    report = compute_delivery_grade(contract)
    print(f"  State: {report.state.value}")
    print(f"  Completion: {report.completion_ratio:.0%} (weighted)")
    print(f"  Payout: {report.payout_ratio:.0%}")
    print(f"  Rejected: m3 (weight=0.2)")
    print(f"  Key: Gradient payout = 80% not 0%. Binary would lose everyone.")
    print()


def scenario_scope_divergence():
    """Scope changed after contract — milestones modified mid-delivery."""
    print("=== Scenario: Scope Divergence (Contract Tampered) ===")
    import time
    now = time.time()
    
    milestones = [
        Milestone("m1", "Original task A", hash_content("task_a"), weight=0.5),
        Milestone("m2", "Original task B", hash_content("task_b"), weight=0.5),
    ]
    
    contract = ScopeContract("c003", "", milestones, 1.0, now, now + 86400*30)
    contract.scope_hash = contract.compute_scope_hash()
    
    # Tamper: change milestone hash after contract
    milestones[1].expected_hash = hash_content("task_b_modified")
    
    verify_milestone(milestones[0], "task_a")
    verify_milestone(milestones[1], "task_b_modified")
    
    report = compute_delivery_grade(contract)
    print(f"  State: {report.state.value}")
    print(f"  Scope integrity: {report.scope_integrity} ← TAMPERED")
    print(f"  Milestones verified: {report.milestones_verified}/{report.milestones_total}")
    print(f"  Key: scope_hash mismatch = DIVERGENT regardless of milestone results")
    print(f"  Dual-deposit model: both parties lose stake on DIVERGENT (Asgaonkar 2018)")
    print()


def scenario_contested_milestone():
    """Parties disagree on milestone verification."""
    print("=== Scenario: Contested Milestone ===")
    import time
    now = time.time()
    
    milestones = [
        Milestone("m1", "Design doc", hash_content("design"), weight=0.3),
        Milestone("m2", "Implementation", hash_content("code"), weight=0.5),
        Milestone("m3", "Testing", hash_content("tests"), weight=0.2),
    ]
    
    contract = ScopeContract("c004", "", milestones, 1.0, now, now + 86400*30)
    contract.scope_hash = contract.compute_scope_hash()
    
    verify_milestone(milestones[0], "design")       # Verified
    milestones[1].state = MilestoneState.CONTESTED  # Parties disagree
    verify_milestone(milestones[2], "tests")        # Verified
    
    report = compute_delivery_grade(contract)
    print(f"  State: {report.state.value}")
    print(f"  Verified: {report.milestones_verified}/{report.milestones_total}")
    print(f"  Payout: {report.payout_ratio:.0%} (contested weight held in escrow)")
    print(f"  Key: CONTESTED ≠ REJECTED. Escrow holds 50% pending dispute resolution.")
    print(f"  Resolution: quorum grading or dual-deposit forfeit")
    print()


if __name__ == "__main__":
    print("Scope Divergence Handler — Partial Delivery Grading for ATF")
    print("Per santaclawd + Asgaonkar & Krishnamachari (USC, arXiv 1806.08379)")
    print("=" * 65)
    print()
    scenario_complete_delivery()
    scenario_partial_delivery()
    scenario_scope_divergence()
    scenario_contested_milestone()
    
    print("=" * 65)
    print("KEY INSIGHT: scope_hash = H(milestone_hashes). Split scope into N")
    print("milestones, hash each independently. Grade = weighted fraction VERIFIED.")
    print("No third-party grader needed if deliverables are hash-verifiable.")
    print("Dual-deposit: both parties stake — DIVERGENT = both forfeit.")
    print("Gradient payout > binary pass/fail. 80% delivered = 80% paid.")
