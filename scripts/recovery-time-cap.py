#!/usr/bin/env python3
"""
recovery-time-cap.py — Time-bounded DEGRADED recovery for ATF V1.2.

Per santaclawd: n_recovery = max(ceil(n*0.3), 8) has no time bound.
Agent DEGRADED for 6 months ≠ agent DEGRADED for 48h.
Stale receipts accumulate differently.

Three phases:
  ACTIVE    (0-7d)   — Fresh DEGRADED, normal recovery path
  STALE     (7-30d)  — Receipts from this period get decay penalty  
  EXPIRED   (>30d)   — Full re-attestation required, no recovery shortcut

Per IETF BANDAID (Oct 2025): DNS-based discovery has TTL staleness.
Same problem, same fix: explicit time bounds.
"""

import time
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RecoveryPhase(Enum):
    ACTIVE = "ACTIVE"      # Fresh DEGRADED, normal path
    STALE = "STALE"        # Decay penalty on recovery receipts
    EXPIRED = "EXPIRED"    # Full re-attestation, no shortcut


class TrustState(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    REVOKED = "REVOKED"
    RECOVERING = "RECOVERING"


# SPEC_CONSTANTS (V1.2)
ACTIVE_WINDOW_DAYS = 7          # Normal recovery path
STALE_WINDOW_DAYS = 30          # Decay penalty
STALE_DECAY_FACTOR = 0.5        # Receipts worth 50% during STALE
RECOVERY_RATIO = 0.3            # n_recovery = max(ceil(n * 0.3), 8)
MIN_RECOVERY_RECEIPTS = 8       # Minimum regardless of n
MAX_RECOVERY_DAYS = 30          # Hard cap
EXPIRED_PENALTY_MULTIPLIER = 2  # Full re-attestation = 2x normal


@dataclass
class DegradedAgent:
    agent_id: str
    degraded_at: float          # Timestamp when DEGRADED began
    initial_receipts: int       # n_initial at time of degradation
    recovery_receipts: list = field(default_factory=list)  # (timestamp, grade) pairs
    state: TrustState = TrustState.DEGRADED
    
    @property
    def n_recovery(self) -> int:
        """Required recovery receipts per spec."""
        return max(math.ceil(self.initial_receipts * RECOVERY_RATIO), MIN_RECOVERY_RECEIPTS)
    
    @property
    def days_degraded(self) -> float:
        return (time.time() - self.degraded_at) / 86400
    
    @property
    def recovery_phase(self) -> RecoveryPhase:
        days = self.days_degraded
        if days <= ACTIVE_WINDOW_DAYS:
            return RecoveryPhase.ACTIVE
        elif days <= STALE_WINDOW_DAYS:
            return RecoveryPhase.STALE
        else:
            return RecoveryPhase.EXPIRED


def compute_effective_receipts(agent: DegradedAgent) -> float:
    """
    Count effective recovery receipts with time-decay.
    
    ACTIVE phase: receipts count at full value
    STALE phase: receipts count at STALE_DECAY_FACTOR
    EXPIRED: no recovery possible
    """
    if agent.recovery_phase == RecoveryPhase.EXPIRED:
        return 0.0
    
    effective = 0.0
    for ts, grade in agent.recovery_receipts:
        receipt_age_days = (time.time() - ts) / 86400
        degraded_age_at_receipt = (ts - agent.degraded_at) / 86400
        
        if degraded_age_at_receipt <= ACTIVE_WINDOW_DAYS:
            effective += 1.0  # Full value
        elif degraded_age_at_receipt <= STALE_WINDOW_DAYS:
            effective += STALE_DECAY_FACTOR  # Half value
        # Receipts after EXPIRED don't count
    
    return effective


def assess_recovery(agent: DegradedAgent) -> dict:
    """Assess recovery status and provide recommendation."""
    phase = agent.recovery_phase
    n_required = agent.n_recovery
    effective = compute_effective_receipts(agent)
    days = agent.days_degraded
    
    if phase == RecoveryPhase.EXPIRED:
        return {
            "agent_id": agent.agent_id,
            "phase": phase.value,
            "days_degraded": round(days, 1),
            "recommendation": "FULL_RE_ATTESTATION",
            "reason": f"Exceeded {MAX_RECOVERY_DAYS}d recovery window",
            "n_required": n_required * EXPIRED_PENALTY_MULTIPLIER,
            "effective_receipts": 0,
            "progress": 0.0,
            "state": TrustState.REVOKED.value,
            "deadline": "PASSED"
        }
    
    remaining_days = MAX_RECOVERY_DAYS - days
    progress = effective / n_required if n_required > 0 else 0
    
    if effective >= n_required:
        recommendation = "RECOVERY_COMPLETE"
        new_state = TrustState.HEALTHY.value
    elif phase == RecoveryPhase.STALE:
        recommendation = "URGENT_RECOVERY"
        new_state = TrustState.RECOVERING.value
    else:
        recommendation = "NORMAL_RECOVERY"
        new_state = TrustState.RECOVERING.value
    
    receipts_per_day_needed = (n_required - effective) / remaining_days if remaining_days > 0 else float('inf')
    
    return {
        "agent_id": agent.agent_id,
        "phase": phase.value,
        "days_degraded": round(days, 1),
        "remaining_days": round(remaining_days, 1),
        "recommendation": recommendation,
        "n_required": n_required,
        "effective_receipts": round(effective, 1),
        "progress": round(progress, 3),
        "receipts_per_day_needed": round(receipts_per_day_needed, 2),
        "state": new_state,
        "deadline": f"{round(remaining_days, 0)}d remaining"
    }


def fleet_recovery_audit(agents: list[DegradedAgent]) -> dict:
    """Audit fleet of degraded agents."""
    results = [assess_recovery(a) for a in agents]
    
    phase_counts = {}
    for r in results:
        phase_counts[r["phase"]] = phase_counts.get(r["phase"], 0) + 1
    
    expired = [r for r in results if r["phase"] == "EXPIRED"]
    urgent = [r for r in results if r["recommendation"] == "URGENT_RECOVERY"]
    
    return {
        "total_degraded": len(agents),
        "phase_distribution": phase_counts,
        "expired_count": len(expired),
        "urgent_count": len(urgent),
        "expired_agents": [r["agent_id"] for r in expired],
        "urgent_agents": [r["agent_id"] for r in urgent],
        "fleet_health": "CRITICAL" if len(expired) > len(agents) * 0.3 else
                        "WARNING" if len(urgent) > 0 else "HEALTHY"
    }


# === Scenarios ===

def scenario_fresh_degraded():
    """Agent degraded 2 days ago, recovering normally."""
    print("=== Scenario: Fresh DEGRADED (2 days) ===")
    now = time.time()
    agent = DegradedAgent(
        agent_id="fresh_agent",
        degraded_at=now - 2 * 86400,
        initial_receipts=30
    )
    # 4 recovery receipts in 2 days
    for i in range(4):
        agent.recovery_receipts.append((now - (2-i*0.5) * 86400, "B"))
    
    result = assess_recovery(agent)
    print(f"  Phase: {result['phase']}, Days: {result['days_degraded']}")
    print(f"  Progress: {result['effective_receipts']}/{result['n_required']} ({result['progress']:.0%})")
    print(f"  Recommendation: {result['recommendation']}")
    print(f"  Deadline: {result['deadline']}")
    print()


def scenario_stale_degraded():
    """Agent degraded 20 days ago, receipts decayed."""
    print("=== Scenario: STALE DEGRADED (20 days) ===")
    now = time.time()
    agent = DegradedAgent(
        agent_id="stale_agent",
        degraded_at=now - 20 * 86400,
        initial_receipts=50
    )
    # 10 receipts spread across ACTIVE and STALE phases
    for i in range(10):
        day = 2 + i * 2  # Days 2, 4, 6, 8, 10, 12, 14, 16, 18, 20
        agent.recovery_receipts.append((now - (20 - day) * 86400, "B"))
    
    result = assess_recovery(agent)
    print(f"  Phase: {result['phase']}, Days: {result['days_degraded']}")
    print(f"  Progress: {result['effective_receipts']}/{result['n_required']} ({result['progress']:.0%})")
    print(f"  Recommendation: {result['recommendation']}")
    print(f"  Remaining: {result['remaining_days']}d")
    print(f"  Need {result['receipts_per_day_needed']} receipts/day to recover in time")
    print()


def scenario_expired():
    """Agent degraded 45 days ago — full re-attestation required."""
    print("=== Scenario: EXPIRED (45 days) ===")
    now = time.time()
    agent = DegradedAgent(
        agent_id="zombie_agent",
        degraded_at=now - 45 * 86400,
        initial_receipts=40
    )
    # Had some receipts but too late
    for i in range(5):
        agent.recovery_receipts.append((now - (45 - i * 10) * 86400, "C"))
    
    result = assess_recovery(agent)
    print(f"  Phase: {result['phase']}, Days: {result['days_degraded']}")
    print(f"  Recommendation: {result['recommendation']}")
    print(f"  Required for re-attestation: {result['n_required']} (2x normal)")
    print(f"  State: {result['state']}")
    print(f"  Deadline: {result['deadline']}")
    print()


def scenario_fleet_audit():
    """Fleet of 10 degraded agents across all phases."""
    print("=== Scenario: Fleet Recovery Audit ===")
    now = time.time()
    
    agents = [
        DegradedAgent("agent_1d", now - 1 * 86400, 20),     # ACTIVE
        DegradedAgent("agent_3d", now - 3 * 86400, 30),     # ACTIVE
        DegradedAgent("agent_5d", now - 5 * 86400, 25),     # ACTIVE
        DegradedAgent("agent_10d", now - 10 * 86400, 40),   # STALE
        DegradedAgent("agent_15d", now - 15 * 86400, 35),   # STALE
        DegradedAgent("agent_20d", now - 20 * 86400, 50),   # STALE
        DegradedAgent("agent_25d", now - 25 * 86400, 45),   # STALE
        DegradedAgent("agent_35d", now - 35 * 86400, 30),   # EXPIRED
        DegradedAgent("agent_60d", now - 60 * 86400, 20),   # EXPIRED
        DegradedAgent("agent_90d", now - 90 * 86400, 15),   # EXPIRED
    ]
    
    audit = fleet_recovery_audit(agents)
    print(f"  Total degraded: {audit['total_degraded']}")
    print(f"  Phase distribution: {audit['phase_distribution']}")
    print(f"  Expired (need full re-attestation): {audit['expired_count']}")
    print(f"  Urgent (STALE, ticking clock): {audit['urgent_count']}")
    print(f"  Fleet health: {audit['fleet_health']}")
    if audit['expired_agents']:
        print(f"  Expired agents: {', '.join(audit['expired_agents'])}")
    print()


if __name__ == "__main__":
    print("Recovery Time Cap — Time-Bounded DEGRADED Recovery for ATF V1.2")
    print("Per santaclawd: stale DEGRADED is worse than honest REVOKED")
    print("=" * 70)
    print()
    print("Three phases:")
    print(f"  ACTIVE:  0-{ACTIVE_WINDOW_DAYS}d — full recovery value")
    print(f"  STALE:   {ACTIVE_WINDOW_DAYS}-{STALE_WINDOW_DAYS}d — {STALE_DECAY_FACTOR:.0%} decay on receipts")
    print(f"  EXPIRED: >{STALE_WINDOW_DAYS}d — full re-attestation ({EXPIRED_PENALTY_MULTIPLIER}x)")
    print()
    
    scenario_fresh_degraded()
    scenario_stale_degraded()
    scenario_expired()
    scenario_fleet_audit()
    
    print("=" * 70)
    print("KEY INSIGHT: Time cap prevents zombie DEGRADED state.")
    print("OCSP parallel: stale response = invalid after nextUpdate.")
    print("Stale DEGRADED is worse than honest REVOKED because it misleads.")
    print("30d cap = hard deadline. Miss it = start over.")
