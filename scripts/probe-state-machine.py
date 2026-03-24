#!/usr/bin/env python3
"""
probe-state-machine.py — ATF receipt state machine with active probing.

Per santaclawd: silence-as-CONFIRMED is not a receipt type. PROBE closes ambiguity.
Per Chandra & Toueg (1996): eventually-strong failure detector (◇S).
Per FLP (1985): cannot distinguish crash from slow in bounded time.

State machine:
  SILENT → PROBE (T-hour active check)
  PROBE → CONFIRMED (ACK received)  
  PROBE → PROBE_TIMEOUT (no ACK in T_probe window)
  PROBE_TIMEOUT → DISPUTED (3 consecutive timeouts)
  PROBE_TIMEOUT → PROBE (retry, < 3 consecutive)

Key insight: PROBE makes the distinction between "confirmed" and "absent"
that silence alone cannot. FLP impossibility means this is the BEST
approximation — perfect detection is impossible.
"""

import time
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ReceiptState(Enum):
    SILENT = "SILENT"              # No receipt yet, no probe sent
    PROBE_SENT = "PROBE_SENT"      # Active probe dispatched
    CONFIRMED = "CONFIRMED"        # ACK received
    PROBE_TIMEOUT = "PROBE_TIMEOUT"  # Probe expired without ACK
    DISPUTED = "DISPUTED"          # 3+ consecutive timeouts
    FAILED = "FAILED"              # Explicit failure receipt


# SPEC_CONSTANTS
T_PROBE_DEFAULT_HOURS = 4        # Default probe interval
T_PROBE_TIMEOUT_HOURS = 1        # How long to wait for ACK
MAX_CONSECUTIVE_TIMEOUTS = 3     # Before escalating to DISPUTED
ADAPTIVE_FACTOR = 1.5            # Timeout grows on consecutive failures
MIN_PROBE_INTERVAL = 1           # Hours
MAX_PROBE_INTERVAL = 24          # Hours


@dataclass
class ProbeEvent:
    probe_id: str
    agent_id: str
    counterparty_id: str
    sent_at: float
    timeout_at: float
    ack_at: Optional[float] = None
    state: ReceiptState = ReceiptState.PROBE_SENT
    consecutive_timeouts: int = 0
    adaptive_timeout: float = T_PROBE_TIMEOUT_HOURS * 3600
    hash: str = ""

    def __post_init__(self):
        if not self.hash:
            self.hash = hashlib.sha256(
                f"{self.probe_id}:{self.agent_id}:{self.sent_at}".encode()
            ).hexdigest()[:16]


@dataclass
class AgentProbeState:
    """Per-counterparty probe tracking."""
    agent_id: str
    counterparty_id: str
    current_state: ReceiptState = ReceiptState.SILENT
    consecutive_timeouts: int = 0
    total_probes: int = 0
    total_acks: int = 0
    total_timeouts: int = 0
    last_confirmed_at: Optional[float] = None
    adaptive_timeout: float = T_PROBE_TIMEOUT_HOURS * 3600
    probe_history: list = field(default_factory=list)


def send_probe(state: AgentProbeState, now: float) -> ProbeEvent:
    """Send a probe and transition to PROBE_SENT."""
    probe = ProbeEvent(
        probe_id=f"probe_{state.total_probes:04d}",
        agent_id=state.agent_id,
        counterparty_id=state.counterparty_id,
        sent_at=now,
        timeout_at=now + state.adaptive_timeout,
        consecutive_timeouts=state.consecutive_timeouts,
        adaptive_timeout=state.adaptive_timeout
    )
    state.current_state = ReceiptState.PROBE_SENT
    state.total_probes += 1
    state.probe_history.append(probe)
    return probe


def receive_ack(state: AgentProbeState, probe: ProbeEvent, ack_time: float) -> dict:
    """Process ACK — transition to CONFIRMED."""
    probe.ack_at = ack_time
    probe.state = ReceiptState.CONFIRMED
    
    state.current_state = ReceiptState.CONFIRMED
    state.consecutive_timeouts = 0  # Reset
    state.total_acks += 1
    state.last_confirmed_at = ack_time
    
    # Adaptive: successful ACK reduces timeout toward default
    state.adaptive_timeout = max(
        T_PROBE_TIMEOUT_HOURS * 3600,
        state.adaptive_timeout * 0.8  # Shrink on success
    )
    
    latency = ack_time - probe.sent_at
    return {
        "transition": "PROBE_SENT → CONFIRMED",
        "latency_seconds": round(latency, 1),
        "consecutive_timeouts_reset": True,
        "ack_rate": round(state.total_acks / state.total_probes, 3) if state.total_probes > 0 else 0
    }


