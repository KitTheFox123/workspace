#!/usr/bin/env python3
"""
milestone-receipt-validator.py — Atomic milestone verification for ATF contracts.

Per santaclawd: milestone_receipts[] = atomic units. TC3 0.92 = 23/25 milestones,
not 92% of one deliverable. scope_hash frozen at contract creation.

Key insight: per-milestone grading > whole-scope grading.
- Each milestone has a binary scope_hash match (pass/fail)
- Runtime drift = failed milestone, not scope amendment
- Contract score = milestones_passed / milestones_total
- Partial delivery is MEASURABLE not ESTIMATED
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MilestoneStatus(Enum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    DISPUTED = "DISPUTED"
    EXPIRED = "EXPIRED"


class ContractGrade(Enum):
    A = "A"  # >= 0.90
    B = "B"  # >= 0.75
    C = "C"  # >= 0.60
    D = "D"  # >= 0.40
    F = "F"  # < 0.40


@dataclass
class Milestone:
    id: str
    description: str
    scope_hash: str  # SHA-256 of expected deliverable spec
    deadline_utc: float
    weight: float = 1.0  # Default equal weight
    
    # Filled during verification
    status: MilestoneStatus = MilestoneStatus.PENDING
    delivery_hash: Optional[str] = None
    verified_at: Optional[float] = None
    grader_id: Optional[str] = None
    evidence_grade: Optional[str] = None


@dataclass
class Contract:
    contract_id: str
    agent_id: str
    counterparty_id: str
    milestones: list
    created_at: float
    contract_hash: str = ""  # Hash of all milestone scope_hashes at creation
    
    def __post_init__(self):
        # Freeze scope at creation
        scope_data = "|".join(m.scope_hash for m in self.milestones)
        self.contract_hash = hashlib.sha256(scope_data.encode()).hexdigest()[:16]


@dataclass
class MilestoneReceipt:
    milestone_id: str
    contract_id: str
    scope_hash: str  # From contract (frozen)
    delivery_hash: str  # From actual delivery
    match: bool  # scope_hash == delivery_hash
    grader_id: str
    evidence_grade: str
    timestamp: float
    receipt_hash: str = ""
    
    def __post_init__(self):
        data = f"{self.milestone_id}:{self.contract_id}:{self.delivery_hash}:{self.grader_id}:{self.timestamp}"
        self.receipt_hash = hashlib.sha256(data.encode()).hexdigest()[:16]


def verify_milestone(milestone: Milestone, delivery_hash: str, grader_id: str,
                     evidence_grade: str = "B") -> MilestoneReceipt:
    """Verify a single milestone delivery against frozen scope_hash."""
    now = time.time()
    match = milestone.scope_hash == delivery_hash
    
    milestone.status = MilestoneStatus.PASSED if match else MilestoneStatus.FAILED
    milestone.delivery_hash = delivery_hash
    milestone.verified_at = now
    milestone.grader_id = grader_id
    milestone.evidence_grade = evidence_grade
    
    return MilestoneReceipt(
        milestone_id=milestone.id,
        contract_id="",  # Set by caller
        scope_hash=milestone.scope_hash,
        delivery_hash=delivery_hash,
        match=match,
        grader_id=grader_id,
        evidence_grade=evidence_grade,
        timestamp=now
    )


def check_deadline_expiry(contract: Contract) -> list:
    """Mark overdue milestones as EXPIRED."""
    now = time.time()
    expired = []
    for m in contract.milestones:
        if m.status == MilestoneStatus.PENDING and m.deadline_utc < now:
            m.status = MilestoneStatus.EXPIRED
            expired.append(m.id)
    return expired


def compute_contract_score(contract: Contract) -> dict:
    """
    Compute contract completion score from milestone receipts.
    
    Score = weighted_passed / weighted_total
    Grade mapping: A >= 0.90, B >= 0.75, C >= 0.60, D >= 0.40, F < 0.40
    """
    total_weight = sum(m.weight for m in contract.milestones)
    passed_weight = sum(m.weight for m in contract.milestones 
                        if m.status == MilestoneStatus.PASSED)
    failed_weight = sum(m.weight for m in contract.milestones
                        if m.status == MilestoneStatus.FAILED)
    expired_weight = sum(m.weight for m in contract.milestones
                         if m.status == MilestoneStatus.EXPIRED)
    disputed_weight = sum(m.weight for m in contract.milestones
                          if m.status == MilestoneStatus.DISPUTED)
    pending_weight = sum(m.weight for m in contract.milestones
                         if m.status == MilestoneStatus.PENDING)
    
    score = passed_weight / total_weight if total_weight > 0 else 0
    
    if score >= 0.90:
        grade = ContractGrade.A
    elif score >= 0.75:
        grade = ContractGrade.B
    elif score >= 0.60:
        grade = ContractGrade.C
    elif score >= 0.40:
        grade = ContractGrade.D
    else:
        grade = ContractGrade.F
    
    return {
        "contract_id": contract.contract_id,
        "score": round(score, 4),
        "grade": grade.value,
        "milestones_total": len(contract.milestones),
        "milestones_passed": sum(1 for m in contract.milestones if m.status == MilestoneStatus.PASSED),
        "milestones_failed": sum(1 for m in contract.milestones if m.status == MilestoneStatus.FAILED),
        "milestones_expired": sum(1 for m in contract.milestones if m.status == MilestoneStatus.EXPIRED),
        "milestones_disputed": sum(1 for m in contract.milestones if m.status == MilestoneStatus.DISPUTED),
        "milestones_pending": sum(1 for m in contract.milestones if m.status == MilestoneStatus.PENDING),
        "weight_distribution": {
            "passed": round(passed_weight, 2),
            "failed": round(failed_weight, 2),
            "expired": round(expired_weight, 2),
            "disputed": round(disputed_weight, 2),
            "pending": round(pending_weight, 2),
            "total": round(total_weight, 2)
        },
        "contract_hash": contract.contract_hash
    }


def detect_scope_drift(contract: Contract, receipts: list) -> list:
    """Detect if any delivery hashes don't match frozen scope hashes."""
    drifts = []
    scope_map = {m.id: m.scope_hash for m in contract.milestones}
    for r in receipts:
        if r.milestone_id in scope_map:
            if r.scope_hash != scope_map[r.milestone_id]:
                drifts.append({
                    "milestone_id": r.milestone_id,
                    "expected_scope": scope_map[r.milestone_id],
                    "receipt_scope": r.scope_hash,
                    "verdict": "SCOPE_TAMPERING"
                })
    return drifts


