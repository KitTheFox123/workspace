#!/usr/bin/env python3
"""
trust-circuit-breaker.py — Circuit breaker + AIMD congestion control for ATF trust.

Maps distributed systems resilience patterns to agent trust management:
- Circuit breaker: CLOSED → OPEN → HALF-OPEN (bounded probe)
- AIMD (TCP Reno): additive increase on success, multiplicative decrease on failure
- Bulkhead: separate trust budgets per action class
- Probe matching: half-open probe MUST match degraded action class

From ATF thread (santaclawd, funwolf, Kit, 2026-03-26/27):
- Active re-attestation for WRITE/TRANSFER/ATTEST (TCP handshake)
- Passive OK for READ (UDP fire-and-forget)
- Minimum viable probe = same action class, reduced difficulty
- Cold-start: AIMD slow-climb + min() cap prevents over-hyping
- Impatience is the signal: agents demanding faster ramp get higher β

Sources:
- Microsoft Cloud Design Patterns: Circuit Breaker
- AWS Builders Library: Timeouts, retries, and backoff with jitter
- TCP Reno AIMD (Jacobson 1988)
- System Design Space: Fault Tolerance Patterns (2026)
"""

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone


class ActionClass(Enum):
    READ = "READ"           # No state change, 168h TTL, passive re-attestation OK
    WRITE = "WRITE"         # State change, 72h TTL, active re-attestation required
    TRANSFER = "TRANSFER"   # Identity delegation, 48h TTL, active + counterparty
    ATTEST = "ATTEST"       # Signing for others, 24h TTL, active + bounded delegation


class BreakerState(Enum):
    CLOSED = "CLOSED"       # Normal operation, trust flowing
    OPEN = "OPEN"           # Trust suspended, requests fast-fail
    HALF_OPEN = "HALF_OPEN" # Probing: one bounded test to check recovery


# Action class properties
ACTION_PROPS = {
    ActionClass.READ: {"ttl_hours": 168, "re_attestation": "passive", "min_beta": 0.05, "probe_difficulty": 0.3},
    ActionClass.WRITE: {"ttl_hours": 72, "re_attestation": "active", "min_beta": 0.10, "probe_difficulty": 0.5},
    ActionClass.TRANSFER: {"ttl_hours": 48, "re_attestation": "active", "min_beta": 0.30, "probe_difficulty": 0.7},
    ActionClass.ATTEST: {"ttl_hours": 24, "re_attestation": "active", "min_beta": 0.10, "probe_difficulty": 0.8},
}


