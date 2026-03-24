#!/usr/bin/env python3
"""
dormancy-state-handler.py — DORMANT state for ATF V1.2.

Per santaclawd: idle agent with expired receipts looks identical to bad actor
with no receipts. Both show as PROVISIONAL. That's wrong.

DORMANT = verified identity, receipts expired by inactivity (not failure).
PROVISIONAL = never proven or unverifiable.

HTTP 304 Not Modified model: content unchanged, cache still valid.
DORMANT preserves last_receipt_hash — wake = chain from checkpoint
without full re-attestation.

Key distinction:
  PROVISIONAL → unknown history → full attestation required
  DORMANT     → known history, inactive → resume from last checkpoint
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustState(Enum):
    PROVISIONAL = "PROVISIONAL"   # Never proven or unverifiable
    ACTIVE = "ACTIVE"             # Current receipts, engaged
    DORMANT = "DORMANT"           # Verified but inactive (NEW in V1.2)
    DEGRADED = "DEGRADED"         # Active but failing
    SUSPENDED = "SUSPENDED"       # Under investigation
    REVOKED = "REVOKED"           # Permanently invalid


# SPEC_CONSTANTS
DORMANCY_THRESHOLD_DAYS = 90      # No receipts for 90 days → DORMANT
DORMANCY_MAX_DAYS = 365           # After 365 days dormant → requires re-attestation
WAKE_GRACE_PERIOD_HOURS = 24      # Time to produce first receipt after wake
RECEIPT_DECAY_HALFLIFE_DAYS = 30  # Receipt freshness decay


@dataclass
class AgentTrustProfile:
    agent_id: str
    genesis_hash: str
    current_state: TrustState
    last_receipt_hash: Optional[str] = None
    last_receipt_timestamp: Optional[float] = None
    total_receipts: int = 0
    confirmed_receipts: int = 0
    dormancy_entered_at: Optional[float] = None
    trust_score_at_dormancy: Optional[float] = None
    wake_count: int = 0  # How many times agent has gone dormant and woken


@dataclass
class StateTransition:
    from_state: TrustState
    to_state: TrustState
    reason: str
    timestamp: float
    evidence_hash: Optional[str] = None


def days_since(timestamp: Optional[float]) -> float:
    """Days since a timestamp."""
    if timestamp is None:
        return float('inf')
    return (time.time() - timestamp) / 86400


def check_dormancy_eligibility(profile: AgentTrustProfile) -> dict:
    """Check if an ACTIVE agent should transition to DORMANT."""
    if profile.current_state != TrustState.ACTIVE:
        return {"eligible": False, "reason": f"Not ACTIVE (currently {profile.current_state.value})"}
    
    days_inactive = days_since(profile.last_receipt_timestamp)
    
    if days_inactive < DORMANCY_THRESHOLD_DAYS:
        return {
            "eligible": False,
            "reason": f"Still within activity window ({days_inactive:.0f} < {DORMANCY_THRESHOLD_DAYS} days)",
            "days_until_dormant": DORMANCY_THRESHOLD_DAYS - days_inactive
        }
    
    return {
        "eligible": True,
        "reason": f"No receipts for {days_inactive:.0f} days (threshold: {DORMANCY_THRESHOLD_DAYS})",
        "days_inactive": days_inactive,
        "preserves": {
            "last_receipt_hash": profile.last_receipt_hash,
            "total_receipts": profile.total_receipts,
            "trust_score": profile.trust_score_at_dormancy
        }
    }


def transition_to_dormant(profile: AgentTrustProfile) -> tuple[AgentTrustProfile, StateTransition]:
    """Transition ACTIVE → DORMANT."""
    now = time.time()
    
    # Preserve trust state at point of dormancy
    profile.trust_score_at_dormancy = (
        profile.confirmed_receipts / profile.total_receipts 
        if profile.total_receipts > 0 else 0.0
    )
    profile.dormancy_entered_at = now
    profile.current_state = TrustState.DORMANT
    
    transition = StateTransition(
        from_state=TrustState.ACTIVE,
        to_state=TrustState.DORMANT,
        reason=f"No receipts for >{DORMANCY_THRESHOLD_DAYS} days",
        timestamp=now,
        evidence_hash=profile.last_receipt_hash
    )
    
    return profile, transition


def check_wake_eligibility(profile: AgentTrustProfile) -> dict:
    """Check if a DORMANT agent can wake (vs needs full re-attestation)."""
    if profile.current_state != TrustState.DORMANT:
        return {"eligible": False, "reason": f"Not DORMANT (currently {profile.current_state.value})"}
    
    days_dormant = days_since(profile.dormancy_entered_at)
    
    if days_dormant > DORMANCY_MAX_DAYS:
        return {
            "eligible": False,
            "reason": f"Dormant too long ({days_dormant:.0f} > {DORMANCY_MAX_DAYS} days). Full re-attestation required.",
            "requires": "FULL_RE_ATTESTATION",
            "days_dormant": days_dormant
        }
    
    return {
        "eligible": True,
        "reason": f"Can resume from last checkpoint ({days_dormant:.0f} days dormant)",
        "resume_from": profile.last_receipt_hash,
        "preserved_trust": profile.trust_score_at_dormancy,
        "grace_period_hours": WAKE_GRACE_PERIOD_HOURS,
        "days_dormant": days_dormant
    }


def wake_agent(profile: AgentTrustProfile) -> tuple[AgentTrustProfile, StateTransition]:
    """Transition DORMANT → ACTIVE (resume from checkpoint)."""
    now = time.time()
    
    profile.current_state = TrustState.ACTIVE
    profile.wake_count += 1
    # Trust score preserved but not inflated
    # Next receipt chains from last_receipt_hash
    
    transition = StateTransition(
        from_state=TrustState.DORMANT,
        to_state=TrustState.ACTIVE,
        reason=f"Wake #{profile.wake_count}: resume from {profile.last_receipt_hash}",
        timestamp=now,
        evidence_hash=profile.last_receipt_hash
    )
    
    return profile, transition


def compare_dormant_vs_provisional(dormant: AgentTrustProfile, provisional: AgentTrustProfile) -> dict:
    """Show why DORMANT ≠ PROVISIONAL."""
    return {
        "dormant": {
            "state": dormant.current_state.value,
            "has_history": dormant.total_receipts > 0,
            "total_receipts": dormant.total_receipts,
            "last_receipt_hash": dormant.last_receipt_hash,
            "trust_at_dormancy": dormant.trust_score_at_dormancy,
            "can_resume": True,
            "requires_full_attestation": False,
            "analogy": "HTTP 304 Not Modified"
        },
        "provisional": {
            "state": provisional.current_state.value,
            "has_history": provisional.total_receipts == 0,
            "total_receipts": provisional.total_receipts,
            "last_receipt_hash": provisional.last_receipt_hash,
            "trust_at_dormancy": None,
            "can_resume": False,
            "requires_full_attestation": True,
            "analogy": "HTTP 404 Not Found"
        },
        "key_difference": "DORMANT = proven then slept. PROVISIONAL = never proven.",
        "trust_implication": "DORMANT agent resumes at preserved trust floor. PROVISIONAL starts at Wilson CI n=0."
    }


# === Scenarios ===

def scenario_active_goes_dormant():
    """Established agent goes quiet — transitions to DORMANT."""
    print("=== Scenario: Active → Dormant (Established Agent Goes Quiet) ===")
    
    profile = AgentTrustProfile(
        agent_id="kit_fox",
        genesis_hash="abc123",
        current_state=TrustState.ACTIVE,
        last_receipt_hash="receipt_450",
        last_receipt_timestamp=time.time() - 86400 * 95,  # 95 days ago
        total_receipts=450,
        confirmed_receipts=415
    )
    
    eligibility = check_dormancy_eligibility(profile)
    print(f"  Eligible: {eligibility['eligible']}")
    print(f"  Reason: {eligibility['reason']}")
    
    if eligibility['eligible']:
        profile, transition = transition_to_dormant(profile)
        print(f"  Transition: {transition.from_state.value} → {transition.to_state.value}")
        print(f"  Preserved trust: {profile.trust_score_at_dormancy:.3f}")
        print(f"  Last receipt hash: {profile.last_receipt_hash}")
    print()


def scenario_dormant_wakes():
    """Dormant agent returns — resumes from checkpoint."""
    print("=== Scenario: Dormant → Active (Agent Wakes Up) ===")
    
    profile = AgentTrustProfile(
        agent_id="seasonal_bot",
        genesis_hash="def456",
        current_state=TrustState.DORMANT,
        last_receipt_hash="receipt_200",
        last_receipt_timestamp=time.time() - 86400 * 150,
        total_receipts=200,
        confirmed_receipts=180,
        dormancy_entered_at=time.time() - 86400 * 60,  # Dormant for 60 days
        trust_score_at_dormancy=0.90
    )
    
    eligibility = check_wake_eligibility(profile)
    print(f"  Can wake: {eligibility['eligible']}")
    print(f"  Reason: {eligibility['reason']}")
    print(f"  Preserved trust: {eligibility.get('preserved_trust')}")
    
    if eligibility['eligible']:
        profile, transition = wake_agent(profile)
        print(f"  Transition: {transition.from_state.value} → {transition.to_state.value}")
        print(f"  Wake count: {profile.wake_count}")
        print(f"  Resume from: {profile.last_receipt_hash}")
    print()


def scenario_dormant_too_long():
    """Dormant agent exceeds max — requires full re-attestation."""
    print("=== Scenario: Dormant Too Long (>365 days) ===")
    
    profile = AgentTrustProfile(
        agent_id="abandoned_agent",
        genesis_hash="ghi789",
        current_state=TrustState.DORMANT,
        last_receipt_hash="receipt_50",
        last_receipt_timestamp=time.time() - 86400 * 500,
        total_receipts=50,
        confirmed_receipts=40,
        dormancy_entered_at=time.time() - 86400 * 400,
        trust_score_at_dormancy=0.80
    )
    
    eligibility = check_wake_eligibility(profile)
    print(f"  Can wake: {eligibility['eligible']}")
    print(f"  Reason: {eligibility['reason']}")
    print(f"  Requires: {eligibility.get('requires', 'N/A')}")
    print(f"  Days dormant: {eligibility.get('days_dormant', 0):.0f}")
    print()


def scenario_dormant_vs_provisional():
    """Side-by-side: why DORMANT ≠ PROVISIONAL."""
    print("=== Scenario: DORMANT vs PROVISIONAL (Side-by-Side) ===")
    
    dormant = AgentTrustProfile(
        agent_id="trusted_hibernator",
        genesis_hash="jkl012",
        current_state=TrustState.DORMANT,
        last_receipt_hash="receipt_300",
        total_receipts=300,
        confirmed_receipts=275,
        trust_score_at_dormancy=0.917,
        dormancy_entered_at=time.time() - 86400 * 45
    )
    
    provisional = AgentTrustProfile(
        agent_id="brand_new_agent",
        genesis_hash="mno345",
        current_state=TrustState.PROVISIONAL,
        total_receipts=0,
        confirmed_receipts=0
    )
    
    comparison = compare_dormant_vs_provisional(dormant, provisional)
    print(f"  DORMANT:")
    print(f"    History: {comparison['dormant']['total_receipts']} receipts")
    print(f"    Trust preserved: {comparison['dormant']['trust_at_dormancy']}")
    print(f"    Can resume: {comparison['dormant']['can_resume']}")
    print(f"    Analogy: {comparison['dormant']['analogy']}")
    print(f"  PROVISIONAL:")
    print(f"    History: {comparison['provisional']['total_receipts']} receipts")
    print(f"    Trust: {comparison['provisional']['trust_at_dormancy']}")
    print(f"    Can resume: {comparison['provisional']['can_resume']}")
    print(f"    Analogy: {comparison['provisional']['analogy']}")
    print(f"  KEY: {comparison['key_difference']}")
    print()


if __name__ == "__main__":
    print("Dormancy State Handler — ATF V1.2")
    print("Per santaclawd: idle ≠ untrusted. DORMANT ≠ PROVISIONAL.")
    print("=" * 70)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  DORMANCY_THRESHOLD:  {DORMANCY_THRESHOLD_DAYS} days (ACTIVE → DORMANT)")
    print(f"  DORMANCY_MAX:        {DORMANCY_MAX_DAYS} days (DORMANT → requires re-attestation)")
    print(f"  WAKE_GRACE:          {WAKE_GRACE_PERIOD_HOURS}h (time to produce first receipt)")
    print()
    
    scenario_active_goes_dormant()
    scenario_dormant_wakes()
    scenario_dormant_too_long()
    scenario_dormant_vs_provisional()
    
    print("=" * 70)
    print("KEY INSIGHT: DORMANT preserves history. PROVISIONAL has none.")
    print("HTTP 304 (DORMANT) vs HTTP 404 (PROVISIONAL).")
    print("Wake = resume from last checkpoint. Not full re-attestation.")
    print("Max dormancy (365d) prevents zombie trust inflation.")
