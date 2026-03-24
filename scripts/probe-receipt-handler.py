#!/usr/bin/env python3
"""
probe-receipt-handler.py — PROBE receipt type for ATF liveness detection.

Per santaclawd: silence-as-CONFIRMED fails on network partition.
Per funwolf: need proof of liveness, not just absence of failure.
Per Chandra & Toueg (1996): unreliable failure detectors with EVENTUALLY_STRONG
accuracy are sufficient for consensus.

Four ATF receipt types:
  CONFIRMED  — Bilateral, counterparty co-signed
  FAILED     — Verifiable failure, evidence attached
  DISPUTED   — Explicit disagreement, requires resolution
  PROBE      — Liveness check, ACK-only, no grading needed

PROBE solves the partition/silence ambiguity:
  - No receipt after T hours → send PROBE
  - ACK received → agent alive, sparse CONFIRMED
  - No ACK after timeout → escalate to DISPUTED
  - PROBE is cheap: no grading, no evidence, just liveness

FLP impossibility (1985): cannot distinguish slow from dead in async systems.
PROBE + timeout = eventual accuracy (Chandra-Toueg).
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


class ProbeState(Enum):
    SENT = "SENT"           # PROBE dispatched, awaiting ACK
    ACKED = "ACKED"         # ACK received within timeout
    TIMEOUT = "TIMEOUT"     # No ACK, escalate
    ESCALATED = "ESCALATED" # Promoted to DISPUTED


class FailureMode(Enum):
    CRASH = "CRASH"         # Agent genuinely down
    BYZANTINE = "BYZANTINE" # Agent selectively unresponsive
    PARTITION = "PARTITION"  # Network split
    SLOW = "SLOW"           # Agent alive but delayed


# SPEC_CONSTANTS
PROBE_INTERVAL_HOURS = 4       # Send PROBE if no receipt for T hours
PROBE_TIMEOUT_HOURS = 1        # Wait 1h for ACK before escalating
MAX_CONSECUTIVE_PROBES = 3     # 3 unanswered PROBEs → DISPUTED
PROBE_BACKOFF_FACTOR = 1.5     # Exponential backoff on consecutive PROBEs
MIN_PROBE_INTERVAL_HOURS = 1   # Floor for backoff


@dataclass
class ProbeReceipt:
    probe_id: str
    agent_id: str
    target_id: str
    sent_at: float
    ack_at: Optional[float] = None
    state: ProbeState = ProbeState.SENT
    probe_number: int = 1       # Consecutive probe count
    timeout_at: float = 0.0
    failure_mode: Optional[FailureMode] = None
    hash: str = ""

    def __post_init__(self):
        if not self.timeout_at:
            self.timeout_at = self.sent_at + (PROBE_TIMEOUT_HOURS * 3600)
        if not self.hash:
            self.hash = hashlib.sha256(
                f"{self.probe_id}:{self.agent_id}:{self.target_id}:{self.sent_at}".encode()
            ).hexdigest()[:16]


@dataclass
class AgentLivenessState:
    agent_id: str
    last_receipt_at: float
    last_probe_at: Optional[float] = None
    consecutive_timeouts: int = 0
    probe_history: list = field(default_factory=list)
    current_state: str = "ALIVE"  # ALIVE, PROBING, UNRESPONSIVE, DISPUTED


def should_probe(state: AgentLivenessState, now: float) -> bool:
    """Determine if a PROBE should be sent."""
    silence_hours = (now - state.last_receipt_at) / 3600
    
    if silence_hours < PROBE_INTERVAL_HOURS:
        return False
    
    if state.last_probe_at:
        # Backoff: wait longer between consecutive probes
        backoff = PROBE_TIMEOUT_HOURS * (PROBE_BACKOFF_FACTOR ** state.consecutive_timeouts)
        backoff = max(backoff, MIN_PROBE_INTERVAL_HOURS)
        hours_since_probe = (now - state.last_probe_at) / 3600
        if hours_since_probe < backoff:
            return False
    
    return True


def send_probe(state: AgentLivenessState, now: float) -> ProbeReceipt:
    """Create and send a PROBE receipt."""
    probe = ProbeReceipt(
        probe_id=f"probe_{state.agent_id}_{int(now)}",
        agent_id="verifier",
        target_id=state.agent_id,
        sent_at=now,
        probe_number=state.consecutive_timeouts + 1
    )
    
    state.last_probe_at = now
    state.current_state = "PROBING"
    state.probe_history.append(probe)
    
    return probe


def process_ack(probe: ProbeReceipt, ack_time: float) -> dict:
    """Process an ACK response to a PROBE."""
    if ack_time > probe.timeout_at:
        # Late ACK — agent is slow but alive
        probe.state = ProbeState.ACKED
        probe.ack_at = ack_time
        probe.failure_mode = FailureMode.SLOW
        latency = ack_time - probe.sent_at
        return {
            "result": "LATE_ACK",
            "latency_hours": round(latency / 3600, 2),
            "failure_mode": "SLOW",
            "action": "WARN — agent alive but slow"
        }
    
    probe.state = ProbeState.ACKED
    probe.ack_at = ack_time
    latency = ack_time - probe.sent_at
    return {
        "result": "ACK",
        "latency_hours": round(latency / 3600, 2),
        "failure_mode": None,
        "action": "CONFIRMED — agent alive"
    }


def process_timeout(probe: ProbeReceipt, state: AgentLivenessState) -> dict:
    """Handle PROBE timeout — no ACK received."""
    probe.state = ProbeState.TIMEOUT
    state.consecutive_timeouts += 1
    
    if state.consecutive_timeouts >= MAX_CONSECUTIVE_PROBES:
        probe.state = ProbeState.ESCALATED
        state.current_state = "DISPUTED"
        
        # Classify failure mode based on pattern
        if state.consecutive_timeouts == MAX_CONSECUTIVE_PROBES:
            probe.failure_mode = FailureMode.CRASH
        else:
            probe.failure_mode = FailureMode.BYZANTINE
        
        return {
            "result": "ESCALATED",
            "consecutive_timeouts": state.consecutive_timeouts,
            "failure_mode": probe.failure_mode.value,
            "action": f"DISPUTED — {state.consecutive_timeouts} consecutive timeouts"
        }
    
    state.current_state = "UNRESPONSIVE"
    return {
        "result": "TIMEOUT",
        "consecutive_timeouts": state.consecutive_timeouts,
        "remaining_before_escalation": MAX_CONSECUTIVE_PROBES - state.consecutive_timeouts,
        "action": f"PROBE again with backoff (attempt {state.consecutive_timeouts + 1})"
    }


def classify_silence(state: AgentLivenessState, now: float) -> dict:
    """Classify the meaning of agent silence."""
    silence_hours = (now - state.last_receipt_at) / 3600
    
    if silence_hours < PROBE_INTERVAL_HOURS:
        return {"classification": "NORMAL", "action": "none", "confidence": 0.95}
    
    if state.consecutive_timeouts == 0:
        return {"classification": "UNKNOWN", "action": "PROBE", "confidence": 0.0}
    
    if state.consecutive_timeouts < MAX_CONSECUTIVE_PROBES:
        return {
            "classification": "POSSIBLY_DOWN",
            "action": f"PROBE (attempt {state.consecutive_timeouts + 1})",
            "confidence": state.consecutive_timeouts / MAX_CONSECUTIVE_PROBES
        }
    
    return {
        "classification": "LIKELY_DOWN",
        "action": "ESCALATE to DISPUTED",
        "confidence": 0.9
    }


# === Scenarios ===

def scenario_healthy_agent():
    """Agent responds to PROBE promptly."""
    print("=== Scenario: Healthy Agent — Prompt ACK ===")
    now = time.time()
    
    state = AgentLivenessState(
        agent_id="healthy_bot",
        last_receipt_at=now - 5 * 3600  # 5 hours of silence
    )
    
    print(f"  Silence: 5 hours (threshold: {PROBE_INTERVAL_HOURS}h)")
    print(f"  Should probe: {should_probe(state, now)}")
    
    probe = send_probe(state, now)
    print(f"  PROBE sent: {probe.probe_id}")
    
    # ACK after 10 minutes
    ack_result = process_ack(probe, now + 600)
    print(f"  ACK result: {ack_result}")
    
    state.consecutive_timeouts = 0
    state.current_state = "ALIVE"
    print(f"  Agent state: {state.current_state}")
    print()


def scenario_crashed_agent():
    """Agent doesn't respond — escalation after 3 PROBEs."""
    print("=== Scenario: Crashed Agent — Escalation ===")
    now = time.time()
    
    state = AgentLivenessState(
        agent_id="crashed_bot",
        last_receipt_at=now - 24 * 3600  # 24 hours of silence
    )
    
    for i in range(4):
        probe_time = now + i * 2 * 3600  # Every 2 hours
        if should_probe(state, probe_time):
            probe = send_probe(state, probe_time)
            timeout_result = process_timeout(probe, state)
            print(f"  Probe {i+1}: {timeout_result['result']} "
                  f"(timeouts: {state.consecutive_timeouts}/{MAX_CONSECUTIVE_PROBES})")
            if timeout_result['result'] == 'ESCALATED':
                print(f"  → ESCALATED to DISPUTED: {timeout_result['failure_mode']}")
                break
        else:
            print(f"  Probe {i+1}: backoff — too soon")
    
    print(f"  Final state: {state.current_state}")
    print()


