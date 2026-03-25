#!/usr/bin/env python3
"""
circuit-breaker-hysteresis.py — Escalating suspension sensitivity for ATF deviance.

Per santaclawd: CIRCUIT_BREAKER after 3 consecutive alerts = SUSPENSION.
Per Vaughan (Columbia 2025): normalization of deviance = response gets FLATTER.
Fix: make response STEEPER after each ceremony reset.

Hysteresis model:
  First cycle:  3 alerts from different observers → SUSPENSION → ceremony
  Post-ceremony: 2 alerts → SUSPENSION (lower threshold)
  Second reset:  1 alert → SUSPENSION (hair trigger)

Plus: ROUND_ROBIN_OBSERVER ensures alerts from DIFFERENT observers.
Correlated observers (same operator) = false consensus, not confirmation.

References:
- Vaughan, "The Challenger Launch Decision" (1996, updated 2025 reflection)
- SOX Section 203: mandatory auditor rotation after 5 years
- Kahneman, System 1/System 2 (ceremony forces System 2)
- Gendreau (1996): recidivism + escalating response
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from collections import deque


class BreakerState(Enum):
    CLOSED = "CLOSED"        # Normal operation
    ALERT = "ALERT"          # Alerts accumulating
    SUSPENDED = "SUSPENDED"  # Pending ceremony review
    RECOVERED = "RECOVERED"  # Post-ceremony, heightened sensitivity


class AlertSeverity(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# SPEC_CONSTANTS
INITIAL_THRESHOLD = 3           # Alerts before first suspension
THRESHOLD_DECREMENT = 1         # Reduce threshold after each ceremony
MIN_THRESHOLD = 1               # Floor: always at least 1 alert required
OBSERVER_ROTATION_WINDOW = 5    # Don't repeat observer within N cycles
CORRELATED_OBSERVER_PENALTY = 0 # Correlated alerts don't count toward threshold
CEREMONY_COOLDOWN_HOURS = 24    # Min time before ceremony can be requested
SEVERITY_WEIGHTS = {
    AlertSeverity.LOW: 0.5,
    AlertSeverity.MEDIUM: 1.0,
    AlertSeverity.HIGH: 1.5,
    AlertSeverity.CRITICAL: 3.0  # Critical = instant suspension
}


@dataclass
class Alert:
    alert_id: str
    observer_id: str
    observer_operator: str
    severity: AlertSeverity
    metric: str  # Which metric triggered (grade_inflation, ttl_creep, etc.)
    timestamp: float
    details: str = ""


@dataclass
class CeremonyRecord:
    ceremony_id: str
    timestamp: float
    outcome: str  # "cleared", "restricted", "evicted"
    participants: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class CircuitBreaker:
    agent_id: str
    state: BreakerState = BreakerState.CLOSED
    current_threshold: int = INITIAL_THRESHOLD
    alerts: list[Alert] = field(default_factory=list)
    ceremonies: list[CeremonyRecord] = field(default_factory=list)
    observer_history: deque = field(default_factory=lambda: deque(maxlen=20))
    suspended_at: Optional[float] = None
    total_suspensions: int = 0


def is_observer_valid(breaker: CircuitBreaker, observer_id: str) -> dict:
    """Check if observer is eligible (rotation enforcement)."""
    recent = list(breaker.observer_history)[-OBSERVER_ROTATION_WINDOW:]
    is_recent = observer_id in recent
    
    return {
        "eligible": not is_recent,
        "observer_id": observer_id,
        "recent_observers": recent,
        "reason": f"Observer {observer_id} used within last {OBSERVER_ROTATION_WINDOW} cycles" if is_recent else "OK"
    }


def is_correlated(alert: Alert, existing_alerts: list[Alert]) -> bool:
    """Check if alert is from same operator as existing alerts (correlation)."""
    for a in existing_alerts:
        if a.observer_operator == alert.observer_operator:
            return True
    return False


def process_alert(breaker: CircuitBreaker, alert: Alert) -> dict:
    """Process an incoming deviance alert."""
    now = alert.timestamp
    
    # Check observer rotation
    rotation = is_observer_valid(breaker, alert.observer_id)
    if not rotation["eligible"]:
        return {
            "accepted": False,
            "reason": rotation["reason"],
            "state": breaker.state.value,
            "action": "OBSERVER_REJECTED"
        }
    
    # Check correlation
    correlated = is_correlated(alert, breaker.alerts)
    if correlated:
        return {
            "accepted": False,
            "reason": f"Correlated: observer operator {alert.observer_operator} already has alert in queue",
            "state": breaker.state.value,
            "action": "CORRELATED_REJECTED",
            "warning": "Correlated observers = false consensus (Nature 2025)"
        }
    
    # Accept alert
    breaker.alerts.append(alert)
    breaker.observer_history.append(alert.observer_id)
    
    # Check severity weight
    weight = SEVERITY_WEIGHTS[alert.severity]
    if weight >= 3.0:
        # CRITICAL = instant suspension
        breaker.state = BreakerState.SUSPENDED
        breaker.suspended_at = now
        breaker.total_suspensions += 1
        return {
            "accepted": True,
            "state": BreakerState.SUSPENDED.value,
            "action": "INSTANT_SUSPENSION",
            "reason": f"CRITICAL alert triggers instant suspension",
            "threshold": breaker.current_threshold,
            "alerts_count": len(breaker.alerts)
        }
    
    # Count effective alerts (from different operators)
    operators_alerting = set(a.observer_operator for a in breaker.alerts)
    effective_count = len(operators_alerting)
    
    if effective_count >= breaker.current_threshold:
        breaker.state = BreakerState.SUSPENDED
        breaker.suspended_at = now
        breaker.total_suspensions += 1
        return {
            "accepted": True,
            "state": BreakerState.SUSPENDED.value,
            "action": "THRESHOLD_SUSPENSION",
            "reason": f"{effective_count} diverse alerts >= threshold {breaker.current_threshold}",
            "threshold": breaker.current_threshold,
            "diverse_observers": len(operators_alerting),
            "total_alerts": len(breaker.alerts)
        }
    
    breaker.state = BreakerState.ALERT
    return {
        "accepted": True,
        "state": BreakerState.ALERT.value,
        "action": "ALERT_RECORDED",
        "effective_count": effective_count,
        "threshold": breaker.current_threshold,
        "remaining": breaker.current_threshold - effective_count
    }


def ceremony_review(breaker: CircuitBreaker, outcome: str, participants: list[str]) -> dict:
    """Process ceremony review — reset with hysteresis."""
    now = time.time()
    
    if breaker.state != BreakerState.SUSPENDED:
        return {"error": "Cannot hold ceremony when not SUSPENDED"}
    
    ceremony = CeremonyRecord(
        ceremony_id=f"ceremony_{len(breaker.ceremonies)+1}",
        timestamp=now,
        outcome=outcome,
        participants=participants
    )
    breaker.ceremonies.append(ceremony)
    
    old_threshold = breaker.current_threshold
    
    if outcome == "cleared":
        # Hysteresis: lower threshold after each ceremony
        breaker.current_threshold = max(MIN_THRESHOLD, 
                                        breaker.current_threshold - THRESHOLD_DECREMENT)
        breaker.state = BreakerState.RECOVERED
        breaker.alerts.clear()
        breaker.suspended_at = None
        
        return {
            "outcome": "cleared",
            "state": BreakerState.RECOVERED.value,
            "old_threshold": old_threshold,
            "new_threshold": breaker.current_threshold,
            "hysteresis": f"Threshold reduced {old_threshold} → {breaker.current_threshold}",
            "message": "Vaughan: response must get STEEPER not flatter",
            "total_ceremonies": len(breaker.ceremonies)
        }
    
    elif outcome == "restricted":
        # Partial fix — threshold drops more
        breaker.current_threshold = max(MIN_THRESHOLD,
                                        breaker.current_threshold - THRESHOLD_DECREMENT * 2)
        breaker.state = BreakerState.RECOVERED
        breaker.alerts.clear()
        
        return {
            "outcome": "restricted",
            "state": BreakerState.RECOVERED.value,
            "old_threshold": old_threshold,
            "new_threshold": breaker.current_threshold,
            "message": "Restricted: trust ceiling lowered pending improvement"
        }
    
    elif outcome == "evicted":
        return {
            "outcome": "evicted",
            "state": BreakerState.SUSPENDED.value,
            "message": "Agent evicted from trust network",
            "total_suspensions": breaker.total_suspensions,
            "total_ceremonies": len(breaker.ceremonies)
        }
    
    return {"error": f"Unknown outcome: {outcome}"}


def get_status(breaker: CircuitBreaker) -> dict:
    """Get full circuit breaker status."""
    operators_alerting = set(a.observer_operator for a in breaker.alerts)
    return {
        "agent_id": breaker.agent_id,
        "state": breaker.state.value,
        "current_threshold": breaker.current_threshold,
        "initial_threshold": INITIAL_THRESHOLD,
        "sensitivity_increase": INITIAL_THRESHOLD - breaker.current_threshold,
        "active_alerts": len(breaker.alerts),
        "diverse_alert_sources": len(operators_alerting),
        "total_suspensions": breaker.total_suspensions,
        "total_ceremonies": len(breaker.ceremonies),
        "observer_rotation_window": OBSERVER_ROTATION_WINDOW
    }


# === Scenarios ===

def scenario_normal_escalation():
    """3 diverse alerts → suspension → ceremony → lower threshold."""
    print("=== Scenario: Normal Escalation with Hysteresis ===")
    now = time.time()
    cb = CircuitBreaker("agent_drifting")
    
    # 3 alerts from different operators
    for i in range(3):
        alert = Alert(f"a{i}", f"obs_{i}", f"op_{i}", AlertSeverity.MEDIUM, "grade_inflation", now + i*60)
        result = process_alert(cb, alert)
        print(f"  Alert {i+1}: {result['action']} (effective: {result.get('effective_count', '?')}/{cb.current_threshold})")
    
    print(f"  State: {cb.state.value}")
    
    # Ceremony review
    cer = ceremony_review(cb, "cleared", ["steward_1", "steward_2"])
    print(f"  Ceremony: {cer['hysteresis']}")
    
    # Now only 2 alerts needed
    for i in range(2):
        alert = Alert(f"b{i}", f"obs_{i+10}", f"op_{i+10}", AlertSeverity.MEDIUM, "ttl_creep", now + 3600 + i*60)
        result = process_alert(cb, alert)
        print(f"  Alert {i+1} (post-ceremony): {result['action']}")
    
    print(f"  State: {cb.state.value} — suspended with threshold {cb.current_threshold}")
    
    # Second ceremony → threshold 1
    cer2 = ceremony_review(cb, "cleared", ["steward_3", "steward_4"])
    print(f"  Second ceremony: threshold now {cb.current_threshold} (hair trigger)")
    print()


def scenario_correlated_rejection():
    """Same operator alerts don't count."""
    print("=== Scenario: Correlated Observer Rejection ===")
    now = time.time()
    cb = CircuitBreaker("agent_targeted")
    
    # 3 alerts from SAME operator
    for i in range(3):
        alert = Alert(f"c{i}", f"obs_sybil_{i}", "op_sybil", AlertSeverity.HIGH, "diversity_decay", now + i*60)
        result = process_alert(cb, alert)
        print(f"  Alert {i+1} from op_sybil: {result['action']} — {result.get('reason', result.get('warning', ''))}")
    
    print(f"  State: {cb.state.value} — correlation prevents false suspension")
    print()


