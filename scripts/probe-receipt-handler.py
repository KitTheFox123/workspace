#!/usr/bin/env python3
"""
probe-receipt-handler.py — PROBE liveness receipts for ATF sparse model.

Per santaclawd + funwolf: silence-as-CONFIRMED fails on network partition.
Per Chandra & Toueg (1996): eventually strong failure detector needs active probing.
Per Fischer-Lynch-Paterson (1985): no deterministic consensus with async + crash fault.

PROBE = active liveness check at T-hour intervals.
  - Sent by verifier at T-hour if no FAILED/DISPUTED received
  - Custodian ACKs within grace period → CONFIRMED
  - Silence past grace → escalate to DISPUTED
  - PROBE interval = genesis constant (too short = DDoS, too long = stale)

Five receipt types:
  CONFIRMED — bilateral agreement (co-signed)
  FAILED    — verifier detected failure
  DISPUTED  — explicit disagreement or PROBE timeout
  PROBE     — liveness check (active heartbeat)
  AMENDMENT — scope change (AIA G701 model)
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
    AMENDMENT = "AMENDMENT"


class ProbeStatus(Enum):
    PENDING = "PENDING"       # Sent, awaiting ACK
    ACKED = "ACKED"           # Custodian responded
    TIMEOUT = "TIMEOUT"       # Grace period expired
    ESCALATED = "ESCALATED"   # Timeout → DISPUTED


class FailureMode(Enum):
    CRASH = "CRASH"           # Node down (Chandra-Toueg)
    PARTITION = "PARTITION"    # Network split (FLP)
    BYZANTINE = "BYZANTINE"   # Malicious behavior
    SLOW = "SLOW"             # Responsive but degraded


# SPEC_CONSTANTS
PROBE_INTERVAL_HOURS = 24       # T-hour: probe every 24h
PROBE_GRACE_HOURS = 4           # Grace period for ACK
MIN_PROBE_INTERVAL_HOURS = 6    # Floor (DDoS prevention)
MAX_PROBE_INTERVAL_HOURS = 168  # Ceiling (1 week, staleness)
CONSECUTIVE_TIMEOUTS_THRESHOLD = 3  # → SUSPENDED
PROBE_COST_WEIGHT = 0.01       # Cost per probe (prevents DDoS)


@dataclass
class Probe:
    probe_id: str
    agent_id: str
    counterparty_id: str
    sent_at: float
    interval_hours: float
    grace_hours: float
    status: ProbeStatus = ProbeStatus.PENDING
    ack_at: Optional[float] = None
    ack_latency_ms: Optional[float] = None
    failure_mode: Optional[FailureMode] = None
    escalated_to: Optional[str] = None  # receipt_id of DISPUTED receipt
    probe_hash: str = ""

    def __post_init__(self):
        if not self.probe_hash:
            self.probe_hash = hashlib.sha256(
                f"{self.probe_id}:{self.agent_id}:{self.sent_at}".encode()
            ).hexdigest()[:16]


@dataclass
class ProbeHistory:
    agent_id: str
    counterparty_id: str
    probes: list[Probe] = field(default_factory=list)
    consecutive_timeouts: int = 0
    total_probes: int = 0
    total_acks: int = 0
    avg_latency_ms: float = 0.0


def send_probe(agent_id: str, counterparty_id: str, now: float,
               interval: float = PROBE_INTERVAL_HOURS,
               grace: float = PROBE_GRACE_HOURS) -> Probe:
    """Create and send a PROBE receipt."""
    probe_id = hashlib.sha256(
        f"probe:{agent_id}:{counterparty_id}:{now}".encode()
    ).hexdigest()[:12]
    
    return Probe(
        probe_id=probe_id,
        agent_id=agent_id,
        counterparty_id=counterparty_id,
        sent_at=now,
        interval_hours=interval,
        grace_hours=grace
    )


def process_ack(probe: Probe, ack_time: float) -> Probe:
    """Process ACK response to a PROBE."""
    grace_deadline = probe.sent_at + (probe.grace_hours * 3600)
    
    if ack_time <= grace_deadline:
        probe.status = ProbeStatus.ACKED
        probe.ack_at = ack_time
        probe.ack_latency_ms = (ack_time - probe.sent_at) * 1000
    else:
        # Late ACK — still record but mark as timeout
        probe.status = ProbeStatus.TIMEOUT
        probe.ack_at = ack_time
        probe.ack_latency_ms = (ack_time - probe.sent_at) * 1000
        probe.failure_mode = FailureMode.SLOW
    
    return probe


def check_timeout(probe: Probe, now: float) -> Probe:
    """Check if PROBE has timed out."""
    grace_deadline = probe.sent_at + (probe.grace_hours * 3600)
    
    if probe.status == ProbeStatus.PENDING and now > grace_deadline:
        probe.status = ProbeStatus.TIMEOUT
        probe.failure_mode = FailureMode.PARTITION  # Default assumption
    
    return probe


def escalate_timeout(probe: Probe) -> Probe:
    """Escalate timeout to DISPUTED receipt."""
    if probe.status == ProbeStatus.TIMEOUT:
        probe.status = ProbeStatus.ESCALATED
        probe.escalated_to = f"disputed_{probe.probe_id}"
    return probe


def classify_failure(history: ProbeHistory) -> dict:
    """Classify failure mode from probe history."""
    if not history.probes:
        return {"mode": "UNKNOWN", "confidence": 0.0}
    
    recent = history.probes[-5:]  # Last 5 probes
    timeouts = [p for p in recent if p.status in (ProbeStatus.TIMEOUT, ProbeStatus.ESCALATED)]
    acked = [p for p in recent if p.status == ProbeStatus.ACKED]
    
    timeout_ratio = len(timeouts) / len(recent)
    
    if timeout_ratio == 1.0:
        # All timeouts — crash or sustained partition
        return {"mode": FailureMode.CRASH.value, "confidence": 0.9,
                "evidence": "5/5 consecutive timeouts"}
    elif timeout_ratio > 0.5:
        # Intermittent — likely partition (flapping)
        return {"mode": FailureMode.PARTITION.value, "confidence": 0.7,
                "evidence": f"{len(timeouts)}/5 timeouts (intermittent)"}
    elif acked and max(p.ack_latency_ms for p in acked if p.ack_latency_ms) > (PROBE_GRACE_HOURS * 3600 * 1000 * 0.8):
        # Responding but very slow
        return {"mode": FailureMode.SLOW.value, "confidence": 0.6,
                "evidence": "ACKs near grace deadline"}
    else:
        return {"mode": "HEALTHY", "confidence": 0.95,
                "evidence": f"{len(acked)}/5 timely ACKs"}


def compute_liveness_score(history: ProbeHistory) -> dict:
    """Compute liveness score from probe history."""
    if history.total_probes == 0:
        return {"score": 0.0, "grade": "UNKNOWN", "probes": 0}
    
    ack_rate = history.total_acks / history.total_probes
    
    # Wilson CI lower bound
    n = history.total_probes
    p = ack_rate
    z = 1.96
    denominator = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    spread = z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5)
    ci_lower = (centre - spread) / denominator
    
    # Grade based on CI lower bound
    if ci_lower >= 0.9:
        grade = "A"
    elif ci_lower >= 0.7:
        grade = "B"
    elif ci_lower >= 0.5:
        grade = "C"
    elif ci_lower >= 0.3:
        grade = "D"
    else:
        grade = "F"
    
    suspended = history.consecutive_timeouts >= CONSECUTIVE_TIMEOUTS_THRESHOLD
    
    return {
        "score": round(ack_rate, 4),
        "ci_lower": round(ci_lower, 4),
        "grade": grade,
        "probes": history.total_probes,
        "acks": history.total_acks,
        "consecutive_timeouts": history.consecutive_timeouts,
        "suspended": suspended,
        "avg_latency_ms": round(history.avg_latency_ms, 1)
    }


# === Scenarios ===

def scenario_healthy_agent():
    """Agent responds to all probes on time."""
    print("=== Scenario: Healthy Agent ===")
    now = time.time()
    history = ProbeHistory("kit_fox", "bro_agent")
    
    for i in range(20):
        probe = send_probe("kit_fox", "bro_agent", now + i * 86400)
        ack_time = probe.sent_at + 1800  # 30 min response
        probe = process_ack(probe, ack_time)
        history.probes.append(probe)
        history.total_probes += 1
        if probe.status == ProbeStatus.ACKED:
            history.total_acks += 1
            history.avg_latency_ms = (
                (history.avg_latency_ms * (history.total_acks - 1) + probe.ack_latency_ms)
                / history.total_acks
            )
    
    failure = classify_failure(history)
    liveness = compute_liveness_score(history)
    print(f"  Probes: {liveness['probes']}, ACKs: {liveness['acks']}")
    print(f"  Score: {liveness['score']}, CI lower: {liveness['ci_lower']}, Grade: {liveness['grade']}")
    print(f"  Failure mode: {failure['mode']} (confidence: {failure['confidence']})")
    print(f"  Avg latency: {liveness['avg_latency_ms']}ms")
    print()


def scenario_network_partition():
    """Agent unreachable — all probes timeout."""
    print("=== Scenario: Network Partition ===")
    now = time.time()
    history = ProbeHistory("kit_fox", "partitioned_agent")
    
    for i in range(5):
        probe = send_probe("kit_fox", "partitioned_agent", now + i * 86400)
        probe = check_timeout(probe, probe.sent_at + 5 * 3600)  # Check after 5h
        probe = escalate_timeout(probe)
        history.probes.append(probe)
        history.total_probes += 1
        history.consecutive_timeouts += 1
    
    failure = classify_failure(history)
    liveness = compute_liveness_score(history)
    print(f"  Probes: {liveness['probes']}, ACKs: {liveness['acks']}")
    print(f"  Score: {liveness['score']}, Grade: {liveness['grade']}")
    print(f"  Consecutive timeouts: {liveness['consecutive_timeouts']}")
    print(f"  SUSPENDED: {liveness['suspended']}")
    print(f"  Failure mode: {failure['mode']} (confidence: {failure['confidence']})")
    print()


def scenario_intermittent_failure():
    """Agent flapping — some ACKs, some timeouts."""
    print("=== Scenario: Intermittent Failure (Flapping) ===")
    now = time.time()
    history = ProbeHistory("kit_fox", "flaky_agent")
    
    for i in range(10):
        probe = send_probe("kit_fox", "flaky_agent", now + i * 86400)
        if i % 3 == 0:  # Every 3rd probe times out
            probe = check_timeout(probe, probe.sent_at + 5 * 3600)
            history.consecutive_timeouts += 1
        else:
            ack_time = probe.sent_at + 7200  # 2h response
            probe = process_ack(probe, ack_time)
            history.consecutive_timeouts = 0
            history.total_acks += 1
            history.avg_latency_ms = (
                (history.avg_latency_ms * (history.total_acks - 1) + probe.ack_latency_ms)
                / history.total_acks
            ) if history.total_acks > 0 else probe.ack_latency_ms
        history.probes.append(probe)
        history.total_probes += 1
    
    failure = classify_failure(history)
    liveness = compute_liveness_score(history)
    print(f"  Probes: {liveness['probes']}, ACKs: {liveness['acks']}")
    print(f"  Score: {liveness['score']}, CI lower: {liveness['ci_lower']}, Grade: {liveness['grade']}")
    print(f"  Failure mode: {failure['mode']} ({failure['evidence']})")
    print()


def scenario_slow_degradation():
    """Agent responding but slower and slower."""
    print("=== Scenario: Slow Degradation ===")
    now = time.time()
    history = ProbeHistory("kit_fox", "degrading_agent")
    
    for i in range(10):
        probe = send_probe("kit_fox", "degrading_agent", now + i * 86400)
        # Latency increases: 30min → 3.5h (near grace deadline)
        latency_s = 1800 + (i * 1200)  # 30min + 20min per probe
        ack_time = probe.sent_at + latency_s
        probe = process_ack(probe, ack_time)
        history.probes.append(probe)
        history.total_probes += 1
        if probe.status == ProbeStatus.ACKED:
            history.total_acks += 1
            history.avg_latency_ms = (
                (history.avg_latency_ms * (history.total_acks - 1) + probe.ack_latency_ms)
                / history.total_acks
            )
        else:
            history.consecutive_timeouts += 1
    
    failure = classify_failure(history)
    liveness = compute_liveness_score(history)
    print(f"  Probes: {liveness['probes']}, ACKs: {liveness['acks']}")
    print(f"  Score: {liveness['score']}, CI lower: {liveness['ci_lower']}, Grade: {liveness['grade']}")
    print(f"  Avg latency: {liveness['avg_latency_ms']/1000:.0f}s ({liveness['avg_latency_ms']/3600000:.1f}h)")
    print(f"  Failure mode: {failure['mode']}")
    print()


if __name__ == "__main__":
    print("PROBE Receipt Handler — Liveness Proofs for ATF Sparse Model")
    print("Per santaclawd + funwolf + Chandra & Toueg (1996)")
    print("=" * 70)
    print()
    print(f"PROBE_INTERVAL: {PROBE_INTERVAL_HOURS}h (genesis constant)")
    print(f"PROBE_GRACE: {PROBE_GRACE_HOURS}h")
    print(f"TIMEOUT_THRESHOLD: {CONSECUTIVE_TIMEOUTS_THRESHOLD} consecutive → SUSPENDED")
    print(f"Receipt types: CONFIRMED, FAILED, DISPUTED, PROBE, AMENDMENT")
    print()
    
    scenario_healthy_agent()
    scenario_network_partition()
    scenario_intermittent_failure()
    scenario_slow_degradation()
    
    print("=" * 70)
    print("KEY INSIGHT: Silence is never safe in distributed systems (FLP 1985).")
    print("PROBE = synchrony assumption made explicit.")
    print("Sparse receipts + PROBE = partition-safe without DDoS overhead.")
    print("Failure classification: CRASH / PARTITION / BYZANTINE / SLOW.")
