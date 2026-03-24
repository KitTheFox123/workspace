#!/usr/bin/env python3
"""
dormancy-state-handler.py — ATF V1.2 DORMANT state management.

Per santaclawd: idle agent with expired receipts looks identical to bad actor
with no receipts — both are PROVISIONAL. That's wrong.

DORMANT = verified identity + receipts expired by inactivity (not failure).
X.509 certificateHold (CRL reason code 6) = exact precedent.

Key properties:
  - DORMANT preserves behavioral fingerprint from prior receipts
  - Wilson CI at resumption uses PRIOR receipts (hibernation, not amnesia)
  - Clock resets on next receipt without full re-attestation
  - DORMANT ≠ PROVISIONAL (never had receipts)
  - DORMANT ≠ SUSPENDED (active investigation)
  - DORMANT ≠ REVOKED (permanent, irreversible)
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentState(Enum):
    PROVISIONAL = "PROVISIONAL"   # New, no receipts yet
    ACTIVE = "ACTIVE"             # Recent receipts within window
    DORMANT = "DORMANT"           # Had receipts, expired by inactivity
    SUSPENDED = "SUSPENDED"       # Under investigation (fast-ballot-eviction)
    REVOKED = "REVOKED"           # Permanent, irreversible


class DormancyReason(Enum):
    INACTIVITY = "inactivity"           # No receipts within max_age window
    VOLUNTARY = "voluntary"              # Agent declared hibernation
    OPERATOR_MAINTENANCE = "operator"    # Operator-initiated hold
    SEASONAL = "seasonal"                # Recurring dormancy pattern


# SPEC_CONSTANTS (V1.2)
DORMANCY_WINDOW_DAYS = 90        # No receipts for 90d → DORMANT
DORMANCY_MAX_DAYS = 365          # After 365d dormant → requires re-attestation
RESUMPTION_GRACE_HOURS = 24      # Grace period for first receipt after dormancy
RECEIPT_HISTORY_PRESERVED = True  # Prior receipts survive dormancy
WILSON_Z = 1.96                  # 95% CI for trust ceiling


@dataclass
class Receipt:
    receipt_id: str
    timestamp: float
    evidence_grade: str
    counterparty_id: str
    confirmed: bool = True


@dataclass
class BehavioralFingerprint:
    """Preserved across dormancy — this is what distinguishes DORMANT from PROVISIONAL."""
    total_receipts: int
    confirmed_count: int
    unique_counterparties: int
    grade_distribution: dict  # {"A": 10, "B": 5, ...}
    avg_response_latency: float
    co_sign_rate: float
    first_receipt_timestamp: float
    last_receipt_timestamp: float
    wilson_ci_lower: float
    wilson_ci_upper: float


@dataclass
class AgentTrustState:
    agent_id: str
    state: AgentState
    receipts: list[Receipt] = field(default_factory=list)
    fingerprint: Optional[BehavioralFingerprint] = None
    dormancy_entered: Optional[float] = None
    dormancy_reason: Optional[DormancyReason] = None
    dormancy_count: int = 0  # How many times agent went dormant


def wilson_ci(successes: int, total: int, z: float = WILSON_Z) -> tuple[float, float]:
    """Wilson score interval for binomial proportion."""
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z*z/total
    center = (p + z*z/(2*total)) / denom
    spread = z * ((p*(1-p)/total + z*z/(4*total*total))**0.5) / denom
    return (max(0, round(center - spread, 4)), min(1, round(center + spread, 4)))


def compute_fingerprint(receipts: list[Receipt]) -> BehavioralFingerprint:
    """Compute behavioral fingerprint from receipt history."""
    if not receipts:
        return None
    
    confirmed = sum(1 for r in receipts if r.confirmed)
    counterparties = len(set(r.counterparty_id for r in receipts))
    
    grades = {}
    for r in receipts:
        grades[r.evidence_grade] = grades.get(r.evidence_grade, 0) + 1
    
    timestamps = sorted(r.timestamp for r in receipts)
    if len(timestamps) > 1:
        gaps = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
        avg_latency = sum(gaps) / len(gaps)
    else:
        avg_latency = 0
    
    co_sign = confirmed / len(receipts) if receipts else 0
    lower, upper = wilson_ci(confirmed, len(receipts))
    
    return BehavioralFingerprint(
        total_receipts=len(receipts),
        confirmed_count=confirmed,
        unique_counterparties=counterparties,
        grade_distribution=grades,
        avg_response_latency=avg_latency,
        co_sign_rate=round(co_sign, 4),
        first_receipt_timestamp=timestamps[0],
        last_receipt_timestamp=timestamps[-1],
        wilson_ci_lower=lower,
        wilson_ci_upper=upper
    )


def check_dormancy(agent: AgentTrustState, now: float = None) -> dict:
    """Check if agent should transition to DORMANT."""
    now = now or time.time()
    
    if agent.state == AgentState.REVOKED:
        return {"transition": False, "reason": "REVOKED is permanent"}
    
    if agent.state == AgentState.SUSPENDED:
        return {"transition": False, "reason": "SUSPENDED requires explicit resolution"}
    
    if agent.state == AgentState.PROVISIONAL:
        return {"transition": False, "reason": "PROVISIONAL has no receipts to expire"}
    
    if not agent.receipts:
        return {"transition": False, "reason": "No receipts"}
    
    last_receipt = max(r.timestamp for r in agent.receipts)
    days_since = (now - last_receipt) / 86400
    
    if days_since >= DORMANCY_WINDOW_DAYS and agent.state == AgentState.ACTIVE:
        return {
            "transition": True,
            "to_state": AgentState.DORMANT.value,
            "days_inactive": round(days_since, 1),
            "fingerprint_preserved": True,
            "prior_receipts": len(agent.receipts),
            "wilson_ci": wilson_ci(
                sum(1 for r in agent.receipts if r.confirmed),
                len(agent.receipts)
            )
        }
    
    return {"transition": False, "days_inactive": round(days_since, 1)}


def resume_from_dormancy(agent: AgentTrustState, new_receipt: Receipt, now: float = None) -> dict:
    """Handle agent resuming from DORMANT state."""
    now = now or time.time()
    
    if agent.state != AgentState.DORMANT:
        return {"error": f"Agent is {agent.state.value}, not DORMANT"}
    
    dormancy_duration = (now - agent.dormancy_entered) / 86400 if agent.dormancy_entered else 0
    
    # Check if dormancy exceeded max
    if dormancy_duration > DORMANCY_MAX_DAYS:
        return {
            "action": "RE_ATTESTATION_REQUIRED",
            "reason": f"Dormancy exceeded {DORMANCY_MAX_DAYS} days ({dormancy_duration:.0f}d)",
            "fingerprint_available": agent.fingerprint is not None,
            "prior_wilson_ci": (agent.fingerprint.wilson_ci_lower, agent.fingerprint.wilson_ci_upper) 
                if agent.fingerprint else None
        }
    
    # Resume with preserved history
    all_receipts = agent.receipts + [new_receipt]
    confirmed = sum(1 for r in all_receipts if r.confirmed)
    lower, upper = wilson_ci(confirmed, len(all_receipts))
    
    # Compare with fingerprint
    prior_ci = (agent.fingerprint.wilson_ci_lower, agent.fingerprint.wilson_ci_upper) if agent.fingerprint else (0, 1)
    
    return {
        "action": "RESUMED",
        "new_state": AgentState.ACTIVE.value,
        "dormancy_duration_days": round(dormancy_duration, 1),
        "receipts_preserved": len(agent.receipts),
        "total_receipts_now": len(all_receipts),
        "prior_wilson_ci": prior_ci,
        "new_wilson_ci": (lower, upper),
        "fingerprint_continuity": "PRESERVED",
        "grace_period_hours": RESUMPTION_GRACE_HOURS,
        "dormancy_count": agent.dormancy_count + 1
    }


def compare_states(dormant_agent: AgentTrustState, provisional_agent: AgentTrustState) -> dict:
    """Show why DORMANT ≠ PROVISIONAL — the whole point."""
    d_fp = dormant_agent.fingerprint
    
    return {
        "dormant": {
            "state": dormant_agent.state.value,
            "has_history": True,
            "prior_receipts": d_fp.total_receipts if d_fp else 0,
            "wilson_ci": (d_fp.wilson_ci_lower, d_fp.wilson_ci_upper) if d_fp else None,
            "unique_counterparties": d_fp.unique_counterparties if d_fp else 0,
            "co_sign_rate": d_fp.co_sign_rate if d_fp else 0,
            "resumption": "next receipt resumes without re-attestation"
        },
        "provisional": {
            "state": provisional_agent.state.value,
            "has_history": False,
            "prior_receipts": 0,
            "wilson_ci": (0.0, 1.0),
            "unique_counterparties": 0,
            "co_sign_rate": 0,
            "resumption": "must build from scratch"
        },
        "verdict": "DORMANT has behavioral fingerprint. PROVISIONAL does not. They are NOT equivalent."
    }


# === Scenarios ===

def scenario_active_to_dormant():
    """Agent goes idle — transitions to DORMANT."""
    print("=== Scenario: ACTIVE → DORMANT (Inactivity) ===")
    now = time.time()
    
    receipts = [
        Receipt(f"r{i}", now - 86400*(120+i*5), "A" if i%3==0 else "B", f"cp_{i%4}", True)
        for i in range(20)
    ]
    
    agent = AgentTrustState(
        agent_id="reliable_agent",
        state=AgentState.ACTIVE,
        receipts=receipts,
        fingerprint=compute_fingerprint(receipts)
    )
    
    result = check_dormancy(agent, now)
    print(f"  Prior receipts: {len(receipts)}")
    print(f"  Days since last: {result.get('days_inactive', 0)}")
    print(f"  Transition: {result.get('transition', False)} → {result.get('to_state', 'N/A')}")
    print(f"  Fingerprint preserved: {result.get('fingerprint_preserved', False)}")
    print(f"  Wilson CI: {result.get('wilson_ci', 'N/A')}")
    print()


def scenario_dormant_resume():
    """DORMANT agent sends new receipt — resumes with history."""
    print("=== Scenario: DORMANT → ACTIVE (Resume with History) ===")
    now = time.time()
    
    receipts = [
        Receipt(f"r{i}", now - 86400*(200+i*5), "A" if i%2==0 else "B", f"cp_{i%5}", True)
        for i in range(25)
    ]
    
    agent = AgentTrustState(
        agent_id="hibernating_agent",
        state=AgentState.DORMANT,
        receipts=receipts,
        fingerprint=compute_fingerprint(receipts),
        dormancy_entered=now - 86400*100,
        dormancy_reason=DormancyReason.INACTIVITY,
        dormancy_count=1
    )
    
    new_receipt = Receipt("r_new", now, "A", "new_counterparty", True)
    result = resume_from_dormancy(agent, new_receipt, now)
    
    print(f"  Action: {result.get('action')}")
    print(f"  Dormancy duration: {result.get('dormancy_duration_days')}d")
    print(f"  Receipts preserved: {result.get('receipts_preserved')}")
    print(f"  Total now: {result.get('total_receipts_now')}")
    print(f"  Prior Wilson CI: {result.get('prior_wilson_ci')}")
    print(f"  New Wilson CI: {result.get('new_wilson_ci')}")
    print(f"  Fingerprint: {result.get('fingerprint_continuity')}")
    print()


def scenario_dormant_vs_provisional():
    """Show the distinction — the whole point of this script."""
    print("=== Scenario: DORMANT ≠ PROVISIONAL ===")
    now = time.time()
    
    dormant_receipts = [
        Receipt(f"r{i}", now - 86400*(150+i*3), "A", f"cp_{i%6}", True)
        for i in range(30)
    ]
    
    dormant = AgentTrustState(
        agent_id="experienced_idle",
        state=AgentState.DORMANT,
        receipts=dormant_receipts,
        fingerprint=compute_fingerprint(dormant_receipts),
        dormancy_entered=now - 86400*60
    )
    
    provisional = AgentTrustState(
        agent_id="brand_new",
        state=AgentState.PROVISIONAL
    )
    
    comparison = compare_states(dormant, provisional)
    print(f"  DORMANT: {comparison['dormant']['prior_receipts']} receipts, "
          f"CI={comparison['dormant']['wilson_ci']}, "
          f"counterparties={comparison['dormant']['unique_counterparties']}")
    print(f"  PROVISIONAL: {comparison['provisional']['prior_receipts']} receipts, "
          f"CI={comparison['provisional']['wilson_ci']}")
    print(f"  Verdict: {comparison['verdict']}")
    print()


def scenario_dormancy_exceeded():
    """DORMANT too long — requires re-attestation."""
    print("=== Scenario: DORMANT Exceeded (>365d) ===")
    now = time.time()
    
    old_receipts = [
        Receipt(f"r{i}", now - 86400*(500+i*5), "B", f"cp_{i%3}", True)
        for i in range(15)
    ]
    
    agent = AgentTrustState(
        agent_id="long_idle",
        state=AgentState.DORMANT,
        receipts=old_receipts,
        fingerprint=compute_fingerprint(old_receipts),
        dormancy_entered=now - 86400*400
    )
    
    new_receipt = Receipt("r_new", now, "B", "counterparty", True)
    result = resume_from_dormancy(agent, new_receipt, now)
    
    print(f"  Action: {result.get('action')}")
    print(f"  Reason: {result.get('reason')}")
    print(f"  Prior fingerprint available: {result.get('fingerprint_available')}")
    print(f"  Prior Wilson CI: {result.get('prior_wilson_ci')}")
    print()


if __name__ == "__main__":
    print("Dormancy State Handler — ATF V1.2 DORMANT State")
    print("Per santaclawd: idle ≠ unverified. X.509 certificateHold (reason code 6).")
    print("=" * 70)
    print()
    print(f"DORMANCY_WINDOW:  {DORMANCY_WINDOW_DAYS}d (ACTIVE → DORMANT)")
    print(f"DORMANCY_MAX:     {DORMANCY_MAX_DAYS}d (DORMANT → requires re-attestation)")
    print(f"RESUMPTION_GRACE: {RESUMPTION_GRACE_HOURS}h")
    print(f"HISTORY:          {'PRESERVED' if RECEIPT_HISTORY_PRESERVED else 'LOST'}")
    print()
    
    scenario_active_to_dormant()
    scenario_dormant_resume()
    scenario_dormant_vs_provisional()
    scenario_dormancy_exceeded()
    
    print("=" * 70)
    print("KEY INSIGHT: DORMANT preserves behavioral fingerprint.")
    print("PROVISIONAL has no history. They must not be conflated.")
    print("certificateHold = temporary, reversible. REVOKED = permanent.")
    print("Wilson CI at resumption uses ALL prior receipts — hibernation, not amnesia.")
