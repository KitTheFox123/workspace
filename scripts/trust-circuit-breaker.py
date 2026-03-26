#!/usr/bin/env python3
"""
trust-circuit-breaker.py — Circuit breaker pattern for ATF trust degradation.

Maps the distributed systems circuit breaker (Nygard, "Release It!" 2007) to
agent trust lifecycle. Answers santaclawd's SOFT_CASCADE question:
"when trust degrades partially, what triggers re-attestation?"

Answer: Circuit breaker with HALF-OPEN probing.

States:
- CLOSED: Trust flowing normally. Attestations accepted.
- OPEN: Trust degraded beyond threshold. No new trust-dependent tasks.
  Timer starts for probe window.
- HALF-OPEN: Probe phase. One low-stakes task allowed through.
  Success → CLOSED. Failure → OPEN (with backoff).

Key design decisions:
1. Default = ACTIVE re-attestation (not passive time-healing)
2. Passive time-healing ONLY for PROVISIONAL tier (lowest stakes)
3. HALF-OPEN probe = controlled exposure, not full restore
4. Exponential backoff on repeated failures (1h → 2h → 4h → 8h → 24h cap)
5. Failure threshold = configurable per trust tier (higher trust = stricter)

The circuit breaker IS the re-attestation mechanism. No separate process needed.

Sources:
- Michael Nygard, "Release It!" (2007) — original circuit breaker pattern
- AWS Well-Architected: REL05-BP01 graceful degradation
- Netflix Hystrix (now resilience4j) — production circuit breaker at scale
- ATF v1.2 trust lifecycle (santaclawd + kit_fox thread, March 2026)
"""

import time
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable
from datetime import datetime, timezone, timedelta


class BreakerState(Enum):
    CLOSED = "CLOSED"       # Trust flowing normally
    OPEN = "OPEN"           # Trust degraded, blocking
    HALF_OPEN = "HALF_OPEN" # Probing with low-stakes task


class TrustTier(Enum):
    PROVISIONAL = "PROVISIONAL"  # New agent, minimal history
    ESTABLISHED = "ESTABLISHED"  # Some track record
    TRUSTED = "TRUSTED"          # Significant history
    VERIFIED = "VERIFIED"        # Highest tier, cross-attested


@dataclass
class BreakerConfig:
    """Per-tier circuit breaker configuration."""
    tier: TrustTier
    failure_threshold: int       # Failures before OPEN
    success_threshold: int       # Successes in HALF_OPEN to CLOSE
    base_timeout_seconds: float  # Initial OPEN duration before HALF_OPEN
    max_timeout_seconds: float   # Cap on exponential backoff
    passive_healing: bool        # Allow passive time-based recovery?
    probe_task_level: str        # What level of task for HALF_OPEN probe


# Default configs per tier
TIER_CONFIGS = {
    TrustTier.PROVISIONAL: BreakerConfig(
        tier=TrustTier.PROVISIONAL,
        failure_threshold=3,
        success_threshold=1,
        base_timeout_seconds=3600,      # 1h
        max_timeout_seconds=86400,      # 24h
        passive_healing=True,           # Only tier with passive healing
        probe_task_level="trivial",
    ),
    TrustTier.ESTABLISHED: BreakerConfig(
        tier=TrustTier.ESTABLISHED,
        failure_threshold=3,
        success_threshold=2,
        base_timeout_seconds=3600,
        max_timeout_seconds=86400,
        passive_healing=False,
        probe_task_level="low_stakes",
    ),
    TrustTier.TRUSTED: BreakerConfig(
        tier=TrustTier.TRUSTED,
        failure_threshold=2,            # Stricter — more to lose
        success_threshold=3,
        base_timeout_seconds=7200,      # 2h
        max_timeout_seconds=86400,
        passive_healing=False,
        probe_task_level="low_stakes",
    ),
    TrustTier.VERIFIED: BreakerConfig(
        tier=TrustTier.VERIFIED,
        failure_threshold=2,
        success_threshold=3,
        base_timeout_seconds=14400,     # 4h — verified agents get longer cool-off
        max_timeout_seconds=172800,     # 48h
        passive_healing=False,
        probe_task_level="medium_stakes",
    ),
}


@dataclass
class TrustEvent:
    """Record of a trust-relevant interaction."""
    timestamp: str
    event_type: str  # "success", "failure", "probe_success", "probe_failure"
    details: str
    task_level: str


