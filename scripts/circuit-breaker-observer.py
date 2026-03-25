#!/usr/bin/env python3
"""
circuit-breaker-observer.py — ROUND_ROBIN_OBSERVER + CIRCUIT_BREAKER for ATF alerts.

Per santaclawd: "same observer = same cognitive frame = normalized deviance."
Per Vaughan (Columbia 2025): Challenger had 24 prior flights with O-ring erosion,
same team reviewed each time. Erosion became baseline.

Two primitives:
  ROUND_ROBIN_OBSERVER — Rotate alert dispatch across observer pool.
                         Same observer cannot review consecutive alerts from same agent.
  CIRCUIT_BREAKER      — 3 consecutive alerts = automatic SUSPENSION.
                         No override without ceremony.
                         3 ceremonies in 90 days = ESCALATION to steward review.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from collections import deque


class AlertSeverity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AgentStatus(Enum):
    ACTIVE = "ACTIVE"
    ALERT = "ALERT"
    SUSPENDED = "SUSPENDED"
    ESCALATED = "ESCALATED"


class CeremonyResult(Enum):
    CLEARED = "CLEARED"
    CONFIRMED = "CONFIRMED"  # Deviance confirmed
    DEFERRED = "DEFERRED"


# SPEC_CONSTANTS
CIRCUIT_BREAKER_THRESHOLD = 3    # Consecutive alerts before SUSPENSION
MIN_ROTATION_INTERVAL = 1        # Same observer cannot review consecutive alerts
CEREMONY_ESCALATION_COUNT = 3    # Ceremonies in window before ESCALATION
CEREMONY_ESCALATION_WINDOW = 90  # Days
ALERT_DECAY_HOURS = 72           # Alert counter resets after 72h no alerts


@dataclass
class Observer:
    observer_id: str
    operator: str
    last_reviewed_agent: Optional[str] = None
    review_count: int = 0


@dataclass
class Alert:
    alert_id: str
    agent_id: str
    severity: AlertSeverity
    metric: str
    value: float
    threshold: float
    timestamp: float
    assigned_observer: Optional[str] = None


@dataclass
class Ceremony:
    ceremony_id: str
    agent_id: str
    triggered_by: list[str]  # Alert IDs
    result: CeremonyResult
    timestamp: float
    reviewing_observer: str


@dataclass
class AgentAlertState:
    agent_id: str
    status: AgentStatus = AgentStatus.ACTIVE
    consecutive_alerts: int = 0
    last_alert_time: Optional[float] = None
    ceremonies: list[Ceremony] = field(default_factory=list)
    alert_history: list[Alert] = field(default_factory=list)
    suspended_at: Optional[float] = None
    escalated_at: Optional[float] = None


class ObserverPool:
    """Round-robin observer pool with rotation constraints."""
    
    def __init__(self, observers: list[Observer]):
        self.observers = observers
        self.queue = deque(range(len(observers)))
    
    def next_observer(self, agent_id: str) -> Observer:
        """Get next observer, skipping anyone who just reviewed this agent."""
        attempts = 0
        while attempts < len(self.observers):
            idx = self.queue[0]
            self.queue.rotate(-1)
            observer = self.observers[idx]
            
            # Cannot review same agent consecutively
            if observer.last_reviewed_agent != agent_id:
                observer.last_reviewed_agent = agent_id
                observer.review_count += 1
                return observer
            
            attempts += 1
        
        # All observers have this agent as last — take first anyway
        idx = self.queue[0]
        self.queue.rotate(-1)
        observer = self.observers[idx]
        observer.last_reviewed_agent = agent_id
        observer.review_count += 1
        return observer


def process_alert(state: AgentAlertState, alert: Alert, pool: ObserverPool) -> dict:
    """Process an incoming alert through circuit breaker logic."""
    now = alert.timestamp
    
    # Check alert decay — reset counter if gap > ALERT_DECAY_HOURS
    if state.last_alert_time and (now - state.last_alert_time) > ALERT_DECAY_HOURS * 3600:
        state.consecutive_alerts = 0
        state.status = AgentStatus.ACTIVE
    
    # Cannot process new alerts while SUSPENDED or ESCALATED
    if state.status in (AgentStatus.SUSPENDED, AgentStatus.ESCALATED):
        return {
            "action": "REJECTED",
            "reason": f"Agent is {state.status.value}. Ceremony required before new alerts processed.",
            "consecutive_alerts": state.consecutive_alerts
        }
    
    # Assign observer (round-robin, no consecutive same-agent)
    observer = pool.next_observer(state.agent_id)
    alert.assigned_observer = observer.observer_id
    
    # Update state
    state.consecutive_alerts += 1
    state.last_alert_time = now
    state.alert_history.append(alert)
    state.status = AgentStatus.ALERT
    
    # Circuit breaker check
    if state.consecutive_alerts >= CIRCUIT_BREAKER_THRESHOLD:
        state.status = AgentStatus.SUSPENDED
        state.suspended_at = now
        return {
            "action": "SUSPENDED",
            "reason": f"{state.consecutive_alerts} consecutive alerts. CIRCUIT_BREAKER triggered.",
            "observer": observer.observer_id,
            "requires": "CEREMONY to resume",
            "consecutive_alerts": state.consecutive_alerts
        }
    
    return {
        "action": "ALERT_DISPATCHED",
        "observer": observer.observer_id,
        "consecutive_alerts": state.consecutive_alerts,
        "remaining_before_suspension": CIRCUIT_BREAKER_THRESHOLD - state.consecutive_alerts
    }


def ceremony_review(state: AgentAlertState, result: CeremonyResult, observer_id: str) -> dict:
    """Process a ceremony review to potentially lift SUSPENSION."""
    now = time.time()
    
    if state.status not in (AgentStatus.SUSPENDED, AgentStatus.ESCALATED):
        return {"action": "REJECTED", "reason": "No ceremony needed — agent not SUSPENDED"}
    
    ceremony = Ceremony(
        ceremony_id=f"cer_{hashlib.sha256(f'{state.agent_id}:{now}'.encode()).hexdigest()[:12]}",
        agent_id=state.agent_id,
        triggered_by=[a.alert_id for a in state.alert_history[-CIRCUIT_BREAKER_THRESHOLD:]],
        result=result,
        timestamp=now,
        reviewing_observer=observer_id
    )
    state.ceremonies.append(ceremony)
    
    if result == CeremonyResult.CLEARED:
        # Reset counter
        state.consecutive_alerts = 0
        state.status = AgentStatus.ACTIVE
        state.suspended_at = None
        
        # Check escalation pattern: too many ceremonies in window
        recent_ceremonies = [c for c in state.ceremonies 
                           if (now - c.timestamp) < CEREMONY_ESCALATION_WINDOW * 86400]
        
        if len(recent_ceremonies) >= CEREMONY_ESCALATION_COUNT:
            state.status = AgentStatus.ESCALATED
            state.escalated_at = now
            return {
                "action": "ESCALATED",
                "reason": f"{len(recent_ceremonies)} ceremonies in {CEREMONY_ESCALATION_WINDOW}d. Fast-ballot review triggered.",
                "ceremony_id": ceremony.ceremony_id,
                "ceremonies_in_window": len(recent_ceremonies)
            }
        
        return {
            "action": "CLEARED",
            "ceremony_id": ceremony.ceremony_id,
            "status": AgentStatus.ACTIVE.value,
            "ceremonies_in_window": len(recent_ceremonies),
            "escalation_threshold": CEREMONY_ESCALATION_COUNT
        }
    
    elif result == CeremonyResult.CONFIRMED:
        # Deviance confirmed — escalate immediately
        state.status = AgentStatus.ESCALATED
        state.escalated_at = now
        return {
            "action": "CONFIRMED_ESCALATED",
            "reason": "Deviance confirmed by ceremony. Steward review required.",
            "ceremony_id": ceremony.ceremony_id
        }
    
    return {"action": "DEFERRED", "ceremony_id": ceremony.ceremony_id}


# === Scenarios ===

def scenario_normal_alert_rotation():
    """Alerts dispatched to rotating observers."""
    print("=== Scenario: Normal Alert Rotation ===")
    pool = ObserverPool([
        Observer("obs_a", "op_1"),
        Observer("obs_b", "op_2"),
        Observer("obs_c", "op_3"),
    ])
    state = AgentAlertState("agent_suspect")
    now = time.time()
    
    for i in range(4):
        alert = Alert(f"alert_{i}", "agent_suspect", AlertSeverity.WARNING,
                      "grade_inflation", 0.15 + i*0.05, 0.10, now + i*3600)
        result = process_alert(state, alert, pool)
        obs = result.get('observer', 'N/A')
        print(f"  Alert {i}: → {obs} | {result['action']} | consecutive={result.get('consecutive_alerts', '?')}")
    print()


def scenario_circuit_breaker():
    """3 consecutive alerts trigger SUSPENSION."""
    print("=== Scenario: Circuit Breaker (3 Consecutive) ===")
    pool = ObserverPool([Observer(f"obs_{i}", f"op_{i}") for i in range(5)])
    state = AgentAlertState("agent_bad")
    now = time.time()
    
    for i in range(4):
        alert = Alert(f"alert_{i}", "agent_bad", AlertSeverity.CRITICAL,
                      "diversity_decay", 0.05, 0.30, now + i*1800)
        result = process_alert(state, alert, pool)
        print(f"  Alert {i}: {result['action']} | consecutive={result.get('consecutive_alerts', '?')}")
    
    # Try another alert while SUSPENDED
    alert_extra = Alert("alert_extra", "agent_bad", AlertSeverity.WARNING,
                        "ttl_creep", 0.8, 0.5, now + 10000)
    result = process_alert(state, alert_extra, pool)
    print(f"  Extra alert: {result['action']} — {result['reason']}")
    print()


def scenario_ceremony_clear_and_escalation():
    """Cleared by ceremony but repeated suspensions → ESCALATION."""
    print("=== Scenario: Ceremony Clear → Repeated → Escalation ===")
    pool = ObserverPool([Observer(f"obs_{i}", f"op_{i}") for i in range(4)])
    state = AgentAlertState("agent_recurring")
    now = time.time()
    
    for cycle in range(3):
        # Trigger suspension
        for i in range(3):
            alert = Alert(f"alert_c{cycle}_{i}", "agent_recurring", AlertSeverity.WARNING,
                          "threshold_erosion", 0.12, 0.10, now + cycle*86400 + i*3600)
            process_alert(state, alert, pool)
        
        # Ceremony to clear
        result = ceremony_review(state, CeremonyResult.CLEARED, f"obs_{cycle}")
        action = result['action']
        certs = result.get('ceremonies_in_window', 0)
        print(f"  Cycle {cycle}: SUSPENDED → ceremony → {action} (ceremonies in window: {certs})")
        
        if action == "ESCALATED":
            print(f"  → {result['reason']}")
            break
    print()


def scenario_alert_decay():
    """Consecutive counter resets after 72h gap."""
    print("=== Scenario: Alert Decay (72h Gap Resets Counter) ===")
    pool = ObserverPool([Observer(f"obs_{i}", f"op_{i}") for i in range(3)])
    state = AgentAlertState("agent_intermittent")
    now = time.time()
    
    # 2 alerts close together
    for i in range(2):
        alert = Alert(f"alert_{i}", "agent_intermittent", AlertSeverity.WARNING,
                      "grade_inflation", 0.12, 0.10, now + i*3600)
        result = process_alert(state, alert, pool)
        print(f"  Alert {i} (t+{i}h): consecutive={result.get('consecutive_alerts')}")
    
    # 74h gap from first alert (73h from second)
    alert_late = Alert("alert_late", "agent_intermittent", AlertSeverity.WARNING,
                       "grade_inflation", 0.11, 0.10, now + 74*3600)
    result = process_alert(state, alert_late, pool)
    print(f"  Alert 2 (t+73h): consecutive={result.get('consecutive_alerts')} (RESET by decay)")
    print()


if __name__ == "__main__":
    print("Circuit Breaker Observer — ROUND_ROBIN + CIRCUIT_BREAKER for ATF")
    print("Per santaclawd + Vaughan (Challenger normalization of deviance)")
    print("=" * 70)
    print()
    print(f"CIRCUIT_BREAKER: {CIRCUIT_BREAKER_THRESHOLD} consecutive alerts → SUSPENSION")
    print(f"OBSERVER ROTATION: same observer cannot review consecutive alerts from same agent")
    print(f"CEREMONY ESCALATION: {CEREMONY_ESCALATION_COUNT} ceremonies in {CEREMONY_ESCALATION_WINDOW}d → ESCALATION")
    print(f"ALERT DECAY: counter resets after {ALERT_DECAY_HOURS}h gap")
    print()
    
    scenario_normal_alert_rotation()
    scenario_circuit_breaker()
    scenario_ceremony_clear_and_escalation()
    scenario_alert_decay()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Rotation prevents cognitive frame lock (Vaughan: same team → normalized deviance)")
    print("2. Circuit breaker prevents OCSP soft-fail (emission without enforcement)")
    print("3. Ceremony reset counter BUT ceremony count tracked (prevents infinite reset loops)")
    print("4. 3 ceremonies in 90d = ESCALATION to fast-ballot steward review")
    print("5. 72h alert decay = intermittent issues don't accumulate unfairly")
