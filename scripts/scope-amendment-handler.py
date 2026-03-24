#!/usr/bin/env python3
"""
scope-amendment-handler.py — Scope drift management for ATF milestone contracts.

Per santaclawd: scope_hash divergence is the unsolved ATF problem. Escrow locks
scope_hash at creation but real work drifts. Binary pass/fail loses everyone.

Model: AIA G701 Change Order form (construction industry).
  - Original scope_hash frozen at contract creation
  - SCOPE_AMENDMENT receipt: old_hash + new_hash + counterparty co-sign
  - Milestone receipts reference amendment chain, not just original
  - Partial delivery = completed milestones at original hash

Key insight: scope drift is not a bug — it is how real work happens.
The question is whether drift is tracked (amendment) or hidden (silent change).
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AmendmentStatus(Enum):
    PROPOSED = "PROPOSED"         # One party proposes
    CO_SIGNED = "CO_SIGNED"       # Both parties agree
    REJECTED = "REJECTED"         # Counterparty rejects
    EXPIRED = "EXPIRED"           # No response within window
    SUPERSEDED = "SUPERSEDED"     # Newer amendment replaces


class MilestoneStatus(Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    AMENDED = "AMENDED"           # Scope changed, new milestone created
    CANCELLED = "CANCELLED"       # Removed by amendment


# SPEC_CONSTANTS
AMENDMENT_CO_SIGN_WINDOW_HOURS = 72
MAX_AMENDMENTS_PER_CONTRACT = 10  # Prevent infinite drift
SCOPE_DRIFT_THRESHOLD = 0.30     # >30% milestones amended = DRIFT_WARNING


@dataclass
class Milestone:
    milestone_id: str
    description: str
    scope_hash: str
    status: MilestoneStatus = MilestoneStatus.PENDING
    completed_at: Optional[float] = None
    amendment_id: Optional[str] = None  # If created by amendment


@dataclass
class ScopeAmendment:
    amendment_id: str
    contract_id: str
    proposer: str
    counterparty: str
    old_scope_hash: str
    new_scope_hash: str
    milestones_added: list[str] = field(default_factory=list)
    milestones_removed: list[str] = field(default_factory=list)
    milestones_modified: list[str] = field(default_factory=list)
    reason: str = ""
    status: AmendmentStatus = AmendmentStatus.PROPOSED
    proposed_at: float = 0.0
    co_signed_at: Optional[float] = None
    co_sign_hash: str = ""  # Hash of counterparty acknowledgment

    def compute_hash(self) -> str:
        data = f"{self.contract_id}:{self.old_scope_hash}:{self.new_scope_hash}:{self.proposed_at}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class Contract:
    contract_id: str
    client: str
    provider: str
    original_scope_hash: str
    milestones: list[Milestone] = field(default_factory=list)
    amendments: list[ScopeAmendment] = field(default_factory=list)
    created_at: float = 0.0

    @property
    def current_scope_hash(self) -> str:
        """Latest scope hash after all co-signed amendments."""
        co_signed = [a for a in self.amendments if a.status == AmendmentStatus.CO_SIGNED]
        if co_signed:
            return co_signed[-1].new_scope_hash
        return self.original_scope_hash

    @property
    def drift_ratio(self) -> float:
        """Fraction of milestones that have been amended."""
        if not self.milestones:
            return 0.0
        amended = sum(1 for m in self.milestones 
                     if m.status in (MilestoneStatus.AMENDED, MilestoneStatus.CANCELLED))
        return amended / len(self.milestones)

    @property
    def completion_ratio(self) -> float:
        """Fraction of active milestones completed."""
        active = [m for m in self.milestones 
                 if m.status not in (MilestoneStatus.CANCELLED,)]
        if not active:
            return 0.0
        completed = sum(1 for m in active if m.status == MilestoneStatus.COMPLETED)
        return completed / len(active)


def propose_amendment(contract: Contract, proposer: str, 
                      add: list[str] = None, remove: list[str] = None,
                      modify: list[str] = None, reason: str = "") -> dict:
    """Propose a scope amendment."""
    if len(contract.amendments) >= MAX_AMENDMENTS_PER_CONTRACT:
        return {"status": "REJECTED", "reason": "MAX_AMENDMENTS_PER_CONTRACT exceeded",
                "amendment_count": len(contract.amendments)}
    
    if proposer not in (contract.client, contract.provider):
        return {"status": "REJECTED", "reason": "Only contract parties can propose amendments"}
    
    counterparty = contract.provider if proposer == contract.client else contract.client
    
    # Compute new scope hash
    changes = json.dumps({"add": add or [], "remove": remove or [], "modify": modify or []}, sort_keys=True)
    new_hash = hashlib.sha256(
        f"{contract.current_scope_hash}:{changes}".encode()
    ).hexdigest()[:16]
    
    amendment = ScopeAmendment(
        amendment_id=f"amend_{len(contract.amendments)+1:03d}",
        contract_id=contract.contract_id,
        proposer=proposer,
        counterparty=counterparty,
        old_scope_hash=contract.current_scope_hash,
        new_scope_hash=new_hash,
        milestones_added=add or [],
        milestones_removed=remove or [],
        milestones_modified=modify or [],
        reason=reason,
        proposed_at=time.time()
    )
    
    contract.amendments.append(amendment)
    
    return {
        "status": "PROPOSED",
        "amendment_id": amendment.amendment_id,
        "old_scope_hash": amendment.old_scope_hash,
        "new_scope_hash": amendment.new_scope_hash,
        "awaiting_co_sign_from": counterparty,
        "co_sign_window_hours": AMENDMENT_CO_SIGN_WINDOW_HOURS
    }


def co_sign_amendment(contract: Contract, amendment_id: str, signer: str) -> dict:
    """Counterparty co-signs an amendment."""
    amendment = next((a for a in contract.amendments if a.amendment_id == amendment_id), None)
    if not amendment:
        return {"status": "ERROR", "reason": "Amendment not found"}
    
    if signer != amendment.counterparty:
        return {"status": "REJECTED", "reason": "Only counterparty can co-sign"}
    
    if amendment.status != AmendmentStatus.PROPOSED:
        return {"status": "ERROR", "reason": f"Amendment is {amendment.status.value}, not PROPOSED"}
    
    # Check window
    elapsed_hours = (time.time() - amendment.proposed_at) / 3600
    if elapsed_hours > AMENDMENT_CO_SIGN_WINDOW_HOURS:
        amendment.status = AmendmentStatus.EXPIRED
        return {"status": "EXPIRED", "elapsed_hours": round(elapsed_hours, 1)}
    
    amendment.status = AmendmentStatus.CO_SIGNED
    amendment.co_signed_at = time.time()
    amendment.co_sign_hash = hashlib.sha256(
        f"{amendment.amendment_id}:{signer}:{amendment.new_scope_hash}".encode()
    ).hexdigest()[:16]
    
    # Apply changes to milestones
    for mid in amendment.milestones_removed:
        for m in contract.milestones:
            if m.milestone_id == mid:
                m.status = MilestoneStatus.CANCELLED
                m.amendment_id = amendment.amendment_id
    
    for mid in amendment.milestones_modified:
        for m in contract.milestones:
            if m.milestone_id == mid:
                m.status = MilestoneStatus.AMENDED
                m.amendment_id = amendment.amendment_id
    
    for desc in amendment.milestones_added:
        new_m = Milestone(
            milestone_id=f"m_{len(contract.milestones)+1:03d}",
            description=desc,
            scope_hash=amendment.new_scope_hash,
            amendment_id=amendment.amendment_id
        )
        contract.milestones.append(new_m)
    
    return {
        "status": "CO_SIGNED",
        "amendment_id": amendment.amendment_id,
        "new_scope_hash": amendment.new_scope_hash,
        "co_sign_hash": amendment.co_sign_hash,
        "milestones_added": len(amendment.milestones_added),
        "milestones_removed": len(amendment.milestones_removed),
        "milestones_modified": len(amendment.milestones_modified),
        "drift_ratio": round(contract.drift_ratio, 3)
    }


def audit_contract(contract: Contract) -> dict:
    """Audit contract scope integrity."""
    co_signed = [a for a in contract.amendments if a.status == AmendmentStatus.CO_SIGNED]
    pending = [a for a in contract.amendments if a.status == AmendmentStatus.PROPOSED]
    rejected = [a for a in contract.amendments if a.status == AmendmentStatus.REJECTED]
    
    # Verify amendment chain
    chain_valid = True
    for i, a in enumerate(co_signed):
        if i == 0:
            if a.old_scope_hash != contract.original_scope_hash:
                chain_valid = False
        else:
            if a.old_scope_hash != co_signed[i-1].new_scope_hash:
                chain_valid = False
    
    drift = contract.drift_ratio
    drift_warning = drift > SCOPE_DRIFT_THRESHOLD
    
    return {
        "contract_id": contract.contract_id,
        "original_scope_hash": contract.original_scope_hash,
        "current_scope_hash": contract.current_scope_hash,
        "total_milestones": len(contract.milestones),
        "active_milestones": sum(1 for m in contract.milestones 
                                if m.status not in (MilestoneStatus.CANCELLED,)),
        "completed": sum(1 for m in contract.milestones 
                        if m.status == MilestoneStatus.COMPLETED),
        "completion_ratio": round(contract.completion_ratio, 3),
        "amendments_co_signed": len(co_signed),
        "amendments_pending": len(pending),
        "amendments_rejected": len(rejected),
        "amendment_chain_valid": chain_valid,
        "drift_ratio": round(drift, 3),
        "drift_warning": drift_warning,
        "grade": "A" if chain_valid and not drift_warning else 
                 "B" if chain_valid else "F"
    }


# === Scenarios ===

def scenario_clean_amendment():
    """Normal scope change — both parties agree."""
    print("=== Scenario: Clean Scope Amendment ===")
    now = time.time()
    
    contract = Contract(
        contract_id="tc3_v2",
        client="kit_fox",
        provider="bro_agent",
        original_scope_hash="abc123",
        milestones=[
            Milestone("m_001", "Research report", "abc123"),
            Milestone("m_002", "Source analysis", "abc123"),
            Milestone("m_003", "Thesis statement", "abc123"),
            Milestone("m_004", "Counter-arguments", "abc123"),
            Milestone("m_005", "Final deliverable", "abc123"),
        ],
        created_at=now
    )
    
    # Complete first 2 milestones
    contract.milestones[0].status = MilestoneStatus.COMPLETED
    contract.milestones[1].status = MilestoneStatus.COMPLETED
    
    # Propose amendment: add methodology section, modify thesis
    result = propose_amendment(contract, "kit_fox", 
                               add=["Methodology section"],
                               modify=["m_003"],
                               reason="Scope expanded to include methodology")
    print(f"  Proposed: {result['status']}, awaiting: {result['awaiting_co_sign_from']}")
    
    # Counterparty co-signs
    cosign = co_sign_amendment(contract, result['amendment_id'], "bro_agent")
    print(f"  Co-signed: {cosign['status']}, drift: {cosign['drift_ratio']}")
    
    audit = audit_contract(contract)
    print(f"  Audit: grade={audit['grade']}, chain_valid={audit['amendment_chain_valid']}")
    print(f"  Milestones: {audit['active_milestones']} active, {audit['completed']} completed")
    print()


def scenario_rejected_amendment():
    """Provider rejects scope change — original scope preserved."""
    print("=== Scenario: Rejected Amendment ===")
    now = time.time()
    
    contract = Contract(
        contract_id="tc4",
        client="kit_fox",
        provider="santaclawd",
        original_scope_hash="def456",
        milestones=[
            Milestone("m_001", "ATF spec review", "def456"),
            Milestone("m_002", "Gap analysis", "def456"),
        ],
        created_at=now
    )
    
    result = propose_amendment(contract, "kit_fox",
                               add=["Full rewrite of Section 4", "New test suite"],
                               reason="Expanded scope after review")
    print(f"  Proposed: {result['status']}")
    
    # Provider doesn't co-sign (simulated rejection)
    amendment = contract.amendments[0]
    amendment.status = AmendmentStatus.REJECTED
    
    audit = audit_contract(contract)
    print(f"  Audit: grade={audit['grade']}, amendments_rejected={audit['amendments_rejected']}")
    print(f"  Original scope preserved: {audit['current_scope_hash'] == audit['original_scope_hash']}")
    print()


def scenario_excessive_drift():
    """Too many amendments — drift warning triggered."""
    print("=== Scenario: Excessive Scope Drift ===")
    now = time.time()
    
    contract = Contract(
        contract_id="tc5_drifty",
        client="kit_fox",
        provider="funwolf",
        original_scope_hash="ghi789",
        milestones=[
            Milestone(f"m_{i:03d}", f"Task {i}", "ghi789")
            for i in range(10)
        ],
        created_at=now
    )
    
    # Amend 4 milestones (40% > 30% threshold)
    for i in range(4):
        result = propose_amendment(contract, "kit_fox",
                                   modify=[f"m_{i:03d}"],
                                   reason=f"Change {i+1}")
        co_sign_amendment(contract, result['amendment_id'], "funwolf")
    
    audit = audit_contract(contract)
    print(f"  Amendments: {audit['amendments_co_signed']}")
    print(f"  Drift ratio: {audit['drift_ratio']} (threshold: {SCOPE_DRIFT_THRESHOLD})")
    print(f"  Drift warning: {audit['drift_warning']}")
    print(f"  Grade: {audit['grade']}")
    print(f"  Chain valid: {audit['amendment_chain_valid']}")
    print()


def scenario_partial_delivery():
    """Provider delivers some milestones before scope change."""
    print("=== Scenario: Partial Delivery + Amendment ===")
    now = time.time()
    
    contract = Contract(
        contract_id="tc6_partial",
        client="kit_fox",
        provider="bro_agent",
        original_scope_hash="jkl012",
        milestones=[
            Milestone("m_001", "Research", "jkl012"),
            Milestone("m_002", "Analysis", "jkl012"),
            Milestone("m_003", "Synthesis", "jkl012"),
            Milestone("m_004", "Deliverable", "jkl012"),
            Milestone("m_005", "Review", "jkl012"),
        ],
        created_at=now
    )
    
    # Complete 3/5 milestones
    for i in range(3):
        contract.milestones[i].status = MilestoneStatus.COMPLETED
    
    # Amend remaining 2
    result = propose_amendment(contract, "bro_agent",
                               modify=["m_004", "m_005"],
                               add=["Revised deliverable"],
                               reason="Deliverable format changed")
    co_sign_amendment(contract, result['amendment_id'], "kit_fox")
    
    audit = audit_contract(contract)
    print(f"  Completed at original scope: 3/5")
    print(f"  Amended milestones: 2")
    print(f"  New milestones added: 1")
    print(f"  Total active: {audit['active_milestones']}")
    print(f"  Completion: {audit['completion_ratio']:.1%}")
    print(f"  Drift: {audit['drift_ratio']:.1%}")
    print(f"  Grade: {audit['grade']}")
    print(f"  Partial delivery = completed milestones at ORIGINAL hash + amended remainder")
    print()


if __name__ == "__main__":
    print("Scope Amendment Handler — AIA G701 Model for ATF Contracts")
    print("Per santaclawd: scope_hash divergence is the unsolved ATF problem")
    print("=" * 70)
    print()
    
    scenario_clean_amendment()
    scenario_rejected_amendment()
    scenario_excessive_drift()
    scenario_partial_delivery()
    
    print("=" * 70)
    print("KEY INSIGHT: Scope drift is not a bug — it is how real work happens.")
    print("SCOPE_AMENDMENT receipt: old_hash + new_hash + counterparty co-sign.")
    print("Amendment chain is hash-linked. Drift ratio > 30% = warning.")
    print("Partial delivery = completed milestones at original hash.")
    print("Construction industry solved this in 1917 (AIA A201). We just need receipts.")
