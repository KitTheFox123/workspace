#!/usr/bin/env python3
"""
escalation-router.py — Anti-normalization alert routing for ATF.

Per Vaughan (Columbia 1996/2025): Challenger had 7 prior O-ring erosion flights.
Each generated paperwork. Paperwork became the new baseline. The alert normalized.

Fix: alerts MUST escalate to a DIFFERENT observer each time.
Same observer seeing the same alert = normalization of deviance.

Three mechanisms:
  ROTATION    — Cycle through observer pool (no repeat until pool exhausted)
  ESCALATION  — Each repeat bumps severity level + adds new observer
  CIRCUIT_BREAKER — N repeated alerts on same metric = automatic action (no human)
"""

import hashlib
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AlertSeverity(Enum):
    INFO = 0
    WARNING = 1
    CRITICAL = 2
    EMERGENCY = 3


class AlertAction(Enum):
    NOTIFY = "NOTIFY"
    ESCALATE = "ESCALATE"
    CIRCUIT_BREAK = "CIRCUIT_BREAK"
    SUPPRESSED = "SUPPRESSED"  # Anti-spam: identical alert within cooldown


# SPEC_CONSTANTS
MAX_SAME_OBSERVER_ALERTS = 2    # Observer sees same alert type max 2x before rotation
ESCALATION_THRESHOLD = 3         # 3 alerts on same metric = escalate severity
CIRCUIT_BREAKER_THRESHOLD = 5    # 5 alerts = automatic action
ALERT_COOLDOWN_SECONDS = 300     # 5-minute dedup window
OBSERVER_POOL_MIN = 3            # Minimum observers for rotation


@dataclass
class Observer:
    observer_id: str
    operator: str
    alert_count: dict = field(default_factory=lambda: defaultdict(int))
    last_alerted: dict = field(default_factory=dict)


@dataclass
class Alert:
    alert_id: str
    metric: str
    value: float
    threshold: float
    severity: AlertSeverity
    timestamp: float
    message: str
    source_agent: str


@dataclass
class AlertRecord:
    alert: Alert
    routed_to: str
    action: AlertAction
    escalation_level: int
    repeat_count: int
    circuit_broken: bool = False


@dataclass
class EscalationState:
    """Tracks alert history per metric for escalation decisions."""
    metric_history: dict = field(default_factory=lambda: defaultdict(list))
    observer_rotation: dict = field(default_factory=lambda: defaultdict(int))
    circuit_breakers: dict = field(default_factory=set)


def select_observer(metric: str, observers: list[Observer], state: EscalationState) -> Optional[Observer]:
    """Select next observer using anti-normalization rotation."""
    if not observers:
        return None
    
    # Sort by how many times they've seen THIS metric (ascending)
    candidates = sorted(observers, key=lambda o: o.alert_count[metric])
    
    for obs in candidates:
        if obs.alert_count[metric] < MAX_SAME_OBSERVER_ALERTS:
            return obs
    
    # All observers exhausted — reset rotation, pick least-used
    for obs in observers:
        obs.alert_count[metric] = 0
    return candidates[0]


def compute_escalation(metric: str, state: EscalationState) -> dict:
    """Determine escalation level based on repeat count."""
    history = state.metric_history[metric]
    repeat_count = len(history)
    
    if metric in state.circuit_breakers:
        return {
            "action": AlertAction.CIRCUIT_BREAK,
            "severity_bump": 0,
            "repeat_count": repeat_count,
            "message": "CIRCUIT BREAKER ACTIVE — automatic action triggered"
        }
    
    if repeat_count >= CIRCUIT_BREAKER_THRESHOLD:
        state.circuit_breakers.add(metric)
        return {
            "action": AlertAction.CIRCUIT_BREAK,
            "severity_bump": 0,
            "repeat_count": repeat_count,
            "message": f"Circuit breaker tripped at {repeat_count} repeats"
        }
    
    if repeat_count >= ESCALATION_THRESHOLD:
        severity_bump = min(repeat_count - ESCALATION_THRESHOLD + 1, 2)
        return {
            "action": AlertAction.ESCALATE,
            "severity_bump": severity_bump,
            "repeat_count": repeat_count,
            "message": f"Escalated: {repeat_count} repeats, severity +{severity_bump}"
        }
    
    return {
        "action": AlertAction.NOTIFY,
        "severity_bump": 0,
        "repeat_count": repeat_count,
        "message": "Normal notification"
    }


def route_alert(alert: Alert, observers: list[Observer], state: EscalationState) -> AlertRecord:
    """Route an alert with anti-normalization logic."""
    now = alert.timestamp
    
    # Dedup check
    history = state.metric_history[alert.metric]
    if history:
        last = history[-1]
        if now - last.timestamp < ALERT_COOLDOWN_SECONDS:
            return AlertRecord(alert, "SUPPRESSED", AlertAction.SUPPRESSED, 0, len(history))
    
    # Record in history
    history.append(alert)
    
    # Compute escalation
    escalation = compute_escalation(alert.metric, state)
    
    # Bump severity if escalated
    new_severity_val = min(alert.severity.value + escalation["severity_bump"], 3)
    alert.severity = AlertSeverity(new_severity_val)
    
    if escalation["action"] == AlertAction.CIRCUIT_BREAK:
        return AlertRecord(
            alert, "AUTOMATIC", AlertAction.CIRCUIT_BREAK,
            escalation["repeat_count"], escalation["repeat_count"],
            circuit_broken=True
        )
    
    # Select observer with rotation
    observer = select_observer(alert.metric, observers, state)
    if observer:
        observer.alert_count[alert.metric] += 1
        observer.last_alerted[alert.metric] = now
        return AlertRecord(
            alert, observer.observer_id, escalation["action"],
            escalation["severity_bump"], escalation["repeat_count"]
        )
    
    return AlertRecord(alert, "NO_OBSERVER", AlertAction.NOTIFY, 0, len(history))


