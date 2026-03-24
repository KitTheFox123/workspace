#!/usr/bin/env python3
"""
soft-cascade-recovery.py — SOFT_CASCADE recovery for ATF V1.1.

Per santaclawd: four primitives confirmed (PROBE_TIMEOUT, ALLEGED, CO_GRADER, DELEGATION).
Gap: SOFT_CASCADE recovery — what happens after DEGRADED?

Recovery states:
  HEALTHY → DEGRADED (upstream fails) → SUSPENDED (grace expires) → RECOVERED | REVOKED

Key insight from RFC 6298 (Jacobson-Karels): exponential backoff for retry intervals.
Re-attestation is not a binary flip — it's a gradual trust rebuild.

Lambda for ALLEGED decay = SPEC_CONSTANT (0.1, halflife ~7h).
CO_GRADER inherits decay curve, does NOT reset (laundering prevention).
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustState(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"        # Upstream failed, within grace
    SUSPENDED = "SUSPENDED"      # Grace expired, no new receipts
    RECOVERY = "RECOVERY"        # Re-attestation in progress
    RECOVERED = "RECOVERED"      # Trust rebuilt
    REVOKED = "REVOKED"         # Permanent termination


class RecoveryPhase(Enum):
    PROBE = "PROBE"              # Liveness check (PROBE_TIMEOUT primitive)
    RE_ATTEST = "RE_ATTEST"      # Fresh attestation required
    OBSERVATION = "OBSERVATION"  # Behavioral monitoring period
    GRADUATED = "GRADUATED"      # Full trust restored


# SPEC_CONSTANTS
GRACE_PERIOD_HOURS = 72          # Genesis constant: time in DEGRADED before SUSPENDED
ALLEGED_DECAY_LAMBDA = 0.1       # Halflife ~7h for ALLEGED receipt weight
MIN_RECOVERY_RECEIPTS = 10       # Minimum receipts to exit OBSERVATION
RECOVERY_OBSERVATION_DAYS = 7    # Minimum observation window
PROBE_TIMEOUT_INITIAL_MS = 5000  # Jacobson-Karels initial RTO
PROBE_BACKOFF_FACTOR = 2.0       # RFC 6298 exponential backoff
PROBE_MAX_RETRIES = 5
MAX_DELEGATION_DEPTH = 3


@dataclass
class AgentTrustRecord:
    agent_id: str
    state: TrustState = TrustState.HEALTHY
    grade: str = "B"
    degraded_at: Optional[float] = None
    suspended_at: Optional[float] = None
    recovery_started_at: Optional[float] = None
    recovery_phase: Optional[RecoveryPhase] = None
    recovery_receipts: int = 0
    grader_id: Optional[str] = None
    grader_changed_at: Optional[float] = None
    alleged_decay_start: Optional[float] = None  # When ALLEGED evidence began aging
    delegation_depth: int = 0
    probe_attempts: int = 0
    last_probe_at: Optional[float] = None


@dataclass
class RecoveryPlan:
    agent_id: str
    phases: list[dict]
    estimated_days: float
    grade_trajectory: list[str]
    risk_factors: list[str]


def alleged_weight(t_elapsed_hours: float, lambda_: float = ALLEGED_DECAY_LAMBDA) -> float:
    """
    ALLEGED receipt weight decays exponentially.
    
    w = 0.5 * exp(-lambda * T)
    At T=0: w=0.5 (starts at half weight — ALLEGED, not CONFIRMED)
    At T=7h: w≈0.25 (halflife)
    At T=24h: w≈0.045
    
    Lambda is SPEC_CONSTANT, NOT grader-defined.
    """
    return 0.5 * math.exp(-lambda_ * t_elapsed_hours)


def probe_timeout_ms(attempt: int) -> float:
    """
    Jacobson-Karels exponential backoff for probe timeouts.
    
    RTO = initial * backoff^attempt
    RFC 6298: RTO doubles on each retry.
    """
    return PROBE_TIMEOUT_INITIAL_MS * (PROBE_BACKOFF_FACTOR ** attempt)


def co_grader_inherits_decay(record: AgentTrustRecord, new_grader_id: str, now: float) -> dict:
    """
    CO_GRADER inherits decay curve from previous grader.
    
    Key insight (santaclawd): decay is evidence staleness, not grader state.
    Resetting would let grader rotation launder stale evidence.
    """
    if record.alleged_decay_start:
        elapsed_hours = (now - record.alleged_decay_start) / 3600
        inherited_weight = alleged_weight(elapsed_hours)
    else:
        elapsed_hours = 0
        inherited_weight = 0.5
    
    return {
        "new_grader": new_grader_id,
        "inherited_decay_start": record.alleged_decay_start,
        "elapsed_hours": round(elapsed_hours, 2),
        "inherited_weight": round(inherited_weight, 4),
        "reset_prevented": True,
        "reason": "decay tracks evidence staleness, not grader identity"
    }


def delegation_double_decay(base_weight: float, delegation_depth: int) -> float:
    """
    ALLEGED + DELEGATION = compounding decay.
    
    Each delegation hop attenuates by 1 grade level.
    Combined with time decay: double uncertainty.
    """
    hop_attenuation = max(0, 1.0 - (delegation_depth * 0.25))
    return base_weight * hop_attenuation


def transition_state(record: AgentTrustRecord, now: float) -> dict:
    """Evaluate and transition trust state."""
    actions = []
    
    if record.state == TrustState.HEALTHY:
        return {"state": "HEALTHY", "actions": [], "next_check": "on_event"}
    
    if record.state == TrustState.DEGRADED:
        if record.degraded_at:
            elapsed_hours = (now - record.degraded_at) / 3600
            remaining_hours = GRACE_PERIOD_HOURS - elapsed_hours
            
            if remaining_hours <= 0:
                record.state = TrustState.SUSPENDED
                record.suspended_at = now
                actions.append("GRACE_EXPIRED → SUSPENDED")
                actions.append("No new receipts accepted")
                actions.append("Challenge window OPEN (72h)")
            else:
                actions.append(f"DEGRADED: {remaining_hours:.1f}h remaining in grace")
                actions.append("Receipts accepted at DEGRADED weight")
    
    if record.state == TrustState.SUSPENDED:
        actions.append("SUSPENDED: awaiting RE_ATTESTATION_REQUEST or REVOCATION")
        actions.append("No new receipts")
        actions.append("Existing receipts retain original grade")
    
    if record.state == TrustState.RECOVERY:
        if record.recovery_phase == RecoveryPhase.PROBE:
            rto = probe_timeout_ms(record.probe_attempts)
            actions.append(f"PROBE phase: attempt {record.probe_attempts}, timeout {rto:.0f}ms")
            if record.probe_attempts >= PROBE_MAX_RETRIES:
                actions.append("PROBE_FAILED → candidate for REVOCATION")
        
        elif record.recovery_phase == RecoveryPhase.RE_ATTEST:
            actions.append("RE_ATTEST: fresh attestation from independent grader required")
        
        elif record.recovery_phase == RecoveryPhase.OBSERVATION:
            if record.recovery_started_at:
                obs_days = (now - record.recovery_started_at) / 86400
                actions.append(f"OBSERVATION: {record.recovery_receipts}/{MIN_RECOVERY_RECEIPTS} receipts, "
                             f"{obs_days:.1f}/{RECOVERY_OBSERVATION_DAYS}d elapsed")
                
                if (record.recovery_receipts >= MIN_RECOVERY_RECEIPTS and 
                    obs_days >= RECOVERY_OBSERVATION_DAYS):
                    record.state = TrustState.RECOVERED
                    record.recovery_phase = RecoveryPhase.GRADUATED
                    actions.append("GRADUATED → RECOVERED")
    
    return {
        "state": record.state.value,
        "phase": record.recovery_phase.value if record.recovery_phase else None,
        "actions": actions
    }


def build_recovery_plan(record: AgentTrustRecord) -> RecoveryPlan:
    """Build phased recovery plan."""
    phases = [
        {
            "phase": "PROBE",
            "duration_hours": 1,
            "description": "Liveness verification via Jacobson-Karels SRTT",
            "success_criteria": "Response within RTO",
            "max_retries": PROBE_MAX_RETRIES
        },
        {
            "phase": "RE_ATTEST",
            "duration_hours": 24,
            "description": "Fresh attestation from independent grader",
            "success_criteria": "New grader (different operator) issues grade",
            "requirement": "Grader MUST NOT share operator with agent"
        },
        {
            "phase": "OBSERVATION",
            "duration_days": RECOVERY_OBSERVATION_DAYS,
            "description": f"Behavioral monitoring: {MIN_RECOVERY_RECEIPTS}+ receipts",
            "success_criteria": f"{MIN_RECOVERY_RECEIPTS} receipts over {RECOVERY_OBSERVATION_DAYS}d",
            "grade_ceiling": "B"  # Cannot return to A immediately
        },
        {
            "phase": "GRADUATED",
            "description": "Full trust restored. Grade ceiling removed after 30d clean.",
            "grade_ceiling_removed_after_days": 30
        }
    ]
    
    risk_factors = []
    if record.delegation_depth > 0:
        risk_factors.append(f"Delegation depth {record.delegation_depth}: double-decay applies")
    if record.alleged_decay_start:
        elapsed = (time.time() - record.alleged_decay_start) / 3600
        if elapsed > 24:
            risk_factors.append(f"ALLEGED evidence {elapsed:.0f}h old: weight={alleged_weight(elapsed):.4f}")
    
    grade_trajectory = ["SUSPENDED", "D", "C", "B", "B→A after 30d"]
    
    return RecoveryPlan(
        agent_id=record.agent_id,
        phases=phases,
        estimated_days=RECOVERY_OBSERVATION_DAYS + 2,  # probe + re-attest + observation
        grade_trajectory=grade_trajectory,
        risk_factors=risk_factors
    )


# === Scenarios ===

def scenario_graceful_recovery():
    """Normal SOFT_CASCADE: DEGRADED → SUSPENDED → RECOVERY → RECOVERED."""
    print("=== Scenario: Graceful SOFT_CASCADE Recovery ===")
    now = time.time()
    
    record = AgentTrustRecord(
        agent_id="recovering_agent",
        state=TrustState.DEGRADED,
        grade="B",
        degraded_at=now - 3600 * 80,  # 80h ago (past grace)
        grader_id="old_grader"
    )
    
    # Transition: should move to SUSPENDED
    result = transition_state(record, now)
    print(f"  State: {result['state']}")
    for a in result['actions']:
        print(f"    → {a}")
    
    # Start recovery
    record.state = TrustState.RECOVERY
    record.recovery_phase = RecoveryPhase.PROBE
    record.recovery_started_at = now
    
    # Probe succeeds
    print(f"  Probe timeout: {probe_timeout_ms(0):.0f}ms (attempt 0)")
    print(f"  Probe timeout: {probe_timeout_ms(1):.0f}ms (attempt 1)")
    
    # Build recovery plan
    plan = build_recovery_plan(record)
    print(f"  Recovery plan: {plan.estimated_days:.0f} days")
    print(f"  Grade trajectory: {' → '.join(plan.grade_trajectory)}")
    print()


def scenario_alleged_decay_curve():
    """ALLEGED receipt weight decay over time."""
    print("=== Scenario: ALLEGED Weight Decay ===")
    hours = [0, 1, 3, 7, 12, 24, 48, 72]
    for h in hours:
        w = alleged_weight(h)
        dw = delegation_double_decay(w, 2)  # 2-hop delegation
        print(f"  T+{h:2d}h: weight={w:.4f}  with 2-hop delegation={dw:.4f}")
    
    print(f"\n  Halflife: ~{math.log(2) / ALLEGED_DECAY_LAMBDA:.1f}h")
    print(f"  At 24h: weight={alleged_weight(24):.4f} (< 5% — effectively expired)")
    print()


def scenario_co_grader_inheritance():
    """CO_GRADER inherits decay, doesn't reset."""
    print("=== Scenario: CO_GRADER Inherits Decay ===")
    now = time.time()
    
    record = AgentTrustRecord(
        agent_id="test_agent",
        state=TrustState.DEGRADED,
        grade="C",
        grader_id="grader_A",
        alleged_decay_start=now - 3600 * 12  # 12h of decay
    )
    
    # New grader takes over
    inheritance = co_grader_inherits_decay(record, "grader_B", now)
    print(f"  Previous grader: grader_A")
    print(f"  New grader: {inheritance['new_grader']}")
    print(f"  Elapsed: {inheritance['elapsed_hours']}h")
    print(f"  Inherited weight: {inheritance['inherited_weight']}")
    print(f"  Reset prevented: {inheritance['reset_prevented']}")
    print(f"  Reason: {inheritance['reason']}")
    print()


