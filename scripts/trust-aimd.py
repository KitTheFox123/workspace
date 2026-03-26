#!/usr/bin/env python3
"""
trust-aimd.py — AIMD (Additive Increase Multiplicative Decrease) trust recovery.

Maps TCP congestion control (RFC 5681) to ATF trust lifecycle.

TCP parallel:
- Congestion window (cwnd) = trust level (0.0 to 1.0)
- Slow start = new agent building trust (exponential growth to threshold)
- Congestion avoidance = steady-state trust (additive increase per successful attestation)
- Packet loss = trust breach (multiplicative decrease: window halved, not zeroed)
- Timeout = severe breach (reset to slow start)
- Fast recovery (RFC 5681 §3.2) = soft cascade recovery with rate limiting

Key design decisions:
1. Recovery is SLOW (additive). Punishment is FAST (multiplicative).
2. Breach does NOT zero trust — halves it. Past history has value.
3. Severe breach (fraud, not just degradation) = timeout, back to slow start.
4. Recovery requires ACTIVE re-attestation, not passive time-heal.
5. Short trust TTL (from trust-lifecycle-acme.py) means non-renewal = natural decay.

Sources:
- RFC 5681: TCP Congestion Control
- TCP Reno: AIMD as foundational fairness mechanism
- santaclawd: "SOFT_CASCADE recovery — passive auto-clear vs active re-attestation"
- Kit: "TCP solved this. AIMD. Additive increase, multiplicative decrease."
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Optional


class TrustPhase(Enum):
    """Trust lifecycle phases mapped to TCP states."""
    SLOW_START = "slow_start"           # New agent, exponential growth
    CONGESTION_AVOIDANCE = "avoidance"  # Steady state, linear growth
    FAST_RECOVERY = "fast_recovery"     # After breach, limited recovery
    TIMEOUT = "timeout"                 # Severe breach, back to start


class EventType(Enum):
    """Trust events mapped to TCP events."""
    SUCCESS = "success"           # Successful attestation (ACK)
    DEGRADATION = "degradation"   # Partial trust loss (duplicate ACK / packet loss)
    BREACH = "breach"             # Serious trust violation (triple dup ACK → fast retransmit)
    FRAUD = "fraud"               # Severe trust violation (timeout)
    RENEWAL = "renewal"           # Active re-attestation (keepalive)
    EXPIRY = "expiry"             # TTL expired without renewal


@dataclass
class TrustState:
    """Current trust state for an agent (analogous to TCP connection state)."""
    agent_id: str
    trust_level: float = 0.1          # Current trust (cwnd equivalent), starts low
    phase: TrustPhase = TrustPhase.SLOW_START
    ssthresh: float = 0.5             # Slow start threshold
    history: list[dict] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_event: Optional[str] = None
    consecutive_successes: int = 0
    breach_count: int = 0
    
    # AIMD parameters
    ADDITIVE_INCREASE: float = 0.05   # Trust gain per success in avoidance
    MULTIPLICATIVE_DECREASE: float = 0.5  # Trust multiplier on breach (halve)
    SLOW_START_GROWTH: float = 2.0    # Exponential growth factor in slow start
    MIN_TRUST: float = 0.01           # Never truly zero
    MAX_TRUST: float = 1.0
    FRAUD_RESET: float = 0.05         # Reset level after fraud (timeout)
    
    def _clamp(self, value: float) -> float:
        return max(self.MIN_TRUST, min(self.MAX_TRUST, value))
    
    def _log(self, event: EventType, old_level: float, detail: str = ""):
        self.history.append({
            "event": event.value,
            "old_trust": round(old_level, 4),
            "new_trust": round(self.trust_level, 4),
            "phase": self.phase.value,
            "ssthresh": round(self.ssthresh, 4),
            "detail": detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    
    def process_event(self, event: EventType) -> dict:
        """Process a trust event using AIMD rules."""
        old_level = self.trust_level
        old_phase = self.phase
        
        if event == EventType.SUCCESS:
            self._handle_success()
        elif event == EventType.DEGRADATION:
            self._handle_degradation()
        elif event == EventType.BREACH:
            self._handle_breach()
        elif event == EventType.FRAUD:
            self._handle_fraud()
        elif event == EventType.RENEWAL:
            self._handle_renewal()
        elif event == EventType.EXPIRY:
            self._handle_expiry()
        
        self.last_event = event.value
        
        return {
            "event": event.value,
            "old_trust": round(old_level, 4),
            "new_trust": round(self.trust_level, 4),
            "delta": round(self.trust_level - old_level, 4),
            "phase": self.phase.value,
            "phase_changed": self.phase != old_phase,
        }
    
    def _handle_success(self):
        """ACK received — increase trust."""
        old = self.trust_level
        self.consecutive_successes += 1
        
        if self.phase == TrustPhase.SLOW_START:
            # Exponential growth: double per success (like TCP slow start)
            self.trust_level = self._clamp(self.trust_level * self.SLOW_START_GROWTH)
            if self.trust_level >= self.ssthresh:
                self.phase = TrustPhase.CONGESTION_AVOIDANCE
                self._log(EventType.SUCCESS, old, "slow_start → avoidance (hit ssthresh)")
                return
        
        elif self.phase == TrustPhase.CONGESTION_AVOIDANCE:
            # Linear growth: additive increase per success
            self.trust_level = self._clamp(self.trust_level + self.ADDITIVE_INCREASE)
        
        elif self.phase == TrustPhase.FAST_RECOVERY:
            # In recovery: slower linear growth (half the normal rate)
            self.trust_level = self._clamp(self.trust_level + self.ADDITIVE_INCREASE * 0.5)
            if self.trust_level >= self.ssthresh:
                self.phase = TrustPhase.CONGESTION_AVOIDANCE
                self._log(EventType.SUCCESS, old, "fast_recovery → avoidance")
                return
        
        elif self.phase == TrustPhase.TIMEOUT:
            # After fraud: back to slow start rules
            self.trust_level = self._clamp(self.trust_level * self.SLOW_START_GROWTH)
            self.phase = TrustPhase.SLOW_START
        
        self._log(EventType.SUCCESS, old)
    
    def _handle_degradation(self):
        """Minor trust loss — like duplicate ACKs."""
        old = self.trust_level
        # Small linear decrease
        self.trust_level = self._clamp(self.trust_level - self.ADDITIVE_INCREASE * 0.5)
        self.consecutive_successes = max(0, self.consecutive_successes - 1)
        self._log(EventType.DEGRADATION, old, "minor degradation")
    
    def _handle_breach(self):
        """Serious breach — multiplicative decrease (TCP fast retransmit)."""
        old = self.trust_level
        self.breach_count += 1
        self.consecutive_successes = 0
        
        # Set new ssthresh to half of current trust
        self.ssthresh = max(self.MIN_TRUST * 2, self.trust_level * self.MULTIPLICATIVE_DECREASE)
        # Halve trust level
        self.trust_level = self._clamp(self.trust_level * self.MULTIPLICATIVE_DECREASE)
        # Enter fast recovery
        self.phase = TrustPhase.FAST_RECOVERY
        
        self._log(EventType.BREACH, old, 
                  f"AIMD: trust halved. ssthresh={self.ssthresh:.4f}. breach #{self.breach_count}")
    
    def _handle_fraud(self):
        """Severe violation — timeout, reset to near-zero."""
        old = self.trust_level
        self.breach_count += 1
        self.consecutive_successes = 0
        
        # TCP timeout: ssthresh = cwnd/2, cwnd = 1 MSS
        self.ssthresh = max(self.MIN_TRUST * 2, self.trust_level * self.MULTIPLICATIVE_DECREASE)
        self.trust_level = self.FRAUD_RESET
        self.phase = TrustPhase.TIMEOUT
        
        self._log(EventType.FRAUD, old,
                  f"TIMEOUT: trust reset to {self.FRAUD_RESET}. requires active re-attestation")
    
    def _handle_renewal(self):
        """Active re-attestation — maintains current level, resets decay timer."""
        old = self.trust_level
        # Renewal doesn't increase trust, just prevents decay
        self._log(EventType.RENEWAL, old, "TTL renewed, decay timer reset")
    
    def _handle_expiry(self):
        """TTL expired — natural decay (non-renewal = soft revocation)."""
        old = self.trust_level
        # Decay by 30% per missed renewal (like not refreshing a cert)
        self.trust_level = self._clamp(self.trust_level * 0.7)
        if self.trust_level < self.ssthresh:
            self.phase = TrustPhase.FAST_RECOVERY
        self._log(EventType.EXPIRY, old, "TTL expired, trust decayed 30%")


def run_scenarios():
    """Demonstrate AIMD trust recovery across lifecycle scenarios."""
    
    print("=" * 70)
    print("TRUST-AIMD: TCP Congestion Control for Agent Trust")
    print("RFC 5681 mapped to ATF trust lifecycle")
    print("=" * 70)
    
    # Scenario 1: Normal lifecycle — slow start → steady state → breach → recovery
    print("\n--- Scenario 1: Full lifecycle (new agent → breach → recovery) ---")
    agent = TrustState(agent_id="agent_alpha")
    
    events = [
        (EventType.SUCCESS, "first attestation"),
        (EventType.SUCCESS, "second attestation"),
        (EventType.SUCCESS, "third attestation (hits ssthresh)"),
        (EventType.SUCCESS, "steady state growth"),
        (EventType.SUCCESS, "steady state growth"),
        (EventType.SUCCESS, "steady state growth"),
        (EventType.BREACH, "⚠️ trust violation detected"),
        (EventType.SUCCESS, "recovery attempt 1"),
        (EventType.SUCCESS, "recovery attempt 2"),
        (EventType.SUCCESS, "recovery attempt 3"),
        (EventType.SUCCESS, "recovery attempt 4"),
        (EventType.SUCCESS, "recovery → avoidance"),
    ]
    
    for event, desc in events:
        result = agent.process_event(event)
        phase_marker = " ←" if result["phase_changed"] else ""
        print(f"  {desc}: {result['old_trust']:.3f} → {result['new_trust']:.3f} "
              f"({result['delta']:+.3f}) [{result['phase']}]{phase_marker}")
    
    # Scenario 2: Fraud — severe reset
    print("\n--- Scenario 2: Fraud detection (timeout → slow start) ---")
    agent2 = TrustState(agent_id="agent_beta", trust_level=0.8, 
                        phase=TrustPhase.CONGESTION_AVOIDANCE)
    
    events2 = [
        (EventType.FRAUD, "🚨 FRAUD detected"),
        (EventType.SUCCESS, "re-attestation 1"),
        (EventType.SUCCESS, "re-attestation 2"),
        (EventType.SUCCESS, "re-attestation 3"),
        (EventType.SUCCESS, "re-attestation 4"),
    ]
    
    for event, desc in events2:
        result = agent2.process_event(event)
        print(f"  {desc}: {result['old_trust']:.3f} → {result['new_trust']:.3f} "
              f"({result['delta']:+.3f}) [{result['phase']}]")
    
    # Scenario 3: TTL expiry — natural decay
    print("\n--- Scenario 3: TTL expiry (non-renewal = soft revocation) ---")
    agent3 = TrustState(agent_id="agent_gamma", trust_level=0.9,
                        phase=TrustPhase.CONGESTION_AVOIDANCE, ssthresh=0.5)
    
    events3 = [
        (EventType.EXPIRY, "missed renewal 1"),
        (EventType.EXPIRY, "missed renewal 2"),
        (EventType.EXPIRY, "missed renewal 3"),
        (EventType.SUCCESS, "finally re-attests"),
        (EventType.SUCCESS, "recovery continues"),
    ]
    
    for event, desc in events3:
        result = agent3.process_event(event)
        print(f"  {desc}: {result['old_trust']:.3f} → {result['new_trust']:.3f} "
              f"({result['delta']:+.3f}) [{result['phase']}]")
    
    # Summary
    print(f"\n{'=' * 70}")
    print("AIMD trust recovery principles:")
    print("  1. Recovery is SLOW (additive). Punishment is FAST (multiplicative).")
    print("  2. Breach halves trust, doesn't zero it. History has value.")
    print("  3. Fraud = timeout, near-zero reset. Active re-attestation required.")
    print("  4. Non-renewal = natural 30% decay per missed TTL. Soft revocation.")
    print("  5. Fast recovery = rate-limited re-earn (half normal growth rate).")
    print(f"\nTCP parallel: slow_start → congestion_avoidance → fast_recovery → timeout")
    print(f"ATF parallel: new_agent → steady_trust → breach_recovery → fraud_reset")


if __name__ == "__main__":
    run_scenarios()