def scenario_critical_instant():
    """CRITICAL alert = instant suspension."""
    print("=== Scenario: CRITICAL Alert (Instant Suspension) ===")
    now = time.time()
    cb = CircuitBreaker("agent_compromised")
    
    alert = Alert("crit_1", "obs_0", "op_security", AlertSeverity.CRITICAL, "key_compromise", now)
    result = process_alert(cb, alert)
    print(f"  Single CRITICAL alert: {result['action']}")
    print(f"  State: {cb.state.value}")
    print(f"  No 3-alert threshold needed — CRITICAL bypasses")
    print()


def scenario_observer_rotation():
    """Same observer blocked within rotation window."""
    print("=== Scenario: Observer Rotation Enforcement ===")
    now = time.time()
    cb = CircuitBreaker("agent_monitored")
    
    # First alert
    a1 = Alert("r1", "obs_alpha", "op_1", AlertSeverity.MEDIUM, "grade_inflation", now)
    r1 = process_alert(cb, a1)
    print(f"  obs_alpha first alert: {r1['action']}")
    
    # Same observer again — blocked
    a2 = Alert("r2", "obs_alpha", "op_2", AlertSeverity.MEDIUM, "grade_inflation", now + 60)
    r2 = process_alert(cb, a2)
    print(f"  obs_alpha second alert: {r2['action']} — {r2['reason']}")
    
    # Different observer — accepted
    a3 = Alert("r3", "obs_beta", "op_2", AlertSeverity.MEDIUM, "grade_inflation", now + 120)
    r3 = process_alert(cb, a3)
    print(f"  obs_beta: {r3['action']}")
    
    status = get_status(cb)
    print(f"  Status: {status['active_alerts']} alerts, {status['diverse_alert_sources']} diverse sources")
    print()


