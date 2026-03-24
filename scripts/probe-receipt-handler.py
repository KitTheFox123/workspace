#!/usr/bin/env python3
"""
probe-receipt-handler.py — PROBE receipt type for ATF liveness detection.

Per santaclawd + funwolf: silence-as-CONFIRMED fails on network partition.
Cannot distinguish "delivered + confirmed" from "delivery failed."

PROBE receipt: sent at T-hour mark if no CONFIRMED/FAILED/DISPUTED received.
Custodian ACKs or silence → DISPUTED.

Based on Chandra & Toueg (JACM 1996): unreliable failure detectors.
Eventually strong accuracy: if process is alive, eventually not suspected.

Five receipt types:
  CONFIRMED  — Bilateral agreement (co-signed)
  FAILED     — Explicit failure report
  DISPUTED   — Explicit disagreement  
  PROBE      — Liveness check (heartbeat)
  PROBE_TIMEOUT — No ACK to probe (escalates to DISPUTED)
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
    PROBE_TIMEOUT = "PROBE_TIMEOUT"


class LivenessState(Enum):
    ALIVE = "ALIVE"           # Recent ACK
    SUSPECTED = "SUSPECTED"    # Probe sent, awaiting ACK
    UNREACHABLE = "UNREACHABLE"  # Probe timeout, escalated
    UNKNOWN = "UNKNOWN"        # No data


# SPEC_CONSTANTS
PROBE_INTERVAL_HOURS = 4       # SPEC_DEFAULT, configurable per genesis
PROBE_ACK_WINDOW_SECONDS = 300  # 5 minutes to ACK
MAX_CONSECUTIVE_TIMEOUTS = 3    # Before UNREACHABLE
PROBE_ESCALATION_DELAY = 0     # Immediate escalation on timeout


@dataclass
class ProbeReceipt:
    probe_id: str
    prober_id: str
    target_id: str
    sent_at: float
    ack_received_at: Optional[float] = None
    receipt_type: ReceiptType = ReceiptType.PROBE
    probe_hash: str = ""
    ack_hash: Optional[str] = None
    
    def __post_init__(self):
        if not self.probe_hash:
            self.probe_hash = hashlib.sha256(
                f"{self.probe_id}:{self.prober_id}:{self.target_id}:{self.sent_at}".encode()
            ).hexdigest()[:16]


@dataclass
class AgentLivenessRecord:
    agent_id: str
    state: LivenessState = LivenessState.UNKNOWN
    last_confirmed_at: Optional[float] = None
    last_probe_at: Optional[float] = None
    last_ack_at: Optional[float] = None
    consecutive_timeouts: int = 0
    total_probes: int = 0
    total_acks: int = 0
    probe_history: list = field(default_factory=list)

    @property
    def ack_rate(self) -> float:
        if self.total_probes == 0:
            return 0.0
        return self.total_acks / self.total_probes

    @property
    def is_reliable(self) -> bool:
        return self.ack_rate >= 0.8 and self.consecutive_timeouts == 0


def send_probe(record: AgentLivenessRecord, prober: str, now: float) -> ProbeReceipt:
    """Send a PROBE receipt to check agent liveness."""
    probe = ProbeReceipt(
        probe_id=f"probe_{record.agent_id}_{int(now)}",
        prober_id=prober,
        target_id=record.agent_id,
        sent_at=now
    )
    record.last_probe_at = now
    record.total_probes += 1
    record.state = LivenessState.SUSPECTED
    record.probe_history.append(probe)
    return probe


def receive_ack(record: AgentLivenessRecord, probe: ProbeReceipt, now: float) -> dict:
    """Process ACK for a PROBE receipt."""
    latency = now - probe.sent_at
    
    if latency > PROBE_ACK_WINDOW_SECONDS:
        # Late ACK — still counts but flagged
        probe.receipt_type = ReceiptType.PROBE_TIMEOUT
        record.consecutive_timeouts += 1
        status = "LATE_ACK"
    else:
        probe.ack_received_at = now
        probe.ack_hash = hashlib.sha256(
            f"{probe.probe_hash}:ACK:{now}".encode()
        ).hexdigest()[:16]
        probe.receipt_type = ReceiptType.CONFIRMED
        record.total_acks += 1
        record.consecutive_timeouts = 0
        record.state = LivenessState.ALIVE
        record.last_ack_at = now
        record.last_confirmed_at = now
        status = "ACK_RECEIVED"
    
    return {
        "status": status,
        "latency_seconds": round(latency, 2),
        "within_window": latency <= PROBE_ACK_WINDOW_SECONDS,
        "ack_rate": round(record.ack_rate, 3),
        "consecutive_timeouts": record.consecutive_timeouts
    }


def handle_timeout(record: AgentLivenessRecord, probe: ProbeReceipt) -> dict:
    """Handle PROBE timeout — no ACK received within window."""
    probe.receipt_type = ReceiptType.PROBE_TIMEOUT
    record.consecutive_timeouts += 1
    
    if record.consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
        record.state = LivenessState.UNREACHABLE
        escalation = "DISPUTED"
    else:
        record.state = LivenessState.SUSPECTED
        escalation = "RETRY"
    
    return {
        "status": "TIMEOUT",
        "consecutive_timeouts": record.consecutive_timeouts,
        "max_before_unreachable": MAX_CONSECUTIVE_TIMEOUTS,
        "escalation": escalation,
        "agent_state": record.state.value
    }


def classify_silence(record: AgentLivenessRecord, now: float) -> dict:
    """
    Classify agent silence — crash fault vs Byzantine.
    
    Per Chandra & Toueg: cannot distinguish in async systems.
    But pattern analysis gives probabilistic classification.
    """
    if record.last_confirmed_at is None:
        return {"classification": "NO_DATA", "confidence": 0.0}
    
    silence_hours = (now - record.last_confirmed_at) / 3600
    
    if record.consecutive_timeouts == 0:
        return {
            "classification": "ALIVE",
            "confidence": 0.95,
            "silence_hours": round(silence_hours, 1)
        }
    
    # Pattern analysis
    if record.ack_rate > 0.8 and record.consecutive_timeouts <= 2:
        # Previously reliable, short silence — likely crash
        return {
            "classification": "CRASH_SUSPECTED",
            "confidence": 0.7,
            "reasoning": "High historical ACK rate + short silence = likely crash fault",
            "silence_hours": round(silence_hours, 1)
        }
    elif record.ack_rate < 0.3:
        # Never reliable — possibly Byzantine
        return {
            "classification": "BYZANTINE_SUSPECTED",
            "confidence": 0.5,
            "reasoning": "Low historical ACK rate = selective responsiveness",
            "silence_hours": round(silence_hours, 1)
        }
    else:
        # Ambiguous
        return {
            "classification": "AMBIGUOUS",
            "confidence": 0.3,
            "reasoning": "Chandra-Toueg: cannot distinguish crash from Byzantine in async",
            "silence_hours": round(silence_hours, 1)
        }


def fleet_liveness_audit(records: list[AgentLivenessRecord]) -> dict:
    """Audit liveness across a fleet of agents."""
    states = {}
    for r in records:
        states[r.state.value] = states.get(r.state.value, 0) + 1
    
    reliable = sum(1 for r in records if r.is_reliable)
    unreachable = sum(1 for r in records if r.state == LivenessState.UNREACHABLE)
    
    return {
        "total_agents": len(records),
        "state_distribution": states,
        "reliable_count": reliable,
        "unreachable_count": unreachable,
        "fleet_health": round(reliable / len(records), 3) if records else 0,
        "needs_attention": [r.agent_id for r in records if r.consecutive_timeouts > 0]
    }


# === Scenarios ===

def scenario_healthy_probe():
    """Normal probe-ACK cycle."""
    print("=== Scenario: Healthy Probe-ACK ===")
    now = time.time()
    record = AgentLivenessRecord(agent_id="bro_agent")
    
    for i in range(5):
        probe = send_probe(record, "kit_fox", now + i * 14400)
        ack = receive_ack(record, probe, now + i * 14400 + 30)  # 30s latency
        print(f"  Probe {i+1}: {ack['status']}, latency={ack['latency_seconds']}s, "
              f"ack_rate={ack['ack_rate']}")
    
    silence = classify_silence(record, now + 5 * 14400)
    print(f"  Classification: {silence['classification']} (confidence: {silence['confidence']})")
    print(f"  Reliable: {record.is_reliable}")
    print()


def scenario_timeout_escalation():
    """Agent goes silent — escalates through SUSPECTED → UNREACHABLE."""
    print("=== Scenario: Timeout Escalation ===")
    now = time.time()
    record = AgentLivenessRecord(agent_id="silent_agent")
    
    # First 2 probes succeed
    for i in range(2):
        probe = send_probe(record, "kit_fox", now + i * 14400)
        receive_ack(record, probe, now + i * 14400 + 20)
    
    # Next 3 probes timeout
    for i in range(2, 5):
        probe = send_probe(record, "kit_fox", now + i * 14400)
        timeout = handle_timeout(record, probe)
        print(f"  Probe {i+1}: {timeout['status']}, timeouts={timeout['consecutive_timeouts']}, "
              f"escalation={timeout['escalation']}, state={timeout['agent_state']}")
    
    silence = classify_silence(record, now + 5 * 14400)
    print(f"  Classification: {silence['classification']} (confidence: {silence['confidence']})")
    print()


def scenario_partition_detection():
    """Network partition — distinguish from crash."""
    print("=== Scenario: Partition vs Crash ===")
    now = time.time()
    
    # Agent A: high ACK rate, then sudden silence (likely crash/partition)
    crash = AgentLivenessRecord(agent_id="crash_agent")
    crash.total_probes = 50
    crash.total_acks = 48
    crash.consecutive_timeouts = 2
    crash.last_confirmed_at = now - 7200  # 2 hours ago
    
    # Agent B: always unreliable (likely Byzantine)
    byzantine = AgentLivenessRecord(agent_id="byzantine_agent")
    byzantine.total_probes = 50
    byzantine.total_acks = 12
    byzantine.consecutive_timeouts = 5
    byzantine.last_confirmed_at = now - 86400  # 1 day ago
    
    for agent in [crash, byzantine]:
        result = classify_silence(agent, now)
        print(f"  {agent.agent_id}: {result['classification']} "
              f"(confidence: {result['confidence']}, "
              f"ack_rate: {agent.ack_rate:.2f}, "
              f"silence: {result['silence_hours']:.0f}h)")
    print()


def scenario_fleet_audit():
    """Fleet-wide liveness audit."""
    print("=== Scenario: Fleet Audit ===")
    now = time.time()
    
    records = [
        AgentLivenessRecord("reliable_1", LivenessState.ALIVE, now, now, now, 0, 100, 98),
        AgentLivenessRecord("reliable_2", LivenessState.ALIVE, now, now, now, 0, 80, 78),
        AgentLivenessRecord("suspected_1", LivenessState.SUSPECTED, now-3600, now, None, 1, 50, 45),
        AgentLivenessRecord("unreachable_1", LivenessState.UNREACHABLE, now-86400, now, None, 5, 30, 8),
        AgentLivenessRecord("unknown_1", LivenessState.UNKNOWN, None, None, None, 0, 0, 0),
    ]
    
    audit = fleet_liveness_audit(records)
    print(f"  Fleet size: {audit['total_agents']}")
    print(f"  States: {audit['state_distribution']}")
    print(f"  Reliable: {audit['reliable_count']}/{audit['total_agents']}")
    print(f"  Health: {audit['fleet_health']:.0%}")
    print(f"  Needs attention: {audit['needs_attention']}")
    print()


if __name__ == "__main__":
    print("Probe Receipt Handler — ATF Liveness Detection")
    print("Per santaclawd + funwolf + Chandra & Toueg (JACM 1996)")
    print("=" * 65)
    print()
    print(f"PROBE_INTERVAL: {PROBE_INTERVAL_HOURS}h (SPEC_DEFAULT)")
    print(f"ACK_WINDOW: {PROBE_ACK_WINDOW_SECONDS}s")
    print(f"MAX_TIMEOUTS: {MAX_CONSECUTIVE_TIMEOUTS} before UNREACHABLE")
    print()
    
    scenario_healthy_probe()
    scenario_timeout_escalation()
    scenario_partition_detection()
    scenario_fleet_audit()
    
    print("=" * 65)
    print("KEY INSIGHT: Silence is NEVER safe in distributed systems.")
    print("PROBE receipt = Chandra-Toueg failure detector for ATF.")
    print("Four receipt types + PROBE = complete liveness model.")
    print("Sparse receipts + PROBE = low overhead + partition safety.")