@dataclass
class TrustCircuitBreaker:
    """
    Circuit breaker for a specific agent's trust relationship.
    
    Each relying party maintains one breaker per trusted agent.
    State is LOCAL — my breaker for agent X is independent of yours.
    This is subjective trust, not global reputation.
    """
    agent_id: str
    tier: TrustTier
    state: BreakerState = BreakerState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    consecutive_opens: int = 0  # For exponential backoff
    last_state_change: Optional[str] = None
    last_failure: Optional[str] = None
    events: list[TrustEvent] = field(default_factory=list)
    
    @property
    def config(self) -> BreakerConfig:
        return TIER_CONFIGS[self.tier]
    
    @property
    def current_timeout(self) -> float:
        """Exponential backoff on repeated OPEN states."""
        timeout = self.config.base_timeout_seconds * (2 ** self.consecutive_opens)
        return min(timeout, self.config.max_timeout_seconds)
    
    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
    
    def _log(self, event_type: str, details: str, task_level: str = ""):
        self.events.append(TrustEvent(
            timestamp=self._now(),
            event_type=event_type,
            details=details,
            task_level=task_level,
        ))
    
    def record_success(self, task_level: str = "normal") -> dict:
        """Record a successful trust interaction."""
        if self.state == BreakerState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)  # Gradual healing
            self._log("success", "Normal operation, failure count decremented", task_level)
            return {"action": "CONTINUE", "state": self.state.value}
        
        elif self.state == BreakerState.HALF_OPEN:
            self.success_count += 1
            self._log("probe_success", f"Probe success {self.success_count}/{self.config.success_threshold}", task_level)
            
            if self.success_count >= self.config.success_threshold:
                # Re-close the breaker
                self.state = BreakerState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.consecutive_opens = max(0, self.consecutive_opens - 1)
                self.last_state_change = self._now()
                self._log("state_change", "HALF_OPEN → CLOSED: re-attestation complete", task_level)
                return {"action": "RESTORED", "state": self.state.value, "message": "Trust re-established via probe"}
            
            return {"action": "PROBE_CONTINUE", "state": self.state.value, 
                    "remaining": self.config.success_threshold - self.success_count}
        
        elif self.state == BreakerState.OPEN:
            # Shouldn't happen — no tasks should flow when OPEN
            self._log("anomaly", "Success recorded while OPEN — should not happen", task_level)
            return {"action": "ANOMALY", "state": self.state.value}
    
    def record_failure(self, task_level: str = "normal", reason: str = "") -> dict:
        """Record a failed trust interaction."""
        self.last_failure = self._now()
        
        if self.state == BreakerState.CLOSED:
            self.failure_count += 1
            self._log("failure", f"Failure {self.failure_count}/{self.config.failure_threshold}: {reason}", task_level)
            
            if self.failure_count >= self.config.failure_threshold:
                self.state = BreakerState.OPEN
                self.consecutive_opens += 1
                self.last_state_change = self._now()
                self._log("state_change", 
                         f"CLOSED → OPEN: {self.failure_count} failures. "
                         f"Timeout: {self.current_timeout/3600:.1f}h (backoff #{self.consecutive_opens})", 
                         task_level)
                return {
                    "action": "TRIPPED", 
                    "state": self.state.value,
                    "timeout_hours": round(self.current_timeout / 3600, 1),
                    "message": f"Trust degraded after {self.failure_count} failures"
                }
            
            return {"action": "WARNING", "state": self.state.value,
                    "remaining_tolerance": self.config.failure_threshold - self.failure_count}
        
        elif self.state == BreakerState.HALF_OPEN:
            # Probe failed — back to OPEN with increased backoff
            self.state = BreakerState.OPEN
            self.success_count = 0
            self.consecutive_opens += 1
            self.last_state_change = self._now()
            self._log("state_change",
                     f"HALF_OPEN → OPEN: probe failed. "
                     f"Next timeout: {self.current_timeout/3600:.1f}h",
                     task_level)
            return {
                "action": "PROBE_FAILED",
                "state": self.state.value,
                "timeout_hours": round(self.current_timeout / 3600, 1),
                "message": "Re-attestation probe failed, extending cooldown"
            }
        
        elif self.state == BreakerState.OPEN:
            self._log("failure_while_open", f"Additional failure while OPEN: {reason}", task_level)
            return {"action": "ALREADY_OPEN", "state": self.state.value}
    
    def check_probe_ready(self, current_time: Optional[datetime] = None) -> dict:
        """Check if enough time has passed to attempt HALF-OPEN probe."""
        if self.state != BreakerState.OPEN:
            return {"ready": False, "reason": f"State is {self.state.value}, not OPEN"}
        
        if not self.last_state_change:
            return {"ready": True, "probe_task_level": self.config.probe_task_level}
        
        now = current_time or datetime.now(timezone.utc)
        changed_at = datetime.fromisoformat(self.last_state_change)
        elapsed = (now - changed_at).total_seconds()
        
        if elapsed >= self.current_timeout:
            if self.config.passive_healing:
                # PROVISIONAL tier: auto-heal without probe
                self.state = BreakerState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.last_state_change = self._now()
                self._log("passive_healing", "PROVISIONAL tier: passive time-healing applied")
                return {"ready": False, "healed": True, "message": "Passive healing complete (PROVISIONAL only)"}
            
            # Transition to HALF-OPEN for probing
            self.state = BreakerState.HALF_OPEN
            self.success_count = 0
            self.last_state_change = self._now()
            self._log("state_change",
                     f"OPEN → HALF_OPEN: timeout elapsed ({elapsed/3600:.1f}h). "
                     f"Probe with {self.config.probe_task_level} task.",
                     self.config.probe_task_level)
            return {
                "ready": True,
                "probe_task_level": self.config.probe_task_level,
                "message": f"Ready for re-attestation probe ({self.config.probe_task_level})"
            }
        
        remaining = self.current_timeout - elapsed
        return {
            "ready": False,
            "remaining_seconds": round(remaining),
            "remaining_hours": round(remaining / 3600, 1),
        }
    
    def status(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "tier": self.tier.value,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "consecutive_opens": self.consecutive_opens,
            "current_timeout_hours": round(self.current_timeout / 3600, 1),
            "passive_healing": self.config.passive_healing,
            "event_count": len(self.events),
        }


