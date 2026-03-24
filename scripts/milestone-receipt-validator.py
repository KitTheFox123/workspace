#!/usr/bin/env python3
"""
milestone-receipt-validator.py — Atomic milestone verification for ATF contracts.

Per santaclawd: milestone_receipts[] = atomic units. Binary scope_hash per milestone.
TC3 proved it: 0.92 = 23/25 milestones, not 92% of one deliverable.

Key constraints:
  - Milestone hashes frozen at contract creation (no runtime scope creep)
  - Runtime drift = failed milestone, not scope amendment
  - Partial delivery = partial payment (proportional to milestones hit)
  - Each milestone independently verifiable

Per CAB Forum SC-081v3 (April 2025): governance via two voter classes.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MilestoneStatus(Enum):
    PENDING = "PENDING"          # Not yet attempted
    DELIVERED = "DELIVERED"      # Deliverable submitted
    VERIFIED = "VERIFIED"        # Third-party verified
    FAILED = "FAILED"            # Verification failed
    DRIFTED = "DRIFTED"          # Scope hash mismatch at delivery
    DISPUTED = "DISPUTED"        # Under dispute


class ContractGrade(Enum):
    A = "A"  # >=0.90
    B = "B"  # >=0.75
    C = "C"  # >=0.50
    D = "D"  # >=0.25
    F = "F"  # <0.25


@dataclass
class Milestone:
    id: str
    description: str
    scope_hash: str          # Frozen at contract creation
    weight: float = 1.0       # Relative weight (default equal)
    status: MilestoneStatus = MilestoneStatus.PENDING
    delivery_hash: Optional[str] = None
    verifier_id: Optional[str] = None
    verified_at: Optional[float] = None
    grade: Optional[str] = None  # A-F from verifier


@dataclass
class Contract:
    contract_id: str
    creator_id: str
    executor_id: str
    milestones: list[Milestone]
    created_at: float
    contract_hash: str = ""     # Hash of all milestone scope_hashes
    frozen: bool = True          # Scope frozen at creation
    
    def __post_init__(self):
        # Contract hash = hash of ordered milestone scope_hashes
        concat = ":".join(m.scope_hash for m in self.milestones)
        self.contract_hash = hashlib.sha256(concat.encode()).hexdigest()[:16]


def verify_scope_integrity(contract: Contract, milestone_id: str, 
                            delivery_hash: str) -> dict:
    """
    Verify delivery against frozen scope hash.
    Drift = delivery doesn't match scope. NOT a scope amendment.
    """
    milestone = next((m for m in contract.milestones if m.id == milestone_id), None)
    if not milestone:
        return {"status": "ERROR", "reason": "milestone_not_found"}
    
    if not contract.frozen:
        return {"status": "ERROR", "reason": "contract_not_frozen"}
    
    # Check if delivery matches scope
    scope_match = delivery_hash == milestone.scope_hash
    
    if scope_match:
        milestone.status = MilestoneStatus.DELIVERED
        milestone.delivery_hash = delivery_hash
        return {
            "status": "DELIVERED",
            "milestone_id": milestone_id,
            "scope_match": True,
            "note": "delivery matches frozen scope"
        }
    else:
        milestone.status = MilestoneStatus.DRIFTED
        milestone.delivery_hash = delivery_hash
        return {
            "status": "DRIFTED",
            "milestone_id": milestone_id,
            "scope_match": False,
            "expected_hash": milestone.scope_hash,
            "actual_hash": delivery_hash,
            "note": "runtime drift detected — failed milestone, not scope amendment"
        }


def grade_milestone(contract: Contract, milestone_id: str,
                    verifier_id: str, grade: str) -> dict:
    """Third-party grades a delivered milestone."""
    milestone = next((m for m in contract.milestones if m.id == milestone_id), None)
    if not milestone:
        return {"status": "ERROR", "reason": "milestone_not_found"}
    
    if milestone.status not in (MilestoneStatus.DELIVERED, MilestoneStatus.DRIFTED):
        return {"status": "ERROR", "reason": f"cannot grade {milestone.status.value}"}
    
    # Axiom 1: verifier != executor
    if verifier_id == contract.executor_id:
        return {"status": "REJECTED", "reason": "axiom_1_violation: self-grading"}
    
    milestone.verifier_id = verifier_id
    milestone.grade = grade
    milestone.verified_at = time.time()
    
    if milestone.status == MilestoneStatus.DRIFTED:
        milestone.status = MilestoneStatus.FAILED
        return {
            "status": "FAILED",
            "reason": "drifted deliverable graded — scope mismatch persists",
            "grade": grade
        }
    
    if grade in ("A", "B", "C"):
        milestone.status = MilestoneStatus.VERIFIED
    else:
        milestone.status = MilestoneStatus.FAILED
    
    return {
        "status": milestone.status.value,
        "milestone_id": milestone_id,
        "grade": grade,
        "verifier": verifier_id
    }


def compute_contract_score(contract: Contract) -> dict:
    """
    Compute contract score as milestone completion ratio.
    TC3 model: 23/25 = 0.92, not 92% of one blob.
    """
    total_weight = sum(m.weight for m in contract.milestones)
    verified_weight = sum(m.weight for m in contract.milestones 
                          if m.status == MilestoneStatus.VERIFIED)
    
    score = verified_weight / total_weight if total_weight > 0 else 0
    
    # Grade assignment
    if score >= 0.90:
        grade = ContractGrade.A
    elif score >= 0.75:
        grade = ContractGrade.B
    elif score >= 0.50:
        grade = ContractGrade.C
    elif score >= 0.25:
        grade = ContractGrade.D
    else:
        grade = ContractGrade.F
    
    status_counts = {}
    for m in contract.milestones:
        s = m.status.value
        status_counts[s] = status_counts.get(s, 0) + 1
    
    return {
        "contract_id": contract.contract_id,
        "contract_hash": contract.contract_hash,
        "score": round(score, 4),
        "grade": grade.value,
        "milestones_total": len(contract.milestones),
        "milestones_verified": sum(1 for m in contract.milestones 
                                    if m.status == MilestoneStatus.VERIFIED),
        "status_distribution": status_counts,
        "partial_payment_ratio": round(score, 4)
    }


def detect_scope_creep(contract: Contract) -> dict:
    """Detect if someone tried to amend scope at runtime."""
    drifted = [m for m in contract.milestones if m.status == MilestoneStatus.DRIFTED]
    failed_scope = [m for m in contract.milestones 
                     if m.status == MilestoneStatus.FAILED and m.delivery_hash != m.scope_hash]
    
    return {
        "scope_frozen": contract.frozen,
        "drifted_milestones": len(drifted),
        "failed_scope_mismatches": len(failed_scope),
        "integrity": "CLEAN" if not drifted and not failed_scope else "SCOPE_DRIFT_DETECTED",
        "note": "drift = failed milestone, NOT scope amendment" if drifted else "no drift"
    }


# === Scenarios ===

def scenario_tc3_model():
    """TC3 reproduction: 23/25 milestones verified."""
    print("=== Scenario: TC3 Model (23/25 Milestones) ===")
    now = time.time()
    
    milestones = []
    for i in range(25):
        scope = hashlib.sha256(f"tc3_milestone_{i}".encode()).hexdigest()[:16]
        milestones.append(Milestone(id=f"m{i:02d}", description=f"Section {i+1}", 
                                     scope_hash=scope))
    
    contract = Contract("tc3", "kit_fox", "bro_agent", milestones, now)
    
    # Deliver and verify 23/25
    for i in range(25):
        scope = milestones[i].scope_hash
        if i < 23:  # First 23 match scope
            verify_scope_integrity(contract, f"m{i:02d}", scope)
            grade_milestone(contract, f"m{i:02d}", "independent_grader", "A")
        elif i == 23:  # m23 drifted
            verify_scope_integrity(contract, f"m{i:02d}", "wrong_hash_aaa")
            grade_milestone(contract, f"m{i:02d}", "independent_grader", "D")
        else:  # m24 not delivered
            pass
    
    result = compute_contract_score(contract)
    print(f"  Score: {result['score']} (Grade {result['grade']})")
    print(f"  Verified: {result['milestones_verified']}/{result['milestones_total']}")
    print(f"  Status: {result['status_distribution']}")
    print(f"  Partial payment: {result['partial_payment_ratio']}")
    
    drift = detect_scope_creep(contract)
    print(f"  Scope integrity: {drift['integrity']}")
    print()


def scenario_full_delivery():
    """Perfect delivery — all milestones verified."""
    print("=== Scenario: Full Delivery (5/5) ===")
    now = time.time()
    
    milestones = []
    for i in range(5):
        scope = hashlib.sha256(f"full_{i}".encode()).hexdigest()[:16]
        milestones.append(Milestone(id=f"m{i}", description=f"Task {i+1}",
                                     scope_hash=scope))
    
    contract = Contract("full", "alice", "bob", milestones, now)
    
    for i in range(5):
        verify_scope_integrity(contract, f"m{i}", milestones[i].scope_hash)
        grade_milestone(contract, f"m{i}", "carol_verifier", "A")
    
    result = compute_contract_score(contract)
    print(f"  Score: {result['score']} (Grade {result['grade']})")
    print(f"  Contract hash: {contract.contract_hash}")
    print()


def scenario_scope_drift():
    """Executor tries to deliver different scope — caught."""
    print("=== Scenario: Scope Drift Attack ===")
    now = time.time()
    
    milestones = [
        Milestone("m0", "Write report", hashlib.sha256(b"report_v1").hexdigest()[:16]),
        Milestone("m1", "Build tool", hashlib.sha256(b"tool_v1").hexdigest()[:16]),
        Milestone("m2", "Deploy", hashlib.sha256(b"deploy_v1").hexdigest()[:16]),
    ]
    
    contract = Contract("drift", "client", "executor", milestones, now)
    
    # m0: correct delivery
    r0 = verify_scope_integrity(contract, "m0", milestones[0].scope_hash)
    print(f"  m0: {r0['status']} (scope match: {r0.get('scope_match')})")
    
    # m1: executor delivers DIFFERENT scope (drift)
    r1 = verify_scope_integrity(contract, "m1", "totally_different_hash")
    print(f"  m1: {r1['status']} — {r1.get('note')}")
    
    # m2: correct
    r2 = verify_scope_integrity(contract, "m2", milestones[2].scope_hash)
    print(f"  m2: {r2['status']}")
    
    # Grade all
    grade_milestone(contract, "m0", "verifier", "A")
    grade_milestone(contract, "m1", "verifier", "B")  # Grades drift → FAILED
    grade_milestone(contract, "m2", "verifier", "A")
    
    result = compute_contract_score(contract)
    print(f"  Score: {result['score']} (Grade {result['grade']})")
    print(f"  Drift detected: {detect_scope_creep(contract)['integrity']}")
    print()


def scenario_self_grading_blocked():
    """Executor tries to grade own milestone — axiom 1 blocks."""
    print("=== Scenario: Self-Grading Blocked (Axiom 1) ===")
    now = time.time()
    
    milestones = [Milestone("m0", "Task", hashlib.sha256(b"task").hexdigest()[:16])]
    contract = Contract("selfgrade", "client", "executor", milestones, now)
    
    verify_scope_integrity(contract, "m0", milestones[0].scope_hash)
    result = grade_milestone(contract, "m0", "executor", "A")  # Self-grade attempt
    print(f"  Self-grade attempt: {result['status']} — {result.get('reason')}")
    
    result2 = grade_milestone(contract, "m0", "independent_verifier", "B")
    print(f"  Independent grade: {result2['status']} — Grade {result2['grade']}")
    print()


def scenario_weighted_milestones():
    """Unequal weight milestones — critical task matters more."""
    print("=== Scenario: Weighted Milestones ===")
    now = time.time()
    
    milestones = [
        Milestone("m0", "Security audit", hashlib.sha256(b"audit").hexdigest()[:16], weight=3.0),
        Milestone("m1", "Documentation", hashlib.sha256(b"docs").hexdigest()[:16], weight=1.0),
        Milestone("m2", "Tests", hashlib.sha256(b"tests").hexdigest()[:16], weight=2.0),
    ]
    
    contract = Contract("weighted", "client", "executor", milestones, now)
    
    # Deliver all, but security audit fails
    verify_scope_integrity(contract, "m0", milestones[0].scope_hash)
    grade_milestone(contract, "m0", "verifier", "D")  # Failed
    
    verify_scope_integrity(contract, "m1", milestones[1].scope_hash)
    grade_milestone(contract, "m1", "verifier", "A")
    
    verify_scope_integrity(contract, "m2", milestones[2].scope_hash)
    grade_milestone(contract, "m2", "verifier", "A")
    
    result = compute_contract_score(contract)
    print(f"  Score: {result['score']} (Grade {result['grade']})")
    print(f"  Security audit (weight 3.0) failed → score only {result['score']}")
    print(f"  Docs + Tests passed but weighted less")
    print()


if __name__ == "__main__":
    print("Milestone Receipt Validator — Atomic Verification for ATF Contracts")
    print("Per santaclawd: milestone_receipts[] = atomic units")
    print("Per CAB Forum SC-081v3: governance via two voter classes")
    print("=" * 70)
    print()
    scenario_tc3_model()
    scenario_full_delivery()
    scenario_scope_drift()
    scenario_self_grading_blocked()
    scenario_weighted_milestones()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Milestones frozen at creation — no runtime scope creep")
    print("2. Drift = failed milestone, NOT scope amendment")  
    print("3. Partial delivery = partial payment (proportional)")
    print("4. Self-grading blocked by Axiom 1")
    print("5. Weight lets critical milestones dominate score")
