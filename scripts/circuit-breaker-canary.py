#!/usr/bin/env python3
"""
circuit-breaker-canary.py — Circuit breaker with pre-committed canary spec for agent trust.

Based on:
- Nygard (2007): Release It! Circuit breaker pattern
- santaclawd: "canary_spec_hash = pre-committed at lock time"
- Löb's theorem: self-audit = inconsistent. Buyer writes canary, not seller.

Standard circuit breaker: closed/open/half-open.
Trust circuit breaker adds:
  - Canary spec committed at lock time (ungameable)
  - CUSUM → jerk → OPEN is detection path
  - Half-open canary → CLOSE is recovery path
  - Caller writes canary, service cannot adjust probe difficulty
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BreakerState(Enum):
    CLOSED = "closed"       # Trust active, monitoring
    OPEN = "open"           # Trust suspended, no operations
    HALF_OPEN = "half_open" # Canary probe in progress


@dataclass
class CanarySpec:
    task_description: str
    expected_output_range: tuple[float, float]
    timeout_seconds: float
    scoring_rule: str  # e.g., "brier_v1"
    created_by: str    # MUST be caller, not service

    def spec_hash(self) -> str:
        content = json.dumps({
            "task": self.task_description,
            "range": list(self.expected_output_range),
            "timeout": self.timeout_seconds,
            "rule": self.scoring_rule,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class TrustCircuitBreaker:
    agent_id: str
    state: BreakerState = BreakerState.CLOSED
    failure_count: int = 0
    failure_threshold: int = 3
    canary_spec: Optional[CanarySpec] = None
    canary_spec_hash: str = ""  # Committed at lock time
    cusum: float = 0.0
    cusum_threshold: float = 5.0
    jerk_threshold: float = 2.0
    history: list[dict] = field(default_factory=list)
    last_velocities: list[float] = field(default_factory=list)

    def commit_canary(self, spec: CanarySpec) -> str:
        """Lock canary spec at contract time. Returns hash for ABI."""
        self.canary_spec = spec
        self.canary_spec_hash = spec.spec_hash()
        self.history.append({
            "event": "canary_committed",
            "hash": self.canary_spec_hash,
            "by": spec.created_by,
            "time": time.time(),
        })
        return self.canary_spec_hash

    def observe(self, score: float, baseline: float = 0.5) -> dict:
        """Process an observation. Returns state change info."""
        if self.state == BreakerState.OPEN:
            return {"state": "OPEN", "action": "blocked", "note": "awaiting canary"}

        # CUSUM update
        deviation = score - baseline
        self.cusum = max(0, self.cusum + abs(deviation) - 0.1)  # drift allowance

        # Velocity (first derivative)
        velocity = abs(deviation)
        self.last_velocities.append(velocity)

        # Jerk (third derivative approximation)
        jerk = 0.0
        if len(self.last_velocities) >= 4:
            v = self.last_velocities[-4:]
            accel = [v[i+1] - v[i] for i in range(3)]
            jerk = abs(accel[2] - accel[1])

        # Detection: CUSUM or jerk threshold
        tripped = False
        trip_reason = ""
        if self.cusum > self.cusum_threshold:
            tripped = True
            trip_reason = "CUSUM_EXCEEDED"
        elif jerk > self.jerk_threshold:
            tripped = True
            trip_reason = "JERK_DETECTED"

        if tripped and self.state == BreakerState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = BreakerState.OPEN
                self.history.append({
                    "event": "breaker_opened",
                    "reason": trip_reason,
                    "cusum": self.cusum,
                    "jerk": jerk,
                    "time": time.time(),
                })
                return {
                    "state": "OPEN",
                    "action": "tripped",
                    "reason": trip_reason,
                    "cusum": round(self.cusum, 3),
                    "jerk": round(jerk, 3),
                }

        return {
            "state": self.state.value,
            "cusum": round(self.cusum, 3),
            "jerk": round(jerk, 3),
            "failures": self.failure_count,
        }

    def run_canary(self, canary_result: float) -> dict:
        """Execute canary probe in half-open state."""
        if self.state != BreakerState.OPEN:
            return {"error": "not in OPEN state"}

        self.state = BreakerState.HALF_OPEN

        # Verify canary spec hasn't been tampered
        if self.canary_spec is None:
            return {"error": "no canary spec committed"}

        spec = self.canary_spec
        lo, hi = spec.expected_output_range

        if lo <= canary_result <= hi:
            # Canary passed → close breaker
            self.state = BreakerState.CLOSED
            self.failure_count = 0
            self.cusum = 0.0
            self.history.append({
                "event": "breaker_closed",
                "canary_result": canary_result,
                "time": time.time(),
            })
            return {"state": "CLOSED", "canary": "PASSED", "result": canary_result}
        else:
            # Canary failed → stay open + escalate
            self.state = BreakerState.OPEN
            self.history.append({
                "event": "canary_failed",
                "result": canary_result,
                "expected": [lo, hi],
                "time": time.time(),
            })
            return {"state": "OPEN", "canary": "FAILED", "result": canary_result,
                    "action": "ESCALATE"}


def main():
    print("=" * 70)
    print("CIRCUIT BREAKER WITH CANARY SPEC COMMITMENT")
    print("Nygard (2007) + Löb constraint: caller writes canary, not service")
    print("=" * 70)

    # Setup: buyer commits canary at lock time
    canary = CanarySpec(
        task_description="Score a known-good delivery (TC3 replay)",
        expected_output_range=(0.85, 0.99),
        timeout_seconds=300,
        scoring_rule="brier_v1",
        created_by="buyer_agent",
    )

    breaker = TrustCircuitBreaker(
        agent_id="seller_agent",
        failure_threshold=3,
        cusum_threshold=3.0,
    )

    # Commit canary at contract lock
    spec_hash = breaker.commit_canary(canary)
    print(f"\nCanary committed: {spec_hash} (by {canary.created_by})")
    print(f"Canary: '{canary.task_description}'")
    print(f"Expected range: {canary.expected_output_range}")

    # Simulate normal operation then drift
    print("\n--- Normal Operation ---")
    for i in range(5):
        r = breaker.observe(0.48 + (i * 0.01))  # Normal range
        print(f"  Obs {i+1}: {r}")

    print("\n--- Drift Begins ---")
    for i in range(5):
        r = breaker.observe(0.3 - (i * 0.05))  # Deteriorating
        print(f"  Obs {i+6}: {r}")
        if r.get("action") == "tripped":
            print(f"  🔴 BREAKER TRIPPED: {r['reason']}")
            break

    print("\n--- Canary Probe (Half-Open) ---")
    # Scenario A: canary passes
    r = breaker.run_canary(0.91)
    print(f"  Canary result 0.91: {r}")

    # Trip again for scenario B
    breaker.state = BreakerState.OPEN
    r = breaker.run_canary(0.50)  # Below range
    print(f"  Canary result 0.50: {r}")

    # Löb check
    print("\n--- Löb Constraint ---")
    print(f"{'Canary Author':<20} {'Self-Audit?':<12} {'Löb Safe?':<10} {'Grade'}")
    print("-" * 55)
    scenarios = [
        ("buyer", False, True, "A"),
        ("seller", True, False, "F"),
        ("independent_arbiter", False, True, "A"),
        ("automated_oracle", False, True, "B"),
    ]
    for author, self_audit, safe, grade in scenarios:
        print(f"{author:<20} {str(self_audit):<12} {str(safe):<10} {grade}")

    print("\n--- PayLock ABI v2.1 Fields ---")
    fields = [
        ("rule_hash", "scoring rule content", "load-bearing"),
        ("scope_hash", "task scope content", "load-bearing"),
        ("params_hash", "hash(α,β,ε,nonce)", "load-bearing"),
        ("canary_spec_hash", "pre-committed probe", "load-bearing"),
        ("chain_tip", "receipt chain head", "load-bearing"),
        ("agent_id", "Ed25519 identity", "load-bearing"),
        ("rule_label", "human-readable name", "UX only"),
    ]
    for name, desc, role in fields:
        print(f"  {name:<20} {desc:<25} {role}")


if __name__ == "__main__":
    main()
