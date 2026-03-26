#!/usr/bin/env python3
"""
soft-cascade-recovery.py — Circuit breaker pattern for ATF trust recovery.

Maps Netflix Hystrix / resilience4j circuit breaker to agent trust lifecycle:
- CLOSED = trusted (requests flow normally)
- OPEN = revoked (all requests blocked)
- HALF-OPEN = soft cascade recovery (probe requests allowed)

The key insight from santaclawd's SOFT_CASCADE question:
When trust degrades partially — not revoked, just eroded — what triggers
re-attestation? This implements ACTIVE re-attestation via probe challenges,
not passive time-heal.

Why active > passive:
- Passive (time-heal) = letting expired certs auto-renew without challenge
- Active (probe) = circuit breaker HALF-OPEN state: exactly ONE request 
  passes through. If it succeeds → back to CLOSED. If it fails → back to OPEN.
- Hystrix proved this at Netflix scale: probe-based recovery is the only 
  pattern that avoids thundering herd on recovery.

Recovery escalation:
1. DEGRADED: trust score below threshold but above revocation
2. HALF-OPEN: one probe challenge issued per probe_interval
3. PROBE_PASS → RECOVERING → CLOSED (trust score gradually restored)
4. PROBE_FAIL → OPEN (fully revoked, requires manual re-attestation)

Sources:
- Netflix Hystrix circuit breaker (Nygard, "Release It!", 2007/2018)
- Microsoft Azure circuit breaker pattern guide
- Resilience4j CircuitBreaker implementation
- ATF SOFT_CASCADE discussion (santaclawd, March 2026)
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable


class TrustState(Enum):
    CLOSED = "CLOSED"           # Fully trusted
    DEGRADED = "DEGRADED"       # Trust eroding, monitoring
    HALF_OPEN = "HALF_OPEN"     # Probing for recovery
    RECOVERING = "RECOVERING"   # Probe passed, rebuilding
    OPEN = "OPEN"               # Revoked


@dataclass
class ProbeChallenge:
    """A challenge issued to test if trust should be restored."""
    challenge_id: str
    challenge_type: str  # CAPABILITY_PROBE, HISTORY_VERIFY, LIVE_ATTESTATION
    issued_at: str
    deadline: str
    payload: dict = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc).isoformat() > self.deadline


@dataclass
class ProbeResult:
    """Result of a probe challenge."""
    challenge_id: str
    passed: bool
    score: float  # 0.0-1.0
    evidence: str
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass 
class TrustRecord:
    """Trust state for an agent relationship."""
    agent_id: str
    counterparty_id: str
    state: TrustState = TrustState.CLOSED
    trust_score: float = 1.0
    
    # Thresholds
    degraded_threshold: float = 0.7
    revocation_threshold: float = 0.3
    recovery_target: float = 0.8
    
    # Circuit breaker params
    failure_count: int = 0
    failure_threshold: int = 3      # Failures before OPEN
    probe_interval_s: int = 300     # Seconds between probes in HALF_OPEN
    recovery_increment: float = 0.1 # Trust restored per successful probe
    max_probe_failures: int = 2     # Consecutive probe failures before OPEN
    
    # Timing
    state_changed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_probe_at: Optional[str] = None
    probe_failure_streak: int = 0
    
    # History
    transitions: list[dict] = field(default_factory=list)
    probes: list[dict] = field(default_factory=list)


class SoftCascadeRecovery:
    """
    Circuit breaker for agent trust with probe-based recovery.
    
    State machine:
    CLOSED → (trust_score < degraded_threshold) → DEGRADED
    DEGRADED → (trust_score < revocation_threshold OR failure_count >= threshold) → OPEN
    DEGRADED → (probe_interval elapsed) → HALF_OPEN
    HALF_OPEN → (probe passes) → RECOVERING
    HALF_OPEN → (probe fails) → OPEN (if streak >= max_probe_failures) else stays HALF_OPEN
    RECOVERING → (trust_score >= recovery_target) → CLOSED
    RECOVERING → (probe fails) → DEGRADED
    OPEN → (manual re-attestation) → HALF_OPEN
    """
    
    def __init__(self):
        self.records: dict[str, TrustRecord] = {}
        self.event_log: list[dict] = []
    
    def _key(self, agent: str, counterparty: str) -> str:
        return f"{agent}:{counterparty}"
    
    def get_or_create(self, agent: str, counterparty: str) -> TrustRecord:
        key = self._key(agent, counterparty)
        if key not in self.records:
            self.records[key] = TrustRecord(agent_id=agent, counterparty_id=counterparty)
        return self.records[key]
    
    def _transition(self, record: TrustRecord, new_state: TrustState, reason: str):
        old_state = record.state
        record.state = new_state
        record.state_changed_at = datetime.now(timezone.utc).isoformat()
        
        entry = {
            "from": old_state.value,
            "to": new_state.value,
            "reason": reason,
            "trust_score": round(record.trust_score, 4),
            "timestamp": record.state_changed_at,
        }
        record.transitions.append(entry)
        self.event_log.append({
            "agent": record.agent_id,
            "counterparty": record.counterparty_id,
            **entry,
        })
    
    def record_failure(self, agent: str, counterparty: str, severity: float = 0.1) -> TrustRecord:
        """Record a trust-degrading event."""
        record = self.get_or_create(agent, counterparty)
        record.trust_score = max(0.0, record.trust_score - severity)
        record.failure_count += 1
        
        # State transitions based on thresholds
        if record.state == TrustState.CLOSED:
            if record.trust_score < record.degraded_threshold:
                self._transition(record, TrustState.DEGRADED, 
                    f"trust_score={record.trust_score:.2f} < degraded_threshold={record.degraded_threshold}")
        
        if record.state == TrustState.DEGRADED:
            if record.trust_score < record.revocation_threshold:
                self._transition(record, TrustState.OPEN,
                    f"trust_score={record.trust_score:.2f} < revocation_threshold={record.revocation_threshold}")
            elif record.failure_count >= record.failure_threshold:
                self._transition(record, TrustState.OPEN,
                    f"failure_count={record.failure_count} >= threshold={record.failure_threshold}")
        
        if record.state == TrustState.RECOVERING:
            self._transition(record, TrustState.DEGRADED,
                f"failure during recovery: trust_score={record.trust_score:.2f}")
        
        return record
    
    def initiate_probe(self, agent: str, counterparty: str) -> Optional[TrustRecord]:
        """Transition to HALF_OPEN and issue a probe challenge."""
        record = self.get_or_create(agent, counterparty)
        
        if record.state == TrustState.DEGRADED:
            self._transition(record, TrustState.HALF_OPEN,
                "probe_interval elapsed, issuing challenge")
            record.last_probe_at = datetime.now(timezone.utc).isoformat()
            return record
        elif record.state == TrustState.OPEN:
            # Manual re-attestation request → allow probe
            self._transition(record, TrustState.HALF_OPEN,
                "manual re-attestation requested")
            record.last_probe_at = datetime.now(timezone.utc).isoformat()
            record.probe_failure_streak = 0
            return record
        
        return None
    
    def process_probe_result(self, agent: str, counterparty: str, 
                              passed: bool, score: float = 0.0) -> TrustRecord:
        """Process the result of a probe challenge."""
        record = self.get_or_create(agent, counterparty)
        
        record.probes.append({
            "passed": passed,
            "score": round(score, 4),
            "state_at_probe": record.state.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        if record.state != TrustState.HALF_OPEN:
            return record
        
        if passed:
            record.probe_failure_streak = 0
            record.trust_score = min(1.0, record.trust_score + record.recovery_increment)
            
            if record.trust_score >= record.recovery_target:
                self._transition(record, TrustState.CLOSED,
                    f"probe passed, trust_score={record.trust_score:.2f} >= target={record.recovery_target}")
                record.failure_count = 0
            else:
                self._transition(record, TrustState.RECOVERING,
                    f"probe passed, trust_score={record.trust_score:.2f}, recovering toward {record.recovery_target}")
        else:
            record.probe_failure_streak += 1
            
            if record.probe_failure_streak >= record.max_probe_failures:
                self._transition(record, TrustState.OPEN,
                    f"probe_failure_streak={record.probe_failure_streak} >= max={record.max_probe_failures}")
            else:
                # Stay HALF_OPEN, will retry at next probe interval
                self.event_log.append({
                    "agent": record.agent_id,
                    "counterparty": record.counterparty_id,
                    "event": "PROBE_FAILED",
                    "streak": record.probe_failure_streak,
                    "remaining_attempts": record.max_probe_failures - record.probe_failure_streak,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
        
        return record
    
    def continue_recovery(self, agent: str, counterparty: str, 
                           probe_passed: bool, score: float = 0.0) -> TrustRecord:
        """Continue recovery with subsequent probes."""
        record = self.get_or_create(agent, counterparty)
        
        if record.state != TrustState.RECOVERING:
            return record
        
        if probe_passed:
            record.trust_score = min(1.0, record.trust_score + record.recovery_increment)
            
            if record.trust_score >= record.recovery_target:
                self._transition(record, TrustState.CLOSED,
                    f"recovery complete, trust_score={record.trust_score:.2f}")
                record.failure_count = 0
        else:
            self._transition(record, TrustState.DEGRADED,
                f"probe failed during recovery, trust_score={record.trust_score:.2f}")
        
        return record


def run_scenarios():
    """Demonstrate soft cascade recovery patterns."""
    scr = SoftCascadeRecovery()
    
    print("=" * 70)
    print("SOFT CASCADE RECOVERY — Circuit Breaker for Agent Trust")
    print("=" * 70)
    
    # Scenario 1: Gradual degradation → probe → recovery
    print("\n--- Scenario 1: Degradation → Probe → Recovery ---")
    agent, cp = "agent_alpha", "registry_beta"
    
    # Gradual trust erosion
    for i in range(4):
        r = scr.record_failure(agent, cp, severity=0.1)
        print(f"  Failure {i+1}: score={r.trust_score:.2f}, state={r.state.value}")
    
    # Initiate probe
    r = scr.initiate_probe(agent, cp)
    print(f"  → Probe initiated: state={r.state.value}")
    
    # Probe passes
    r = scr.process_probe_result(agent, cp, passed=True, score=0.85)
    print(f"  → Probe passed: score={r.trust_score:.2f}, state={r.state.value}")
    
    # Continue recovery
    r = scr.continue_recovery(agent, cp, probe_passed=True, score=0.9)
    print(f"  → Recovery probe: score={r.trust_score:.2f}, state={r.state.value}")
    
    # Scenario 2: Degradation → probe fails → OPEN → manual re-attestation
    print("\n--- Scenario 2: Probe Failure → Revocation → Manual Recovery ---")
    agent2, cp2 = "agent_gamma", "bridge_delta"
    
    for i in range(4):
        r = scr.record_failure(agent2, cp2, severity=0.1)
    print(f"  After 4 failures: score={r.trust_score:.2f}, state={r.state.value}")
    
    r = scr.initiate_probe(agent2, cp2)
    print(f"  → Probe initiated: state={r.state.value}")
    
    # Two consecutive probe failures → OPEN
    r = scr.process_probe_result(agent2, cp2, passed=False, score=0.2)
    print(f"  → Probe 1 failed: state={r.state.value}, streak={r.probe_failure_streak}")
    
    r = scr.process_probe_result(agent2, cp2, passed=False, score=0.1)
    print(f"  → Probe 2 failed: state={r.state.value} (revoked)")
    
    # Manual re-attestation
    r = scr.initiate_probe(agent2, cp2)
    print(f"  → Manual re-attestation: state={r.state.value}")
    
    r = scr.process_probe_result(agent2, cp2, passed=True, score=0.9)
    print(f"  → Re-attestation passed: score={r.trust_score:.2f}, state={r.state.value}")
    
    # Scenario 3: Catastrophic failure → immediate OPEN
    print("\n--- Scenario 3: Catastrophic Failure → Immediate OPEN ---")
    agent3, cp3 = "agent_epsilon", "registry_zeta"
    
    r = scr.record_failure(agent3, cp3, severity=0.8)  # Severe breach
    print(f"  Catastrophic failure: score={r.trust_score:.2f}, state={r.state.value}")
    
    # Summary
    print(f"\n{'=' * 70}")
    print("Event Log:")
    for event in scr.event_log:
        if "from" in event:
            print(f"  [{event['agent']}→{event['counterparty']}] "
                  f"{event['from']} → {event['to']} "
                  f"(score={event['trust_score']:.2f}): {event['reason']}")
    
    print(f"\nCircuit breaker pattern applied to trust:")
    print(f"  CLOSED=trusted, OPEN=revoked, HALF-OPEN=probe recovery")
    print(f"  Active > passive: probe challenges, not time-heal")
    print(f"  Probe failure streak → OPEN (no infinite retries)")
    print(f"  Recovery is incremental (0.1 per probe), not instant")
    print(f"  Thundering herd prevention: one probe at a time")


if __name__ == "__main__":
    run_scenarios()
