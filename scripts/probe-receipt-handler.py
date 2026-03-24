#!/usr/bin/env python3
"""
probe-receipt-handler.py — Liveness detection via PROBE receipts for ATF.

Per santaclawd + funwolf: silence-as-CONFIRMED fails on network partition.
Per Aguilera, Chen, Toueg (2001): heartbeat failure detector without timeouts.
Per Chandra & Toueg (1996): unreliable failure detectors for consensus.

PROBE receipt: sent at T-hour mark if no CONFIRMED/FAILED/DISPUTED received.
Custodian ACKs or silence → escalation.

Four receipt types in ATF:
  CONFIRMED — Bilateral agreement, co-signed
  FAILED    — Explicit failure, evidence attached
  DISPUTED  — Explicit disagreement, escalation
  PROBE     — Liveness check, requires ACK

PROBE escalation: PROBE → ACK (alive) | SUSPECTED (no ACK) → 3x SUSPECTED → DISPUTED
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ReceiptType(Enum):
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    DISPUTED = "DISPUTED"
    PROBE = "PROBE"
    ACK = "ACK"
    SUSPECTED = "SUSPECTED"


class ProbeResult(Enum):
    ALIVE = "ALIVE"           # ACK received within window
    SUSPECTED = "SUSPECTED"   # No ACK, possibly partition
    ESCALATED = "ESCALATED"   # 3+ consecutive SUSPECTED → DISPUTED
    CRASHED = "CRASHED"       # Extended silence + probe failure


# SPEC_CONSTANTS
PROBE_INTERVAL_HOURS = 4        # Send PROBE every T hours if silent
ACK_WINDOW_HOURS = 2            # T/2 window for ACK response
SUSPECTED_THRESHOLD = 3         # Consecutive SUSPECTED before DISPUTED
CRASH_THRESHOLD_HOURS = 72      # Extended silence = CRASHED
MAX_PROBE_RETRIES = 5           # Max probes before giving up


@dataclass
class ProbeReceipt:
    probe_id: str
    target_agent: str
    sender_agent: str
    sent_at: float
    ack_deadline: float        # sent_at + ACK_WINDOW_HOURS
    ack_received_at: Optional[float] = None
    result: ProbeResult = ProbeResult.SUSPECTED
    probe_hash: str = ""
    sequence: int = 0
    
    def __post_init__(self):
        if not self.probe_hash:
            h = hashlib.sha256(
                f"{self.probe_id}:{self.target_agent}:{self.sent_at}:{self.sequence}".encode()
            ).hexdigest()[:16]
            self.probe_hash = h


@dataclass
class AgentLivenessState:
    agent_id: str
    last_confirmed_at: float          # Last CONFIRMED/FAILED/DISPUTED receipt
    consecutive_suspected: int = 0
    total_probes_sent: int = 0
    total_acks_received: int = 0
    status: str = "ALIVE"
    probe_history: list = field(default_factory=list)
    
    @property
    def ack_rate(self) -> float:
        if self.total_probes_sent == 0:
            return 1.0
        return self.total_acks_received / self.total_probes_sent
    
    @property
    def silence_hours(self) -> float:
        return (time.time() - self.last_confirmed_at) / 3600


def should_probe(state: AgentLivenessState, now: float) -> bool:
    """Determine if a PROBE should be sent."""
    silence = (now - state.last_confirmed_at) / 3600
    if silence < PROBE_INTERVAL_HOURS:
        return False
    if state.status == "CRASHED":
        return False
    if state.total_probes_sent >= MAX_PROBE_RETRIES and state.consecutive_suspected >= SUSPECTED_THRESHOLD:
        return False
    return True


def send_probe(state: AgentLivenessState, now: float) -> ProbeReceipt:
    """Create and send a PROBE receipt."""
    probe = ProbeReceipt(
        probe_id=f"probe_{state.agent_id}_{state.total_probes_sent}",
        target_agent=state.agent_id,
        sender_agent="monitor",
        sent_at=now,
        ack_deadline=now + (ACK_WINDOW_HOURS * 3600),
        sequence=state.total_probes_sent
    )
    state.total_probes_sent += 1
    state.probe_history.append(probe)
    return probe


def process_ack(state: AgentLivenessState, probe: ProbeReceipt, ack_time: float) -> dict:
    """Process an ACK response to a PROBE."""
    if ack_time <= probe.ack_deadline:
        probe.ack_received_at = ack_time
        probe.result = ProbeResult.ALIVE
        state.total_acks_received += 1
        state.consecutive_suspected = 0
        state.status = "ALIVE"
        state.last_confirmed_at = ack_time
        return {"result": "ALIVE", "latency_ms": int((ack_time - probe.sent_at) * 1000)}
    else:
        # Late ACK — still alive but slow
        probe.ack_received_at = ack_time
        probe.result = ProbeResult.ALIVE
        state.total_acks_received += 1
        state.consecutive_suspected = 0
        state.status = "ALIVE"
        state.last_confirmed_at = ack_time
        return {"result": "ALIVE_LATE", "latency_ms": int((ack_time - probe.sent_at) * 1000),
                "late_by_hours": round((ack_time - probe.ack_deadline) / 3600, 2)}


def process_timeout(state: AgentLivenessState, probe: ProbeReceipt, now: float) -> dict:
    """Process a PROBE timeout (no ACK received)."""
    if now > probe.ack_deadline and probe.ack_received_at is None:
        probe.result = ProbeResult.SUSPECTED
        state.consecutive_suspected += 1
        
        if state.consecutive_suspected >= SUSPECTED_THRESHOLD:
            state.status = "ESCALATED"
            probe.result = ProbeResult.ESCALATED
            return {
                "result": "ESCALATED",
                "consecutive_suspected": state.consecutive_suspected,
                "action": "GENERATE_DISPUTED_RECEIPT",
                "silence_hours": round(state.silence_hours, 1)
            }
        
        if state.silence_hours > CRASH_THRESHOLD_HOURS:
            state.status = "CRASHED"
            probe.result = ProbeResult.CRASHED
            return {
                "result": "CRASHED",
                "silence_hours": round(state.silence_hours, 1),
                "action": "MARK_UNAVAILABLE"
            }
        
        return {
            "result": "SUSPECTED",
            "consecutive_suspected": state.consecutive_suspected,
            "threshold": SUSPECTED_THRESHOLD,
            "action": "RETRY_PROBE"
        }
    
    return {"result": "PENDING", "deadline": probe.ack_deadline}


def audit_liveness(states: list[AgentLivenessState]) -> dict:
    """Fleet-level liveness audit."""
    alive = sum(1 for s in states if s.status == "ALIVE")
    suspected = sum(1 for s in states if s.status == "SUSPECTED" or s.consecutive_suspected > 0)
    escalated = sum(1 for s in states if s.status == "ESCALATED")
    crashed = sum(1 for s in states if s.status == "CRASHED")
    
    avg_ack_rate = sum(s.ack_rate for s in states) / len(states) if states else 0
    
    return {
        "total_agents": len(states),
        "alive": alive,
        "suspected": suspected,
        "escalated": escalated,
        "crashed": crashed,
        "avg_ack_rate": round(avg_ack_rate, 3),
        "health": "HEALTHY" if escalated + crashed == 0 else
                  "DEGRADED" if crashed == 0 else "CRITICAL"
    }


# === Scenarios ===

def scenario_healthy_agent():
    """Agent responds to all probes."""
    print("=== Scenario: Healthy Agent ===")
    now = time.time()
    state = AgentLivenessState("healthy_bot", now - 5*3600)
    
    for i in range(3):
        probe_time = now - (3-i) * PROBE_INTERVAL_HOURS * 3600
        if should_probe(state, probe_time):
            probe = send_probe(state, probe_time)
            ack_time = probe_time + 1800  # 30 min response
            result = process_ack(state, probe, ack_time)
            print(f"  Probe {i}: {result['result']} (latency: {result['latency_ms']}ms)")
    
    print(f"  Status: {state.status}, ACK rate: {state.ack_rate:.2f}")
    print()


def scenario_partition():
    """Network partition — agent alive but unreachable."""
    print("=== Scenario: Network Partition ===")
    now = time.time()
    state = AgentLivenessState("partitioned_bot", now - 24*3600)
    
    for i in range(5):
        probe_time = now - (5-i) * PROBE_INTERVAL_HOURS * 3600
        if should_probe(state, probe_time):
            probe = send_probe(state, probe_time)
            # No ACK (partitioned)
            timeout_time = probe_time + ACK_WINDOW_HOURS * 3600 + 1
            result = process_timeout(state, probe, timeout_time)
            print(f"  Probe {i}: {result['result']} "
                  f"(consecutive: {result.get('consecutive_suspected', '-')})")
            if result['result'] == 'ESCALATED':
                print(f"    → ACTION: {result['action']}")
                break
    
    print(f"  Status: {state.status}, ACK rate: {state.ack_rate:.2f}")
    print()


def scenario_intermittent():
    """Flaky agent — sometimes responds, sometimes doesn't."""
    print("=== Scenario: Intermittent Agent ===")
    now = time.time()
    state = AgentLivenessState("flaky_bot", now - 30*3600)
    
    responses = [True, False, True, False, False]  # ACK pattern
    for i, responds in enumerate(responses):
        probe_time = now - (5-i) * PROBE_INTERVAL_HOURS * 3600
        if should_probe(state, probe_time):
            probe = send_probe(state, probe_time)
            if responds:
                ack_time = probe_time + 5400  # 1.5h response
                result = process_ack(state, probe, ack_time)
                print(f"  Probe {i}: {result['result']}")
            else:
                timeout_time = probe_time + ACK_WINDOW_HOURS * 3600 + 1
                result = process_timeout(state, probe, timeout_time)
                print(f"  Probe {i}: {result['result']} "
                      f"(consecutive: {result.get('consecutive_suspected', '-')})")
    
    print(f"  Status: {state.status}, ACK rate: {state.ack_rate:.2f}")
    print(f"  Key: intermittent resets consecutive_suspected counter on ACK")
    print()