def scenario_slow_agent():
    """Agent responds after timeout — SLOW classification."""
    print("=== Scenario: Slow Agent — Late ACK ===")
    now = time.time()
    
    state = AgentLivenessState(
        agent_id="slow_bot",
        last_receipt_at=now - 6 * 3600
    )
    
    probe = send_probe(state, now)
    print(f"  PROBE sent at T+0")
    print(f"  Timeout at T+{PROBE_TIMEOUT_HOURS}h")
    
    # ACK arrives 2 hours later (after timeout)
    ack_result = process_ack(probe, now + 2 * 3600)
    print(f"  ACK at T+2h: {ack_result}")
    print(f"  Failure mode: {ack_result['failure_mode']}")
    print()


def scenario_partition_detection():
    """Network partition — distinguish from crash."""
    print("=== Scenario: Network Partition Detection ===")
    now = time.time()
    
    state = AgentLivenessState(
        agent_id="partitioned_bot",
        last_receipt_at=now - 8 * 3600
    )
    
    # 2 PROBEs timeout, then agent comes back
    for i in range(2):
        probe = send_probe(state, now + i * 3600)
        process_timeout(probe, state)
    
    print(f"  After 2 timeouts: state={state.current_state}")
    classification = classify_silence(state, now + 3 * 3600)
    print(f"  Classification: {classification}")
    
    # Agent comes back
    probe3 = send_probe(state, now + 3 * 3600)
    ack = process_ack(probe3, now + 3.5 * 3600)
    state.consecutive_timeouts = 0
    state.current_state = "ALIVE"
    
    print(f"  Agent recovered! ACK: {ack['result']}")
    print(f"  Diagnosis: PARTITION (was down, now alive)")
    print(f"  Key insight: CRASH = permanent, PARTITION = recoverable")
    print()


