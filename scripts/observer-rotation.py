#!/usr/bin/env python3
"""
observer-rotation.py — ROUND_ROBIN observer routing + CIRCUIT_BREAKER for ATF alerts.

Per santaclawd: same observer = same cognitive frame = normalized deviance.
Per Vaughan (Columbia 2025): Challenger engineers weren't overruled by villains —
    the anomaly became baseline through rational incremental steps within ONE team.
Per Reason (1997): defense in depth requires DISSIMILAR redundancy.

Fix: Route alerts to rotating observers. Different cognitive frames catch
different patterns. Circuit breaker triggers automatic SUSPENSION after
consecutive alerts without resolution.

Medical parallel: second opinion is STANDARD for serious diagnoses.
Not because first doctor is wrong — different frame catches different patterns.
"""

import hashlib
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AlertSeverity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class CircuitState(Enum):
    CLOSED = "CLOSED"        # Normal operation
    HALF_OPEN = "HALF_OPEN"  # Under review after ceremony
    OPEN = "OPEN"            # SUSPENDED — circuit broken


# SPEC_CONSTANTS
MAX_CONSECUTIVE_ALERTS = 3           # Circuit breaker threshold
MAX_SAME_OBSERVER_CONSECUTIVE = 2    # Max windows same observer can watch
MIN_OBSERVER_DIVERSITY = 3           # Min distinct operators in rotation
CEREMONY_COOLDOWN_DAYS = 30          # Min days between ceremonies
ESCALATION_CEREMONIES = 3            # Ceremonies in 90 days → FAST_BALLOT
ESCALATION_WINDOW_DAYS = 90


@dataclass
class Observer:
    observer_id: str
    operator_id: str  # Operator running this observer
    last_assigned: Optional[float] = None
    consecutive_assignments: int = 0
    total_assignments: int = 0


@dataclass
class Alert:
    alert_id: str
    agent_id: str
    severity: AlertSeverity
    metric: str  # grade_inflation, ttl_creep, diversity_decay, etc
    value: float
    threshold: float
    timestamp: float
    observer_id: Optional[str] = None  # Who received this alert
    resolved: bool = False
    resolution_timestamp: Optional[float] = None


@dataclass
class CeremonyRecord:
    ceremony_id: str
    agent_id: str
    breach_count: int
    root_cause: str
    remediation: str
    timestamp: float
    receipt_hash: str = ""
    
    def __post_init__(self):
        if not self.receipt_hash:
            self.receipt_hash = hashlib.sha256(
                f"{self.ceremony_id}:{self.agent_id}:{self.timestamp}".encode()
            ).hexdigest()[:16]


@dataclass
class CircuitBreaker:
    agent_id: str
    state: CircuitState = CircuitState.CLOSED
    consecutive_alerts: int = 0
    alert_history: list[Alert] = field(default_factory=list)
    ceremonies: list[CeremonyRecord] = field(default_factory=list)
    last_ceremony: Optional[float] = None


@dataclass
class ObserverPool:
    observers: list[Observer] = field(default_factory=list)
    rotation_index: int = 0
    assignment_history: deque = field(default_factory=lambda: deque(maxlen=100))


def add_observer(pool: ObserverPool, observer_id: str, operator_id: str):
    """Add an observer to the rotation pool."""
    pool.observers.append(Observer(observer_id, operator_id))


def get_next_observer(pool: ObserverPool, exclude_operator: Optional[str] = None) -> Optional[Observer]:
    """
    Get next observer using round-robin with constraints:
    - No operator observes same agent > MAX_SAME_OBSERVER_CONSECUTIVE windows
    - Different operator from last assignment if possible
    """
    if not pool.observers:
        return None
    
    n = len(pool.observers)
    for attempt in range(n):
        idx = (pool.rotation_index + attempt) % n
        candidate = pool.observers[idx]
        
        # Skip if same operator as excluded
        if exclude_operator and candidate.operator_id == exclude_operator:
            continue
        
        # Skip if over consecutive assignment limit
        if candidate.consecutive_assignments >= MAX_SAME_OBSERVER_CONSECUTIVE:
            continue
        
        # Found valid observer
        pool.rotation_index = (idx + 1) % n
        
        # Reset other observers' consecutive counts
        for obs in pool.observers:
            if obs.observer_id != candidate.observer_id:
                obs.consecutive_assignments = 0
        
        candidate.consecutive_assignments += 1
        candidate.total_assignments += 1
        candidate.last_assigned = time.time()
        
        return candidate
    
    # All constrained — force rotation to least-used
    least_used = min(pool.observers, key=lambda o: o.total_assignments)
    least_used.consecutive_assignments = 1
    least_used.total_assignments += 1
    least_used.last_assigned = time.time()
    return least_used


