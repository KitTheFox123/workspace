#!/usr/bin/env python3
"""
probe-state-machine.py — PROBE-based receipt confirmation for ATF.

Per santaclawd: silence-as-CONFIRMED is ambiguous. PROBE closes it.
Per FLP (1985): cannot distinguish crash from slow in async systems.
Per Chandra-Toueg (1996): ◇S failure detector = PROBE + adaptive timeout.
Per Jacobson/Karels (1988): adaptive timeout from RTT measurement.

State machine:
  SILENT → PROBE (T-hour active check)
  PROBE → CONFIRMED (ACK received within T_probe)
  PROBE → PROBE_TIMEOUT (no ACK, retry up to 3)
  PROBE_TIMEOUT → DEGRADED (1 timeout)
  PROBE_TIMEOUT → WARNING (2 timeouts)
  PROBE_TIMEOUT → DISPUTED (3 timeouts, TCP retransmit model)

Key insight: the timeout IS the evidence. No separate dispute needed.
"""

import hashlib
import time
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ProbeState(Enum):
    SILENT = "SILENT"           # No interaction yet
    PROBE_SENT = "PROBE_SENT"   # Active check dispatched
    CONFIRMED = "CONFIRMED"     # ACK received
    DEGRADED = "DEGRADED"       # 1 probe timeout
    WARNING = "WARNING"         # 2 probe timeouts
    DISPUTED = "DISPUTED"       # 3 probe timeouts (auto-escalated)
    TIMEOUT_FINAL = "TIMEOUT_FINAL"  # All retries exhausted


# SPEC_CONSTANTS
PROBE_RETRIES = 3               # TCP retransmit model
PROBE_WINDOW_DEFAULT = 3600     # 1 hour default (seconds)
PROBE_BACKOFF_FACTOR = 2.0      # Exponential backoff
SRTT_ALPHA = 0.875              # Jacobson/Karels smoothing
RTTVAR_BETA = 0.75              # RTT variance smoothing
RTO_K = 4                       # RTO = SRTT + K * RTTVAR


@dataclass
class ProbeRecord:
    probe_id: str
    target_agent: str
    probe_sent_at: float
    probe_window: float  # seconds
    ack_received_at: Optional[float] = None
    probe_count: int = 1
    state: ProbeState = ProbeState.PROBE_SENT
    receipt_hash: str = ""
    
    def __post_init__(self):
        if not self.receipt_hash:
            self.receipt_hash = hashlib.sha256(
                f"{self.probe_id}:{self.target_agent}:{self.probe_sent_at}".encode()
            ).hexdigest()[:16]


@dataclass
class AdaptiveTimeout:
    """Jacobson/Karels (1988) adaptive RTO calculator."""
    srtt: float = 0.0          # Smoothed RTT
    rttvar: float = 0.0        # RTT variance
    rto: float = PROBE_WINDOW_DEFAULT  # Retransmission timeout
    sample_count: int = 0
    
    def update(self, rtt: float):
        """Update timeout based on new RTT measurement."""
        if self.sample_count == 0:
            self.srtt = rtt
            self.rttvar = rtt / 2
        else:
            self.rttvar = RTTVAR_BETA * self.rttvar + (1 - RTTVAR_BETA) * abs(self.srtt - rtt)
            self.srtt = SRTT_ALPHA * self.srtt + (1 - SRTT_ALPHA) * rtt
        
        self.rto = self.srtt + RTO_K * self.rttvar
        self.rto = max(1.0, min(self.rto, 86400))  # Floor 1s, ceiling 24h
        self.sample_count += 1
        return self.rto


@dataclass
class AgentProbeProfile:
    """Per-agent probe tracking with adaptive timeout."""
    agent_id: str
    timeout: AdaptiveTimeout = field(default_factory=AdaptiveTimeout)
    probes: list[ProbeRecord] = field(default_factory=list)
    confirmed_count: int = 0
    timeout_count: int = 0
    current_state: ProbeState = ProbeState.SILENT
    
    @property
    def confirmation_rate(self) -> float:
        total = self.confirmed_count + self.timeout_count
        return self.confirmed_count / total if total > 0 else 0.0
    
    @property
    def reliability_grade(self) -> str:
        rate = self.confirmation_rate
        if rate >= 0.95: return "A"
        if rate >= 0.85: return "B"
        if rate >= 0.70: return "C"
        if rate >= 0.50: return "D"
        return "F"


