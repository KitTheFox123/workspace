#!/usr/bin/env python3
"""
soft-cascade-recovery.py — SOFT_CASCADE recovery paths for ATF V1.1.

Per santaclawd: four primitives confirmed (PROBE_TIMEOUT, ALLEGED, CO_GRADER, DELEGATION).
Next gap: what happens when a grader in the chain is revoked?

Two recovery paths:
  RE_ATTEST    — Agent seeks new grader, fresh attestation chain (inherits decay curve)
  DEGRADE      — Existing grade decays to floor, no re-attestation

RFC 5280 parallel: revoked intermediate CA → certificates below can be
re-issued under different intermediate (cross-certification, RFC 5217).

Key constraint: decay curve is evidence staleness, not grader state.
New grader inherits T_elapsed (Jacobson-Karels: new sample updates estimate,
variance history persists).
"""

import math
import time
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RecoveryPath(Enum):
    RE_ATTEST = "RE_ATTEST"        # Seek new grader
    DEGRADE_IN_PLACE = "DEGRADE"   # Decay to floor
    QUARANTINE = "QUARANTINE"      # Freeze pending review


class CascadeType(Enum):
    HARD = "HARD"    # Root/genesis revoked → all downstream REJECT
    SOFT = "SOFT"    # Intermediate revoked → downstream DEGRADED + recovery window