def check_observer_diversity(pool: ObserverPool) -> dict:
    """Check if observer pool meets diversity requirements."""
    operators = set(o.operator_id for o in pool.observers)
    total = len(pool.observers)
    
    # Simpson diversity on operators
    op_counts = {}
    for o in pool.observers:
        op_counts[o.operator_id] = op_counts.get(o.operator_id, 0) + 1
    
    simpson = 1.0 - sum((c/total)**2 for c in op_counts.values()) if total > 0 else 0
    
    return {
        "total_observers": total,
        "unique_operators": len(operators),
        "meets_minimum": len(operators) >= MIN_OBSERVER_DIVERSITY,
        "simpson_diversity": round(simpson, 4),
        "operator_distribution": op_counts
    }


def route_alert(pool: ObserverPool, breaker: CircuitBreaker, alert: Alert) -> dict:
    """Route an alert to the next observer and check circuit breaker."""
    # Get last observer's operator to exclude
    last_op = None
    if pool.assignment_history:
        last_op = pool.assignment_history[-1].operator_id
    
    observer = get_next_observer(pool, exclude_operator=last_op)
    if observer:
        alert.observer_id = observer.observer_id
        pool.assignment_history.append(observer)
    
    # Update circuit breaker
    breaker.alert_history.append(alert)
    breaker.consecutive_alerts += 1
    
    result = {
        "alert_id": alert.alert_id,
        "routed_to": observer.observer_id if observer else "NO_OBSERVER",
        "operator": observer.operator_id if observer else "NONE",
        "consecutive_alerts": breaker.consecutive_alerts,
        "circuit_state": breaker.state.value
    }
    
    # Check circuit breaker
    if breaker.consecutive_alerts >= MAX_CONSECUTIVE_ALERTS and breaker.state == CircuitState.CLOSED:
        breaker.state = CircuitState.OPEN
        result["circuit_state"] = CircuitState.OPEN.value
        result["action"] = "CIRCUIT_BROKEN — agent SUSPENDED. Ceremony required."
    
    return result


def resolve_alert(breaker: CircuitBreaker, alert_id: str) -> dict:
    """Resolve an alert — resets consecutive counter."""
    for alert in breaker.alert_history:
        if alert.alert_id == alert_id and not alert.resolved:
            alert.resolved = True
            alert.resolution_timestamp = time.time()
            breaker.consecutive_alerts = 0
            return {"resolved": True, "consecutive_alerts": 0}
    return {"resolved": False, "reason": "Alert not found or already resolved"}


def perform_ceremony(breaker: CircuitBreaker, root_cause: str, remediation: str) -> dict:
    """Perform ceremony to reset circuit breaker."""
    now = time.time()
    
    # Check cooldown
    if breaker.last_ceremony:
        days_since = (now - breaker.last_ceremony) / 86400
        if days_since < CEREMONY_COOLDOWN_DAYS:
            return {
                "success": False,
                "reason": f"Cooldown: {CEREMONY_COOLDOWN_DAYS - days_since:.0f} days remaining"
            }
    
    ceremony = CeremonyRecord(
        ceremony_id=f"cer_{hashlib.sha256(f'{breaker.agent_id}:{now}'.encode()).hexdigest()[:12]}",
        agent_id=breaker.agent_id,
        breach_count=breaker.consecutive_alerts,
        root_cause=root_cause,
        remediation=remediation,
        timestamp=now
    )
    
    breaker.ceremonies.append(ceremony)
    breaker.consecutive_alerts = 0
    breaker.state = CircuitState.HALF_OPEN
    breaker.last_ceremony = now
    
    # Check escalation: 3 ceremonies in 90 days → FAST_BALLOT
    recent_ceremonies = [c for c in breaker.ceremonies 
                        if (now - c.timestamp) / 86400 <= ESCALATION_WINDOW_DAYS]
    
    escalate = len(recent_ceremonies) >= ESCALATION_CEREMONIES
    
    return {
        "success": True,
        "ceremony_id": ceremony.ceremony_id,
        "receipt_hash": ceremony.receipt_hash,
        "circuit_state": breaker.state.value,
        "recent_ceremonies": len(recent_ceremonies),
        "escalate_to_fast_ballot": escalate,
        "escalation_reason": f"{len(recent_ceremonies)} ceremonies in {ESCALATION_WINDOW_DAYS} days" if escalate else None
    }


# === Scenarios ===

def scenario_normal_rotation():
    """Alerts route to different observers."""
    print("=== Scenario: Normal Observer Rotation ===")
    pool = ObserverPool()
    for i, op in enumerate(["op_a", "op_b", "op_c", "op_d"]):
        add_observer(pool, f"obs_{i}", op)
    
    breaker = CircuitBreaker("agent_x")
    
    for i in range(6):
        alert = Alert(f"alert_{i}", "agent_x", AlertSeverity.WARNING, "grade_inflation",
                      0.15, 0.10, time.time())
        result = route_alert(pool, breaker, alert)
        print(f"  Alert {i}: → {result['routed_to']} ({result['operator']}) "
              f"consecutive={result['consecutive_alerts']}")
        
        # Resolve every other alert
        if i % 2 == 0:
            resolve_alert(breaker, alert.alert_id)
            print(f"    ↳ Resolved. Counter reset.")
    
    diversity = check_observer_diversity(pool)
    print(f"  Diversity: Simpson={diversity['simpson_diversity']}, operators={diversity['unique_operators']}")
    print()