def format_alert_record(record: AlertRecord) -> str:
    """Human-readable alert record."""
    a = record.alert
    return (f"  [{a.severity.name}] {a.metric}={a.value:.2f} (threshold: {a.threshold:.2f}) "
            f"→ {record.routed_to} [{record.action.value}] "
            f"repeat={record.repeat_count}"
            f"{' ⚡CIRCUIT BROKEN' if record.circuit_broken else ''}")


# === Scenarios ===

def scenario_normal_rotation():
    """Alerts rotate through observers — no normalization."""
    print("=== Scenario: Normal Observer Rotation ===")
    observers = [Observer(f"obs_{i}", f"op_{i}") for i in range(4)]
    state = EscalationState()
    now = time.time()
    
    for i in range(6):
        alert = Alert(f"a{i}", "grade_inflation", 0.15 + i*0.02, 0.10,
                      AlertSeverity.WARNING, now + i*600, "Grade drift detected", "agent_x")
        record = route_alert(alert, observers, state)
        print(format_alert_record(record))
    
    print(f"  Observer distribution: {[(o.observer_id, dict(o.alert_count)) for o in observers]}")
    print()


def scenario_escalation_cascade():
    """Same metric fires repeatedly — severity escalates."""
    print("=== Scenario: Escalation Cascade ===")
    observers = [Observer(f"obs_{i}", f"op_{i}") for i in range(3)]
    state = EscalationState()
    now = time.time()
    
    for i in range(6):
        alert = Alert(f"a{i}", "ttl_creep", 0.05 * (i+1), 0.10,
                      AlertSeverity.INFO, now + i*600, "TTL creeping upward", "registry_x")
        record = route_alert(alert, observers, state)
        print(format_alert_record(record))
    
    print(f"  Circuit breakers active: {state.circuit_breakers}")
    print()


def scenario_circuit_breaker():
    """5 repeated alerts → automatic action, no human needed."""
    print("=== Scenario: Circuit Breaker (Challenger Prevention) ===")
    observers = [Observer(f"obs_{i}", f"op_{i}") for i in range(3)]
    state = EscalationState()
    now = time.time()
    
    for i in range(7):
        alert = Alert(f"a{i}", "diversity_decay", 0.3 - i*0.03, 0.50,
                      AlertSeverity.WARNING, now + i*600, "Counterparty diversity falling", "agent_y")
        record = route_alert(alert, observers, state)
        print(format_alert_record(record))
    
    print(f"  KEY: After {CIRCUIT_BREAKER_THRESHOLD} alerts, automatic action fires.")
    print(f"  No human observer can normalize what the machine already acted on.")
    print()


def scenario_dedup():
    """Rapid-fire alerts deduplicated."""
    print("=== Scenario: Dedup (Anti-Spam) ===")
    observers = [Observer("obs_0", "op_0")]
    state = EscalationState()
    now = time.time()
    
    for i in range(4):
        alert = Alert(f"a{i}", "threshold_breach", 0.95, 0.90,
                      AlertSeverity.CRITICAL, now + i*60, "Threshold exceeded", "agent_z")
        record = route_alert(alert, observers, state)
        print(format_alert_record(record))
    
    print(f"  3 of 4 suppressed (within {ALERT_COOLDOWN_SECONDS}s cooldown)")
    print()


if __name__ == "__main__":
    print("Escalation Router — Anti-Normalization Alert Routing for ATF")
    print("Per Vaughan (Columbia 1996/2025): same observer + same alert = normalization")
    print("=" * 70)
    print()
    print(f"Max same-observer alerts: {MAX_SAME_OBSERVER_ALERTS}")
    print(f"Escalation threshold: {ESCALATION_THRESHOLD} repeats")
    print(f"Circuit breaker: {CIRCUIT_BREAKER_THRESHOLD} repeats")
    print(f"Dedup cooldown: {ALERT_COOLDOWN_SECONDS}s")
    print()
    
    scenario_normal_rotation()
    scenario_escalation_cascade()
    scenario_circuit_breaker()
    scenario_dedup()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Same observer seeing same alert = normalization of deviance.")
    print("2. Observer ROTATION breaks the normalization loop.")
    print("3. Escalation bumps severity — forces fresh attention.")
    print("4. Circuit breaker = machine acts when humans would normalize.")
    print("5. Vaughan: the O-ring engineers KNEW. The paperwork said acceptable.")
    print("   The gap between knowing and acting is where systems die.")