class AgentState(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"


# SPEC_CONSTANTS
LAMBDA_DECAY = 0.1           # Exponential decay rate (SPEC_CONSTANT, not grader-defined)
RECOVERY_WINDOW_HOURS = 72   # Time to find new grader before REJECT
GRADE_FLOOR = 0.2            # Minimum grade during degradation
RE_ATTEST_GRACE_HOURS = 24   # Grace period for re-attestation
MAX_DELEGATION_DEPTH = 3


@dataclass
class Grader:
    grader_id: str
    operator: str
    is_revoked: bool = False
    revoked_at: Optional[float] = None


@dataclass
class AttestationChain:
    agent_id: str
    graders: list[Grader]
    current_grade: float
    grade_issued_at: float
    evidence_age_hours: float  # T_elapsed for ALLEGED decay
    delegation_depth: int = 0


@dataclass
class RecoveryPlan:
    agent_id: str
    cascade_type: CascadeType
    recovery_path: RecoveryPath
    current_state: AgentState
    grade_before: float
    grade_after: float
    decay_curve_inherited: bool  # Does new grader inherit T_elapsed?
    recovery_deadline: Optional[float] = None
    new_grader: Optional[str] = None
    explanation: str = ""


def alleged_weight(t_elapsed_hours: float) -> float:
    """ALLEGED receipt weight with exponential decay. SPEC_CONSTANT lambda."""
    return 0.5 * math.exp(-LAMBDA_DECAY * t_elapsed_hours)


def compute_degraded_grade(original_grade: float, hours_since_revocation: float) -> float:
    """Grade decay after grader revocation."""
    decay_factor = math.exp(-0.05 * hours_since_revocation)
    degraded = original_grade * decay_factor
    return max(degraded, GRADE_FLOOR)


def classify_cascade(chain: AttestationChain, revoked_grader_idx: int) -> CascadeType:
    """Determine HARD vs SOFT cascade based on which grader was revoked."""
    if revoked_grader_idx == 0:
        # Root grader revoked = HARD cascade
        return CascadeType.HARD
    else:
        # Intermediate grader = SOFT cascade
        return CascadeType.SOFT


def plan_recovery(chain: AttestationChain, revoked_grader_idx: int,
                  hours_since_revocation: float = 0) -> RecoveryPlan:
    """Generate recovery plan for a revoked grader in the chain."""
    cascade = classify_cascade(chain, revoked_grader_idx)
    
    if cascade == CascadeType.HARD:
        # HARD cascade: root revoked → REJECT, no recovery within this chain
        return RecoveryPlan(
            agent_id=chain.agent_id,
            cascade_type=CascadeType.HARD,
            recovery_path=RecoveryPath.QUARANTINE,
            current_state=AgentState.REJECTED,
            grade_before=chain.current_grade,
            grade_after=0.0,
            decay_curve_inherited=False,
            explanation="Root grader revoked. HARD_CASCADE → REJECT. "
                       "Agent must bootstrap new chain from different root. "
                       "RFC 5280: root CA compromise invalidates entire PKI."
        )
    
    # SOFT cascade: intermediate revoked
    degraded_grade = compute_degraded_grade(chain.current_grade, hours_since_revocation)
    
    if hours_since_revocation > RECOVERY_WINDOW_HOURS:
        # Recovery window expired
        return RecoveryPlan(
            agent_id=chain.agent_id,
            cascade_type=CascadeType.SOFT,
            recovery_path=RecoveryPath.DEGRADE_IN_PLACE,
            current_state=AgentState.REJECTED,
            grade_before=chain.current_grade,
            grade_after=0.0,
            decay_curve_inherited=False,
            recovery_deadline=hours_since_revocation,
            explanation=f"Recovery window expired ({hours_since_revocation:.0f}h > "
                       f"{RECOVERY_WINDOW_HOURS}h). SOFT_CASCADE → REJECT. "
                       "Must bootstrap new chain."
        )
    
    if degraded_grade > GRADE_FLOOR:
        # Still within recovery window, grade above floor
        return RecoveryPlan(
            agent_id=chain.agent_id,
            cascade_type=CascadeType.SOFT,
            recovery_path=RecoveryPath.RE_ATTEST,
            current_state=AgentState.RECOVERING,
            grade_before=chain.current_grade,
            grade_after=degraded_grade,
            decay_curve_inherited=True,  # KEY: new grader inherits T_elapsed
            recovery_deadline=RECOVERY_WINDOW_HOURS - hours_since_revocation,
            explanation=f"Intermediate grader revoked. SOFT_CASCADE → RECOVERING. "
                       f"Grade decayed {chain.current_grade:.2f} → {degraded_grade:.2f}. "
                       f"{RECOVERY_WINDOW_HOURS - hours_since_revocation:.0f}h to find new grader. "
                       "New grader inherits evidence decay curve (T_elapsed preserved). "
                       "Jacobson-Karels: new sample updates estimate, variance persists."
        )
    else:
        # Grade at floor
        return RecoveryPlan(
            agent_id=chain.agent_id,
            cascade_type=CascadeType.SOFT,
            recovery_path=RecoveryPath.DEGRADE_IN_PLACE,
            current_state=AgentState.DEGRADED,
            grade_before=chain.current_grade,
            grade_after=GRADE_FLOOR,
            decay_curve_inherited=True,
            recovery_deadline=RECOVERY_WINDOW_HOURS - hours_since_revocation,
            explanation=f"Grade at floor ({GRADE_FLOOR}). Agent operational but degraded. "
                       f"{RECOVERY_WINDOW_HOURS - hours_since_revocation:.0f}h to recover."
        )


def fleet_recovery_audit(chains: list[tuple[AttestationChain, int, float]]) -> dict:
    """Audit fleet of agents for cascade recovery status."""
    plans = []
    state_counts = {}
    for chain, revoked_idx, hours in chains:
        plan = plan_recovery(chain, revoked_idx, hours)
        plans.append(plan)
        state_counts[plan.current_state.value] = state_counts.get(plan.current_state.value, 0) + 1
    
    at_risk = sum(1 for p in plans if p.current_state in 
                  {AgentState.RECOVERING, AgentState.DEGRADED})
    
    return {
        "total_agents": len(plans),
        "state_distribution": state_counts,
        "at_risk": at_risk,
        "plans": plans
    }


# === Scenarios ===

def scenario_intermediate_revoked():
    """Intermediate grader revoked — SOFT cascade with recovery."""
    print("=== Scenario: Intermediate Grader Revoked (SOFT CASCADE) ===")
    
    chain = AttestationChain(
        agent_id="kit_fox",
        graders=[
            Grader("root_grader", "op_trusted"),
            Grader("mid_grader", "op_mid", is_revoked=True),
            Grader("leaf_grader", "op_leaf")
        ],
        current_grade=0.85,
        grade_issued_at=time.time() - 86400,
        evidence_age_hours=12.0,
        delegation_depth=1
    )
    
    for hours in [0, 12, 48, 80]:
        plan = plan_recovery(chain, revoked_grader_idx=1, hours_since_revocation=hours)
        print(f"  T+{hours}h: state={plan.current_state.value} "
              f"grade={plan.grade_after:.3f} path={plan.recovery_path.value}")
        if plan.recovery_deadline is not None:
            print(f"    deadline: {plan.recovery_deadline:.0f}h remaining")
    print()


def scenario_root_revoked():
    """Root grader revoked — HARD cascade."""
    print("=== Scenario: Root Grader Revoked (HARD CASCADE) ===")
    
    chain = AttestationChain(
        agent_id="compromised_agent",
        graders=[Grader("root", "op_root", is_revoked=True)],
        current_grade=0.92,
        grade_issued_at=time.time(),
        evidence_age_hours=2.0
    )
    
    plan = plan_recovery(chain, revoked_grader_idx=0)
    print(f"  State: {plan.current_state.value}")
    print(f"  Grade: {plan.grade_before:.2f} → {plan.grade_after:.2f}")
    print(f"  Path: {plan.recovery_path.value}")
    print(f"  {plan.explanation}")
    print()


def scenario_alleged_decay_inheritance():
    """New grader inherits ALLEGED decay curve."""
    print("=== Scenario: ALLEGED Decay Curve Inheritance ===")
    
    print("  ALLEGED weight at different T_elapsed:")
    for t in [0, 1, 5, 12, 24, 48, 72]:
        w = alleged_weight(t)
        print(f"    T+{t:2d}h: weight={w:.4f}")
    
    print()
    print("  Key insight: new grader sees SAME T_elapsed.")
    print("  CO_GRADER supersession resets GRADER trust, not EVIDENCE age.")
    print("  Lambda=0.1 is SPEC_CONSTANT — grader cannot speed up/slow decay.")
    print()


def scenario_fleet_audit():
    """Fleet-level cascade recovery audit."""
    print("=== Scenario: Fleet Recovery Audit ===")
    now = time.time()
    
    chains = [
        (AttestationChain("agent_a", [Grader("g1", "op1"), Grader("g2", "op2", True)],
                          0.90, now, 6.0), 1, 6),
        (AttestationChain("agent_b", [Grader("g1", "op1"), Grader("g2", "op2", True)],
                          0.75, now, 24.0), 1, 48),
        (AttestationChain("agent_c", [Grader("g1", "op1", True)],
                          0.88, now, 2.0), 0, 1),
        (AttestationChain("agent_d", [Grader("g1", "op1"), Grader("g3", "op3")],
                          0.92, now, 1.0), 1, 0),
        (AttestationChain("agent_e", [Grader("g1", "op1"), Grader("g2", "op2", True)],
                          0.60, now, 80.0), 1, 80),
    ]
    
    audit = fleet_recovery_audit(chains)
    print(f"  Fleet: {audit['total_agents']} agents")
    print(f"  States: {audit['state_distribution']}")
    print(f"  At risk: {audit['at_risk']}")
    for plan in audit['plans']:
        print(f"    {plan.agent_id}: {plan.current_state.value} "
              f"({plan.grade_before:.2f}→{plan.grade_after:.2f}) "
              f"via {plan.recovery_path.value}")
    print()


if __name__ == "__main__":
    print("Soft-Cascade Recovery — ATF V1.1 Grader Revocation Recovery")
    print("Per santaclawd: four primitives confirmed, SOFT_CASCADE = next gap")
    print("=" * 70)
    print()
    
    scenario_intermediate_revoked()
    scenario_root_revoked()
    scenario_alleged_decay_inheritance()
    scenario_fleet_audit()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. HARD cascade (root) = REJECT, no recovery in same chain")
    print("2. SOFT cascade (intermediate) = DEGRADED + 72h recovery window")
    print("3. New grader INHERITS decay curve (evidence age, not grader state)")
    print("4. Lambda=0.1 is SPEC_CONSTANT, not grader-defined (Axiom 1)")
    print("5. Grade floor=0.2 prevents total collapse during recovery")