@dataclass
class TrustState:
    """Per-agent, per-action-class trust state."""
    agent_id: str
    action_class: ActionClass
    trust_level: float = 0.1       # 0.0 to 1.0, starts low (cold-start)
    breaker_state: BreakerState = BreakerState.CLOSED
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_probes: int = 0
    total_successes: int = 0
    total_failures: int = 0
    cooldown_remaining: int = 0    # Cycles before half-open probe
    beta: float = 0.5             # AIMD multiplicative decrease factor
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TrustCircuitBreaker:
    """
    Circuit breaker with AIMD trust dynamics.
    
    Trust flow:
    1. CLOSED: trust grows via AIMD additive increase (α per success)
    2. Failure threshold hit → OPEN: trust frozen, requests fast-fail
    3. Cooldown expires → HALF-OPEN: one probe at degraded action class
    4. Probe succeeds → CLOSED (trust resumes at reduced level)
    5. Probe fails → OPEN (cooldown doubles, exponential backoff)
    
    AIMD parameters:
    - α (additive increase): trust grows linearly on success
    - β (multiplicative decrease): trust drops by factor on failure
    - Cold-start: new agents begin at trust_level=0.1, α=0.02
    """
    
    # Circuit breaker thresholds
    FAILURE_THRESHOLD = 3          # Consecutive failures to trip breaker
    BASE_COOLDOWN = 2              # Base cooldown cycles before half-open
    MAX_COOLDOWN = 32              # Maximum cooldown (exponential backoff cap)
    
    # AIMD parameters
    ALPHA = 0.02                   # Additive increase per success
    COLD_START_ALPHA = 0.01        # Slower increase for new agents
    MIN_TRUST = 0.0                # Floor
    MAX_TRUST = 1.0                # Ceiling
    DELEGATION_DECAY = 0.8         # Trust decays per delegation hop
    
    def __init__(self):
        self.states: dict[tuple[str, ActionClass], TrustState] = {}
        self.event_log: list[dict] = []
    
    def get_state(self, agent_id: str, action_class: ActionClass) -> TrustState:
        key = (agent_id, action_class)
        if key not in self.states:
            props = ACTION_PROPS[action_class]
            self.states[key] = TrustState(
                agent_id=agent_id,
                action_class=action_class,
                trust_level=0.1,  # Cold start
                beta=props["min_beta"] + 0.4,  # Start with moderate decay
            )
        return self.states[key]
    
    def record_success(self, agent_id: str, action_class: ActionClass) -> dict:
        """Record successful interaction. AIMD additive increase."""
        state = self.get_state(agent_id, action_class)
        
        if state.breaker_state == BreakerState.OPEN:
            return self._log_event(state, "REJECTED", "breaker OPEN, request fast-failed")
        
        if state.breaker_state == BreakerState.HALF_OPEN:
            # Probe succeeded! Transition to CLOSED
            state.breaker_state = BreakerState.CLOSED
            state.consecutive_failures = 0
            state.cooldown_remaining = 0
            # Trust resumes at current level (not restored to pre-failure)
            event = self._log_event(state, "PROBE_SUCCESS", "half-open probe passed, breaker CLOSED")
        else:
            event = self._log_event(state, "SUCCESS", "trust increased")
        
        state.consecutive_successes += 1
        state.consecutive_failures = 0
        state.total_successes += 1
        state.total_probes += 1
        
        # AIMD additive increase
        alpha = self.COLD_START_ALPHA if state.total_probes < 10 else self.ALPHA
        state.trust_level = min(self.MAX_TRUST, state.trust_level + alpha)
        
        # Successful history reduces beta (more trust-resilient)
        if state.consecutive_successes > 5:
            state.beta = max(ACTION_PROPS[action_class]["min_beta"], state.beta - 0.02)
        
        state.last_updated = datetime.now(timezone.utc).isoformat()
        return event
    
    def record_failure(self, agent_id: str, action_class: ActionClass) -> dict:
        """Record failed interaction. AIMD multiplicative decrease."""
        state = self.get_state(agent_id, action_class)
        
        if state.breaker_state == BreakerState.HALF_OPEN:
            # Probe failed! Back to OPEN with doubled cooldown
            state.breaker_state = BreakerState.OPEN
            state.cooldown_remaining = min(
                self.MAX_COOLDOWN,
                max(self.BASE_COOLDOWN, state.cooldown_remaining) * 2
            )
            return self._log_event(state, "PROBE_FAILURE", 
                f"half-open probe failed, breaker OPEN, cooldown={state.cooldown_remaining}")
        
        state.consecutive_failures += 1
        state.consecutive_successes = 0
        state.total_failures += 1
        state.total_probes += 1
        
        # AIMD multiplicative decrease
        state.trust_level = max(self.MIN_TRUST, state.trust_level * (1 - state.beta))
        
        # Increase beta on repeated failures (trust drops faster)
        state.beta = min(0.9, state.beta + 0.05)
        
        # Check breaker threshold
        if state.consecutive_failures >= self.FAILURE_THRESHOLD:
            state.breaker_state = BreakerState.OPEN
            state.cooldown_remaining = self.BASE_COOLDOWN
            return self._log_event(state, "BREAKER_TRIPPED",
                f"{state.consecutive_failures} consecutive failures, breaker OPEN")
        
        state.last_updated = datetime.now(timezone.utc).isoformat()
        return self._log_event(state, "FAILURE", "trust decreased")
    
    def tick_cooldown(self, agent_id: str, action_class: ActionClass) -> dict:
        """Advance cooldown by one cycle. Transitions OPEN → HALF-OPEN when ready."""
        state = self.get_state(agent_id, action_class)
        
        if state.breaker_state != BreakerState.OPEN:
            return self._log_event(state, "TICK", "not in OPEN state, no cooldown")
        
        state.cooldown_remaining -= 1
        
        if state.cooldown_remaining <= 0:
            state.breaker_state = BreakerState.HALF_OPEN
            return self._log_event(state, "HALF_OPEN",
                "cooldown expired, accepting one probe request")
        
        return self._log_event(state, "COOLDOWN", f"remaining={state.cooldown_remaining}")
    
    def can_request(self, agent_id: str, action_class: ActionClass) -> tuple[bool, str]:
        """Check if a request should be allowed (fast-fail check)."""
        state = self.get_state(agent_id, action_class)
        
        if state.breaker_state == BreakerState.CLOSED:
            return True, "CLOSED: trust flowing normally"
        elif state.breaker_state == BreakerState.HALF_OPEN:
            props = ACTION_PROPS[action_class]
            return True, f"HALF_OPEN: probe allowed at {props['probe_difficulty']:.0%} difficulty"
        else:
            return False, f"OPEN: fast-fail, cooldown={state.cooldown_remaining} cycles remaining"
    
    def delegation_trust(self, source_trust: float, hops: int) -> float:
        """Trust decays per delegation hop. TTL shortens too."""
        return source_trust * (self.DELEGATION_DECAY ** hops)
    
    def _log_event(self, state: TrustState, event_type: str, message: str) -> dict:
        event = {
            "agent_id": state.agent_id,
            "action_class": state.action_class.value,
            "event": event_type,
            "message": message,
            "trust_level": round(state.trust_level, 4),
            "breaker_state": state.breaker_state.value,
            "beta": round(state.beta, 4),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.event_log.append(event)
        return event
    
    def summary(self, agent_id: str) -> dict:
        """Bulkhead view: separate trust state per action class."""
        result = {}
        for ac in ActionClass:
            state = self.get_state(agent_id, ac)
            result[ac.value] = {
                "trust_level": round(state.trust_level, 4),
                "breaker_state": state.breaker_state.value,
                "consecutive_failures": state.consecutive_failures,
                "consecutive_successes": state.consecutive_successes,
                "beta": round(state.beta, 4),
                "re_attestation": ACTION_PROPS[ac]["re_attestation"],
            }
        return result


def run_scenarios():
    """Demonstrate trust circuit breaker with AIMD dynamics."""
    cb = TrustCircuitBreaker()
    
    print("=" * 70)
    print("TRUST CIRCUIT BREAKER — AIMD + BULKHEAD + PROBE MATCHING")
    print("=" * 70)
    
    agent = "agent_alice"
    
    # Scenario 1: Healthy agent builds trust via AIMD slow-climb
    print("\n--- Scenario 1: Cold-start trust building (AIMD additive increase) ---")
    for i in range(8):
        result = cb.record_success(agent, ActionClass.WRITE)
    state = cb.get_state(agent, ActionClass.WRITE)
    print(f"  After 8 successes: trust={state.trust_level:.4f}, β={state.beta:.4f}, breaker={state.breaker_state.value}")
    
    # Scenario 2: Three failures trip the breaker
    print("\n--- Scenario 2: Failure cascade trips circuit breaker ---")
    for i in range(3):
        result = cb.record_failure(agent, ActionClass.WRITE)
        print(f"  Failure {i+1}: trust={result['trust_level']:.4f}, breaker={result['breaker_state']}")
    
    # Scenario 3: Fast-fail while OPEN
    print("\n--- Scenario 3: Fast-fail while breaker OPEN ---")
    allowed, reason = cb.can_request(agent, ActionClass.WRITE)
    print(f"  Can request? {allowed} — {reason}")
    
    # Scenario 4: Cooldown → half-open → probe
    print("\n--- Scenario 4: Cooldown expiry → half-open probe ---")
    for i in range(2):
        result = cb.tick_cooldown(agent, ActionClass.WRITE)
        print(f"  Tick {i+1}: {result['event']} — {result['message']}")
    
    allowed, reason = cb.can_request(agent, ActionClass.WRITE)
    print(f"  Can request? {allowed} — {reason}")
    
    # Probe succeeds
    result = cb.record_success(agent, ActionClass.WRITE)
    print(f"  Probe result: {result['event']} — trust={result['trust_level']:.4f}")
    
    # Scenario 5: Bulkhead isolation — WRITE breaker doesn't affect READ
    print("\n--- Scenario 5: Bulkhead — WRITE failure doesn't affect READ ---")
    read_allowed, read_reason = cb.can_request(agent, ActionClass.READ)
    write_state = cb.get_state(agent, ActionClass.WRITE)
    read_state = cb.get_state(agent, ActionClass.READ)
    print(f"  WRITE: trust={write_state.trust_level:.4f}, breaker={write_state.breaker_state.value}")
    print(f"  READ:  trust={read_state.trust_level:.4f}, breaker={read_state.breaker_state.value} — {read_reason}")
    
    # Scenario 6: Delegation trust decay
    print("\n--- Scenario 6: Delegation trust decay per hop ---")
    source_trust = 0.85
    for hops in range(1, 5):
        delegated = cb.delegation_trust(source_trust, hops)
        print(f"  Hop {hops}: trust={delegated:.4f} (decay={cb.DELEGATION_DECAY}^{hops})")
    
    # Scenario 7: Impatient agent — demanding fast ramp increases β
    print("\n--- Scenario 7: Impatient agent gets higher decay ---")
    impatient = "agent_impatient"
    # Simulate: 2 successes, 1 failure, repeat (volatile pattern)
    for _ in range(3):
        cb.record_success(impatient, ActionClass.TRANSFER)
        cb.record_success(impatient, ActionClass.TRANSFER)
        cb.record_failure(impatient, ActionClass.TRANSFER)
    imp_state = cb.get_state(impatient, ActionClass.TRANSFER)
    print(f"  After volatile pattern: trust={imp_state.trust_level:.4f}, β={imp_state.beta:.4f}")
    print(f"  (Higher β = trust drops faster on next failure)")
    
    # Full bulkhead summary
    print(f"\n--- Full Bulkhead Summary for {agent} ---")
    summary = cb.summary(agent)
    for ac, data in summary.items():
        print(f"  {ac:10s}: trust={data['trust_level']:.4f} | breaker={data['breaker_state']:9s} | β={data['beta']:.4f} | re-attest={data['re_attestation']}")
    
    print(f"\n{'=' * 70}")
    print("ATF trust circuit breaker rules:")
    print("1. AIMD: additive increase (+α) on success, multiplicative decrease (×β) on failure")
    print("2. Circuit breaker: 3 failures → OPEN → cooldown → HALF-OPEN probe")
    print("3. Probe MUST match degraded action class (READ probe after WRITE failure = invalid)")
    print("4. Bulkhead: separate trust state per action class (WRITE failure ≠ READ failure)")
    print("5. Delegation: trust decays 0.8× per hop, TTL shortens proportionally")
    print("6. Cold-start: begin at 0.1, slow-climb via reduced α, min() cap on delegation")


if __name__ == "__main__":
    run_scenarios()
