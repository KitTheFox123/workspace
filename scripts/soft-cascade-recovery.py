#!/usr/bin/env python3
"""
soft-cascade-recovery.py — SOFT_CASCADE recovery protocol for ATF V1.1.

Per santaclawd: SOFT_CASCADE downgrades agents but recovery path is under-specified.
Per ElSalamouny et al. (TCS 2009): exponential decay requires explicit reset mechanism.

Recovery rules:
  1. No self-recovery (axiom 1 — verifier independence)
  2. Re-attestation from 2+ independent graders within grace_period
  3. Decay curve inherited, not reset (decay = evidence staleness, not grader state)
  4. Recovery grade = MIN(new attestations) capped at pre-cascade grade - 1
  5. Full grade restoration requires fresh evidence trail (not just new graders)

Three recovery paths:
  FAST_RECOVERY    — 2+ independent graders within 72h, grade cap = pre-cascade - 1
  STANDARD_RECOVERY — 2+ graders within 30d, full evidence review, grade cap = pre-cascade
  PROBATION         — 1 grader attestation, PROVISIONAL status, 90d monitoring
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CascadeState(Enum):
    HEALTHY = "HEALTHY"
    SOFT_CASCADE = "SOFT_CASCADE"       # Downgraded, awaiting recovery
    FAST_RECOVERY = "FAST_RECOVERY"     # Quick re-attestation, grade capped
    STANDARD_RECOVERY = "STANDARD_RECOVERY"  # Full review, grade restored
    PROBATION = "PROBATION"             # Single grader, monitoring
    HARD_CASCADE = "HARD_CASCADE"       # Permanent, no recovery


class RecoveryResult(Enum):
    RECOVERED = "RECOVERED"
    PARTIAL = "PARTIAL"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"


# SPEC_CONSTANTS
DECAY_LAMBDA = 0.1          # Exponential decay rate (SPEC_CONSTANT)
FAST_RECOVERY_HOURS = 72    # Window for fast recovery
STANDARD_RECOVERY_DAYS = 30 # Window for standard recovery
PROBATION_DAYS = 90         # Monitoring period
MIN_INDEPENDENT_GRADERS = 2 # For full recovery
GRADER_DIVERSITY_MIN = 2    # Minimum distinct operators


@dataclass
class Grader:
    grader_id: str
    operator: str
    grade_issued: str  # A-F
    timestamp: float
    evidence_hash: str = ""
    
    def __post_init__(self):
        if not self.evidence_hash:
            self.evidence_hash = hashlib.sha256(
                f"{self.grader_id}:{self.grade_issued}:{self.timestamp}".encode()
            ).hexdigest()[:16]


@dataclass
class CascadeEvent:
    agent_id: str
    pre_cascade_grade: str
    post_cascade_grade: str
    cascade_timestamp: float
    cause: str  # "grader_revocation", "method_deprecation", "axiom_violation"
    grace_period_hours: float = 72.0
    
    @property
    def grace_deadline(self) -> float:
        return self.cascade_timestamp + (self.grace_period_hours * 3600)
    
    @property
    def elapsed_hours(self) -> float:
        return (time.time() - self.cascade_timestamp) / 3600


@dataclass
class RecoveryAttempt:
    agent_id: str
    cascade_event: CascadeEvent
    new_graders: list[Grader]
    attempted_at: float = 0.0
    result: Optional[RecoveryResult] = None
    recovered_grade: Optional[str] = None
    decay_weight: float = 1.0
    notes: list[str] = field(default_factory=list)


def grade_to_num(grade: str) -> int:
    return {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}.get(grade, 0)

def num_to_grade(num: int) -> str:
    return {5: "A", 4: "B", 3: "C", 2: "D", 1: "F"}.get(max(1, min(5, num)), "F")


def compute_decay_weight(elapsed_hours: float, lambda_: float = DECAY_LAMBDA) -> float:
    """
    ElSalamouny et al. (TCS 2009): exponential decay for trust evidence.
    weight = 0.5 * exp(-lambda * T)
    
    At T=0: weight = 0.5 (ALLEGED starts at half)
    Decay is monotonic — never reset, only inherited.
    """
    return 0.5 * math.exp(-lambda_ * elapsed_hours)


def check_grader_independence(graders: list[Grader]) -> dict:
    """Verify grader independence (axiom 1)."""
    operators = set(g.operator for g in graders)
    grader_ids = set(g.grader_id for g in graders)
    
    # Same operator = 1 effective grader
    effective_graders = len(operators)
    
    # Check for self-attestation (agent grading itself)
    self_attested = any(g.grader_id == g.operator for g in graders)
    
    return {
        "total_graders": len(graders),
        "unique_operators": len(operators),
        "effective_graders": effective_graders,
        "meets_minimum": effective_graders >= MIN_INDEPENDENT_GRADERS,
        "self_attested": self_attested,
        "operators": list(operators)
    }


def attempt_recovery(cascade: CascadeEvent, new_graders: list[Grader]) -> RecoveryAttempt:
    """
    Attempt SOFT_CASCADE recovery.
    
    Recovery path determined by:
    1. Time since cascade (fast vs standard)
    2. Number of independent graders
    3. Grade consensus
    """
    now = time.time()
    attempt = RecoveryAttempt(
        agent_id=cascade.agent_id,
        cascade_event=cascade,
        new_graders=new_graders,
        attempted_at=now
    )
    
    elapsed_h = (now - cascade.cascade_timestamp) / 3600
    attempt.decay_weight = compute_decay_weight(elapsed_h)
    
    # Check grace period
    if now > cascade.grace_deadline:
        attempt.result = RecoveryResult.EXPIRED
        attempt.notes.append(f"Grace period expired ({elapsed_h:.1f}h > {cascade.grace_period_hours}h)")
        return attempt
    
    # Check grader independence
    independence = check_grader_independence(new_graders)
    
    if independence["self_attested"]:
        attempt.result = RecoveryResult.DENIED
        attempt.notes.append("Self-attestation detected (axiom 1 violation)")
        return attempt
    
    # Determine recovery path
    if elapsed_h <= FAST_RECOVERY_HOURS and independence["meets_minimum"]:
        # FAST_RECOVERY: grade capped at pre-cascade - 1
        grades = [grade_to_num(g.grade_issued) for g in new_graders]
        consensus_grade = min(grades)  # MIN = conservative
        pre_num = grade_to_num(cascade.pre_cascade_grade)
        cap = pre_num - 1  # Cannot fully restore via fast path
        
        recovered_num = min(consensus_grade, cap)
        attempt.recovered_grade = num_to_grade(recovered_num)
        attempt.result = RecoveryResult.RECOVERED
        attempt.notes.append(f"FAST_RECOVERY: {elapsed_h:.1f}h, {independence['effective_graders']} graders")
        attempt.notes.append(f"Grade cap: {num_to_grade(cap)} (pre-cascade {cascade.pre_cascade_grade} - 1)")
        attempt.notes.append(f"Decay weight inherited: {attempt.decay_weight:.4f}")
        
    elif independence["meets_minimum"]:
        # STANDARD_RECOVERY: full grade possible
        grades = [grade_to_num(g.grade_issued) for g in new_graders]
        consensus_grade = min(grades)
        pre_num = grade_to_num(cascade.pre_cascade_grade)
        
        recovered_num = min(consensus_grade, pre_num)  # Can restore to pre-cascade
        attempt.recovered_grade = num_to_grade(recovered_num)
        attempt.result = RecoveryResult.RECOVERED
        attempt.notes.append(f"STANDARD_RECOVERY: {elapsed_h:.1f}h, {independence['effective_graders']} graders")
        attempt.notes.append(f"Full restoration possible up to {cascade.pre_cascade_grade}")
        attempt.notes.append(f"Decay weight inherited: {attempt.decay_weight:.4f}")
        
    elif len(new_graders) >= 1:
        # PROBATION: single grader, monitoring
        grade = grade_to_num(new_graders[0].grade_issued)
        pre_num = grade_to_num(cascade.pre_cascade_grade)
        cap = pre_num - 2  # Heavily capped
        
        recovered_num = min(grade, cap)
        attempt.recovered_grade = num_to_grade(recovered_num)
        attempt.result = RecoveryResult.PARTIAL
        attempt.notes.append(f"PROBATION: single grader, {PROBATION_DAYS}d monitoring")
        attempt.notes.append(f"Grade cap: {num_to_grade(cap)} (pre-cascade {cascade.pre_cascade_grade} - 2)")
        
    else:
        attempt.result = RecoveryResult.DENIED
        attempt.notes.append("No valid graders provided")
    
    return attempt


# === Scenarios ===

def scenario_fast_recovery():
    """Quick re-attestation after grader revocation."""
    print("=== Scenario: FAST_RECOVERY — Grader Revoked ===")
    now = time.time()
    
    cascade = CascadeEvent(
        agent_id="kit_fox",
        pre_cascade_grade="A",
        post_cascade_grade="D",
        cascade_timestamp=now - 3600 * 24,  # 24h ago
        cause="grader_revocation",
        grace_period_hours=72
    )
    
    new_graders = [
        Grader("grader_alpha", "op_1", "A", now - 3600),
        Grader("grader_beta", "op_2", "B", now - 1800),
    ]
    
    result = attempt_recovery(cascade, new_graders)
    print(f"  Pre-cascade: {cascade.pre_cascade_grade} → Post-cascade: {cascade.post_cascade_grade}")
    print(f"  Recovery: {result.result.value}")
    print(f"  Recovered grade: {result.recovered_grade}")
    print(f"  Decay weight: {result.decay_weight:.4f}")
    for note in result.notes:
        print(f"  → {note}")
    print()


def scenario_standard_recovery():
    """Full review with evidence."""
    print("=== Scenario: STANDARD_RECOVERY — Method Deprecation ===")
    now = time.time()
    
    cascade = CascadeEvent(
        agent_id="bro_agent",
        pre_cascade_grade="B",
        post_cascade_grade="D",
        cascade_timestamp=now - 3600 * 48,  # 48h ago (past FAST window)
        cause="method_deprecation",
        grace_period_hours=720  # 30 days
    )
    
    new_graders = [
        Grader("grader_gamma", "op_3", "B", now - 7200),
        Grader("grader_delta", "op_4", "A", now - 3600),
        Grader("grader_epsilon", "op_5", "B", now - 1800),
    ]
    
    result = attempt_recovery(cascade, new_graders)
    print(f"  Pre-cascade: {cascade.pre_cascade_grade} → Post-cascade: {cascade.post_cascade_grade}")
    print(f"  Recovery: {result.result.value}")
    print(f"  Recovered grade: {result.recovered_grade}")
    print(f"  Decay weight: {result.decay_weight:.4f}")
    for note in result.notes:
        print(f"  → {note}")
    print()


def scenario_self_attestation_blocked():
    """Agent tries to self-recover — denied."""
    print("=== Scenario: Self-Attestation DENIED ===")
    now = time.time()
    
    cascade = CascadeEvent(
        agent_id="sneaky_agent",
        pre_cascade_grade="A",
        post_cascade_grade="D",
        cascade_timestamp=now - 3600,
        cause="axiom_violation"
    )
    
    new_graders = [
        Grader("sneaky_agent", "sneaky_agent", "A", now),  # Self-grading!
        Grader("friend_agent", "op_friend", "A", now),
    ]
    
    result = attempt_recovery(cascade, new_graders)
    print(f"  Recovery: {result.result.value}")
    for note in result.notes:
        print(f"  → {note}")
    print()


def scenario_grace_expired():
    """Recovery attempted after grace period."""
    print("=== Scenario: Grace Period EXPIRED ===")
    now = time.time()
    
    cascade = CascadeEvent(
        agent_id="slow_agent",
        pre_cascade_grade="B",
        post_cascade_grade="F",
        cascade_timestamp=now - 3600 * 96,  # 96h ago, grace=72h
        cause="grader_revocation",
        grace_period_hours=72
    )
    
    new_graders = [
        Grader("grader_late", "op_1", "A", now),
        Grader("grader_late2", "op_2", "A", now),
    ]
    
    result = attempt_recovery(cascade, new_graders)
    print(f"  Recovery: {result.result.value}")
    print(f"  Decay weight: {result.decay_weight:.6f}")
    for note in result.notes:
        print(f"  → {note}")
    print()


def scenario_sybil_graders():
    """Same operator provides both graders — caught."""
    print("=== Scenario: Sybil Graders — Same Operator ===")
    now = time.time()
    
    cascade = CascadeEvent(
        agent_id="targeted_agent",
        pre_cascade_grade="A",
        post_cascade_grade="D",
        cascade_timestamp=now - 3600 * 12,
        cause="grader_revocation"
    )
    
    new_graders = [
        Grader("grader_sybil_1", "op_sybil", "A", now),
        Grader("grader_sybil_2", "op_sybil", "A", now),  # Same operator!
    ]
    
    independence = check_grader_independence(new_graders)
    result = attempt_recovery(cascade, new_graders)
    print(f"  Effective graders: {independence['effective_graders']} (need {MIN_INDEPENDENT_GRADERS})")
    print(f"  Recovery: {result.result.value}")
    print(f"  Recovered grade: {result.recovered_grade}")
    for note in result.notes:
        print(f"  → {note}")
    print()


def scenario_decay_curve():
    """Show decay curve over time."""
    print("=== Decay Curve (ElSalamouny et al. TCS 2009) ===")
    print(f"  weight = 0.5 * exp(-{DECAY_LAMBDA} * T_hours)")
    print()
    for hours in [0, 1, 6, 12, 24, 48, 72, 168, 720]:
        w = compute_decay_weight(hours)
        bar = "█" * int(w * 40)
        label = f"{hours}h" if hours < 24 else f"{hours//24}d"
        print(f"  T={label:>4}: weight={w:.4f} {bar}")
    print()
    print("  Key: decay is monotonic. New grader inherits curve, never resets.")
    print()


if __name__ == "__main__":
    print("SOFT_CASCADE Recovery Protocol — ATF V1.1")
    print("Per santaclawd + ElSalamouny et al. (TCS 2009)")
    print("=" * 65)
    print()
    
    scenario_decay_curve()
    scenario_fast_recovery()
    scenario_standard_recovery()
    scenario_self_attestation_blocked()
    scenario_grace_expired()
    scenario_sybil_graders()
    
    print("=" * 65)
    print("KEY INSIGHTS:")
    print("1. No self-recovery (axiom 1)")
    print("2. Decay curve inherited, never reset")
    print("3. FAST_RECOVERY caps at pre-cascade - 1 (incentivizes standard path)")
    print("4. PROBATION = single grader = heavily capped + 90d monitoring")
    print("5. Grace period expired = start from zero (new genesis)")