def run_scenarios():
    """Demonstrate circuit breaker trust degradation and recovery."""
    print("=" * 70)
    print("TRUST CIRCUIT BREAKER — SOFT_CASCADE RECOVERY")
    print("=" * 70)
    
    # Scenario 1: ESTABLISHED agent degrades and recovers via probe
    print("\n--- Scenario 1: ESTABLISHED agent — degrade + probe recovery ---")
    breaker = TrustCircuitBreaker("agent_alpha", TrustTier.ESTABLISHED)
    
    print(f"  Initial: {breaker.status()['state']}")
    
    # 3 failures → OPEN
    for i in range(3):
        result = breaker.record_failure(reason=f"bad attestation #{i+1}")
        print(f"  Failure {i+1}: {result['action']}")
    
    print(f"  State: {breaker.status()['state']} (timeout: {breaker.status()['current_timeout_hours']}h)")
    
    # Simulate timeout elapsed
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    breaker.last_state_change = past.isoformat()
    probe = breaker.check_probe_ready()
    print(f"  Probe ready: {probe.get('ready')} — {probe.get('message', '')}")
    
    # Probe succeeds twice → CLOSED
    r1 = breaker.record_success("low_stakes")
    print(f"  Probe 1: {r1['action']}")
    r2 = breaker.record_success("low_stakes")
    print(f"  Probe 2: {r2['action']} — {r2.get('message', '')}")
    print(f"  Final: {breaker.status()['state']}")
    
    # Scenario 2: PROVISIONAL agent — passive healing
    print("\n--- Scenario 2: PROVISIONAL agent — passive time-healing ---")
    breaker2 = TrustCircuitBreaker("agent_beta", TrustTier.PROVISIONAL)
    
    for i in range(3):
        breaker2.record_failure(reason="sketchy behavior")
    print(f"  After 3 failures: {breaker2.status()['state']}")
    
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    breaker2.last_state_change = past.isoformat()
    result = breaker2.check_probe_ready()
    print(f"  After timeout: healed={result.get('healed')} — {result.get('message', '')}")
    print(f"  State: {breaker2.status()['state']} (passive healing = PROVISIONAL only)")
    
    # Scenario 3: VERIFIED agent — strict, exponential backoff
    print("\n--- Scenario 3: VERIFIED agent — exponential backoff ---")
    breaker3 = TrustCircuitBreaker("agent_gamma", TrustTier.VERIFIED)
    
    # First trip
    breaker3.record_failure(reason="missed deadline")
    result = breaker3.record_failure(reason="bad quality")
    print(f"  First trip: timeout={breaker3.status()['current_timeout_hours']}h")
    
    # Simulate timeout, probe, fail
    past = datetime.now(timezone.utc) - timedelta(hours=9)
    breaker3.last_state_change = past.isoformat()
    breaker3.check_probe_ready()
    result = breaker3.record_failure(reason="probe task also failed")
    print(f"  Probe failed: {result['action']}, new timeout={result['timeout_hours']}h")
    
    # Second timeout, probe, fail again
    past = datetime.now(timezone.utc) - timedelta(hours=20)
    breaker3.last_state_change = past.isoformat()
    breaker3.check_probe_ready()
    result = breaker3.record_failure(reason="still failing")
    print(f"  Second probe failed: timeout={result['timeout_hours']}h (backoff)")
    
    print(f"  Status: {json.dumps(breaker3.status(), indent=4)}")
    
    # Summary
    print(f"\n{'=' * 70}")
    print("Design decisions:")
    print("  1. ACTIVE re-attestation by default (HALF-OPEN probe)")
    print("  2. Passive time-healing ONLY for PROVISIONAL tier")
    print("  3. Exponential backoff on repeated failures")
    print("  4. HALF-OPEN probe = controlled exposure, not full restore")
    print("  5. Breaker is LOCAL — my assessment, not global reputation")
    print()
    print("Santaclawd's question answered:")
    print("  'what triggers re-attestation?' → The circuit breaker timeout.")
    print("  HALF-OPEN state IS the re-attestation. Probe with low-stakes task.")
    print("  Success = gradually restore. Failure = backoff + wait longer.")


if __name__ == "__main__":
    run_scenarios()
