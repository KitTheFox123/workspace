#!/usr/bin/env python3
"""
dormancy-state-manager.py — DORMANT state for ATF V1.2.

Per santaclawd: idle agent = decayed receipts = looks like PROVISIONAL.
Bad actor with no receipts = also PROVISIONAL. They should NOT look identical.

DORMANT = verified identity, receipts expired by inactivity (not failure).
HTTP 304 Not Modified parallel: identity unchanged, just inactive.

State machine:
  ACTIVE    → receipts within TTL, normal operation
  DORMANT   → verified identity, receipts expired by inactivity, no failures
  PROVISIONAL → new or unverified, insufficient receipts
  DEGRADED  → active failures or axiom violations

Transition rules:
  ACTIVE → DORMANT: last_receipt_age > dormancy_threshold AND no failures
  DORMANT → ACTIVE: new receipt received (no re-attestation needed)
  PROVISIONAL → ACTIVE: sufficient receipts accumulated
  ACTIVE → DEGRADED: axiom violation or dispute pattern
  DORMANT → DEGRADED: genesis fields changed during dormancy (requires re-attestation)

Per AID (Agent Identity & Discovery, v1.2.0, Feb 2026): _agent.<domain> DNS TXT
for endpoint discovery. ATF _atf.<domain> for trust state. Compose, don't compete.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentState(Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    PROVISIONAL = "PROVISIONAL"
    DEGRADED = "DEGRADED"


class TransitionReason(Enum):
    INACTIVITY_TIMEOUT = "inactivity_timeout"
    NEW_RECEIPT = "new_receipt"
    SUFFICIENT_RECEIPTS = "sufficient_receipts"
    AXIOM_VIOLATION = "axiom_violation"
    DISPUTE_PATTERN = "dispute_pattern"
    GENESIS_CHANGED = "genesis_changed"
    MANUAL_REACTIVATION = "manual_reactivation"
    INITIAL_REGISTRATION = "initial_registration"


# SPEC_CONSTANTS (V1.2)
DORMANCY_THRESHOLD_DAYS = 90        # Inactive > 90d → DORMANT
PROVISIONAL_MIN_RECEIPTS = 5        # Need 5+ receipts to exit PROVISIONAL
DEGRADED_DISPUTE_RATE = 0.30        # >30% disputed → DEGRADED
DORMANCY_PRESERVE_DAYS = 365        # DORMANT preserved for 1 year before expiry
REACTIVATION_GRACE_RECEIPTS = 1     # Single new receipt reactivates from DORMANT


@dataclass
class AgentTrustRecord:
    agent_id: str
    genesis_hash: str
    state: AgentState = AgentState.PROVISIONAL
    total_receipts: int = 0
    confirmed_receipts: int = 0
    disputed_receipts: int = 0
    last_receipt_timestamp: float = 0.0
    last_state_change: float = 0.0
    dormancy_entered: Optional[float] = None
    genesis_changed_during_dormancy: bool = False
    state_history: list = field(default_factory=list)


@dataclass
class StateTransition:
    from_state: str
    to_state: str
    reason: str
    timestamp: float
    receipt_id: Optional[str] = None
    details: str = ""


def compute_state(record: AgentTrustRecord, now: float = None) -> tuple[AgentState, Optional[TransitionReason]]:
    """Determine correct state based on current conditions."""
    if now is None:
        now = time.time()
    
    days_since_receipt = (now - record.last_receipt_timestamp) / 86400 if record.last_receipt_timestamp > 0 else float('inf')
    dispute_rate = record.disputed_receipts / max(record.total_receipts, 1)
    
    # Check for DEGRADED conditions (highest priority)
    if dispute_rate > DEGRADED_DISPUTE_RATE and record.total_receipts >= 10:
        return AgentState.DEGRADED, TransitionReason.DISPUTE_PATTERN
    
    if record.genesis_changed_during_dormancy and record.state == AgentState.DORMANT:
        return AgentState.DEGRADED, TransitionReason.GENESIS_CHANGED
    
    # Check for PROVISIONAL (insufficient evidence)
    if record.total_receipts < PROVISIONAL_MIN_RECEIPTS:
        return AgentState.PROVISIONAL, TransitionReason.INITIAL_REGISTRATION
    
    # Check for DORMANT (inactive but verified)
    if days_since_receipt > DORMANCY_THRESHOLD_DAYS:
        # Only go DORMANT if previously ACTIVE (not from DEGRADED)
        if record.state in (AgentState.ACTIVE, AgentState.DORMANT):
            return AgentState.DORMANT, TransitionReason.INACTIVITY_TIMEOUT
        else:
            return record.state, None
    
    # Otherwise ACTIVE
    return AgentState.ACTIVE, TransitionReason.SUFFICIENT_RECEIPTS


def process_new_receipt(record: AgentTrustRecord, receipt_type: str = "CONFIRMED",
                        receipt_id: str = "") -> StateTransition:
    """Process a new receipt and potentially transition state."""
    now = time.time()
    old_state = record.state
    
    record.total_receipts += 1
    if receipt_type == "CONFIRMED":
        record.confirmed_receipts += 1
    elif receipt_type == "DISPUTED":
        record.disputed_receipts += 1
    record.last_receipt_timestamp = now
    
    # Reactivation from DORMANT
    if old_state == AgentState.DORMANT:
        if not record.genesis_changed_during_dormancy:
            record.state = AgentState.ACTIVE
            record.dormancy_entered = None
            return StateTransition(
                from_state=old_state.value,
                to_state=AgentState.ACTIVE.value,
                reason=TransitionReason.NEW_RECEIPT.value,
                timestamp=now,
                receipt_id=receipt_id,
                details="Reactivated from DORMANT. No re-attestation needed."
            )
        else:
            record.state = AgentState.DEGRADED
            return StateTransition(
                from_state=old_state.value,
                to_state=AgentState.DEGRADED.value,
                reason=TransitionReason.GENESIS_CHANGED.value,
                timestamp=now,
                receipt_id=receipt_id,
                details="Genesis changed during dormancy. Re-attestation required."
            )
    
    new_state, reason = compute_state(record, now)
    if new_state != old_state:
        record.state = new_state
        record.last_state_change = now
        return StateTransition(
            from_state=old_state.value,
            to_state=new_state.value,
            reason=reason.value if reason else "state_update",
            timestamp=now,
            receipt_id=receipt_id
        )
    
    return StateTransition(
        from_state=old_state.value,
        to_state=old_state.value,
        reason="no_change",
        timestamp=now,
        receipt_id=receipt_id
    )


def check_dormancy_expiry(record: AgentTrustRecord, now: float = None) -> Optional[str]:
    """Check if DORMANT state has expired (agent should be removed from registry)."""
    if now is None:
        now = time.time()
    
    if record.state != AgentState.DORMANT or record.dormancy_entered is None:
        return None
    
    days_dormant = (now - record.dormancy_entered) / 86400
    if days_dormant > DORMANCY_PRESERVE_DAYS:
        return f"EXPIRED: dormant for {days_dormant:.0f} days (limit: {DORMANCY_PRESERVE_DAYS}d). Remove from active registry."
    
    return f"PRESERVED: dormant for {days_dormant:.0f} days ({DORMANCY_PRESERVE_DAYS - days_dormant:.0f}d remaining)"


def fleet_dormancy_audit(records: list[AgentTrustRecord]) -> dict:
    """Audit fleet for dormancy distribution."""
    states = {}
    for r in records:
        states[r.state.value] = states.get(r.state.value, 0) + 1
    
    dormant = [r for r in records if r.state == AgentState.DORMANT]
    provisional = [r for r in records if r.state == AgentState.PROVISIONAL]
    
    # Key metric: how many PROVISIONAL would be DORMANT if we had the state?
    misclassified = [r for r in provisional if r.total_receipts >= PROVISIONAL_MIN_RECEIPTS]
    
    return {
        "total_agents": len(records),
        "state_distribution": states,
        "dormant_count": len(dormant),
        "provisional_count": len(provisional),
        "misclassified_provisional": len(misclassified),
        "health": "CLEAN" if not misclassified else f"MISCLASSIFIED: {len(misclassified)} agents"
    }


# === Scenarios ===

def scenario_active_to_dormant():
    """Agent goes idle — transitions to DORMANT, not PROVISIONAL."""
    print("=== Scenario: ACTIVE → DORMANT (Inactivity) ===")
    now = time.time()
    
    record = AgentTrustRecord(
        agent_id="kit_fox",
        genesis_hash="abc123",
        state=AgentState.ACTIVE,
        total_receipts=50,
        confirmed_receipts=47,
        disputed_receipts=1,
        last_receipt_timestamp=now - 86400 * 100,  # 100 days ago
        last_state_change=now - 86400 * 100
    )
    
    new_state, reason = compute_state(record, now)
    print(f"  Agent: {record.agent_id} ({record.total_receipts} receipts, {record.confirmed_receipts} confirmed)")
    print(f"  Last receipt: 100 days ago")
    print(f"  Current state: {record.state.value} → Computed: {new_state.value}")
    print(f"  Reason: {reason.value if reason else 'none'}")
    print(f"  Key: DORMANT preserves identity. PROVISIONAL would lose trust history.")
    print()


def scenario_dormant_reactivation():
    """DORMANT agent receives new receipt — reactivates without re-attestation."""
    print("=== Scenario: DORMANT → ACTIVE (Reactivation) ===")
    now = time.time()
    
    record = AgentTrustRecord(
        agent_id="seasonal_agent",
        genesis_hash="def456",
        state=AgentState.DORMANT,
        total_receipts=30,
        confirmed_receipts=28,
        disputed_receipts=0,
        last_receipt_timestamp=now - 86400 * 120,
        dormancy_entered=now - 86400 * 30
    )
    
    transition = process_new_receipt(record, "CONFIRMED", "receipt_reactivate_001")
    print(f"  Agent: {record.agent_id} (was DORMANT for 30 days)")
    print(f"  New receipt received")
    print(f"  Transition: {transition.from_state} → {transition.to_state}")
    print(f"  Reason: {transition.reason}")
    print(f"  Details: {transition.details}")
    print(f"  Re-attestation needed: NO")
    print()


def scenario_genesis_changed_during_dormancy():
    """Genesis modified while DORMANT — transitions to DEGRADED."""
    print("=== Scenario: DORMANT + Genesis Changed → DEGRADED ===")
    now = time.time()
    
    record = AgentTrustRecord(
        agent_id="migrated_agent",
        genesis_hash="ghi789",
        state=AgentState.DORMANT,
        total_receipts=20,
        confirmed_receipts=18,
        disputed_receipts=0,
        last_receipt_timestamp=now - 86400 * 150,
        dormancy_entered=now - 86400 * 60,
        genesis_changed_during_dormancy=True  # Model migration while dormant
    )
    
    transition = process_new_receipt(record, "CONFIRMED", "receipt_post_migration")
    print(f"  Agent: {record.agent_id} (DORMANT, genesis changed)")
    print(f"  Transition: {transition.from_state} → {transition.to_state}")
    print(f"  Reason: {transition.reason}")
    print(f"  Details: {transition.details}")
    print(f"  Key: Genesis change during dormancy = untrusted until re-verified")
    print()


def scenario_dormant_vs_provisional():
    """Show that DORMANT ≠ PROVISIONAL — different trust semantics."""
    print("=== Scenario: DORMANT vs PROVISIONAL (Disambiguation) ===")
    now = time.time()
    
    dormant = AgentTrustRecord(
        agent_id="trusted_but_idle",
        genesis_hash="jkl012",
        state=AgentState.DORMANT,
        total_receipts=100,
        confirmed_receipts=95,
        last_receipt_timestamp=now - 86400 * 180,
        dormancy_entered=now - 86400 * 90
    )
    
    provisional = AgentTrustRecord(
        agent_id="new_unknown",
        genesis_hash="mno345",
        state=AgentState.PROVISIONAL,
        total_receipts=2,
        confirmed_receipts=2,
        last_receipt_timestamp=now - 86400 * 5
    )
    
    print(f"  DORMANT agent: {dormant.total_receipts} receipts, {dormant.confirmed_receipts} confirmed, idle 180 days")
    print(f"  PROVISIONAL agent: {provisional.total_receipts} receipts, {provisional.confirmed_receipts} confirmed, active 5 days ago")
    print()
    print(f"  Without DORMANT state: BOTH look like PROVISIONAL (wrong!)")
    print(f"  With DORMANT state: trusted_but_idle preserves reputation history")
    print(f"  Reactivation cost: DORMANT=1 receipt, PROVISIONAL=5 receipts")
    print(f"  HTTP parallel: DORMANT=304 Not Modified, PROVISIONAL=401 Unauthorized")
    print()


def scenario_fleet_audit():
    """Fleet-level dormancy audit."""
    print("=== Scenario: Fleet Dormancy Audit ===")
    now = time.time()
    
    records = [
        AgentTrustRecord("active_1", "h1", AgentState.ACTIVE, 50, 48, 0, now - 86400),
        AgentTrustRecord("active_2", "h2", AgentState.ACTIVE, 30, 28, 1, now - 86400 * 3),
        AgentTrustRecord("dormant_1", "h3", AgentState.DORMANT, 80, 75, 2, now - 86400 * 120,
                        dormancy_entered=now - 86400 * 30),
        AgentTrustRecord("dormant_2", "h4", AgentState.DORMANT, 40, 38, 0, now - 86400 * 200,
                        dormancy_entered=now - 86400 * 110),
        AgentTrustRecord("provisional_1", "h5", AgentState.PROVISIONAL, 3, 3, 0, now - 86400 * 2),
        AgentTrustRecord("provisional_2", "h6", AgentState.PROVISIONAL, 1, 1, 0, now - 86400),
        AgentTrustRecord("degraded_1", "h7", AgentState.DEGRADED, 20, 10, 8, now - 86400 * 5),
    ]
    
    audit = fleet_dormancy_audit(records)
    print(f"  Total agents: {audit['total_agents']}")
    print(f"  Distribution: {audit['state_distribution']}")
    print(f"  Dormant: {audit['dormant_count']} (identity preserved)")
    print(f"  Provisional: {audit['provisional_count']} (building trust)")
    print(f"  Health: {audit['health']}")
    
    # Check expiry
    for r in records:
        if r.state == AgentState.DORMANT:
            expiry = check_dormancy_expiry(r, now)
            print(f"  {r.agent_id}: {expiry}")
    print()


if __name__ == "__main__":
    print("Dormancy State Manager — ATF V1.2 DORMANT State")
    print("Per santaclawd: idle ≠ bad. DORMANT ≠ PROVISIONAL.")
    print("=" * 60)
    print()
    
    scenario_active_to_dormant()
    scenario_dormant_reactivation()
    scenario_genesis_changed_during_dormancy()
    scenario_dormant_vs_provisional()
    scenario_fleet_audit()
    
    print("=" * 60)
    print("KEY INSIGHT: DORMANT preserves identity and trust history.")
    print("HTTP 304 Not Modified: unchanged, just inactive.")
    print("Reactivation = 1 receipt, not full re-attestation.")
    print("Genesis change during dormancy = DEGRADED (re-verify).")
    print("AID (_agent) discovers endpoint. ATF (_atf) discovers trust.")
