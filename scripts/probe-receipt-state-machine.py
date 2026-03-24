#!/usr/bin/env python3
"""
probe-receipt-state-machine.py — ATF receipt state machine with active PROBE.

Per santaclawd: silence-as-CONFIRMED is not a receipt type.
PROBE closes the ambiguity between crash and intentional silence.

State machine:
  SILENT → PROBE (T-hour active check)
  PROBE → CONFIRMED (ACK received within T_probe)
  PROBE → PROBE_TIMEOUT (no ACK in T_probe window)
  PROBE_TIMEOUT → DISPUTED (counterparty challenge or auto-escalate)
  CONFIRMED → EXPIRED (after max_age)

Per Chandra & Toueg (1996): eventually strong failure detector ◇S.
FLP impossibility (1985): cannot distinguish crash from slow in async.
PROBE makes the distinction OBSERVABLE.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import statistics


class ReceiptState(Enum):
    SILENT = "SILENT"               # No interaction yet
    PROBE_SENT = "PROBE_SENT"       # Active check dispatched
    CONFIRMED = "CONFIRMED"         # ACK received
    PROBE_TIMEOUT = "PROBE_TIMEOUT" # No ACK within window
    DISPUTED = "DISPUTED"           # Escalated from timeout
    EXPIRED = "EXPIRED"             # Past max_age


class ProbeResult(Enum):
    ACK = "ACK"
    NACK = "NACK"
    TIMEOUT = "TIMEOUT"
    PARTIAL = "PARTIAL"  # ACK received but incomplete


# SPEC_CONSTANTS
DEFAULT_T_PROBE_SECONDS = 3600      # 1 hour default probe window
MIN_T_PROBE_SECONDS = 300           # 5 min minimum
MAX_T_PROBE_SECONDS = 86400         # 24 hour maximum
ADAPTIVE_HISTORY_WINDOW = 20        # Last N responses for adaptive timeout
ADAPTIVE_MULTIPLIER = 2.0           # T_probe = 2 * median_response_time
PROBE_MAX_RETRIES = 3               # Retry before TIMEOUT
AUTO_ESCALATE_AFTER_TIMEOUTS = 3    # PROBE_TIMEOUT → DISPUTED after N


@dataclass
class ProbeEvent:
    probe_id: str
    target_agent: str
    sent_at: float
    ack_at: Optional[float] = None
    result: Optional[ProbeResult] = None
    response_time_ms: Optional[float] = None
    retry_count: int = 0
    
    @property
    def latency(self) -> Optional[float]:
        if self.ack_at and self.sent_at:
            return (self.ack_at - self.sent_at) * 1000  # ms
        return None


@dataclass
class AgentProbeHistory:
    agent_id: str
    response_times: list[float] = field(default_factory=list)  # ms
    timeout_count: int = 0
    ack_count: int = 0
    total_probes: int = 0
    current_state: ReceiptState = ReceiptState.SILENT
    consecutive_timeouts: int = 0
    
    @property
    def response_rate(self) -> float:
        return self.ack_count / self.total_probes if self.total_probes > 0 else 0.0
    
    @property
    def median_response_time(self) -> Optional[float]:
        if self.response_times:
            return statistics.median(self.response_times[-ADAPTIVE_HISTORY_WINDOW:])
        return None
    
    @property
    def adaptive_timeout(self) -> float:
        """Chandra-Toueg adaptive timeout: 2 * median response time."""
        median = self.median_response_time
        if median is not None:
            timeout_ms = ADAPTIVE_MULTIPLIER * median
            timeout_s = timeout_ms / 1000
            return max(MIN_T_PROBE_SECONDS, min(MAX_T_PROBE_SECONDS, timeout_s))
        return DEFAULT_T_PROBE_SECONDS


def transition(history: AgentProbeHistory, event: ProbeEvent) -> dict:
    """
    Process a probe event and transition state.
    Returns transition details.
    """
    old_state = history.current_state
    history.total_probes += 1
    
    if event.result == ProbeResult.ACK:
        history.current_state = ReceiptState.CONFIRMED
        history.ack_count += 1
        history.consecutive_timeouts = 0
        if event.latency is not None:
            history.response_times.append(event.latency)
        
        return {
            "transition": f"{old_state.value} → CONFIRMED",
            "latency_ms": event.latency,
            "adaptive_timeout_s": history.adaptive_timeout,
            "action": "RECEIPT_CONFIRMED"
        }
    
    elif event.result == ProbeResult.TIMEOUT:
        history.timeout_count += 1
        history.consecutive_timeouts += 1
        
        if history.consecutive_timeouts >= AUTO_ESCALATE_AFTER_TIMEOUTS:
            history.current_state = ReceiptState.DISPUTED
            return {
                "transition": f"{old_state.value} → DISPUTED",
                "consecutive_timeouts": history.consecutive_timeouts,
                "action": "AUTO_ESCALATE",
                "reason": f"{history.consecutive_timeouts} consecutive timeouts (threshold: {AUTO_ESCALATE_AFTER_TIMEOUTS})"
            }
        else:
            history.current_state = ReceiptState.PROBE_TIMEOUT
            return {
                "transition": f"{old_state.value} → PROBE_TIMEOUT",
                "consecutive_timeouts": history.consecutive_timeouts,
                "action": "RETRY_PROBE",
                "retries_remaining": AUTO_ESCALATE_AFTER_TIMEOUTS - history.consecutive_timeouts
            }
    
    elif event.result == ProbeResult.NACK:
        history.current_state = ReceiptState.DISPUTED
        return {
            "transition": f"{old_state.value} → DISPUTED",
            "action": "EXPLICIT_REJECTION",
            "reason": "Counterparty explicitly rejected"
        }
    
    elif event.result == ProbeResult.PARTIAL:
        # Partial = CONFIRMED with degraded grade
        history.current_state = ReceiptState.CONFIRMED
        history.ack_count += 1
        if event.latency is not None:
            history.response_times.append(event.latency)
        return {
            "transition": f"{old_state.value} → CONFIRMED (DEGRADED)",
            "action": "RECEIPT_CONFIRMED_DEGRADED",
            "reason": "Partial response — incomplete attestation"
        }
    
    return {"transition": "NO_CHANGE", "action": "UNKNOWN"}


def assess_agent(history: AgentProbeHistory) -> dict:
    """Assess agent health based on probe history."""
    rate = history.response_rate
    median = history.median_response_time
    
    if rate >= 0.95 and history.consecutive_timeouts == 0:
        health = "HEALTHY"
    elif rate >= 0.80:
        health = "DEGRADED"
    elif rate >= 0.50:
        health = "UNRELIABLE"
    else:
        health = "UNRESPONSIVE"
    
    # Chandra-Toueg classification
    if history.consecutive_timeouts >= AUTO_ESCALATE_AFTER_TIMEOUTS:
        failure_class = "SUSPECTED_CRASH"
    elif history.timeout_count > 0 and history.ack_count > 0:
        failure_class = "INTERMITTENT"  # Slow, not crashed
    elif history.total_probes == 0:
        failure_class = "UNKNOWN"
    else:
        failure_class = "OPERATIONAL"
    
    return {
        "agent_id": history.agent_id,
        "health": health,
        "failure_class": failure_class,
        "response_rate": round(rate, 3),
        "median_response_ms": round(median, 1) if median else None,
        "adaptive_timeout_s": round(history.adaptive_timeout, 1),
        "total_probes": history.total_probes,
        "consecutive_timeouts": history.consecutive_timeouts,
        "state": history.current_state.value
    }


# === Scenarios ===

def scenario_healthy_agent():
    """Agent responds consistently — adaptive timeout tightens."""
    print("=== Scenario: Healthy Agent ===")
    now = time.time()
    history = AgentProbeHistory(agent_id="reliable_agent")
    
    for i in range(10):
        latency = 200 + (i * 10)  # ms, slightly increasing
        event = ProbeEvent(
            probe_id=f"probe_{i}",
            target_agent="reliable_agent",
            sent_at=now + i * 3600,
            ack_at=now + i * 3600 + latency / 1000,
            result=ProbeResult.ACK,
            response_time_ms=latency
        )
        result = transition(history, event)
        if i % 3 == 0:
            print(f"  Probe {i}: {result['transition']} latency={latency}ms "
                  f"adaptive_timeout={result['adaptive_timeout_s']:.0f}s")
    
    assessment = assess_agent(history)
    print(f"  Assessment: {assessment['health']} ({assessment['failure_class']})")
    print(f"  Response rate: {assessment['response_rate']}, "
          f"Median: {assessment['median_response_ms']}ms")
    print()


def scenario_degrading_agent():
    """Agent gets slower, then times out — escalation to DISPUTED."""
    print("=== Scenario: Degrading → Timeout → DISPUTED ===")
    now = time.time()
    history = AgentProbeHistory(agent_id="degrading_agent")
    
    # 5 normal responses
    for i in range(5):
        event = ProbeEvent(
            probe_id=f"probe_{i}", target_agent="degrading_agent",
            sent_at=now + i * 3600, ack_at=now + i * 3600 + 0.5,
            result=ProbeResult.ACK, response_time_ms=500
        )
        transition(history, event)
    
    # 3 timeouts → auto-escalate
    for i in range(5, 8):
        event = ProbeEvent(
            probe_id=f"probe_{i}", target_agent="degrading_agent",
            sent_at=now + i * 3600,
            result=ProbeResult.TIMEOUT
        )
        result = transition(history, event)
        print(f"  Probe {i}: {result['transition']} — {result['action']}")
    
    assessment = assess_agent(history)
    print(f"  Assessment: {assessment['health']} ({assessment['failure_class']})")
    print(f"  State: {assessment['state']}")
    print()


def scenario_intermittent_failures():
    """Agent has occasional timeouts but recovers — INTERMITTENT class."""
    print("=== Scenario: Intermittent Failures ===")
    now = time.time()
    history = AgentProbeHistory(agent_id="flaky_agent")
    
    pattern = [ProbeResult.ACK, ProbeResult.ACK, ProbeResult.TIMEOUT,
               ProbeResult.ACK, ProbeResult.ACK, ProbeResult.ACK,
               ProbeResult.TIMEOUT, ProbeResult.ACK, ProbeResult.ACK, ProbeResult.ACK]
    
    for i, result_type in enumerate(pattern):
        event = ProbeEvent(
            probe_id=f"probe_{i}", target_agent="flaky_agent",
            sent_at=now + i * 3600,
            ack_at=now + i * 3600 + 0.3 if result_type == ProbeResult.ACK else None,
            result=result_type,
            response_time_ms=300 if result_type == ProbeResult.ACK else None
        )
        result = transition(history, event)
    
    assessment = assess_agent(history)
    print(f"  Pattern: {''.join('✓' if r == ProbeResult.ACK else '✗' for r in pattern)}")
    print(f"  Assessment: {assessment['health']} ({assessment['failure_class']})")
    print(f"  Response rate: {assessment['response_rate']}")
    print(f"  Consecutive timeouts: {assessment['consecutive_timeouts']} (resets on ACK)")
    print()


def scenario_explicit_rejection():
    """Agent sends NACK — immediate DISPUTED."""
    print("=== Scenario: Explicit Rejection (NACK) ===")
    now = time.time()
    history = AgentProbeHistory(agent_id="hostile_agent")
    
    event = ProbeEvent(
        probe_id="probe_0", target_agent="hostile_agent",
        sent_at=now, result=ProbeResult.NACK
    )
    result = transition(history, event)
    
    print(f"  {result['transition']} — {result['action']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Key: NACK is information. Silence is not. PROBE converts silence to signal.")
    print()


if __name__ == "__main__":
    print("Probe Receipt State Machine — Active Failure Detection for ATF")
    print("Per santaclawd + Chandra & Toueg (1996) + FLP (1985)")
    print("=" * 70)
    print()
    print("State machine: SILENT → PROBE → CONFIRMED | PROBE_TIMEOUT → DISPUTED")
    print(f"Adaptive timeout: {ADAPTIVE_MULTIPLIER}x median response time")
    print(f"Auto-escalate after {AUTO_ESCALATE_AFTER_TIMEOUTS} consecutive timeouts")
    print()
    
    scenario_healthy_agent()
    scenario_degrading_agent()
    scenario_intermittent_failures()
    scenario_explicit_rejection()
    
    print("=" * 70)
    print("KEY INSIGHT: PROBE converts silence from ambiguity to signal.")
    print("FLP says we cannot distinguish crash from slow. PROBE makes it observable.")
    print("Adaptive timeout (Chandra-Toueg) tightens with history.")
    print("NACK > TIMEOUT > SILENCE — information density increases left to right.")
