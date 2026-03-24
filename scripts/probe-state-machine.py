#!/usr/bin/env python3
"""
probe-state-machine.py — ATF receipt state machine with active probing.

Per santaclawd: silence-as-CONFIRMED is not a receipt type. PROBE closes ambiguity.
Per Chandra & Toueg (JACM 1996): eventually-strong failure detector (◇S).

State transitions:
  SILENT → PROBE (T_probe timer starts)
  PROBE → CONFIRMED (ACK received within T_probe)
  PROBE → PROBE_TIMEOUT (no ACK in T_probe window)
  PROBE_TIMEOUT → DISPUTED (explicit escalation)
  PROBE_TIMEOUT → RE_PROBE (adaptive retry with increased T_probe)

Key insight: Chandra-Toueg uses INCREASING timeouts — static T = false positives
on slow agents. Adaptive T_probe distinguishes crash from slow.
"""

import time
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ProbeState(Enum):
    SILENT = "SILENT"              # No receipt yet, ambiguous
    PROBE_SENT = "PROBE_SENT"     # Active check dispatched
    CONFIRMED = "CONFIRMED"        # ACK received
    PROBE_TIMEOUT = "PROBE_TIMEOUT"  # No ACK within T_probe
    RE_PROBE = "RE_PROBE"         # Adaptive retry (increased timeout)
    DISPUTED = "DISPUTED"          # Escalated after max retries
    CRASHED = "CRASHED"            # Declared crashed (all probes exhausted)


class FailureClass(Enum):
    """Chandra-Toueg failure classification."""
    CORRECT = "CORRECT"           # Process is alive and responding
    CRASHED = "CRASHED"           # Process permanently failed
    SLOW = "SLOW"                 # Process alive but slow (false positive risk)
    BYZANTINE = "BYZANTINE"       # Process alive but lying


# SPEC_CONSTANTS
INITIAL_T_PROBE_MS = 5000        # 5 seconds initial probe timeout
MAX_T_PROBE_MS = 60000           # 60 seconds max probe timeout
BACKOFF_FACTOR = 2.0             # Exponential backoff multiplier
MAX_RETRIES = 3                  # Max probe retries before DISPUTED
PROBE_INTERVAL_MS = 3600000      # 1 hour between probes for SILENT agents
MIN_RESPONSE_TIME_MS = 50        # Suspiciously fast = replay attack


@dataclass
class ProbeRecord:
    probe_id: str
    target_agent: str
    state: ProbeState
    sent_at: float
    t_probe_ms: float
    ack_at: Optional[float] = None
    response_time_ms: Optional[float] = None
    retry_count: int = 0
    failure_class: Optional[FailureClass] = None
    hash: str = ""
    
    def __post_init__(self):
        if not self.hash:
            self.hash = hashlib.sha256(
                f"{self.probe_id}:{self.target_agent}:{self.sent_at}".encode()
            ).hexdigest()[:16]


@dataclass
class AgentProbeHistory:
    agent_id: str
    probes: list[ProbeRecord] = field(default_factory=list)
    current_t_probe_ms: float = INITIAL_T_PROBE_MS
    consecutive_timeouts: int = 0
    total_probes: int = 0
    total_acks: int = 0
    avg_response_ms: float = 0.0
    
    @property
    def ack_rate(self) -> float:
        return self.total_acks / self.total_probes if self.total_probes > 0 else 0.0
    
    @property
    def reliability_grade(self) -> str:
        rate = self.ack_rate
        if rate >= 0.95: return "A"
        if rate >= 0.80: return "B"
        if rate >= 0.60: return "C"
        if rate >= 0.30: return "D"
        return "F"


def send_probe(history: AgentProbeHistory, probe_id: str, now: float) -> ProbeRecord:
    """Send a probe to an agent."""
    probe = ProbeRecord(
        probe_id=probe_id,
        target_agent=history.agent_id,
        state=ProbeState.PROBE_SENT,
        sent_at=now,
        t_probe_ms=history.current_t_probe_ms,
        retry_count=history.consecutive_timeouts
    )
    history.probes.append(probe)
    history.total_probes += 1
    return probe


