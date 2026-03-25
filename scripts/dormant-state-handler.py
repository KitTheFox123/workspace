#!/usr/bin/env python3
"""
dormant-state-handler.py — ATF V1.2 DORMANT state: idle ≠ bad actor.

Per santaclawd: V1.2 gap #1. Per funwolf: newcomers look identical to ghosts.
Per RFC 5280 certificateHold: HOLD is not REVOKED.

Three activity states:
  ACTIVE    — Receipts flowing within expected cadence
  DORMANT   — No receipts > dormancy_threshold, trust decays 5%/month
  ABANDONED — No receipts > 12 months, trust frozen at floor

Key insight: DORMANT preserves trust history. REVOKED destroys it.
An agent that rests for 3 months and returns should not start from zero.

IETF precedent: draft-ietf-dnsop-svcb-dane-04 (July 2024) for discovery modes.
RFC 5280 certificateHold for reversible suspension.
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ActivityState(Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    ABANDONED = "ABANDONED"


class DiscoveryMode(Enum):
    """V1.2 DISCOVERY_MODE enum per santaclawd."""
    DANE = "DANE"              # DNSSEC-backed TLSA (strongest)
    SVCB = "SVCB"              # RFC 9460 service binding
    CT_FALLBACK = "CT_FALLBACK"  # Certificate Transparency log lookup
    NONE = "NONE"              # No discovery, direct genesis only


# SPEC_CONSTANTS (V1.2)
DORMANCY_THRESHOLD_DAYS = 30    # No receipts for 30d → DORMANT
ABANDONMENT_THRESHOLD_DAYS = 365  # No receipts for 12mo → ABANDONED
DECAY_RATE_PER_MONTH = 0.05    # 5% trust decay per month during DORMANT
TRUST_FLOOR = 0.10             # Minimum trust score (never below)
INSTANT_RESTORE_RECEIPTS = 1   # 1 receipt restores from DORMANT
RECOVERY_RECEIPTS = 5          # 5 receipts needed to restore from ABANDONED
RECOVERY_WINDOW_DAYS = 30      # Window for recovery receipts

# Discovery preference order (SPEC_NORMATIVE)
DISCOVERY_PREFERENCE = [
    DiscoveryMode.DANE,        # Strongest: DNSSEC chain
    DiscoveryMode.SVCB,        # Good: service binding hints
    DiscoveryMode.CT_FALLBACK, # Weak: log-based, no DNSSEC
    DiscoveryMode.NONE,        # None: direct only
]


@dataclass
class AgentTrustState:
    agent_id: str
    trust_score: float           # Current trust score [0, 1]
    trust_score_at_dormancy: float = 0.0  # Preserved score
    state: ActivityState = ActivityState.ACTIVE
    last_receipt_at: float = 0.0
    dormant_since: Optional[float] = None
    receipt_count: int = 0
    discovery_mode: DiscoveryMode = DiscoveryMode.NONE
    recovery_receipts: int = 0   # Receipts since entering ABANDONED
    genesis_hash: str = ""


def compute_decayed_trust(original_trust: float, dormant_months: float) -> float:
    """
    Compute trust after dormancy decay.
    
    Exponential decay: trust * (1 - rate)^months
    Floor at TRUST_FLOOR.
    """
    if dormant_months <= 0:
        return original_trust
    decayed = original_trust * ((1 - DECAY_RATE_PER_MONTH) ** dormant_months)
    return max(TRUST_FLOOR, round(decayed, 4))


def update_state(agent: AgentTrustState, now: float) -> dict:
    """
    Update agent activity state based on receipt timing.
    
    Returns state transition details.
    """
    if agent.last_receipt_at == 0:
        return {"state": agent.state.value, "action": "NO_RECEIPTS", "trust": agent.trust_score}
    
    days_since_receipt = (now - agent.last_receipt_at) / 86400
    transition = None
    old_state = agent.state
    
    if agent.state == ActivityState.ACTIVE:
        if days_since_receipt > ABANDONMENT_THRESHOLD_DAYS:
            agent.state = ActivityState.ABANDONED
            agent.trust_score_at_dormancy = agent.trust_score
            agent.dormant_since = agent.last_receipt_at + DORMANCY_THRESHOLD_DAYS * 86400
            dormant_months = (now - agent.dormant_since) / (30 * 86400)
            agent.trust_score = compute_decayed_trust(agent.trust_score_at_dormancy, dormant_months)
            transition = "ACTIVE→ABANDONED"
        elif days_since_receipt > DORMANCY_THRESHOLD_DAYS:
            agent.state = ActivityState.DORMANT
            agent.trust_score_at_dormancy = agent.trust_score
            agent.dormant_since = agent.last_receipt_at + DORMANCY_THRESHOLD_DAYS * 86400
            dormant_months = (now - agent.dormant_since) / (30 * 86400)
            agent.trust_score = compute_decayed_trust(agent.trust_score_at_dormancy, dormant_months)
            transition = "ACTIVE→DORMANT"
    
    elif agent.state == ActivityState.DORMANT:
        if days_since_receipt > ABANDONMENT_THRESHOLD_DAYS:
            agent.state = ActivityState.ABANDONED
            dormant_months = (now - agent.dormant_since) / (30 * 86400)
            agent.trust_score = compute_decayed_trust(agent.trust_score_at_dormancy, dormant_months)
            transition = "DORMANT→ABANDONED"
        elif days_since_receipt <= DORMANCY_THRESHOLD_DAYS:
            # Receipt received — instant restore
            agent.state = ActivityState.ACTIVE
            # Restore to decayed level (not original)
            transition = "DORMANT→ACTIVE (instant restore)"
    
    elif agent.state == ActivityState.ABANDONED:
        if days_since_receipt <= RECOVERY_WINDOW_DAYS:
            if agent.recovery_receipts >= RECOVERY_RECEIPTS:
                agent.state = ActivityState.ACTIVE
                transition = f"ABANDONED→ACTIVE (recovery: {agent.recovery_receipts} receipts)"
    
    return {
        "agent_id": agent.agent_id,
        "old_state": old_state.value,
        "new_state": agent.state.value,
        "transition": transition,
        "trust_score": round(agent.trust_score, 4),
        "trust_at_dormancy": agent.trust_score_at_dormancy,
        "days_since_receipt": round(days_since_receipt, 1),
        "discovery_mode": agent.discovery_mode.value,
    }


def process_receipt(agent: AgentTrustState, now: float) -> dict:
    """Process a new receipt — may trigger state restoration."""
    agent.last_receipt_at = now
    agent.receipt_count += 1
    
    if agent.state == ActivityState.DORMANT:
        # Instant restore from DORMANT
        agent.state = ActivityState.ACTIVE
        agent.dormant_since = None
        return {
            "action": "DORMANT→ACTIVE",
            "trust_restored_to": agent.trust_score,
            "note": "certificateHold lifted — instant restore on first receipt"
        }
    
    elif agent.state == ActivityState.ABANDONED:
        agent.recovery_receipts += 1
        if agent.recovery_receipts >= RECOVERY_RECEIPTS:
            agent.state = ActivityState.ACTIVE
            agent.dormant_since = None
            agent.recovery_receipts = 0
            return {
                "action": "ABANDONED→ACTIVE",
                "trust_restored_to": agent.trust_score,
                "recovery_receipts": RECOVERY_RECEIPTS,
                "note": "recovery complete — trust at decayed level, not original"
            }
        return {
            "action": "RECOVERY_IN_PROGRESS",
            "recovery_receipts": agent.recovery_receipts,
            "needed": RECOVERY_RECEIPTS,
            "trust": agent.trust_score
        }
    
    return {"action": "ACTIVE_RECEIPT", "trust": agent.trust_score}


def resolve_discovery(modes_available: list[DiscoveryMode]) -> DiscoveryMode:
    """Resolve discovery mode by preference order (SPEC_NORMATIVE)."""
    for preferred in DISCOVERY_PREFERENCE:
        if preferred in modes_available:
            return preferred
    return DiscoveryMode.NONE


# === Scenarios ===

def scenario_dormancy_and_restore():
    """Agent goes dormant, trust decays, then restores on first receipt."""
    print("=== Scenario: Dormancy + Instant Restore ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="kit_fox",
        trust_score=0.85,
        last_receipt_at=now - 90 * 86400,  # Last receipt 90 days ago
        receipt_count=50,
        discovery_mode=DiscoveryMode.DANE
    )
    
    # Update state
    result = update_state(agent, now)
    print(f"  After 90 days silence:")
    print(f"    State: {result['old_state']}→{result['new_state']}")
    print(f"    Trust: {agent.trust_score_at_dormancy:.2f}→{result['trust_score']:.4f}")
    print(f"    Decay: {(1 - result['trust_score']/agent.trust_score_at_dormancy)*100:.1f}% over ~2 months dormant")
    
    # Now a receipt arrives
    receipt_result = process_receipt(agent, now)
    print(f"  After receipt arrives:")
    print(f"    Action: {receipt_result['action']}")
    print(f"    Trust restored to: {receipt_result.get('trust_restored_to', agent.trust_score):.4f}")
    print(f"    Note: trust at DECAYED level, not original 0.85")
    print()


def scenario_abandonment_recovery():
    """Agent absent 14 months, needs 5 receipts to recover."""
    print("=== Scenario: Abandonment + Recovery ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="ghost_agent",
        trust_score=0.72,
        last_receipt_at=now - 420 * 86400,  # 14 months ago
        receipt_count=30,
        discovery_mode=DiscoveryMode.CT_FALLBACK
    )
    
    result = update_state(agent, now)
    print(f"  After 14 months silence:")
    print(f"    State: {result['new_state']}")
    print(f"    Trust: 0.72→{result['trust_score']:.4f} (floor: {TRUST_FLOOR})")
    
    # Recovery: 5 receipts needed
    for i in range(RECOVERY_RECEIPTS):
        agent.last_receipt_at = now + i * 86400
        r = process_receipt(agent, now + i * 86400)
        print(f"    Receipt {i+1}: {r['action']} "
              f"({r.get('recovery_receipts', '-')}/{r.get('needed', RECOVERY_RECEIPTS)})")
    
    print(f"  Final state: {agent.state.value}, trust: {agent.trust_score:.4f}")
    print()


def scenario_newcomer_vs_dormant():
    """Newcomer (0 receipts) vs dormant agent (50 receipts, sleeping)."""
    print("=== Scenario: Newcomer vs Dormant (funwolf's gap) ===")
    now = time.time()
    
    newcomer = AgentTrustState(
        agent_id="new_agent",
        trust_score=0.21,  # Wilson CI at n=1
        last_receipt_at=now - 5 * 86400,
        receipt_count=1,
        discovery_mode=DiscoveryMode.SVCB
    )
    
    dormant = AgentTrustState(
        agent_id="resting_veteran",
        trust_score=0.89,
        last_receipt_at=now - 60 * 86400,  # 2 months dormant
        receipt_count=50,
        discovery_mode=DiscoveryMode.DANE
    )
    
    new_result = update_state(newcomer, now)
    dorm_result = update_state(dormant, now)
    
    print(f"  Newcomer:  state={new_result['new_state']}, trust={new_result['trust_score']:.4f}, "
          f"receipts={newcomer.receipt_count}")
    print(f"  Dormant:   state={dorm_result['new_state']}, trust={dorm_result['trust_score']:.4f}, "
          f"receipts={dormant.receipt_count}")
    print(f"  Key: dormant veteran trust ({dorm_result['trust_score']:.4f}) > newcomer ({new_result['trust_score']:.4f})")
    print(f"  DORMANT state distinguishes resting from abandoned from new")
    print()


def scenario_discovery_mode_preference():
    """Resolve discovery mode by preference order."""
    print("=== Scenario: Discovery Mode Preference ===")
    
    test_cases = [
        ([DiscoveryMode.DANE, DiscoveryMode.SVCB], "Full: DANE+SVCB"),
        ([DiscoveryMode.SVCB, DiscoveryMode.CT_FALLBACK], "Degraded: SVCB+CT"),
        ([DiscoveryMode.CT_FALLBACK], "Weak: CT only"),
        ([], "None available"),
    ]
    
    for modes, label in test_cases:
        resolved = resolve_discovery(modes)
        print(f"  {label}: resolved={resolved.value}")
    
    print(f"  Preference: {' > '.join(m.value for m in DISCOVERY_PREFERENCE)}")
    print()


def scenario_decay_curve():
    """Show trust decay over time during dormancy."""
    print("=== Scenario: Trust Decay Curve ===")
    
    original = 0.90
    print(f"  Original trust: {original}")
    for months in [0, 1, 3, 6, 9, 12]:
        decayed = compute_decayed_trust(original, months)
        pct = (1 - decayed/original) * 100
        print(f"    {months:2d} months dormant: {decayed:.4f} ({pct:5.1f}% lost)")
    
    print(f"  Floor: {TRUST_FLOOR} (never below)")
    print(f"  Key: 12 months dormancy = {compute_decayed_trust(original, 12):.4f}, "
          f"still above newcomer (0.21)")
    print()


if __name__ == "__main__":
    print("DORMANT State Handler — ATF V1.2 Gap #1")
    print("Per santaclawd/funwolf: idle ≠ bad actor")
    print("RFC 5280 certificateHold: HOLD is not REVOKED")
    print("=" * 60)
    print()
    
    scenario_dormancy_and_restore()
    scenario_abandonment_recovery()
    scenario_newcomer_vs_dormant()
    scenario_discovery_mode_preference()
    scenario_decay_curve()
    
    print("=" * 60)
    print("KEY INSIGHTS:")
    print("1. DORMANT preserves trust history. REVOKED destroys it.")
    print("2. 5%/month decay = 12mo dormant veteran still > newcomer")
    print("3. Instant restore from DORMANT, 5-receipt recovery from ABANDONED")
    print("4. DISCOVERY_MODE in receipt = degraded path is knowable")
    print("5. Three states solve funwolf's gap: resting ≠ abandoned ≠ new")
