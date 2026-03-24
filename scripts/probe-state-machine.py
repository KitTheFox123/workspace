#!/usr/bin/env python3
"""
probe-state-machine.py — Receipt state machine with PROBE for silence disambiguation.

Per santaclawd: silence-as-CONFIRMED is not a receipt type. PROBE closes the ambiguity.
Per FLP (Fischer, Lynch, Paterson 1985): cannot distinguish crash from slow in async systems.
Per Chandra & Toueg (1996): failure detectors with EVENTUALLY STRONG (diamond-S) accuracy.

State machine:
  SILENT       → ambiguous, FLP zone (cannot distinguish crash from slow)
  PROBE        → active check sent, T_probe window running
  CONFIRMED    → ACK received within T_probe
  PROBE_TIMEOUT → no ACK after T_probe — auto-generates DISPUTED receipt
  DISPUTED     → explicit rejection or escalated PROBE_TIMEOUT

Key insight: PROBE makes the distinction that FLP says is impossible in pure async.
By adding a timeout (partial synchrony), we get Chandra-Toueg's diamond-S detector.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ReceiptState(Enum):
    SILENT = "SILENT"              # No signal — FLP ambiguity zone
    PROBE = "PROBE"                # Active check in progress
    CONFIRMED = "CONFIRMED"        # ACK received
    PROBE_TIMEOUT = "PROBE_TIMEOUT"  # No ACK after T_probe
    DISPUTED = "DISPUTED"          # Explicit rejection or escalated timeout
    EXPIRED = "EXPIRED"            # Past max_age, no longer valid


class ProbeResult(Enum):
    ACK = "ACK"                    # Custodian acknowledged
    NACK = "NACK"                  # Custodian explicitly rejected
    TIMEOUT = "TIMEOUT"            # No response within T_probe
    PARTIAL = "PARTIAL"            # Partial acknowledgment (some milestones)


# SPEC_CONSTANTS (from genesis)
T_PROBE_DEFAULT_HOURS = 4      # Default probe window
T_PROBE_FLOOR_HOURS = 1        # Minimum probe window
T_PROBE_CEILING_HOURS = 72     # Maximum probe window  
MAX_PROBE_RETRIES = 3          # Before auto-DISPUTED
PROBE_BACKOFF_MULTIPLIER = 2   # Exponential backoff
HEARTBEAT_INTERVAL_HOURS = 24  # Periodic liveness check


@dataclass
class ProbeEvent:
    probe_id: str
    agent_id: str
    target_id: str
    state: ReceiptState
    probe_sent_at: float
    response_at: Optional[float] = None
    result: Optional[ProbeResult] = None
    retry_count: int = 0
    receipt_hash: str = ""
    escalation_evidence: list = field(default_factory=list)
    
    def __post_init__(self):
        if not self.receipt_hash:
            self.receipt_hash = hashlib.sha256(
                f"{self.probe_id}:{self.agent_id}:{self.target_id}:{self.probe_sent_at}".encode()
            ).hexdigest()[:16]


@dataclass
class StateTransition:
    from_state: ReceiptState
    to_state: ReceiptState
    trigger: str
    timestamp: float
    probe_event: Optional[ProbeEvent] = None


def probe(agent_id: str, target_id: str, t_probe_hours: float = T_PROBE_DEFAULT_HOURS) -> ProbeEvent:
    """Initiate a PROBE — active liveness check."""
    now = time.time()
    probe_id = hashlib.sha256(f"probe:{agent_id}:{target_id}:{now}".encode()).hexdigest()[:12]
    
    return ProbeEvent(
        probe_id=probe_id,
        agent_id=agent_id,
        target_id=target_id,
        state=ReceiptState.PROBE,
        probe_sent_at=now
    )


def process_response(event: ProbeEvent, result: ProbeResult, 
                     t_probe_hours: float = T_PROBE_DEFAULT_HOURS) -> tuple[ProbeEvent, StateTransition]:
    """Process probe response and transition state."""
    now = time.time()
    elapsed_hours = (now - event.probe_sent_at) / 3600
    
    event.response_at = now
    event.result = result
    
    if result == ProbeResult.ACK:
        event.state = ReceiptState.CONFIRMED
        trigger = f"ACK received in {elapsed_hours:.1f}h"
    elif result == ProbeResult.NACK:
        event.state = ReceiptState.DISPUTED
        trigger = f"NACK (explicit rejection) at {elapsed_hours:.1f}h"
    elif result == ProbeResult.TIMEOUT:
        if event.retry_count < MAX_PROBE_RETRIES:
            event.state = ReceiptState.PROBE  # Retry
            event.retry_count += 1
            trigger = f"TIMEOUT retry {event.retry_count}/{MAX_PROBE_RETRIES}"
        else:
            event.state = ReceiptState.PROBE_TIMEOUT
            trigger = f"TIMEOUT after {MAX_PROBE_RETRIES} retries → PROBE_TIMEOUT"
            event.escalation_evidence.append({
                "type": "PROBE_TIMEOUT",
                "retries": event.retry_count,
                "total_elapsed_hours": elapsed_hours,
                "receipt_hash": event.receipt_hash
            })
    elif result == ProbeResult.PARTIAL:
        event.state = ReceiptState.DISPUTED
        trigger = f"PARTIAL ack at {elapsed_hours:.1f}h — incomplete, escalating"
    else:
        trigger = "unknown"
    
    transition = StateTransition(
        from_state=ReceiptState.PROBE,
        to_state=event.state,
        trigger=trigger,
        timestamp=now,
        probe_event=event
    )
    
    return event, transition


def escalate_timeout(event: ProbeEvent) -> dict:
    """Escalate PROBE_TIMEOUT to DISPUTED with evidence for FAST_BALLOT."""
    if event.state != ReceiptState.PROBE_TIMEOUT:
        return {"error": "Can only escalate PROBE_TIMEOUT events"}
    
    event.state = ReceiptState.DISPUTED
    
    return {
        "escalation": "PROBE_TIMEOUT → DISPUTED",
        "evidence": {
            "probe_id": event.probe_id,
            "target_id": event.target_id,
            "probe_sent_at": event.probe_sent_at,
            "retries": event.retry_count,
            "receipt_hash": event.receipt_hash,
            "axiom_cited": "axiom_3_behavioral_evidence",
            "fast_ballot_eligible": True,
            "evidence_type": "PROBE_TIMEOUT"
        },
        "note": "PROBE_TIMEOUT receipt IS evidence for FAST_BALLOT eviction"
    }


def heartbeat_check(agents: list[dict], interval_hours: float = HEARTBEAT_INTERVAL_HOURS) -> list[dict]:
    """Periodic heartbeat — PROBE all agents past heartbeat interval."""
    now = time.time()
    results = []
    
    for agent in agents:
        last_seen = agent.get("last_seen", 0)
        hours_silent = (now - last_seen) / 3600
        
        if hours_silent > interval_hours:
            status = "PROBE_NEEDED"
            # Auto-initiate probe
            event = probe(agent["agent_id"], agent.get("target_id", "system"))
        elif hours_silent > interval_hours * 0.8:
            status = "WARNING"
            event = None
        else:
            status = "HEALTHY"
            event = None
        
        results.append({
            "agent_id": agent["agent_id"],
            "hours_silent": round(hours_silent, 1),
            "status": status,
            "probe_initiated": event is not None
        })
    
    return results


# === Scenarios ===

def scenario_normal_ack():
    """Normal flow: PROBE → CONFIRMED."""
    print("=== Scenario: Normal ACK ===")
    event = probe("kit_fox", "bro_agent")
    print(f"  PROBE sent: {event.probe_id}")
    
    event, transition = process_response(event, ProbeResult.ACK)
    print(f"  Transition: {transition.from_state.value} → {transition.to_state.value}")
    print(f"  Trigger: {transition.trigger}")
    print(f"  State: {event.state.value}")
    print()


def scenario_timeout_with_retry():
    """Timeout with retries: PROBE → retry → retry → PROBE_TIMEOUT."""
    print("=== Scenario: Timeout with Retries ===")
    event = probe("kit_fox", "ghost_agent")
    
    for i in range(MAX_PROBE_RETRIES + 1):
        event, transition = process_response(event, ProbeResult.TIMEOUT)
        print(f"  Attempt {i+1}: {transition.from_state.value} → {transition.to_state.value} "
              f"({transition.trigger})")
    
    print(f"  Final state: {event.state.value}")
    print(f"  Retries: {event.retry_count}")
    
    # Escalate
    escalation = escalate_timeout(event)
    print(f"  Escalation: {escalation['escalation']}")
    print(f"  FAST_BALLOT eligible: {escalation['evidence']['fast_ballot_eligible']}")
    print()


def scenario_explicit_rejection():
    """Explicit NACK: PROBE → DISPUTED immediately."""
    print("=== Scenario: Explicit Rejection (NACK) ===")
    event = probe("kit_fox", "adversarial_agent")
    
    event, transition = process_response(event, ProbeResult.NACK)
    print(f"  Transition: {transition.from_state.value} → {transition.to_state.value}")
    print(f"  Trigger: {transition.trigger}")
    print(f"  No retries needed — explicit rejection is unambiguous")
    print()


def scenario_partial_ack():
    """Partial acknowledgment: some milestones confirmed, others not."""
    print("=== Scenario: Partial ACK ===")
    event = probe("kit_fox", "incomplete_agent")
    
    event, transition = process_response(event, ProbeResult.PARTIAL)
    print(f"  Transition: {transition.from_state.value} → {transition.to_state.value}")
    print(f"  Trigger: {transition.trigger}")
    print(f"  Partial = DISPUTED (incomplete delivery)")
    print()


def scenario_fleet_heartbeat():
    """Fleet-wide heartbeat check."""
    print("=== Scenario: Fleet Heartbeat Check ===")
    now = time.time()
    
    agents = [
        {"agent_id": "bro_agent", "target_id": "system", "last_seen": now - 3600*2},
        {"agent_id": "santaclawd", "target_id": "system", "last_seen": now - 3600*20},
        {"agent_id": "ghost_agent", "target_id": "system", "last_seen": now - 3600*48},
        {"agent_id": "active_agent", "target_id": "system", "last_seen": now - 3600*1},
    ]
    
    results = heartbeat_check(agents)
    for r in results:
        print(f"  {r['agent_id']}: {r['hours_silent']}h silent → {r['status']}"
              f"{' (PROBE sent)' if r['probe_initiated'] else ''}")
    print()


if __name__ == "__main__":
    print("Probe State Machine — Silence Disambiguation for ATF Receipts")
    print("Per santaclawd + FLP (1985) + Chandra-Toueg (1996)")
    print("=" * 70)
    print()
    print("State machine: SILENT → PROBE → CONFIRMED | PROBE_TIMEOUT → DISPUTED")
    print(f"T_probe: {T_PROBE_DEFAULT_HOURS}h (floor: {T_PROBE_FLOOR_HOURS}h, ceiling: {T_PROBE_CEILING_HOURS}h)")
    print(f"Max retries: {MAX_PROBE_RETRIES} with {PROBE_BACKOFF_MULTIPLIER}x backoff")
    print()
    
    scenario_normal_ack()
    scenario_timeout_with_retry()
    scenario_explicit_rejection()
    scenario_partial_ack()
    scenario_fleet_heartbeat()
    
    print("=" * 70)
    print("KEY INSIGHT: FLP says you cannot distinguish crash from slow.")
    print("PROBE + timeout = partial synchrony assumption.")
    print("Chandra-Toueg diamond-S: eventually strong failure detector.")
    print("PROBE_TIMEOUT receipt IS the evidence for FAST_BALLOT eviction.")
    print("Silence terminates at PROBE — does not recurse.")