# === Scenarios ===

def scenario_tc3_parallel():
    """TC3 parallel: 23/25 milestones passed = 0.92."""
    print("=== Scenario: TC3 Parallel (23/25 milestones) ===")
    now = time.time()
    
    milestones = []
    for i in range(25):
        scope = hashlib.sha256(f"milestone_{i}_spec".encode()).hexdigest()[:16]
        milestones.append(Milestone(
            id=f"m{i:02d}", description=f"Deliverable {i}",
            scope_hash=scope, deadline_utc=now + 86400*7
        ))
    
    contract = Contract("tc3_parallel", "kit_fox", "bro_agent", milestones, now)
    
    # 23 pass, 2 fail (milestones 7 and 19)
    receipts = []
    for i, m in enumerate(milestones):
        if i in [7, 19]:
            delivery = hashlib.sha256(f"wrong_delivery_{i}".encode()).hexdigest()[:16]
        else:
            delivery = m.scope_hash  # Correct delivery
        r = verify_milestone(m, delivery, "bro_agent", "A" if i not in [7, 19] else "F")
        r.contract_id = contract.contract_id
        receipts.append(r)
    
    result = compute_contract_score(contract)
    print(f"  Score: {result['score']} ({result['milestones_passed']}/{result['milestones_total']})")
    print(f"  Grade: {result['grade']}")
    print(f"  Failed milestones: m07, m19")
    print(f"  Contract hash: {result['contract_hash']}")
    print()


