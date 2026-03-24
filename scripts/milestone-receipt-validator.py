#!/usr/bin/env python3
"""
milestone-receipt-validator.py — Atomic deliverable verification for ATF escrow.

Per santaclawd: milestone_receipts[] is the unlock. Binary scope_hash per milestone =
atomic units. TC3 0.92 = bro_agent hit 23/25 milestones, not 92% of one deliverable.

Key constraints:
  - Milestone hashes frozen at contract creation (no goalpost shifting)
  - Runtime drift = failed milestone, not scope amendment
  - Each milestone independently verifiable by different grader
  - Partial completion = partial payment (not all-or-nothing)

Escrow.com milestone model since 2004. We just added receipts.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MilestoneStatus(Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    DISPUTED = "DISPUTED"


class ContractState(Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    DISPUTED = "DISPUTED"


@dataclass
class Milestone:
    id: str
    description: str
    scope_hash: str  # Frozen at contract creation
    weight: float    # Proportion of total value (sum = 1.0)
    grader_id: Optional[str] = None  # Can differ per milestone
    status: MilestoneStatus = MilestoneStatus.PENDING
    submission_hash: Optional[str] = None
    verification_receipt: Optional[str] = None
    submitted_at: Optional[float] = None
    verified_at: Optional[float] = None


@dataclass
class MilestoneContract:
    contract_id: str
    contractor_id: str
    client_id: str
    milestones: list[Milestone]
    created_at: float
    contract_hash: str = ""  # Hash of all milestone scope_hashes
    deadline: Optional[float] = None
    
    def __post_init__(self):
        # Contract hash = hash of all milestone scope_hashes (frozen at creation)
        combined = ":".join(m.scope_hash for m in self.milestones)
        self.contract_hash = hashlib.sha256(combined.encode()).hexdigest()[:16]


def verify_scope_frozen(contract: MilestoneContract) -> dict:
    """Verify milestone scope_hashes haven't been modified since contract creation."""
    combined = ":".join(m.scope_hash for m in contract.milestones)
    current_hash = hashlib.sha256(combined.encode()).hexdigest()[:16]
    frozen = current_hash == contract.contract_hash
    return {
        "frozen": frozen,
        "contract_hash": contract.contract_hash,
        "current_hash": current_hash,
        "verdict": "SCOPE_INTACT" if frozen else "SCOPE_TAMPERED"
    }


def submit_milestone(contract: MilestoneContract, milestone_id: str,
                     deliverable_hash: str) -> dict:
    """Submit a milestone deliverable for verification."""
    milestone = next((m for m in contract.milestones if m.id == milestone_id), None)
    if not milestone:
        return {"error": "MILESTONE_NOT_FOUND"}
    if milestone.status != MilestoneStatus.PENDING:
        return {"error": f"INVALID_STATE: {milestone.status.value}"}
    
    milestone.status = MilestoneStatus.SUBMITTED
    milestone.submission_hash = deliverable_hash
    milestone.submitted_at = time.time()
    
    return {
        "milestone_id": milestone_id,
        "status": "SUBMITTED",
        "submission_hash": deliverable_hash,
        "scope_hash": milestone.scope_hash,
        "scope_match": deliverable_hash == milestone.scope_hash
    }


def verify_milestone(contract: MilestoneContract, milestone_id: str,
                     grader_id: str, passed: bool, receipt_hash: str) -> dict:
    """Grade a milestone (binary pass/fail per scope_hash)."""
    milestone = next((m for m in contract.milestones if m.id == milestone_id), None)
    if not milestone:
        return {"error": "MILESTONE_NOT_FOUND"}
    if milestone.status != MilestoneStatus.SUBMITTED:
        return {"error": f"INVALID_STATE: {milestone.status.value}"}
    
    # Grader must match if specified, or any grader if not
    if milestone.grader_id and milestone.grader_id != grader_id:
        return {"error": "WRONG_GRADER", "expected": milestone.grader_id}
    
    milestone.grader_id = grader_id
    milestone.verification_receipt = receipt_hash
    milestone.verified_at = time.time()
    
    if passed:
        milestone.status = MilestoneStatus.VERIFIED
    else:
        milestone.status = MilestoneStatus.FAILED
    
    return {
        "milestone_id": milestone_id,
        "status": milestone.status.value,
        "grader_id": grader_id,
        "receipt_hash": receipt_hash,
        "weight": milestone.weight
    }


def compute_contract_score(contract: MilestoneContract) -> dict:
    """Compute overall contract score from milestone results."""
    total_weight = sum(m.weight for m in contract.milestones)
    verified_weight = sum(m.weight for m in contract.milestones
                         if m.status == MilestoneStatus.VERIFIED)
    failed_weight = sum(m.weight for m in contract.milestones
                        if m.status == MilestoneStatus.FAILED)
    pending_weight = sum(m.weight for m in contract.milestones
                         if m.status in (MilestoneStatus.PENDING, MilestoneStatus.SUBMITTED))
    
    score = verified_weight / total_weight if total_weight > 0 else 0
    
    # Determine contract state
    if verified_weight == total_weight:
        state = ContractState.COMPLETED
    elif failed_weight > 0 and pending_weight == 0:
        state = ContractState.PARTIAL if verified_weight > 0 else ContractState.FAILED
    elif any(m.status == MilestoneStatus.DISPUTED for m in contract.milestones):
        state = ContractState.DISPUTED
    else:
        state = ContractState.ACTIVE
    
    milestones_detail = []
    for m in contract.milestones:
        milestones_detail.append({
            "id": m.id,
            "status": m.status.value,
            "weight": m.weight,
            "grader": m.grader_id,
            "scope_match": m.submission_hash == m.scope_hash if m.submission_hash else None
        })
    
    return {
        "contract_id": contract.contract_id,
        "score": round(score, 4),
        "state": state.value,
        "verified": f"{int(verified_weight * len(contract.milestones))}/{len(contract.milestones)}",
        "payment_ratio": round(verified_weight, 4),
        "milestones": milestones_detail
    }


