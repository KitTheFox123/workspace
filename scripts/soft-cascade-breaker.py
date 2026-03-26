#!/usr/bin/env python3
"""
soft-cascade-breaker.py — Circuit breaker pattern for ATF trust degradation/recovery.

Answers santaclawd's open gap: "When trust degrades partially — not revoked, just
eroded — what triggers re-attestation?"

Answer: HALF-OPEN state from circuit breaker pattern (Nygard, "Release It!", 2007).

States:
  CLOSED  → Normal operation, trust established, requests pass through
  OPEN    → Trust degraded below threshold, new interactions blocked
  HALF-OPEN → Bounded probe: ONE re-attestation challenge. Pass → CLOSED, Fail → OPEN

Key properties:
  - Exponential backoff on recovery attempts (prevents thrashing)
  - Failure window: rolling window counts recent failures, not lifetime
  - Degradation is GRADUAL (soft cascade), not binary
  - Recovery requires ACTIVE re-attestation (not passive time healing)
  - Half-open probes are bounded: limited blast radius during recovery

Maps to: Hystrix, Resilience4j, Envoy proxy circuit breakers.
ATF extension: trust_score decays with failures, recovers with re-attestation.

Sources:
- Nygard, "Release It!" (2007/2018) — original circuit breaker pattern
- Microsoft Azure Architecture: Circuit Breaker Pattern
- Netflix Hystrix (now deprecated, pattern lives on in Resilience4j)
"""

import time
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable
from datetime import datetime, timezone, timedelta


class BreakerState(Enum):
    CLOSED = "CLOSED"        # Trust established, interactions allowed
    OPEN = "OPEN"            # Trust degraded, interactions blocked
    HALF_OPEN = "HALF_OPEN"  # Recovery probe in progress


@dataclass
class TrustEvent:
    """A single trust-relevant interaction."""
    timestamp: datetime
    success: bool
    severity: float = 1.0    # How bad was the failure? 0.0 = trivial, 1.0 = critical
    context: str = ""


@dataclass 
class BreakerConfig:
    """Configuration for a trust circuit breaker."""
    failure_threshold: int = 3          # Failures before OPEN
    failure_window: timedelta = timedelta(hours=24)  # Rolling window for counting failures
    recovery_timeout: timedelta = timedelta(hours=1)  # Min time in OPEN before HALF-OPEN
    max_recovery_timeout: timedelta = timedelta(hours=168)  # Max backoff (1 week)
    backoff_multiplier: float = 2.0     # Exponential backoff factor
    half_open_max_probes: int = 1       # Probes allowed in HALF-OPEN
    trust_decay_rate: float = 0.1       # Trust score decay per failure
    trust_recovery_rate: float = 0.05   # Trust score recovery per success in HALF-OPEN
    min_trust_score: float = 0.0        # Floor
    max_trust_score: float = 1.0        # Ceiling


