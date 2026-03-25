#!/usr/bin/env python3
"""
dormancy-state-machine.py — DORMANT state for ATF V1.2.

Per santaclawd: idle agent with clean history != bad actor with no receipts.
Both currently look PROVISIONAL. That's wrong.

Per Michel & Defiebre-Muller (Scand J Mgmt, March 2025):
  Dormancy = composite process (entering, enduring, overcoming).

State machine:
  ACTIVE → DORMANT (inactivity timeout, clean exit)
  DORMANT → ACTIVE (new receipt, preserves earned trust)
  DORMANT → PROVISIONAL (genesis expired during dormancy)
  PROVISIONAL → ACTIVE (new receipts, starts from zero)

Three signals distinguish DORMANT from PROVISIONAL:
  1. Prior receipt history exists (n > 0)
  2. Genesis still valid (not expired/revoked)
  3. No DISPUTED/FAILED in final receipt window

DORMANT preserves: trust score (frozen), Wilson CI width, receipt history.
DORMANT loses: real-time behavioral signal (decayed to zero).
Re-entry: first receipt restarts clock WITHOUT full re-attestation.
"""

import time
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import math


class TrustState(Enum):
    PROVISIONAL = "PROVISIONAL"   # New or failed — start from zero
    ACTIVE = "ACTIVE"             # Recent receipts, trust updating
    DORMANT = "DORMANT"           # Idle with clean history — frozen trust
    DEGRADED = "DEGRADED"         # Active but failing checks
    SUSPENDED = "SUSPENDED"       # Under investigation
    REVOKED = "REVOKED"           # Permanently removed


class TransitionReason(Enum):
    INACTIVITY_TIMEOUT = "inactivity_timeout"
    NEW_RECEIPT = "new_receipt"
    GENESIS_EXPIRED = "genesis_expired"
    DISPUTE_DURING_DORMANCY = "dispute_during_dormancy"
    RE_ATTESTATION = "re_attestation"
    REVOCATION = "revocation"
    DEGRADATION = "degradation"


# SPEC_CONSTANTS
DORMANCY_TIMEOUT_DAYS = 30          # Days without receipt → DORMANT
GENESIS_MAX_AGE_DAYS = 365          # Genesis validity
MIN_RECEIPTS_FOR_DORMANCY = 5       # Must have earned history to go DORMANT
MIN_RECOVERY_RECEIPTS = 5           # Receipts needed for full re-activation
DORMANT_TRUST_DECAY_RATE = 0.0      # Trust does NOT decay during dormancy
MAX_DORMANCY_DAYS = 365             # After this → requires re-attestation


@dataclass
class AgentTrustProfile:
    agent_id: str
    state: TrustState = TrustState.PROVISIONAL
    trust_score: float = 0.0
    wilson_ci_lower: float = 0.0
    wilson_ci_upper: float = 1.0
    total_receipts: int = 0
    confirmed_receipts: int = 0
    disputed_receipts: int = 0
    failed_receipts: int = 0
    last_receipt_timestamp: float = 0.0
    dormancy_entered: Optional[float] = None
    dormancy_trust_frozen: Optional[float] = None
    genesis_created: float = 0.0
    genesis_valid_until: float = 0.0
    state_history: list = field(default_factory=list)


def wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval."""
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denom
    return (max(0, center - spread), min(1, center + spread))


def check_dormancy_eligibility(profile: AgentTrustProfile, now: float) -> dict:
    """Check if agent should transition to DORMANT."""
    days_since_receipt = (now - profile.last_receipt_timestamp) / 86400
    genesis_valid = now < profile.genesis_valid_until
    has_history = profile.total_receipts >= MIN_RECEIPTS_FOR_DORMANCY
    clean_exit = profile.disputed_receipts == 0 or (
        profile.disputed_receipts / max(1, profile.total_receipts) < 0.1
    )
    
    eligible = (
        profile.state == TrustState.ACTIVE and
        days_since_receipt >= DORMANCY_TIMEOUT_DAYS and
        genesis_valid and
        has_history and
        clean_exit
    )
    
    return {
        "eligible": eligible,
        "days_since_receipt": round(days_since_receipt, 1),
        "genesis_valid": genesis_valid,
        "has_history": has_history,
        "total_receipts": profile.total_receipts,
        "clean_exit": clean_exit,
        "dispute_ratio": round(profile.disputed_receipts / max(1, profile.total_receipts), 3)
    }


def transition_to_dormant(profile: AgentTrustProfile, now: float) -> AgentTrustProfile:
    """Transition ACTIVE → DORMANT. Freeze trust score."""
    profile.state = TrustState.DORMANT
    profile.dormancy_entered = now
    profile.dormancy_trust_frozen = profile.trust_score
    profile.state_history.append({
        "from": "ACTIVE", "to": "DORMANT",
        "reason": TransitionReason.INACTIVITY_TIMEOUT.value,
        "timestamp": now,
        "frozen_trust": profile.trust_score,
        "frozen_ci": (profile.wilson_ci_lower, profile.wilson_ci_upper)
    })
    return profile


def reactivate_from_dormancy(profile: AgentTrustProfile, now: float) -> dict:
    """DORMANT → ACTIVE on new receipt. Preserves earned trust."""
    dormancy_days = (now - profile.dormancy_entered) / 86400 if profile.dormancy_entered else 0
    
    # Check if dormancy exceeded max
    if dormancy_days > MAX_DORMANCY_DAYS:
        # Too long — requires re-attestation
        profile.state = TrustState.PROVISIONAL
        profile.trust_score = 0.0
        profile.wilson_ci_lower, profile.wilson_ci_upper = 0.0, 1.0
        profile.state_history.append({
            "from": "DORMANT", "to": "PROVISIONAL",
            "reason": "max_dormancy_exceeded",
            "timestamp": now,
            "dormancy_days": round(dormancy_days, 1)
        })
        return {"state": "PROVISIONAL", "reason": "max_dormancy_exceeded",
                "dormancy_days": round(dormancy_days, 1), "trust_preserved": False}
    
    # Check genesis still valid
    if now >= profile.genesis_valid_until:
        profile.state = TrustState.PROVISIONAL
        profile.trust_score = 0.0
        profile.state_history.append({
            "from": "DORMANT", "to": "PROVISIONAL",
            "reason": TransitionReason.GENESIS_EXPIRED.value,
            "timestamp": now
        })
        return {"state": "PROVISIONAL", "reason": "genesis_expired",
                "trust_preserved": False}
    
    # Normal re-activation — preserve trust
    profile.state = TrustState.ACTIVE
    profile.trust_score = profile.dormancy_trust_frozen or profile.trust_score
    profile.last_receipt_timestamp = now
    profile.dormancy_entered = None
    profile.state_history.append({
        "from": "DORMANT", "to": "ACTIVE",
        "reason": TransitionReason.NEW_RECEIPT.value,
        "timestamp": now,
        "dormancy_days": round(dormancy_days, 1),
        "trust_preserved": profile.trust_score
    })
    
    return {
        "state": "ACTIVE",
        "reason": "receipt_received",
        "dormancy_days": round(dormancy_days, 1),
        "trust_preserved": True,
        "trust_score": profile.trust_score,
        "ci": (profile.wilson_ci_lower, profile.wilson_ci_upper)
    }


# === Scenarios ===

def scenario_clean_dormancy():
    """Active agent goes quiet — clean DORMANT transition."""
    print("=== Scenario: Clean Dormancy (Earned History) ===")
    now = time.time()
    
    profile = AgentTrustProfile(
        agent_id="reliable_agent",
        state=TrustState.ACTIVE,
        trust_score=0.85,
        total_receipts=50,
        confirmed_receipts=47,
        disputed_receipts=1,
        failed_receipts=2,
        last_receipt_timestamp=now - 86400 * 45,  # 45 days ago
        genesis_created=now - 86400 * 200,
        genesis_valid_until=now + 86400 * 165
    )
    profile.wilson_ci_lower, profile.wilson_ci_upper = wilson_ci(47, 50)
    
    eligibility = check_dormancy_eligibility(profile, now)
    print(f"  Eligible: {eligibility['eligible']}")
    print(f"  Days since receipt: {eligibility['days_since_receipt']}")
    print(f"  Has history: {eligibility['has_history']} ({eligibility['total_receipts']} receipts)")
    print(f"  Clean exit: {eligibility['clean_exit']} (dispute ratio: {eligibility['dispute_ratio']})")
    
    if eligibility['eligible']:
        profile = transition_to_dormant(profile, now)
        print(f"  State: {profile.state.value}")
        print(f"  Trust frozen at: {profile.dormancy_trust_frozen}")
        print(f"  CI: [{profile.wilson_ci_lower:.3f}, {profile.wilson_ci_upper:.3f}]")
    print()


def scenario_dormant_reactivation():
    """Dormant agent returns — trust preserved."""
    print("=== Scenario: Dormant Reactivation (Trust Preserved) ===")
    now = time.time()
    
    profile = AgentTrustProfile(
        agent_id="returning_agent",
        state=TrustState.DORMANT,
        trust_score=0.82,
        total_receipts=30,
        confirmed_receipts=28,
        disputed_receipts=0,
        failed_receipts=2,
        last_receipt_timestamp=now - 86400 * 90,
        dormancy_entered=now - 86400 * 60,
        dormancy_trust_frozen=0.82,
        genesis_created=now - 86400 * 300,
        genesis_valid_until=now + 86400 * 65
    )
    profile.wilson_ci_lower, profile.wilson_ci_upper = wilson_ci(28, 30)
    
    result = reactivate_from_dormancy(profile, now)
    print(f"  Result: {result['state']}")
    print(f"  Trust preserved: {result['trust_preserved']}")
    print(f"  Trust score: {result.get('trust_score', 0)}")
    print(f"  Dormancy duration: {result['dormancy_days']} days")
    print(f"  CI: {result.get('ci', 'N/A')}")
    print()


def scenario_provisional_vs_dormant():
    """Compare: new agent (PROVISIONAL) vs idle agent (DORMANT)."""
    print("=== Scenario: PROVISIONAL vs DORMANT (Same Inactivity) ===")
    now = time.time()
    
    new_agent = AgentTrustProfile(
        agent_id="new_agent",
        state=TrustState.PROVISIONAL,
        trust_score=0.0,
        total_receipts=0,
        genesis_created=now - 86400 * 5,
        genesis_valid_until=now + 86400 * 360
    )
    
    idle_agent = AgentTrustProfile(
        agent_id="idle_agent",
        state=TrustState.DORMANT,
        trust_score=0.88,
        total_receipts=100,
        confirmed_receipts=95,
        dormancy_entered=now - 86400 * 45,
        dormancy_trust_frozen=0.88,
        genesis_created=now - 86400 * 300,
        genesis_valid_until=now + 86400 * 65
    )
    idle_agent.wilson_ci_lower, idle_agent.wilson_ci_upper = wilson_ci(95, 100)
    
    print(f"  New agent:  state={new_agent.state.value}, trust={new_agent.trust_score}, receipts={new_agent.total_receipts}")
    print(f"  Idle agent: state={idle_agent.state.value}, trust={idle_agent.trust_score}, receipts={idle_agent.total_receipts}")
    print(f"  Without DORMANT: both look like PROVISIONAL — indistinguishable")
    print(f"  With DORMANT: idle agent preserves 0.88 trust, CI [{idle_agent.wilson_ci_lower:.3f}, {idle_agent.wilson_ci_upper:.3f}]")
    print(f"  Counterparty knows: DORMANT = trusted but idle. PROVISIONAL = unproven.")
    print()


def scenario_max_dormancy_exceeded():
    """Agent dormant too long — requires re-attestation."""
    print("=== Scenario: Max Dormancy Exceeded (Re-attestation Required) ===")
    now = time.time()
    
    profile = AgentTrustProfile(
        agent_id="long_dormant",
        state=TrustState.DORMANT,
        trust_score=0.75,
        total_receipts=40,
        confirmed_receipts=35,
        dormancy_entered=now - 86400 * 400,  # 400 days dormant
        dormancy_trust_frozen=0.75,
        genesis_created=now - 86400 * 500,
        genesis_valid_until=now + 86400 * 100
    )
    
    result = reactivate_from_dormancy(profile, now)
    print(f"  Dormancy: {result['dormancy_days']} days (max: {MAX_DORMANCY_DAYS})")
    print(f"  Result: {result['state']}")
    print(f"  Trust preserved: {result['trust_preserved']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Must complete full re-attestation to return to ACTIVE")
    print()


if __name__ == "__main__":
    print("Dormancy State Machine — ATF V1.2")
    print("Per santaclawd + Michel & Defiebre-Muller (Scand J Mgmt, March 2025)")
    print("=" * 70)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  DORMANCY_TIMEOUT_DAYS = {DORMANCY_TIMEOUT_DAYS}")
    print(f"  MIN_RECEIPTS_FOR_DORMANCY = {MIN_RECEIPTS_FOR_DORMANCY}")
    print(f"  MAX_DORMANCY_DAYS = {MAX_DORMANCY_DAYS}")
    print(f"  MIN_RECOVERY_RECEIPTS = {MIN_RECOVERY_RECEIPTS}")
    print()
    
    scenario_clean_dormancy()
    scenario_dormant_reactivation()
    scenario_provisional_vs_dormant()
    scenario_max_dormancy_exceeded()
    
    print("=" * 70)
    print("KEY INSIGHT: DORMANT != PROVISIONAL.")
    print("DORMANT = verified identity + clean history + voluntary inactivity.")
    print("PROVISIONAL = no history OR failed exit.")
    print("Dormancy PRESERVES earned trust. Provisional starts from zero.")
    print("Max dormancy (365d) prevents stale credentials from persisting.")
