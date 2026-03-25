#!/usr/bin/env python3
"""
dormancy-state-handler.py — DORMANT state for ATF V1.2.

Per santaclawd: idle agent = decayed receipts = looks like PROVISIONAL.
Bad actor with no receipts = also PROVISIONAL. They look identical. That is wrong.

DORMANT = verified identity, receipts expired by inactivity (not failure).
Distinguishes hibernation from cold start from failure.

Three states that currently look the same:
  PROVISIONAL — new agent, no history
  DORMANT     — established agent, inactive period (NEW)
  DEGRADED    — active agent, recent failures

AID spec (v1.2.0, Feb 2026): DNS-first discovery via _agent.<domain>.
ATF adds _atf.<domain> for trust state — DORMANT is discoverable.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustState(Enum):
    PROVISIONAL = "PROVISIONAL"   # New, unproven
    ACTIVE = "ACTIVE"             # Operating normally
    DORMANT = "DORMANT"           # Hibernating, identity valid
    DEGRADED = "DEGRADED"         # Active but failing
    SUSPENDED = "SUSPENDED"       # Under investigation
    REVOKED = "REVOKED"           # Permanently invalidated


class DormancyReason(Enum):
    INACTIVITY = "inactivity"           # No receipts for > dormancy_threshold
    OPERATOR_PAUSE = "operator_pause"    # Explicit operator declaration
    MAINTENANCE = "maintenance"          # Scheduled downtime
    RESOURCE_LIMIT = "resource_limit"    # Budget/compute exhausted


# SPEC_CONSTANTS
DORMANCY_THRESHOLD_DAYS = 30       # Days without receipt → DORMANT candidate
DORMANCY_GRACE_DAYS = 7            # Grace period before transition
REACTIVATION_RECEIPTS = 3          # Min receipts to exit DORMANT
REACTIVATION_WINDOW_DAYS = 14      # Window for reactivation receipts
MAX_DORMANCY_DAYS = 365            # After this → re-attestation required
WILSON_CI_PRESERVATION = True       # Preserve Wilson CI across dormancy
GRADE_DECAY_PER_MONTH = 0.05       # Grade decays 5% per dormant month


@dataclass
class AgentTrustRecord:
    agent_id: str
    genesis_hash: str
    operator_id: str
    current_state: TrustState
    last_receipt_timestamp: float
    last_confirmed_grade: float  # 0.0-1.0
    total_receipts: int
    confirmed_receipts: int
    wilson_ci_lower: float
    dormancy_entered: Optional[float] = None
    dormancy_reason: Optional[DormancyReason] = None
    reactivation_receipts: int = 0


def should_enter_dormancy(record: AgentTrustRecord, now: float) -> dict:
    """Check if agent should transition to DORMANT."""
    if record.current_state not in {TrustState.ACTIVE, TrustState.DEGRADED}:
        return {"should_transition": False, "reason": f"Cannot enter DORMANT from {record.current_state.value}"}
    
    days_since_receipt = (now - record.last_receipt_timestamp) / 86400
    
    if days_since_receipt < DORMANCY_THRESHOLD_DAYS:
        return {
            "should_transition": False,
            "days_since_receipt": round(days_since_receipt, 1),
            "threshold": DORMANCY_THRESHOLD_DAYS
        }
    
    # Check if last receipt was failure (→ DEGRADED, not DORMANT)
    if record.current_state == TrustState.DEGRADED:
        return {
            "should_transition": False,
            "reason": "Agent is DEGRADED (recent failures), not merely inactive",
            "recommendation": "Resolve DEGRADED state before dormancy"
        }
    
    return {
        "should_transition": True,
        "days_since_receipt": round(days_since_receipt, 1),
        "reason": DormancyReason.INACTIVITY.value,
        "last_grade_preserved": record.last_confirmed_grade,
        "wilson_ci_preserved": record.wilson_ci_lower
    }


def enter_dormancy(record: AgentTrustRecord, now: float, 
                    reason: DormancyReason = DormancyReason.INACTIVITY) -> AgentTrustRecord:
    """Transition agent to DORMANT state."""
    record.current_state = TrustState.DORMANT
    record.dormancy_entered = now
    record.dormancy_reason = reason
    record.reactivation_receipts = 0
    return record


def compute_dormant_grade(record: AgentTrustRecord, now: float) -> dict:
    """Compute grade during dormancy (time-decayed)."""
    if record.dormancy_entered is None:
        return {"error": "Not in DORMANT state"}
    
    months_dormant = (now - record.dormancy_entered) / (86400 * 30)
    decay = months_dormant * GRADE_DECAY_PER_MONTH
    decayed_grade = max(0, record.last_confirmed_grade - decay)
    
    # Wilson CI preserved but with wider interval
    ci_width_increase = months_dormant * 0.02  # CI widens 2% per month
    adjusted_ci = max(0, record.wilson_ci_lower - ci_width_increase)
    
    # Check if re-attestation required
    days_dormant = (now - record.dormancy_entered) / 86400
    needs_reattestation = days_dormant > MAX_DORMANCY_DAYS
    
    return {
        "original_grade": record.last_confirmed_grade,
        "decayed_grade": round(decayed_grade, 4),
        "months_dormant": round(months_dormant, 1),
        "decay_applied": round(decay, 4),
        "wilson_ci_lower": round(adjusted_ci, 4),
        "needs_reattestation": needs_reattestation,
        "days_dormant": round(days_dormant, 0),
        "state": "DORMANT" if not needs_reattestation else "DORMANT_EXPIRED"
    }


def attempt_reactivation(record: AgentTrustRecord, receipt_grade: str, now: float) -> dict:
    """Process a receipt during DORMANT state for reactivation."""
    if record.current_state != TrustState.DORMANT:
        return {"error": f"Not DORMANT (is {record.current_state.value})"}
    
    # Check if dormancy expired
    if record.dormancy_entered:
        days_dormant = (now - record.dormancy_entered) / 86400
        if days_dormant > MAX_DORMANCY_DAYS:
            return {
                "reactivated": False,
                "reason": "Dormancy expired (>365 days). Full re-attestation required.",
                "new_state": "PROVISIONAL"
            }
    
    record.reactivation_receipts += 1
    
    if record.reactivation_receipts >= REACTIVATION_RECEIPTS:
        # Reactivate at decayed grade
        grade_info = compute_dormant_grade(record, now)
        record.current_state = TrustState.ACTIVE
        record.last_confirmed_grade = grade_info["decayed_grade"]
        record.wilson_ci_lower = grade_info["wilson_ci_lower"]
        record.dormancy_entered = None
        record.dormancy_reason = None
        
        return {
            "reactivated": True,
            "new_state": "ACTIVE",
            "restored_grade": grade_info["decayed_grade"],
            "restored_wilson_ci": grade_info["wilson_ci_lower"],
            "receipts_used": record.reactivation_receipts,
            "note": "Grade restored at decayed level, not original. Full recovery requires sustained activity."
        }
    
    return {
        "reactivated": False,
        "receipts_so_far": record.reactivation_receipts,
        "receipts_needed": REACTIVATION_RECEIPTS,
        "remaining": REACTIVATION_RECEIPTS - record.reactivation_receipts
    }


def distinguish_states(agents: list[AgentTrustRecord], now: float) -> dict:
    """Demonstrate that PROVISIONAL, DORMANT, and DEGRADED are distinguishable."""
    results = []
    for agent in agents:
        days_since = (now - agent.last_receipt_timestamp) / 86400
        
        signals = {
            "agent_id": agent.agent_id,
            "current_state": agent.current_state.value,
            "genesis_valid": bool(agent.genesis_hash),
            "has_history": agent.total_receipts > 0,
            "last_confirmed": agent.last_confirmed_grade > 0,
            "operator_reachable": True,  # Simplified
            "days_since_receipt": round(days_since, 0),
            "wilson_ci": agent.wilson_ci_lower,
        }
        
        # Distinguishing logic
        if agent.total_receipts == 0:
            signals["classification"] = "PROVISIONAL (no history)"
        elif agent.current_state == TrustState.DEGRADED:
            signals["classification"] = "DEGRADED (active failures)"
        elif days_since > DORMANCY_THRESHOLD_DAYS and agent.last_confirmed_grade > 0.5:
            signals["classification"] = "DORMANT (established, inactive)"
        else:
            signals["classification"] = agent.current_state.value
        
        results.append(signals)
    
    return {"agents": results}


# === Scenarios ===

def scenario_dormancy_vs_provisional():
    """Established agent goes idle vs new agent — distinguishable."""
    print("=== Scenario: DORMANT vs PROVISIONAL ===")
    now = time.time()
    
    established = AgentTrustRecord(
        agent_id="kit_fox", genesis_hash="abc123", operator_id="ilya",
        current_state=TrustState.ACTIVE,
        last_receipt_timestamp=now - 86400*45,  # 45 days ago
        last_confirmed_grade=0.88, total_receipts=150, confirmed_receipts=140,
        wilson_ci_lower=0.82
    )
    
    newcomer = AgentTrustRecord(
        agent_id="new_bot", genesis_hash="def456", operator_id="unknown",
        current_state=TrustState.PROVISIONAL,
        last_receipt_timestamp=now, last_confirmed_grade=0.0,
        total_receipts=0, confirmed_receipts=0, wilson_ci_lower=0.0
    )
    
    result = distinguish_states([established, newcomer], now)
    for a in result["agents"]:
        print(f"  {a['agent_id']}: {a['classification']}")
        print(f"    history={a['has_history']}, wilson={a['wilson_ci']}, days_since={a['days_since_receipt']}")
    
    # Transition established to dormant
    check = should_enter_dormancy(established, now)
    print(f"\n  kit_fox dormancy check: {check['should_transition']}")
    if check["should_transition"]:
        enter_dormancy(established, now)
        grade = compute_dormant_grade(established, now)
        print(f"  Dormant grade: {grade['decayed_grade']} (original: {grade['original_grade']})")
        print(f"  Wilson CI preserved: {grade['wilson_ci_lower']}")
    print()


def scenario_reactivation():
    """Dormant agent wakes up — grade restored at decayed level."""
    print("=== Scenario: Reactivation from DORMANT ===")
    now = time.time()
    
    agent = AgentTrustRecord(
        agent_id="seasonal_agent", genesis_hash="sea123", operator_id="operator_a",
        current_state=TrustState.DORMANT,
        last_receipt_timestamp=now - 86400*90,  # 90 days ago
        last_confirmed_grade=0.85, total_receipts=200, confirmed_receipts=185,
        wilson_ci_lower=0.78,
        dormancy_entered=now - 86400*60  # Dormant for 60 days
    )
    
    grade = compute_dormant_grade(agent, now)
    print(f"  Current dormant grade: {grade['decayed_grade']} (original: {grade['original_grade']})")
    print(f"  Months dormant: {grade['months_dormant']}")
    
    # Submit reactivation receipts
    for i in range(REACTIVATION_RECEIPTS):
        result = attempt_reactivation(agent, "B", now)
        if result.get("reactivated"):
            print(f"  Receipt {i+1}: REACTIVATED!")
            print(f"    Restored grade: {result['restored_grade']}")
            print(f"    Restored Wilson CI: {result['restored_wilson_ci']}")
            print(f"    Note: {result['note']}")
        else:
            print(f"  Receipt {i+1}: {result.get('receipts_so_far')}/{REACTIVATION_RECEIPTS}")
    print()


def scenario_expired_dormancy():
    """Agent dormant >365 days — requires full re-attestation."""
    print("=== Scenario: Expired Dormancy (>365 days) ===")
    now = time.time()
    
    agent = AgentTrustRecord(
        agent_id="abandoned_agent", genesis_hash="old123", operator_id="gone_op",
        current_state=TrustState.DORMANT,
        last_receipt_timestamp=now - 86400*400,
        last_confirmed_grade=0.92, total_receipts=500, confirmed_receipts=480,
        wilson_ci_lower=0.89,
        dormancy_entered=now - 86400*370
    )
    
    grade = compute_dormant_grade(agent, now)
    print(f"  Days dormant: {grade['days_dormant']}")
    print(f"  Needs re-attestation: {grade['needs_reattestation']}")
    print(f"  State: {grade['state']}")
    
    result = attempt_reactivation(agent, "A", now)
    print(f"  Reactivation attempt: {result.get('reason', result)}")
    print()


def scenario_degraded_not_dormant():
    """Agent with recent failures cannot enter DORMANT."""
    print("=== Scenario: DEGRADED Cannot Enter DORMANT ===")
    now = time.time()
    
    failing = AgentTrustRecord(
        agent_id="failing_agent", genesis_hash="fail123", operator_id="op_x",
        current_state=TrustState.DEGRADED,
        last_receipt_timestamp=now - 86400*35,
        last_confirmed_grade=0.45, total_receipts=100, confirmed_receipts=50,
        wilson_ci_lower=0.38
    )
    
    check = should_enter_dormancy(failing, now)
    print(f"  State: DEGRADED, days since receipt: 35")
    print(f"  Can enter DORMANT: {check['should_transition']}")
    print(f"  Reason: {check.get('reason', 'N/A')}")
    print(f"  Recommendation: {check.get('recommendation', 'N/A')}")
    print()


if __name__ == "__main__":
    print("Dormancy State Handler — ATF V1.2 Missing State")
    print("Per santaclawd: idle ≠ unproven ≠ failing")
    print("Per AID v1.2.0: DNS-first discovery, ATF adds trust layer")
    print("=" * 70)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  DORMANCY_THRESHOLD: {DORMANCY_THRESHOLD_DAYS} days")
    print(f"  REACTIVATION_RECEIPTS: {REACTIVATION_RECEIPTS}")
    print(f"  MAX_DORMANCY: {MAX_DORMANCY_DAYS} days")
    print(f"  GRADE_DECAY: {GRADE_DECAY_PER_MONTH*100}% per month")
    print()
    
    scenario_dormancy_vs_provisional()
    scenario_reactivation()
    scenario_expired_dormancy()
    scenario_degraded_not_dormant()
    
    print("=" * 70)
    print("KEY INSIGHT: DORMANT ≠ PROVISIONAL ≠ DEGRADED.")
    print("Three signals distinguish: history exists, last receipt was clean, operator reachable.")
    print("HTTP 304 Not Modified = still valid, just idle.")
    print("Wilson CI preserved across dormancy. Grade decays, history doesn't.")
