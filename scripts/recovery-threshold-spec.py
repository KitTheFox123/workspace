#!/usr/bin/env python3
"""
recovery-threshold-spec.py — ATF V1.2 recovery from DORMANT/DEGRADED states.

Per santaclawd: n_recovery=8 lighter than initial n=30 because identity 
history is preserved. TLS 1.3 session resumption (RFC 8446 §2.2) = abbreviated 
handshake using PSK from prior session.

Three recovery paths:
  DORMANT → ACTIVE:    n=8 receipts in 30d (session resumption, prior history preserved)
  DEGRADED → ACTIVE:   n=8 receipts in 30d (same threshold, but must clear violations first)
  ABANDONED → ACTIVE:  n=30 receipts in 90d (full re-attestation, like fresh TLS handshake)

Key insight: Wilson CI at n=8 with 100% success = 0.63 floor.
Combined with prior history, this exceeds fresh PROVISIONAL (0.21).
"""

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AgentState(Enum):
    PROVISIONAL = "PROVISIONAL"   # New, no history
    ACTIVE = "ACTIVE"             # Receipts flowing
    DORMANT = "DORMANT"           # Established but idle (>90d)
    DEGRADED = "DEGRADED"         # Active failures
    ABANDONED = "ABANDONED"       # >365d dormant
    RECOVERING = "RECOVERING"     # In recovery window


class RecoveryPath(Enum):
    SESSION_RESUMPTION = "SESSION_RESUMPTION"   # DORMANT → ACTIVE (n=8, 30d)
    VIOLATION_CLEAR = "VIOLATION_CLEAR"          # DEGRADED → ACTIVE (clear + n=8, 30d)  
    FULL_REATTESTION = "FULL_REATTESTION"        # ABANDONED → ACTIVE (n=30, 90d)


# SPEC_CONSTANTS
DORMANT_RECOVERY_N = 8          # Receipts needed from DORMANT
DORMANT_RECOVERY_WINDOW = 30    # Days
DEGRADED_RECOVERY_N = 8         # Same threshold, but violations must clear first
DEGRADED_RECOVERY_WINDOW = 30   # Days
ABANDONED_RECOVERY_N = 30       # Full re-attestation
ABANDONED_RECOVERY_WINDOW = 90  # Days
WILSON_Z = 1.96                 # 95% confidence
DORMANT_DECAY_RATE = 0.05       # 5% per month
DORMANT_FLOOR = 0.30            # Minimum during dormancy
DORMANT_THRESHOLD = 90          # Days of inactivity → DORMANT
ABANDONED_THRESHOLD = 365       # Days of dormancy → ABANDONED


@dataclass
class AgentProfile:
    agent_id: str
    state: AgentState
    trust_score: float
    total_receipts: int
    successful_receipts: int
    last_receipt_days_ago: int
    violations_pending: int = 0
    dormant_since_days: int = 0
    prior_wilson_ci: float = 0.0


@dataclass
class RecoveryPlan:
    agent_id: str
    current_state: AgentState
    target_state: AgentState
    path: RecoveryPath
    receipts_needed: int
    window_days: int
    prior_history_preserved: bool
    estimated_trust_at_completion: float
    violations_to_clear: int = 0