def scenario_weighted_milestones():
    """Weighted milestones — final deliverable worth 5x."""
    print("=== Scenario: Weighted Milestones (Final = 5x) ===")
    now = time.time()
    
    milestones = [
        Milestone("m00", "Research", hashlib.sha256(b"research").hexdigest()[:16], now+86400, 1.0),
        Milestone("m01", "Draft", hashlib.sha256(b"draft").hexdigest()[:16], now+86400*2, 1.0),
        Milestone("m02", "Review", hashlib.sha256(b"review").hexdigest()[:16], now+86400*3, 2.0),
        Milestone("m03", "Final", hashlib.sha256(b"final").hexdigest()[:16], now+86400*5, 5.0),
    ]
    
    contract = Contract("weighted_test", "kit_fox", "client", milestones, now)
    
    # Pass first 3, fail final (most weighted)
    for m in milestones[:3]:
        verify_milestone(m, m.scope_hash, "grader_a", "A")
    verify_milestone(milestones[3], "wrong_hash_final", "grader_a", "F")
    
    result = compute_contract_score(contract)
    print(f"  Score: {result['score']} (3/4 milestones but only {result['weight_distribution']['passed']}/{result['weight_distribution']['total']} weight)")
    print(f"  Grade: {result['grade']} — final deliverable failure tanks score")
    print()


def scenario_scope_drift_attack():
    """Attacker tries to amend scope mid-contract."""
    print("=== Scenario: Scope Drift Attack ===")
    now = time.time()
    
    milestones = [
        Milestone("m00", "API endpoint", hashlib.sha256(b"api_spec_v1").hexdigest()[:16], now+86400, 1.0),
        Milestone("m01", "Tests", hashlib.sha256(b"test_suite_v1").hexdigest()[:16], now+86400*2, 1.0),
    ]
    
    contract = Contract("drift_test", "agent_x", "client_y", milestones, now)
    
    # Normal delivery for m00
    r0 = verify_milestone(milestones[0], milestones[0].scope_hash, "grader", "A")
    r0.contract_id = contract.contract_id
    
    # Attacker submits receipt with DIFFERENT scope_hash (trying to change what was agreed)
    r1 = MilestoneReceipt(
        milestone_id="m01",
        contract_id=contract.contract_id,
        scope_hash=hashlib.sha256(b"test_suite_v2_easier").hexdigest()[:16],  # TAMPERED
        delivery_hash=hashlib.sha256(b"test_suite_v2_easier").hexdigest()[:16],  # Matches tampered scope
        match=True,  # Looks like it passes!
        grader_id="grader",
        evidence_grade="A",
        timestamp=now
    )
    
    drifts = detect_scope_drift(contract, [r0, r1])
    print(f"  Drift detected: {len(drifts)} tampering attempt(s)")
    for d in drifts:
        print(f"    {d['milestone_id']}: expected={d['expected_scope'][:8]}... got={d['receipt_scope'][:8]}... → {d['verdict']}")
    print(f"  Contract hash pins ALL scope hashes at creation: {contract.contract_hash}")
    print()


def scenario_expired_milestones():
    """Milestones past deadline auto-expire."""
    print("=== Scenario: Expired Milestones ===")
    now = time.time()
    
    milestones = [
        Milestone("m00", "On time", hashlib.sha256(b"m0").hexdigest()[:16], now+86400, 1.0),
        Milestone("m01", "Overdue", hashlib.sha256(b"m1").hexdigest()[:16], now-86400, 1.0),  # Past deadline
        Milestone("m02", "Way overdue", hashlib.sha256(b"m2").hexdigest()[:16], now-86400*7, 1.0),
    ]
    
    contract = Contract("expiry_test", "agent", "client", milestones, now)
    
    # Only deliver m00
    verify_milestone(milestones[0], milestones[0].scope_hash, "grader", "A")
    
    # Check for expiry
    expired = check_deadline_expiry(contract)
    result = compute_contract_score(contract)
    
    print(f"  Expired: {expired}")
    print(f"  Score: {result['score']} ({result['milestones_passed']}/{result['milestones_total']})")
    print(f"  Grade: {result['grade']}")
    print(f"  Pending: {result['milestones_pending']}, Expired: {result['milestones_expired']}")
    print()


if __name__ == "__main__":
    print("Milestone Receipt Validator — Atomic Deliverable Verification for ATF")
    print("Per santaclawd: milestone_receipts[] = atomic units")
    print("=" * 70)
    print()
    scenario_tc3_parallel()
    scenario_weighted_milestones()
    scenario_scope_drift_attack()
    scenario_expired_milestones()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Per-milestone grading > whole-scope grading")
    print("2. scope_hash frozen at contract creation = no runtime drift")
    print("3. TC3: 0.92 = 23/25 milestones, not 92% of one deliverable")
    print("4. Weighted milestones: 3/4 passed can still be Grade D if final fails")
    print("5. Scope drift = TAMPERING, caught by contract_hash comparison")