def handle_timeout(state: AgentProbeState, probe: ProbeEvent) -> dict:
    """Process timeout — escalate or retry."""
    probe.state = ReceiptState.PROBE_TIMEOUT
    state.total_timeouts += 1
    state.consecutive_timeouts += 1
    
    # Adaptive: grow timeout on consecutive failures (Chandra-Toueg)
    state.adaptive_timeout = min(
        MAX_PROBE_INTERVAL * 3600,
        state.adaptive_timeout * ADAPTIVE_FACTOR
    )
    
    if state.consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
        state.current_state = ReceiptState.DISPUTED
        return {
            "transition": f"PROBE_TIMEOUT → DISPUTED (consecutive={state.consecutive_timeouts})",
            "escalated": True,
            "reason": f"{MAX_CONSECUTIVE_TIMEOUTS} consecutive timeouts",
            "adaptive_timeout_hours": round(state.adaptive_timeout / 3600, 2),
            "ack_rate": round(state.total_acks / state.total_probes, 3) if state.total_probes > 0 else 0
        }
    else:
        state.current_state = ReceiptState.PROBE_TIMEOUT
        return {
            "transition": f"PROBE_TIMEOUT → RETRY ({state.consecutive_timeouts}/{MAX_CONSECUTIVE_TIMEOUTS})",
            "escalated": False,
            "retries_remaining": MAX_CONSECUTIVE_TIMEOUTS - state.consecutive_timeouts,
            "adaptive_timeout_hours": round(state.adaptive_timeout / 3600, 2)
        }


def assess_counterparty(state: AgentProbeState) -> dict:
    """Assess counterparty reliability from probe history."""
    if state.total_probes == 0:
        return {"grade": "UNKNOWN", "reason": "No probes sent"}
    
    ack_rate = state.total_acks / state.total_probes
    
    # Wilson CI lower bound
    from math import sqrt
    n = state.total_probes
    p = ack_rate
    z = 1.96
    denom = 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    spread = z * sqrt((p*(1-p) + z*z/(4*n)) / n) / denom
    wilson_lower = max(0, center - spread)
    
    if wilson_lower >= 0.9:
        grade = "RELIABLE"
    elif wilson_lower >= 0.7:
        grade = "RESPONSIVE"
    elif wilson_lower >= 0.4:
        grade = "INTERMITTENT"
    else:
        grade = "UNRELIABLE"
    
    return {
        "grade": grade,
        "ack_rate": round(ack_rate, 3),
        "wilson_lower": round(wilson_lower, 3),
        "total_probes": state.total_probes,
        "total_acks": state.total_acks,
        "consecutive_timeouts": state.consecutive_timeouts,
        "current_state": state.current_state.value
    }


# === Scenarios ===

def scenario_healthy_counterparty():
    """Responsive agent — all probes ACKed."""
    print("=== Scenario: Healthy Counterparty ===")
    now = time.time()
    state = AgentProbeState("kit_fox", "bro_agent")
    
    for i in range(10):
        probe = send_probe(state, now + i * 14400)  # Every 4 hours
        result = receive_ack(state, probe, now + i * 14400 + 120)  # ACK in 2 min
        print(f"  Probe {i}: {result['transition']} (latency: {result['latency_seconds']}s)")
    
    assessment = assess_counterparty(state)
    print(f"  Assessment: {assessment['grade']} (Wilson: {assessment['wilson_lower']}, ACK rate: {assessment['ack_rate']})")
    print()


def scenario_degrading_counterparty():
    """Agent starts responsive, then degrades."""
    print("=== Scenario: Degrading Counterparty ===")
    now = time.time()
    state = AgentProbeState("kit_fox", "degrading_agent")
    
    # First 5: healthy
    for i in range(5):
        probe = send_probe(state, now + i * 14400)
        result = receive_ack(state, probe, now + i * 14400 + 60)
        print(f"  Probe {i}: {result['transition']}")
    
    # Next 4: timeouts leading to DISPUTED
    for i in range(5, 9):
        probe = send_probe(state, now + i * 14400)
        result = handle_timeout(state, probe)
        print(f"  Probe {i}: {result['transition']} (adaptive timeout: {result['adaptive_timeout_hours']:.1f}h)")
        if result.get('escalated'):
            break
    
    assessment = assess_counterparty(state)
    print(f"  Assessment: {assessment['grade']} (Wilson: {assessment['wilson_lower']}, state: {assessment['current_state']})")
    print()


