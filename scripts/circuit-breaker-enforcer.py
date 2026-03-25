#!/usr/bin/env python3
"""
circuit-breaker-enforcer.py — Automated enforcement for ATF SPEC_CONSTANT deviations.

Per santaclawd: "the O-ring engineers KNEW. paperwork said acceptable. that gap is where systems die."
Per drainfun: "the people closest to the deviance stop seeing it."
Per Vaughan (Columbia 1996/2025): normalization of deviance = rational incremental drift.

Key insight: DEVIANCE_ALERT without enforcement = OCSP soft-fail.
3 consecutive alerts on same constant = CIRCUIT_BREAKER trips → automatic SUSPENSION.
No human override without ceremony (quorum of 5/14 witnesses).

Parallels:
- NYSE circuit breakers (SEC Rule 80B): 7%/13%/20% thresholds, escalating halt
- Sarbanes-Oxley Section 203: 5-year mandatory auditor rotation
- Michael Nygard (Release It!, 2007): circuit breaker pattern for cascading failures
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BreakerState(Enum):
    CLOSED = "CLOSED"           # Normal operation
    HALF_OPEN = "HALF_OPEN"     # Testing after trip (1 probe allowed)
    OPEN = "OPEN"               # Tripped — operations suspended
    LOCKED_OPEN = "LOCKED_OPEN" # Ceremony required to reset


class AlertSeverity(Enum):
    WARNING = "WARNING"       # Approaching threshold
    BREACH = "BREACH"         # Threshold exceeded
    CRITICAL = "CRITICAL"     # Sustained breach (3+ consecutive)


class SpecConstant(Enum):
    MIN_COUNTERPARTY_CLASSES = "MIN_COUNTERPARTY_CLASSES"
    WILSON_CI_FLOOR = "WILSON_CI_FLOOR"
    RECENCY_HALFLIFE_DAYS = "RECENCY_HALFLIFE_DAYS"
    MAX_STALE_TRANSACTIONS = "MAX_STALE_TRANSACTIONS"
    PROPAGATION_THRESHOLD = "PROPAGATION_THRESHOLD"
    GRADE_CEILING_DELTA = "GRADE_CEILING_DELTA"
    OVERLAP_RATIO = "OVERLAP_RATIO"
    EMERGENCY_WITNESS_THRESHOLD = "EMERGENCY_WITNESS_THRESHOLD"


# SPEC_CONSTANTS for the circuit breaker itself
CONSECUTIVE_BREACH_TRIP = 3          # Breaches before trip
WARNING_THRESHOLD_RATIO = 0.80       # 80% of limit = warning
HALF_OPEN_PROBE_INTERVAL = 3600      # 1 hour between probes
CEREMONY_QUORUM = 5                  # of 14 witnesses to reset LOCKED_OPEN
MAX_HALF_OPEN_PROBES = 3             # Probes before auto-lock
NYSE_LEVEL_1_PCT = 0.07              # 7% = 15-min halt
NYSE_LEVEL_2_PCT = 0.13              # 13% = 15-min halt
NYSE_LEVEL_3_PCT = 0.20              # 20% = market closed


@dataclass
class DevianceAlert:
    constant: SpecConstant
    observed_value: float
    expected_value: float
    deviation_pct: float
    severity: AlertSeverity
    timestamp: float
    context: str = ""


@dataclass
class CircuitBreaker:
    constant: SpecConstant
    state: BreakerState = BreakerState.CLOSED
    consecutive_breaches: int = 0
    total_breaches: int = 0
    total_warnings: int = 0
    last_trip_at: Optional[float] = None
    last_reset_at: Optional[float] = None
    half_open_probes: int = 0
    alerts: list[DevianceAlert] = field(default_factory=list)
    
    def trip_count(self) -> int:
        """Total times this breaker has tripped."""
        return sum(1 for a in self.alerts if a.severity == AlertSeverity.CRITICAL)


@dataclass
class CeremonyReset:
    breaker_constant: SpecConstant
    requested_at: float
    witnesses: list[str] = field(default_factory=list)
    votes_for: int = 0
    votes_against: int = 0
    approved: bool = False


def evaluate_constant(breaker: CircuitBreaker, observed: float, expected: float, 
                      context: str = "") -> DevianceAlert:
    """Evaluate a SPEC_CONSTANT and generate alert if needed."""
    now = time.time()
    
    if expected == 0:
        deviation_pct = 1.0 if observed != 0 else 0.0
    else:
        deviation_pct = abs(observed - expected) / abs(expected)
    
    # Determine severity
    if deviation_pct >= 1.0:
        severity = AlertSeverity.CRITICAL
    elif deviation_pct > 0:
        severity = AlertSeverity.BREACH
    elif deviation_pct >= WARNING_THRESHOLD_RATIO:
        severity = AlertSeverity.WARNING
    else:
        severity = AlertSeverity.WARNING
    
    # Check if this is an actual breach (observed violates expected)
    is_breach = observed != expected and deviation_pct > 0
    
    alert = DevianceAlert(
        constant=breaker.constant,
        observed_value=observed,
        expected_value=expected,
        deviation_pct=round(deviation_pct, 4),
        severity=severity if is_breach else AlertSeverity.WARNING,
        timestamp=now,
        context=context
    )
    
    breaker.alerts.append(alert)
    
    if is_breach:
        breaker.consecutive_breaches += 1
        breaker.total_breaches += 1
    else:
        breaker.consecutive_breaches = 0  # Reset on compliance
    
    return alert


def check_trip(breaker: CircuitBreaker) -> dict:
    """Check if circuit breaker should trip."""
    if breaker.state == BreakerState.LOCKED_OPEN:
        return {"action": "LOCKED", "reason": "Ceremony required to reset"}
    
    if breaker.state == BreakerState.OPEN:
        # Check if enough time for half-open probe
        if breaker.last_trip_at:
            elapsed = time.time() - breaker.last_trip_at
            if elapsed >= HALF_OPEN_PROBE_INTERVAL:
                breaker.state = BreakerState.HALF_OPEN
                return {"action": "HALF_OPEN", "reason": "Probe window opened"}
        return {"action": "SUSPENDED", "reason": "Breaker OPEN, waiting for probe window"}
    
    if breaker.state == BreakerState.HALF_OPEN:
        if breaker.consecutive_breaches > 0:
            # Probe failed
            breaker.half_open_probes += 1
            if breaker.half_open_probes >= MAX_HALF_OPEN_PROBES:
                breaker.state = BreakerState.LOCKED_OPEN
                return {"action": "LOCKED_OPEN", 
                        "reason": f"Failed {MAX_HALF_OPEN_PROBES} probes. Ceremony required.",
                        "probes_failed": breaker.half_open_probes}
            breaker.state = BreakerState.OPEN
            breaker.last_trip_at = time.time()
            return {"action": "RE_TRIPPED", "reason": "Probe failed, back to OPEN",
                    "probes_remaining": MAX_HALF_OPEN_PROBES - breaker.half_open_probes}
        else:
            # Probe passed
            breaker.state = BreakerState.CLOSED
            breaker.half_open_probes = 0
            breaker.last_reset_at = time.time()
            return {"action": "RESET", "reason": "Probe passed, breaker CLOSED"}
    
    # CLOSED state — check for trip
    if breaker.consecutive_breaches >= CONSECUTIVE_BREACH_TRIP:
        breaker.state = BreakerState.OPEN
        breaker.last_trip_at = time.time()
        
        # NYSE-style escalation
        nyse_level = "LEVEL_1"
        if breaker.trip_count() >= 3:
            nyse_level = "LEVEL_3"
            breaker.state = BreakerState.LOCKED_OPEN
        elif breaker.trip_count() >= 2:
            nyse_level = "LEVEL_2"
        
        return {
            "action": "TRIPPED",
            "reason": f"{breaker.consecutive_breaches} consecutive breaches",
            "nyse_level": nyse_level,
            "state": breaker.state.value,
            "total_trips": breaker.trip_count()
        }
    
    return {"action": "OK", "consecutive": breaker.consecutive_breaches,
            "remaining": CONSECUTIVE_BREACH_TRIP - breaker.consecutive_breaches}


def request_ceremony_reset(breaker: CircuitBreaker, witnesses: list[tuple[str, bool]]) -> CeremonyReset:
    """Request ceremony to reset a LOCKED_OPEN breaker."""
    ceremony = CeremonyReset(
        breaker_constant=breaker.constant,
        requested_at=time.time(),
        witnesses=[w[0] for w in witnesses],
        votes_for=sum(1 for _, v in witnesses if v),
        votes_against=sum(1 for _, v in witnesses if not v)
    )
    
    ceremony.approved = ceremony.votes_for >= CEREMONY_QUORUM
    
    if ceremony.approved:
        breaker.state = BreakerState.CLOSED
        breaker.consecutive_breaches = 0
        breaker.half_open_probes = 0
        breaker.last_reset_at = time.time()
    
    return ceremony


# === Scenarios ===

def scenario_gradual_drift():
    """Grade inflation over time — 3 breaches → trip."""
    print("=== Scenario: Gradual Grade Inflation (Vaughan Pattern) ===")
    breaker = CircuitBreaker(SpecConstant.WILSON_CI_FLOOR)
    
    # 5 evaluations: normal, normal, breach, breach, breach → trip
    evaluations = [
        (0.60, 0.60, "Quarter 1: normal"),
        (0.58, 0.60, "Quarter 2: slight drift"),
        (0.45, 0.60, "Quarter 3: breach - grades inflated"),
        (0.40, 0.60, "Quarter 4: sustained breach"),
        (0.35, 0.60, "Quarter 5: critical drift"),
    ]
    
    for observed, expected, ctx in evaluations:
        alert = evaluate_constant(breaker, observed, expected, ctx)
        trip = check_trip(breaker)
        print(f"  {ctx}: observed={observed} expected={expected} "
              f"severity={alert.severity.value} consecutive={breaker.consecutive_breaches} "
              f"→ {trip['action']}")
    
    print(f"  Final state: {breaker.state.value}")
    print()


def scenario_probe_recovery():
    """Breaker trips, then recovers through half-open probe."""
    print("=== Scenario: Trip + Probe Recovery ===")
    breaker = CircuitBreaker(SpecConstant.MAX_STALE_TRANSACTIONS)
    
    # Trip it
    for i in range(3):
        evaluate_constant(breaker, 5, 3, f"Breach {i+1}")
    trip = check_trip(breaker)
    print(f"  Tripped: {trip['action']} — {trip['reason']}")
    
    # Wait for probe window
    breaker.last_trip_at = time.time() - HALF_OPEN_PROBE_INTERVAL - 1
    probe1 = check_trip(breaker)
    print(f"  Probe window: {probe1['action']}")
    
    # Probe passes (compliant observation)
    evaluate_constant(breaker, 3, 3, "Probe: compliant")
    result = check_trip(breaker)
    print(f"  Probe result: {result['action']} — {result['reason']}")
    print(f"  State: {breaker.state.value}")
    print()


def scenario_locked_open_ceremony():
    """Multiple trips → LOCKED_OPEN → ceremony reset."""
    print("=== Scenario: LOCKED_OPEN → Ceremony Reset ===")
    breaker = CircuitBreaker(SpecConstant.PROPAGATION_THRESHOLD)
    
    # Trip 3 times (each time 3 consecutive breaches)
    for trip_num in range(3):
        for i in range(3):
            evaluate_constant(breaker, 0.50, 0.80, f"Trip {trip_num+1} breach {i+1}")
        result = check_trip(breaker)
        if breaker.state == BreakerState.LOCKED_OPEN:
            print(f"  Trip {trip_num+1}: {result['action']} — {result.get('nyse_level', '')}")
            break
        else:
            print(f"  Trip {trip_num+1}: {result['action']} — {result.get('nyse_level', '')}")
            # Reset for next trip cycle
            breaker.state = BreakerState.CLOSED
            breaker.consecutive_breaches = 0
    
    print(f"  State: {breaker.state.value}")
    
    # Ceremony with insufficient quorum
    witnesses_low = [(f"w{i}", i < 3) for i in range(10)]  # Only 3 yes
    ceremony1 = request_ceremony_reset(breaker, witnesses_low)
    print(f"  Ceremony (3/10 yes): approved={ceremony1.approved}")
    
    # Ceremony with sufficient quorum
    witnesses_high = [(f"w{i}", i < 7) for i in range(10)]  # 7 yes
    ceremony2 = request_ceremony_reset(breaker, witnesses_high)
    print(f"  Ceremony (7/10 yes): approved={ceremony2.approved}")
    print(f"  State after ceremony: {breaker.state.value}")
    print()


def scenario_nyse_escalation():
    """NYSE-style escalating halts."""
    print("=== Scenario: NYSE-Style Escalating Halts ===")
    print(f"  Level 1 ({NYSE_LEVEL_1_PCT:.0%}): 15-min halt → OPEN (probe after interval)")
    print(f"  Level 2 ({NYSE_LEVEL_2_PCT:.0%}): 15-min halt → OPEN (shorter probe window)")
    print(f"  Level 3 ({NYSE_LEVEL_3_PCT:.0%}): Market closed → LOCKED_OPEN (ceremony required)")
    print()
    print("  ATF mapping:")
    print("    Level 1 = first trip: OPEN, auto-recovery possible")
    print("    Level 2 = second trip: OPEN, tighter probe")
    print("    Level 3 = third trip: LOCKED_OPEN, ceremony only")
    print("    Each level = evidence that self-correction failed")
    print()


if __name__ == "__main__":
    print("Circuit Breaker Enforcer — Automated SPEC_CONSTANT Enforcement for ATF")
    print("Per santaclawd + Vaughan (1996/2025) + Nygard (Release It!, 2007)")
    print("=" * 70)
    print()
    print(f"Trip threshold: {CONSECUTIVE_BREACH_TRIP} consecutive breaches")
    print(f"Probe interval: {HALF_OPEN_PROBE_INTERVAL}s")
    print(f"Max probes before lock: {MAX_HALF_OPEN_PROBES}")
    print(f"Ceremony quorum: {CEREMONY_QUORUM}/14 witnesses")
    print()
    
    scenario_gradual_drift()
    scenario_probe_recovery()
    scenario_locked_open_ceremony()
    scenario_nyse_escalation()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Alert without enforcement = OCSP soft-fail. Circuit breaker IS enforcement.")
    print("2. NYSE escalation: repeated trips → escalating severity → ceremony lock.")
    print("3. Vaughan: the paperwork said acceptable. Automated trip removes human override.")
    print("4. SOX 203: observer rotation. Fresh verifiers > long-tenured ones.")
    print("5. LOCKED_OPEN = no human override without ceremony. The ceremony IS the control.")