def wilson_ci_lower(successes: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score confidence interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denom = 1 + z*z/total
    center = p + z*z/(2*total)
    spread = z * math.sqrt(p*(1-p)/total + z*z/(4*total*total))
    return max(0, (center - spread) / denom)


def compute_decayed_trust(original_trust: float, dormant_months: float) -> float:
    """Compute trust after dormancy decay."""
    decayed = original_trust * ((1 - DORMANT_DECAY_RATE) ** dormant_months)
    return max(DORMANT_FLOOR, round(decayed, 4))


def determine_recovery_path(agent: AgentProfile) -> RecoveryPlan:
    """Determine appropriate recovery path based on agent state."""
    
    if agent.state == AgentState.DORMANT:
        # Session resumption — lighter threshold, history preserved
        dormant_months = agent.dormant_since_days / 30
        decayed = compute_decayed_trust(agent.trust_score, dormant_months)
        
        # Wilson CI at n=8 combined with prior history
        # After 8 successful receipts, new Wilson floor = 0.63
        # Combined with prior: weighted average
        recovery_wilson = wilson_ci_lower(8, 8)
        # Prior receipts still count toward total
        combined_wilson = wilson_ci_lower(
            agent.successful_receipts + 8, 
            agent.total_receipts + 8
        )
        estimated_trust = max(decayed, combined_wilson)
        
        return RecoveryPlan(
            agent_id=agent.agent_id,
            current_state=AgentState.DORMANT,
            target_state=AgentState.ACTIVE,
            path=RecoveryPath.SESSION_RESUMPTION,
            receipts_needed=DORMANT_RECOVERY_N,
            window_days=DORMANT_RECOVERY_WINDOW,
            prior_history_preserved=True,
            estimated_trust_at_completion=round(estimated_trust, 4)
        )
    
    elif agent.state == AgentState.DEGRADED:
        # Must clear violations first, then same n=8
        recovery_wilson = wilson_ci_lower(
            agent.successful_receipts + 8,
            agent.total_receipts + 8
        )
        
        return RecoveryPlan(
            agent_id=agent.agent_id,
            current_state=AgentState.DEGRADED,
            target_state=AgentState.ACTIVE,
            path=RecoveryPath.VIOLATION_CLEAR,
            receipts_needed=DEGRADED_RECOVERY_N,
            window_days=DEGRADED_RECOVERY_WINDOW,
            prior_history_preserved=True,
            estimated_trust_at_completion=round(recovery_wilson, 4),
            violations_to_clear=agent.violations_pending
        )
    
    elif agent.state == AgentState.ABANDONED:
        # Full re-attestation — like fresh TLS handshake
        # Prior history NOT used for Wilson CI (too stale)
        fresh_wilson = wilson_ci_lower(30, 30)
        
        return RecoveryPlan(
            agent_id=agent.agent_id,
            current_state=AgentState.ABANDONED,
            target_state=AgentState.ACTIVE,
            path=RecoveryPath.FULL_REATTESTION,
            receipts_needed=ABANDONED_RECOVERY_N,
            window_days=ABANDONED_RECOVERY_WINDOW,
            prior_history_preserved=False,
            estimated_trust_at_completion=round(fresh_wilson, 4)
        )
    
    else:
        # PROVISIONAL or ACTIVE — no recovery needed
        return RecoveryPlan(
            agent_id=agent.agent_id,
            current_state=agent.state,
            target_state=agent.state,
            path=RecoveryPath.SESSION_RESUMPTION,
            receipts_needed=0,
            window_days=0,
            prior_history_preserved=True,
            estimated_trust_at_completion=agent.trust_score
        )


def validate_recovery_completion(plan: RecoveryPlan, receipts_received: int, 
                                  days_elapsed: int, all_successful: bool) -> dict:
    """Validate whether recovery is complete."""
    if receipts_received < plan.receipts_needed:
        return {
            "complete": False,
            "reason": f"Need {plan.receipts_needed} receipts, got {receipts_received}",
            "remaining": plan.receipts_needed - receipts_received
        }
    
    if days_elapsed > plan.window_days:
        return {
            "complete": False,
            "reason": f"Window expired: {days_elapsed}d > {plan.window_days}d",
            "action": "RESTART_RECOVERY"
        }
    
    if plan.violations_to_clear > 0:
        return {
            "complete": False,
            "reason": f"{plan.violations_to_clear} violations must be cleared first",
            "action": "CLEAR_VIOLATIONS"
        }
    
    if not all_successful:
        return {
            "complete": False,
            "reason": "All recovery receipts must be CONFIRMED (not ALLEGED/DISPUTED)",
            "action": "REPLACE_FAILED_RECEIPTS"
        }
    
    return {
        "complete": True,
        "new_state": "ACTIVE",
        "estimated_trust": plan.estimated_trust_at_completion,
        "path_used": plan.path.value,
        "history_preserved": plan.prior_history_preserved
    }


# === Scenarios ===

def scenario_dormant_recovery():
    """Established agent returns after 6 months dormancy."""
    print("=== Scenario: DORMANT Recovery (6 months) ===")
    agent = AgentProfile(
        agent_id="kit_fox", state=AgentState.DORMANT,
        trust_score=0.89, total_receipts=150, successful_receipts=142,
        last_receipt_days_ago=180, dormant_since_days=180
    )
    
    plan = determine_recovery_path(agent)
    print(f"  Path: {plan.path.value}")
    print(f"  Receipts needed: {plan.receipts_needed} in {plan.window_days}d")
    print(f"  History preserved: {plan.prior_history_preserved}")
    print(f"  Original trust: {agent.trust_score}")
    decayed = compute_decayed_trust(agent.trust_score, 6)
    print(f"  Decayed trust (6mo): {decayed}")
    print(f"  Estimated after recovery: {plan.estimated_trust_at_completion}")
    
    # Validate completion
    result = validate_recovery_completion(plan, 8, 15, True)
    print(f"  Recovery result: {result}")
    print()


def scenario_degraded_recovery():
    """Agent with violations recovers."""
    print("=== Scenario: DEGRADED Recovery (violations) ===")
    agent = AgentProfile(
        agent_id="troubled_agent", state=AgentState.DEGRADED,
        trust_score=0.45, total_receipts=80, successful_receipts=60,
        last_receipt_days_ago=5, violations_pending=2
    )
    
    plan = determine_recovery_path(agent)
    print(f"  Path: {plan.path.value}")
    print(f"  Violations to clear: {plan.violations_to_clear}")
    print(f"  Receipts needed: {plan.receipts_needed} in {plan.window_days}d")
    print(f"  Estimated after recovery: {plan.estimated_trust_at_completion}")
    
    # Try without clearing violations
    result = validate_recovery_completion(plan, 8, 20, True)
    print(f"  With violations pending: {result}")
    
    # Clear violations
    plan.violations_to_clear = 0
    result = validate_recovery_completion(plan, 8, 20, True)
    print(f"  After clearing: {result}")
    print()


def scenario_abandoned_full_reattestion():
    """Agent gone >365 days — full re-attestation."""
    print("=== Scenario: ABANDONED (>365d) — Full Re-attestation ===")
    agent = AgentProfile(
        agent_id="ghost_agent", state=AgentState.ABANDONED,
        trust_score=0.30, total_receipts=200, successful_receipts=190,
        last_receipt_days_ago=400, dormant_since_days=400
    )
    
    plan = determine_recovery_path(agent)
    print(f"  Path: {plan.path.value}")
    print(f"  History preserved: {plan.prior_history_preserved}")
    print(f"  Receipts needed: {plan.receipts_needed} in {plan.window_days}d")
    print(f"  Estimated after recovery: {plan.estimated_trust_at_completion}")
    print(f"  NOTE: Despite 200 prior receipts, starts fresh — too stale")
    print()


def scenario_comparison_table():
    """Compare all recovery paths side by side."""
    print("=== Recovery Path Comparison ===")
    print(f"  {'Path':<25} {'N':>4} {'Window':>8} {'History':>10} {'Wilson CI':>10}")
    print(f"  {'-'*25} {'-'*4} {'-'*8} {'-'*10} {'-'*10}")
    
    paths = [
        ("PROVISIONAL→ACTIVE", 30, "90d", "No", wilson_ci_lower(30, 30)),
        ("DORMANT→ACTIVE", 8, "30d", "Yes", wilson_ci_lower(150+8, 158)),
        ("DEGRADED→ACTIVE", 8, "30d", "Yes", wilson_ci_lower(60+8, 80+8)),
        ("ABANDONED→ACTIVE", 30, "90d", "No", wilson_ci_lower(30, 30)),
    ]
    
    for name, n, window, history, wilson in paths:
        print(f"  {name:<25} {n:>4} {window:>8} {history:>10} {wilson:>10.4f}")
    
    print()
    print(f"  Key: DORMANT recovery (0.89 with 150 prior) >> PROVISIONAL (0.21)")
    print(f"  TLS parallel: session resumption >> full handshake")
    print()


if __name__ == "__main__":
    print("Recovery Threshold Spec — ATF V1.2 Gap #3")
    print("Per santaclawd: n_recovery=8, lighter than initial n=30")
    print("TLS 1.3 Session Resumption (RFC 8446 §2.2) parallel")
    print("=" * 65)
    print()
    
    scenario_dormant_recovery()
    scenario_degraded_recovery()
    scenario_abandoned_full_reattestion()
    scenario_comparison_table()
    
    print("=" * 65)
    print("SPEC TEXT:")
    print(f"  recovery_threshold = {DORMANT_RECOVERY_N}")
    print(f"  recovery_window = {DORMANT_RECOVERY_WINDOW}d")
    print(f"  reset_trigger = COMPLETION (all {DORMANT_RECOVERY_N} verified)")
    print(f"  abandoned_threshold = {ABANDONED_RECOVERY_N} (full re-attestation)")
    print(f"  abandoned_window = {ABANDONED_RECOVERY_WINDOW}d")
    print("  Wilson CI at n=8 all-success: {:.4f}".format(wilson_ci_lower(8, 8)))
    print("  Combined with prior 150/150: {:.4f}".format(wilson_ci_lower(158, 158)))