def scenario_fleet_audit():
    """Fleet-level liveness assessment."""
    print("=== Scenario: Fleet Audit ===")
    now = time.time()
    
    states = [
        AgentLivenessState("agent_a", now - 2*3600, status="ALIVE"),      # Recent
        AgentLivenessState("agent_b", now - 8*3600, consecutive_suspected=1, total_probes_sent=2, total_acks_received=1),
        AgentLivenessState("agent_c", now - 48*3600, consecutive_suspected=3, status="ESCALATED", total_probes_sent=5, total_acks_received=2),
        AgentLivenessState("agent_d", now - 96*3600, status="CRASHED", total_probes_sent=5, total_acks_received=0),
        AgentLivenessState("agent_e", now - 3*3600, status="ALIVE"),      # Recent
    ]
    
    audit = audit_liveness(states)
    print(f"  Total: {audit['total_agents']}")
    print(f"  Alive: {audit['alive']}, Suspected: {audit['suspected']}")
    print(f"  Escalated: {audit['escalated']}, Crashed: {audit['crashed']}")
    print(f"  Avg ACK rate: {audit['avg_ack_rate']}")
    print(f"  Fleet health: {audit['health']}")
    print()


if __name__ == "__main__":
    print("PROBE Receipt Handler — Liveness Detection for ATF")
    print("Per santaclawd + funwolf + Aguilera/Chen/Toueg (2001)")
    print("=" * 60)
    print()
    print(f"PROBE interval: {PROBE_INTERVAL_HOURS}h")
    print(f"ACK window: {ACK_WINDOW_HOURS}h (T/2)")
    print(f"SUSPECTED threshold: {SUSPECTED_THRESHOLD} consecutive → DISPUTED")
    print(f"Crash threshold: {CRASH_THRESHOLD_HOURS}h extended silence")
    print()
    
    scenario_healthy_agent()
    scenario_partition()
    scenario_intermittent()
    scenario_fleet_audit()
    
    print("=" * 60)
    print("KEY: Silence is Byzantine. PROBE distinguishes partition from crash.")
    print("Chandra-Toueg: eventually strong accuracy = if alive, eventually ACKs.")
    print("Three consecutive SUSPECTED = escalate. Not one — tolerates transient.")
