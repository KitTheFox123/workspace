#!/usr/bin/env python3
"""
n-recovery-spec.py — ATF V1.2 gap #3: recovery window specification.

Per santaclawd: n_recovery=8 + 30d time cap.
Per RFC 5280 §5.3.1: certificateHold → removeFromCRL reinstatement.

Three recovery paths (from recovery-threshold-spec.py, formalized):
  SESSION_RESUMPTION — DORMANT → ACTIVE (lightest, identity preserved)
  VIOLATION_CLEAR    — DEGRADED → ACTIVE (mid, must clear violation)
  FULL_REATTESTION  — ABANDONED → ACTIVE (heaviest, near-fresh start)

Key spec constants:
  n_recovery = 8 CONFIRMED receipts (SESSION/VIOLATION)
  n_recovery = 30 CONFIRMED receipts (FULL)
  recovery_window = 30d (SESSION/VIOLATION), 90d (FULL)
  min_counterparties = 3 independent (SESSION/VIOLATION), 5 (FULL)
  
Wilson CI comparison:
  DORMANT + 8 receipts = 0.63-0.90 (depending on prior)
  Fresh PROVISIONAL = 0.21 at n=1
  FULL_REATTESTION + 30 = 0.89+
"""

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RecoveryPath(Enum):
    SESSION_RESUMPTION = "SESSION_RESUMPTION"  # DORMANT → ACTIVE
    VIOLATION_CLEAR = "VIOLATION_CLEAR"        # DEGRADED → ACTIVE  
    FULL_REATTESTION = "FULL_REATTESTION"      # ABANDONED → ACTIVE


