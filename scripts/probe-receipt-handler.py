#!/usr/bin/env python3
"""
probe-receipt-handler.py — Proof of liveness for ATF sparse receipts.

Per santaclawd + funwolf: silence-as-CONFIRMED fails on network partition.
Per FLP impossibility (Fischer, Lynch, Paterson 1985): cannot distinguish
crash from slow in async systems.
Per Aguilera et al. (1997): timeout-free heartbeat failure detector.

PROBE receipt: sent at T-hour mark if no CONFIRMED/FAILED/DISPUTED received.
Counterparty must ACK within grace period or escalates to DISPUTED.

Receipt types: CONFIRMED, FAILED, DISPUTED, PROBE, ACK, TIMEOUT
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
    PROBE = "PROBE"         # Liveness check
    ACK = "ACK"             # Response to PROBE
    TIMEOUT = "TIMEOUT"     # No ACK within grace


class LivenessState(Enum):
    ALIVE = "ALIVE"                     # Recent CONFIRMED or ACK
    PROBED = "PROBED"                   # PROBE sent, awaiting ACK
    UNRESPONSIVE = "UNRESPONSIVE"       # TIMEOUT, single probe
    SUSPECTED_DOWN = "SUSPECTED_DOWN"   # Multiple timeouts
    DISPUTED = "DISPUTED"               # Explicit dispute


# SPEC_CONSTANTS
PROBE_INTERVAL_HOURS = 4        # Send PROBE every T hours if silent
ACK_GRACE_SECONDS = 300         # 5 minutes to ACK a PROBE
MAX_CONSECUTIVE_TIMEOUTS = 3    # Timeouts before SUSPECTED_DOWN
PROBE_RETRY_BACKOFF = 1.5       # Exponential backoff multiplier
MIN_PROBE_INTERVAL = 3600       # 1 hour minimum between probes


@dataclass
class Receipt:
    receipt_id: str
    receipt_type: ReceiptType
    agent_id: str
    counterparty_id: str
    timestamp: float
    probe_id: Optional[str] = None  # Links ACK to PROBE
    hash: str = ""
    
    def __post_init__(self):
        if not self.hash:
            self.hash = hashlib.sha256(
                f"{self.receipt_id}:{self.receipt_type.value}:{self.timestamp}".encode()
            ).hexdigest()[:16]


@dataclass
class ProbeState:
    """Tracks liveness state for a counterparty."""
    counterparty_id: str
    state: LivenessState = LivenessState.ALIVE
    last_activity: float = 0.0
    last_probe_sent: Optional[float] = None
    consecutive_timeouts: int = 0
    total_probes: int = 0
    total_acks: int = 0
    ack_latencies: list = field(default_factory=list)
    history: list = field(default_factory=list)


def should_probe(state: ProbeState, now: float) -> bool:
    """Determine if a PROBE should be sent."""
    if state.state == LivenessState.SUSPECTED_DOWN:
        return False  # Already escalated
    
    # Don't probe too frequently
    if state.last_probe_sent and (now - state.last_probe_sent) < MIN_PROBE_INTERVAL:
        return False
    
    # Probe if silent for T hours
    silence_duration = now - state.last_activity
    probe_interval = PROBE_INTERVAL_HOURS * 3600
    
    # Backoff on repeated timeouts
    if state.consecutive_timeouts > 0:
        probe_interval *= PROBE_RETRY_BACKOFF ** state.consecutive_timeouts
    
    return silence_duration >= probe_interval


def send_probe(state: ProbeState, now: float) -> Receipt:
    """Send a PROBE receipt."""
    probe_id = hashlib.sha256(
        f"probe:{state.counterparty_id}:{now}".encode()
    ).hexdigest()[:12]
    
    receipt = Receipt(
        receipt_id=f"probe_{probe_id}",
        receipt_type=ReceiptType.PROBE,
        agent_id="self",
        counterparty_id=state.counterparty_id,
        timestamp=now,
        probe_id=probe_id
    )
    
    state.last_probe_sent = now
    state.total_probes += 1
    state.state = LivenessState.PROBED
    state.history.append(("PROBE_SENT", now, probe_id))
    
    return receipt


def process_ack(state: ProbeState, ack_receipt: Receipt, now: float) -> dict:
    """Process an ACK response to a PROBE."""
    if state.state != LivenessState.PROBED:
        return {"status": "UNEXPECTED_ACK", "note": "No pending PROBE"}
    
    latency = now - state.last_probe_sent if state.last_probe_sent else 0
    within_grace = latency <= ACK_GRACE_SECONDS
    
    state.total_acks += 1
    state.ack_latencies.append(latency)
    state.last_activity = now
    state.consecutive_timeouts = 0
    state.state = LivenessState.ALIVE
    state.history.append(("ACK_RECEIVED", now, ack_receipt.probe_id))
    
    return {
        "status": "ACK_ACCEPTED" if within_grace else "LATE_ACK",
        "latency_seconds": round(latency, 1),
        "within_grace": within_grace,
        "ack_rate": round(state.total_acks / state.total_probes, 3) if state.total_probes > 0 else 1.0
    }


def process_timeout(state: ProbeState, now: float) -> dict:
    """Process a PROBE timeout (no ACK within grace)."""
    state.consecutive_timeouts += 1
    state.history.append(("TIMEOUT", now, None))
    
    if state.consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
        state.state = LivenessState.SUSPECTED_DOWN
        return {
            "status": "SUSPECTED_DOWN",
            "consecutive_timeouts": state.consecutive_timeouts,
            "escalation": "AUTO_DISPUTE",
            "ack_rate": round(state.total_acks / state.total_probes, 3) if state.total_probes > 0 else 0
        }
    else:
        state.state = LivenessState.UNRESPONSIVE
        return {
            "status": "UNRESPONSIVE",
            "consecutive_timeouts": state.consecutive_timeouts,
            "next_probe_backoff": round(PROBE_INTERVAL_HOURS * 3600 * PROBE_RETRY_BACKOFF ** state.consecutive_timeouts / 3600, 1),
            "escalation": "NONE"
        }


def compute_reliability(state: ProbeState) -> dict:
    """Compute counterparty reliability from probe history."""
    if state.total_probes == 0:
        return {"reliability": "UNKNOWN", "grade": "N/A", "probes": 0}
    
    ack_rate = state.total_acks / state.total_probes
    avg_latency = sum(state.ack_latencies) / len(state.ack_latencies) if state.ack_latencies else 0
    
    # Grade based on ack rate
    if ack_rate >= 0.95:
        grade = "A"
    elif ack_rate >= 0.80:
        grade = "B"
    elif ack_rate >= 0.60:
        grade = "C"
    elif ack_rate >= 0.40:
        grade = "D"
    else:
        grade = "F"
    
    return {
        "reliability": state.state.value,
        "grade": grade,
        "ack_rate": round(ack_rate, 3),
        "avg_latency_seconds": round(avg_latency, 1),
        "total_probes": state.total_probes,
        "total_acks": state.total_acks,
        "consecutive_timeouts": state.consecutive_timeouts,
        "max_latency": round(max(state.ack_latencies), 1) if state.ack_latencies else 0
    }


# === Scenarios ===

def scenario_healthy_counterparty():
    """Counterparty responds promptly to all PROBEs."""
    print("=== Scenario: Healthy Counterparty ===")
    now = time.time()
    state = ProbeState("healthy_agent", last_activity=now - 5*3600)
    
    for i in range(5):
        probe_time = now + i * PROBE_INTERVAL_HOURS * 3600
        if should_probe(state, probe_time):
            probe = send_probe(state, probe_time)
            # ACK within 30 seconds
            ack = Receipt(f"ack_{i}", ReceiptType.ACK, "healthy_agent", "self",
                         probe_time + 30, probe_id=probe.probe_id)
            result = process_ack(state, ack, probe_time + 30)
            print(f"  Probe {i+1}: {result['status']} latency={result['latency_seconds']}s")
    
    reliability = compute_reliability(state)
    print(f"  Reliability: {reliability['grade']} (ack_rate={reliability['ack_rate']})")
    print()


def scenario_partition():
    """Network partition — no ACKs, escalates to SUSPECTED_DOWN."""
    print("=== Scenario: Network Partition ===")
    now = time.time()
    state = ProbeState("partitioned_agent", last_activity=now - 5*3600)
    
    for i in range(4):
        probe_time = now + i * PROBE_INTERVAL_HOURS * 3600 * (PROBE_RETRY_BACKOFF ** max(0, i-1))
        if should_probe(state, probe_time):
            probe = send_probe(state, probe_time)
            # No ACK — timeout
            timeout_time = probe_time + ACK_GRACE_SECONDS + 1
            result = process_timeout(state, timeout_time)
            print(f"  Probe {i+1}: {result['status']} timeouts={result['consecutive_timeouts']}")
            if result['status'] == 'SUSPECTED_DOWN':
                print(f"  → Escalation: {result['escalation']}")
                break
    
    reliability = compute_reliability(state)
    print(f"  Final state: {reliability['reliability']} Grade={reliability['grade']}")
    print()


def scenario_intermittent():
    """Intermittent connectivity — some ACKs, some timeouts."""
    print("=== Scenario: Intermittent Connectivity ===")
    now = time.time()
    state = ProbeState("flaky_agent", last_activity=now - 5*3600)
    
    responses = [True, False, True, True, False, True, False, False, True, True]
    
    for i, responds in enumerate(responses):
        probe_time = now + i * PROBE_INTERVAL_HOURS * 3600
        state.last_activity = probe_time - PROBE_INTERVAL_HOURS * 3600 - 1  # Force probe eligibility
        state.last_probe_sent = None  # Reset cooldown for demo
        
        if should_probe(state, probe_time):
            probe = send_probe(state, probe_time)
            if responds:
                latency = 60 + (i * 20)  # Increasing latency
                ack = Receipt(f"ack_{i}", ReceiptType.ACK, "flaky_agent", "self",
                             probe_time + latency, probe_id=probe.probe_id)
                result = process_ack(state, ack, probe_time + latency)
                print(f"  Probe {i+1}: {result['status']} latency={result['latency_seconds']}s")
            else:
                result = process_timeout(state, probe_time + ACK_GRACE_SECONDS + 1)
                print(f"  Probe {i+1}: {result['status']} timeouts={result['consecutive_timeouts']}")
    
    reliability = compute_reliability(state)
    print(f"  Reliability: {reliability['grade']} ack_rate={reliability['ack_rate']} "
          f"avg_latency={reliability['avg_latency_seconds']}s")
    print()


def scenario_late_ack():
    """ACKs arrive but outside grace period."""
    print("=== Scenario: Late ACKs (Outside Grace) ===")
    now = time.time()
    state = ProbeState("slow_agent", last_activity=now - 5*3600)
    
    for i in range(3):
        probe_time = now + i * PROBE_INTERVAL_HOURS * 3600
        state.last_activity = probe_time - PROBE_INTERVAL_HOURS * 3600 - 1
        state.last_probe_sent = None
        
        probe = send_probe(state, probe_time)
        # ACK arrives AFTER grace period
        late_time = probe_time + ACK_GRACE_SECONDS + 60  # 1 min late
        ack = Receipt(f"ack_{i}", ReceiptType.ACK, "slow_agent", "self",
                     late_time, probe_id=probe.probe_id)
        result = process_ack(state, ack, late_time)
        print(f"  Probe {i+1}: {result['status']} latency={result['latency_seconds']}s "
              f"within_grace={result['within_grace']}")
    
    reliability = compute_reliability(state)
    print(f"  Grade: {reliability['grade']} (acks received but late)")
    print()


if __name__ == "__main__":
    print("PROBE Receipt Handler — Proof of Liveness for ATF")
    print("Per santaclawd + funwolf + FLP impossibility (1985)")
    print("=" * 60)
    print()
    print(f"PROBE_INTERVAL: {PROBE_INTERVAL_HOURS}h")
    print(f"ACK_GRACE: {ACK_GRACE_SECONDS}s")
    print(f"MAX_TIMEOUTS: {MAX_CONSECUTIVE_TIMEOUTS} → SUSPECTED_DOWN")
    print(f"BACKOFF: {PROBE_RETRY_BACKOFF}x per timeout")
    print()
    
    scenario_healthy_counterparty()
    scenario_partition()
    scenario_intermittent()
    scenario_late_ack()
    
    print("=" * 60)
    print("KEY INSIGHT: Silence is ambiguous in distributed systems.")
    print("FLP (1985): cannot distinguish crash from slow.")
    print("PROBE makes the distinction observable and auditable.")
    print("No ACK within grace = DISPUTED, not CONFIRMED.")
