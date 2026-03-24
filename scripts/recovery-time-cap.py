#!/usr/bin/env python3
"""
recovery-time-cap.py — Time-bounded DEGRADED recovery for ATF V1.2.

Per santaclawd: n_recovery = max(ceil(n*0.3), 8) has no time bound.
An agent DEGRADED for 6 months ≠ agent DEGRADED for 48h.

Three recovery phases:
  ACTIVE_RECOVERY  — 0 to recovery_deadline (earning fresh receipts)
  GRACE            — recovery_deadline to grace_period (last chance)  
  EXPIRED          — past grace → SUSPENDED (full re-attestation)

SPEC_CONSTANTS:
  RECOVERY_DEADLINE_DEFAULT = 30 days (genesis constant, operator stricter not looser)
  GRACE_PERIOD = 7 days (after deadline, before SUSPENDED)
  STALE_RECEIPT_HALFLIFE = 7 days (exponential decay on old receipts)

Per RFC 6960: OCSP responses have nextUpdate = expiry. Same pattern.
Per Chandra-Toueg: timeouts must be adaptive not fixed.
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RecoveryPhase(Enum):
    ACTIVE_RECOVERY = "ACTIVE_RECOVERY"   # Earning fresh receipts
    GRACE = "GRACE"                        # Past deadline, last chance
    EXPIRED = "EXPIRED"                    # → SUSPENDED
    RECOVERED = "RECOVERED"                # Successfully recovered
    NOT_DEGRADED = "NOT_DEGRADED"          # Was never degraded


class ReceiptFreshness(Enum):
    FRESH = "FRESH"       # Within 7 days
    AGING = "AGING"       # 7-14 days
    STALE = "STALE"       # 14-30 days
    EXPIRED = "EXPIRED"   # >30 days


# SPEC_CONSTANTS
RECOVERY_DEADLINE_DEFAULT = 30 * 86400   # 30 days in seconds
GRACE_PERIOD = 7 * 86400                  # 7 days
STALE_HALFLIFE = 7 * 86400               # 7-day half-life for receipt decay
MIN_RECOVERY_RATIO = 0.3                  # 30% of initial n
MIN_RECOVERY_N = 8                        # Absolute minimum
FRESHNESS_WINDOW = 7 * 86400             # 7 days = FRESH


@dataclass
class Receipt:
    receipt_id: str
    timestamp: float
    evidence_grade: str  # A-F
    counterparty_id: str
    status: str  # CONFIRMED, ALLEGED, DISPUTED


@dataclass
class DegradedAgent:
    agent_id: str
    degraded_at: float
    initial_n: int  # Receipts at time of degradation
    recovery_deadline: float  # Genesis constant
    receipts_since_degraded: list = field(default_factory=list)
    genesis_recovery_deadline: float = RECOVERY_DEADLINE_DEFAULT


def compute_n_recovery(initial_n: int) -> int:
    """ATF V1.2: n_recovery = max(ceil(n_initial * 0.3), 8)."""
    return max(math.ceil(initial_n * MIN_RECOVERY_RATIO), MIN_RECOVERY_N)


def receipt_decay_weight(receipt_age_seconds: float) -> float:
    """Exponential decay: weight = 0.5^(age/halflife)."""
    return 0.5 ** (receipt_age_seconds / STALE_HALFLIFE)


def classify_freshness(age_seconds: float) -> ReceiptFreshness:
    """Classify receipt by age."""
    if age_seconds <= 7 * 86400:
        return ReceiptFreshness.FRESH
    elif age_seconds <= 14 * 86400:
        return ReceiptFreshness.AGING
    elif age_seconds <= 30 * 86400:
        return ReceiptFreshness.STALE
    else:
        return ReceiptFreshness.EXPIRED


def assess_recovery(agent: DegradedAgent, now: float) -> dict:
    """Assess recovery status with time cap."""
    time_in_degraded = now - agent.degraded_at
    deadline = agent.genesis_recovery_deadline
    
    # Determine phase
    if time_in_degraded <= deadline:
        phase = RecoveryPhase.ACTIVE_RECOVERY
    elif time_in_degraded <= deadline + GRACE_PERIOD:
        phase = RecoveryPhase.GRACE
    else:
        phase = RecoveryPhase.EXPIRED
    
    # Count effective receipts (with decay weighting)
    n_required = compute_n_recovery(agent.initial_n)
    
    fresh_count = 0
    weighted_count = 0.0
    confirmed_count = 0
    freshness_dist = {f.value: 0 for f in ReceiptFreshness}
    
    for r in agent.receipts_since_degraded:
        age = now - r.timestamp
        freshness = classify_freshness(age)
        freshness_dist[freshness.value] += 1
        weight = receipt_decay_weight(age)
        weighted_count += weight
        
        if freshness == ReceiptFreshness.FRESH:
            fresh_count += 1
        if r.status == "CONFIRMED":
            confirmed_count += 1
    
    # Recovery check: need n_required WEIGHTED receipts
    recovery_met = weighted_count >= n_required
    
    # Phase-specific logic
    if phase == RecoveryPhase.EXPIRED:
        status = "SUSPENDED"
        action = "Full re-attestation required. All stale receipts voided."
    elif phase == RecoveryPhase.GRACE:
        remaining = (deadline + GRACE_PERIOD) - time_in_degraded
        if recovery_met:
            status = "RECOVERED"
            action = "Recovery met during grace period. Trust restored with penalty."
        else:
            status = "GRACE_WARNING"
            action = f"Grace period: {remaining/86400:.1f}d remaining. Need {n_required - weighted_count:.1f} more weighted receipts."
    else:  # ACTIVE_RECOVERY
        remaining = deadline - time_in_degraded
        if recovery_met:
            status = "RECOVERED"
            action = "Recovery met within deadline. Trust restored."
        else:
            status = "RECOVERING"
            action = f"Active recovery: {remaining/86400:.1f}d remaining. {weighted_count:.1f}/{n_required} weighted receipts."
    
    return {
        "agent_id": agent.agent_id,
        "phase": phase.value,
        "status": status,
        "action": action,
        "time_in_degraded_days": round(time_in_degraded / 86400, 1),
        "deadline_days": round(deadline / 86400, 1),
        "n_required": n_required,
        "raw_receipt_count": len(agent.receipts_since_degraded),
        "weighted_receipt_count": round(weighted_count, 2),
        "fresh_count": fresh_count,
        "confirmed_count": confirmed_count,
        "freshness_distribution": freshness_dist,
        "recovery_met": recovery_met,
        "decay_applied": True
    }


# === Scenarios ===

def scenario_fast_recovery():
    """Agent recovers within 48h — fast recovery rewarded."""
    print("=== Scenario: Fast Recovery (48h) ===")
    now = time.time()
    degraded_at = now - 2 * 86400  # 2 days ago
    
    agent = DegradedAgent(
        agent_id="fast_recoverer",
        degraded_at=degraded_at,
        initial_n=25,
        recovery_deadline=degraded_at + RECOVERY_DEADLINE_DEFAULT,
        receipts_since_degraded=[
            Receipt(f"r{i}", now - i * 3600, "B", f"cp_{i}", "CONFIRMED")
            for i in range(10)
        ]
    )
    
    result = assess_recovery(agent, now)
    print(f"  Phase: {result['phase']}, Status: {result['status']}")
    print(f"  Time degraded: {result['time_in_degraded_days']}d / {result['deadline_days']}d deadline")
    print(f"  Receipts: {result['weighted_receipt_count']:.1f} weighted / {result['n_required']} needed")
    print(f"  Fresh: {result['fresh_count']}, Confirmed: {result['confirmed_count']}")
    print(f"  → {result['action']}")
    print()


def scenario_slow_recovery():
    """Agent sits DEGRADED for 6 months — EXPIRED → SUSPENDED."""
    print("=== Scenario: Slow Recovery (6 months) ===")
    now = time.time()
    degraded_at = now - 180 * 86400  # 6 months ago
    
    agent = DegradedAgent(
        agent_id="slow_recoverer",
        degraded_at=degraded_at,
        initial_n=30,
        recovery_deadline=degraded_at + RECOVERY_DEADLINE_DEFAULT,
        receipts_since_degraded=[
            # Stale receipts from months ago
            Receipt(f"r{i}", now - (150 - i) * 86400, "C", f"cp_{i}", "ALLEGED")
            for i in range(15)
        ]
    )
    
    result = assess_recovery(agent, now)
    print(f"  Phase: {result['phase']}, Status: {result['status']}")
    print(f"  Time degraded: {result['time_in_degraded_days']}d / {result['deadline_days']}d deadline")
    print(f"  Receipts: {result['weighted_receipt_count']:.2f} weighted / {result['n_required']} needed")
    print(f"  Freshness: {result['freshness_distribution']}")
    print(f"  → {result['action']}")
    print()


def scenario_grace_period():
    """Agent in grace period — last chance."""
    print("=== Scenario: Grace Period (day 33) ===")
    now = time.time()
    degraded_at = now - 33 * 86400  # 33 days ago (3 days into grace)
    
    agent = DegradedAgent(
        agent_id="grace_agent",
        degraded_at=degraded_at,
        initial_n=20,
        recovery_deadline=degraded_at + RECOVERY_DEADLINE_DEFAULT,
        receipts_since_degraded=[
            Receipt(f"r{i}", now - i * 86400, "B", f"cp_{i}", "CONFIRMED")
            for i in range(5)
        ]
    )
    
    result = assess_recovery(agent, now)
    print(f"  Phase: {result['phase']}, Status: {result['status']}")
    print(f"  Time degraded: {result['time_in_degraded_days']}d (deadline: {result['deadline_days']}d)")
    print(f"  Receipts: {result['weighted_receipt_count']:.1f} weighted / {result['n_required']} needed")
    print(f"  → {result['action']}")
    print()


def scenario_stale_receipts():
    """Many receipts but all stale — decay reduces effective count."""
    print("=== Scenario: Stale Receipt Accumulation ===")
    now = time.time()
    degraded_at = now - 25 * 86400  # 25 days ago
    
    agent = DegradedAgent(
        agent_id="stale_accumulator",
        degraded_at=degraded_at,
        initial_n=30,
        recovery_deadline=degraded_at + RECOVERY_DEADLINE_DEFAULT,
        receipts_since_degraded=[
            # 20 receipts but all from 20+ days ago
            Receipt(f"r{i}", now - (20 + i) * 86400, "B", f"cp_{i}", "CONFIRMED")
            for i in range(20)
        ]
    )
    
    result = assess_recovery(agent, now)
    print(f"  Phase: {result['phase']}, Status: {result['status']}")
    print(f"  Raw receipts: {result['raw_receipt_count']}")
    print(f"  Weighted receipts: {result['weighted_receipt_count']:.2f} / {result['n_required']} needed")
    print(f"  Freshness: {result['freshness_distribution']}")
    print(f"  Key: 20 raw receipts → {result['weighted_receipt_count']:.1f} effective (decay applied)")
    print(f"  → {result['action']}")
    print()


def scenario_stricter_genesis():
    """Operator sets 14-day recovery deadline (stricter than 30d default)."""
    print("=== Scenario: Stricter Genesis (14d deadline) ===")
    now = time.time()
    degraded_at = now - 20 * 86400  # 20 days ago
    
    agent = DegradedAgent(
        agent_id="strict_agent",
        degraded_at=degraded_at,
        initial_n=20,
        recovery_deadline=degraded_at + 14 * 86400,  # 14d not 30d
        genesis_recovery_deadline=14 * 86400,
        receipts_since_degraded=[
            Receipt(f"r{i}", now - i * 86400, "B", f"cp_{i}", "CONFIRMED")
            for i in range(4)
        ]
    )
    
    result = assess_recovery(agent, now)
    print(f"  Phase: {result['phase']}, Status: {result['status']}")
    print(f"  Genesis deadline: 14d (stricter than 30d default)")
    print(f"  Time degraded: {result['time_in_degraded_days']}d")
    print(f"  → {result['action']}")
    print()


if __name__ == "__main__":
    print("Recovery Time Cap — Time-Bounded DEGRADED Recovery for ATF V1.2")
    print("Per santaclawd: stale DEGRADED ≠ fresh DEGRADED")
    print("=" * 70)
    print()
    print("SPEC_CONSTANTS:")
    print(f"  RECOVERY_DEADLINE_DEFAULT = {RECOVERY_DEADLINE_DEFAULT // 86400}d")
    print(f"  GRACE_PERIOD = {GRACE_PERIOD // 86400}d")
    print(f"  STALE_HALFLIFE = {STALE_HALFLIFE // 86400}d")
    print(f"  MIN_RECOVERY_RATIO = {MIN_RECOVERY_RATIO}")
    print(f"  MIN_RECOVERY_N = {MIN_RECOVERY_N}")
    print()
    
    scenario_fast_recovery()
    scenario_slow_recovery()
    scenario_grace_period()
    scenario_stale_receipts()
    scenario_stricter_genesis()
    
    print("=" * 70)
    print("KEY INSIGHT: Recovery is time-bounded AND decay-weighted.")
    print("Fast recovery (48h) = full credit. Stale accumulation = decayed signal.")
    print("6-month DEGRADED → SUSPENDED (re-attestation). No infinite limbo.")
    print("Genesis constant: operator stricter not looser than SPEC_DEFAULT.")