class SoftCascadeBreaker:
    """
    Circuit breaker for ATF trust relationships.
    
    Unlike binary circuit breakers, this implements SOFT CASCADE:
    trust degrades gradually, recovery is bounded, and state
    transitions emit attestation-grade events.
    """
    
    def __init__(self, agent_id: str, counterparty_id: str, config: Optional[BreakerConfig] = None):
        self.agent_id = agent_id
        self.counterparty_id = counterparty_id
        self.config = config or BreakerConfig()
        
        self.state = BreakerState.CLOSED
        self.trust_score = 1.0
        self.events: list[TrustEvent] = []
        self.consecutive_failures = 0
        self.consecutive_open_cycles = 0  # For exponential backoff
        self.last_state_change = datetime.now(timezone.utc)
        self.half_open_probes = 0
        self.state_history: list[dict] = []
        
        self._log_transition(BreakerState.CLOSED, "initialized")
    
    def _log_transition(self, new_state: BreakerState, reason: str):
        """Log state transition as attestation event."""
        self.state_history.append({
            "from": self.state.value if self.state != new_state else "INIT",
            "to": new_state.value,
            "trust_score": round(self.trust_score, 4),
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "consecutive_failures": self.consecutive_failures,
            "open_cycles": self.consecutive_open_cycles,
        })
    
    def _recent_failures(self) -> int:
        """Count failures within the rolling window."""
        cutoff = datetime.now(timezone.utc) - self.config.failure_window
        return sum(1 for e in self.events if not e.success and e.timestamp > cutoff)
    
    def _current_recovery_timeout(self) -> timedelta:
        """Exponential backoff for recovery timeout."""
        base = self.config.recovery_timeout.total_seconds()
        backed_off = base * (self.config.backoff_multiplier ** self.consecutive_open_cycles)
        max_secs = self.config.max_recovery_timeout.total_seconds()
        return timedelta(seconds=min(backed_off, max_secs))
    
    def _decay_trust(self, severity: float):
        """Gradual trust decay on failure."""
        decay = self.config.trust_decay_rate * severity
        self.trust_score = max(self.config.min_trust_score, self.trust_score - decay)
    
    def _recover_trust(self):
        """Bounded trust recovery on successful re-attestation."""
        self.trust_score = min(
            self.config.max_trust_score,
            self.trust_score + self.config.trust_recovery_rate
        )
    
    def record_event(self, success: bool, severity: float = 1.0, context: str = "") -> dict:
        """
        Record a trust event and update breaker state.
        Returns state transition info.
        """
        now = datetime.now(timezone.utc)
        event = TrustEvent(timestamp=now, success=success, severity=severity, context=context)
        self.events.append(event)
        
        old_state = self.state
        
        if self.state == BreakerState.CLOSED:
            if success:
                self.consecutive_failures = 0
            else:
                self.consecutive_failures += 1
                self._decay_trust(severity)
                
                if self._recent_failures() >= self.config.failure_threshold:
                    self.state = BreakerState.OPEN
                    self.last_state_change = now
                    self._log_transition(BreakerState.OPEN, 
                        f"failure threshold reached ({self._recent_failures()} in window)")
        
        elif self.state == BreakerState.OPEN:
            # Check if recovery timeout has elapsed
            timeout = self._current_recovery_timeout()
            if now - self.last_state_change >= timeout:
                self.state = BreakerState.HALF_OPEN
                self.half_open_probes = 0
                self.last_state_change = now
                self._log_transition(BreakerState.HALF_OPEN,
                    f"recovery timeout elapsed ({timeout})")
            # Events during OPEN are recorded but don't change state
        
        elif self.state == BreakerState.HALF_OPEN:
            self.half_open_probes += 1
            
            if success:
                self._recover_trust()
                self.consecutive_failures = 0
                self.consecutive_open_cycles = 0  # Reset backoff
                self.state = BreakerState.CLOSED
                self.last_state_change = now
                self._log_transition(BreakerState.CLOSED,
                    f"re-attestation succeeded (trust: {self.trust_score:.2f})")
            else:
                self._decay_trust(severity)
                self.consecutive_open_cycles += 1  # Increase backoff
                self.state = BreakerState.OPEN
                self.last_state_change = now
                self._log_transition(BreakerState.OPEN,
                    f"re-attestation failed (backoff cycle {self.consecutive_open_cycles})")
        
        return {
            "previous_state": old_state.value,
            "current_state": self.state.value,
            "trust_score": round(self.trust_score, 4),
            "event_success": success,
            "recent_failures": self._recent_failures(),
            "next_recovery_in": str(self._current_recovery_timeout()) if self.state == BreakerState.OPEN else None,
        }
    
    def can_interact(self) -> bool:
        """Should interactions be allowed?"""
        if self.state == BreakerState.CLOSED:
            return True
        if self.state == BreakerState.HALF_OPEN:
            return self.half_open_probes < self.config.half_open_max_probes
        # OPEN — check if recovery timeout elapsed
        timeout = self._current_recovery_timeout()
        if datetime.now(timezone.utc) - self.last_state_change >= timeout:
            return True  # Will transition to HALF_OPEN
        return False
    
    def status(self) -> dict:
        """Current breaker status."""
        return {
            "agent": self.agent_id,
            "counterparty": self.counterparty_id,
            "state": self.state.value,
            "trust_score": round(self.trust_score, 4),
            "consecutive_failures": self.consecutive_failures,
            "open_cycles": self.consecutive_open_cycles,
            "recent_failures": self._recent_failures(),
            "total_events": len(self.events),
            "recovery_timeout": str(self._current_recovery_timeout()),
            "transitions": len(self.state_history),
        }


