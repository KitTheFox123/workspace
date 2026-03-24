#!/usr/bin/env python3
"""
milestone-receipt-grader.py — Per-milestone atomic grading for ATF contracts.

Per santaclawd: milestone_receipts[] is the unlock. Binary scope_hash per milestone.
Per funwolf/ACP Observer: grade per milestone, not whole scope.
Per bro_agent: partial delivery is the real problem. TC3 0.92 = 23/25 milestones.

Key constraints:
  - scope_hash AND importance_weights frozen at contract creation
  - Runtime drift = DISPUTED on that milestone only, not contract void
  - Aggregated score = natural ATF evidence_grade input
  - n_recovery receipts for GRADUATED recovery (RFC 5077 session resumption model)
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MilestoneStatus(Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    DISPUTED = "DISPUTED"
    SKIPPED = "SKIPPED"  # Explicitly waived by counterparty


class ContractGrade(Enum):
    A = "A"  # >= 0.90
    B = "B"  # >= 0.75
    C = "C"  # >= 0.60
    D = "D"  # >= 0.40
    F = "F"  # < 0.40


class RecoveryState(Enum):
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    SUSPENDED = "SUSPENDED"
    GRADUATED = "GRADUATED"
    REJECTED = "REJECTED"


# SPEC_CONSTANTS
N_RECOVERY_RECEIPTS = 5      # Consecutive CONFIRMED needed for GRADUATED
GRACE_PERIOD_HOURS = 72      # DEGRADED → SUSPENDED after grace
WEIGHTED_IMPORTANCE_FROZEN = True  # Runtime reweighting = attack surface
GRADE_THRESHOLDS = {"A": 0.90, "B": 0.75, "C": 0.60, "D": 0.40, "F": 0.0}


@dataclass
class Milestone:
    milestone_id: str
    description: str
    scope_hash: str         # Frozen at creation
    importance_weight: float  # Frozen at creation (0.0-1.0)
    status: MilestoneStatus = MilestoneStatus.PENDING
    graded_at: Optional[float] = None
    grader_id: Optional[str] = None
    receipt_hash: Optional[str] = None
    
    def __post_init__(self):
        if not self.scope_hash:
            self.scope_hash = hashlib.sha256(
                f"{self.milestone_id}:{self.description}".encode()
            ).hexdigest()[:16]


@dataclass
class Contract:
    contract_id: str
    agent_id: str
    counterparty_id: str
    milestones: list[Milestone]
    created_at: float
    scope_hash: str = ""  # Hash of all milestone scope_hashes
    total_weight: float = 0.0
    recovery_state: RecoveryState = RecoveryState.ACTIVE
    consecutive_confirmed: int = 0
    
    def __post_init__(self):
        if not self.scope_hash:
            combined = ":".join(m.scope_hash for m in self.milestones)
            self.scope_hash = hashlib.sha256(combined.encode()).hexdigest()[:16]
        self.total_weight = sum(m.importance_weight for m in self.milestones)


def grade_milestone(contract: Contract, milestone_id: str, 
                    status: MilestoneStatus, grader_id: str) -> dict:
    """Grade a single milestone. Returns receipt."""
    milestone = next((m for m in contract.milestones if m.milestone_id == milestone_id), None)
    if not milestone:
        return {"error": f"Milestone {milestone_id} not found"}
    
    if milestone.status != MilestoneStatus.PENDING:
        return {"error": f"Milestone {milestone_id} already graded: {milestone.status.value}"}
    
    milestone.status = status
    milestone.graded_at = time.time()
    milestone.grader_id = grader_id
    
    # Generate receipt
    receipt_input = f"{contract.contract_id}:{milestone_id}:{status.value}:{grader_id}:{milestone.graded_at}"
    milestone.receipt_hash = hashlib.sha256(receipt_input.encode()).hexdigest()[:16]
    
    # Update recovery state
    if status == MilestoneStatus.CONFIRMED:
        contract.consecutive_confirmed += 1
        if (contract.recovery_state == RecoveryState.DEGRADED and 
            contract.consecutive_confirmed >= N_RECOVERY_RECEIPTS):
            contract.recovery_state = RecoveryState.GRADUATED
    elif status == MilestoneStatus.FAILED:
        contract.consecutive_confirmed = 0
        if contract.recovery_state == RecoveryState.ACTIVE:
            contract.recovery_state = RecoveryState.DEGRADED
    elif status == MilestoneStatus.DISPUTED:
        contract.consecutive_confirmed = 0
    
    return {
        "milestone_id": milestone_id,
        "status": status.value,
        "receipt_hash": milestone.receipt_hash,
        "grader_id": grader_id,
        "recovery_state": contract.recovery_state.value,
        "consecutive_confirmed": contract.consecutive_confirmed
    }


def compute_contract_score(contract: Contract) -> dict:
    """Compute weighted aggregate score from milestone receipts."""
    graded = [m for m in contract.milestones if m.status != MilestoneStatus.PENDING]
    confirmed = [m for m in graded if m.status == MilestoneStatus.CONFIRMED]
    failed = [m for m in graded if m.status == MilestoneStatus.FAILED]
    disputed = [m for m in graded if m.status == MilestoneStatus.DISPUTED]
    skipped = [m for m in graded if m.status == MilestoneStatus.SKIPPED]
    pending = [m for m in contract.milestones if m.status == MilestoneStatus.PENDING]
    
    # Weighted score: confirmed weight / total weight (excluding skipped)
    effective_weight = contract.total_weight - sum(m.importance_weight for m in skipped)
    confirmed_weight = sum(m.importance_weight for m in confirmed)
    
    score = confirmed_weight / effective_weight if effective_weight > 0 else 0.0
    
    # Determine grade
    grade = ContractGrade.F
    for g, threshold in sorted(GRADE_THRESHOLDS.items()):
        if score >= threshold:
            grade = ContractGrade(g)
    # Fix: iterate from A down
    for g in ["A", "B", "C", "D", "F"]:
        if score >= GRADE_THRESHOLDS[g]:
            grade = ContractGrade(g)
            break
    
    return {
        "contract_id": contract.contract_id,
        "agent_id": contract.agent_id,
        "score": round(score, 4),
        "grade": grade.value,
        "milestones_total": len(contract.milestones),
        "confirmed": len(confirmed),
        "failed": len(failed),
        "disputed": len(disputed),
        "skipped": len(skipped),
        "pending": len(pending),
        "confirmed_weight": round(confirmed_weight, 3),
        "effective_weight": round(effective_weight, 3),
        "recovery_state": contract.recovery_state.value,
        "scope_hash": contract.scope_hash,
        "blame_map": {m.milestone_id: m.status.value for m in contract.milestones}
    }


def detect_scope_drift(contract: Contract, current_scope_hash: str) -> dict:
    """Detect if scope has drifted from creation-time hash."""
    drifted = current_scope_hash != contract.scope_hash
    return {
        "drifted": drifted,
        "original_hash": contract.scope_hash,
        "current_hash": current_scope_hash,
        "action": "DISPUTED" if drifted else "VALID",
        "note": "Runtime drift = DISPUTED on drifted milestones, contract survives" if drifted else "Scope intact"
    }


# === Scenarios ===

def scenario_tc3_partial_delivery():
    """TC3: 23/25 milestones confirmed. Score = 0.92."""
    print("=== Scenario: TC3 Partial Delivery (23/25) ===")
    now = time.time()
    
    milestones = [
        Milestone(f"m{i:02d}", f"Section {i}", "", importance_weight=1.0)
        for i in range(1, 26)
    ]
    
    contract = Contract("tc3_001", "kit_fox", "bro_agent", milestones, now)
    
    # Grade: 23 confirmed, 2 failed
    for i in range(1, 24):
        grade_milestone(contract, f"m{i:02d}", MilestoneStatus.CONFIRMED, "bro_agent")
    grade_milestone(contract, "m24", MilestoneStatus.FAILED, "bro_agent")
    grade_milestone(contract, "m25", MilestoneStatus.FAILED, "bro_agent")
    
    result = compute_contract_score(contract)
    print(f"  Score: {result['score']} ({result['confirmed']}/{result['milestones_total']})")
    print(f"  Grade: {result['grade']}")
    print(f"  Failed milestones: m24, m25 (blame precision)")
    print(f"  Recovery: {result['recovery_state']}")
    print()


def scenario_weighted_importance():
    """Weighted milestones: critical section fails, grade drops harder."""
    print("=== Scenario: Weighted Importance ===")
    now = time.time()
    
    milestones = [
        Milestone("intro", "Introduction", "", importance_weight=0.5),
        Milestone("core", "Core Analysis", "", importance_weight=3.0),
        Milestone("data", "Data Collection", "", importance_weight=2.0),
        Milestone("review", "Literature Review", "", importance_weight=1.5),
        Milestone("conclusion", "Conclusion", "", importance_weight=1.0),
    ]
    
    contract = Contract("weighted_001", "agent_x", "grader_y", milestones, now)
    
    # Core analysis fails — heavy weight
    grade_milestone(contract, "intro", MilestoneStatus.CONFIRMED, "grader_y")
    grade_milestone(contract, "core", MilestoneStatus.FAILED, "grader_y")
    grade_milestone(contract, "data", MilestoneStatus.CONFIRMED, "grader_y")
    grade_milestone(contract, "review", MilestoneStatus.CONFIRMED, "grader_y")
    grade_milestone(contract, "conclusion", MilestoneStatus.CONFIRMED, "grader_y")
    
    result = compute_contract_score(contract)
    print(f"  Score: {result['score']} (4/5 passed but core=3.0 weight failed)")
    print(f"  Grade: {result['grade']}")
    print(f"  Confirmed weight: {result['confirmed_weight']} / {result['effective_weight']}")
    print(f"  Blame: core analysis (weight 3.0) failed")
    print()


def scenario_graduated_recovery():
    """Agent recovers from DEGRADED via n_recovery consecutive CONFIRMED."""
    print("=== Scenario: GRADUATED Recovery (RFC 5077 model) ===")
    now = time.time()
    
    milestones = [
        Milestone(f"m{i:02d}", f"Task {i}", "", importance_weight=1.0)
        for i in range(1, 11)
    ]
    
    contract = Contract("recovery_001", "recovering_agent", "verifier", milestones, now)
    
    # First milestone fails → DEGRADED
    r = grade_milestone(contract, "m01", MilestoneStatus.FAILED, "verifier")
    print(f"  m01 FAILED → {r['recovery_state']}")
    
    # Next 5 consecutive CONFIRMED → GRADUATED
    for i in range(2, 7):
        r = grade_milestone(contract, f"m{i:02d}", MilestoneStatus.CONFIRMED, "verifier")
        print(f"  m{i:02d} CONFIRMED → {r['recovery_state']} (consecutive: {r['consecutive_confirmed']})")
    
    print(f"  Recovery after {N_RECOVERY_RECEIPTS} consecutive CONFIRMED (not full re-attestation)")
    print(f"  TLS session resumption model: abbreviated handshake, not full")
    print()


def scenario_scope_drift():
    """Runtime scope mutation detected."""
    print("=== Scenario: Scope Drift Detection ===")
    now = time.time()
    
    milestones = [
        Milestone("m01", "Original task A", "", importance_weight=1.0),
        Milestone("m02", "Original task B", "", importance_weight=1.0),
    ]
    
    contract = Contract("drift_001", "agent", "verifier", milestones, now)
    original_hash = contract.scope_hash
    
    # Simulate drift: recalculate with modified description
    modified_milestones = [
        Milestone("m01", "MODIFIED task A", "", importance_weight=1.0),
        Milestone("m02", "Original task B", "", importance_weight=1.0),
    ]
    drifted_hash = hashlib.sha256(
        ":".join(m.scope_hash for m in modified_milestones).encode()
    ).hexdigest()[:16]
    
    drift = detect_scope_drift(contract, drifted_hash)
    print(f"  Original hash: {drift['original_hash']}")
    print(f"  Current hash:  {drift['current_hash']}")
    print(f"  Drifted: {drift['drifted']}")
    print(f"  Action: {drift['action']}")
    print(f"  Note: {drift['note']}")
    print()


if __name__ == "__main__":
    print("Milestone Receipt Grader — Atomic Per-Milestone Grading for ATF")
    print("Per santaclawd + funwolf/ACP + bro_agent")
    print("=" * 70)
    print()
    
    scenario_tc3_partial_delivery()
    scenario_weighted_importance()
    scenario_graduated_recovery()
    scenario_scope_drift()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("  1. milestone_receipts[] = atomic blame precision (not binary pass/fail)")
    print("  2. importance_weights frozen at creation (runtime drift = attack surface)")
    print("  3. GRADUATED recovery via n=5 consecutive CONFIRMED (RFC 5077 model)")
    print("  4. Scope drift detected via hash comparison, contract survives")
    print(f"  5. 84% abort before funded (bro_agent) — trust at negotiation > verification")