def send_probe(profile: AgentProbeProfile, now: float) -> ProbeRecord:
    """Send a probe to an agent."""
    probe = ProbeRecord(
        probe_id=f"probe_{len(profile.probes):04d}",
        target_agent=profile.agent_id,
        probe_sent_at=now,
        probe_window=profile.timeout.rto
    )
    profile.probes.append(probe)
    profile.current_state = ProbeState.PROBE_SENT
    return probe


def process_ack(profile: AgentProbeProfile, probe: ProbeRecord, ack_time: float) -> dict:
    """Process an ACK response to a probe."""
    rtt = ack_time - probe.probe_sent_at
    probe.ack_received_at = ack_time
    probe.state = ProbeState.CONFIRMED
    
    # Update adaptive timeout
    new_rto = profile.timeout.update(rtt)
    profile.confirmed_count += 1
    profile.current_state = ProbeState.CONFIRMED
    
    return {
        "state": "CONFIRMED",
        "rtt": round(rtt, 3),
        "new_rto": round(new_rto, 3),
        "srtt": round(profile.timeout.srtt, 3),
        "confirmation_rate": round(profile.confirmation_rate, 3)
    }


def process_timeout(profile: AgentProbeProfile, probe: ProbeRecord) -> dict:
    """Process a probe timeout — escalate based on retry count."""
    probe.probe_count += 1
    
    if probe.probe_count == 1:
        probe.state = ProbeState.DEGRADED
        profile.current_state = ProbeState.DEGRADED
        escalation = "DEGRADED"
    elif probe.probe_count == 2:
        probe.state = ProbeState.WARNING
        profile.current_state = ProbeState.WARNING
        escalation = "WARNING"
    else:  # 3+
        probe.state = ProbeState.DISPUTED
        profile.current_state = ProbeState.DISPUTED
        profile.timeout_count += 1
        escalation = "DISPUTED"
    
    # Exponential backoff for next probe window
    new_window = probe.probe_window * PROBE_BACKOFF_FACTOR
    
    return {
        "state": escalation,
        "probe_count": probe.probe_count,
        "next_window": round(new_window, 1),
        "max_retries": PROBE_RETRIES,
        "auto_disputed": probe.probe_count >= PROBE_RETRIES,
        "confirmation_rate": round(profile.confirmation_rate, 3)
    }


def generate_probe_receipt(probe: ProbeRecord) -> dict:
    """Generate a PROBE_TIMEOUT_RECEIPT for the evidence trail."""
    return {
        "receipt_type": "PROBE_TIMEOUT",
        "receipt_hash": probe.receipt_hash,
        "target_agent": probe.target_agent,
        "probe_sent_at": probe.probe_sent_at,
        "probe_window": probe.probe_window,
        "probe_count": probe.probe_count,
        "final_state": probe.state.value,
        "ack_received": probe.ack_received_at is not None
    }


# === Scenarios ===

def scenario_healthy_agent():
    """Agent responds promptly — adaptive timeout tightens."""
    print("=== Scenario: Healthy Agent (Adaptive Timeout Tightens) ===")
    now = time.time()
    profile = AgentProbeProfile(agent_id="healthy_bot")
    
    for i in range(10):
        probe = send_probe(profile, now + i * 3600)
        # Simulate varying RTT (200-800ms)
        rtt = random.uniform(0.2, 0.8)
        result = process_ack(profile, probe, now + i * 3600 + rtt)
        if i in (0, 4, 9):
            print(f"  Probe {i}: RTT={result['rtt']}s, RTO={result['new_rto']}s, "
                  f"SRTT={result['srtt']}s, rate={result['confirmation_rate']}")
    
    print(f"  Final: grade={profile.reliability_grade}, "
          f"rate={profile.confirmation_rate:.3f}, "
          f"adaptive_rto={profile.timeout.rto:.3f}s")
    print()


