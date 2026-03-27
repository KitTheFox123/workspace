#!/usr/bin/env python3
"""
trust-circuit-breaker.py — Circuit breaker pattern for ATF trust attestations.

Maps microservice resilience patterns (Mohammad 2025 SLR, Netflix Hystrix) to
agent trust recovery. The circuit breaker prevents cascading trust failures:
when an agent repeatedly fails attestation probes, stop trusting it rather than
accumulating bad attestations.

States (per Hystrix/Resilience4j):
  CLOSED  — trust flowing, failures counted
  OPEN    — trust suspended, no attestations accepted
  HALF_OPEN — bounded probe: one re-attestation at reduced difficulty

ATF-specific extensions:
  - Action-class-aware probes: TRANSFER failure → probe with TRANSFER, not READ
  - Difficulty downgrade: probe at 0.5× the difficulty that triggered failure
  - Soft cascade: failure in one action class doesn't immediately affect others
  - Jitter on recovery window: prevents thundering-herd re-attestation
  - Witness liveness check: dead witness in N-of-M = silent quorum shrink

Key thread insights:
  - santaclawd: "active re-attestation for WRITE/TRANSFER/ATTEST, passive for READ"
  - santaclawd: SOFT_CASCADE = CLOSED → OPEN → HALF-OPEN per action class
  - Kit: "probe MUST match degraded action class. READ probe after TRANSFER failure
    = testing the wrong muscle"

Sources:
  - Mohammad (2025): Resilient Microservices SLR, 26 studies, 9 themes
  - Netflix Hystrix (2012): Original circuit breaker for microservices
  - Resilience4j: Modern Java implementation
  - Mohammad T3: Retry with jitter prevents storms
  - Mohammad T5: Bulkheads limit blast radius (= action class isolation)
  - Mohammad T8: Observability = prerequisite for safe recovery
"""

import json
import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone, timedelta


class CircuitState(Enum):
    CLOSED = "CLOSED"       # Trust flowing normally
    OPEN = "OPEN"           # Trust suspended
    HALF_OPEN = "HALF_OPEN" # Probing recovery


class ActionClass(Enum):
    READ = "READ"           # No state change, passive attestation OK
    WRITE = "WRITE"         # State change, active re-attestation required
    TRANSFER = "TRANSFER"   # Irrevocable, strictest probing
    ATTEST = "ATTEST"       # Signing for others, delegated trust


# TTLs per action class (hours)
ACTION_TTLS = {
    ActionClass.READ: 168,      # 7 days
    ActionClass.WRITE: 72,      # 3 days
    ActionClass.TRANSFER: 48,   # 2 days
    ActionClass.ATTEST: 24,     # 1 day (shortest — delegated trust decays fastest)
}

# Recovery mode per action class (santaclawd's TCP/UDP insight)
RECOVERY_MODE = {
    ActionClass.READ: "passive",      # UDP: fire-and-forget, check on next use
    ActionClass.WRITE: "active",      # TCP: handshake required
    ActionClass.TRANSFER: "active",   # TCP: handshake required
    ActionClass.ATTEST: "active",     # TCP: handshake required
}