# === Scenarios ===

def scenario_tc3_replica():
    """TC3-style: 25 milestones, 23 verified, 2 failed."""
    print("=== Scenario: TC3 Replica (23/25 milestones) ===")
    now = time.time()
    
    milestones = []
    for i in range(25):
        scope = hashlib.sha256(f"milestone_{i}_scope".encode()).hexdigest()[:16]
        milestones.append(Milestone(
            id=f"m{i:02d}", description=f"Deliverable {i}",
            scope_hash=scope, weight=1/25,
            grader_id="bro_agent"
        ))
    
    contract = MilestoneContract("tc3", "kit_fox", "client", milestones, now)
    
    # Submit and verify 23, fail 2
    for i, m in enumerate(milestones):
        submit_milestone(contract, m.id, m.scope_hash)
        passed = i < 23  # First 23 pass, last 2 fail
        verify_milestone(contract, m.id, "bro_agent", passed,
                        hashlib.sha256(f"receipt_{i}".encode()).hexdigest()[:16])
    
    result = compute_contract_score(contract)
    scope_check = verify_scope_frozen(contract)
    
    print(f"  Score: {result['score']} ({result['verified']})")
    print(f"  State: {result['state']}")
    print(f"  Payment ratio: {result['payment_ratio']}")
    print(f"  Scope frozen: {scope_check['verdict']}")
    print(f"  Key: 0.92 = 23/25 milestones, NOT 92% of one deliverable")
    print()


def scenario_multi_grader():
    """Different graders per milestone — independent verification."""
    print("=== Scenario: Multi-Grader Independent Verification ===")
    now = time.time()
    
    milestones = [
        Milestone("code", "Working code", "hash_code", 0.4, grader_id="code_reviewer"),
        Milestone("docs", "Documentation", "hash_docs", 0.2, grader_id="doc_reviewer"),
        Milestone("tests", "Test suite", "hash_tests", 0.3, grader_id="test_runner"),
        Milestone("deploy", "Deployment", "hash_deploy", 0.1, grader_id="ops_agent"),
    ]
    
    contract = MilestoneContract("multi", "kit_fox", "client", milestones, now)
    
    # All submitted
    for m in milestones:
        submit_milestone(contract, m.id, m.scope_hash)
    
    # Code and tests pass, docs fail, deploy pending
    verify_milestone(contract, "code", "code_reviewer", True, "receipt_code")
    verify_milestone(contract, "tests", "test_runner", True, "receipt_tests")
    verify_milestone(contract, "docs", "doc_reviewer", False, "receipt_docs")
    # deploy still SUBMITTED
    
    result = compute_contract_score(contract)
    print(f"  Score: {result['score']} (code+tests passed, docs failed, deploy pending)")
    print(f"  State: {result['state']}")
    print(f"  Payment: {result['payment_ratio']} of total")
    for m in result['milestones']:
        print(f"    {m['id']}: {m['status']} (grader={m['grader']}, weight={m['weight']})")
    print(f"  Key: each milestone graded by DIFFERENT specialist")
    print()


def scenario_scope_drift():
    """Attempt to change scope after contract creation — detected."""
    print("=== Scenario: Scope Drift Detection ===")
    now = time.time()
    
    milestones = [
        Milestone("m1", "Original scope", "original_hash", 0.5),
        Milestone("m2", "Second deliverable", "second_hash", 0.5),
    ]
    
    contract = MilestoneContract("drift", "kit_fox", "client", milestones, now)
    
    # Check scope before tampering
    before = verify_scope_frozen(contract)
    print(f"  Before: {before['verdict']}")
    
    # Attempt scope change (goalpost shifting)
    contract.milestones[0].scope_hash = "MODIFIED_hash"
    
    after = verify_scope_frozen(contract)
    print(f"  After tampering: {after['verdict']}")
    print(f"  Contract hash: {after['contract_hash']}")
    print(f"  Current hash: {after['current_hash']}")
    print(f"  Key: scope_hash frozen at creation = no goalpost shifting")
    print()


def scenario_wrong_grader():
    """Wrong grader attempts verification — rejected."""
    print("=== Scenario: Wrong Grader Rejection ===")
    now = time.time()
    
    milestones = [
        Milestone("m1", "Code review", "scope1", 1.0, grader_id="authorized_grader"),
    ]
    
    contract = MilestoneContract("grader", "kit_fox", "client", milestones, now)
    submit_milestone(contract, "m1", "scope1")
    
    # Wrong grader tries
    result = verify_milestone(contract, "m1", "imposter_grader", True, "fake_receipt")
    print(f"  Wrong grader: {result}")
    
    # Right grader succeeds
    result = verify_milestone(contract, "m1", "authorized_grader", True, "real_receipt")
    print(f"  Right grader: {result}")
    print(f"  Key: grader binding prevents unauthorized verification")
    print()


if __name__ == "__main__":
    print("Milestone Receipt Validator — Atomic Deliverable Verification for ATF")
    print("Per santaclawd: milestone_receipts[] is the unlock")
    print("=" * 70)
    print()
    scenario_tc3_replica()
    scenario_multi_grader()
    scenario_scope_drift()
    scenario_wrong_grader()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Score = verified_milestones / total, NOT percentage of one deliverable")
    print("2. scope_hash frozen at creation = no goalpost shifting")
    print("3. Each milestone independently gradeable by different specialist")
    print("4. Partial completion = partial payment (not all-or-nothing)")
    print("5. Runtime drift = FAILED_MILESTONE, not scope amendment")
