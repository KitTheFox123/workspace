#!/usr/bin/env python3
"""
recovery-time-cap.py — Time-bounded recovery for ATF DEGRADED agents.

Per santaclawd: n_recovery = max(ceil(n*0.3), 8) but no time bound.
An agent DEGRADED for 6 months ≠ 48h. Stale ALLEGED receipts accumulate
misleading recovery signals.

RFC 5280 Section 3.3: CRL nextUpdate = time bound on validity.
Same principle: DEGRADED state must expire.

Three phases:
  DEGRADED_ACTIVE  — 0-30d, recovery possible via n_recovery receipts
  DEGRADED_STALE   — 30-90d, recovery requires 2x n_recovery + audit
  DEGRADED_EXPIRED — >90d, full re-attestation from BOOTSTRAP_REQUEST
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RecoveryPhase(Enum):
    DEGRADED_ACTIVE = "DEGRADED_ACTIVE"     # Fresh, recovery straightforward
    DEGRADED_STALE = "DEGRADED_STALE"       # Aging, harder recovery
    DEGRADED_EXPIRED = "DEGRADED_EXPIRED"   # Must re-bootstrap
    RECOVERED = "RECOVERED"
    BOOTSTRAPPING = "BOOTSTRAPPING"


# SPEC_CONSTANTS
ACTIVE_WINDOW_DAYS = 30       # Phase 1: normal recovery
STALE_WINDOW_DAYS = 90        # Phase 2: harder recovery  
RECOVERY_RATIO = 0.3          # n_recovery = ceil(n_initial * ratio)
MIN_RECOVERY_N = 8            # Floor
STALE_MULTIPLIER = 2.0        # 2x receipts needed in stale phase
RECEIPT_DECAY_HALFLIFE = 14   # Days before receipt weight halves
MAX_ALLEGED_STACK = 50        # Cap on stale ALLEGED receipts counted


@dataclass
class DegradedAgent:
    agent_id: str
    degraded_at: float        # Timestamp of DEGRADED entry
    n_initial: int            # Original attestation count
    receipts_since: list = field(default_factory=list)  # (timestamp, grade, counterparty)
    reason: str = ""
    
    @property
    def n_recovery(self) -> int:
        return max(int(self.n_initial * RECOVERY_RATIO + 0.999), MIN_RECOVERY_N)
    
    @property
    def days_degraded(self) -> float:
        return (time.time() - self.degraded_at) / 86400
    
    @property
    def phase(self) -> RecoveryPhase:
        d = self.days_degraded
        if d <= ACTIVE_WINDOW_DAYS:
            return RecoveryPhase.DEGRADED_ACTIVE
        elif d <= STALE_WINDOW_DAYS:
            return RecoveryPhase.DEGRADED_STALE
        else:
            return RecoveryPhase.DEGRADED_EXPIRED


def receipt_weight(receipt_age_days: float) -> float:
    """Exponential decay on receipt freshness."""
    return 2 ** (-receipt_age_days / RECEIPT_DECAY_HALFLIFE)


def evaluate_recovery(agent: DegradedAgent) -> dict:
    """Evaluate whether agent can recover from DEGRADED."""
    phase = agent.phase
    now = time.time()
    
    if phase == RecoveryPhase.DEGRADED_EXPIRED:
        return {
            "agent_id": agent.agent_id,
            "phase": phase.value,
            "days_degraded": round(agent.days_degraded, 1),
            "recovery_possible": False,
            "action": "BOOTSTRAP_REQUEST required. Full re-attestation.",
            "n_recovery": agent.n_recovery,
            "receipts_counted": 0,
            "weighted_receipts": 0.0,
            "reason": f"DEGRADED > {STALE_WINDOW_DAYS}d. Stale ALLEGED stack unreliable."
        }
    
    # Count receipts with decay weighting
    required = agent.n_recovery
    if phase == RecoveryPhase.DEGRADED_STALE:
        required = int(required * STALE_MULTIPLIER)
    
    weighted_sum = 0.0
    valid_receipts = 0
    alleged_count = 0
    
    for ts, grade, counterparty in agent.receipts_since:
        age_days = (now - ts) / 86400
        weight = receipt_weight(age_days)
        
        # Grade multiplier
        grade_mult = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4, "F": 0.0}.get(grade, 0.0)
        
        # ALLEGED receipts count but are capped
        if grade in ("D", "F"):
            alleged_count += 1
            if alleged_count > MAX_ALLEGED_STACK:
                continue  # Cap stale ALLEGED
        
        contribution = weight * grade_mult
        weighted_sum += contribution
        if contribution > 0.1:  # Minimum threshold
            valid_receipts += 1
    
    can_recover = weighted_sum >= required * 0.7  # 70% of weighted target
    
    return {
        "agent_id": agent.agent_id,
        "phase": phase.value,
        "days_degraded": round(agent.days_degraded, 1),
        "n_recovery_base": agent.n_recovery,
        "n_recovery_adjusted": required,
        "receipts_total": len(agent.receipts_since),
        "receipts_valid": valid_receipts,
        "weighted_sum": round(weighted_sum, 2),
        "weighted_target": round(required * 0.7, 2),
        "alleged_capped": alleged_count > MAX_ALLEGED_STACK,
        "recovery_possible": can_recover,
        "action": "RECOVER" if can_recover else f"Need {round(required * 0.7 - weighted_sum, 1)} more weighted receipts",
        "next_phase_in": _next_phase_days(agent)
    }


def _next_phase_days(agent: DegradedAgent) -> Optional[float]:
    d = agent.days_degraded
    if d < ACTIVE_WINDOW_DAYS:
        return round(ACTIVE_WINDOW_DAYS - d, 1)
    elif d < STALE_WINDOW_DAYS:
        return round(STALE_WINDOW_DAYS - d, 1)
    return None  # Already expired


# === Scenarios ===

def scenario_fresh_recovery():
    """Agent recovers within 30-day active window."""
    print("=== Scenario: Fresh Recovery (Active Phase) ===")
    now = time.time()
    
    agent = DegradedAgent(
        agent_id="recovering_agent",
        degraded_at=now - 86400 * 10,  # 10 days ago
        n_initial=30,
        reason="grader_revoked"
    )
    
    # Add 12 good receipts over last 10 days
    for i in range(12):
        agent.receipts_since.append((now - 86400 * i, "B", f"counter_{i}"))
    
    result = evaluate_recovery(agent)
    print(f"  Phase: {result['phase']}")
    print(f"  Days degraded: {result['days_degraded']}")
    print(f"  n_recovery: {result['n_recovery_base']} (adjusted: {result['n_recovery_adjusted']})")
    print(f"  Weighted receipts: {result['weighted_sum']}/{result['weighted_target']}")
    print(f"  Recovery: {result['action']}")
    print(f"  Next phase in: {result['next_phase_in']}d")
    print()


def scenario_stale_harder():
    """Agent in stale phase — needs 2x receipts."""
    print("=== Scenario: Stale Phase (2x Requirement) ===")
    now = time.time()
    
    agent = DegradedAgent(
        agent_id="slow_recovery",
        degraded_at=now - 86400 * 45,  # 45 days ago
        n_initial=25,
        reason="dispute_pattern"
    )
    
    # 8 receipts, some old
    for i in range(8):
        agent.receipts_since.append((now - 86400 * (i * 5), "B", f"counter_{i}"))
    
    result = evaluate_recovery(agent)
    print(f"  Phase: {result['phase']}")
    print(f"  Days degraded: {result['days_degraded']}")
    print(f"  n_recovery: {result['n_recovery_base']} → {result['n_recovery_adjusted']} (2x stale)")
    print(f"  Weighted receipts: {result['weighted_sum']}/{result['weighted_target']}")
    print(f"  Recovery: {result['action']}")
    print(f"  Next phase in: {result['next_phase_in']}d")
    print()


def scenario_expired_rebootstrap():
    """Agent DEGRADED > 90 days — must re-bootstrap."""
    print("=== Scenario: Expired — Full Re-Bootstrap Required ===")
    now = time.time()
    
    agent = DegradedAgent(
        agent_id="abandoned_agent",
        degraded_at=now - 86400 * 120,  # 120 days ago
        n_initial=40,
        reason="operator_revoked"
    )
    
    # Even with receipts, expired = no recovery
    for i in range(20):
        agent.receipts_since.append((now - 86400 * i, "A", f"counter_{i}"))
    
    result = evaluate_recovery(agent)
    print(f"  Phase: {result['phase']}")
    print(f"  Days degraded: {result['days_degraded']}")
    print(f"  Has {len(agent.receipts_since)} receipts but: {result['action']}")
    print(f"  Recovery possible: {result['recovery_possible']}")
    print()


def scenario_alleged_stack_misleading():
    """Stale ALLEGED receipts accumulate — capped at MAX_ALLEGED_STACK."""
    print("=== Scenario: Misleading ALLEGED Stack ===")
    now = time.time()
    
    agent = DegradedAgent(
        agent_id="alleged_heavy",
        degraded_at=now - 86400 * 20,  # 20 days ago
        n_initial=30,
        reason="availability_failure"
    )
    
    # 60 D-grade ALLEGED receipts (quantity without quality)
    for i in range(60):
        agent.receipts_since.append((now - 86400 * (i * 0.3), "D", f"sybil_{i % 3}"))
    
    result = evaluate_recovery(agent)
    print(f"  Phase: {result['phase']}")
    print(f"  Total receipts: {result['receipts_total']}")
    print(f"  Valid (weighted > 0.1): {result['receipts_valid']}")
    print(f"  ALLEGED capped: {result['alleged_capped']}")
    print(f"  Weighted sum: {result['weighted_sum']}/{result['weighted_target']}")
    print(f"  Recovery: {result['action']}")
    print(f"  KEY: quantity of low-grade receipts ≠ recovery signal")
    print()


if __name__ == "__main__":
    print("Recovery Time Cap — Time-Bounded DEGRADED Recovery for ATF")
    print("Per santaclawd + RFC 5280 Section 3.3 (CRL nextUpdate)")
    print("=" * 70)
    print()
    print(f"Phases: ACTIVE (0-{ACTIVE_WINDOW_DAYS}d) → STALE ({ACTIVE_WINDOW_DAYS}-{STALE_WINDOW_DAYS}d) → EXPIRED (>{STALE_WINDOW_DAYS}d)")
    print(f"STALE = {STALE_MULTIPLIER}x receipts needed. EXPIRED = BOOTSTRAP_REQUEST.")
    print(f"Receipt decay: {RECEIPT_DECAY_HALFLIFE}d half-life. ALLEGED cap: {MAX_ALLEGED_STACK}.")
    print()
    
    scenario_fresh_recovery()
    scenario_stale_harder()
    scenario_expired_rebootstrap()
    scenario_alleged_stack_misleading()
    
    print("=" * 70)
    print("KEY INSIGHT: DEGRADED without time bound = infinite limbo.")
    print("RFC 5280 CRL nextUpdate = same principle: validity has a deadline.")
    print("Stale ALLEGED receipts mislead — cap + decay + phase gates fix it.")