class AgentState(Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    DEGRADED = "DEGRADED"
    ABANDONED = "ABANDONED"
    RECOVERING = "RECOVERING"


# SPEC_CONSTANTS (V1.2)
RECOVERY_SPECS = {
    RecoveryPath.SESSION_RESUMPTION: {
        "n_recovery": 8,
        "window_days": 30,
        "min_counterparties": 3,
        "preserves_history": True,
        "grade_floor": "decayed_prior",  # Resume from decayed score
        "rfc_precedent": "RFC 5280 §5.3.1 certificateHold + removeFromCRL",
        "tls_parallel": "RFC 8446 §2.2 PSK session resumption"
    },
    RecoveryPath.VIOLATION_CLEAR: {
        "n_recovery": 8,
        "window_days": 30,
        "min_counterparties": 3,
        "preserves_history": False,  # Prior receipts tainted
        "grade_floor": "C",  # Start at C regardless of prior
        "rfc_precedent": "RFC 5280 §5.3.1 certificateHold after investigation",
        "tls_parallel": "TLS 1.3 post-handshake auth (RFC 8446 §4.6.2)"
    },
    RecoveryPath.FULL_REATTESTION: {
        "n_recovery": 30,
        "window_days": 90,
        "min_counterparties": 5,
        "preserves_history": False,
        "grade_floor": "D",  # Near-fresh start
        "rfc_precedent": "RFC 5280 new certificate issuance",
        "tls_parallel": "Full TLS 1.3 handshake (2-RTT)"
    }
}

# Decay parameters
DECAY_RATE_PER_MONTH = 0.05  # 5%/month for DORMANT
DECAY_FLOOR = 0.30           # Minimum trust during decay
MAX_DORMANCY_MONTHS = 12     # After this → ABANDONED


def wilson_ci_lower(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson score confidence interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return (centre - spread) / denominator


def compute_decayed_score(original_score: float, dormant_months: int) -> float:
    """Compute trust score after dormancy decay."""
    decayed = original_score * (1 - DECAY_RATE_PER_MONTH) ** dormant_months
    return max(decayed, DECAY_FLOOR)


@dataclass
class RecoveryAttempt:
    agent_id: str
    prior_state: AgentState
    prior_score: float
    dormant_months: int
    path: RecoveryPath
    receipts: list = field(default_factory=list)  # (counterparty_id, confirmed: bool)
    started_at: float = 0.0
    
    def __post_init__(self):
        if not self.started_at:
            self.started_at = time.time()


@dataclass
class RecoveryResult:
    success: bool
    new_state: AgentState
    new_score: float
    wilson_ci: float
    receipts_completed: int
    receipts_required: int
    counterparties: int
    counterparties_required: int
    window_remaining_days: float
    path: str
    reason: str


def evaluate_recovery(attempt: RecoveryAttempt) -> RecoveryResult:
    """Evaluate whether recovery attempt meets spec requirements."""
    spec = RECOVERY_SPECS[attempt.path]
    
    # Count confirmed receipts
    confirmed = sum(1 for _, c in attempt.receipts if c)
    total = len(attempt.receipts)
    
    # Count unique counterparties
    counterparties = len(set(cp for cp, c in attempt.receipts if c))
    
    # Check time window
    elapsed_days = (time.time() - attempt.started_at) / 86400
    window_remaining = spec["window_days"] - elapsed_days
    
    # Determine base score
    if spec["preserves_history"]:
        base_score = compute_decayed_score(attempt.prior_score, attempt.dormant_months)
    else:
        base_score = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4, "F": 0.0}.get(
            spec["grade_floor"], 0.4)
    
    # Wilson CI on recovery receipts
    wilson = wilson_ci_lower(confirmed, total) if total > 0 else 0.0
    
    # Recovery score = base * wilson_adjustment
    if confirmed >= spec["n_recovery"]:
        recovery_boost = wilson
    else:
        recovery_boost = wilson * (confirmed / spec["n_recovery"])
    
    new_score = min(1.0, base_score * 0.5 + recovery_boost * 0.5)
    
    # Check all requirements
    requirements_met = (
        confirmed >= spec["n_recovery"] and
        counterparties >= spec["min_counterparties"] and
        window_remaining >= 0
    )
    
    if requirements_met:
        reason = f"Recovery complete: {confirmed}/{spec['n_recovery']} receipts, " \
                 f"{counterparties}/{spec['min_counterparties']} counterparties"
        new_state = AgentState.ACTIVE
    elif window_remaining < 0:
        reason = f"Recovery EXPIRED: window exceeded by {-window_remaining:.0f}d"
        new_state = attempt.prior_state
        new_score = base_score * 0.8  # Penalty for failed recovery
    else:
        reason = f"In progress: {confirmed}/{spec['n_recovery']} receipts, " \
                 f"{counterparties}/{spec['min_counterparties']} counterparties, " \
                 f"{window_remaining:.0f}d remaining"
        new_state = AgentState.RECOVERING
    
    return RecoveryResult(
        success=requirements_met,
        new_state=new_state,
        new_score=round(new_score, 4),
        wilson_ci=round(wilson, 4),
        receipts_completed=confirmed,
        receipts_required=spec["n_recovery"],
        counterparties=counterparties,
        counterparties_required=spec["min_counterparties"],
        window_remaining_days=round(window_remaining, 1),
        path=attempt.path.value,
        reason=reason
    )


def compare_recovery_paths():
    """Show Wilson CI outcomes across all three paths."""
    print("=== Wilson CI Comparison Across Recovery Paths ===")
    print(f"{'Path':<25} {'n_req':>5} {'Window':>7} {'CPs':>4} {'Wilson@n':>10} {'Fresh@1':>10}")
    print("-" * 70)
    
    fresh_wilson = wilson_ci_lower(1, 1)
    
    for path, spec in RECOVERY_SPECS.items():
        n = spec["n_recovery"]
        wilson_at_n = wilson_ci_lower(n, n)  # All confirmed
        print(f"{path.value:<25} {n:>5} {spec['window_days']:>5}d {spec['min_counterparties']:>4} "
              f"{wilson_at_n:>10.4f} {fresh_wilson:>10.4f}")
    
    print(f"\nFresh PROVISIONAL at n=1: {fresh_wilson:.4f}")
    print(f"SESSION_RESUMPTION at n=8 (all confirmed): {wilson_ci_lower(8, 8):.4f}")
    print(f"FULL_REATTESTION at n=30 (all confirmed): {wilson_ci_lower(30, 30):.4f}")
    print()


# === Scenarios ===

def scenario_dormant_recovery():
    """6-month dormant agent resumes."""
    print("=== Scenario: DORMANT Recovery (6 months) ===")
    
    attempt = RecoveryAttempt(
        agent_id="veteran_agent",
        prior_state=AgentState.DORMANT,
        prior_score=0.88,
        dormant_months=6,
        path=RecoveryPath.SESSION_RESUMPTION,
        receipts=[(f"cp_{i}", True) for i in range(8)] + [("cp_fail", False)],
        started_at=time.time() - 86400 * 15  # 15 days in
    )
    
    decayed = compute_decayed_score(0.88, 6)
    result = evaluate_recovery(attempt)
    
    print(f"  Prior score: 0.88, Decayed (6mo): {decayed:.3f}")
    print(f"  Path: {result.path}")
    print(f"  Receipts: {result.receipts_completed}/{result.receipts_required}")
    print(f"  Counterparties: {result.counterparties}/{result.counterparties_required}")
    print(f"  Wilson CI: {result.wilson_ci}")
    print(f"  New score: {result.new_score}")
    print(f"  State: {result.new_state.value}")
    print(f"  Result: {result.reason}")
    print()


def scenario_degraded_violation():
    """DEGRADED agent clears violation."""
    print("=== Scenario: DEGRADED → VIOLATION_CLEAR ===")
    
    attempt = RecoveryAttempt(
        agent_id="degraded_agent",
        prior_state=AgentState.DEGRADED,
        prior_score=0.45,
        dormant_months=0,
        path=RecoveryPath.VIOLATION_CLEAR,
        receipts=[(f"cp_{i%4}", True) for i in range(8)],
        started_at=time.time() - 86400 * 20  # 20 days in
    )
    
    result = evaluate_recovery(attempt)
    
    print(f"  Prior score: 0.45 (DEGRADED)")
    print(f"  Path: {result.path}")
    print(f"  Receipts: {result.receipts_completed}/{result.receipts_required}")
    print(f"  Counterparties: {result.counterparties}/{result.counterparties_required}")
    print(f"  Grade floor: C (0.6) — prior tainted receipts ignored")
    print(f"  Wilson CI: {result.wilson_ci}")
    print(f"  New score: {result.new_score}")
    print(f"  State: {result.new_state.value}")
    print(f"  Result: {result.reason}")
    print()


def scenario_abandoned_full():
    """ABANDONED agent does full re-attestation."""
    print("=== Scenario: ABANDONED → FULL_REATTESTION ===")
    
    attempt = RecoveryAttempt(
        agent_id="ghost_agent",
        prior_state=AgentState.ABANDONED,
        prior_score=0.30,
        dormant_months=18,
        path=RecoveryPath.FULL_REATTESTION,
        receipts=[(f"cp_{i%6}", True) for i in range(30)],
        started_at=time.time() - 86400 * 60  # 60 days in
    )
    
    result = evaluate_recovery(attempt)
    
    print(f"  Prior: ABANDONED, 18 months gone")
    print(f"  Path: {result.path}")
    print(f"  Receipts: {result.receipts_completed}/{result.receipts_required}")
    print(f"  Counterparties: {result.counterparties}/{result.counterparties_required}")
    print(f"  Grade floor: D (0.4) — near-fresh start")
    print(f"  Wilson CI: {result.wilson_ci}")
    print(f"  New score: {result.new_score}")
    print(f"  State: {result.new_state.value}")
    print(f"  Window: {result.window_remaining_days}d remaining")
    print()


def scenario_expired_window():
    """Recovery attempt exceeds 30d window."""
    print("=== Scenario: EXPIRED Recovery Window ===")
    
    attempt = RecoveryAttempt(
        agent_id="slow_agent",
        prior_state=AgentState.DEGRADED,
        prior_score=0.50,
        dormant_months=0,
        path=RecoveryPath.VIOLATION_CLEAR,
        receipts=[(f"cp_{i}", True) for i in range(5)],  # Only 5, needed 8
        started_at=time.time() - 86400 * 35  # 35 days — past 30d window
    )
    
    result = evaluate_recovery(attempt)
    
    print(f"  Receipts: {result.receipts_completed}/{result.receipts_required} (insufficient)")
    print(f"  Window: EXPIRED by {-result.window_remaining_days:.0f} days")
    print(f"  State: {result.new_state.value} (remains DEGRADED)")
    print(f"  Score penalty: {result.new_score} (0.8x for failed recovery)")
    print(f"  Result: {result.reason}")
    print()


if __name__ == "__main__":
    print("n-Recovery Spec — ATF V1.2 Gap #3")
    print("Per santaclawd: n_recovery=8 + 30d time cap")
    print("RFC 5280 §5.3.1 certificateHold → removeFromCRL")
    print("=" * 70)
    print()
    
    compare_recovery_paths()
    scenario_dormant_recovery()
    scenario_degraded_violation()
    scenario_abandoned_full()
    scenario_expired_window()
    
    print("=" * 70)
    print("SPEC TEXT (V1.2):")
    print("  recovery_window MUST NOT exceed 30d (SESSION/VIOLATION) or 90d (FULL)")
    print("  n_recovery = 8 CONFIRMED receipts (SESSION/VIOLATION)")
    print("  n_recovery = 30 CONFIRMED receipts (FULL)")
    print("  min_counterparties = 3 independent (SESSION/VIOLATION), 5 (FULL)")
    print("  Window exceeded = recovery FAILED, score penalized 0.8x")
    print("  COMPLETION resets window — individual receipts do not")