def scenario_flaky_network():
    """Intermittent ACKs — some succeed, some timeout."""
    print("=== Scenario: Flaky Network (Intermittent) ===")
    now = time.time()
    state = AgentProbeState("kit_fox", "flaky_agent")
    
    # Pattern: ACK, timeout, ACK, timeout, ACK, timeout, timeout, ACK
    pattern = [True, False, True, False, True, False, False, True, True, True]
    
    for i, ack in enumerate(pattern):
        probe = send_probe(state, now + i * 14400)
        if ack:
            result = receive_ack(state, probe, now + i * 14400 + 300)
            print(f"  Probe {i}: {result['transition']}")
        else:
            result = handle_timeout(state, probe)
            print(f"  Probe {i}: {result['transition']}")
    
    assessment = assess_counterparty(state)
    print(f"  Assessment: {assessment['grade']} (Wilson: {assessment['wilson_lower']}, consecutive: {assessment['consecutive_timeouts']})")
    print(f"  Key: intermittent resets consecutive counter — never reaches DISPUTED")
    print()


def scenario_crash_vs_byzantine():
    """Distinguish crash fault from Byzantine behavior."""
    print("=== Scenario: Crash vs Byzantine ===")
    now = time.time()
    
    # Crash: sudden stop, all subsequent probes timeout
    crash_state = AgentProbeState("kit_fox", "crashed_agent")
    for i in range(3):
        probe = send_probe(crash_state, now + i * 14400)
        receive_ack(crash_state, probe, now + i * 14400 + 30)
    for i in range(3, 7):
        probe = send_probe(crash_state, now + i * 14400)
        handle_timeout(crash_state, probe)
    
    crash_assessment = assess_counterparty(crash_state)
    
    # Byzantine: selective responses (responds to some, ignores others)
    byz_state = AgentProbeState("kit_fox", "byzantine_agent")
    byz_pattern = [True, True, False, True, False, False, True, False, True, False]
    for i, ack in enumerate(byz_pattern):
        probe = send_probe(byz_state, now + i * 14400)
        if ack:
            receive_ack(byz_state, probe, now + i * 14400 + 50)
        else:
            handle_timeout(byz_state, probe)
    
    byz_assessment = assess_counterparty(byz_state)
    
    print(f"  Crash:     {crash_assessment['grade']} (ACK: {crash_assessment['ack_rate']}, "
          f"consecutive: {crash_assessment['consecutive_timeouts']}, state: {crash_assessment['current_state']})")
    print(f"  Byzantine: {byz_assessment['grade']} (ACK: {byz_assessment['ack_rate']}, "
          f"consecutive: {byz_assessment['consecutive_timeouts']}, state: {byz_assessment['current_state']})")
    print(f"  Key: crash = clean split (all ACK then all timeout). Byzantine = intermittent.")
    print(f"  Chandra-Toueg: both eventually detected, crash faster (consecutive threshold).")
    print()


if __name__ == "__main__":
    print("Probe State Machine — ATF Receipt Verification via Active Probing")
    print("Per santaclawd + Chandra & Toueg (1996) + FLP (1985)")
    print("=" * 70)
    print()
    print("States: SILENT → PROBE_SENT → CONFIRMED | PROBE_TIMEOUT → DISPUTED")
    print(f"T_probe: {T_PROBE_DEFAULT_HOURS}h, T_timeout: {T_PROBE_TIMEOUT_HOURS}h, "
          f"MAX_CONSECUTIVE: {MAX_CONSECUTIVE_TIMEOUTS}")
    print()
    
    scenario_healthy_counterparty()
    scenario_degrading_counterparty()
    scenario_flaky_network()
    scenario_crash_vs_byzantine()
    
    print("=" * 70)
    print("KEY INSIGHT: FLP impossibility means perfect failure detection is impossible.")
    print("PROBE + adaptive timeout = best approximation (Chandra-Toueg ◇S).")
    print("3 consecutive timeouts → DISPUTED. Intermittent resets counter.")
    print("Crash faults detected faster than Byzantine (clean split vs intermittent).")
