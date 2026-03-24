#!/usr/bin/env python3
"""
probe-state-machine.py — ATF receipt probe state machine.

Per santaclawd: silence-as-CONFIRMED is not a receipt type. PROBE closes the ambiguity.
Per Chandra & Toueg (1996): eventually-strong failure detector (◇S).

State machine:
  SILENT → PROBE_SENT (T-hour active check)
  PROBE_SENT → CONFIRMED (ACK received within T_probe)
  PROBE_SENT → PROBE_TIMEOUT (no ACK in T_probe window)
  PROBE_TIMEOUT → DISPUTED (auto-escalated, no human flag needed)

Key invariant: silence NEVER produces a receipt. Every receipt is an explicit act.
Three PROBE_TIMEOUTs in 7 days → DEGRADED.

FLP impossibility (1985): cannot distinguish crash from slow in async system.
◇S: eventually accurate — false suspicions are temporary, real crashes are permanent.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ProbeState(Enum):
    SILENT = "SILENT"              # No interaction, no receipt
    PROBE_SENT = "PROBE_SENT"     # Active check dispatched
    CONFIRMED = "CONFIRMED"        # ACK received
    PROBE_TIMEOUT = "PROBE_TIMEOUT"  # No ACK within window
    DISPUTED = "DISPUTED"          # Auto-escalated from timeout


class AgentHealth(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"      # 3+ timeouts in 7d
    QUARANTINED = "QUARANTINED"  # 5+ timeouts or operator-level issue


# SPEC_CONSTANTS
T_PROBE_DEFAULT_SECONDS = 3600     # 1 hour
T_PROBE_FLOOR_SECONDS = 300        # 5 minutes minimum
T_PROBE_CEILING_SECONDS = 86400    # 24 hours maximum
TIMEOUT_DEGRADED_THRESHOLD = 3     # timeouts in window
TIMEOUT_QUARANTINE_THRESHOLD = 5
TIMEOUT_WINDOW_DAYS = 7
SIGNING_WINDOW_DEFAULT = 86400     # 24h for amendment signing


@dataclass
class ProbeReceipt:
    """Receipt generated at each state transition."""
    receipt_id: str
    agent_id: str
    counterparty_id: str
    state: ProbeState
    timestamp: float
    prev_receipt_hash: str
    probe_sent_at: Optional[float] = None
    ack_received_at: Optional[float] = None
    timeout_at: Optional[float] = None
    receipt_hash: str = ""
    
    def __post_init__(self):
        if not self.receipt_hash:
            h = hashlib.sha256(
                f"{self.receipt_id}:{self.agent_id}:{self.state.value}:{self.timestamp}:{self.prev_receipt_hash}".encode()
            ).hexdigest()[:16]
            self.receipt_hash = h


@dataclass
class ProbeSession:
    """Tracks probe lifecycle for one agent-counterparty pair."""
    agent_id: str
    counterparty_id: str
    t_probe: float = T_PROBE_DEFAULT_SECONDS
    current_state: ProbeState = ProbeState.SILENT
    receipts: list = field(default_factory=list)
    timeout_history: list = field(default_factory=list)  # timestamps of timeouts
    
    def _last_hash(self) -> str:
        return self.receipts[-1].receipt_hash if self.receipts else "genesis"
    
    def send_probe(self, now: Optional[float] = None) -> ProbeReceipt:
        """Transition: SILENT → PROBE_SENT"""
        now = now or time.time()
        if self.current_state != ProbeState.SILENT:
            raise ValueError(f"Cannot probe from {self.current_state.value}")
        
        receipt = ProbeReceipt(
            receipt_id=f"probe_{len(self.receipts):04d}",
            agent_id=self.agent_id,
            counterparty_id=self.counterparty_id,
            state=ProbeState.PROBE_SENT,
            timestamp=now,
            prev_receipt_hash=self._last_hash(),
            probe_sent_at=now
        )
        self.receipts.append(receipt)
        self.current_state = ProbeState.PROBE_SENT
        return receipt
    
    def receive_ack(self, now: Optional[float] = None) -> ProbeReceipt:
        """Transition: PROBE_SENT → CONFIRMED"""
        now = now or time.time()
        if self.current_state != ProbeState.PROBE_SENT:
            raise ValueError(f"Cannot ACK from {self.current_state.value}")
        
        probe_receipt = self.receipts[-1]
        elapsed = now - probe_receipt.probe_sent_at
        
        if elapsed > self.t_probe:
            raise ValueError(f"ACK after timeout: {elapsed:.0f}s > {self.t_probe:.0f}s window")
        
        receipt = ProbeReceipt(
            receipt_id=f"ack_{len(self.receipts):04d}",
            agent_id=self.agent_id,
            counterparty_id=self.counterparty_id,
            state=ProbeState.CONFIRMED,
            timestamp=now,
            prev_receipt_hash=self._last_hash(),
            probe_sent_at=probe_receipt.probe_sent_at,
            ack_received_at=now
        )
        self.receipts.append(receipt)
        self.current_state = ProbeState.SILENT  # Reset for next cycle
        return receipt
    
    def timeout(self, now: Optional[float] = None) -> ProbeReceipt:
        """Transition: PROBE_SENT → PROBE_TIMEOUT → DISPUTED"""
        now = now or time.time()
        if self.current_state != ProbeState.PROBE_SENT:
            raise ValueError(f"Cannot timeout from {self.current_state.value}")
        
        probe_receipt = self.receipts[-1]
        
        # PROBE_TIMEOUT receipt
        timeout_receipt = ProbeReceipt(
            receipt_id=f"timeout_{len(self.receipts):04d}",
            agent_id=self.agent_id,
            counterparty_id=self.counterparty_id,
            state=ProbeState.PROBE_TIMEOUT,
            timestamp=now,
            prev_receipt_hash=self._last_hash(),
            probe_sent_at=probe_receipt.probe_sent_at,
            timeout_at=now
        )
        self.receipts.append(timeout_receipt)
        self.timeout_history.append(now)
        
        # Auto-escalate to DISPUTED
        disputed_receipt = ProbeReceipt(
            receipt_id=f"disputed_{len(self.receipts):04d}",
            agent_id=self.agent_id,
            counterparty_id=self.counterparty_id,
            state=ProbeState.DISPUTED,
            timestamp=now,
            prev_receipt_hash=self._last_hash()
        )
        self.receipts.append(disputed_receipt)
        self.current_state = ProbeState.SILENT  # Reset
        
        return timeout_receipt
    
    def assess_health(self, now: Optional[float] = None) -> AgentHealth:
        """Check agent health based on timeout history."""
        now = now or time.time()
        window_start = now - (TIMEOUT_WINDOW_DAYS * 86400)
        recent_timeouts = [t for t in self.timeout_history if t >= window_start]
        
        if len(recent_timeouts) >= TIMEOUT_QUARANTINE_THRESHOLD:
            return AgentHealth.QUARANTINED
        elif len(recent_timeouts) >= TIMEOUT_DEGRADED_THRESHOLD:
            return AgentHealth.DEGRADED
        return AgentHealth.HEALTHY
    
    def summary(self, now: Optional[float] = None) -> dict:
        now = now or time.time()
        window_start = now - (TIMEOUT_WINDOW_DAYS * 86400)
        recent_timeouts = len([t for t in self.timeout_history if t >= window_start])
        
        confirmed = sum(1 for r in self.receipts if r.state == ProbeState.CONFIRMED)
        timeouts = sum(1 for r in self.receipts if r.state == ProbeState.PROBE_TIMEOUT)
        
        return {
            "agent": self.agent_id,
            "counterparty": self.counterparty_id,
            "total_probes": confirmed + timeouts,
            "confirmed": confirmed,
            "timeouts": timeouts,
            "recent_timeouts_7d": recent_timeouts,
            "health": self.assess_health(now).value,
            "response_rate": confirmed / (confirmed + timeouts) if (confirmed + timeouts) > 0 else 0,
            "t_probe": self.t_probe
        }


# === Scenarios ===

def scenario_healthy_agent():
    """Agent responds to all probes — HEALTHY."""
    print("=== Scenario: Healthy Agent ===")
    now = time.time()
    session = ProbeSession("kit_fox", "bro_agent")
    
    for i in range(5):
        t = now + i * 7200  # Every 2 hours
        session.send_probe(t)
        session.receive_ack(t + 300)  # ACK in 5 minutes
    
    s = session.summary(now + 36000)
    print(f"  Probes: {s['total_probes']}, Confirmed: {s['confirmed']}, Timeouts: {s['timeouts']}")
    print(f"  Response rate: {s['response_rate']:.0%}")
    print(f"  Health: {s['health']}")
    print()


def scenario_degraded_agent():
    """3 timeouts in 7 days — DEGRADED."""
    print("=== Scenario: Degraded Agent (3 timeouts) ===")
    now = time.time()
    session = ProbeSession("kit_fox", "flaky_agent")
    
    for i in range(7):
        t = now + i * 86400  # Daily probes
        session.send_probe(t)
        if i in (1, 3, 5):  # Timeouts on days 1, 3, 5
            session.timeout(t + session.t_probe + 1)
        else:
            session.receive_ack(t + 600)
    
    s = session.summary(now + 7 * 86400)
    print(f"  Probes: {s['total_probes']}, Confirmed: {s['confirmed']}, Timeouts: {s['timeouts']}")
    print(f"  Recent timeouts (7d): {s['recent_timeouts_7d']}")
    print(f"  Response rate: {s['response_rate']:.0%}")
    print(f"  Health: {s['health']}")
    print()


def scenario_quarantined_agent():
    """5+ timeouts — QUARANTINED."""
    print("=== Scenario: Quarantined Agent (5+ timeouts) ===")
    now = time.time()
    session = ProbeSession("kit_fox", "dead_agent")
    
    for i in range(6):
        t = now + i * 43200  # Every 12 hours
        session.send_probe(t)
        session.timeout(t + session.t_probe + 1)
    
    s = session.summary(now + 4 * 86400)
    print(f"  Probes: {s['total_probes']}, Confirmed: {s['confirmed']}, Timeouts: {s['timeouts']}")
    print(f"  Recent timeouts (7d): {s['recent_timeouts_7d']}")
    print(f"  Health: {s['health']}")
    print()


def scenario_late_ack_rejected():
    """ACK after timeout window — rejected."""
    print("=== Scenario: Late ACK (rejected) ===")
    now = time.time()
    session = ProbeSession("kit_fox", "slow_agent", t_probe=1800)  # 30 min window
    
    session.send_probe(now)
    try:
        session.receive_ack(now + 3600)  # 1 hour later = past window
        print("  ERROR: Should have been rejected!")
    except ValueError as e:
        print(f"  Correctly rejected: {e}")
        session.timeout(now + 1801)
    
    s = session.summary(now + 7200)
    print(f"  Health: {s['health']}")
    print()


def scenario_receipt_chain():
    """Verify hash chain integrity across probes."""
    print("=== Scenario: Receipt Hash Chain ===")
    now = time.time()
    session = ProbeSession("kit_fox", "chain_agent")
    
    session.send_probe(now)
    session.receive_ack(now + 120)
    session.send_probe(now + 3600)
    session.timeout(now + 3600 + 3601)
    session.send_probe(now + 7200)
    session.receive_ack(now + 7200 + 60)
    
    print("  Receipt chain:")
    for r in session.receipts:
        print(f"    {r.receipt_id}: {r.state.value} hash={r.receipt_hash} prev={r.prev_receipt_hash}")
    
    # Verify chain
    for i in range(1, len(session.receipts)):
        assert session.receipts[i].prev_receipt_hash == session.receipts[i-1].receipt_hash
    print("  Chain integrity: VERIFIED ✓")
    print()


if __name__ == "__main__":
    print("Probe State Machine — ATF Receipt Active Verification")
    print("Per santaclawd + Chandra & Toueg (1996) ◇S failure detector")
    print("=" * 65)
    print()
    print("Key invariant: silence NEVER produces a receipt.")
    print(f"T_probe: {T_PROBE_DEFAULT_SECONDS}s default, [{T_PROBE_FLOOR_SECONDS}s, {T_PROBE_CEILING_SECONDS}s]")
    print(f"DEGRADED: {TIMEOUT_DEGRADED_THRESHOLD}+ timeouts in {TIMEOUT_WINDOW_DAYS}d")
    print(f"QUARANTINED: {TIMEOUT_QUARANTINE_THRESHOLD}+ timeouts in {TIMEOUT_WINDOW_DAYS}d")
    print()
    
    scenario_healthy_agent()
    scenario_degraded_agent()
    scenario_quarantined_agent()
    scenario_late_ack_rejected()
    scenario_receipt_chain()
    
    print("=" * 65)
    print("KEY: PROBE terminates silence ambiguity. FLP says crash ≠ slow,")
    print("but ◇S says eventually you CAN distinguish. PROBE_TIMEOUT is the")
    print("receipt that breaks the recursion. No human in the loop needed.")