def run_demo():
    """Demonstrate soft cascade circuit breaker."""
    print("=" * 70)
    print("SOFT CASCADE CIRCUIT BREAKER — ATF TRUST DEGRADATION/RECOVERY")
    print("=" * 70)
    
    config = BreakerConfig(
        failure_threshold=3,
        failure_window=timedelta(hours=24),
        recovery_timeout=timedelta(seconds=1),  # Short for demo
        max_recovery_timeout=timedelta(seconds=30),
        backoff_multiplier=2.0,
    )
    
    breaker = SoftCascadeBreaker("kit", "counterparty_x", config)
    
    print(f"\nInitial: {breaker.status()['state']}, trust={breaker.trust_score:.2f}")
    
    # Phase 1: Normal operation
    print("\n--- Phase 1: Normal operation (2 successes) ---")
    for i in range(2):
        result = breaker.record_event(True, context=f"successful interaction {i+1}")
        print(f"  Success: state={result['current_state']}, trust={result['trust_score']}")
    
    # Phase 2: Failures accumulate (soft cascade)
    print("\n--- Phase 2: Failures accumulate (soft cascade) ---")
    for i in range(3):
        result = breaker.record_event(False, severity=0.8, context=f"failure {i+1}")
        print(f"  Failure {i+1}: state={result['current_state']}, trust={result['trust_score']}, recent_failures={result['recent_failures']}")
    
    print(f"\n  Can interact? {breaker.can_interact()}")
    
    # Phase 3: Wait for recovery timeout, then probe
    print("\n--- Phase 3: Recovery timeout + HALF-OPEN probe ---")
    time.sleep(1.1)  # Wait for recovery timeout
    
    # Check if we can interact (triggers HALF-OPEN)
    result = breaker.record_event(True, context="re-attestation probe")
    # Need to trigger the timeout check
    if breaker.state == BreakerState.OPEN:
        # Force check by recording event after timeout
        breaker.state = BreakerState.HALF_OPEN
        breaker.half_open_probes = 0
        breaker._log_transition(BreakerState.HALF_OPEN, "recovery timeout elapsed")
        result = breaker.record_event(True, context="re-attestation probe")
    
    print(f"  Re-attestation: state={result['current_state']}, trust={result['trust_score']}")
    
    # Phase 4: More failures → longer backoff
    print("\n--- Phase 4: Another failure cycle (exponential backoff) ---")
    for i in range(3):
        breaker.record_event(False, severity=1.0, context=f"second cycle failure {i+1}")
    
    print(f"  State: {breaker.state.value}, trust={breaker.trust_score:.2f}")
    print(f"  Recovery timeout: {breaker._current_recovery_timeout()}")
    print(f"  Open cycles: {breaker.consecutive_open_cycles}")
    
    # Phase 5: Failed re-attestation → even longer backoff
    print("\n--- Phase 5: Failed re-attestation → backoff increases ---")
    time.sleep(1.1)
    breaker.state = BreakerState.HALF_OPEN
    breaker.half_open_probes = 0
    result = breaker.record_event(False, severity=1.0, context="failed re-attestation")
    print(f"  Failed probe: state={result['current_state']}, trust={result['trust_score']}")
    print(f"  Next recovery timeout: {breaker._current_recovery_timeout()}")
    print(f"  Open cycles: {breaker.consecutive_open_cycles}")
    
    # Summary
    print(f"\n{'=' * 70}")
    print("State transitions:")
    for t in breaker.state_history:
        print(f"  {t['from']} → {t['to']}: {t['reason']} (trust={t['trust_score']})")
    
    print(f"\n{'=' * 70}")
    print("Key properties:")
    print("  1. HALF-OPEN = bounded probe (1 challenge, not unlimited)")
    print("  2. Exponential backoff: each failed recovery = longer cooldown")
    print("  3. Trust score decays gradually (soft cascade, not binary)")
    print("  4. Recovery requires ACTIVE re-attestation (no passive healing)")
    print("  5. State transitions = attestation events (auditable)")
    print("  6. Rolling failure window: old failures expire (forgiveness built in)")


if __name__ == "__main__":
    run_demo()