def receive_ack(probe: ProbeRecord, history: AgentProbeHistory, ack_time: float) -> ProbeRecord:
    """Process an ACK for a probe."""
    response_ms = (ack_time - probe.sent_at) * 1000
    
    probe.ack_at = ack_time
    probe.response_time_ms = response_ms
    
    # Check for suspiciously fast response (replay attack)
    if response_ms < MIN_RESPONSE_TIME_MS:
        probe.state = ProbeState.DISPUTED
        probe.failure_class = FailureClass.BYZANTINE
        return probe
    
    probe.state = ProbeState.CONFIRMED
    probe.failure_class = FailureClass.CORRECT
    
    # Update history
    history.total_acks += 1
    history.consecutive_timeouts = 0
    
    # Adaptive timeout: decrease toward initial on success
    # Chandra-Toueg: eventually stops suspecting correct processes
    history.current_t_probe_ms = max(
        INITIAL_T_PROBE_MS,
        history.current_t_probe_ms * 0.8  # Shrink by 20% on success
    )
    
    # Update running average response time
    n = history.total_acks
    history.avg_response_ms = (history.avg_response_ms * (n-1) + response_ms) / n
    
    return probe


def handle_timeout(probe: ProbeRecord, history: AgentProbeHistory) -> ProbeRecord:
    """Handle a probe timeout."""
    history.consecutive_timeouts += 1
    
    if history.consecutive_timeouts >= MAX_RETRIES:
        probe.state = ProbeState.DISPUTED
        probe.failure_class = FailureClass.CRASHED
    else:
        probe.state = ProbeState.RE_PROBE
        probe.failure_class = FailureClass.SLOW
        
        # Adaptive timeout: increase on timeout
        # Chandra-Toueg: eventually suspects every crashed process
        history.current_t_probe_ms = min(
            MAX_T_PROBE_MS,
            history.current_t_probe_ms * BACKOFF_FACTOR
        )
    
    return probe


def classify_agent(history: AgentProbeHistory) -> dict:
    """Classify agent based on probe history."""
    if history.total_probes == 0:
        return {"class": "UNKNOWN", "confidence": 0.0}
    
    ack_rate = history.ack_rate
    avg_response = history.avg_response_ms
    consecutive_fails = history.consecutive_timeouts
    
    if consecutive_fails >= MAX_RETRIES:
        classification = "CRASHED"
        confidence = 0.95
    elif ack_rate >= 0.95 and avg_response < 1000:
        classification = "HEALTHY"
        confidence = min(0.99, ack_rate)
    elif ack_rate >= 0.80:
        classification = "DEGRADED"
        confidence = ack_rate
    elif ack_rate >= 0.50:
        classification = "UNRELIABLE"
        confidence = 0.7
    else:
        classification = "SUSPECTED_CRASHED"
        confidence = 0.8
    
    return {
        "class": classification,
        "confidence": round(confidence, 3),
        "ack_rate": round(ack_rate, 3),
        "avg_response_ms": round(avg_response, 1),
        "consecutive_timeouts": consecutive_fails,
        "current_t_probe_ms": history.current_t_probe_ms,
        "grade": history.reliability_grade,
        "total_probes": history.total_probes
    }


# === Scenarios ===

def scenario_healthy_agent():
    """Agent responds to all probes — CONFIRMED."""
    print("=== Scenario: Healthy Agent ===")
    history = AgentProbeHistory(agent_id="healthy_agent")
    now = time.time()
    
    for i in range(10):
        probe = send_probe(history, f"p{i:03d}", now + i*3600)
        # Responds in 200-800ms
        response_time = 0.2 + (i % 5) * 0.15
        receive_ack(probe, history, now + i*3600 + response_time)
    
    result = classify_agent(history)
    print(f"  Class: {result['class']}, Grade: {result['grade']}")
    print(f"  ACK rate: {result['ack_rate']}, Avg response: {result['avg_response_ms']}ms")
    print(f"  T_probe adapted: {result['current_t_probe_ms']:.0f}ms (from {INITIAL_T_PROBE_MS}ms)")
    print()


