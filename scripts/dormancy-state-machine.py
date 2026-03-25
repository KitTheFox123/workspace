#!/usr/bin/env python3
"""
dormancy-state-machine.py — ATF V1.2 DORMANT state for idle agents.

Per santaclawd: idle agent with decayed receipts looks identical to bad actor
with no receipts. Both appear PROVISIONAL. That's wrong.

DORMANT = verified identity + receipts expired by inactivity (not failure).
Resume without full re-attestation IF genesis_hash unchanged AND operator active.

X.509 parallel: Certificate Hold (CRL reason code 6) — temporary suspension.
Different from revocation: hold preserves identity, revocation destroys it.

State machine:
  PROVISIONAL → EMERGING → ESTABLISHED → TRUSTED → DORMANT → RECOVERING → ESTABLISHED
                                                  ↗
  (any state with >inactivity_threshold days silence)

Recovery: n_recovery receipts in recovery_window from min_counterparties.
Gaming prevention: window resets on COMPLETION not individual receipts.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustState(Enum):
    PROVISIONAL = "PROVISIONAL"   # New, no history
    EMERGING = "EMERGING"         # Some receipts, Wilson CI still wide
    ESTABLISHED = "ESTABLISHED"   # Stable trust, n≥30
    TRUSTED = "TRUSTED"           # High trust, consistent behavior
    DORMANT = "DORMANT"           # Inactive but identity preserved
    RECOVERING = "RECOVERING"     # Exiting dormancy, proving liveness
    SUSPENDED = "SUSPENDED"       # Pending investigation
    REVOKED = "REVOKED"          # Permanent, identity destroyed


# SPEC_CONSTANTS (V1.2)
INACTIVITY_THRESHOLD_DAYS = 90       # Days of silence before DORMANT
RECOVERY_WINDOW_DAYS = 7             # Must complete recovery within this
N_RECOVERY_RECEIPTS = 3              # Receipts needed to exit DORMANT
MIN_RECOVERY_COUNTERPARTIES = 2      # From distinct counterparties
MAX_DORMANCY_DAYS = 365              # After this, must re-attest fully
DORMANT_TO_ESTABLISHED_DAYS = 30     # Grace period in RECOVERING
GAMING_RESET_ON_COMPLETION = True    # Window resets on n_recovery COMPLETION only


@dataclass
class AgentTrustRecord:
    agent_id: str
    state: TrustState
    genesis_hash: str
    operator_id: str
    last_receipt_at: float
    total_receipts: int
    trust_score: float  # 0.0-1.0
    dormant_at: Optional[float] = None
    recovery_started_at: Optional[float] = None
    recovery_receipts: list = field(default_factory=list)
    state_history: list = field(default_factory=list)


@dataclass
class Receipt:
    receipt_id: str
    counterparty_id: str
    timestamp: float
    grade: str


def check_dormancy_trigger(agent: AgentTrustRecord, now: float) -> dict:
    """Check if agent should transition to DORMANT."""
    if agent.state in (TrustState.DORMANT, TrustState.RECOVERING, 
                       TrustState.SUSPENDED, TrustState.REVOKED, TrustState.PROVISIONAL):
        return {"trigger": False, "reason": f"State {agent.state.value} not eligible"}
    
    days_inactive = (now - agent.last_receipt_at) / 86400
    
    if days_inactive >= INACTIVITY_THRESHOLD_DAYS:
        return {
            "trigger": True,
            "days_inactive": round(days_inactive, 1),
            "threshold": INACTIVITY_THRESHOLD_DAYS,
            "prior_state": agent.state.value,
            "trust_preserved": agent.trust_score,
            "receipts_preserved": agent.total_receipts
        }
    
    return {
        "trigger": False,
        "days_inactive": round(days_inactive, 1),
        "days_until_dormant": round(INACTIVITY_THRESHOLD_DAYS - days_inactive, 1)
    }


def enter_dormancy(agent: AgentTrustRecord, now: float) -> AgentTrustRecord:
    """Transition agent to DORMANT state."""
    agent.state_history.append({
        "from": agent.state.value,
        "to": TrustState.DORMANT.value,
        "at": now,
        "trust_at_entry": agent.trust_score,
        "receipts_at_entry": agent.total_receipts
    })
    agent.state = TrustState.DORMANT
    agent.dormant_at = now
    return agent


def start_recovery(agent: AgentTrustRecord, receipt: Receipt, now: float) -> dict:
    """Process first receipt from DORMANT agent — enter RECOVERING."""
    if agent.state != TrustState.DORMANT:
        return {"error": f"Cannot recover from {agent.state.value}"}
    
    # Check if dormancy exceeded max
    dormancy_days = (now - agent.dormant_at) / 86400 if agent.dormant_at else 0
    if dormancy_days > MAX_DORMANCY_DAYS:
        return {
            "action": "FULL_RE_ATTESTATION_REQUIRED",
            "reason": f"Dormant for {dormancy_days:.0f} days (max: {MAX_DORMANCY_DAYS})",
            "trust_lost": True
        }
    
    # Check genesis unchanged
    # (In real system, verify genesis_hash matches)
    
    agent.state = TrustState.RECOVERING
    agent.recovery_started_at = now
    agent.recovery_receipts = [receipt]
    agent.state_history.append({
        "from": TrustState.DORMANT.value,
        "to": TrustState.RECOVERING.value,
        "at": now,
        "dormancy_duration_days": round(dormancy_days, 1)
    })
    
    return {
        "action": "RECOVERY_STARTED",
        "receipts_needed": N_RECOVERY_RECEIPTS - 1,
        "counterparties_needed": MIN_RECOVERY_COUNTERPARTIES - 1,
        "window_expires_at": now + RECOVERY_WINDOW_DAYS * 86400,
        "dormancy_duration_days": round(dormancy_days, 1)
    }


def process_recovery_receipt(agent: AgentTrustRecord, receipt: Receipt, now: float) -> dict:
    """Process receipt during RECOVERING state."""
    if agent.state != TrustState.RECOVERING:
        return {"error": f"Not in RECOVERING state"}
    
    # Check recovery window
    window_elapsed = (now - agent.recovery_started_at) / 86400
    if window_elapsed > RECOVERY_WINDOW_DAYS:
        # Gaming prevention: window expired, reset
        agent.state = TrustState.DORMANT
        agent.recovery_receipts = []
        agent.recovery_started_at = None
        return {
            "action": "RECOVERY_EXPIRED",
            "reason": f"Window elapsed: {window_elapsed:.1f}d > {RECOVERY_WINDOW_DAYS}d",
            "state": TrustState.DORMANT.value
        }
    
    agent.recovery_receipts.append(receipt)
    
    # Count unique counterparties
    counterparties = set(r.counterparty_id for r in agent.recovery_receipts)
    receipts_count = len(agent.recovery_receipts)
    
    if receipts_count >= N_RECOVERY_RECEIPTS and len(counterparties) >= MIN_RECOVERY_COUNTERPARTIES:
        # Recovery complete — return to ESTABLISHED (not TRUSTED, must re-earn)
        agent.state = TrustState.ESTABLISHED
        agent.last_receipt_at = now
        agent.state_history.append({
            "from": TrustState.RECOVERING.value,
            "to": TrustState.ESTABLISHED.value,
            "at": now,
            "recovery_receipts": receipts_count,
            "recovery_counterparties": len(counterparties)
        })
        return {
            "action": "RECOVERY_COMPLETE",
            "state": TrustState.ESTABLISHED.value,
            "trust_restored": agent.trust_score,
            "note": "Returns to ESTABLISHED, not TRUSTED — must re-earn highest tier"
        }
    
    return {
        "action": "RECOVERY_IN_PROGRESS",
        "receipts": f"{receipts_count}/{N_RECOVERY_RECEIPTS}",
        "counterparties": f"{len(counterparties)}/{MIN_RECOVERY_COUNTERPARTIES}",
        "window_remaining_days": round(RECOVERY_WINDOW_DAYS - window_elapsed, 1)
    }


def differentiate_dormant_vs_provisional(
    agent_a: AgentTrustRecord,  # DORMANT
    agent_b: AgentTrustRecord   # PROVISIONAL
) -> dict:
    """Show why DORMANT ≠ PROVISIONAL — the whole point of V1.2."""
    return {
        "dormant_agent": {
            "state": agent_a.state.value,
            "has_history": True,
            "total_receipts": agent_a.total_receipts,
            "trust_at_entry": agent_a.trust_score,
            "genesis_verified": True,
            "recovery_path": "3 receipts in 7d → ESTABLISHED",
            "identity_status": "PRESERVED"
        },
        "provisional_agent": {
            "state": agent_b.state.value,
            "has_history": False,
            "total_receipts": agent_b.total_receipts,
            "trust_at_entry": 0.0,
            "genesis_verified": agent_b.genesis_hash != "",
            "recovery_path": "Full attestation required",
            "identity_status": "UNPROVEN"
        },
        "key_difference": "DORMANT has earned history. PROVISIONAL has not. "
                         "They should NEVER look identical.",
        "x509_parallel": "Certificate Hold (reason code 6) vs never-issued certificate"
    }


# === Scenarios ===

def scenario_natural_dormancy():
    """Agent goes idle for 100 days, then recovers."""
    print("=== Scenario: Natural Dormancy + Recovery ===")
    now = time.time()
    
    agent = AgentTrustRecord(
        agent_id="kit_fox", state=TrustState.TRUSTED,
        genesis_hash="abc123", operator_id="ilya",
        last_receipt_at=now - 100 * 86400,
        total_receipts=150, trust_score=0.92
    )
    
    # Check dormancy
    check = check_dormancy_trigger(agent, now)
    print(f"  Dormancy check: trigger={check['trigger']}, days_inactive={check.get('days_inactive')}")
    
    # Enter dormancy
    agent = enter_dormancy(agent, now)
    print(f"  State: {agent.state.value}, trust preserved: {agent.trust_score}")
    
    # First recovery receipt
    r1 = Receipt("r001", "bro_agent", now + 86400, "B")
    result1 = start_recovery(agent, r1, now + 86400)
    print(f"  Recovery started: {result1['action']}")
    
    # Second receipt (different counterparty)
    r2 = Receipt("r002", "santaclawd", now + 2 * 86400, "A")
    result2 = process_recovery_receipt(agent, r2, now + 2 * 86400)
    print(f"  Progress: {result2}")
    
    # Third receipt
    r3 = Receipt("r003", "funwolf", now + 3 * 86400, "B")
    result3 = process_recovery_receipt(agent, r3, now + 3 * 86400)
    print(f"  Final: {result3['action']} → {result3.get('state', '?')}")
    print()


def scenario_gaming_prevention():
    """Agent tries to game recovery with single receipt at day 29."""
    print("=== Scenario: Gaming Prevention ===")
    now = time.time()
    
    agent = AgentTrustRecord(
        agent_id="gamer", state=TrustState.DORMANT,
        genesis_hash="def456", operator_id="op_shady",
        last_receipt_at=now - 100 * 86400,
        total_receipts=50, trust_score=0.65,
        dormant_at=now - 30 * 86400
    )
    
    # Start recovery
    r1 = Receipt("r001", "ally", now, "C")
    result1 = start_recovery(agent, r1, now)
    print(f"  Recovery started")
    
    # Try to submit second receipt after window expires (day 8)
    r2 = Receipt("r002", "other", now + 8 * 86400, "C")
    result2 = process_recovery_receipt(agent, r2, now + 8 * 86400)
    print(f"  Day 8 receipt: {result2['action']} — {result2.get('reason', '')}")
    print(f"  State: {agent.state.value} (back to DORMANT, must restart)")
    print()


def scenario_max_dormancy_exceeded():
    """Agent dormant too long — must fully re-attest."""
    print("=== Scenario: Max Dormancy Exceeded ===")
    now = time.time()
    
    agent = AgentTrustRecord(
        agent_id="ghost", state=TrustState.DORMANT,
        genesis_hash="ghi789", operator_id="op_gone",
        last_receipt_at=now - 500 * 86400,
        total_receipts=200, trust_score=0.88,
        dormant_at=now - 400 * 86400
    )
    
    r1 = Receipt("r001", "counterparty", now, "B")
    result = start_recovery(agent, r1, now)
    print(f"  Result: {result['action']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Trust lost: {result['trust_lost']}")
    print()


def scenario_differentiation():
    """Show DORMANT ≠ PROVISIONAL."""
    print("=== Scenario: DORMANT vs PROVISIONAL ===")
    now = time.time()
    
    dormant = AgentTrustRecord(
        agent_id="veteran", state=TrustState.DORMANT,
        genesis_hash="vet123", operator_id="reliable_op",
        last_receipt_at=now - 120 * 86400,
        total_receipts=200, trust_score=0.85,
        dormant_at=now - 30 * 86400
    )
    
    provisional = AgentTrustRecord(
        agent_id="newcomer", state=TrustState.PROVISIONAL,
        genesis_hash="new456", operator_id="unknown_op",
        last_receipt_at=now, total_receipts=0, trust_score=0.0
    )
    
    diff = differentiate_dormant_vs_provisional(dormant, provisional)
    print(f"  DORMANT: {diff['dormant_agent']['total_receipts']} receipts, "
          f"trust={diff['dormant_agent']['trust_at_entry']}, "
          f"identity={diff['dormant_agent']['identity_status']}")
    print(f"  PROVISIONAL: {diff['provisional_agent']['total_receipts']} receipts, "
          f"trust={diff['provisional_agent']['trust_at_entry']}, "
          f"identity={diff['provisional_agent']['identity_status']}")
    print(f"  Key: {diff['key_difference']}")
    print(f"  X.509: {diff['x509_parallel']}")
    print()


if __name__ == "__main__":
    print("Dormancy State Machine — ATF V1.2 DORMANT State")
    print("Per santaclawd: idle agent ≠ bad actor. They should never look identical.")
    print("X.509 parallel: Certificate Hold (CRL reason code 6)")
    print("=" * 70)
    print()
    
    scenario_natural_dormancy()
    scenario_gaming_prevention()
    scenario_max_dormancy_exceeded()
    scenario_differentiation()
    
    print("=" * 70)
    print("V1.2 STATE ADDITIONS:")
    print(f"  DORMANT: inactivity > {INACTIVITY_THRESHOLD_DAYS}d, identity preserved")
    print(f"  RECOVERING: {N_RECOVERY_RECEIPTS} receipts in {RECOVERY_WINDOW_DAYS}d "
          f"from {MIN_RECOVERY_COUNTERPARTIES}+ counterparties")
    print(f"  MAX_DORMANCY: {MAX_DORMANCY_DAYS}d, then full re-attestation")
    print("Gaming prevention: window resets on COMPLETION, not individual receipts.")