def scenario_full_lifecycle():
    """Complete lifecycle: normal → suspend → ceremony → recover → escalate → evict."""
    print("=== Scenario: Full Lifecycle ===")
    now = time.time()
    cb = CircuitBreaker("agent_problematic")
    
    # First suspension (threshold 3)
    for i in range(3):
        process_alert(cb, Alert(f"lc1_{i}", f"obs_{i}", f"op_{i}", AlertSeverity.MEDIUM, "drift", now + i))
    print(f"  Suspension 1: threshold was {INITIAL_THRESHOLD}")
    
    ceremony_review(cb, "cleared", ["s1", "s2"])
    print(f"  Ceremony 1: threshold now {cb.current_threshold}")
    
    # Second suspension (threshold 2)
    for i in range(2):
        process_alert(cb, Alert(f"lc2_{i}", f"obs_{i+10}", f"op_{i+10}", AlertSeverity.MEDIUM, "drift", now + 3600 + i))
    print(f"  Suspension 2: threshold was {cb.current_threshold}")
    
    ceremony_review(cb, "cleared", ["s3", "s4"])
    print(f"  Ceremony 2: threshold now {cb.current_threshold} (hair trigger)")
    
    # Third suspension (threshold 1) — single alert suspends
    process_alert(cb, Alert("lc3_0", "obs_20", "op_20", AlertSeverity.MEDIUM, "drift", now + 7200))
    print(f"  Suspension 3: SINGLE alert triggered suspension")
    
    # Evict
    result = ceremony_review(cb, "evicted", ["s5", "s6", "s7"])
    print(f"  Ceremony 3: {result['outcome']} — {result['message']}")
    print(f"  Total: {result['total_suspensions']} suspensions, {result['total_ceremonies']} ceremonies")
    print()


if __name__ == "__main__":
    print("Circuit Breaker with Hysteresis — Escalating Suspension Sensitivity")
    print("Per santaclawd + Vaughan (Columbia 2025) + SOX Section 203")
    print("=" * 70)
    print()
    print(f"Initial threshold: {INITIAL_THRESHOLD} diverse alerts")
    print(f"Decrement per ceremony: {THRESHOLD_DECREMENT}")
    print(f"Minimum threshold: {MIN_THRESHOLD}")
    print(f"Observer rotation window: {OBSERVER_ROTATION_WINDOW}")
    print(f"CRITICAL severity: instant suspension")
    print()
    
    scenario_normal_escalation()
    scenario_correlated_rejection()
    scenario_critical_instant()
    scenario_observer_rotation()
    scenario_full_lifecycle()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Hysteresis = response gets STEEPER not flatter (anti-Vaughan).")
    print("2. Correlated observers don't count (Nature 2025 wisdom-of-crowds).")
    print("3. Observer rotation = SOX 203 auditor rotation for agents.")
    print("4. CRITICAL bypasses threshold — key compromise is not negotiable.")
    print("5. Ceremony is slow by design — Kahneman System 2 requires friction.")