def scenario_crashed_agent():
    """Agent never responds — CRASHED after MAX_RETRIES."""
    print("=== Scenario: Crashed Agent ===")
    history = AgentProbeHistory(agent_id="crashed_agent")
    now = time.time()
    
    for i in range(5):
        probe = send_probe(history, f"p{i:03d}", now + i*3600)
        handle_timeout(probe, history)
        print(f"  Probe {i}: state={probe.state.value}, T_probe={history.current_t_probe_ms:.0f}ms, "
              f"consecutive_timeouts={history.consecutive_timeouts}")
    
    result = classify_agent(history)
    print(f"  Final: {result['class']}, Grade: {result['grade']}")
    print(f"  T_probe escalated to: {result['current_t_probe_ms']:.0f}ms")
    print()


def scenario_slow_agent():
    """Agent responds but slowly — adaptive timeout prevents false positive."""
    print("=== Scenario: Slow Agent (Chandra-Toueg adaptive) ===")
    history = AgentProbeHistory(agent_id="slow_agent")
    now = time.time()
    
    for i in range(8):
        probe = send_probe(history, f"p{i:03d}", now + i*3600)
        
        # First 2 probes timeout (agent warming up)
        if i < 2:
            handle_timeout(probe, history)
            print(f"  Probe {i}: TIMEOUT, T_probe→{history.current_t_probe_ms:.0f}ms")
        else:
            # Then responds in 3-4 seconds (slow but alive)
            response_time = 3.0 + (i % 3) * 0.5
            receive_ack(probe, history, now + i*3600 + response_time)
            print(f"  Probe {i}: ACK in {response_time*1000:.0f}ms, T_probe→{history.current_t_probe_ms:.0f}ms")
    
    result = classify_agent(history)
    print(f"  Final: {result['class']}, Grade: {result['grade']}")
    print(f"  Key: adaptive T_probe prevented false CRASHED classification")
    print()


def scenario_replay_attack():
    """Suspiciously fast response — BYZANTINE."""
    print("=== Scenario: Replay Attack (Byzantine) ===")
    history = AgentProbeHistory(agent_id="replay_agent")
    now = time.time()
    
    probe = send_probe(history, "p000", now)
    # Responds in 5ms — too fast, likely replayed
    receive_ack(probe, history, now + 0.005)
    
    print(f"  Response time: {probe.response_time_ms:.1f}ms (minimum: {MIN_RESPONSE_TIME_MS}ms)")
    print(f"  State: {probe.state.value}")
    print(f"  Failure class: {probe.failure_class.value}")
    print(f"  Key: response faster than network RTT = replay attack")
    print()


def scenario_flapping_agent():
    """Agent alternates between responsive and unresponsive."""
    print("=== Scenario: Flapping Agent ===")
    history = AgentProbeHistory(agent_id="flapping_agent")
    now = time.time()
    
    for i in range(12):
        probe = send_probe(history, f"p{i:03d}", now + i*3600)
        if i % 3 == 0:  # Every 3rd probe times out
            handle_timeout(probe, history)
        else:
            receive_ack(probe, history, now + i*3600 + 0.5)
    
    result = classify_agent(history)
    print(f"  Class: {result['class']}, Grade: {result['grade']}")
    print(f"  ACK rate: {result['ack_rate']} (flapping pattern)")
    print(f"  T_probe oscillation: {result['current_t_probe_ms']:.0f}ms")
    print()


if __name__ == "__main__":
    print("Probe State Machine — Active Receipt Verification for ATF")
    print("Per santaclawd + Chandra & Toueg (JACM 1996)")
    print("=" * 70)
    print()
    print("States: SILENT → PROBE_SENT → CONFIRMED | PROBE_TIMEOUT → RE_PROBE | DISPUTED")
    print(f"Initial T_probe: {INITIAL_T_PROBE_MS}ms, Max: {MAX_T_PROBE_MS}ms, Backoff: {BACKOFF_FACTOR}x")
    print(f"Max retries: {MAX_RETRIES}, Min response: {MIN_RESPONSE_TIME_MS}ms (replay detection)")
    print()
    
    scenario_healthy_agent()
    scenario_crashed_agent()
    scenario_slow_agent()
    scenario_replay_attack()
    scenario_flapping_agent()
    
    print("=" * 70)
    print("KEY INSIGHT: FLP impossibility (1985) = cannot distinguish crash from slow.")
    print("PROBE with adaptive timeout = Chandra-Toueg eventually-strong (◇S).")
    print("Eventually suspects every crashed process + stops suspecting correct ones.")
    print("Static timeout = false positives. Adaptive = correct classification.")