def scenario_probe_backoff():
    """Jacobson-Karels exponential backoff for probes."""
    print("=== Scenario: Probe Backoff (RFC 6298) ===")
    for i in range(PROBE_MAX_RETRIES + 1):
        rto = probe_timeout_ms(i)
        print(f"  Attempt {i}: RTO = {rto:.0f}ms ({rto/1000:.1f}s)")
    print(f"\n  Max retries: {PROBE_MAX_RETRIES}")
    print(f"  Total worst-case: {sum(probe_timeout_ms(i) for i in range(PROBE_MAX_RETRIES+1))/1000:.1f}s")
    print()


def scenario_delegation_double_decay():
    """ALLEGED + DELEGATION = compounding uncertainty."""
    print("=== Scenario: Double Decay (ALLEGED × DELEGATION) ===")
    for depth in range(MAX_DELEGATION_DEPTH + 1):
        w_fresh = delegation_double_decay(alleged_weight(0), depth)
        w_12h = delegation_double_decay(alleged_weight(12), depth)
        w_24h = delegation_double_decay(alleged_weight(24), depth)
        print(f"  Depth {depth}: fresh={w_fresh:.4f}  12h={w_12h:.4f}  24h={w_24h:.4f}")
    print(f"\n  Key: depth 3 + 24h = {delegation_double_decay(alleged_weight(24), 3):.6f} (negligible)")
    print()


if __name__ == "__main__":
    print("SOFT_CASCADE Recovery — ATF V1.1 Trust State Machine")
    print("Per santaclawd: four primitives + SOFT_CASCADE = complete surface")
    print("=" * 70)
    print()
    
    scenario_graceful_recovery()
    scenario_alleged_decay_curve()
    scenario_co_grader_inheritance()
    scenario_probe_backoff()
    scenario_delegation_double_decay()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Lambda = SPEC_CONSTANT (0.1). Graders don't set their own decay rate.")
    print("2. CO_GRADER inherits decay. Reset = evidence laundering.")
    print("3. ALLEGED+DELEGATION = compounding uncertainty. Double-decay by design.")
    print("4. Recovery is graduated: PROBE → RE_ATTEST → OBSERVATION → GRADUATED.")
    print("5. Grade ceiling B during recovery. A requires 30d clean post-graduation.")
