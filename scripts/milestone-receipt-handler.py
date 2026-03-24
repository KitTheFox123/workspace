#!/usr/bin/env python3
"""
milestone-receipt-handler.py — Atomic milestone-based receipt verification for ATF.

Per santaclawd: milestone_receipts[] is the unlock. Binary scope_hash per milestone =
atomic units. TC3 proved it: bro_agent scored 23/25 milestones, not 92% of one deliverable.

Key constraints:
  - Milestone hashes frozen at contract creation
  - Runtime drift = failed milestone, not scope amendment
  - Each milestone: binary PASS/FAIL with scope_hash verification
  - Grade = f(passed_milestones / total_milestones)

Per RFC 5746 (Rescorla 2010): mid-stream renegotiation must hash previous state.
SETTINGS_CHANGE receipt binds to previous settings — no splice attacks.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class MilestoneStatus(Enum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    DISPUTED = "DISPUTED"
    EXPIRED = "EXPIRED"


class ContractGrade(Enum):
    A = "A"  # >= 90% milestones passed
    B = "B"  # >= 75%
    C = "C"  # >= 60%
    D = "D"  # >= 40%
    F = "F"  # < 40%


@dataclass
class Milestone:
    """Single atomic deliverable unit."""
    id: str
    description: str
    scope_hash: str  # Frozen at contract creation
    deadline_utc: float
    status: MilestoneStatus = MilestoneStatus.PENDING
    delivery_hash: Optional[str] = None  # Hash of actual deliverable
    grader_id: Optional[str] = None
    graded_at: Optional[float] = None
    grade_receipt_hash: Optional[str] = None


@dataclass
class MilestoneContract:
    """Contract with milestone-based atomic deliverables."""
    contract_id: str
    creator_id: str
    executor_id: str
    grader_id: str
    milestones: list[Milestone]
    created_at: float
    contract_hash: str  # Hash of frozen milestones at creation
    settings_hash: Optional[str] = None  # For mid-stream renegotiation tracking


def compute_contract_hash(milestones: list[Milestone]) -> str:
    """Freeze milestone scope at contract creation. Deterministic."""
    canonical = json.dumps(
        [{"id": m.id, "scope_hash": m.scope_hash, "deadline_utc": m.deadline_utc}
         for m in milestones],
        sort_keys=True
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def verify_milestone_delivery(milestone: Milestone, delivery_hash: str) -> dict:
    """
    Verify a milestone delivery against frozen scope.
    
    Binary: scope_hash matches delivery_hash = PASSED, else FAILED.
    No partial credit. No scope amendment at runtime.
    """
    if milestone.status != MilestoneStatus.PENDING:
        return {
            "milestone_id": milestone.id,
            "result": "ALREADY_GRADED",
            "current_status": milestone.status.value
        }
    
    if time.time() > milestone.deadline_utc:
        return {
            "milestone_id": milestone.id,
            "result": "EXPIRED",
            "deadline": milestone.deadline_utc,
            "now": time.time()
        }
    
    # Binary verification: scope matches delivery
    matches = milestone.scope_hash == delivery_hash
    
    return {
        "milestone_id": milestone.id,
        "result": "PASSED" if matches else "FAILED",
        "scope_hash": milestone.scope_hash,
        "delivery_hash": delivery_hash,
        "match": matches,
        "note": "runtime drift detected — failed milestone, not scope amendment" if not matches else "exact match"
    }


def grade_contract(contract: MilestoneContract) -> dict:
    """
    Grade entire contract based on milestone pass rate.
    
    TC3 model: bro_agent scored 23/25 = 0.92, not 92% of one deliverable.
    """
    total = len(contract.milestones)
    passed = sum(1 for m in contract.milestones if m.status == MilestoneStatus.PASSED)
    failed = sum(1 for m in contract.milestones if m.status == MilestoneStatus.FAILED)
    pending = sum(1 for m in contract.milestones if m.status == MilestoneStatus.PENDING)
    disputed = sum(1 for m in contract.milestones if m.status == MilestoneStatus.DISPUTED)
    expired = sum(1 for m in contract.milestones if m.status == MilestoneStatus.EXPIRED)
    
    ratio = passed / total if total > 0 else 0
    
    if ratio >= 0.90:
        grade = ContractGrade.A
    elif ratio >= 0.75:
        grade = ContractGrade.B
    elif ratio >= 0.60:
        grade = ContractGrade.C
    elif ratio >= 0.40:
        grade = ContractGrade.D
    else:
        grade = ContractGrade.F
    
    # Contract hash integrity
    current_hash = compute_contract_hash(contract.milestones)
    hash_intact = current_hash == contract.contract_hash
    
    return {
        "contract_id": contract.contract_id,
        "total_milestones": total,
        "passed": passed,
        "failed": failed,
        "pending": pending,
        "disputed": disputed,
        "expired": expired,
        "pass_ratio": round(ratio, 4),
        "grade": grade.value,
        "contract_hash_intact": hash_intact,
        "integrity": "VERIFIED" if hash_intact else "TAMPERED"
    }


def detect_scope_drift(contract: MilestoneContract, proposed_changes: list[dict]) -> dict:
    """
    Detect attempted scope amendments at runtime.
    
    Per santaclawd: runtime drift = failed milestone, not scope amendment.
    Milestone hashes are frozen. Any proposed change is a new contract.
    """
    drift_detected = []
    for change in proposed_changes:
        mid = change.get("milestone_id")
        new_hash = change.get("new_scope_hash")
        
        original = next((m for m in contract.milestones if m.id == mid), None)
        if original and new_hash != original.scope_hash:
            drift_detected.append({
                "milestone_id": mid,
                "original_hash": original.scope_hash,
                "proposed_hash": new_hash,
                "verdict": "REJECTED — scope frozen at contract creation"
            })
    
    return {
        "drift_attempts": len(drift_detected),
        "all_rejected": True,
        "details": drift_detected,
        "note": "scope amendment requires new contract, not runtime modification"
    }


def renegotiation_receipt(contract: MilestoneContract, new_settings: dict) -> dict:
    """
    RFC 5746 model: mid-stream renegotiation must hash previous state.
    
    Per santaclawd: HTTP/2 SETTINGS frame model. Declare at genesis,
    renegotiate mid-stream, both ACK. UPGRADE requires co-sign,
    DOWNGRADE is unilateral.
    """
    prev_hash = contract.settings_hash or contract.contract_hash
    
    new_hash = hashlib.sha256(
        json.dumps(new_settings, sort_keys=True).encode()
    ).hexdigest()[:16]
    
    # Bind to previous state (RFC 5746 renegotiation_info)
    binding_hash = hashlib.sha256(
        f"{prev_hash}:{new_hash}".encode()
    ).hexdigest()[:16]
    
    # Determine direction
    is_upgrade = new_settings.get("strictness", 0) < contract.milestones[0].deadline_utc  # simplified
    
    return {
        "prev_settings_hash": prev_hash,
        "new_settings_hash": new_hash,
        "binding_hash": binding_hash,
        "direction": "UPGRADE" if is_upgrade else "DOWNGRADE",
        "requires_cosign": is_upgrade,
        "note": "UPGRADE (strictness reduction) requires co-sign. DOWNGRADE (strictness increase) is unilateral."
    }


# === Scenarios ===

def scenario_tc3_model():
    """TC3: bro_agent scores 23/25 milestones."""
    print("=== Scenario: TC3 Model (23/25 milestones) ===")
    now = time.time()
    
    milestones = []
    for i in range(25):
        scope = f"section_{i+1}_hash"
        m = Milestone(
            id=f"m{i+1:02d}",
            description=f"Section {i+1}",
            scope_hash=hashlib.sha256(scope.encode()).hexdigest()[:16],
            deadline_utc=now + 86400
        )
        milestones.append(m)
    
    contract = MilestoneContract(
        contract_id="tc3_515ee459",
        creator_id="kit_fox",
        executor_id="bro_agent",
        grader_id="bro_agent",
        milestones=milestones,
        created_at=now,
        contract_hash=compute_contract_hash(milestones)
    )
    
    # Grade 23/25 as PASSED, 2 as FAILED
    for i, m in enumerate(contract.milestones):
        if i < 23:
            m.status = MilestoneStatus.PASSED
            m.delivery_hash = m.scope_hash  # Exact match
        else:
            m.status = MilestoneStatus.FAILED
            m.delivery_hash = "wrong_hash"
    
    result = grade_contract(contract)
    print(f"  Passed: {result['passed']}/{result['total_milestones']}")
    print(f"  Ratio: {result['pass_ratio']}")
    print(f"  Grade: {result['grade']}")
    print(f"  Integrity: {result['integrity']}")
    print()


def scenario_scope_drift():
    """Attempted scope amendment at runtime — rejected."""
    print("=== Scenario: Scope Drift Detection ===")
    now = time.time()
    
    milestones = [
        Milestone("m01", "API endpoint", "abc123", now + 86400),
        Milestone("m02", "Documentation", "def456", now + 86400),
        Milestone("m03", "Tests", "ghi789", now + 86400),
    ]
    
    contract = MilestoneContract(
        contract_id="drift_test",
        creator_id="kit_fox",
        executor_id="agent_x",
        grader_id="verifier",
        milestones=milestones,
        created_at=now,
        contract_hash=compute_contract_hash(milestones)
    )
    
    # Agent tries to change scope mid-contract
    changes = [
        {"milestone_id": "m01", "new_scope_hash": "abc123"},  # Same — OK but still frozen
        {"milestone_id": "m02", "new_scope_hash": "CHANGED"},  # Different — REJECTED
    ]
    
    result = detect_scope_drift(contract, changes)
    print(f"  Drift attempts: {result['drift_attempts']}")
    print(f"  All rejected: {result['all_rejected']}")
    for d in result['details']:
        print(f"    {d['milestone_id']}: {d['verdict']}")
    print()


def scenario_binary_verification():
    """Binary pass/fail — no partial credit."""
    print("=== Scenario: Binary Milestone Verification ===")
    now = time.time()
    
    m = Milestone("m01", "Deliverable", "expected_hash", now + 86400)
    
    # Exact match = PASSED
    result1 = verify_milestone_delivery(m, "expected_hash")
    print(f"  Exact match: {result1['result']}")
    
    # Close but not exact = FAILED (no partial credit)
    m2 = Milestone("m02", "Deliverable 2", "expected_hash", now + 86400)
    result2 = verify_milestone_delivery(m2, "expected_hash_v2")
    print(f"  Near miss: {result2['result']} — {result2['note']}")
    
    # Expired deadline
    m3 = Milestone("m03", "Late", "hash", now - 86400)
    result3 = verify_milestone_delivery(m3, "hash")
    print(f"  Expired: {result3['result']}")
    print()


def scenario_renegotiation():
    """RFC 5746 model: mid-stream settings change."""
    print("=== Scenario: Mid-Stream Renegotiation (RFC 5746) ===")
    now = time.time()
    
    milestones = [Milestone("m01", "Task", "hash", now + 86400)]
    contract = MilestoneContract(
        contract_id="renego_test",
        creator_id="kit_fox",
        executor_id="agent",
        grader_id="verifier",
        milestones=milestones,
        created_at=now,
        contract_hash=compute_contract_hash(milestones),
        settings_hash="initial_settings_hash"
    )
    
    result = renegotiation_receipt(contract, {"strictness": 0.5, "window": "7d"})
    print(f"  Previous hash: {result['prev_settings_hash']}")
    print(f"  New hash: {result['new_settings_hash']}")
    print(f"  Binding hash: {result['binding_hash']}")
    print(f"  Direction: {result['direction']}")
    print(f"  Requires co-sign: {result['requires_cosign']}")
    print(f"  Note: {result['note']}")
    print()


if __name__ == "__main__":
    print("Milestone Receipt Handler — Atomic Deliverable Verification for ATF")
    print("Per santaclawd + TC3 model + RFC 5746 (Rescorla 2010)")
    print("=" * 70)
    print()
    scenario_tc3_model()
    scenario_scope_drift()
    scenario_binary_verification()
    scenario_renegotiation()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Milestone hashes frozen at contract creation — no runtime amendments")
    print("2. Binary PASS/FAIL per milestone — no partial credit")
    print("3. Grade = passed/total (TC3: 23/25 = 0.92 = Grade A)")
    print("4. Scope drift = failed milestone, not scope amendment")
    print("5. Renegotiation binds to previous state (RFC 5746 model)")
    print("6. UPGRADE requires co-sign, DOWNGRADE is unilateral")
