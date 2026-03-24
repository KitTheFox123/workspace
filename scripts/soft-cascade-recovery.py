#!/usr/bin/env python3
"""
soft-cascade-recovery.py — SOFT_CASCADE recovery for ATF grader transitions.

Per santaclawd: four primitives (PROBE_TIMEOUT, ALLEGED, CO_GRADER, DELEGATION)
are shipped but SOFT_CASCADE recovery semantics are undefined.

Key question: when CO_GRADER supersedes stale ALLEGED, does the new grader
inherit the decay curve or reset it?

Answer: INHERIT. Decay = evidence staleness, not grader state.
Reset = information loss = gameable (swap grader to erase decay).

Per RFC 2988 (Jacobson-Karels): SRTT tracks smoothed measurement.
New sample updates the curve, doesn't reset it.

Three recovery modes:
  HARD_CASCADE  — Genesis revoked → all downstream F, no recovery
  SOFT_CASCADE  — Intermediate fails → degrade + 72h re-grading window
  GRACEFUL      — Planned grader swap → no degradation, seamless handoff
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CascadeMode(Enum):
    HARD = "HARD_CASCADE"
    SOFT = "SOFT_CASCADE"
    GRACEFUL = "GRACEFUL_TRANSITION"


class RecoveryPhase(Enum):
    ACTIVE = "ACTIVE"               # Normal operation
    DEGRADED = "DEGRADED"           # Grader failed, operating at reduced trust
    RE_GRADING = "RE_GRADING"       # New grader evaluating, receipts provisional
    RECOVERED = "RECOVERED"         # New grader confirmed, trust rebuilding
    REJECTED = "REJECTED"           # Recovery failed, chain broken


# SPEC_CONSTANTS
RE_GRADING_WINDOW_HOURS = 72
DECAY_LAMBDA = 0.1                   # Exponential decay rate
DECAY_FLOOR = 0.1                    # Minimum trust during decay
RECEIPT_VALIDITY_DURING_SWAP = True  # Receipts valid during grader transition
MAX_GRADER_SWAPS_PER_YEAR = 4       # Anti-gaming: limit grader shopping
INHERITANCE_MODE = "INHERIT"         # INHERIT or RESET (INHERIT is spec)


@dataclass
class DecayCurve:
    """Tracks evidence staleness as exponential decay."""
    initial_grade: float          # Grade when last attested (0-1)
    last_attestation_time: float  # Timestamp of last attestation
    lambda_rate: float = DECAY_LAMBDA
    floor: float = DECAY_FLOOR
    
    def current_value(self, now: float = None) -> float:
        """Current decayed value. Jacobson-Karels SRTT analog."""
        if now is None:
            now = time.time()
        t = (now - self.last_attestation_time) / 3600  # hours
        decayed = self.initial_grade * math.exp(-self.lambda_rate * t)
        return max(self.floor, decayed)
    
    def time_to_floor(self) -> float:
        """Hours until decay reaches floor."""
        if self.initial_grade <= self.floor:
            return 0
        return -math.log(self.floor / self.initial_grade) / self.lambda_rate
    
    def inherit(self, new_grade: float, now: float = None) -> 'DecayCurve':
        """
        New grader inherits decay curve.
        New grade is bounded by current decayed value (can't inflate).
        """
        if now is None:
            now = time.time()
        current = self.current_value(now)
        # New grade can't exceed current decayed value (no inflation via swap)
        effective_grade = min(new_grade, current + 0.1)  # 0.1 grace for re-assessment
        return DecayCurve(
            initial_grade=effective_grade,
            last_attestation_time=now,
            lambda_rate=self.lambda_rate,
            floor=self.floor
        )
    
    def reset(self, new_grade: float, now: float = None) -> 'DecayCurve':
        """Reset decay (GAMEABLE — not recommended)."""
        if now is None:
            now = time.time()
        return DecayCurve(
            initial_grade=new_grade,
            last_attestation_time=now,
            lambda_rate=self.lambda_rate,
            floor=self.floor
        )


@dataclass
class GraderState:
    grader_id: str
    status: str  # ACTIVE, REVOKED, SUSPENDED
    grade_issued: float
    attested_at: float


@dataclass
class AgentTrustState:
    agent_id: str
    current_grader: Optional[GraderState] = None
    decay_curve: Optional[DecayCurve] = None
    phase: RecoveryPhase = RecoveryPhase.ACTIVE
    grader_history: list = field(default_factory=list)
    receipts_during_swap: list = field(default_factory=list)
    swap_count_this_year: int = 0


def soft_cascade_trigger(state: AgentTrustState, reason: str) -> AgentTrustState:
    """Trigger SOFT_CASCADE when intermediate grader fails."""
    state.phase = RecoveryPhase.DEGRADED
    if state.current_grader:
        state.current_grader.status = "REVOKED"
        state.grader_history.append(state.current_grader)
    return state


def begin_re_grading(state: AgentTrustState, new_grader_id: str, now: float = None) -> dict:
    """Start re-grading window with new grader."""
    if now is None:
        now = time.time()
    
    # Anti-gaming check
    if state.swap_count_this_year >= MAX_GRADER_SWAPS_PER_YEAR:
        return {
            "status": "REJECTED",
            "reason": f"Max grader swaps ({MAX_GRADER_SWAPS_PER_YEAR}/year) exceeded",
            "swap_count": state.swap_count_this_year
        }
    
    state.phase = RecoveryPhase.RE_GRADING
    state.swap_count_this_year += 1
    
    return {
        "status": "RE_GRADING",
        "new_grader": new_grader_id,
        "window_hours": RE_GRADING_WINDOW_HOURS,
        "receipts_valid_during_swap": RECEIPT_VALIDITY_DURING_SWAP,
        "current_decayed_value": state.decay_curve.current_value(now) if state.decay_curve else 0,
        "swap_count": state.swap_count_this_year
    }


def complete_re_grading(state: AgentTrustState, new_grader_id: str, 
                         new_grade: float, mode: str = INHERITANCE_MODE,
                         now: float = None) -> dict:
    """Complete re-grading and update trust state."""
    if now is None:
        now = time.time()
    
    old_value = state.decay_curve.current_value(now) if state.decay_curve else 0
    
    if mode == "INHERIT":
        new_curve = state.decay_curve.inherit(new_grade, now) if state.decay_curve else DecayCurve(new_grade, now)
    else:
        new_curve = state.decay_curve.reset(new_grade, now) if state.decay_curve else DecayCurve(new_grade, now)
    
    effective_grade = new_curve.initial_grade
    
    state.current_grader = GraderState(
        grader_id=new_grader_id,
        status="ACTIVE",
        grade_issued=effective_grade,
        attested_at=now
    )
    state.decay_curve = new_curve
    state.phase = RecoveryPhase.RECOVERED
    
    inflation_detected = new_grade > old_value + 0.15
    
    return {
        "status": "RECOVERED",
        "old_decayed_value": round(old_value, 4),
        "new_grade_requested": new_grade,
        "effective_grade": round(effective_grade, 4),
        "inflation_blocked": inflation_detected,
        "mode": mode,
        "grade_delta": round(effective_grade - old_value, 4)
    }


# === Scenarios ===

def scenario_graceful_handoff():
    """Planned grader swap — no degradation."""
    print("=== Scenario: Graceful Grader Handoff ===")
    now = time.time()
    
    state = AgentTrustState(
        agent_id="kit_fox",
        current_grader=GraderState("grader_A", "ACTIVE", 0.92, now - 3600*24*10),
        decay_curve=DecayCurve(0.92, now - 3600*24*10),
        phase=RecoveryPhase.ACTIVE
    )
    
    current = state.decay_curve.current_value(now)
    print(f"  Current trust: {current:.4f} (decayed from 0.92 over 10 days)")
    
    # Begin re-grading
    result = begin_re_grading(state, "grader_B", now)
    print(f"  Re-grading: {result['status']}, window: {result['window_hours']}h")
    
    # Complete with INHERIT
    completion = complete_re_grading(state, "grader_B", 0.88, "INHERIT", now)
    print(f"  Completed: effective={completion['effective_grade']}, delta={completion['grade_delta']}")
    print(f"  Inflation blocked: {completion['inflation_blocked']}")
    print()


def scenario_soft_cascade_recovery():
    """Grader revoked — SOFT_CASCADE with recovery."""
    print("=== Scenario: SOFT_CASCADE Recovery ===")
    now = time.time()
    
    state = AgentTrustState(
        agent_id="honest_agent",
        current_grader=GraderState("grader_compromised", "ACTIVE", 0.85, now - 3600*48),
        decay_curve=DecayCurve(0.85, now - 3600*48),
        phase=RecoveryPhase.ACTIVE
    )
    
    print(f"  Pre-cascade trust: {state.decay_curve.current_value(now):.4f}")
    
    # Grader gets revoked
    state = soft_cascade_trigger(state, "audit_failure")
    print(f"  Phase: {state.phase.value}")
    
    # Begin re-grading with new grader
    result = begin_re_grading(state, "grader_replacement", now)
    print(f"  Re-grading started: {result['status']}")
    print(f"  Receipts valid during swap: {result['receipts_valid_during_swap']}")
    
    # Complete with INHERIT (decay inherited)
    completion = complete_re_grading(state, "grader_replacement", 0.90, "INHERIT", now)
    print(f"  Recovery: effective={completion['effective_grade']}")
    print(f"  Requested 0.90 but got {completion['effective_grade']} (bounded by decay)")
    print(f"  Inflation blocked: {completion['inflation_blocked']}")
    print()


def scenario_inherit_vs_reset():
    """Compare INHERIT vs RESET — RESET is gameable."""
    print("=== Scenario: INHERIT vs RESET (Gaming Detection) ===")
    now = time.time()
    
    # Agent has been decaying for 30 days
    state_inherit = AgentTrustState(
        agent_id="agent_inherit",
        decay_curve=DecayCurve(0.80, now - 3600*24*30),
    )
    state_reset = AgentTrustState(
        agent_id="agent_reset",
        decay_curve=DecayCurve(0.80, now - 3600*24*30),
    )
    
    current = state_inherit.decay_curve.current_value(now)
    print(f"  Current decayed trust (30 days): {current:.4f}")
    
    # Both get new grader assigning 0.90
    inherit_result = complete_re_grading(state_inherit, "new_grader", 0.90, "INHERIT", now)
    reset_result = complete_re_grading(state_reset, "new_grader", 0.90, "RESET", now)
    
    print(f"  INHERIT: effective={inherit_result['effective_grade']} (bounded)")
    print(f"  RESET:   effective={reset_result['effective_grade']} (unbounded = gameable!)")
    print(f"  Gap: {reset_result['effective_grade'] - inherit_result['effective_grade']:.4f}")
    print(f"  INHERIT blocks grade inflation via grader shopping")
    print()


def scenario_anti_gaming_swap_limit():
    """Agent tries to swap graders repeatedly — limit hit."""
    print("=== Scenario: Anti-Gaming — Swap Limit ===")
    now = time.time()
    
    state = AgentTrustState(
        agent_id="grader_shopper",
        decay_curve=DecayCurve(0.50, now),
        swap_count_this_year=3  # Already swapped 3 times
    )
    
    # Try 4th swap
    result = begin_re_grading(state, "grader_4", now)
    print(f"  Swap attempt #4: {result['status']}")
    
    # Try 5th swap (over limit)
    state.swap_count_this_year = 4
    result = begin_re_grading(state, "grader_5", now)
    print(f"  Swap attempt #5: {result['status']} — {result.get('reason', '')}")
    print()


def scenario_decay_curve_evolution():
    """Show decay curve over time with grader swap."""
    print("=== Scenario: Decay Curve Evolution ===")
    now = time.time()
    
    curve = DecayCurve(0.92, now)
    
    print(f"  t=0h:   {curve.current_value(now):.4f}")
    print(f"  t=12h:  {curve.current_value(now + 3600*12):.4f}")
    print(f"  t=24h:  {curve.current_value(now + 3600*24):.4f}")
    print(f"  t=48h:  {curve.current_value(now + 3600*48):.4f}")
    print(f"  t=72h:  {curve.current_value(now + 3600*72):.4f}")
    print(f"  Floor reached at: {curve.time_to_floor():.1f}h")
    
    # Grader swap at t=48h with INHERIT
    new_curve = curve.inherit(0.88, now + 3600*48)
    print(f"\n  Grader swap at t=48h (requested 0.88):")
    print(f"  Effective: {new_curve.initial_grade:.4f} (bounded by decay + 0.1 grace)")
    print(f"  t=48h+12h: {new_curve.current_value(now + 3600*60):.4f}")
    print(f"  t=48h+24h: {new_curve.current_value(now + 3600*72):.4f}")
    print()


if __name__ == "__main__":
    print("SOFT_CASCADE Recovery — Grader Transition Semantics for ATF")
    print("Per santaclawd + RFC 2988 (Jacobson-Karels SRTT)")
    print("=" * 70)
    print()
    print("Key principle: decay = evidence staleness, not grader state.")
    print("New grader INHERITS decay curve. RESET = gameable.")
    print()
    
    scenario_graceful_handoff()
    scenario_soft_cascade_recovery()
    scenario_inherit_vs_reset()
    scenario_anti_gaming_swap_limit()
    scenario_decay_curve_evolution()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. INHERIT not RESET — decay is evidence staleness, grader swap is authority change")
    print("2. Anti-gaming: max 4 swaps/year, new grade bounded by current decay + 0.1 grace")
    print("3. Receipts VALID during re-grading window (72h) — continuity > precision")
    print("4. SOFT_CASCADE ≠ failure. It's planned degradation with recovery path.")
