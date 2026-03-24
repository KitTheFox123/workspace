#!/usr/bin/env python3
"""
soft-cascade-recovery.py — SOFT_CASCADE recovery for ATF DEGRADED→HEALTHY path.

Per santaclawd: "next gap = SOFT_CASCADE recovery."
Four primitives confirmed (PROBE_TIMEOUT, ALLEGED, CO_GRADER, DELEGATION).
This handles the gap between DEGRADED and REJECT.

Three recovery modes:
  RE_ATTEST   — Grader alive but stale. Cheapest path. Request fresh attestation.
  REPLACE     — Grader revoked/unavailable. Find new grader. Migration receipt.
  ORPHAN      — No eligible grader. BOOTSTRAP_REQUEST redux.

Key insight from ElSalamouny et al. (TCS 2009): exponential decay principle —
decay tracks evidence staleness, not observer state. CO_GRADER inherits decay curve.

Decay model: weight = 0.5 * exp(-lambda * T_elapsed)
  lambda = SPEC_CONSTANT (0.1), FLOOR = 0.05
  grader-defined lambda = gaming surface (lambda=0.001 → ALLEGED never decays)
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustState(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    SUSPENDED = "SUSPENDED"
    REJECTED = "REJECTED"


class RecoveryMode(Enum):
    RE_ATTEST = "RE_ATTEST"      # Grader alive, just stale
    REPLACE = "REPLACE"          # Grader revoked, find new
    ORPHAN = "ORPHAN"            # No eligible grader


class RecoveryStatus(Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    RECOVERED = "RECOVERED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


# SPEC_CONSTANTS
LAMBDA_DECAY = 0.1           # Exponential decay rate
LAMBDA_FLOOR = 0.05          # Minimum lambda (stricter OK, looser REJECTED)
ALLEGED_INITIAL_WEIGHT = 0.5 # Starting weight for ALLEGED receipts
GRACE_PERIOD_HOURS = 72      # Before DEGRADED → SUSPENDED
RE_ATTEST_TIMEOUT_HOURS = 24 # Time for grader to respond to RE_ATTEST
REPLACE_TIMEOUT_HOURS = 168  # 7 days to find replacement grader
ORPHAN_TIMEOUT_HOURS = 720   # 30 days before ORPHAN → REJECTED
MIN_GRADER_DIVERSITY = 2     # Minimum independent graders for recovery


@dataclass
class GraderInfo:
    grader_id: str
    operator: str
    is_alive: bool
    is_revoked: bool
    last_attestation_age_hours: float
    co_sign_rate: float


@dataclass
class Agent:
    agent_id: str
    current_state: TrustState
    current_grade: str  # A-F
    grader: GraderInfo
    alleged_receipts: list = field(default_factory=list)
    delegation_depth: int = 0
    degraded_since_hours: float = 0.0


@dataclass
class RecoveryPlan:
    agent_id: str
    mode: RecoveryMode
    status: RecoveryStatus
    steps: list = field(default_factory=list)
    timeout_hours: float = 0.0
    fallback_mode: Optional[RecoveryMode] = None
    decay_inherited: bool = True  # ElSalamouny: inherit, don't reset


def compute_alleged_weight(t_elapsed_hours: float, lambda_val: float = LAMBDA_DECAY) -> float:
    """
    Compute ALLEGED receipt weight with exponential decay.
    weight = 0.5 * exp(-lambda * T)
    
    Per ElSalamouny et al. (TCS 2009): decay tracks evidence staleness.
    """
    if lambda_val < LAMBDA_FLOOR:
        lambda_val = LAMBDA_FLOOR  # Enforce floor
    return ALLEGED_INITIAL_WEIGHT * math.exp(-lambda_val * t_elapsed_hours)


def classify_recovery_mode(agent: Agent) -> RecoveryMode:
    """Determine cheapest recovery path."""
    grader = agent.grader
    
    if grader.is_revoked:
        # Check if any other grader available
        return RecoveryMode.REPLACE
    
    if not grader.is_alive:
        if grader.last_attestation_age_hours > REPLACE_TIMEOUT_HOURS:
            return RecoveryMode.ORPHAN  # Long-dead grader, likely no replacement
        return RecoveryMode.REPLACE
    
    # Grader alive but stale
    if grader.last_attestation_age_hours > GRACE_PERIOD_HOURS:
        return RecoveryMode.RE_ATTEST
    
    # Not actually degraded?
    return RecoveryMode.RE_ATTEST


def build_recovery_plan(agent: Agent) -> RecoveryPlan:
    """Build recovery plan with fallback chain."""
    mode = classify_recovery_mode(agent)
    
    if mode == RecoveryMode.RE_ATTEST:
        steps = [
            f"1. Send RE_ATTESTATION_REQUEST to grader {agent.grader.grader_id}",
            f"2. Wait {RE_ATTEST_TIMEOUT_HOURS}h for response",
            "3. If response: verify fresh attestation, compute new grade",
            "4. If no response: escalate to REPLACE mode",
            "5. ALLEGED receipts during gap: weight decayed (inherited curve)"
        ]
        timeout = RE_ATTEST_TIMEOUT_HOURS
        fallback = RecoveryMode.REPLACE
        
    elif mode == RecoveryMode.REPLACE:
        steps = [
            f"1. Mark grader {agent.grader.grader_id} as UNAVAILABLE",
            "2. Broadcast GRADER_MIGRATION_REQUEST to registry",
            "3. Candidate graders submit bids (co-sign rate + operator diversity)",
            f"4. Wait {REPLACE_TIMEOUT_HOURS}h for candidates",
            "5. Select grader: highest co-sign rate from different operator",
            "6. Issue GRADER_MIGRATION_RECEIPT (old_grader → new_grader)",
            "7. New grader INHERITS decay curve (ElSalamouny: staleness is evidence, not observer)",
            "8. If no candidates: escalate to ORPHAN mode"
        ]
        timeout = REPLACE_TIMEOUT_HOURS
        fallback = RecoveryMode.ORPHAN
        
    else:  # ORPHAN
        steps = [
            "1. No eligible grader found. Agent enters ORPHAN state.",
            "2. Issue BOOTSTRAP_REQUEST (cold-start redux)",
            "3. Wilson CI ceiling applies: n=1→0.21, n=5→0.57",
            f"4. {ORPHAN_TIMEOUT_HOURS}h to find bootstrap grader",
            "5. If timeout: DEGRADED → SUSPENDED → REJECTED",
            "6. Existing ALLEGED receipts: weight continues decaying",
            "7. Recovery requires operator intervention (genesis-level)"
        ]
        timeout = ORPHAN_TIMEOUT_HOURS
        fallback = None
    
    return RecoveryPlan(
        agent_id=agent.agent_id,
        mode=mode,
        status=RecoveryStatus.PENDING,
        steps=steps,
        timeout_hours=timeout,
        fallback_mode=fallback,
        decay_inherited=True
    )


def simulate_decay_during_recovery(t_hours: list[float]) -> list[dict]:
    """Show ALLEGED weight decay during recovery window."""
    results = []
    for t in t_hours:
        weight = compute_alleged_weight(t)
        grade_equivalent = (
            "A" if weight > 0.4 else
            "B" if weight > 0.3 else
            "C" if weight > 0.2 else
            "D" if weight > 0.1 else
            "F"
        )
        results.append({
            "t_hours": t,
            "weight": round(weight, 4),
            "grade_equivalent": grade_equivalent,
            "usable": weight > 0.05
        })
    return results


def compute_double_decay(t_hours: float, delegation_depth: int) -> float:
    """
    ALLEGED + DELEGATION double-decay.
    Per santaclawd: compounding uncertainty = compounding staleness.
    """
    alleged_weight = compute_alleged_weight(t_hours)
    delegation_factor = max(0, 1.0 - (delegation_depth * 0.25))  # 1/hop decay
    return round(alleged_weight * delegation_factor, 4)


# === Scenarios ===

def scenario_re_attest():
    """Grader alive but stale — cheapest recovery."""
    print("=== Scenario: RE_ATTEST — Stale Grader ===")
    agent = Agent(
        agent_id="kit_fox",
        current_state=TrustState.DEGRADED,
        current_grade="B",
        grader=GraderInfo("grader_alpha", "op_1", is_alive=True, is_revoked=False,
                          last_attestation_age_hours=96, co_sign_rate=0.85),
        degraded_since_hours=24
    )
    
    plan = build_recovery_plan(agent)
    print(f"  Mode: {plan.mode.value}")
    print(f"  Timeout: {plan.timeout_hours}h")
    print(f"  Fallback: {plan.fallback_mode.value if plan.fallback_mode else 'NONE'}")
    print(f"  Decay inherited: {plan.decay_inherited}")
    for step in plan.steps:
        print(f"    {step}")
    
    # Show decay during recovery
    decay = simulate_decay_during_recovery([0, 6, 12, 24, 48, 72])
    print(f"\n  ALLEGED weight decay during recovery:")
    for d in decay:
        print(f"    T+{d['t_hours']:3.0f}h: weight={d['weight']:.4f} grade≈{d['grade_equivalent']} usable={d['usable']}")
    print()


def scenario_grader_revoked():
    """Grader revoked — need replacement."""
    print("=== Scenario: REPLACE — Grader Revoked ===")
    agent = Agent(
        agent_id="new_agent",
        current_state=TrustState.DEGRADED,
        current_grade="C",
        grader=GraderInfo("grader_bad", "op_compromised", is_alive=True, is_revoked=True,
                          last_attestation_age_hours=48, co_sign_rate=0.30),
        degraded_since_hours=48
    )
    
    plan = build_recovery_plan(agent)
    print(f"  Mode: {plan.mode.value}")
    print(f"  Timeout: {plan.timeout_hours}h")
    print(f"  Fallback: {plan.fallback_mode.value if plan.fallback_mode else 'NONE'}")
    for step in plan.steps:
        print(f"    {step}")
    print()


def scenario_orphan():
    """No grader available — bootstrap redux."""
    print("=== Scenario: ORPHAN — No Eligible Grader ===")
    agent = Agent(
        agent_id="isolated_agent",
        current_state=TrustState.DEGRADED,
        current_grade="D",
        grader=GraderInfo("grader_dead", "op_gone", is_alive=False, is_revoked=False,
                          last_attestation_age_hours=500, co_sign_rate=0.0),
        degraded_since_hours=168
    )
    
    plan = build_recovery_plan(agent)
    print(f"  Mode: {plan.mode.value}")
    print(f"  Timeout: {plan.timeout_hours}h")
    print(f"  Fallback: {plan.fallback_mode}")
    for step in plan.steps:
        print(f"    {step}")
    print()


def scenario_double_decay():
    """ALLEGED + DELEGATION compounding decay."""
    print("=== Scenario: Double Decay (ALLEGED + DELEGATION) ===")
    print("  Per santaclawd: compounding uncertainty = compounding staleness")
    print()
    
    for depth in [0, 1, 2, 3]:
        for t in [1, 12, 24, 72]:
            weight = compute_double_decay(t, depth)
            alleged_only = compute_alleged_weight(t)
            print(f"  depth={depth} t={t:3d}h: alleged={alleged_only:.4f} "
                  f"double_decay={weight:.4f} "
                  f"{'USABLE' if weight > 0.05 else 'EXPIRED'}")
        print()


def scenario_lambda_gaming():
    """Demonstrate why lambda must be SPEC_CONSTANT."""
    print("=== Scenario: Lambda Gaming Prevention ===")
    print("  Why grader-defined lambda = gaming surface")
    print()
    
    for label, lam in [("SPEC_DEFAULT (0.1)", 0.1), 
                        ("Gaming attempt (0.001)", 0.001),
                        ("Enforced floor (0.05)", 0.05)]:
        w24 = compute_alleged_weight(24, lam)
        w168 = compute_alleged_weight(168, lam)
        print(f"  {label}:")
        print(f"    T+24h:  weight={w24:.4f}")
        print(f"    T+168h: weight={w168:.4f}")
        if lam < LAMBDA_FLOOR:
            print(f"    ⚠ REJECTED: lambda {lam} < FLOOR {LAMBDA_FLOOR}")
        print()


if __name__ == "__main__":
    print("Soft-Cascade Recovery — DEGRADED→HEALTHY Path for ATF V1.1")
    print("Per santaclawd + ElSalamouny et al. (TCS 2009)")
    print("=" * 70)
    print()
    
    scenario_re_attest()
    scenario_grader_revoked()
    scenario_orphan()
    scenario_double_decay()
    scenario_lambda_gaming()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Three recovery modes: RE_ATTEST (cheapest) → REPLACE → ORPHAN")
    print("2. CO_GRADER inherits decay curve (ElSalamouny: staleness is evidence)")
    print("3. Lambda = SPEC_CONSTANT, not grader-defined (gaming surface)")
    print("4. ALLEGED+DELEGATION = double decay (compounding uncertainty)")
    print("5. ORPHAN = BOOTSTRAP_REQUEST redux (Wilson CI cold-start)")