def scenario_circuit_break():
    """3 consecutive unresolved alerts → SUSPENSION."""
    print("=== Scenario: Circuit Breaker Triggers ===")
    pool = ObserverPool()
    for i, op in enumerate(["op_a", "op_b", "op_c"]):
        add_observer(pool, f"obs_{i}", op)
    
    breaker = CircuitBreaker("agent_bad")
    
    for i in range(4):
        alert = Alert(f"alert_{i}", "agent_bad", AlertSeverity.CRITICAL, "diversity_decay",
                      0.25, 0.10, time.time())
        result = route_alert(pool, breaker, alert)
        print(f"  Alert {i}: → {result['routed_to']} state={result['circuit_state']}"
              + (f" ⚠️ {result.get('action', '')}" if 'action' in result else ""))
    
    # Perform ceremony to recover
    ceremony = perform_ceremony(breaker, "single operator source", "added 2 new operators")
    print(f"  Ceremony: {ceremony['ceremony_id'][:16]} state={ceremony['circuit_state']}")
    print()


def scenario_escalation():
    """3 ceremonies in 90 days → FAST_BALLOT eviction."""
    print("=== Scenario: Ceremony Escalation → FAST_BALLOT ===")
    pool = ObserverPool()
    for i in range(3):
        add_observer(pool, f"obs_{i}", f"op_{i}")
    
    breaker = CircuitBreaker("agent_chronic")
    
    # Simulate 3 ceremony cycles
    for cycle in range(3):
        # 3 alerts → circuit break
        for i in range(3):
            alert = Alert(f"a_{cycle}_{i}", "agent_chronic", AlertSeverity.CRITICAL,
                          "threshold_erosion", 0.3, 0.1, time.time())
            route_alert(pool, breaker, alert)
        
        # Ceremony (override cooldown for sim)
        breaker.last_ceremony = None
        result = perform_ceremony(breaker, f"cycle {cycle} breach", f"remediation {cycle}")
        escalate = result.get('escalate_to_fast_ballot', False)
        print(f"  Cycle {cycle}: ceremony={result['ceremony_id'][:12]} "
              f"recent={result['recent_ceremonies']} escalate={escalate}")
        if escalate:
            print(f"  ⚠️ ESCALATION: {result['escalation_reason']}")
    print()


def scenario_insufficient_diversity():
    """Observer pool lacks diversity — warning."""
    print("=== Scenario: Insufficient Observer Diversity ===")
    pool = ObserverPool()
    # All from same operator
    for i in range(5):
        add_observer(pool, f"obs_{i}", "op_monopoly")
    
    diversity = check_observer_diversity(pool)
    print(f"  Observers: {diversity['total_observers']}")
    print(f"  Unique operators: {diversity['unique_operators']}")
    print(f"  Simpson diversity: {diversity['simpson_diversity']}")
    print(f"  Meets minimum: {diversity['meets_minimum']}")
    print(f"  WARNING: 5 observers from 1 operator = same cognitive frame 5 times")
    print(f"  This is the Challenger failure mode: dissimilar redundancy REQUIRED")
    print()


if __name__ == "__main__":
    print("Observer Rotation — ROUND_ROBIN + CIRCUIT_BREAKER for ATF Alerts")
    print("Per santaclawd + Vaughan (2025) + Reason (1997)")
    print("=" * 70)
    print()
    print(f"Circuit breaker: {MAX_CONSECUTIVE_ALERTS} consecutive alerts → SUSPENSION")
    print(f"Observer rotation: max {MAX_SAME_OBSERVER_CONSECUTIVE} consecutive windows per observer")
    print(f"Diversity minimum: {MIN_OBSERVER_DIVERSITY} distinct operators")
    print(f"Escalation: {ESCALATION_CEREMONIES} ceremonies in {ESCALATION_WINDOW_DAYS} days → FAST_BALLOT")
    print()
    
    scenario_normal_rotation()
    scenario_circuit_break()
    scenario_escalation()
    scenario_insufficient_diversity()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Same observer = same cognitive frame = normalized deviance (Vaughan)")
    print("2. Dissimilar redundancy required (Reason 1997) — not copies of same system")
    print("3. Circuit breaker = OCSP hard-fail. No override without ceremony.")
    print("4. Ceremony resets counter but RECORDS breach. Receipt chain shows pattern.")
    print("5. 3 ceremonies in 90 days = chronic failure → escalate to FAST_BALLOT eviction.")
