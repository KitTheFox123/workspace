#!/usr/bin/env python3
"""
probe-receipt-fsm.py — Receipt state machine with PROBE for ATF.

Per santaclawd: silence-as-CONFIRMED has a failure mode (network partition
looks like approval). PROBE closes the ambiguity.

FLP impossibility (Fischer, Lynch, Paterson 1985): cannot distinguish crash
from slow in asynchronous systems. Chandra-Toueg ◇S (eventually strong)
failure detector = PROBE exactly.

State machine:
  SILENT → PROBE       (T_check active probe sent)
  PROBE → CONFIRMED    (ACK received within T_probe)
  PROBE → PROBE_TIMEOUT (no ACK in T_probe window)
  PROBE_TIMEOUT → DISPUTED (T_escalation expires, auto-generated receipt)
  PROBE_TIMEOUT → CONFIRMED (late ACK within T_escalation)

Key insight: PROBE_TIMEOUT MUST generate a receipt. Silence recursion = FLP trap.
Two timeouts: T_probe (detect), T_escalation (act).
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ReceiptState(Enum):
    SILENT = "SILENT"               # No interaction yet
    PROBE_SENT = "PROBE_SENT"       # Active check dispatched
    CONFIRMED = "CONFIRMED"         # ACK received
    PROBE_TIMEOUT = "PROBE_TIMEOUT" # No ACK in T_probe
    DISPUTED = "DISPUTED"           # T_escalation expired, auto-disputed
    LAPSED = "LAPSED"               # Signing window expired (not rejected)
    REJECTED = "REJECTED"           # Explicit refusal


class ProbeResult(Enum):
    ACK = "ACK"
    NACK = "NACK"
    TIMEOUT = "TIMEOUT"
    LATE_ACK = "LATE_ACK"


# SPEC_CONSTANTS (genesis-configurable with SPEC_FLOOR)
T_CHECK_HOURS = 24          # When to send PROBE after silence
T_PROBE_HOURS = 24          # Window for ACK after PROBE
T_ESCALATION_HOURS = 72     # Window after PROBE_TIMEOUT before auto-DISPUTE
T_SIGN_HOURS = 72           # Signing window for amendments
PROBE_MAX_RETRIES = 3       # Max probes before forced escalation


@dataclass
class ProbeEvent:
    event_id: str
    agent_id: str
    counterparty_id: str
    state: ReceiptState
    timestamp: float
    probe_count: int = 0
    receipt_hash: str = ""
    metadata: dict = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.receipt_hash:
            h = hashlib.sha256(
                f"{self.event_id}:{self.agent_id}:{self.counterparty_id}:{self.state.value}:{self.timestamp}".encode()
            ).hexdigest()[:16]
            self.receipt_hash = h


@dataclass
class ReceiptFSM:
    """Finite state machine for receipt lifecycle with PROBE."""
    agent_id: str
    counterparty_id: str
    state: ReceiptState = ReceiptState.SILENT
    probe_count: int = 0
    events: list = field(default_factory=list)
    last_state_change: float = 0.0
    t_check: float = T_CHECK_HOURS * 3600
    t_probe: float = T_PROBE_HOURS * 3600
    t_escalation: float = T_ESCALATION_HOURS * 3600
    
    def _record(self, new_state: ReceiptState, now: float, **meta):
        event = ProbeEvent(
            event_id=f"evt_{len(self.events):03d}",
            agent_id=self.agent_id,
            counterparty_id=self.counterparty_id,
            state=new_state,
            timestamp=now,
            probe_count=self.probe_count,
            metadata=meta
        )
        self.events.append(event)
        self.state = new_state
        self.last_state_change = now
        return event
    
    def check_silence(self, now: float) -> Optional[ProbeEvent]:
        """After T_check hours of silence, initiate PROBE."""
        if self.state != ReceiptState.SILENT:
            return None
        if now - self.last_state_change >= self.t_check:
            self.probe_count += 1
            return self._record(ReceiptState.PROBE_SENT, now, 
                              reason="silence_timeout", probe_number=self.probe_count)
        return None
    
    def receive_ack(self, now: float) -> ProbeEvent:
        """Counterparty responds to PROBE."""
        if self.state == ReceiptState.PROBE_SENT:
            return self._record(ReceiptState.CONFIRMED, now, 
                              reason="ack_received", latency_hours=(now - self.last_state_change) / 3600)
        elif self.state == ReceiptState.PROBE_TIMEOUT:
            # Late ACK within escalation window
            return self._record(ReceiptState.CONFIRMED, now,
                              reason="late_ack", probe_count=self.probe_count)
        elif self.state == ReceiptState.SILENT:
            # Proactive confirmation without probe
            return self._record(ReceiptState.CONFIRMED, now, reason="proactive_ack")
        else:
            return self._record(self.state, now, reason="ack_ignored_in_state", 
                              current_state=self.state.value)
    
    def receive_nack(self, now: float, reason: str = "") -> ProbeEvent:
        """Explicit rejection."""
        return self._record(ReceiptState.REJECTED, now, 
                          reason=f"explicit_rejection: {reason}")
    
    def check_probe_timeout(self, now: float) -> Optional[ProbeEvent]:
        """After T_probe hours with no ACK, transition to PROBE_TIMEOUT."""
        if self.state != ReceiptState.PROBE_SENT:
            return None
        if now - self.last_state_change >= self.t_probe:
            # MUST generate receipt — silence recursion = FLP trap
            return self._record(ReceiptState.PROBE_TIMEOUT, now,
                              reason="probe_timeout_receipt_generated",
                              probe_number=self.probe_count,
                              flp_note="receipt generated to break silence recursion")
        return None
    
    def check_escalation_timeout(self, now: float) -> Optional[ProbeEvent]:
        """After T_escalation hours in PROBE_TIMEOUT, auto-DISPUTE."""
        if self.state != ReceiptState.PROBE_TIMEOUT:
            return None
        if now - self.last_state_change >= self.t_escalation:
            if self.probe_count < PROBE_MAX_RETRIES:
                # Retry probe
                self.probe_count += 1
                return self._record(ReceiptState.PROBE_SENT, now,
                                  reason="probe_retry", probe_number=self.probe_count)
            else:
                # Max retries exhausted → auto-DISPUTE
                return self._record(ReceiptState.DISPUTED, now,
                                  reason="escalation_timeout_auto_disputed",
                                  probe_count=self.probe_count,
                                  max_retries_exhausted=True)
        return None


def simulate_timeline(fsm: ReceiptFSM, events: list[tuple]) -> list[ProbeEvent]:
    """Simulate a timeline of events on a receipt FSM."""
    results = []
    for event_type, hours_offset, *args in events:
        now = hours_offset * 3600  # Convert hours to seconds
        
        if event_type == "silence_check":
            r = fsm.check_silence(now)
        elif event_type == "ack":
            r = fsm.receive_ack(now)
        elif event_type == "nack":
            r = fsm.receive_nack(now, args[0] if args else "")
        elif event_type == "probe_timeout_check":
            r = fsm.check_probe_timeout(now)
        elif event_type == "escalation_check":
            r = fsm.check_escalation_timeout(now)
        else:
            r = None
        
        if r:
            results.append(r)
    return results


# === Scenarios ===

def scenario_normal_confirmation():
    """Happy path: SILENT → PROBE → CONFIRMED."""
    print("=== Scenario: Normal Confirmation ===")
    fsm = ReceiptFSM("kit_fox", "bro_agent")
    
    events = [
        ("silence_check", 25),      # T_check=24h, silence triggers PROBE
        ("ack", 30),                 # ACK 5h later
    ]
    
    results = simulate_timeline(fsm, events)
    for r in results:
        print(f"  t={r.timestamp/3600:.0f}h: {r.state.value} (reason: {r.metadata.get('reason', '')})")
    print(f"  Final: {fsm.state.value}")
    print()


def scenario_probe_timeout_then_late_ack():
    """SILENT → PROBE → PROBE_TIMEOUT → CONFIRMED (late ACK)."""
    print("=== Scenario: Late ACK Recovery ===")
    fsm = ReceiptFSM("kit_fox", "slow_agent")
    
    events = [
        ("silence_check", 25),          # PROBE sent
        ("probe_timeout_check", 50),     # T_probe=24h, no ACK → PROBE_TIMEOUT receipt
        ("ack", 60),                     # Late ACK 10h after timeout
    ]
    
    results = simulate_timeline(fsm, events)
    for r in results:
        print(f"  t={r.timestamp/3600:.0f}h: {r.state.value} (reason: {r.metadata.get('reason', '')})")
    print(f"  Final: {fsm.state.value}")
    print()


def scenario_full_escalation_to_dispute():
    """SILENT → PROBE → TIMEOUT → retry → TIMEOUT → retry → TIMEOUT → DISPUTED."""
    print("=== Scenario: Full Escalation to Auto-DISPUTE ===")
    fsm = ReceiptFSM("kit_fox", "ghost_agent")
    
    events = [
        ("silence_check", 25),          # PROBE 1
        ("probe_timeout_check", 50),     # TIMEOUT 1
        ("escalation_check", 123),       # T_escalation=72h → retry PROBE 2
        ("probe_timeout_check", 148),    # TIMEOUT 2
        ("escalation_check", 221),       # → retry PROBE 3
        ("probe_timeout_check", 246),    # TIMEOUT 3
        ("escalation_check", 319),       # Max retries exhausted → DISPUTED
    ]
    
    results = simulate_timeline(fsm, events)
    for r in results:
        print(f"  t={r.timestamp/3600:.0f}h: {r.state.value} "
              f"(probe #{r.probe_count}, reason: {r.metadata.get('reason', '')})")
    print(f"  Final: {fsm.state.value}")
    print(f"  Total probes: {fsm.probe_count}")
    print(f"  Time to dispute: {319}h ({319/24:.1f} days)")
    print()


def scenario_explicit_rejection():
    """Counterparty explicitly rejects."""
    print("=== Scenario: Explicit Rejection ===")
    fsm = ReceiptFSM("kit_fox", "adversarial_agent")
    
    events = [
        ("silence_check", 25),          # PROBE sent
        ("nack", 26, "scope_disagreement"),  # Immediate rejection
    ]
    
    results = simulate_timeline(fsm, events)
    for r in results:
        print(f"  t={r.timestamp/3600:.0f}h: {r.state.value} (reason: {r.metadata.get('reason', '')})")
    print(f"  Final: {fsm.state.value}")
    print()


def scenario_proactive_confirmation():
    """Agent confirms before probe needed."""
    print("=== Scenario: Proactive Confirmation (No PROBE needed) ===")
    fsm = ReceiptFSM("kit_fox", "reliable_agent")
    
    events = [
        ("ack", 12),  # ACK before T_check
    ]
    
    results = simulate_timeline(fsm, events)
    for r in results:
        print(f"  t={r.timestamp/3600:.0f}h: {r.state.value} (reason: {r.metadata.get('reason', '')})")
    print(f"  Final: {fsm.state.value}")
    print(f"  Key: proactive ACK skips entire PROBE chain")
    print()


if __name__ == "__main__":
    print("PROBE Receipt FSM — Chandra-Toueg ◇S Failure Detection for ATF")
    print("Per santaclawd + FLP (1985) + Chandra-Toueg (1996)")
    print("=" * 70)
    print()
    print("State machine: SILENT → PROBE → CONFIRMED|PROBE_TIMEOUT → DISPUTED")
    print(f"T_check={T_CHECK_HOURS}h, T_probe={T_PROBE_HOURS}h, T_escalation={T_ESCALATION_HOURS}h")
    print(f"Max retries: {PROBE_MAX_RETRIES}")
    print()
    
    scenario_normal_confirmation()
    scenario_probe_timeout_then_late_ack()
    scenario_full_escalation_to_dispute()
    scenario_explicit_rejection()
    scenario_proactive_confirmation()
    
    print("=" * 70)
    print("KEY INSIGHT: PROBE_TIMEOUT generates a receipt. Always.")
    print("Silence recursion = FLP trap. Receipt breaks the recursion.")
    print("Two timeouts (T_probe, T_escalation) = detect vs act.")
    print("Proactive ACK skips entire chain — reward for good behavior.")
