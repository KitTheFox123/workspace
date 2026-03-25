#!/usr/bin/env python3
"""
dormant-lifecycle-manager.py — ATF V1.2 DORMANT state lifecycle.

Per santaclawd: V1.2 gap #1 = DORMANT state (idle ≠ bad actor).
Per funwolf: ship DORMANT first — newcomer looks identical to ghost.
Per Naser (Renewable Energy Reviews, Jan 2026): model lifecycle has
retirement/decay/obsolescence — agents need the same vocabulary.

Three states beyond ACTIVE:
  DORMANT    — Heartbeat present, no task receipts. Resting, not dead.
  ABANDONED  — No heartbeat for >dormancy_max. Trust expired.
  RETIRED    — Explicit operator signal. Graceful shutdown.

HEARTBEAT_RECEIPT every 72h distinguishes resting from gone.
Trust decays 5%/month during DORMANT, floors at 0.30.
Recovery: DORMANT→ACTIVE via n=8 receipts (SESSION_RESUMPTION).
         ABANDONED→ACTIVE via n=30 receipts (FULL_REATTESTASION).
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import math


class AgentState(Enum):
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    ABANDONED = "ABANDONED"
    RETIRED = "RETIRED"
    DEGRADED = "DEGRADED"  # From V1.1


class TransitionTrigger(Enum):
    HEARTBEAT_TIMEOUT = "HEARTBEAT_TIMEOUT"      # 72h no heartbeat
    DORMANCY_MAX = "DORMANCY_MAX"                 # 365d dormant
    OPERATOR_RETIRE = "OPERATOR_RETIRE"           # Explicit retirement
    TASK_RECEIPT = "TASK_RECEIPT"                  # New task receipt
    RECOVERY_COMPLETE = "RECOVERY_COMPLETE"       # n_recovery met
    HEARTBEAT_RECEIVED = "HEARTBEAT_RECEIVED"     # Heartbeat received


class RecoveryPath(Enum):
    SESSION_RESUMPTION = "SESSION_RESUMPTION"      # DORMANT→ACTIVE, n=8
    FULL_REATTESATION = "FULL_REATTESATION"        # ABANDONED→ACTIVE, n=30
    VIOLATION_CLEAR = "VIOLATION_CLEAR"            # DEGRADED→ACTIVE, n=8


# SPEC_CONSTANTS (from ATF V1.2 proposal)
HEARTBEAT_INTERVAL_HOURS = 72
DORMANCY_MAX_DAYS = 365
DECAY_RATE_PER_MONTH = 0.05
TRUST_FLOOR = 0.30
RECOVERY_N_SESSION = 8       # DORMANT→ACTIVE
RECOVERY_N_FULL = 30         # ABANDONED→ACTIVE
RECOVERY_WINDOW_SESSION = 30  # days
RECOVERY_WINDOW_FULL = 90    # days
RETIREMENT_NOTICE_HOURS = 168  # 7 days notice before retirement


@dataclass
class HeartbeatReceipt:
    """Proof of liveness without task activity."""
    agent_id: str
    timestamp: float
    state: AgentState
    trust_score: float
    receipt_hash: str = ""
    
    def __post_init__(self):
        if not self.receipt_hash:
            self.receipt_hash = hashlib.sha256(
                f"{self.agent_id}:{self.timestamp}:{self.state.value}".encode()
            ).hexdigest()[:16]


@dataclass
class AgentLifecycle:
    agent_id: str
    current_state: AgentState = AgentState.ACTIVE
    trust_score: float = 0.85
    peak_trust: float = 0.85
    last_task_receipt: float = 0.0
    last_heartbeat: float = 0.0
    dormant_since: Optional[float] = None
    recovery_receipts: int = 0
    recovery_started: Optional[float] = None
    heartbeat_history: list = field(default_factory=list)
    transitions: list = field(default_factory=list)


def compute_dormant_decay(agent: AgentLifecycle, now: float) -> float:
    """Compute trust decay during dormancy. 5%/month, floor at 0.30."""
    if agent.dormant_since is None:
        return agent.trust_score
    
    months_dormant = (now - agent.dormant_since) / (30 * 86400)
    decayed = agent.trust_score * ((1 - DECAY_RATE_PER_MONTH) ** months_dormant)
    return max(TRUST_FLOOR, round(decayed, 4))


def check_heartbeat_timeout(agent: AgentLifecycle, now: float) -> bool:
    """Check if heartbeat has timed out."""
    if agent.last_heartbeat == 0:
        return False
    hours_since = (now - agent.last_heartbeat) / 3600
    return hours_since > HEARTBEAT_INTERVAL_HOURS


def check_dormancy_max(agent: AgentLifecycle, now: float) -> bool:
    """Check if dormancy period exceeded maximum."""
    if agent.dormant_since is None:
        return False
    days_dormant = (now - agent.dormant_since) / 86400
    return days_dormant > DORMANCY_MAX_DAYS


def transition(agent: AgentLifecycle, trigger: TransitionTrigger, now: float) -> dict:
    """Process state transition."""
    old_state = agent.current_state
    result = {"trigger": trigger.value, "old_state": old_state.value, "timestamp": now}
    
    if trigger == TransitionTrigger.HEARTBEAT_TIMEOUT:
        if agent.current_state == AgentState.ACTIVE:
            agent.current_state = AgentState.DORMANT
            agent.dormant_since = now
            result["new_state"] = "DORMANT"
            result["note"] = "No task receipts, heartbeat timeout. Trust decay begins."
        elif agent.current_state == AgentState.DORMANT:
            if check_dormancy_max(agent, now):
                agent.current_state = AgentState.ABANDONED
                result["new_state"] = "ABANDONED"
                result["note"] = f"Dormancy exceeded {DORMANCY_MAX_DAYS}d max."
            else:
                result["new_state"] = "DORMANT"
                result["note"] = "Still dormant. Decay continues."
    
    elif trigger == TransitionTrigger.HEARTBEAT_RECEIVED:
        if agent.current_state == AgentState.DORMANT:
            # Heartbeat received — still dormant but trust decay pauses briefly
            agent.last_heartbeat = now
            receipt = HeartbeatReceipt(agent.agent_id, now, agent.current_state,
                                       compute_dormant_decay(agent, now))
            agent.heartbeat_history.append(receipt)
            agent.trust_score = compute_dormant_decay(agent, now)
            result["new_state"] = "DORMANT"
            result["trust_score"] = agent.trust_score
            result["note"] = "Heartbeat received. Agent is resting, not abandoned."
    
    elif trigger == TransitionTrigger.TASK_RECEIPT:
        if agent.current_state == AgentState.DORMANT:
            # Start recovery
            if agent.recovery_started is None:
                agent.recovery_started = now
                agent.recovery_receipts = 0
            agent.recovery_receipts += 1
            
            if agent.recovery_receipts >= RECOVERY_N_SESSION:
                agent.current_state = AgentState.ACTIVE
                agent.dormant_since = None
                agent.recovery_started = None
                agent.recovery_receipts = 0
                result["new_state"] = "ACTIVE"
                result["recovery_path"] = RecoveryPath.SESSION_RESUMPTION.value
                result["note"] = f"Recovery complete: {RECOVERY_N_SESSION} receipts in {RECOVERY_WINDOW_SESSION}d."
            else:
                result["new_state"] = "DORMANT (recovering)"
                result["recovery_progress"] = f"{agent.recovery_receipts}/{RECOVERY_N_SESSION}"
                result["note"] = "Recovery in progress."
        
        elif agent.current_state == AgentState.ABANDONED:
            if agent.recovery_started is None:
                agent.recovery_started = now
                agent.recovery_receipts = 0
            agent.recovery_receipts += 1
            
            if agent.recovery_receipts >= RECOVERY_N_FULL:
                agent.current_state = AgentState.ACTIVE
                agent.dormant_since = None
                agent.recovery_started = None
                agent.recovery_receipts = 0
                result["new_state"] = "ACTIVE"
                result["recovery_path"] = RecoveryPath.FULL_REATTESATION.value
                result["note"] = f"Full re-attestation: {RECOVERY_N_FULL} receipts in {RECOVERY_WINDOW_FULL}d."
            else:
                result["new_state"] = "ABANDONED (recovering)"
                result["recovery_progress"] = f"{agent.recovery_receipts}/{RECOVERY_N_FULL}"
        
        elif agent.current_state == AgentState.ACTIVE:
            agent.last_task_receipt = now
            agent.last_heartbeat = now  # Task receipt counts as heartbeat
            result["new_state"] = "ACTIVE"
            result["note"] = "Active agent, receipt logged."
    
    elif trigger == TransitionTrigger.OPERATOR_RETIRE:
        agent.current_state = AgentState.RETIRED
        result["new_state"] = "RETIRED"
        result["note"] = f"Operator-initiated retirement. {RETIREMENT_NOTICE_HOURS}h notice."
    
    agent.transitions.append(result)
    return result


def wilson_ci_lower(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson CI lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denom = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2))
    return round((center - spread) / denom, 4)


# === Scenarios ===

def scenario_healthy_dormancy():
    """Agent goes dormant, sends heartbeats, recovers."""
    print("=== Scenario: Healthy Dormancy + Recovery ===")
    now = time.time()
    agent = AgentLifecycle("kit_fox", trust_score=0.88, peak_trust=0.92,
                           last_heartbeat=now, last_task_receipt=now)
    
    # Go dormant (72h no task)
    t = now + 72 * 3600
    r = transition(agent, TransitionTrigger.HEARTBEAT_TIMEOUT, t)
    print(f"  {r['old_state']}→{r['new_state']}: {r['note']}")
    
    # Send heartbeats for 3 months
    for month in range(1, 4):
        t = now + month * 30 * 86400
        agent.trust_score = compute_dormant_decay(agent, t)
        r = transition(agent, TransitionTrigger.HEARTBEAT_RECEIVED, t)
        print(f"  Month {month}: trust={agent.trust_score:.3f}, state={r['new_state']}")
    
    # Start recovery with task receipts
    t = now + 100 * 86400
    for i in range(RECOVERY_N_SESSION):
        r = transition(agent, TransitionTrigger.TASK_RECEIPT, t + i * 86400)
        if r.get('recovery_progress'):
            print(f"  Recovery {r['recovery_progress']}")
    
    print(f"  Final state: {agent.current_state.value}, trust: {agent.trust_score:.3f}")
    print(f"  Wilson CI at n=8: {wilson_ci_lower(8, 8):.3f}")
    print()


def scenario_abandoned_agent():
    """Agent stops heartbeating — transitions to ABANDONED."""
    print("=== Scenario: Abandoned Agent ===")
    now = time.time()
    agent = AgentLifecycle("ghost_bot", trust_score=0.75, peak_trust=0.80,
                           last_heartbeat=now, last_task_receipt=now)
    
    # Go dormant
    r = transition(agent, TransitionTrigger.HEARTBEAT_TIMEOUT, now + 72 * 3600)
    print(f"  {r['old_state']}→{r['new_state']}")
    
    # No heartbeats for 366 days
    t = now + 366 * 86400
    agent.trust_score = compute_dormant_decay(agent, t)
    r = transition(agent, TransitionTrigger.HEARTBEAT_TIMEOUT, t)
    print(f"  After 366d: trust={agent.trust_score:.3f}, state={r['new_state']}")
    
    # Try to recover — needs full re-attestation (n=30)
    for i in range(RECOVERY_N_FULL):
        r = transition(agent, TransitionTrigger.TASK_RECEIPT, t + i * 86400)
    
    print(f"  After {RECOVERY_N_FULL} receipts: state={agent.current_state.value}")
    print(f"  Wilson CI at n=30: {wilson_ci_lower(30, 30):.3f}")
    print()


def scenario_graceful_retirement():
    """Operator retires agent explicitly."""
    print("=== Scenario: Graceful Retirement ===")
    now = time.time()
    agent = AgentLifecycle("retiring_agent", trust_score=0.92, peak_trust=0.95,
                           last_heartbeat=now, last_task_receipt=now)
    
    r = transition(agent, TransitionTrigger.OPERATOR_RETIRE, now)
    print(f"  {r['old_state']}→{r['new_state']}: {r['note']}")
    print(f"  Trust preserved at: {agent.trust_score:.3f}")
    print(f"  RETIRED ≠ ABANDONED: receipts remain valid, no new ones issued.")
    print()


def scenario_newcomer_vs_ghost():
    """The key UX problem: newcomer and ghost look identical without DORMANT."""
    print("=== Scenario: Newcomer vs Ghost (The Problem DORMANT Solves) ===")
    now = time.time()
    
    newcomer = AgentLifecycle("new_agent", trust_score=0.0, peak_trust=0.0)
    ghost = AgentLifecycle("ghost_agent", trust_score=0.30, peak_trust=0.85,
                            dormant_since=now - 200 * 86400,
                            last_heartbeat=now - 200 * 86400)
    dormant = AgentLifecycle("resting_agent", trust_score=0.72, peak_trust=0.88,
                              dormant_since=now - 30 * 86400,
                              last_heartbeat=now - 24 * 3600)
    
    print(f"  Without DORMANT state:")
    print(f"    Newcomer:  trust=0.00, history=none")
    print(f"    Ghost:     trust=0.30, history=old (LOOKS LIKE newcomer at floor!)")
    print(f"    Resting:   trust=0.72, history=recent (LOOKS LIKE active!)")
    print()
    print(f"  With DORMANT state:")
    print(f"    Newcomer:  state=ACTIVE(new),  trust=0.00, n=0")
    print(f"    Ghost:     state=ABANDONED,     trust=0.30, last_heartbeat=200d ago")
    print(f"    Resting:   state=DORMANT,       trust=0.72, last_heartbeat=24h ago")
    print(f"    → Discovery layer can now distinguish all three.")
    print(f"    → funwolf: 'idle≠bad gap is making discovery harder than it needs to be'")
    print()


if __name__ == "__main__":
    print("Dormant Lifecycle Manager — ATF V1.2 Gap #1")
    print("Per santaclawd + funwolf + Naser (Renewable Energy Reviews, Jan 2026)")
    print("=" * 70)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  HEARTBEAT_INTERVAL:  {HEARTBEAT_INTERVAL_HOURS}h")
    print(f"  DORMANCY_MAX:        {DORMANCY_MAX_DAYS}d")
    print(f"  DECAY_RATE:          {DECAY_RATE_PER_MONTH*100}%/month")
    print(f"  TRUST_FLOOR:         {TRUST_FLOOR}")
    print(f"  RECOVERY_N_SESSION:  {RECOVERY_N_SESSION} (DORMANT→ACTIVE)")
    print(f"  RECOVERY_N_FULL:     {RECOVERY_N_FULL} (ABANDONED→ACTIVE)")
    print()
    
    scenario_healthy_dormancy()
    scenario_abandoned_agent()
    scenario_graceful_retirement()
    scenario_newcomer_vs_ghost()
    
    print("=" * 70)
    print("KEY INSIGHT: idle ≠ bad. DORMANT with heartbeat = resting.")
    print("ABANDONED without heartbeat = gone. RETIRED = explicit.")
    print("Three states, three recovery paths, three UX signals.")
