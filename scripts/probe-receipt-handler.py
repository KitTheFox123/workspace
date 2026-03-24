#!/usr/bin/env python3
"""
probe-receipt-handler.py — Liveness probing for ATF sparse receipt model.

Per santaclawd: silence-as-CONFIRMED fails on network partition.
Cannot distinguish "delivered + confirmed" from "delivery failed."

PROBE receipt: sent at T-hour mark if no FAILED/DISPUTED received.
  - ACK within window → CONFIRMED
  - Silence after PROBE → DISPUTED (post-PROBE silence ≠ pre-PROBE silence)
  - PROBE delivery failure → PARTITION_SUSPECTED

Per Chandra & Toueg (1996): EVENTUALLY_STRONG failure detector
needs periodic probes to distinguish crash from partition.

Grader-of-graders (per santaclawd): Wilson CI on grader track record.
Ground truth = did counterparty dispute? Dispute IS the grading signal.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ReceiptState(Enum):
    PENDING = "PENDING"             # Awaiting any signal
    CONFIRMED = "CONFIRMED"         # ACK received (explicit or probe-ACK)
    FAILED = "FAILED"               # Explicit failure receipt
    DISPUTED = "DISPUTED"           # Explicit dispute
    PROBE_SENT = "PROBE_SENT"       # Liveness probe dispatched
    PROBE_ACKED = "PROBE_ACKED"     # Probe answered → CONFIRMED
    PROBE_SILENT = "PROBE_SILENT"   # Post-probe silence → escalate
    PARTITION = "PARTITION"         # Probe delivery itself failed


class ProbeResult(Enum):
    ACK = "ACK"                     # Counterparty alive and confirms
    NACK = "NACK"                   # Counterparty alive but disputes
    SILENT = "SILENT"               # No response within window
    DELIVERY_FAILED = "DELIVERY_FAILED"  # Probe couldn't be delivered


# SPEC_CONSTANTS
PROBE_INTERVAL_HOURS = 24           # Send probe if no signal after T hours
PROBE_ACK_WINDOW_HOURS = 4          # Counterparty has 4h to respond to probe
MAX_PROBES_BEFORE_ESCALATION = 3    # After 3 unanswered probes → PARTITION
GRADER_MIN_EVENTS = 30              # Wilson CI minimum for grader reliability
GRADER_SUSPENSION_THRESHOLD = 0.4   # Disagreement rate above this → SUSPENDED


@dataclass
class Milestone:
    milestone_id: str
    scope_hash: str
    state: ReceiptState = ReceiptState.PENDING
    last_signal_at: Optional[float] = None
    probe_count: int = 0
    probe_history: list = field(default_factory=list)
    grader_id: Optional[str] = None
    grade: Optional[str] = None


@dataclass
class Probe:
    probe_id: str
    milestone_id: str
    sent_at: float
    result: Optional[ProbeResult] = None
    responded_at: Optional[float] = None
    delivery_hash: str = ""


@dataclass
class GraderRecord:
    grader_id: str
    total_gradings: int = 0
    disputed_gradings: int = 0
    agreement_rate: float = 1.0
    wilson_ci_lower: float = 0.0
    status: str = "ACTIVE"


def wilson_ci_lower(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * ((p * (1 - p) / total + z**2 / (4 * total**2)) ** 0.5)
    return max(0, (center - spread) / denominator)


def should_probe(milestone: Milestone, now: float) -> bool:
    """Determine if a probe should be sent."""
    if milestone.state in {ReceiptState.CONFIRMED, ReceiptState.FAILED, 
                           ReceiptState.DISPUTED, ReceiptState.PARTITION}:
        return False
    
    if milestone.state == ReceiptState.PROBE_SENT:
        return False  # Already probing
    
    if milestone.last_signal_at is None:
        return True  # Never heard anything
    
    hours_since_signal = (now - milestone.last_signal_at) / 3600
    return hours_since_signal >= PROBE_INTERVAL_HOURS


def send_probe(milestone: Milestone, now: float) -> Probe:
    """Create and dispatch a probe."""
    probe_id = hashlib.sha256(
        f"{milestone.milestone_id}:{milestone.probe_count}:{now}".encode()
    ).hexdigest()[:16]
    
    probe = Probe(
        probe_id=probe_id,
        milestone_id=milestone.milestone_id,
        sent_at=now,
        delivery_hash=hashlib.sha256(f"probe:{probe_id}".encode()).hexdigest()[:16]
    )
    
    milestone.state = ReceiptState.PROBE_SENT
    milestone.probe_count += 1
    milestone.probe_history.append(probe)
    
    return probe


def process_probe_result(milestone: Milestone, probe: Probe, 
                         result: ProbeResult, now: float) -> dict:
    """Process probe response and update milestone state."""
    probe.result = result
    probe.responded_at = now
    
    if result == ProbeResult.ACK:
        milestone.state = ReceiptState.CONFIRMED
        milestone.last_signal_at = now
        return {"action": "CONFIRMED", "detail": "Probe ACKed — counterparty alive and confirms"}
    
    elif result == ProbeResult.NACK:
        milestone.state = ReceiptState.DISPUTED
        milestone.last_signal_at = now
        return {"action": "DISPUTED", "detail": "Probe NACKed — counterparty alive but disputes"}
    
    elif result == ProbeResult.SILENT:
        if milestone.probe_count >= MAX_PROBES_BEFORE_ESCALATION:
            milestone.state = ReceiptState.PARTITION
            return {"action": "PARTITION", 
                    "detail": f"Silent after {milestone.probe_count} probes — partition suspected"}
        else:
            milestone.state = ReceiptState.PROBE_SILENT
            return {"action": "PROBE_SILENT", 
                    "detail": f"Silent after probe {milestone.probe_count}/{MAX_PROBES_BEFORE_ESCALATION}"}
    
    elif result == ProbeResult.DELIVERY_FAILED:
        milestone.state = ReceiptState.PARTITION
        return {"action": "PARTITION", "detail": "Probe delivery failed — network partition"}
    
    return {"action": "UNKNOWN", "detail": "Unhandled probe result"}


def evaluate_grader(grader: GraderRecord) -> dict:
    """Evaluate grader reliability using Wilson CI."""
    agreements = grader.total_gradings - grader.disputed_gradings
    grader.agreement_rate = agreements / grader.total_gradings if grader.total_gradings > 0 else 0
    grader.wilson_ci_lower = wilson_ci_lower(agreements, grader.total_gradings)
    
    if grader.total_gradings < GRADER_MIN_EVENTS:
        grader.status = "PROVISIONAL"
        detail = f"Insufficient events ({grader.total_gradings}/{GRADER_MIN_EVENTS})"
    elif grader.agreement_rate < (1 - GRADER_SUSPENSION_THRESHOLD):
        grader.status = "SUSPENDED"
        detail = f"High disagreement rate ({1-grader.agreement_rate:.1%})"
    else:
        grader.status = "ACTIVE"
        detail = f"Reliable (Wilson CI lower: {grader.wilson_ci_lower:.3f})"
    
    return {
        "grader_id": grader.grader_id,
        "status": grader.status,
        "agreement_rate": round(grader.agreement_rate, 3),
        "wilson_ci_lower": round(grader.wilson_ci_lower, 3),
        "total_events": grader.total_gradings,
        "detail": detail
    }


# === Scenarios ===

def scenario_normal_probe_ack():
    """Silence then probe → ACK → CONFIRMED."""
    print("=== Scenario: Normal Probe → ACK ===")
    now = time.time()
    m = Milestone("m001", "scope_abc123", last_signal_at=now - 25*3600)
    
    print(f"  State: {m.state.value}, hours since signal: 25")
    print(f"  Should probe: {should_probe(m, now)}")
    
    probe = send_probe(m, now)
    print(f"  Probe sent: {probe.probe_id}, state: {m.state.value}")
    
    result = process_probe_result(m, probe, ProbeResult.ACK, now + 3600)
    print(f"  Result: {result['action']} — {result['detail']}")
    print(f"  Final state: {m.state.value}")
    print()


def scenario_escalating_silence():
    """Three silent probes → PARTITION."""
    print("=== Scenario: Escalating Silence → PARTITION ===")
    now = time.time()
    m = Milestone("m002", "scope_def456", last_signal_at=now - 25*3600)
    
    for i in range(3):
        probe_time = now + i * 25 * 3600
        probe = send_probe(m, probe_time)
        result = process_probe_result(m, probe, ProbeResult.SILENT, probe_time + 5*3600)
        print(f"  Probe {i+1}: {result['action']} — {result['detail']}")
        if m.state != ReceiptState.PARTITION:
            m.state = ReceiptState.PENDING  # Reset for next probe cycle
    
    print(f"  Final state: {m.state.value}")
    print(f"  Total probes: {m.probe_count}")
    print()


def scenario_probe_nack():
    """Probe → NACK → DISPUTED."""
    print("=== Scenario: Probe → NACK (Dispute) ===")
    now = time.time()
    m = Milestone("m003", "scope_ghi789", last_signal_at=now - 30*3600)
    
    probe = send_probe(m, now)
    result = process_probe_result(m, probe, ProbeResult.NACK, now + 2*3600)
    print(f"  Result: {result['action']} — {result['detail']}")
    print(f"  Key insight: NACK is BETTER than silence. Counterparty is alive and engaged.")
    print()


def scenario_delivery_failure():
    """Probe can't be delivered → immediate PARTITION."""
    print("=== Scenario: Probe Delivery Failure → PARTITION ===")
    now = time.time()
    m = Milestone("m004", "scope_jkl012", last_signal_at=now - 48*3600)
    
    probe = send_probe(m, now)
    result = process_probe_result(m, probe, ProbeResult.DELIVERY_FAILED, now)
    print(f"  Result: {result['action']} — {result['detail']}")
    print(f"  No ambiguity: if probe can't reach counterparty, partition is certain.")
    print()


