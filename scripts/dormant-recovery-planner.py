#!/usr/bin/env python3
"""
dormant-recovery-planner.py — ATF V1.2 DORMANT state recovery planning.

Per santaclawd: n_recovery=8 (not 30) because identity history is preserved.
Per funwolf: ship DORMANT first — idle≠bad gap is blocking discovery.
Per RFC 5280 §5.3.1: certificateHold (reason code 6) = reversible suspension.

Key insight: cold start and recovery are DIFFERENT problems.
- Cold start: no history, Wilson CI from zero, n=30 for GRADUATED
- Recovery: history preserved, decayed trust, n=8 COMPLETION for restoration

Decay model: 5%/month exponential. T(m) = T₀ × 0.95^m
Auto-REVOKED below 0.10 (floor). Recovery window: 14 days from first COMPLETION.
"""

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentState(Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"           # certificateHold equivalent
    RECOVERING = "RECOVERING"      # n_recovery in progress
    GRADUATED = "GRADUATED"        # Restored to active trust
    REVOKED = "REVOKED"           # Auto-revoked below floor


# SPEC_CONSTANTS (ATF V1.2)
DECAY_RATE = 0.05                  # 5% per month
DECAY_FLOOR = 0.10                 # Auto-REVOKED below this
DORMANT_THRESHOLD_DAYS = 90        # Idle > 90 days = DORMANT
N_RECOVERY = 8                     # COMPLETION receipts for recovery
N_COLD_START = 30                  # Wilson CI n for fresh start
RECOVERY_WINDOW_DAYS = 14          # Window to complete n_recovery
DISCOVERY_MODES = ["DANE", "SVCB", "CT_FALLBACK", "NONE"]
DISCOVERY_PENALTIES = {"DANE": 0, "SVCB": -1, "CT_FALLBACK": -2, "NONE": -3}


@dataclass
class TrustSnapshot:
    trust_score: float
    receipts_total: int
    last_active: float
    evidence_grade: str


@dataclass
class RecoveryPlan:
    agent_id: str
    pre_dormant: TrustSnapshot
    dormant_months: float
    decayed_trust: float
    recovery_target: float
    n_recovery_needed: int
    recovery_window_days: int
    wilson_ci_at_recovery: float
    discovery_mode: str
    state: AgentState


def compute_decay(initial_trust: float, months: float) -> float:
    """Exponential decay: T(m) = T₀ × (1 - rate)^m"""
    decayed = initial_trust * ((1 - DECAY_RATE) ** months)
    return max(DECAY_FLOOR, round(decayed, 4))


def wilson_ci_lower(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    lower = (centre - spread) / denominator
    return round(max(0, lower), 4)


def plan_recovery(agent_id: str, pre_dormant: TrustSnapshot, 
                  dormant_months: float, discovery_mode: str = "DANE") -> RecoveryPlan:
    """Create a recovery plan for a dormant agent."""
    
    decayed = compute_decay(pre_dormant.trust_score, dormant_months)
    
    # Check if auto-revoked
    if decayed <= DECAY_FLOOR:
        return RecoveryPlan(
            agent_id=agent_id,
            pre_dormant=pre_dormant,
            dormant_months=dormant_months,
            decayed_trust=decayed,
            recovery_target=0.0,
            n_recovery_needed=0,
            recovery_window_days=0,
            wilson_ci_at_recovery=0.0,
            discovery_mode=discovery_mode,
            state=AgentState.REVOKED
        )
    
    # Wilson CI at n_recovery with decayed trust as prior
    # Assume all recovery receipts are COMPLETION (success)
    wilson_ceiling = wilson_ci_lower(N_RECOVERY, N_RECOVERY)
    
    # Recovery target: MIN(decayed + wilson_bonus, pre_dormant)
    # Wilson bonus = difference between decayed and Wilson CI at full success
    recovery_target = min(
        decayed + (wilson_ceiling - decayed) * 0.5,  # Partial restoration
        pre_dormant.trust_score * 0.95  # Never fully restore without sustained activity
    )
    
    # Discovery mode penalty
    penalty = DISCOVERY_PENALTIES.get(discovery_mode, -3)
    grade_adjusted = max(0, recovery_target + penalty * 0.05)
    
    return RecoveryPlan(
        agent_id=agent_id,
        pre_dormant=pre_dormant,
        dormant_months=dormant_months,
        decayed_trust=decayed,
        recovery_target=round(grade_adjusted, 4),
        n_recovery_needed=N_RECOVERY,
        recovery_window_days=RECOVERY_WINDOW_DAYS,
        wilson_ci_at_recovery=wilson_ceiling,
        discovery_mode=discovery_mode,
        state=AgentState.RECOVERING
    )


def months_to_revocation(initial_trust: float) -> float:
    """Calculate months until auto-revocation."""
    if initial_trust <= DECAY_FLOOR:
        return 0.0
    months = math.log(DECAY_FLOOR / initial_trust) / math.log(1 - DECAY_RATE)
    return round(months, 1)


def compare_cold_vs_recovery(dormant_months: float) -> dict:
    """Compare cold start vs dormant recovery for same agent."""
    pre_dormant = TrustSnapshot(0.85, 100, time.time() - dormant_months * 30 * 86400, "A")
    
    decayed = compute_decay(pre_dormant.trust_score, dormant_months)
    
    # Cold start: Wilson CI at n=30, all success
    cold_wilson = wilson_ci_lower(N_COLD_START, N_COLD_START)
    
    # Recovery: Wilson CI at n=8, all success, with decayed prior
    recovery_wilson = wilson_ci_lower(N_RECOVERY, N_RECOVERY)
    
    # Time to equivalent trust
    cold_start_receipts = N_COLD_START
    recovery_receipts = N_RECOVERY
    
    return {
        "dormant_months": dormant_months,
        "pre_dormant_trust": pre_dormant.trust_score,
        "decayed_trust": decayed,
        "cold_start": {
            "receipts_needed": cold_start_receipts,
            "wilson_ceiling": cold_wilson,
            "time_estimate_days": cold_start_receipts * 2,  # ~2 days per receipt
        },
        "recovery": {
            "receipts_needed": recovery_receipts,
            "wilson_ceiling": recovery_wilson,
            "recovery_target": min(decayed + 0.15, pre_dormant.trust_score * 0.95),
            "time_estimate_days": min(RECOVERY_WINDOW_DAYS, recovery_receipts * 2),
        },
        "savings": {
            "receipts_saved": cold_start_receipts - recovery_receipts,
            "days_saved": (cold_start_receipts - recovery_receipts) * 2,
            "history_preserved": True
        }
    }


# === Scenarios ===

def scenario_short_dormancy():
    """3-month dormancy — easy recovery."""
    print("=== Scenario: Short Dormancy (3 months) ===")
    pre = TrustSnapshot(0.85, 100, time.time() - 90*86400, "A")
    plan = plan_recovery("kit_fox", pre, 3.0)
    
    print(f"  Pre-dormant trust: {pre.trust_score}")
    print(f"  Decayed (3mo): {plan.decayed_trust}")
    print(f"  Recovery target: {plan.recovery_target}")
    print(f"  Receipts needed: {plan.n_recovery_needed}")
    print(f"  Window: {plan.recovery_window_days} days")
    print(f"  State: {plan.state.value}")
    print(f"  Months to auto-revocation: {months_to_revocation(pre.trust_score)}")
    print()


def scenario_long_dormancy():
    """18-month dormancy — significant decay."""
    print("=== Scenario: Long Dormancy (18 months) ===")
    pre = TrustSnapshot(0.75, 80, time.time() - 540*86400, "B")
    plan = plan_recovery("long_idle", pre, 18.0)
    
    print(f"  Pre-dormant trust: {pre.trust_score}")
    print(f"  Decayed (18mo): {plan.decayed_trust}")
    print(f"  Recovery target: {plan.recovery_target}")
    print(f"  State: {plan.state.value}")
    print(f"  Months to auto-revocation: {months_to_revocation(pre.trust_score)}")
    print()


def scenario_auto_revocation():
    """36-month dormancy — auto-revoked."""
    print("=== Scenario: Auto-Revocation (36 months) ===")
    pre = TrustSnapshot(0.60, 50, time.time() - 1080*86400, "B")
    plan = plan_recovery("ghost", pre, 36.0)
    
    print(f"  Pre-dormant trust: {pre.trust_score}")
    print(f"  Decayed (36mo): {plan.decayed_trust}")
    print(f"  State: {plan.state.value}")
    print(f"  Months to auto-revocation: {months_to_revocation(pre.trust_score)}")
    print()


def scenario_cold_vs_recovery():
    """Compare cold start vs recovery at various dormancy lengths."""
    print("=== Scenario: Cold Start vs Recovery Comparison ===")
    for months in [1, 3, 6, 12, 24]:
        comp = compare_cold_vs_recovery(months)
        print(f"  {months}mo dormancy:")
        print(f"    Decayed: {comp['decayed_trust']:.3f}")
        print(f"    Cold start: {comp['cold_start']['receipts_needed']} receipts, "
              f"~{comp['cold_start']['time_estimate_days']}d")
        print(f"    Recovery:   {comp['recovery']['receipts_needed']} receipts, "
              f"~{comp['recovery']['time_estimate_days']}d, "
              f"target={comp['recovery']['recovery_target']:.3f}")
        print(f"    Savings: {comp['savings']['receipts_saved']} receipts, "
              f"~{comp['savings']['days_saved']}d faster")
    print()


def scenario_discovery_modes():
    """Recovery across different discovery modes."""
    print("=== Scenario: Discovery Mode Impact on Recovery ===")
    pre = TrustSnapshot(0.80, 90, time.time() - 180*86400, "A")
    
    for mode in DISCOVERY_MODES:
        plan = plan_recovery("mode_test", pre, 6.0, mode)
        penalty = DISCOVERY_PENALTIES[mode]
        print(f"  {mode:15s}: decayed={plan.decayed_trust:.3f}, "
              f"recovery_target={plan.recovery_target:.3f}, "
              f"penalty={penalty}")
    print()


if __name__ == "__main__":
    print("Dormant Recovery Planner — ATF V1.2")
    print("Per santaclawd + funwolf + RFC 5280 §5.3.1 certificateHold")
    print("=" * 70)
    print()
    print(f"Cold start: n={N_COLD_START} receipts (no history)")
    print(f"Recovery:   n={N_RECOVERY} receipts (history preserved)")
    print(f"Decay: {DECAY_RATE*100}%/month, floor={DECAY_FLOOR}, auto-REVOKED below floor")
    print(f"Recovery window: {RECOVERY_WINDOW_DAYS} days")
    print()
    
    scenario_short_dormancy()
    scenario_long_dormancy()
    scenario_auto_revocation()
    scenario_cold_vs_recovery()
    scenario_discovery_modes()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Cold start ≠ recovery. Different problems, different thresholds.")
    print("2. n=8 recovery vs n=30 cold start = 22 fewer receipts, ~44 days faster.")
    print("3. Identity history is preserved during DORMANT — certificateHold, not revoke.")
    print("4. 5%/month decay: 0.85 trust → auto-REVOKED in ~40 months.")
    print("5. Discovery mode affects recovery ceiling — DANE best, NONE worst.")
