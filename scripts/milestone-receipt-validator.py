#!/usr/bin/env python3
"""
milestone-receipt-validator.py — Atomic milestone-based delivery verification for ATF.

Per santaclawd: milestone_receipts[] is the unlock. Binary scope_hash per milestone
= atomic units. TC3 0.92 = bro_agent hit 23/25 milestones, not 92% of one deliverable.

Key constraint: milestone hashes frozen at contract creation. Runtime drift = failed
milestone, not scope amendment.

Escrow.com has done milestone-based inspection+release since 2014.
Difference: ATF milestones are machine-verifiable (scope_hash match = binary).
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MilestoneStatus(Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    VERIFIED = "VERIFIED"        # Grader confirmed scope_hash match
    FAILED = "FAILED"            # scope_hash mismatch
    DISPUTED = "DISPUTED"        # Counterparty disputes
    EXPIRED = "EXPIRED"          # Past deadline


class ContractGrade(Enum):
    COMPLETE = "COMPLETE"        # All milestones verified
    PARTIAL = "PARTIAL"          # Some milestones verified
    FAILED = "FAILED"            # Majority failed
    DISPUTED = "DISPUTED"        # Active disputes


@dataclass
class Milestone:
    id: str
    description: str
    scope_hash: str              # Frozen at contract creation
    weight: float                # 0-1, all must sum to 1.0
    deadline: float              # Unix timestamp
    status: MilestoneStatus = MilestoneStatus.PENDING
    delivery_hash: Optional[str] = None
    delivery_timestamp: Optional[float] = None
    grader_id: Optional[str] = None
    grade: Optional[str] = None


@dataclass
class MilestoneContract:
    contract_id: str
    agent_id: str
    counterparty_id: str
    grader_id: str
    milestones: list[Milestone]
    created_at: float
    contract_hash: str           # Hash of all milestone scope_hashes
    
    def compute_contract_hash(self) -> str:
        """Deterministic hash of frozen scope."""
        scope_data = "|".join(
            f"{m.id}:{m.scope_hash}:{m.weight}:{m.deadline}"
            for m in sorted(self.milestones, key=lambda x: x.id)
        )
        return hashlib.sha256(scope_data.encode()).hexdigest()[:16]
    
    def verify_contract_integrity(self) -> bool:
        """Verify no milestone scope_hashes changed since creation."""
        return self.compute_contract_hash() == self.contract_hash


def verify_milestone_delivery(milestone: Milestone, delivery_hash: str) -> dict:
    """
    Binary verification: does delivery match frozen scope_hash?
    
    This is the key insight: milestone verification is BINARY.
    scope_hash match = VERIFIED. Mismatch = FAILED. No partial credit.
    """
    match = delivery_hash == milestone.scope_hash
    
    return {
        "milestone_id": milestone.id,
        "scope_hash": milestone.scope_hash,
        "delivery_hash": delivery_hash,
        "match": match,
        "status": MilestoneStatus.VERIFIED.value if match else MilestoneStatus.FAILED.value,
        "verdict": "BINARY_MATCH" if match else "SCOPE_DRIFT"
    }


def grade_contract(contract: MilestoneContract) -> dict:
    """
    Grade entire contract based on milestone completion.
    
    TC3 model: 0.92 = 23/25 milestones, not 92% of one deliverable.
    Weighted sum, but each milestone is binary pass/fail.
    """
    verified = sum(m.weight for m in contract.milestones 
                   if m.status == MilestoneStatus.VERIFIED)
    failed = sum(m.weight for m in contract.milestones 
                 if m.status == MilestoneStatus.FAILED)
    pending = sum(m.weight for m in contract.milestones 
                  if m.status == MilestoneStatus.PENDING)
    disputed = sum(m.weight for m in contract.milestones 
                   if m.status == MilestoneStatus.DISPUTED)
    expired = sum(m.weight for m in contract.milestones 
                  if m.status == MilestoneStatus.EXPIRED)
    
    score = verified  # Only verified milestones count
    
    if disputed > 0:
        overall = ContractGrade.DISPUTED
    elif score >= 0.95:
        overall = ContractGrade.COMPLETE
    elif score >= 0.5:
        overall = ContractGrade.PARTIAL
    else:
        overall = ContractGrade.FAILED
    
    integrity = contract.verify_contract_integrity()
    
    return {
        "contract_id": contract.contract_id,
        "integrity": "VALID" if integrity else "TAMPERED",
        "score": round(score, 4),
        "grade": overall.value,
        "breakdown": {
            "verified": round(verified, 4),
            "failed": round(failed, 4),
            "pending": round(pending, 4),
            "disputed": round(disputed, 4),
            "expired": round(expired, 4)
        },
        "milestone_count": len(contract.milestones),
        "milestones_verified": sum(1 for m in contract.milestones 
                                    if m.status == MilestoneStatus.VERIFIED),
        "milestones_failed": sum(1 for m in contract.milestones 
                                  if m.status == MilestoneStatus.FAILED)
    }


def detect_scope_drift(contract: MilestoneContract, proposed_changes: dict) -> dict:
    """
    Detect attempts to amend milestones after contract creation.
    
    Key constraint: milestone hashes frozen at contract creation.
    Runtime drift = failed milestone, not scope amendment.
    """
    drift_detected = []
    for milestone_id, new_hash in proposed_changes.items():
        original = next((m for m in contract.milestones if m.id == milestone_id), None)
        if original and new_hash != original.scope_hash:
            drift_detected.append({
                "milestone_id": milestone_id,
                "original_hash": original.scope_hash,
                "proposed_hash": new_hash,
                "verdict": "SCOPE_DRIFT_REJECTED"
            })
    
    return {
        "contract_id": contract.contract_id,
        "drift_attempts": len(drift_detected),
        "drifts": drift_detected,
        "policy": "FROZEN_AT_CREATION — amendment requires new contract"
    }


# === Scenarios ===

def scenario_tc3_model():
    """TC3: 23/25 milestones = 0.92, not 92% of one deliverable."""
    print("=== Scenario: TC3 Model (23/25 Milestones) ===")
    now = time.time()
    
    milestones = []
    for i in range(25):
        scope = f"milestone_{i:02d}_deliverable"
        scope_hash = hashlib.sha256(scope.encode()).hexdigest()[:16]
        m = Milestone(
            id=f"m{i:02d}",
            description=f"Deliverable section {i+1}",
            scope_hash=scope_hash,
            weight=1.0/25,
            deadline=now + 86400 * 30
        )
        # 23 verified, 2 failed
        if i < 23:
            m.status = MilestoneStatus.VERIFIED
            m.delivery_hash = scope_hash
        else:
            m.status = MilestoneStatus.FAILED
            m.delivery_hash = "wrong_hash_drift"
        milestones.append(m)
    
    contract = MilestoneContract(
        contract_id="tc3_001",
        agent_id="kit_fox",
        counterparty_id="bro_agent",
        grader_id="braindiff",
        milestones=milestones,
        created_at=now,
        contract_hash=""
    )
    contract.contract_hash = contract.compute_contract_hash()
    
    result = grade_contract(contract)
    print(f"  Score: {result['score']} ({result['milestones_verified']}/{result['milestone_count']})")
    print(f"  Grade: {result['grade']}")
    print(f"  Integrity: {result['integrity']}")
    print(f"  Key: 0.92 = 23 binary passes, NOT 92% of one blob")
    print()


def scenario_scope_drift():
    """Attempt to amend milestones after contract creation."""
    print("=== Scenario: Scope Drift Rejection ===")
    now = time.time()
    
    milestones = [
        Milestone("m01", "Research report", "abc123", 0.5, now + 86400*7),
        Milestone("m02", "Implementation", "def456", 0.5, now + 86400*14),
    ]
    
    contract = MilestoneContract(
        contract_id="drift_test",
        agent_id="drifter",
        counterparty_id="client",
        grader_id="auditor",
        milestones=milestones,
        created_at=now,
        contract_hash=""
    )
    contract.contract_hash = contract.compute_contract_hash()
    
    # Agent tries to change scope mid-contract
    drift = detect_scope_drift(contract, {
        "m01": "abc123",      # unchanged
        "m02": "new_scope"    # DRIFT!
    })
    
    print(f"  Drift attempts: {drift['drift_attempts']}")
    for d in drift['drifts']:
        print(f"  {d['milestone_id']}: {d['original_hash']} → {d['proposed_hash']} = {d['verdict']}")
    print(f"  Policy: {drift['policy']}")
    print()


def scenario_binary_verification():
    """Demonstrate binary pass/fail — no partial credit."""
    print("=== Scenario: Binary Verification (No Partial Credit) ===")
    now = time.time()
    
    scope_hash = hashlib.sha256(b"exact_deliverable_spec").hexdigest()[:16]
    milestone = Milestone("m01", "Exact deliverable", scope_hash, 1.0, now + 86400)
    
    # Exact match
    result1 = verify_milestone_delivery(milestone, scope_hash)
    print(f"  Exact match: {result1['verdict']} (hash={result1['delivery_hash'][:8]}...)")
    
    # Close but not exact — still FAILED
    close_hash = hashlib.sha256(b"exact_deliverable_spec_v2").hexdigest()[:16]
    result2 = verify_milestone_delivery(milestone, close_hash)
    print(f"  Close match: {result2['verdict']} (hash={result2['delivery_hash'][:8]}...)")
    
    # Completely wrong
    result3 = verify_milestone_delivery(milestone, "completely_wrong")
    print(f"  Wrong: {result3['verdict']}")
    print(f"  Key: Binary. No 'close enough'. Hash matches or doesn't.")
    print()


def scenario_weighted_milestones():
    """Different milestone weights — core vs optional deliverables."""
    print("=== Scenario: Weighted Milestones (Core vs Optional) ===")
    now = time.time()
    
    milestones = [
        Milestone("core1", "Core architecture", "h1", 0.30, now + 86400*7, 
                  MilestoneStatus.VERIFIED, "h1"),
        Milestone("core2", "Core implementation", "h2", 0.30, now + 86400*14,
                  MilestoneStatus.VERIFIED, "h2"),
        Milestone("opt1", "Documentation", "h3", 0.15, now + 86400*21,
                  MilestoneStatus.VERIFIED, "h3"),
        Milestone("opt2", "Tests", "h4", 0.15, now + 86400*21,
                  MilestoneStatus.FAILED, "wrong"),
        Milestone("opt3", "Demo", "h5", 0.10, now + 86400*28,
                  MilestoneStatus.EXPIRED),
    ]
    
    contract = MilestoneContract(
        contract_id="weighted_001",
        agent_id="builder",
        counterparty_id="client",
        grader_id="auditor",
        milestones=milestones,
        created_at=now,
        contract_hash=""
    )
    contract.contract_hash = contract.compute_contract_hash()
    
    result = grade_contract(contract)
    print(f"  Score: {result['score']} (core={0.60}, optional verified={0.15})")
    print(f"  Grade: {result['grade']}")
    print(f"  Breakdown: {result['breakdown']}")
    print(f"  Key: Core milestones both passed. Optional mixed. Score = 0.75 = PARTIAL.")
    print()


if __name__ == "__main__":
    print("Milestone Receipt Validator — Atomic Delivery Verification for ATF")
    print("Per santaclawd: milestone_receipts[] = binary scope_hash per milestone")
    print("=" * 70)
    print()
    scenario_tc3_model()
    scenario_scope_drift()
    scenario_binary_verification()
    scenario_weighted_milestones()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Milestones are BINARY (hash match or not). No partial credit.")
    print("2. Scope hashes FROZEN at contract creation. Drift = new contract.")
    print("3. TC3 0.92 = 23/25 milestones, not 92% of one deliverable.")
    print("4. Weighted milestones: core vs optional, but each still binary.")
    print("5. Grader grades per-milestone, not whole scope (per santaclawd).")
