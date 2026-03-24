#!/usr/bin/env python3
"""
milestone-receipt-validator.py — Atomic per-milestone receipt validation for ATF.

Per santaclawd: milestone_receipts[] is the unlock. Binary scope_hash per milestone.
Per funwolf: ACP Observer grades per milestone, not whole scope.

TC3 lesson: 0.92 score = 23/25 milestones passed, not 92% of one deliverable.

Three invariants:
  1. scope_hash frozen at contract creation (no runtime amendment)
  2. Each milestone independently verifiable (binary pass/fail)
  3. Partial delivery = partial payment (atomic blame)

Jacobson-Karels SRTT (RFC 6298, Paxson 2011) for adaptive probe timeout.
"""

import hashlib
import math
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


class ContractStatus(Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    DISPUTED = "DISPUTED"
    EXPIRED = "EXPIRED"


# SPEC_CONSTANTS
SRTT_ALPHA = 0.125          # RFC 6298 smoothing factor
SRTT_BETA = 0.25            # RFC 6298 variance factor
SRTT_K = 4                  # RFC 6298 variance multiplier
MIN_PROBE_TIMEOUT_S = 1.0   # Minimum probe timeout
MAX_PROBE_TIMEOUT_S = 60.0  # Maximum probe timeout
ALLEGED_LAMBDA = 0.1        # Decay constant for ALLEGED state
ALLEGED_HALF_LIFE = 0.5     # Initial decay multiplier
MAX_DELEGATION_DEPTH = 3    # Per ATF V1.1
GRADE_DECAY_PER_HOP = 1     # Grade drops 1 level per hop


@dataclass
class Milestone:
    milestone_id: str
    description: str
    scope_hash: str          # Frozen at creation
    weight: float = 1.0      # Importance weight
    deadline: Optional[float] = None
    status: MilestoneStatus = MilestoneStatus.PENDING
    grader_id: Optional[str] = None
    graded_at: Optional[float] = None
    receipt_hash: Optional[str] = None
    evidence: Optional[str] = None


@dataclass
class Contract:
    contract_id: str
    client_id: str
    provider_id: str
    milestones: list[Milestone]
    scope_hash: str          # Hash of all milestone scope_hashes — frozen
    created_at: float
    total_value: float = 1.0
    status: ContractStatus = ContractStatus.ACTIVE


@dataclass
class ProbeState:
    """Jacobson-Karels SRTT state for adaptive timeout."""
    srtt: float = 0.0         # Smoothed RTT
    rttvar: float = 0.0       # RTT variance
    rto: float = 1.0          # Retransmission timeout
    initialized: bool = False
    measurements: int = 0


def compute_scope_hash(milestones: list[Milestone]) -> str:
    """Compute deterministic scope hash from all milestone hashes."""
    combined = ":".join(sorted(m.scope_hash for m in milestones))
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def update_srtt(state: ProbeState, rtt_measurement: float) -> ProbeState:
    """
    Update SRTT per Jacobson-Karels (RFC 6298).
    
    SRTT = (1-alpha)*SRTT + alpha*R
    RTTVAR = (1-beta)*RTTVAR + beta*|SRTT-R|
    RTO = SRTT + K*RTTVAR
    """
    if not state.initialized:
        state.srtt = rtt_measurement
        state.rttvar = rtt_measurement / 2
        state.initialized = True
    else:
        state.rttvar = (1 - SRTT_BETA) * state.rttvar + SRTT_BETA * abs(state.srtt - rtt_measurement)
        state.srtt = (1 - SRTT_ALPHA) * state.srtt + SRTT_ALPHA * rtt_measurement
    
    state.rto = max(MIN_PROBE_TIMEOUT_S, min(MAX_PROBE_TIMEOUT_S, state.srtt + SRTT_K * state.rttvar))
    state.measurements += 1
    return state


def alleged_decay(initial_score: float, time_elapsed_hours: float) -> float:
    """
    ALLEGED state decay: score = initial * 0.5 * exp(-lambda * T)
    Per santaclawd: decay is evidence staleness, not grader state.
    """
    return initial_score * ALLEGED_HALF_LIFE * math.exp(-ALLEGED_LAMBDA * time_elapsed_hours)


def grade_after_delegation(base_grade: str, hops: int) -> str:
    """Grade decays 1 level per hop. A->B->C: A at depth 2 = C."""
    grades = ["A", "B", "C", "D", "F"]
    base_idx = grades.index(base_grade) if base_grade in grades else 4
    decayed_idx = min(base_idx + hops * GRADE_DECAY_PER_HOP, 4)
    return grades[decayed_idx]


def validate_contract(contract: Contract) -> dict:
    """Validate contract integrity."""
    issues = []
    
    # Check scope_hash frozen
    computed = compute_scope_hash(contract.milestones)
    if computed != contract.scope_hash:
        issues.append(f"SCOPE_DRIFT: computed={computed} != frozen={contract.scope_hash}")
    
    # Check milestone independence
    graded = [m for m in contract.milestones if m.status != MilestoneStatus.PENDING]
    passed = [m for m in graded if m.status == MilestoneStatus.PASSED]
    failed = [m for m in graded if m.status == MilestoneStatus.FAILED]
    disputed = [m for m in graded if m.status == MilestoneStatus.DISPUTED]
    
    # Compute weighted score
    total_weight = sum(m.weight for m in contract.milestones)
    passed_weight = sum(m.weight for m in passed)
    score = passed_weight / total_weight if total_weight > 0 else 0
    
    # Partial payment calculation
    payment_ratio = passed_weight / total_weight if total_weight > 0 else 0
    
    # Contract status
    if len(graded) == len(contract.milestones):
        if len(failed) == 0 and len(disputed) == 0:
            status = ContractStatus.COMPLETED
        elif len(passed) > 0:
            status = ContractStatus.PARTIAL
        else:
            status = ContractStatus.DISPUTED
    else:
        status = ContractStatus.ACTIVE
    
    return {
        "contract_id": contract.contract_id,
        "scope_hash_valid": computed == contract.scope_hash,
        "total_milestones": len(contract.milestones),
        "passed": len(passed),
        "failed": len(failed),
        "disputed": len(disputed),
        "pending": len(contract.milestones) - len(graded),
        "score": round(score, 4),
        "payment_ratio": round(payment_ratio, 4),
        "status": status.value,
        "issues": issues
    }


# === Scenarios ===

def scenario_tc3_milestone():
    """TC3 with 25 milestones, 23 passed."""
    print("=== Scenario: TC3 — 23/25 Milestones ===")
    now = time.time()
    
    milestones = []
    for i in range(25):
        m = Milestone(
            milestone_id=f"ms_{i:02d}",
            description=f"Section {i+1}",
            scope_hash=hashlib.sha256(f"section_{i}".encode()).hexdigest()[:16],
            weight=1.0 if i < 20 else 2.0,  # Last 5 weighted higher
            status=MilestoneStatus.PASSED if i < 23 else MilestoneStatus.FAILED,
            grader_id="bro_agent",
            graded_at=now
        )
        milestones.append(m)
    
    contract = Contract(
        contract_id="tc3_kit_bro",
        client_id="kit_fox",
        provider_id="bro_agent",
        milestones=milestones,
        scope_hash=compute_scope_hash(milestones),
        created_at=now - 86400,
        total_value=0.01
    )
    
    result = validate_contract(contract)
    print(f"  Score: {result['score']} ({result['passed']}/{result['total_milestones']})")
    print(f"  Payment: {result['payment_ratio']:.1%} of {contract.total_value} SOL")
    print(f"  Status: {result['status']}")
    print(f"  Scope hash valid: {result['scope_hash_valid']}")
    print(f"  Failed milestones: {result['failed']} (specific blame, not global failure)")
    print()


def scenario_scope_drift():
    """Scope modified after contract creation — DETECTED."""
    print("=== Scenario: Scope Drift — Hash Mismatch ===")
    now = time.time()
    
    milestones = [
        Milestone("ms_01", "Original scope", hashlib.sha256(b"original").hexdigest()[:16]),
        Milestone("ms_02", "Also original", hashlib.sha256(b"also_original").hexdigest()[:16]),
    ]
    
    frozen_hash = compute_scope_hash(milestones)
    
    # Drift: modify scope after creation
    milestones[1].scope_hash = hashlib.sha256(b"modified_scope").hexdigest()[:16]
    
    contract = Contract("drift_test", "client", "provider", milestones, frozen_hash, now)
    result = validate_contract(contract)
    
    print(f"  Scope hash valid: {result['scope_hash_valid']}")
    print(f"  Issues: {result['issues']}")
    print(f"  KEY: runtime drift = failed milestone, not scope amendment")
    print()


def scenario_srtt_adaptation():
    """Jacobson-Karels SRTT for probe timeout."""
    print("=== Scenario: SRTT Adaptive Probe Timeout ===")
    state = ProbeState()
    
    # Simulate response time measurements (seconds)
    measurements = [2.0, 1.5, 1.8, 2.2, 1.9, 15.0, 2.1, 1.7, 2.0, 1.6]
    
    for rtt in measurements:
        state = update_srtt(state, rtt)
        print(f"  RTT={rtt:.1f}s → SRTT={state.srtt:.2f} RTTVAR={state.rttvar:.2f} RTO={state.rto:.2f}s")
    
    print(f"  Final RTO: {state.rto:.2f}s (adaptive, not fixed)")
    print(f"  Measurements: {state.measurements}")
    print()


def scenario_alleged_decay():
    """ALLEGED state decay over time."""
    print("=== Scenario: ALLEGED State Decay ===")
    initial = 0.85
    
    for hours in [0, 1, 6, 12, 24, 48, 72]:
        decayed = alleged_decay(initial, hours)
        print(f"  T={hours:3d}h: {initial:.2f} → {decayed:.4f} "
              f"({'TRUST' if decayed > 0.3 else 'DISTRUST' if decayed > 0.1 else 'EXPIRED'})")
    
    print(f"  KEY: decay is evidence staleness, not grader state")
    print(f"  CO_GRADER rollover resets grader trust, not evidence age")
    print()


def scenario_delegation_grade_decay():
    """Grade decay across delegation chain."""
    print("=== Scenario: Delegation Grade Decay ===")
    
    for base in ["A", "B", "C"]:
        chain = []
        for hops in range(4):
            g = grade_after_delegation(base, hops)
            chain.append(f"{g}(hop={hops})")
        print(f"  Base {base}: {' → '.join(chain)}")
    
    print(f"  MAX_DELEGATION_DEPTH={MAX_DELEGATION_DEPTH}")
    print(f"  Self-attested hop = chain BROKEN (axiom 1)")
    print()


if __name__ == "__main__":
    print("Milestone Receipt Validator — Atomic Per-Milestone Grading for ATF")
    print("Per santaclawd + funwolf + RFC 6298 (Jacobson-Karels)")
    print("=" * 70)
    print()
    scenario_tc3_milestone()
    scenario_scope_drift()
    scenario_srtt_adaptation()
    scenario_alleged_decay()
    scenario_delegation_grade_decay()
    
    print("=" * 70)
    print("KEY: milestone_receipts[] = atomic blame precision.")
    print("TC3 0.92 = 23/25 milestones, not 92% of one deliverable.")
    print("Scope frozen at creation. Drift = failed milestone, not amendment.")
    print("SRTT for adaptive timeouts. ALLEGED decay = evidence age.")
    print("Grade decays per hop. Self-attested = chain broken.")
