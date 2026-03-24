#!/usr/bin/env python3
"""
recovery-time-cap.py — Time-bounded DEGRADED recovery for ATF V1.2.

Per santaclawd: n_recovery = max(ceil(n*0.3), 8) exists but no time bound.
An agent DEGRADED for 6 months ≠ 48 hours. Stale ALLEGED receipts mislead.

Three recovery phases:
  ACTIVE_RECOVERY  — 0-72h from DEGRADED entry. Fresh receipts count 1.0x.
  STALE_RECOVERY   — 72h-30d. Receipts count 0.5x (time-decayed).
  EXPIRED          — >30d. Full re-attestation required. Cannot recover in-place.

X.509 parallel: CRL thisUpdate/nextUpdate. OCSP responses expire.
Short-lived certs (6 days) replace revocation — same principle.
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RecoveryPhase(Enum):
    ACTIVE = "ACTIVE_RECOVERY"     # 0-72h, full weight
    STALE = "STALE_RECOVERY"       # 72h-30d, 0.5x weight
    EXPIRED = "EXPIRED"            # >30d, re-attestation required
    RECOVERED = "RECOVERED"        # Successfully recovered
    RE_ATTESTATION = "RE_ATTESTATION"  # Must start fresh


# SPEC_CONSTANTS (V1.2)
ACTIVE_WINDOW_HOURS = 72          # Phase 1: full-weight recovery
STALE_WINDOW_DAYS = 30            # Phase 2: decayed recovery
RECEIPT_HALF_LIFE_HOURS = 168     # 7 days — receipt value halves
MIN_RECOVERY_RECEIPTS = 8         # Minimum to exit DEGRADED
RECOVERY_RATIO = 0.3              # n_recovery = max(ceil(n * 0.3), MIN)
STALE_DECAY_FACTOR = 0.5          # Receipts in STALE phase count 0.5x
EXPIRED_PENALTY = "FULL_RE_ATTESTATION"


@dataclass
class Receipt:
    receipt_id: str
    timestamp: float
    evidence_grade: str  # A-F
    counterparty_id: str
    is_confirmed: bool   # CONFIRMED vs ALLEGED
    
    def effective_weight(self, degraded_at: float) -> float:
        """Compute time-decayed weight of this receipt."""
        age_hours = (self.timestamp - degraded_at) / 3600
        
        if age_hours < 0:
            return 0.0  # Receipt predates DEGRADED — doesn't count
        
        if age_hours <= ACTIVE_WINDOW_HOURS:
            phase_multiplier = 1.0
        elif age_hours <= STALE_WINDOW_DAYS * 24:
            phase_multiplier = STALE_DECAY_FACTOR
        else:
            return 0.0  # Expired
        
        # Half-life decay within phase
        decay = 0.5 ** (age_hours / RECEIPT_HALF_LIFE_HOURS)
        
        # CONFIRMED > ALLEGED
        confirmation_multiplier = 1.0 if self.is_confirmed else 0.7
        
        # Grade weight
        grade_weights = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4, "F": 0.0}
        grade_mult = grade_weights.get(self.evidence_grade, 0.0)
        
        return round(phase_multiplier * decay * confirmation_multiplier * grade_mult, 4)


@dataclass
class RecoveryState:
    agent_id: str
    degraded_at: float
    n_initial: int
    receipts: list[Receipt] = field(default_factory=list)
    
    @property
    def n_recovery(self) -> int:
        return max(math.ceil(self.n_initial * RECOVERY_RATIO), MIN_RECOVERY_RECEIPTS)
    
    @property
    def hours_since_degraded(self) -> float:
        return (time.time() - self.degraded_at) / 3600
    
    @property
    def phase(self) -> RecoveryPhase:
        hours = self.hours_since_degraded
        if hours <= ACTIVE_WINDOW_HOURS:
            return RecoveryPhase.ACTIVE
        elif hours <= STALE_WINDOW_DAYS * 24:
            return RecoveryPhase.STALE
        else:
            return RecoveryPhase.EXPIRED
    
    def effective_receipt_count(self) -> float:
        """Sum of time-decayed receipt weights."""
        return sum(r.effective_weight(self.degraded_at) for r in self.receipts)
    
    def recovery_progress(self) -> dict:
        """Calculate recovery progress."""
        phase = self.phase
        effective = self.effective_receipt_count()
        target = self.n_recovery
        progress = min(effective / target, 1.0) if target > 0 else 0
        
        if phase == RecoveryPhase.EXPIRED:
            return {
                "phase": phase.value,
                "status": "REQUIRES_RE_ATTESTATION",
                "effective_receipts": round(effective, 2),
                "target": target,
                "progress": 0.0,
                "message": f"DEGRADED for >{STALE_WINDOW_DAYS}d. Recovery window closed. Full re-attestation required."
            }
        
        recovered = effective >= target
        
        return {
            "phase": phase.value,
            "status": "RECOVERED" if recovered else "IN_PROGRESS",
            "effective_receipts": round(effective, 2),
            "target": target,
            "progress": round(progress, 4),
            "hours_remaining": max(0, STALE_WINDOW_DAYS * 24 - self.hours_since_degraded),
            "phase_multiplier": 1.0 if phase == RecoveryPhase.ACTIVE else STALE_DECAY_FACTOR,
            "receipts_raw": len(self.receipts),
            "message": (
                f"Recovered! {effective:.1f}/{target} effective receipts." if recovered
                else f"Need {target - effective:.1f} more effective receipts in {phase.value} phase."
            )
        }


def compare_recovery_speeds(n_initial: int) -> dict:
    """Compare 48h recovery vs 6-month recovery."""
    now = time.time()
    
    # Fast recovery: 48h ago
    fast = RecoveryState("fast_agent", now - 48*3600, n_initial)
    for i in range(12):
        fast.receipts.append(Receipt(
            f"r{i}", now - (48-i*4)*3600, "B", f"cp_{i}", True
        ))
    
    # Slow recovery: 6 months ago
    slow = RecoveryState("slow_agent", now - 180*24*3600, n_initial)
    for i in range(12):
        slow.receipts.append(Receipt(
            f"r{i}", now - (180*24 - i*24)*3600, "B", f"cp_{i}", True
        ))
    
    return {
        "n_initial": n_initial,
        "n_recovery": fast.n_recovery,
        "fast_48h": fast.recovery_progress(),
        "slow_6mo": slow.recovery_progress()
    }


# === Scenarios ===

def scenario_active_recovery():
    """Agent recovers within 72h — full weight."""
    print("=== Scenario: Active Recovery (48h) ===")
    now = time.time()
    state = RecoveryState("kit_fox", now - 48*3600, 25)
    
    # 10 CONFIRMED receipts over 48h
    for i in range(10):
        state.receipts.append(Receipt(
            f"r{i}", now - (48-i*5)*3600, "B", f"bro_agent_{i%3}", True
        ))
    
    progress = state.recovery_progress()
    print(f"  Phase: {progress['phase']}")
    print(f"  Effective: {progress['effective_receipts']}/{progress['target']}")
    print(f"  Progress: {progress['progress']:.0%}")
    print(f"  Status: {progress['status']}")
    print()


def scenario_stale_recovery():
    """Agent recovers after 15 days — decayed weight."""
    print("=== Scenario: Stale Recovery (15 days) ===")
    now = time.time()
    state = RecoveryState("slow_agent", now - 15*24*3600, 25)
    
    # 10 receipts at day 14-15
    for i in range(10):
        state.receipts.append(Receipt(
            f"r{i}", now - (15*24 - i*3)*3600, "B", f"cp_{i}", True
        ))
    
    progress = state.recovery_progress()
    print(f"  Phase: {progress['phase']}")
    print(f"  Effective: {progress['effective_receipts']}/{progress['target']}")
    print(f"  Progress: {progress['progress']:.0%}")
    print(f"  Phase multiplier: {progress['phase_multiplier']}x")
    print(f"  Hours remaining: {progress['hours_remaining']:.0f}h")
    print(f"  Note: same 10 receipts = {progress['progress']:.0%} in STALE vs ~100% in ACTIVE")
    print()


def scenario_expired():
    """Agent DEGRADED > 30 days — must re-attest."""
    print("=== Scenario: Expired (45 days) ===")
    now = time.time()
    state = RecoveryState("zombie_agent", now - 45*24*3600, 25)
    
    # Even with fresh receipts, expired = re-attestation
    for i in range(15):
        state.receipts.append(Receipt(
            f"r{i}", now - i*3600, "A", f"cp_{i}", True
        ))
    
    progress = state.recovery_progress()
    print(f"  Phase: {progress['phase']}")
    print(f"  Status: {progress['status']}")
    print(f"  Message: {progress['message']}")
    print(f"  15 fresh A-grade receipts = does not matter. Window closed.")
    print()


def scenario_48h_vs_6mo():
    """Direct comparison: same receipts, different timing."""
    print("=== Scenario: 48h vs 6mo Recovery Comparison ===")
    result = compare_recovery_speeds(25)
    
    fast = result['fast_48h']
    slow = result['slow_6mo']
    
    print(f"  n_initial={result['n_initial']}, n_recovery={result['n_recovery']}")
    print(f"  Fast (48h):  {fast['status']} — {fast['effective_receipts']}/{fast['target']} ({fast['progress']:.0%})")
    print(f"  Slow (6mo):  {slow['status']} — {slow['effective_receipts']}/{slow['target']} ({slow['progress']:.0%})")
    print(f"  Key: same receipt count, DIFFERENT outcomes. Time cap is load-bearing.")
    print()


def scenario_alleged_vs_confirmed():
    """ALLEGED receipts during recovery count less."""
    print("=== Scenario: ALLEGED vs CONFIRMED During Recovery ===")
    now = time.time()
    
    confirmed = RecoveryState("confirmed_agent", now - 24*3600, 20)
    alleged = RecoveryState("alleged_agent", now - 24*3600, 20)
    
    for i in range(8):
        confirmed.receipts.append(Receipt(f"r{i}", now - i*3600, "B", f"cp_{i}", True))
        alleged.receipts.append(Receipt(f"r{i}", now - i*3600, "B", f"cp_{i}", False))
    
    c_progress = confirmed.recovery_progress()
    a_progress = alleged.recovery_progress()
    
    print(f"  8 CONFIRMED: {c_progress['effective_receipts']:.2f}/{c_progress['target']} ({c_progress['progress']:.0%})")
    print(f"  8 ALLEGED:   {a_progress['effective_receipts']:.2f}/{a_progress['target']} ({a_progress['progress']:.0%})")
    print(f"  ALLEGED = 0.7x weight. Recovery from DEGRADED rewards bilateral verification.")
    print()


if __name__ == "__main__":
    print("Recovery Time Cap — Time-Bounded DEGRADED Recovery for ATF V1.2")
    print("Per santaclawd: 48h recovery ≠ 6-month recovery")
    print("=" * 70)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  ACTIVE_WINDOW:     {ACTIVE_WINDOW_HOURS}h (full weight)")
    print(f"  STALE_WINDOW:      {STALE_WINDOW_DAYS}d (0.5x weight)")
    print(f"  EXPIRED:           >{STALE_WINDOW_DAYS}d (re-attestation)")
    print(f"  RECEIPT_HALF_LIFE: {RECEIPT_HALF_LIFE_HOURS}h")
    print(f"  MIN_RECOVERY:      {MIN_RECOVERY_RECEIPTS} receipts")
    print()
    
    scenario_active_recovery()
    scenario_stale_recovery()
    scenario_expired()
    scenario_48h_vs_6mo()
    scenario_alleged_vs_confirmed()
    
    print("=" * 70)
    print("KEY INSIGHT: Recovery without time bound = zombie DEGRADED.")
    print("X.509 CRL has thisUpdate/nextUpdate. OCSP responses expire.")
    print("ATF recovery MUST expire. 30d cap. After that: re-attest from zero.")
    print("Short-lived recovery > long-lived recovery + revocation.")