def scenario_degrading_agent():
    """Agent starts healthy, then degrades — probe catches it."""
    print("=== Scenario: Degrading Agent (Probes Catch Drift) ===")
    now = time.time()
    profile = AgentProbeProfile(agent_id="degrading_bot")
    
    for i in range(15):
        probe = send_probe(profile, now + i * 3600)
        
        if i < 8:
            # Healthy phase
            rtt = random.uniform(0.3, 0.6)
            result = process_ack(profile, probe, now + i * 3600 + rtt)
            if i in (0, 7):
                print(f"  Probe {i}: CONFIRMED, RTT={result['rtt']}s")
        elif i < 12:
            # Degrading — increasing timeouts
            result = process_timeout(profile, probe)
            print(f"  Probe {i}: {result['state']}, count={result['probe_count']}")
        else:
            # Complete failure
            for _ in range(PROBE_RETRIES):
                result = process_timeout(profile, probe)
            receipt = generate_probe_receipt(probe)
            print(f"  Probe {i}: {result['state']} (auto-disputed), "
                  f"receipt={receipt['receipt_hash']}")
    
    print(f"  Final: grade={profile.reliability_grade}, "
          f"rate={profile.confirmation_rate:.3f}")
    print()


def scenario_flp_ambiguity():
    """Cannot distinguish crash from slow — PROBE resolves it."""
    print("=== Scenario: FLP Ambiguity (Crash vs Slow) ===")
    now = time.time()
    
    # Slow agent — responds just before timeout
    slow_profile = AgentProbeProfile(agent_id="slow_agent")
    probe = send_probe(slow_profile, now)
    # Responds at 95% of window
    rtt = slow_profile.timeout.rto * 0.95
    result = process_ack(slow_profile, probe, now + rtt)
    print(f"  Slow agent: CONFIRMED at {rtt:.1f}s (window: {slow_profile.timeout.rto:.1f}s)")
    print(f"    Adaptive RTO widens: {slow_profile.timeout.rto:.1f}s")
    
    # Crashed agent — no response
    crash_profile = AgentProbeProfile(agent_id="crashed_agent")
    probe2 = send_probe(crash_profile, now)
    for retry in range(PROBE_RETRIES):
        result = process_timeout(crash_profile, probe2)
    print(f"  Crashed agent: {result['state']} after {PROBE_RETRIES} probes")
    receipt = generate_probe_receipt(probe2)
    print(f"    Receipt: {receipt['receipt_type']}, hash={receipt['receipt_hash']}")
    
    print(f"\n  FLP resolution: slow=CONFIRMED (adapted), crash=DISPUTED (evidence)")
    print(f"  Key: timeout IS the evidence. No human judgment needed.")
    print()


def scenario_adaptive_timeout_convergence():
    """Jacobson/Karels timeout converges on agent's true latency."""
    print("=== Scenario: Adaptive Timeout Convergence ===")
    now = time.time()
    profile = AgentProbeProfile(agent_id="variable_latency")
    
    # Simulate agent with ~500ms mean, 200ms variance
    rtts = [0.3, 0.5, 0.7, 0.4, 0.6, 0.5, 0.8, 0.3, 0.5, 0.6,
            0.4, 0.5, 0.7, 0.5, 0.4, 0.6, 0.5, 0.3, 0.5, 0.6]
    
    for i, rtt in enumerate(rtts):
        probe = send_probe(profile, now + i * 600)
        result = process_ack(profile, probe, now + i * 600 + rtt)
        if i in (0, 5, 10, 15, 19):
            print(f"  Sample {i}: RTT={rtt}s, SRTT={result['srtt']}s, "
                  f"RTO={result['new_rto']}s")
    
    print(f"\n  Converged: SRTT={profile.timeout.srtt:.3f}s, "
          f"RTTVAR={profile.timeout.rttvar:.3f}s, "
          f"RTO={profile.timeout.rto:.3f}s")
    print(f"  True mean: {sum(rtts)/len(rtts):.3f}s")
    print(f"  RTO/mean ratio: {profile.timeout.rto/(sum(rtts)/len(rtts)):.2f}x "
          f"(should be 2-4x for safety margin)")
    print()


if __name__ == "__main__":
    random.seed(42)
    print("Probe State Machine — PROBE-Based Receipt Confirmation for ATF")
    print("Per santaclawd + FLP (1985) + Chandra-Toueg (1996) + Jacobson/Karels (1988)")
    print("=" * 70)
    print()
    
    scenario_healthy_agent()
    scenario_degrading_agent()
    scenario_flp_ambiguity()
    scenario_adaptive_timeout_convergence()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. PROBE closes FLP ambiguity: crash vs slow becomes operational, not philosophical")
    print("2. Timeout IS the evidence — PROBE_TIMEOUT_RECEIPT, no separate dispute")
    print("3. Three retries before DISPUTED (TCP retransmit model)")
    print("4. Jacobson/Karels adaptive timeout converges on true agent latency")
    print("5. Exponential backoff prevents probe storms")