def scenario_grader_evaluation():
    """Grader-of-graders via Wilson CI."""
    print("=== Scenario: Grader Reliability Evaluation ===")
    
    graders = [
        GraderRecord("reliable_grader", total_gradings=50, disputed_gradings=3),
        GraderRecord("new_grader", total_gradings=8, disputed_gradings=1),
        GraderRecord("bad_grader", total_gradings=40, disputed_gradings=20),
        GraderRecord("perfect_grader", total_gradings=100, disputed_gradings=0),
    ]
    
    for g in graders:
        result = evaluate_grader(g)
        print(f"  {result['grader_id']}: {result['status']} "
              f"(agreement={result['agreement_rate']:.1%}, "
              f"Wilson={result['wilson_ci_lower']:.3f}, "
              f"n={result['total_events']})")
    
    print()
    print("  Key: ground truth = counterparty disputes. No infinite regress.")
    print("  Dispute IS the grading signal.")
    print()


if __name__ == "__main__":
    print("Probe Receipt Handler — Liveness for ATF Sparse Receipts")
    print("Per santaclawd + Chandra & Toueg (1996)")
    print("=" * 65)
    print()
    print(f"PROBE_INTERVAL: {PROBE_INTERVAL_HOURS}h")
    print(f"ACK_WINDOW: {PROBE_ACK_WINDOW_HOURS}h")
    print(f"MAX_PROBES: {MAX_PROBES_BEFORE_ESCALATION}")
    print()
    
    scenario_normal_probe_ack()
    scenario_escalating_silence()
    scenario_probe_nack()
    scenario_delivery_failure()
    scenario_grader_evaluation()
    
    print("=" * 65)
    print("KEY INSIGHTS:")
    print("1. Pre-PROBE silence ≠ post-PROBE silence")
    print("2. NACK > silence (counterparty alive + engaged)")
    print("3. Delivery failure = certain partition (no ambiguity)")
    print("4. Grader ground truth = dispute rate (no infinite regress)")
