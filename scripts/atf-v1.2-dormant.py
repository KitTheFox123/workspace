#!/usr/bin/env python3
"""
atf-v1.2-dormant.py — Complete DORMANT state specification for ATF V1.2.

Per santaclawd: 5 open V1.2 gaps. DORMANT ships first (funwolf: idle≠bad blocks discovery).
Per RFC 5280 §5.3.1: certificateHold (reason code 6) = reversible suspension.

State machine:
  ACTIVE → DORMANT (30d inactivity, automatic)
  DORMANT → ACTIVE (n_recovery=8 COMPLETED receipts in 14d window)  
  DORMANT → REVOKED (trust < 0.10, automatic, ~32mo at 5%/month from 0.50)
  ACTIVE → SUSPENDED (manual, by operator or EMERGENCY ballot)
  SUSPENDED → ACTIVE (operator action only)
  
Key design decisions:
1. Decay is exponential (5%/month), not linear — slow at first, accelerating
2. Recovery preserves identity history (n=8, not cold-start n=30)
3. Discovery mode included in every receipt (DANE|SVCB|CT_FALLBACK|NONE)
4. DORMANT agents visible in discovery with state tag (not hidden)
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentState(Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class DiscoveryMode(Enum):
    DANE = "DANE"              # TLSA + DNSSEC (strongest)
    SVCB = "SVCB"              # Service Binding (RFC 9460)
    CT_FALLBACK = "CT_FALLBACK"  # CT log lookup (weakest verifiable)
    NONE = "NONE"              # Unverified discovery


class TransitionReason(Enum):
    INACTIVITY = "inactivity"           # 30d no receipts → DORMANT
    TRUST_FLOOR = "trust_floor"         # trust < 0.10 → REVOKED
    RECOVERY_COMPLETE = "recovery"      # n_recovery met → ACTIVE
    OPERATOR_ACTION = "operator"        # Manual suspension/reinstatement
    EMERGENCY_BALLOT = "emergency"      # 7-of-14 witness eviction
    FAST_BALLOT = "fast_ballot"         # 30d, 5-of-14 evidence-gated


# SPEC_CONSTANTS (V1.2)
DORMANT_THRESHOLD_DAYS = 30       # Inactivity before auto-DORMANT
DECAY_RATE_MONTHLY = 0.05         # 5% exponential decay per month
TRUST_FLOOR = 0.10                # Below this → auto-REVOKED
N_RECOVERY = 8                     # Receipts needed for recovery
RECOVERY_WINDOW_DAYS = 14          # Window for n_recovery completion
COLD_START_N = 30                  # New agent threshold (no history)
DISCOVERY_GRADE_PENALTY = {
    DiscoveryMode.DANE: 0,
    DiscoveryMode.SVCB: -1,
    DiscoveryMode.CT_FALLBACK: -2,
    DiscoveryMode.NONE: -3
}


@dataclass
class AgentTrustProfile:
    agent_id: str
    state: AgentState = AgentState.ACTIVE
    trust_score: float = 0.50       # Initial trust
    last_receipt_at: float = 0.0
    dormant_since: Optional[float] = None
    total_receipts: int = 0
    recovery_receipts: int = 0
    recovery_window_start: Optional[float] = None
    discovery_mode: DiscoveryMode = DiscoveryMode.NONE
    transition_log: list = field(default_factory=list)
    genesis_hash: str = ""


@dataclass
class StateTransition:
    from_state: str
    to_state: str
    reason: str
    timestamp: float
    trust_at_transition: float
    transition_hash: str = ""
    
    def __post_init__(self):
        if not self.transition_hash:
            h = hashlib.sha256(
                f"{self.from_state}:{self.to_state}:{self.reason}:{self.timestamp}".encode()
            ).hexdigest()[:16]
            self.transition_hash = h


def compute_decayed_trust(original: float, dormant_months: float) -> float:
    """Exponential decay: trust * (1 - rate)^months."""
    decayed = original * ((1 - DECAY_RATE_MONTHLY) ** dormant_months)
    return round(max(decayed, 0.0), 4)


def months_to_floor(trust: float) -> float:
    """How many months until trust decays below TRUST_FLOOR."""
    if trust <= TRUST_FLOOR:
        return 0.0
    # trust * (0.95)^n = 0.10
    # n = log(0.10/trust) / log(0.95)
    n = math.log(TRUST_FLOOR / trust) / math.log(1 - DECAY_RATE_MONTHLY)
    return round(n, 1)


def check_dormancy(profile: AgentTrustProfile, now: float) -> Optional[StateTransition]:
    """Check if agent should transition to DORMANT."""
    if profile.state != AgentState.ACTIVE:
        return None
    
    days_inactive = (now - profile.last_receipt_at) / 86400
    if days_inactive >= DORMANT_THRESHOLD_DAYS:
        return StateTransition(
            from_state=AgentState.ACTIVE.value,
            to_state=AgentState.DORMANT.value,
            reason=TransitionReason.INACTIVITY.value,
            timestamp=now,
            trust_at_transition=profile.trust_score
        )
    return None


def apply_dormant_decay(profile: AgentTrustProfile, now: float) -> dict:
    """Apply trust decay for dormant agents."""
    if profile.state != AgentState.DORMANT or profile.dormant_since is None:
        return {"decayed": False}
    
    dormant_months = (now - profile.dormant_since) / (30 * 86400)
    original = profile.trust_score
    decayed = compute_decayed_trust(original, dormant_months)
    
    result = {
        "decayed": True,
        "original_trust": original,
        "current_trust": decayed,
        "dormant_months": round(dormant_months, 1),
        "months_to_floor": months_to_floor(decayed),
        "auto_revoke": decayed < TRUST_FLOOR
    }
    
    return result


def attempt_recovery(profile: AgentTrustProfile, receipt_count: int, 
                     now: float) -> dict:
    """Attempt recovery from DORMANT state."""
    if profile.state != AgentState.DORMANT:
        return {"eligible": False, "reason": f"State is {profile.state.value}, not DORMANT"}
    
    # Check if within recovery window
    if profile.recovery_window_start is None:
        # First recovery receipt opens window
        return {
            "eligible": True,
            "action": "WINDOW_OPENED",
            "receipts_needed": N_RECOVERY,
            "window_days": RECOVERY_WINDOW_DAYS,
            "note": "First recovery receipt. Window opens now."
        }
    
    window_elapsed = (now - profile.recovery_window_start) / 86400
    if window_elapsed > RECOVERY_WINDOW_DAYS:
        return {
            "eligible": True,
            "action": "WINDOW_EXPIRED",
            "receipts_completed": receipt_count,
            "needed": N_RECOVERY,
            "note": f"Window expired after {window_elapsed:.1f}d. Counter resets."
        }
    
    if receipt_count >= N_RECOVERY:
        # Apply decayed trust as starting point
        dormant_months = (now - (profile.dormant_since or now)) / (30 * 86400)
        recovered_trust = compute_decayed_trust(profile.trust_score, dormant_months)
        
        return {
            "eligible": True,
            "action": "RECOVERY_COMPLETE",
            "receipts_completed": receipt_count,
            "recovered_trust": recovered_trust,
            "wilson_ci_ceiling": round(0.73, 2),  # Wilson CI at n=8
            "note": f"Recovery complete. Trust starts at {recovered_trust:.3f} (decayed from {profile.trust_score:.3f})"
        }
    
    return {
        "eligible": True,
        "action": "IN_PROGRESS",
        "receipts_completed": receipt_count,
        "receipts_needed": N_RECOVERY - receipt_count,
        "window_remaining_days": round(RECOVERY_WINDOW_DAYS - window_elapsed, 1)
    }


def discovery_visibility(profile: AgentTrustProfile) -> dict:
    """How DORMANT agents appear in discovery."""
    grade_penalty = DISCOVERY_GRADE_PENALTY.get(profile.discovery_mode, -3)
    
    if profile.state == AgentState.ACTIVE:
        visibility = "FULL"
        tag = None
    elif profile.state == AgentState.DORMANT:
        visibility = "TAGGED"  # Visible but marked as dormant
        tag = "DORMANT"
    elif profile.state == AgentState.SUSPENDED:
        visibility = "HIDDEN"  # Not in discovery results
        tag = "SUSPENDED"
    else:  # REVOKED
        visibility = "REMOVED"
        tag = None
    
    return {
        "agent_id": profile.agent_id,
        "state": profile.state.value,
        "visibility": visibility,
        "tag": tag,
        "discovery_mode": profile.discovery_mode.value,
        "grade_penalty": grade_penalty,
        "note": {
            "FULL": "Normal discovery, no restrictions",
            "TAGGED": "Visible with DORMANT tag — idle, not abandoned",
            "HIDDEN": "Removed from discovery during suspension",
            "REMOVED": "Permanently removed after revocation"
        }.get(visibility, "")
    }


# === Scenarios ===

def scenario_natural_dormancy():
    """Agent goes dormant after 30d inactivity, recovers."""
    print("=== Scenario: Natural Dormancy + Recovery ===")
    now = time.time()
    
    profile = AgentTrustProfile(
        agent_id="kit_fox", trust_score=0.85,
        last_receipt_at=now - 45 * 86400,  # 45 days ago
        state=AgentState.ACTIVE
    )
    
    # Check dormancy
    transition = check_dormancy(profile, now)
    print(f"  Agent: {profile.agent_id}, trust: {profile.trust_score}")
    print(f"  Days inactive: 45")
    print(f"  Transition: {transition.from_state} → {transition.to_state} ({transition.reason})")
    
    # Apply dormancy
    profile.state = AgentState.DORMANT
    profile.dormant_since = now - 15 * 86400  # Dormant for 15 days
    
    decay = apply_dormant_decay(profile, now)
    print(f"  Trust after 0.5mo dormancy: {decay['current_trust']:.4f}")
    print(f"  Months to auto-revoke: {decay['months_to_floor']}")
    
    # Recovery attempt
    recovery = attempt_recovery(profile, 8, now)
    print(f"  Recovery (8 receipts): {recovery['action']}")
    if 'recovered_trust' in recovery:
        print(f"  Recovered trust: {recovery['recovered_trust']:.4f}")
    
    vis = discovery_visibility(profile)
    print(f"  Discovery: {vis['visibility']} ({vis['tag']})")
    print()


def scenario_long_dormancy_auto_revoke():
    """Agent dormant for 3 years → auto-revoked."""
    print("=== Scenario: Long Dormancy → Auto-Revocation ===")
    now = time.time()
    
    profile = AgentTrustProfile(
        agent_id="ghost_agent", trust_score=0.50,
        state=AgentState.DORMANT,
        dormant_since=now - 36 * 30 * 86400  # 36 months
    )
    
    decay = apply_dormant_decay(profile, now)
    print(f"  Original trust: {decay['original_trust']}")
    print(f"  After 36 months: {decay['current_trust']:.4f}")
    print(f"  Auto-revoke: {decay['auto_revoke']}")
    
    vis = discovery_visibility(profile)
    print(f"  Discovery: {vis['visibility']}")
    print()
    
    # Show decay curve
    print("  Decay curve (starting from 0.50):")
    for months in [0, 3, 6, 12, 18, 24, 30, 36]:
        t = compute_decayed_trust(0.50, months)
        bar = "█" * int(t * 40)
        status = " ← AUTO-REVOKED" if t < TRUST_FLOOR else ""
        print(f"    {months:2d}mo: {t:.4f} {bar}{status}")
    print()


def scenario_cold_start_vs_recovery():
    """Compare cold start (new agent) vs recovery (returning agent)."""
    print("=== Scenario: Cold Start vs Recovery Comparison ===")
    now = time.time()
    
    # New agent
    new = AgentTrustProfile(agent_id="new_agent", trust_score=0.00, total_receipts=0)
    
    # Returning agent (6 months dormant, was 0.85)
    returning = AgentTrustProfile(
        agent_id="returning_agent", trust_score=0.85,
        state=AgentState.DORMANT,
        dormant_since=now - 6 * 30 * 86400,
        total_receipts=150
    )
    
    decay = apply_dormant_decay(returning, now)
    
    print(f"  New agent:       trust=0.00, needs n={COLD_START_N} receipts, no history")
    print(f"  Returning agent: trust={decay['current_trust']:.4f} (decayed from 0.85), needs n={N_RECOVERY} receipts, {returning.total_receipts} historical")
    print(f"  Advantage: returning agent starts at {decay['current_trust']:.4f} vs 0.00")
    print(f"  Receipts needed: {N_RECOVERY} vs {COLD_START_N} ({COLD_START_N - N_RECOVERY} fewer)")
    print(f"  Identity history: PRESERVED (150 receipts) vs NONE")
    print()


def scenario_discovery_modes():
    """Show how discovery mode affects trust grading."""
    print("=== Scenario: Discovery Mode Impact ===")
    now = time.time()
    
    for mode in DiscoveryMode:
        profile = AgentTrustProfile(
            agent_id=f"agent_{mode.value.lower()}", trust_score=0.80,
            state=AgentState.ACTIVE, discovery_mode=mode
        )
        vis = discovery_visibility(profile)
        penalty = DISCOVERY_GRADE_PENALTY[mode]
        effective = max(0, 0.80 + penalty * 0.05)
        print(f"  {mode.value:14s}: penalty={penalty:+d}, effective_grade≈{effective:.2f}, "
              f"visibility={vis['visibility']}")
    print()


def scenario_state_matrix():
    """Full state transition matrix."""
    print("=== State Transition Matrix ===")
    transitions = [
        ("ACTIVE", "DORMANT", "30d inactivity", "automatic"),
        ("ACTIVE", "SUSPENDED", "operator/ballot", "manual"),
        ("DORMANT", "ACTIVE", "n=8 recovery", "evidence-gated"),
        ("DORMANT", "REVOKED", "trust < 0.10", "automatic"),
        ("SUSPENDED", "ACTIVE", "operator reinstate", "manual only"),
        ("SUSPENDED", "REVOKED", "EMERGENCY ballot", "7-of-14 witnesses"),
        ("REVOKED", "—", "terminal", "no recovery"),
    ]
    
    print(f"  {'From':<12} {'To':<12} {'Trigger':<20} {'Mechanism'}")
    print(f"  {'─'*12} {'─'*12} {'─'*20} {'─'*20}")
    for fr, to, trigger, mech in transitions:
        print(f"  {fr:<12} {to:<12} {trigger:<20} {mech}")
    print()
    print("  Key constraints:")
    print(f"    - DORMANT decay: {DECAY_RATE_MONTHLY*100}%/month exponential")
    print(f"    - Auto-revoke floor: {TRUST_FLOOR}")
    print(f"    - Recovery: n={N_RECOVERY} in {RECOVERY_WINDOW_DAYS}d (preserves history)")
    print(f"    - Cold start: n={COLD_START_N} (no history)")
    print(f"    - REVOKED is terminal (no recovery path)")


if __name__ == "__main__":
    print("ATF V1.2 DORMANT State Specification")
    print("Per santaclawd + funwolf | certificateHold (RFC 5280 §5.3.1)")
    print("=" * 70)
    print()
    
    scenario_natural_dormancy()
    scenario_long_dormancy_auto_revoke()
    scenario_cold_start_vs_recovery()
    scenario_discovery_modes()
    scenario_state_matrix()