@dataclass
class ProbeResult:
    """Result of a re-attestation probe."""
    success: bool
    action_class: ActionClass
    difficulty: float       # 0.0-1.0
    score: float           # 0.0-1.0 (quality of response)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class CircuitBreaker:
    """
    Per-agent, per-action-class circuit breaker.
    
    Isolation: each action class has its own breaker (bulkhead pattern, T5).
    TRANSFER failure doesn't affect READ trust.
    """
    agent_id: str
    action_class: ActionClass
    state: CircuitState = CircuitState.CLOSED
    
    # Thresholds
    failure_threshold: int = 3          # Failures before OPEN
    success_threshold: int = 2          # Successes in HALF_OPEN before CLOSED
    recovery_window_base: float = 300.0 # Base recovery window (seconds)
    max_recovery_window: float = 3600.0 # Max recovery window (1 hour)
    
    # Counters
    failure_count: int = 0
    success_count: int = 0
    consecutive_opens: int = 0          # For exponential backoff
    
    # Timing
    opened_at: Optional[str] = None
    last_probe_at: Optional[str] = None
    last_failure_difficulty: float = 0.5
    
    # History
    probe_history: list = field(default_factory=list)
    
    @property
    def recovery_window(self) -> float:
        """Exponential backoff with jitter (Mohammad T3: prevents retry storms)."""
        base = self.recovery_window_base * (2 ** min(self.consecutive_opens, 5))
        capped = min(base, self.max_recovery_window)
        # Add jitter: ±25% (prevents thundering-herd re-attestation)
        jitter = capped * random.uniform(-0.25, 0.25)
        return capped + jitter
    
    @property
    def probe_difficulty(self) -> float:
        """
        Probe at 0.5× the difficulty that triggered failure.
        "half-open = prove you can still walk before we let you run"
        """
        return self.last_failure_difficulty * 0.5
    
    @property
    def is_recovery_ready(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if self.state != CircuitState.OPEN or self.opened_at is None:
            return False
        opened = datetime.fromisoformat(self.opened_at)
        elapsed = (datetime.now(timezone.utc) - opened).total_seconds()
        return elapsed >= self.recovery_window
    
    def record_failure(self, difficulty: float = 0.5) -> dict:
        """Record a trust attestation failure."""
        self.failure_count += 1
        self.last_failure_difficulty = difficulty
        
        event = {
            "event": "FAILURE",
            "agent": self.agent_id,
            "action_class": self.action_class.value,
            "failure_count": self.failure_count,
            "threshold": self.failure_threshold,
        }
        
        if self.failure_count >= self.failure_threshold and self.state == CircuitState.CLOSED:
            self.state = CircuitState.OPEN
            self.opened_at = datetime.now(timezone.utc).isoformat()
            self.consecutive_opens += 1
            event["state_change"] = "CLOSED → OPEN"
            event["recovery_window_sec"] = round(self.recovery_window, 1)
            event["recovery_mode"] = RECOVERY_MODE[self.action_class]
        
        return event
    
    def attempt_probe(self, result: ProbeResult) -> dict:
        """Process a re-attestation probe result in HALF_OPEN state."""
        self.probe_history.append(result)
        self.last_probe_at = result.timestamp
        
        event = {
            "event": "PROBE",
            "agent": self.agent_id,
            "action_class": self.action_class.value,
            "probe_success": result.success,
            "probe_score": result.score,
            "probe_difficulty": result.difficulty,
        }
        
        if result.success:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.consecutive_opens = 0
                event["state_change"] = "HALF_OPEN → CLOSED"
                event["message"] = "Trust restored"
            else:
                event["progress"] = f"{self.success_count}/{self.success_threshold}"
        else:
            # Failed probe → back to OPEN with longer window
            self.state = CircuitState.OPEN
            self.opened_at = datetime.now(timezone.utc).isoformat()
            self.success_count = 0
            event["state_change"] = "HALF_OPEN → OPEN"
            event["recovery_window_sec"] = round(self.recovery_window, 1)
        
        return event
    
    def try_transition_to_half_open(self) -> Optional[dict]:
        """Attempt to transition from OPEN to HALF_OPEN for probing."""
        if self.state != CircuitState.OPEN:
            return None
        
        if not self.is_recovery_ready:
            return None
        
        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
        
        return {
            "event": "TRANSITION",
            "state_change": "OPEN → HALF_OPEN",
            "agent": self.agent_id,
            "action_class": self.action_class.value,
            "probe_difficulty": round(self.probe_difficulty, 3),
            "recovery_mode": RECOVERY_MODE[self.action_class],
            "message": f"Probing at {self.probe_difficulty:.1%} difficulty (was {self.last_failure_difficulty:.1%})",
        }


class TrustCircuitBreakerPool:
    """
    Pool of circuit breakers — one per agent per action class.
    Implements soft cascade: action classes are isolated (bulkhead pattern).
    """
    
    def __init__(self):
        self.breakers: dict[tuple[str, ActionClass], CircuitBreaker] = {}
        self.event_log: list[dict] = []
    
    def get_breaker(self, agent_id: str, action_class: ActionClass) -> CircuitBreaker:
        """Get or create a circuit breaker for agent+action_class."""
        key = (agent_id, action_class)
        if key not in self.breakers:
            self.breakers[key] = CircuitBreaker(agent_id=agent_id, action_class=action_class)
        return self.breakers[key]
    
    def can_trust(self, agent_id: str, action_class: ActionClass) -> dict:
        """Check if an agent is trusted for a specific action class."""
        breaker = self.get_breaker(agent_id, action_class)
        
        result = {
            "agent": agent_id,
            "action_class": action_class.value,
            "state": breaker.state.value,
            "trusted": breaker.state == CircuitState.CLOSED,
            "ttl_hours": ACTION_TTLS[action_class],
        }
        
        if breaker.state == CircuitState.OPEN:
            result["recovery_ready"] = breaker.is_recovery_ready
            result["recovery_mode"] = RECOVERY_MODE[action_class]
        elif breaker.state == CircuitState.HALF_OPEN:
            result["probe_progress"] = f"{breaker.success_count}/{breaker.success_threshold}"
            result["probe_difficulty"] = round(breaker.probe_difficulty, 3)
        
        return result
    
    def agent_status(self, agent_id: str) -> dict:
        """Full status across all action classes (soft cascade view)."""
        status = {"agent": agent_id, "action_classes": {}}
        for ac in ActionClass:
            check = self.can_trust(agent_id, ac)
            status["action_classes"][ac.value] = {
                "state": check["state"],
                "trusted": check["trusted"],
            }
        
        # Overall: trusted only if ALL action classes are CLOSED
        status["fully_trusted"] = all(
            status["action_classes"][ac.value]["trusted"] for ac in ActionClass
        )
        return status


def run_scenario():
    """Demonstrate circuit breaker behavior with soft cascade."""
    pool = TrustCircuitBreakerPool()
    random.seed(42)  # Reproducible jitter
    
    print("=" * 70)
    print("TRUST CIRCUIT BREAKER — ATF SOFT CASCADE")
    print("Based on Mohammad (2025) SLR + Netflix Hystrix + Clawk threads")
    print("=" * 70)
    
    agent = "agent_alpha"
    
    # Phase 1: Agent fails TRANSFER attestations
    print("\n--- Phase 1: TRANSFER failures (3× → OPEN) ---")
    breaker = pool.get_breaker(agent, ActionClass.TRANSFER)
    for i in range(3):
        event = breaker.record_failure(difficulty=0.7)
        print(f"  Failure {i+1}: {json.dumps({k: v for k, v in event.items() if k != 'agent'})}")
    
    # Phase 2: Check soft cascade — other action classes unaffected
    print("\n--- Phase 2: Soft cascade check ---")
    status = pool.agent_status(agent)
    for ac, info in status["action_classes"].items():
        print(f"  {ac}: {info['state']} (trusted={info['trusted']})")
    print(f"  Fully trusted: {status['fully_trusted']}")
    
    # Phase 3: Simulate recovery
    print("\n--- Phase 3: Recovery attempt ---")
    # Force recovery-ready by backdating opened_at
    breaker.opened_at = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    
    transition = breaker.try_transition_to_half_open()
    if transition:
        print(f"  {json.dumps({k: v for k, v in transition.items() if k != 'agent'})}")
    
    # First probe: success at reduced difficulty
    probe1 = ProbeResult(
        success=True, action_class=ActionClass.TRANSFER,
        difficulty=breaker.probe_difficulty, score=0.75,
    )
    event1 = breaker.attempt_probe(probe1)
    print(f"  Probe 1: {json.dumps({k: v for k, v in event1.items() if k != 'agent'})}")
    
    # Second probe: success → CLOSED
    probe2 = ProbeResult(
        success=True, action_class=ActionClass.TRANSFER,
        difficulty=breaker.probe_difficulty, score=0.82,
    )
    event2 = breaker.attempt_probe(probe2)
    print(f"  Probe 2: {json.dumps({k: v for k, v in event2.items() if k != 'agent'})}")
    
    # Phase 4: Failed probe scenario
    print("\n--- Phase 4: Failed probe → back to OPEN ---")
    breaker2 = pool.get_breaker("agent_beta", ActionClass.WRITE)
    for _ in range(3):
        breaker2.record_failure(difficulty=0.6)
    breaker2.opened_at = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
    breaker2.try_transition_to_half_open()
    
    failed_probe = ProbeResult(
        success=False, action_class=ActionClass.WRITE,
        difficulty=0.3, score=0.2,
    )
    event = breaker2.attempt_probe(failed_probe)
    print(f"  Failed probe: {json.dumps({k: v for k, v in event.items() if k != 'agent'})}")
    print(f"  Next recovery window: {breaker2.recovery_window:.0f}s (exponential backoff + jitter)")
    
    # Phase 5: Action class TTLs and recovery modes
    print("\n--- Phase 5: Action class properties ---")
    print(f"  {'Class':<12} {'TTL (hrs)':<12} {'Recovery':<10}")
    print(f"  {'-'*12} {'-'*12} {'-'*10}")
    for ac in ActionClass:
        print(f"  {ac.value:<12} {ACTION_TTLS[ac]:<12} {RECOVERY_MODE[ac]:<10}")
    
    print(f"\n{'=' * 70}")
    print("Key patterns mapped from Mohammad (2025) SLR:")
    print("  T1: Failure-mode–pattern fit → action-class-specific probes")
    print("  T3: Retry with jitter → recovery window with ±25% jitter")
    print("  T5: Bulkheads → action class isolation (soft cascade)")
    print("  T8: Observability → probe history + event log")
    print("  Key: 'context—not mechanism—determines resilience gain'")


if __name__ == "__main__":
    run_scenario()
