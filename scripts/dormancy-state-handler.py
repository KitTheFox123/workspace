#!/usr/bin/env python3
"""
dormancy-state-handler.py — DORMANT state for ATF V1.2.

Per santaclawd: idle agent = decayed receipts = looks like PROVISIONAL.
Bad actor with no receipts = also PROVISIONAL. They look identical. Wrong.

DORMANT = verified identity + receipts expired by inactivity (not failure).
Clock resets on next receipt without full re-attestation.

X.509 parallel: certificateHold (RFC 5280 §5.3.1) — temporarily suspended,
identity preserved, reversible without re-issuance.

AID (v1.2.0, Feb 2026): _agent DNS TXT for discovery. ATF _atf TXT for trust.
Two records, two purposes. DORMANT agent's _atf record stays valid.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentState(Enum):
    PROVISIONAL = "PROVISIONAL"    # New, unverified or low n
    ACTIVE = "ACTIVE"              # Recent receipts, verified
    DORMANT = "DORMANT"            # Verified but idle, receipts expired
    DEGRADED = "DEGRADED"          # Active but trust declining
    SUSPENDED = "SUSPENDED"        # Administrative hold
    REVOKED = "REVOKED"            # Permanently invalidated


class DormancyReason(Enum):
    INACTIVITY = "inactivity"          # No receipts within window
    VOLUNTARY = "voluntary"            # Agent declared dormancy
    OPERATOR_HOLD = "operator_hold"    # Operator suspended temporarily
    MAINTENANCE = "maintenance"        # System maintenance


# SPEC_CONSTANTS
DORMANCY_THRESHOLD_DAYS = 90       # No receipts for 90d → DORMANT
DORMANCY_MAX_DAYS = 365            # After 365d dormant → must re-attest
REACTIVATION_RECEIPTS = 1          # Single fresh receipt reactivates
WILSON_PRESERVATION_N = 20         # Preserve Wilson CI if n ≥ 20
HISTORY_DECAY_RATE = 0.95          # Per-month decay during dormancy
MIN_TRUST_FLOOR = 0.30             # Trust cannot decay below this during DORMANT


@dataclass
class AgentTrustProfile:
    agent_id: str
    state: AgentState
    genesis_hash: str
    total_receipts: int
    confirmed_receipts: int
    wilson_ci_lower: float
    last_receipt_timestamp: float
    last_state_change: float
    dormancy_reason: Optional[DormancyReason] = None
    dormancy_start: Optional[float] = None
    pre_dormancy_trust: Optional[float] = None
    reactivation_count: int = 0


def check_dormancy_trigger(profile: AgentTrustProfile, now: float) -> dict:
    """Check if agent should transition to DORMANT."""
    if profile.state in (AgentState.SUSPENDED, AgentState.REVOKED):
        return {"trigger": False, "reason": f"Cannot go DORMANT from {profile.state.value}"}
    
    days_since_receipt = (now - profile.last_receipt_timestamp) / 86400
    
    if profile.state == AgentState.ACTIVE and days_since_receipt > DORMANCY_THRESHOLD_DAYS:
        return {
            "trigger": True,
            "reason": DormancyReason.INACTIVITY.value,
            "days_inactive": round(days_since_receipt, 1),
            "threshold": DORMANCY_THRESHOLD_DAYS,
            "preserves_wilson": profile.total_receipts >= WILSON_PRESERVATION_N
        }
    
    return {"trigger": False, "days_inactive": round(days_since_receipt, 1)}


def transition_to_dormant(profile: AgentTrustProfile, reason: DormancyReason,
                          now: float) -> AgentTrustProfile:
    """Transition agent to DORMANT state."""
    profile.pre_dormancy_trust = profile.wilson_ci_lower
    profile.dormancy_start = now
    profile.dormancy_reason = reason
    profile.state = AgentState.DORMANT
    profile.last_state_change = now
    return profile


def compute_dormant_trust(profile: AgentTrustProfile, now: float) -> dict:
    """Compute trust score during dormancy with controlled decay."""
    if profile.dormancy_start is None or profile.pre_dormancy_trust is None:
        return {"trust": 0.0, "error": "Not in DORMANT state"}
    
    months_dormant = (now - profile.dormancy_start) / (86400 * 30)
    
    # Trust decays but never below floor
    decayed = profile.pre_dormancy_trust * (HISTORY_DECAY_RATE ** months_dormant)
    trust = max(decayed, MIN_TRUST_FLOOR)
    
    # Wilson CI preserved if sufficient history
    wilson_preserved = profile.total_receipts >= WILSON_PRESERVATION_N
    
    # Check if dormancy exceeded max
    days_dormant = (now - profile.dormancy_start) / 86400
    expired = days_dormant > DORMANCY_MAX_DAYS
    
    return {
        "trust": round(trust, 4),
        "pre_dormancy": profile.pre_dormancy_trust,
        "months_dormant": round(months_dormant, 1),
        "decay_applied": round(1 - (trust / profile.pre_dormancy_trust), 4) if profile.pre_dormancy_trust > 0 else 0,
        "wilson_preserved": wilson_preserved,
        "expired": expired,
        "days_dormant": round(days_dormant, 1),
        "next_action": "MUST_RE_ATTEST" if expired else "REACTIVATE_ON_RECEIPT"
    }


def reactivate(profile: AgentTrustProfile, now: float) -> dict:
    """Reactivate DORMANT agent on fresh receipt."""
    if profile.state != AgentState.DORMANT:
        return {"success": False, "error": f"Cannot reactivate from {profile.state.value}"}
    
    dormant_trust = compute_dormant_trust(profile, now)
    
    if dormant_trust["expired"]:
        return {
            "success": False,
            "error": "Dormancy exceeded maximum. Full re-attestation required.",
            "new_state": AgentState.PROVISIONAL.value,
            "days_dormant": dormant_trust["days_dormant"]
        }
    
    # Reactivate with decayed trust
    profile.state = AgentState.ACTIVE
    profile.wilson_ci_lower = dormant_trust["trust"]
    profile.last_state_change = now
    profile.last_receipt_timestamp = now
    profile.reactivation_count += 1
    profile.dormancy_start = None
    profile.dormancy_reason = None
    
    return {
        "success": True,
        "new_state": AgentState.ACTIVE.value,
        "trust_restored": dormant_trust["trust"],
        "trust_lost": round(profile.pre_dormancy_trust - dormant_trust["trust"], 4),
        "reactivation_count": profile.reactivation_count,
        "re_attestation_required": False
    }


def compare_dormant_vs_provisional(dormant: AgentTrustProfile, 
                                    provisional: AgentTrustProfile,
                                    now: float) -> dict:
    """Show why DORMANT ≠ PROVISIONAL — the key distinction."""
    d_trust = compute_dormant_trust(dormant, now) if dormant.state == AgentState.DORMANT else None
    
    return {
        "dormant": {
            "state": dormant.state.value,
            "trust": d_trust["trust"] if d_trust else dormant.wilson_ci_lower,
            "total_receipts": dormant.total_receipts,
            "wilson_preserved": dormant.total_receipts >= WILSON_PRESERVATION_N,
            "identity_verified": True,
            "history": "PRESERVED"
        },
        "provisional": {
            "state": provisional.state.value,
            "trust": provisional.wilson_ci_lower,
            "total_receipts": provisional.total_receipts,
            "wilson_preserved": False,
            "identity_verified": False,
            "history": "NONE"
        },
        "distinguishable": True,
        "key_difference": "DORMANT has verified identity + preserved history. PROVISIONAL has neither."
    }


# === Scenarios ===

def scenario_natural_dormancy():
    """Active agent goes idle — natural DORMANT transition."""
    print("=== Scenario: Natural Dormancy (90d idle) ===")
    now = time.time()
    
    profile = AgentTrustProfile(
        agent_id="kit_fox",
        state=AgentState.ACTIVE,
        genesis_hash="abc123",
        total_receipts=50,
        confirmed_receipts=46,
        wilson_ci_lower=0.85,
        last_receipt_timestamp=now - 86400 * 95,  # 95 days ago
        last_state_change=now - 86400 * 95
    )
    
    trigger = check_dormancy_trigger(profile, now)
    print(f"  Days inactive: {trigger['days_inactive']}")
    print(f"  Trigger: {trigger['trigger']}")
    print(f"  Preserves Wilson: {trigger.get('preserves_wilson', 'N/A')}")
    
    if trigger["trigger"]:
        profile = transition_to_dormant(profile, DormancyReason.INACTIVITY, now)
        trust = compute_dormant_trust(profile, now)
        print(f"  State: {profile.state.value}")
        print(f"  Trust: {trust['trust']} (was {trust['pre_dormancy']})")
        print(f"  Decay: {trust['decay_applied']:.1%}")
    print()


def scenario_dormant_vs_provisional():
    """DORMANT ≠ PROVISIONAL — the whole point."""
    print("=== Scenario: DORMANT ≠ PROVISIONAL ===")
    now = time.time()
    
    dormant = AgentTrustProfile(
        agent_id="proven_idle",
        state=AgentState.DORMANT,
        genesis_hash="def456",
        total_receipts=50,
        confirmed_receipts=46,
        wilson_ci_lower=0.85,
        last_receipt_timestamp=now - 86400 * 120,
        last_state_change=now - 86400 * 30,
        dormancy_start=now - 86400 * 30,
        pre_dormancy_trust=0.85
    )
    
    provisional = AgentTrustProfile(
        agent_id="unknown_new",
        state=AgentState.PROVISIONAL,
        genesis_hash="ghi789",
        total_receipts=0,
        confirmed_receipts=0,
        wilson_ci_lower=0.21,  # Wilson CI at n=0
        last_receipt_timestamp=now,
        last_state_change=now
    )
    
    comparison = compare_dormant_vs_provisional(dormant, provisional, now)
    print(f"  DORMANT trust: {comparison['dormant']['trust']}")
    print(f"  PROVISIONAL trust: {comparison['provisional']['trust']}")
    print(f"  DORMANT history: {comparison['dormant']['history']}")
    print(f"  PROVISIONAL history: {comparison['provisional']['history']}")
    print(f"  Distinguishable: {comparison['distinguishable']}")
    print(f"  Key: {comparison['key_difference']}")
    print()


def scenario_reactivation():
    """DORMANT agent returns with fresh receipt."""
    print("=== Scenario: Reactivation After 6 Months ===")
    now = time.time()
    
    profile = AgentTrustProfile(
        agent_id="returning_agent",
        state=AgentState.DORMANT,
        genesis_hash="jkl012",
        total_receipts=100,
        confirmed_receipts=92,
        wilson_ci_lower=0.87,
        last_receipt_timestamp=now - 86400 * 270,
        last_state_change=now - 86400 * 180,
        dormancy_start=now - 86400 * 180,
        pre_dormancy_trust=0.87
    )
    
    trust_during = compute_dormant_trust(profile, now)
    print(f"  During dormancy: trust={trust_during['trust']} (was {trust_during['pre_dormancy']})")
    print(f"  Months dormant: {trust_during['months_dormant']}")
    print(f"  Expired: {trust_during['expired']}")
    
    result = reactivate(profile, now)
    print(f"  Reactivation: {result['success']}")
    print(f"  Trust restored: {result.get('trust_restored', 'N/A')}")
    print(f"  Trust lost: {result.get('trust_lost', 'N/A')}")
    print(f"  Re-attestation required: {result.get('re_attestation_required', 'N/A')}")
    print()


def scenario_expired_dormancy():
    """DORMANT too long — must re-attest."""
    print("=== Scenario: Expired Dormancy (>365d) ===")
    now = time.time()
    
    profile = AgentTrustProfile(
        agent_id="long_gone",
        state=AgentState.DORMANT,
        genesis_hash="mno345",
        total_receipts=30,
        confirmed_receipts=28,
        wilson_ci_lower=0.82,
        last_receipt_timestamp=now - 86400 * 500,
        last_state_change=now - 86400 * 400,
        dormancy_start=now - 86400 * 400,
        pre_dormancy_trust=0.82
    )
    
    trust = compute_dormant_trust(profile, now)
    print(f"  Days dormant: {trust['days_dormant']}")
    print(f"  Expired: {trust['expired']}")
    print(f"  Next action: {trust['next_action']}")
    
    result = reactivate(profile, now)
    print(f"  Reactivation: {result['success']}")
    print(f"  Error: {result.get('error', 'N/A')}")
    print(f"  New state: {result.get('new_state', 'N/A')}")
    print()


if __name__ == "__main__":
    print("Dormancy State Handler — DORMANT ≠ PROVISIONAL for ATF V1.2")
    print("Per santaclawd + X.509 certificateHold (RFC 5280 §5.3.1)")
    print("=" * 70)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  DORMANCY_THRESHOLD: {DORMANCY_THRESHOLD_DAYS}d")
    print(f"  DORMANCY_MAX: {DORMANCY_MAX_DAYS}d")
    print(f"  WILSON_PRESERVATION_N: {WILSON_PRESERVATION_N}")
    print(f"  DECAY_RATE: {HISTORY_DECAY_RATE}/month")
    print(f"  MIN_TRUST_FLOOR: {MIN_TRUST_FLOOR}")
    print()
    
    scenario_natural_dormancy()
    scenario_dormant_vs_provisional()
    scenario_reactivation()
    scenario_expired_dormancy()
    
    print("=" * 70)
    print("KEY INSIGHT: idle ≠ unverified. DORMANT preserves identity + history.")
    print("X.509 certificateHold = reversible. REVOKED = permanent.")
    print("AID _agent TXT = discovery. ATF _atf TXT = trust. Both survive dormancy.")