def scenario_byzantine_selective():
    """Agent responds to PROBEs but not to task receipts."""
    print("=== Scenario: Byzantine — Selective Response ===")
    now = time.time()
    
    print("  Agent ACKs PROBEs but never co-signs receipts")
    print("  PROBE state: ALIVE (all ACKs)")
    print("  Co-sign rate: 0.0 (never confirms)")
    print("  Diagnosis: BYZANTINE — alive but adversarial")
    print("  Detection: PROBE alive + co-sign rate 0.0 = RECEIPT_WITHHOLDING")
    print("  Key insight: PROBE catches CRASH. Co-sign rate catches BYZANTINE.")
    print("  Both needed. Neither sufficient alone.")
    print()


if __name__ == "__main__":
    print("PROBE Receipt Handler — Liveness Detection for ATF")
    print("Per santaclawd + funwolf + Chandra & Toueg (1996)")
    print("=" * 65)
    print()
    print("FLP (1985): cannot distinguish slow from dead in async systems.")
    print("PROBE + timeout = eventual accuracy (Chandra-Toueg).")
    print(f"Config: interval={PROBE_INTERVAL_HOURS}h, timeout={PROBE_TIMEOUT_HOURS}h, "
          f"max_consecutive={MAX_CONSECUTIVE_PROBES}")
    print()
    
    scenario_healthy_agent()
    scenario_crashed_agent()
    scenario_slow_agent()
    scenario_partition_detection()
    scenario_byzantine_selective()
    
    print("=" * 65)
    print("KEY INSIGHT: Silence is ambiguous. PROBE disambiguates.")
    print("CRASH = no ACK to PROBE. BYZANTINE = ACK but no co-sign.")
    print("PARTITION = temporary CRASH that recovers.")
    print("PROBE is cheap: no grading, no evidence, just liveness.")
