#!/usr/bin/env python3
"""
pre-assignment-anchor.py — Pre-assignment state commitment for delivery proof.

Based on:
- santaclawd: "delivery proof fails at state_before, not hashing"
- AutoPilotAI: 63 accepted bids → 0 payments on NEAR (expiry trap)
- Hoyte (2024): commit-reveal for intent binding

The problem: provider delivers work, requester disputes initial state.
hash(before||action||after) is vulnerable if state_before is bilateral.
Fix: requester commits hash(state_before) to chain BEFORE task assignment.
Timestamp proves ordering. No bilateral agreement required.

PayLock v2.1 addition: pre_assignment_hash slot, committed at fund time.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DisputeOutcome(Enum):
    REQUESTER_WINS = "requester_wins"
    PROVIDER_WINS = "provider_wins"
    AMBIGUOUS = "ambiguous"


@dataclass
class StateCommitment:
    state_hash: str
    timestamp: float
    committer: str  # Who committed (requester or provider)
    anchor_type: str  # "chain", "smtp", "isnad"


@dataclass 
class TaskContract:
    task_id: str
    requester: str
    provider: str
    pre_assignment_hash: Optional[str] = None  # Committed BEFORE assignment
    pre_assignment_ts: Optional[float] = None
    assignment_ts: Optional[float] = None
    delivery_hash: Optional[str] = None
    delivery_ts: Optional[float] = None
    
    def has_pre_anchor(self) -> bool:
        return (self.pre_assignment_hash is not None and 
                self.pre_assignment_ts is not None and
                self.pre_assignment_ts < (self.assignment_ts or float('inf')))
    
    def temporal_ordering_valid(self) -> bool:
        """pre_anchor < assignment < delivery."""
        ts = [t for t in [self.pre_assignment_ts, self.assignment_ts, self.delivery_ts] if t]
        return ts == sorted(ts) and len(ts) >= 2


def hash_state(state: dict) -> str:
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()[:16]


def resolve_dispute(contract: TaskContract, 
                     claimed_before: dict,
                     actual_delivery: dict) -> tuple[DisputeOutcome, str]:
    """Resolve delivery dispute using pre-assignment anchor."""
    
    if not contract.has_pre_anchor():
        # No pre-anchor: bilateral dispute, ambiguous
        return DisputeOutcome.AMBIGUOUS, "NO_PRE_ANCHOR: state_before disputed bilaterally"
    
    if not contract.temporal_ordering_valid():
        return DisputeOutcome.AMBIGUOUS, "TEMPORAL_VIOLATION: timestamps out of order"
    
    # Verify claimed state_before matches pre-committed hash
    claimed_hash = hash_state(claimed_before)
    if claimed_hash != contract.pre_assignment_hash:
        return DisputeOutcome.PROVIDER_WINS, \
            f"STATE_MISMATCH: requester claimed {claimed_hash} but committed {contract.pre_assignment_hash}"
    
    # Pre-anchor matches: requester's state_before is verified
    # Now check delivery against scope
    if actual_delivery:
        return DisputeOutcome.REQUESTER_WINS, \
            "DELIVERY_VERIFIED: state_before anchored, delivery auditable"
    
    return DisputeOutcome.AMBIGUOUS, "INSUFFICIENT_EVIDENCE"


def grade_contract(contract: TaskContract) -> tuple[str, str]:
    """Grade contract by pre-assignment anchoring."""
    if not contract.has_pre_anchor():
        return "F", "NO_ANCHOR"
    if not contract.temporal_ordering_valid():
        return "D", "TEMPORAL_VIOLATION"
    return "A", "PROPERLY_ANCHORED"


def main():
    print("=" * 70)
    print("PRE-ASSIGNMENT STATE ANCHOR")
    print("santaclawd: 'delivery proof fails at state_before, not hashing'")
    print("=" * 70)

    now = time.time()

    # Scenario 1: Properly anchored contract
    print("\n--- Scenario 1: Properly Anchored ---")
    state_before = {"repo": "isnad-rfc", "commit": "abc123", "files": 12}
    c1 = TaskContract(
        task_id="515ee459",
        requester="kit_fox",
        provider="bro_agent",
        pre_assignment_hash=hash_state(state_before),
        pre_assignment_ts=now - 3600,  # 1hr before assignment
        assignment_ts=now - 3000,
        delivery_hash=hash_state({"score": 9200}),
        delivery_ts=now,
    )
    grade, diag = grade_contract(c1)
    print(f"Contract: {c1.task_id}, Grade: {grade} ({diag})")
    print(f"Pre-anchor: {c1.pre_assignment_hash} @ t-3600")
    
    # Requester tries to dispute with DIFFERENT state_before
    fake_before = {"repo": "isnad-rfc", "commit": "def456", "files": 15}
    outcome, reason = resolve_dispute(c1, fake_before, {"score": 9200})
    print(f"Dispute (fake state_before): {outcome.value} — {reason}")

    # Honest dispute
    outcome2, reason2 = resolve_dispute(c1, state_before, {"score": 9200})
    print(f"Dispute (honest state_before): {outcome2.value} — {reason2}")

    # Scenario 2: No pre-anchor (NEAR-style)
    print("\n--- Scenario 2: No Pre-Anchor (NEAR AI Market) ---")
    c2 = TaskContract(
        task_id="near_job_42",
        requester="poster",
        provider="autopilot",
        assignment_ts=now - 3000,
        delivery_hash=hash_state({"result": "done"}),
        delivery_ts=now,
    )
    grade2, diag2 = grade_contract(c2)
    print(f"Contract: {c2.task_id}, Grade: {grade2} ({diag2})")
    outcome3, reason3 = resolve_dispute(c2, {"requirements": "v1"}, {"result": "done"})
    print(f"Dispute: {outcome3.value} — {reason3}")
    print("→ AutoPilotAI's 63 accepted bids, 0 payments: no pre-anchor = requester always wins")

    # Scenario 3: Temporal violation (backdated anchor)
    print("\n--- Scenario 3: Backdated Anchor ---")
    c3 = TaskContract(
        task_id="backdated",
        requester="cheater",
        provider="honest_agent",
        pre_assignment_hash=hash_state({"fake": True}),
        pre_assignment_ts=now + 100,  # AFTER assignment (backdated)
        assignment_ts=now - 3000,
        delivery_ts=now,
    )
    grade3, diag3 = grade_contract(c3)
    print(f"Contract: {c3.task_id}, Grade: {grade3} ({diag3})")

    # Summary
    print("\n--- PayLock ABI v2.1 Addition ---")
    print("pre_assignment_hash: bytes32  // Committed at fund time")
    print("pre_assignment_ts:   uint64   // Timestamp (external witness)")
    print("assignment_ts:       uint64   // When task was assigned")
    print()
    print("Temporal ordering: pre_anchor < assignment < delivery")
    print("Dispute: compare chain entry vs claimed state_before")
    print("No bilateral agreement required — just temporal ordering.")
    print()
    print("--- Marketplace Grades ---")
    print(f"{'Platform':<20} {'Pre-anchor':<15} {'Grade'}")
    print("-" * 50)
    platforms = [
        ("NEAR AI Market", "None", "F"),
        ("PayLock v1", "None", "F"),
        ("PayLock v2.1", "At fund time", "A"),
        ("TC4 (actual)", "Email thread", "B"),
    ]
    for name, anchor, g in platforms:
        print(f"{name:<20} {anchor:<15} {g}")


if __name__ == "__main__":
    main()
