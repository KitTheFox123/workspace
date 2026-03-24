#!/usr/bin/env python3
"""
probe-receipt-handler.py — Liveness probes for ATF sparse receipt model.

Per santaclawd + funwolf: silence-as-CONFIRMED fails on network partition.
Cannot distinguish "delivered + confirmed" from "delivery failed."

PROBE receipt: sent at T-hour mark if no FAILED/DISPUTED received.
Custodian ACKs or silence → UNCONFIRMED (not CONFIRMED).

Per Aguilera et al. (1997): timeout-free failure detectors use heartbeat
MESSAGES not heartbeat TIMEOUTS. PROBE = heartbeat message for trust state.

Five receipt states:
  CONFIRMED  — bilateral agreement (co-signed)
  FAILED     — explicit failure reported
  DISPUTED   — explicit disagreement
  PROBE      — liveness check sent, awaiting ACK
  UNCONFIRMED — PROBE sent, no ACK received within window

SMTP parallel: VRFY command (RFC 5321) — rarely used but proves channel works.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ReceiptState(Enum):
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    DISPUTED = "DISPUTED"
    PROBE = "PROBE"           # Liveness check in flight
    UNCONFIRMED = "UNCONFIRMED"  # PROBE timeout — partition or failure


class ProbeResult(Enum):
    ACK = "ACK"               # Custodian responded — state persists
    NACK = "NACK"             # Custodian explicitly rejected
    TIMEOUT = "TIMEOUT"       # No response within window
    CHANNEL_FAIL = "CHANNEL_FAIL"  # Delivery of PROBE itself failed


# SPEC_CONSTANTS
PROBE_INTERVAL_HOURS = 24     # Send PROBE every T hours if silent
PROBE_ACK_WINDOW_HOURS = 4    # ACK required within this window
MAX_CONSECUTIVE_TIMEOUTS = 3  # Before escalation to UNCONFIRMED
PROBE_ESCALATION_CHAIN = [
    "PROBE",           # First: standard probe
    "PROBE_ELEVATED",  # Second: elevated priority
    "PROBE_FINAL",     # Third: last chance before UNCONFIRMED
]


@dataclass
class ProbeEvent:
    probe_id: str
    target_agent: str
    milestone_hash: Optional[str]
    sent_at: float
    probe_type: str = "PROBE"  # PROBE / PROBE_ELEVATED / PROBE_FINAL
    result: Optional[ProbeResult] = None
    ack_at: Optional[float] = None
    hash: str = ""
    
    def __post_init__(self):
        if not self.hash:
            self.hash = hashlib.sha256(
                f"{self.probe_id}:{self.target_agent}:{self.sent_at}".encode()
            ).hexdigest()[:16]


@dataclass
class AgentLivenessState:
    agent_id: str
    last_receipt_at: float
    last_probe_at: Optional[float] = None
    consecutive_timeouts: int = 0
    state: ReceiptState = ReceiptState.CONFIRMED
    probe_history: list = field(default_factory=list)


def should_probe(agent: AgentLivenessState, now: float) -> bool:
    """Determine if a PROBE should be sent."""
    hours_since_receipt = (now - agent.last_receipt_at) / 3600
    
    # Don't probe if we have a recent receipt
    if hours_since_receipt < PROBE_INTERVAL_HOURS:
        return False
    
    # Don't probe if we already have one in flight
    if agent.state == ReceiptState.PROBE:
        if agent.last_probe_at:
            hours_since_probe = (now - agent.last_probe_at) / 3600
            if hours_since_probe < PROBE_ACK_WINDOW_HOURS:
                return False  # Still waiting for ACK
    
    return True


def send_probe(agent: AgentLivenessState, now: float) -> ProbeEvent:
    """Send a PROBE to the agent."""
    probe_type = PROBE_ESCALATION_CHAIN[
        min(agent.consecutive_timeouts, len(PROBE_ESCALATION_CHAIN) - 1)
    ]
    
    probe = ProbeEvent(
        probe_id=f"probe_{agent.agent_id}_{int(now)}",
        target_agent=agent.agent_id,
        milestone_hash=None,
        sent_at=now,
        probe_type=probe_type
    )
    
    agent.state = ReceiptState.PROBE
    agent.last_probe_at = now
    agent.probe_history.append(probe)
    
    return probe


def process_ack(agent: AgentLivenessState, probe: ProbeEvent, 
                result: ProbeResult, now: float) -> dict:
    """Process a PROBE response."""
    probe.result = result
    probe.ack_at = now if result == ProbeResult.ACK else None
    
    if result == ProbeResult.ACK:
        agent.state = ReceiptState.CONFIRMED
        agent.consecutive_timeouts = 0
        agent.last_receipt_at = now
        return {"action": "CONFIRMED", "message": "Liveness verified"}
    
    elif result == ProbeResult.NACK:
        agent.state = ReceiptState.DISPUTED
        agent.consecutive_timeouts = 0
        return {"action": "DISPUTED", "message": "Custodian explicitly rejected"}
    
    elif result == ProbeResult.TIMEOUT:
        agent.consecutive_timeouts += 1
        if agent.consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
            agent.state = ReceiptState.UNCONFIRMED
            return {
                "action": "UNCONFIRMED",
                "message": f"{MAX_CONSECUTIVE_TIMEOUTS} consecutive timeouts — partition or failure",
                "consecutive_timeouts": agent.consecutive_timeouts
            }
        else:
            return {
                "action": "PROBE_RETRY",
                "message": f"Timeout {agent.consecutive_timeouts}/{MAX_CONSECUTIVE_TIMEOUTS}",
                "next_probe": PROBE_ESCALATION_CHAIN[
                    min(agent.consecutive_timeouts, len(PROBE_ESCALATION_CHAIN) - 1)
                ]
            }
    
    elif result == ProbeResult.CHANNEL_FAIL:
        agent.state = ReceiptState.UNCONFIRMED
        return {"action": "CHANNEL_FAILURE", "message": "Delivery channel broken"}


def audit_fleet(agents: list[AgentLivenessState]) -> dict:
    """Fleet-level liveness audit."""
    states = {}
    for a in agents:
        states[a.state.value] = states.get(a.state.value, 0) + 1
    
    total = len(agents)
    unconfirmed = states.get("UNCONFIRMED", 0)
    probing = states.get("PROBE", 0)
    
    health = "HEALTHY" if unconfirmed == 0 else (
        "DEGRADED" if unconfirmed / total < 0.1 else "CRITICAL"
    )
    
    return {
        "total_agents": total,
        "state_distribution": states,
        "health": health,
        "probe_pending": probing,
        "unconfirmed_rate": round(unconfirmed / total, 3) if total > 0 else 0
    }


# === Scenarios ===

def scenario_healthy_ack():
    """Normal operation: PROBE sent, ACK received."""
    print("=== Scenario: Healthy ACK ===")
    now = time.time()
    
    agent = AgentLivenessState("bro_agent", last_receipt_at=now - 86400 * 2)
    
    print(f"  Last receipt: 48h ago")
    print(f"  Should probe: {should_probe(agent, now)}")
    
    probe = send_probe(agent, now)
    print(f"  Sent: {probe.probe_type}")
    
    result = process_ack(agent, probe, ProbeResult.ACK, now + 3600)
    print(f"  Result: {result['action']} — {result['message']}")
    print(f"  State: {agent.state.value}")
    print()


def scenario_partition_timeout():
    """Network partition: 3 consecutive timeouts → UNCONFIRMED."""
    print("=== Scenario: Partition — 3 Timeouts → UNCONFIRMED ===")
    now = time.time()
    
    agent = AgentLivenessState("partitioned_agent", last_receipt_at=now - 86400 * 3)
    
    for i in range(3):
        probe = send_probe(agent, now + i * PROBE_INTERVAL_HOURS * 3600)
        result = process_ack(agent, probe, ProbeResult.TIMEOUT, 
                           now + (i + 1) * PROBE_INTERVAL_HOURS * 3600)
        print(f"  Probe {i+1} ({probe.probe_type}): {result['action']} — {result['message']}")
    
    print(f"  Final state: {agent.state.value}")
    print(f"  Consecutive timeouts: {agent.consecutive_timeouts}")
    print()


def scenario_nack_dispute():
    """Custodian explicitly rejects → DISPUTED."""
    print("=== Scenario: Explicit NACK → DISPUTED ===")
    now = time.time()
    
    agent = AgentLivenessState("hostile_agent", last_receipt_at=now - 86400)
    
    probe = send_probe(agent, now)
    result = process_ack(agent, probe, ProbeResult.NACK, now + 7200)
    print(f"  Probe: {probe.probe_type}")
    print(f"  Result: {result['action']} — {result['message']}")
    print(f"  State: {agent.state.value}")
    print()


def scenario_recovery_after_partition():
    """Agent recovers after 2 timeouts — resets counter."""
    print("=== Scenario: Recovery After 2 Timeouts ===")
    now = time.time()
    
    agent = AgentLivenessState("recovering_agent", last_receipt_at=now - 86400 * 4)
    
    # Two timeouts
    for i in range(2):
        probe = send_probe(agent, now + i * PROBE_INTERVAL_HOURS * 3600)
        result = process_ack(agent, probe, ProbeResult.TIMEOUT,
                           now + (i + 1) * PROBE_INTERVAL_HOURS * 3600)
        print(f"  Probe {i+1}: {result['action']}")
    
    # Recovery
    probe = send_probe(agent, now + 3 * PROBE_INTERVAL_HOURS * 3600)
    result = process_ack(agent, probe, ProbeResult.ACK,
                        now + 3 * PROBE_INTERVAL_HOURS * 3600 + 1800)
    print(f"  Probe 3: {result['action']} — counter reset!")
    print(f"  Consecutive timeouts: {agent.consecutive_timeouts}")
    print(f"  State: {agent.state.value}")
    print()


def scenario_fleet_audit():
    """Fleet-level health check."""
    print("=== Scenario: Fleet Audit ===")
    now = time.time()
    
    agents = [
        AgentLivenessState("healthy_1", now - 3600, state=ReceiptState.CONFIRMED),
        AgentLivenessState("healthy_2", now - 7200, state=ReceiptState.CONFIRMED),
        AgentLivenessState("probing_1", now - 86400*2, state=ReceiptState.PROBE),
        AgentLivenessState("unconfirmed_1", now - 86400*5, state=ReceiptState.UNCONFIRMED, consecutive_timeouts=3),
        AgentLivenessState("disputed_1", now - 86400, state=ReceiptState.DISPUTED),
    ]
    
    audit = audit_fleet(agents)
    print(f"  Fleet: {audit['total_agents']} agents")
    print(f"  States: {audit['state_distribution']}")
    print(f"  Health: {audit['health']}")
    print(f"  Unconfirmed rate: {audit['unconfirmed_rate']}")
    print()


if __name__ == "__main__":
    print("Probe Receipt Handler — Liveness Probes for ATF Sparse Model")
    print("Per santaclawd + funwolf + Aguilera et al. (1997)")
    print("=" * 70)
    print()
    print("Five receipt states: CONFIRMED | FAILED | DISPUTED | PROBE | UNCONFIRMED")
    print(f"Probe interval: {PROBE_INTERVAL_HOURS}h | ACK window: {PROBE_ACK_WINDOW_HOURS}h")
    print(f"Max timeouts before UNCONFIRMED: {MAX_CONSECUTIVE_TIMEOUTS}")
    print(f"Escalation: {' → '.join(PROBE_ESCALATION_CHAIN)}")
    print()
    
    scenario_healthy_ack()
    scenario_partition_timeout()
    scenario_nack_dispute()
    scenario_recovery_after_partition()
    scenario_fleet_audit()
    
    print("=" * 70)
    print("KEY INSIGHT: Silence is ambiguous. PROBE makes it unambiguous.")
    print("No ACK after PROBE = UNCONFIRMED (partition or failure).")
    print("No ACK without PROBE = still could be CONFIRMED (sparse model).")
    print("SMTP VRFY parallel: proves channel works, not just content.")
